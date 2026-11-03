# Install BARIA on Windows 11

Install **Node.js 24 LTS** and
[uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.14 can be
provisioned automatically by uv; VS Code and Git are not required when using a
downloaded ZIP. Python source supports 3.12+, but this release is
validated with 3.14.3. Dependencies are pinned in the committed locks; no paid
provider account is needed for the default demonstration.

## Quick setup

Clone the published repository or extract its ZIP, then open its root in Explorer:

1. Double-click **`Instalar.cmd`** once. Internet is required for dependencies.
   The window stays open and reports success or a missing prerequisite.
2. Double-click **`Iniciar BARIA.cmd`** for daily use. No separate terminal
   commands are needed. It waits for backend readiness before opening Electron.
3. Close all booking and AI Control Center windows to finish. The launcher
   gracefully shuts down its own backend and closes its console.

Keep the launcher's console open during use. A second launch from this folder
reports that BARIA is already running. If another service occupies the configured
port, it reports the conflict without stopping or attaching to that service.
Data, credentials and configuration survive normal shutdown and repeated setup.
The launcher stores its desktop profile separately in ignored `.desktop-profile/`.

After updating source code, run **`Instalar.cmd`** again to rebuild dependencies
and desktop assets. Daily startup does not reinstall or rebuild the application.

Command-line equivalent for installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Setup creates `.venv/`, installs locked backend and frontend packages, creates
`backend/.env` with **two distinct random tokens**, runs Alembic from an empty
database, and builds Electron. It preserves an existing `.env`; it never copies
development credentials or history. SQLite/checkpoints and mock restaurants are
initialized by migration and first application startup. Do not share the generated
`.env`, databases or Electron profile.

Command-line equivalent for daily startup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch-app.ps1
```

For development or diagnostics, the existing separate-process commands remain
available. Do not run these alongside the combined launcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-backend.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-app.ps1
```

Open AI Control Center through the application's navigation. With an independently
managed backend, it can also be opened directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-app.ps1 -Admin
```

Backend health: <http://127.0.0.1:8001/api/health>. Interactive API schema:
<http://127.0.0.1:8001/docs>. Privileged API requests require their respective
bearer token. Credentials are read by Electron Main, never placed in the renderer.
Run **one** backend executor per database; do not use multiple Uvicorn workers.

## First booking

Select the clearly marked simulated restaurants, arrange their priority, and enter
a future reservation date, 21:00 and four guests. Start a **simulation** with the
priority-success scenario. The deterministic example contacts three candidates:
unavailable, incompatible alternative, then explicit simulated confirmation.
Inspect the result in the main app and the recorded run in AI Control Center.

An API-driven equivalent, with the backend running:

```powershell
Set-Location backend
../.venv/Scripts/python.exe -m scripts.demo_booking --mode ai_simulation
```

Mock restaurants are fixtures, not evidence of live availability. The interactive
map downloads public map tiles; the mock restaurant list and simulation work
without OpenAI or Twilio. Optional real catalog imports are described in
[backend/docs/restaurant-catalog.md](backend/docs/restaurant-catalog.md).

## Optional isolated history (up to 300 contact attempts)

This generates **new recorded simulations**, never fabricated customer history.
It refuses to replace an existing directory and does not read `backend/.env`.
One priority-success booking has three completed attempts. Use 100 bookings for
300 attempts; generation may take several minutes on synchronized storage.

```powershell
Set-Location backend
../.venv/Scripts/python.exe -m scripts.generate_demo --directory ../.demo/archive --bookings 100
```

To inspect this archive, stop your existing backend, then from `backend/` run:

```powershell
../.venv/Scripts/python.exe -m scripts.serve_demo --directory ../.demo/archive
```

From a second terminal in the root, point Electron Main to the isolated credentials:

```powershell
$env:BARIA_BACKEND_ENV = (Resolve-Path '.demo/archive/.env').Path
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-app.ps1 -Admin
```

Close those windows and remove `BARIA_BACKEND_ENV` from that terminal before
returning to the normal database. No full archive is required for normal use.

## Tests and video source

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -WithVideo
powershell -NoProfile -ExecutionPolicy Bypass -File video/run.ps1 studio
```

The approved export is already available in `docs/media/`; rendering it is optional.
See [TEST_REPORT.md](TEST_REPORT.md) for executed checks and [video/README.md](video/README.md).

## Common errors

| Symptom                                     | Resolution                                                                           |
| ------------------------------------------- | ------------------------------------------------------------------------------------ |
| `node` or `uv` not found                    | Install the prerequisite and reopen PowerShell.                                      |
| Desktop files missing / environment missing | Run `Instalar.cmd`, then `Iniciar BARIA.cmd`.                                        |
| BARIA already starting or running           | Switch to its existing window, or close its windows before restarting.               |
| Backend startup failed                      | Run `scripts/start-backend.ps1` separately for diagnostics.                          |
| Python cannot be located                    | Install Python 3.14; check `py -3.14 --version`, or allow uv to provision it.        |
| OneDrive hardlink error                     | Use the included setup script, which sets uv copy mode.                              |
| Missing SQLite schema                       | Run `scripts/init-db.ps1`, then restart the backend.                                 |
| Port 8001 occupied / executor lock          | Stop the other backend; do not share a live DB between executors.                    |
| Admin unauthorized                          | Ensure distinct local/admin tokens; restart backend and Electron after changes.      |
| Electron runs like Node                     | Remove `ELECTRON_RUN_AS_NODE`; the launcher does this automatically.                 |
| Map has no tiles                            | Check internet access to the configured map style; use restaurant list view offline. |
| npm install download fails                  | Check registry/proxy access; retry `npm.cmd ci` in the failing project.              |

All paths are relative. No original developer environment, catalog cache, private
database or portable runtime is included or required.
