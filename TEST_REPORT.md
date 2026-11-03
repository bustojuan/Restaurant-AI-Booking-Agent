# Release validation report

## Windows double-click startup (3 November 2026)

`Instalar.cmd` was executed in a new independent folder: dependency installation,
private configuration, database migration and desktop build succeeded. The
installer now explicitly provisions Electron's executable instead of deferring
its download to daily startup; that provisioning command also succeeded.
`Iniciar BARIA.cmd` then opened the actual visible Electron application against
its own local backend. A duplicate launch was rejected. Closing the window exited
with code 0, stopped that backend and released its listening port.

The three launcher regression tests passed, covering occupied-port safety,
early backend exit and real backend shutdown through the private control pipe.
Ruff and PowerShell syntax checks passed. No original application was modified
and no paid provider was enabled. See the
[launcher validation receipt](docs/validation/windows-launcher.json).

The full backend batch reported 158 passed and two failures: existing LangGraph
integration tests exceeded their 15-second wait while the fresh installation
was running. Both passed on an isolated recheck (2/2). This is not reported as
one uninterrupted green 160-test run; no booking policy or test timeout was
changed to make the checks pass.

Date: 3 November 2026. Target: Windows 11; execution environment reported Windows
NT 10.0.26200.0, CPython 3.14.3, Node.js 24.22.2, npm 11.19.1, uv 0.11.1 and
Git 2.53.0.windows.2. All application validation ran in the independent release
folder, never in the development project. A second staged export used its own
fresh virtual environment, npm installation, environment files and database.
Registry/download caches and standard runtimes are distinct from reusing original
application dependencies; no original node_modules, virtualenv, database, env or
build output was used.

## Final result

FINAL_RESULTS_PENDING

Machine-readable sanitized receipts are in [docs/validation](docs/validation).
Raw traces, test databases, profiles, credentials and logs remain excluded.

## Commands and coverage

From `backend/` with the release interpreter:

```powershell
../.venv/Scripts/python.exe -m compileall -q app scripts tests alembic
../.venv/Scripts/python.exe -m ruff check .
../.venv/Scripts/python.exe -m ruff format --check .
../.venv/Scripts/python.exe -m pytest -q --junitxml=../.release-validation/backend.xml
../.venv/Scripts/python.exe -m scripts.export_contracts
../.venv/Scripts/python.exe -m scripts.evaluate_ai --output ../docs/validation/ai-evaluation.json
../.venv/Scripts/python.exe -m scripts.voice_preflight
```

Backend coverage includes versioned drafts and autosave; positional/atomic queue
edits and duplicate/concurrent mutation rejection; catalog, identity and images;
sequential booking, alternatives, mandatory rules and financial approvals;
confirmation evidence, failed/ambiguous outcomes and recovery; LangGraph routing,
scoped tools, checkpoint resume, terminal summaries and evaluations; admin auth,
persisted events, graphs, purged cursors, explanations and replay projections.
Tests use on-disk SQLite and Alembic initialization. Generated contracts match the
original schemas; the concurrency correction changes no endpoint or contract.

The added regressions stall an observation read and background maintenance,
and a concurrent reader/writer snapshot, while verifying API responsiveness and
writer completion. Profiling identified
blocking pool checkout in the administrative WebSocket and a synchronous SQLite
maintenance commit on the ASGI main thread. Storage work now runs on worker
threads; supervisor shutdown waits for in-flight work before releasing ownership.
Application SQLite now uses WAL with synchronous=FULL and independent short-lived
connections to avoid read/write contention and bounded-pool starvation. BEGIN
IMMEDIATE/versioned mutations, booking decisions, graph routes and prompts are
unchanged.

From `frontend/`:

```powershell
npx.cmd prettier --check .
node --check scripts/admin.mjs
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e -- --reporter=list,json
```

Prettier is the repository's existing style check; no unrelated ESLint framework
was introduced. Production build includes TypeScript validation, Main, preload
and renderer. Electron coverage includes actual windows/bridge isolation,
restaurant map/list and drag/drop, saved ordering, drafts, autosave/concurrency,
approvals/cancellation, admin/main navigation, call history/detail, graph,
inspector, timeline, replay, analytics, Playground, settings and denied access.
Visual capture tests exercise 1440×900 and 1920×1080; main layout tests additionally
exercise the existing desktop sizes. One optional OSM snapshot test requires the
excluded local catalog cache; it is intentionally skipped without that input.

From `video/`, using freshly installed locked Remotion dependencies:

```powershell
npm.cmd run check
node scripts/captions.mjs --check
node scripts/validate.mjs ../docs/media/ai-restaurant-booker-demo.mp4
```

The approved MP4 passed metadata/source checks and full H.264/AAC decode. It has
1920×1080 picture, 30 fps, 5,850 frames and 195.008-second container duration.
46 English subtitle cues pass alignment/overlap checks; sidecars are included.
No new render or edit was made. Both SVGs were rendered with independently
installed Playwright at 1920, 960 and 800 pixels; measured width/overlap/card-bound
and connector-crossing checks returned zero issues. Both diagrams were visually
inspected at full size and 800 pixels; selected actual application captures were
also inspected. These checks do not claim real telephone audio validation.

## Independent clean installation

Executed `scripts/setup.ps1` on a fresh export of the reviewed Git index in a
separate test folder. It installed 78 locked Python dependencies and 528 npm
packages, generated distinct private tokens, migrated an empty SQLite database
and built Electron. After the concurrency correction, final staged source and
hashed lock export were refreshed into that independent installation; the final
smoke uses another newly migrated empty database with the same independent
installed dependencies. No original development path is required.

The real local backend was launched on an isolated loopback test port. The
reusable `frontend/scripts/release-smoke.mjs` created a LangGraph simulation,
verified explicit confirmation after three persisted attempts, opened the actual
booking application and administrator window, and checked real recorded calls,
graph nodes and waterfall rows. Screenshots/receipt were generated by those
windows. See [clean-install receipt](docs/validation/clean-install.json).

The release demo generator was additionally executed with two bookings: six
recorded attempts, two confirmations, no providers. It supports 1–100 bookings
(up to 300 attempts); the full 100-booking archive was not generated for this
release. The existing optional production archive generator remains included.

## Provider verification boundary

Local tests exercise Live authentication/session setup, PCM/PCMU frames,
interruptions/delegation, corrections, constrained negotiation/verification,
Twilio request payloads, webhook signatures, stream binding/replay rejection,
allowlists, explicit authorization, duration/cost guards, hangup, uncertainty and
reconciliation with mocked transports/HTTP. Preflight confirms providers remain
disabled in the release demonstration configuration.

No paid model request, microphone acceptance test, real telephone call or
restaurant contact was performed. Account/model access, audible two-way behavior,
public gateway delivery, real billing and provider hangup require the operator's
separate authorized acceptance process in [REAL_CALL_READINESS.md](REAL_CALL_READINESS.md).

## Security and resolved validation issues

Gitleaks and the public-index scan found no credential leaks in reviewed source.
A private-value comparison found no original credential value in public files;
values were neither printed nor published. Runtime dependency audits report no
known findings; the full frontend development tree retains 17 moderate advisories
as documented in [SECURITY.md](SECURITY.md).

Initial uv hardlink installation failed on OneDrive; reinstalling with copy mode
resolved it. All public setup commands use copy mode and hashed pinned packages.
Early UI runs exposed the storage/main-loop contention above, and were not
reported as passes. Their failed/interrupted attempts were followed by the final
post-fix results at the top of this report. An optional separately managed E2E
server mode is available for Windows process-tree teardown problems.

No real provider acceptance, signed installer, Linux or macOS validation is
claimed. Deprecation warnings from LangSmith's imported compatibility code are
recorded by pytest; tracing is disabled by default. The approved video remains a
disclosed simulated/illustrative demonstration rather than customer history.
