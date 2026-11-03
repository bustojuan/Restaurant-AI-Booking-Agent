# BARIA desktop application

Electron, React and TypeScript provide the English booking application and the
independent dark-mode AI Control Center. The renderer uses typed preload bridges;
API tokens remain in Electron Main/backend. No browser-only deployment is implied.

See [installation](../INSTALLATION.md), [configuration](../CONFIGURATION.md),
[API contracts](../backend/docs/frontend-api.md) and [release validation](../TEST_REPORT.md).

From this directory, after root setup:

```powershell
npm.cmd run dev
npm.cmd run build
npm.cmd start
npm.cmd run start:admin
npm.cmd test
npm.cmd run test:e2e
```

The backend must already be running. `npm.cmd run package` produces an unsigned
Windows directory build; the Python backend remains a separate local process.
The source release is validated on Windows 11 with Node.js 24.

## Test isolation

Playwright starts `tests/start-backend.py` with a fresh temporary SQLite database,
fixed non-production test tokens, deterministic extraction and all paid providers
disabled. Live catalog snapshots are optional and are not distributed.

For Windows environments where automatic process-tree termination hangs, run the
isolated test server in a separate terminal, then set
`BARIA_E2E_EXTERNAL_SERVER=1` in the test terminal. Never point this option at a
personal backend; the suite assumes the fixed isolated test credentials/port.

```powershell
../.venv/Scripts/python.exe tests/start-backend.py
```

In another terminal in `frontend/`:

```powershell
$env:BARIA_E2E_EXTERNAL_SERVER = '1'
npm.cmd run test:e2e
```

Stop that server with Ctrl+C when tests finish and remove the environment variable
before returning to automatic startup. The harness uses the application's default Uvicorn transport. SQLite page reads in
WebSocket handlers run on worker threads so pool contention cannot block the ASGI loop.

For a freshly installed local demonstration only,
`node scripts/release-smoke.mjs http://127.0.0.1:8001` creates a three-attempt
simulation and verifies the actual Electron booking/admin windows, graph and
timeline. It rejects enabled voice/telephony or paid extraction configuration.
Receipts and screenshots stay in ignored `.release-validation/`.
