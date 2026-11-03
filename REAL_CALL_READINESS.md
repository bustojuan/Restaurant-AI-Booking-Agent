# OpenAI and Twilio: configuration and first-call readiness

The implementation includes server-side GPT-Live audio, client delegation,
Twilio outbound calls, signed callbacks, bidirectional Media Streams, bounded
approval waits, hangup and reconciliation. The default demo is provider-free.
Local protocol/HTTP tests are distinct from real audio and telephone acceptance;
see [TEST_REPORT.md](TEST_REPORT.md) for this release's executed evidence.

## 1. Configure OpenAI

Create a project API key in the [OpenAI platform](https://platform.openai.com/api-keys).
Enable API billing and confirm project access/quota for the configured models.
Keep the key in `backend/.env` as `OPENAI_API_KEY`; never put it into React, Vite,
screenshots, URLs or the repository. API authentication is server-side bearer
authentication. See the [official API overview](https://developers.openai.com/api/reference/overview).

BARIA uses two distinct paths:

- `AI_EXTRACTION_MODE=responses` uses the OpenAI Responses SDK for structured
  extraction, with `REASONING_MODEL=gpt-6-luna`. The default deterministic
  extractor uses no API. Changing the model does not change backend policies.
- Voice uses `VOICE_MODEL=gpt-live-1`, `VOICE_NAME=marin`, and
  `wss://api.openai.com/v1/live/sessions`. The backend sends `session.start`
  with `session_config`, instructions, `store=false`, client delegation and
  the configured audio format. This is the **GPT-Live protocol**, not the legacy
  Realtime tool-call API. Do not replace the endpoint with a Realtime URL.
  [Official WebSocket guide](https://developers.openai.com/api/docs/guides/voice-websockets).

Local sandbox audio is PCM 24 kHz; telephone audio uses PCMU 8 kHz. Audio input,
output and bounded specialist delegation are handled independently. Transcripts
exist in a bounded in-memory window; complete conversations and audio are not
persisted by default. `store=false` is a request setting, not a substitute for
reviewing provider data policies.

Run the **configuration-only** diagnostic from `backend/`:

```powershell
../.venv/Scripts/python.exe -m scripts.voice_preflight
```

It makes no external connection and reports variable names, never secrets or
phone numbers. A ready configuration is not a completed provider acceptance test.

For a manually authorized paid microphone test, install the optional audio extra
in your own environment, set `VOICE_SANDBOX_ENABLED=true`, create a suitable draft
and follow [VOICE_ARCHITECTURE.md](backend/VOICE_ARCHITECTURE.md). The CLI requires
`--booking-id`, `--allow-api-costs` and `--consent-audio-processing`:

```powershell
uv pip install --link-mode=copy --python ../.venv/Scripts/python.exe -e ".[audio]"
../.venv/Scripts/python.exe -m scripts.voice_sandbox --booking-id YOUR_DRAFT_ID --allow-api-costs --consent-audio-processing
```

Use headphones and an authorized test participant. This command processes paid
audio; it is intentionally absent from setup and automated tests.

## 2. Configure Twilio

Create your own [Twilio Voice account](https://www.twilio.com/docs/voice/quickstart),
enable billing as applicable, and obtain a Voice-capable number authorized for
outbound calls. Check geographic permissions and destination restrictions; trial
accounts can require verified destinations and apply additional limitations.
Use the account's current console guidance rather than assuming unrestricted
dialing. [Trial guide](https://www.twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account).

Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` and exactly one
authorized own E.164 destination in `TELEPHONY_ALLOWED_NUMBERS` for the first test.
This adapter uses SID/Auth Token authentication; no API-key variable is invented.
Confirm model access, then set positive conservative EUR values for
`TELEPHONY_COST_PER_MINUTE`, `LIVE_COST_PER_MINUTE` and
`REASONING_RESERVED_COST_PER_CALL`. Configure permitted Europe/Madrid hours.

The adapter creates calls through the [Calls REST resource](https://www.twilio.com/docs/voice/api/call-resource)
with inline TwiML, a status callback, recording disabled, 20-second ringing timeout
and an authorized time limit. There is no automatic retry of call creation.

## 3. Expose only the voice gateway

Keep the business/admin API on `127.0.0.1:8001`. Start the separate gateway from
`backend/`, after migration:

```powershell
../.venv/Scripts/python.exe -m app.voice.gateway
```

Use your chosen HTTPS/WSS tunnel or reverse proxy **only for port 8002**. Set
`TELEPHONY_PUBLIC_ORIGIN=https://YOUR_GATEWAY_HOST` with no path or query and
restart API and gateway. The gateway exposes only:

```text
POST https://YOUR_GATEWAY_HOST/twilio/status/{session_id}
WS   wss://YOUR_GATEWAY_HOST/twilio/media
```

The backend supplies these URLs dynamically in the outbound call/TwiML; no inbound
restaurant webhook is required. Do not proxy local booking/admin routes. Preserve
the public URL used for [X-Twilio-Signature verification](https://www.twilio.com/docs/usage/security).
Media binding also checks a per-attempt nonce, account, Call SID, expected format
and single-use connection. Follow the [Media Streams networking requirements](https://www.twilio.com/docs/voice/media-streams).

## 4. Authorize one own-number call explicitly

With an authorized participant, configure all guards, then set
`REAL_TELEPHONY_ENABLED=true` and restart both processes. This alone does not dial.
Create a clearly labelled own-number fixture without calling:

```powershell
../.venv/Scripts/python.exe -m scripts.prepare_own_number_test --prepare-own-number-fixture
```

The script requires exactly one allowlisted own number and prints only draft ID
and version. Send `POST /api/bookings/{id}/start` with the local bearer token,
current `If-Match` and the following contract (replace expiry with a future,
timezone-aware ISO timestamp; choose your own budget):

```json
{
  "mode": "real_telephony",
  "scenario_id": "confirm-first",
  "call_authorization": {
    "explicit_authorization": true,
    "own_test_numbers_only": true,
    "audio_processing_consent": true,
    "max_calls": 1,
    "max_duration_seconds": 120,
    "max_estimated_cost_eur": 3,
    "expires_at": "REPLACE_WITH_FUTURE_ISO_TIMESTAMP"
  }
}
```

`scenario_id` is a contract compatibility field; it does not script real provider
responses. The engine rechecks authorization before each call. Allowlisting is
an operator declaration, not proof of phone ownership. Budget reservation is an
estimate, not a guarantee of final charges.

## 5. Observe, terminate and reconcile

Verify greeting/transparency, intelligible two-way audio, interruptions,
corrections, silence, alternative proposals, deposit approval and connection loss.
Check Voice → specialist → Voice events and explicit confirmation evidence.
Compare actual human experience with persisted backend events and provider status.
Do not treat a proposal or terminated transport as booking confirmation.

Cancel through the booking API to request Live closure and Twilio hangup. Check
`GET /api/voice/bookings/{id}/calls`. An uncertain timeout or possible reservation
halts automatic continuation and **never permits an automatic redial**.
`POST /api/voice/calls/{call_id}/reconcile` requires local authorization/version
and only clears negative uncertainty with the documented user attestation and
terminated matching call. If no Call SID was returned, locate the original call
in Twilio and verify its outcome manually. A positive reservation requires evidence
review; reconciliation does not manufacture a confirmation.

## Troubleshooting and acceptance boundary

| Issue | Check |
| --- | --- |
| OpenAI 401/403 | Project key, model permission, billing and quota; never log the key. |
| Live protocol error | Supported GPT-Live model and current event protocol; legacy Realtime is different. |
| Twilio rejects destination | Voice capability, account restrictions, verified destination, geographic permissions and allowlist. |
| Callback rejected | Exact HTTPS origin/path, Auth Token, proxy URL handling and signature header. |
| No media / wrong format | Public WSS reachability, PCMU 8 kHz mono, SID/nonce binding and no replayed stream. |
| Call blocked locally | Authorization expiry, version, allowed hours, positive tariffs, budget or previous uncertain call. |

Automated tests cover mocked Live frames, HTTP requests, signatures, guards,
delegation, state and recovery. Real provider account access, microphone audio,
public tunnel delivery, audible conversation, actual billing and real hangup
remain operator acceptance checks. No paid API or telephone call is made during
this release's validation. See [VOICE_ACCEPTANCE.md](backend/VOICE_ACCEPTANCE.md)
and [TELEPHONY_SETUP.md](backend/TELEPHONY_SETUP.md) for detailed technical procedures.
