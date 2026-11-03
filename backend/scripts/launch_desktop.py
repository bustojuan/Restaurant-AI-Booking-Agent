"""Start the local desktop and its own backend, with bounded graceful cleanup."""

import argparse
import http.client
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from filelock import FileLock, Timeout
from pydantic import ValidationError

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def require_free_port(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host, port))
        except OSError:
            raise RuntimeError(
                f"Port {port} is already in use. Close the other backend, or set PORT in backend/.env. "
                "No existing process has been stopped."
            ) from None


def wait_ready(process: subprocess.Popen, host: str, port: int, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The backend could not start. Run scripts/start-backend.ps1 for diagnostics.")
        connection = http.client.HTTPConnection(host, port, timeout=1)
        try:
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            if response.status == 200 and process.poll() is None:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(0.2)
    raise RuntimeError("Backend startup timed out. Run scripts/start-backend.ps1 for diagnostics.")


def stop_backend(process: subprocess.Popen) -> None:
    # Closing the private control pipe asks Uvicorn to run its normal lifespan shutdown.
    if process.stdin:
        process.stdin.close()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.terminate()  # Only this launcher's child; never an existing service.
        process.wait(timeout=10)


def serve_backend() -> None:
    import uvicorn

    from app.main import create_app

    settings = Settings()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            access_log=False,
            log_level="warning",
        )
    )

    def watch_parent():
        sys.stdin.buffer.read(1)
        server.should_exit = True

    threading.Thread(target=watch_parent, daemon=True).start()
    server.run()


def launch() -> int:
    from app.migrate import upgrade

    os.chdir(ROOT / "backend")
    if not Path(".env").is_file():
        raise RuntimeError("Run Instalar.cmd once before starting BARIA.")
    settings = Settings()
    if settings.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("The desktop launcher requires HOST=127.0.0.1 or localhost in backend/.env.")
    electron = ROOT / "frontend/node_modules/electron/dist/electron.exe"
    if not electron.is_file() or not (ROOT / "frontend/out/main/index.js").is_file():
        raise RuntimeError("Desktop files are missing. Run Instalar.cmd to install and build BARIA.")
    lock = FileLock(str(ROOT / ".desktop.launcher.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise RuntimeError("BARIA is already starting or running from this folder.") from None
    try:
        require_free_port(settings.host, settings.port)
        print("Preparing the local database...", flush=True)
        upgrade(settings.database_url)
        print("Starting the backend...", flush=True)
        backend = subprocess.Popen(
            [sys.executable, "-m", "scripts.launch_desktop", "--backend"],
            cwd=ROOT / "backend",
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        desktop = None
        try:
            wait_ready(backend, settings.host, settings.port)
            env = os.environ.copy()
            for key in ("ELECTRON_RUN_AS_NODE", "BARIA_ADMIN_ONLY", "ELECTRON_RENDERER_URL"):
                env.pop(key, None)
            env["BARIA_BACKEND_ENV"] = str(ROOT / "backend/.env")
            env["BARIA_BACKEND_URL"] = f"http://127.0.0.1:{settings.port}"
            env["LOCAL_API_TOKEN"] = settings.local_api_token.get_secret_value()
            env["ADMIN_API_TOKEN"] = (
                settings.admin_api_token.get_secret_value() if settings.admin_api_token else ""
            )
            env.setdefault("BARIA_USER_DATA", str(ROOT / ".desktop-profile"))
            print("Opening BARIA. Close all BARIA windows to stop its backend.", flush=True)
            desktop = subprocess.Popen(
                [str(electron), "."],
                cwd=ROOT / "frontend",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while desktop.poll() is None:
                if backend.poll() is not None:
                    raise RuntimeError("The backend stopped unexpectedly. Close BARIA and restart it.")
                time.sleep(0.25)
            if desktop.returncode:
                raise RuntimeError(
                    "Electron could not run. Run Instalar.cmd again to repair its installation."
                )
        finally:
            if desktop and desktop.poll() is None:
                # Only the process tree created above, never another BARIA instance.
                subprocess.run(
                    ["taskkill.exe", "/PID", str(desktop.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                desktop.wait(timeout=10)
            print("Stopping BARIA's backend...", flush=True)
            stop_backend(backend)
    finally:
        lock.release()
    print("BARIA closed.", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.backend:
            serve_backend()
            return 0
        return launch()
    except KeyboardInterrupt:
        print("BARIA startup cancelled.")
        return 1
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors())
        print(f"Invalid backend/.env configuration ({fields}). Values have not been printed.")
        return 1
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 1
    except Exception as error:  # noqa: BLE001 -- startup diagnostics must never print secret-bearing values
        print(f"BARIA could not start ({type(error).__name__}). See INSTALLATION.md.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
