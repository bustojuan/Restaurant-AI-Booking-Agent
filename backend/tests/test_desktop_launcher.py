"""The desktop launcher must not stop other services or abandon its own executor."""

import socket
import subprocess
import sys
from pathlib import Path

import pytest
from filelock import FileLock

from app.migrate import upgrade
from scripts.launch_desktop import require_free_port, stop_backend, wait_ready


def test_occupied_port_is_rejected_without_stopping_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match="already in use"):
            require_free_port("127.0.0.1", port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_exited_backend_fails_without_waiting_for_timeout():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=5)
    with pytest.raises(RuntimeError, match="could not start"):
        wait_ready(process, "127.0.0.1", 1, timeout=30)


def test_control_pipe_closes_real_backend_and_releases_executor(tmp_path, monkeypatch):
    database = tmp_path / "launcher.db"
    upgrade(f"sqlite:///{database}")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    for name, value in {
        "DATABASE_URL": f"sqlite:///{database}",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "LOCAL_API_TOKEN": "launcher-test-local-token-at-least-24",
        "ADMIN_API_TOKEN": "launcher-test-admin-token-at-least-24",
        "AI_EXTRACTION_MODE": "deterministic",
        "VOICE_SANDBOX_ENABLED": "false",
        "REAL_TELEPHONY_ENABLED": "false",
        "LANGSMITH_TRACING_ENABLED": "false",
    }.items():
        monkeypatch.setenv(name, value)
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.launch_desktop", "--backend"],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_ready(process, "127.0.0.1", port, timeout=45)
    finally:
        stop_backend(process)
    assert process.returncode == 0
    require_free_port("127.0.0.1", port)
    with FileLock(str(database) + ".executor.lock", timeout=0):
        pass
