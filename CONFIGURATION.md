# Configuration

The backend reads `backend/.env` when launched from `backend/`. The setup script
creates it from `.env.example` with random credentials. Restart processes after
changing settings. Pydantic validates types and limits; JSON arrays must use
double quotes. Blank optional secrets should remain commented out.

## Application and security

| Variable | Default / purpose |
| --- | --- |
| `HOST`, `PORT` | `127.0.0.1`, `8001`; keep the business API local. |
| `DATABASE_URL` | `sqlite:///./booking.db`; relative to backend working directory. |
| `LOCAL_API_TOKEN` | Required, at least 24 characters; application API bearer credential. |
| `ADMIN_API_TOKEN` | Separate token, at least 24 characters; administrative REST/WS and Playground. |
| `CORS_ORIGINS` | `["http://localhost:5173"]`; explicit allowed browser origins. Electron Main handles transport. |
| `SEED_MOCK_DATA` | `true`; safe clearly labelled restaurants for the demo. |
| `IMAGE_CATALOG_PATH` | Unset; optional local rights-reviewed image manifest. No photo by default. |
| `CALL_DELAY_SECONDS` | `0.1`, range 0–30; simulated contact pacing. |
| `CALL_TIMEOUT_SECONDS` | `5`, range >0–60; simulated attempt timeout. |

Favorites, workspace configuration, drafts, priority positions, bookings and
events persist in the application SQLite database. LangGraph checkpoints use a
separate SQLite file derived from that database path. Application SQLite uses WAL,
FULL synchronous durability and independent short-lived connections; BEGIN
IMMEDIATE still serializes writes. Do not copy either while
its executor is running. Queue/configuration writes require versions and are
restricted to DRAFT. Search state does not replace selection or favorites.

## AI and voice

| Variable | Default / purpose |
| --- | --- |
| `AI_EXTRACTION_MODE` | `deterministic`; `responses` opts into OpenAI structured extraction. |
| `REASONING_MODEL` | `gpt-6-luna`; model supplied to Responses extraction. |
| `VOICE_MODEL` | `gpt-live-1`; GPT-Live voice model. |
| `VOICE_NAME` | `marin`; supported voice for the selected model. |
| `OPENAI_API_KEY` | Unset; backend-only project API key. |
| `AI_MAX_STEPS` | `1000`, range 20–5000; graph recursion/step bound. |
| `AI_RETENTION_DAYS` | `30`, range 1–365; AI evidence/checkpoint/observation retention. |
| `LANGSMITH_TRACING_ENABLED` | `false`; external tracing is disabled by default. |
| `VOICE_SANDBOX_ENABLED` | `false`; explicit activation required for paid audio diagnostics. |
| `VOICE_MAX_SECONDS` | `180`, range 10–600; server voice session bound. |
| `VOICE_MAX_DELEGATIONS` | `8`, range 1–20; bounded specialist delegation. |
| `APPROVAL_WAIT_SECONDS` | `30`, range 5–120; live user approval wait. |

Simulation does not use paid models. `responses` changes extraction, not the
authority to accept constraints or persist a confirmation. An acceptable offer
alone is never a confirmed reservation.

## Telephony (disabled until explicitly configured)

| Variable | Default / purpose |
| --- | --- |
| `REAL_TELEPHONY_ENABLED` | `false`; outbound calling master guard. |
| `TWILIO_ACCOUNT_SID` | Unset; account SID `AC` followed by 32 hex characters. |
| `TWILIO_AUTH_TOKEN` | Unset; REST authentication and webhook signature verification. |
| `TWILIO_PHONE_NUMBER` | Unset; eligible outbound Twilio number in E.164. |
| `TELEPHONY_PUBLIC_ORIGIN` | Unset; exact HTTPS origin of the **gateway-only** tunnel. |
| `TELEPHONY_GATEWAY_PORT` | `8002`; separate loopback gateway. |
| `TELEPHONY_ALLOWED_NUMBERS` | `[]`; JSON array of explicitly authorized own numbers in E.164. |
| `TELEPHONY_START_HOUR`, `TELEPHONY_END_HOUR` | `10`, `20`; permitted hours in Europe/Madrid. |
| `TELEPHONY_COST_PER_MINUTE` | Unset; positive conservative EUR telephony tariff. |
| `LIVE_COST_PER_MINUTE` | Unset; positive conservative EUR Live tariff. |
| `REASONING_RESERVED_COST_PER_CALL` | Unset; positive EUR reasoning allowance per call. |

Use actual account pricing to configure cost estimates. A reserved estimate is
not a provider invoice. Server configuration does not replace per-run explicit
authorization, consent, expiry, call count and budget. See
[REAL_CALL_READINESS.md](REAL_CALL_READINESS.md).

## Supported modes

| Mode | Behavior | Provider credentials |
| --- | --- | --- |
| `simulation` | Classic deterministic engine with scenario fixtures | None |
| `ai_simulation` | LangGraph agents, scoped tools, checkpoints and recorded observations | None with deterministic extraction |
| `voice_sandbox` | Authorized microphone/speaker session with GPT-Live; no phone dial | OpenAI, enabled sandbox, consent |
| `real_telephony` | Twilio outbound contact, gateway audio and Live delegation | OpenAI + Twilio + all authorization guards |

## Desktop transport

`frontend/.env.example` documents `VITE_MAP_STYLE` (public map style URL, default
OpenFreeMap Liberty). Never create `VITE_*` credentials. Electron **Main** reads
`BARIA_BACKEND_URL` (default `http://127.0.0.1:8001`) and `BARIA_BACKEND_ENV`
(default repository `backend/.env`). `LOCAL_API_TOKEN`/`ADMIN_API_TOKEN` may also
be supplied to Main through its environment. `BARIA_USER_DATA` selects an
isolated Electron profile; `BARIA_ADMIN_ONLY=1` opens the independent admin window.
Both bridges expose typed allowlisted operations, not credentials.

For fresh initialization run `scripts/init-db.ps1`. See
[backend/docs/frontend-api.md](backend/docs/frontend-api.md) and
[backend/ADMIN_API.md](backend/ADMIN_API.md) for REST and WS contracts.
