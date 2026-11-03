# BARIA — architecture diagrams

Editable vector diagrams of the repository implementation, restyled on
2026-11-03 using the supplied light-mode visual references. The references guide
the design; the components and routes come from the source code.

| Diagram              | Vector                         | PNG previews                                                                                              | Editable layout                             |
| -------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| System Architecture  | [SVG](system-architecture.svg) | [1920](system-architecture.png) · [960](system-architecture-960.png) · [800](system-architecture-800.png) | [Python source](src/system_architecture.py) |
| Multi-Agent Workflow | [SVG](agent-workflow.svg)      | [1920](agent-workflow.png) · [960](agent-workflow-960.png) · [800](agent-workflow-800.png)                | [Python source](src/agent_workflow.py)      |

## Visual design

Both illustrations share a white background, navy typography, original line
icons, rounded cards and pale blue, green, amber and lavender sections. Their
1920 × 840 canvas keeps the layout wide and readable in a README. Text remains
native and selectable; the SVGs contain no raster images or external fonts.

System Architecture separates the technology stack, desktop clients, backend,
persistence and external integrations. Observability sits inside Backend Core.
Application DB and Event Store are logical groups in the same SQLite file;
Checkpoints uses a separate file. The voice gateway communicates with the
booking backend through the existing SQLite mailbox. The Overpass connector
represents manual cached imports, not a live availability lookup.

The workflow retains Preparation, Contact, Backend Decision and Post-execution.
Voice Session can request Negotiation or Verification checks during contact;
Offer Review and Confirmation Review subsequently inspect saved results.
The requested external-voice acceptance footnote and its superscript marker have
been removed from the diagram and its accessible description.

## Reading the workflow

Dashed arrows describe **conditional routes**, not animation, concurrent work or
historical evidence. Double-headed links combine request and decision return, or
approval and resumption. The Backend Decision panel is a legend of persisted
outcomes, not an extra graph node. Supervisor's finish branch reaches Memory &
Summary and then Evaluation.

The diagram compresses the configured booking graph: START/load is folded into
Planning, prepare_call into the Research → Voice Session link, and the approval
and pause nodes into Human decision. Classic simulation bypasses LangGraph.
Voice delegation and deterministic simulation checks are different paths, as
described in the source details below. These are configured relationships, not
evidence that a historical call traversed every route.

The layouts use the shared [SVG vocabulary](src/svg.py). Source verification and
rendering results are recorded in [source-check.json](source-check.json),
[render-check.json](render-check.json) and [validation.md](validation.md).

## Source evidence

The executable source takes precedence over older architecture prose. See the [release validation report](../../TEST_REPORT.md) for current evidence.

| Diagram component                                                                | Implementation inspected                                                                                                                                                                                                                                                                |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Electron Main, separate desktop/admin bridges, token custody, HTTP/WS allowlists | [Main](../../frontend/electron/main/index.ts), [preload](../../frontend/electron/preload/index.ts), [desktop policy](../../frontend/electron/main/policy.ts), [admin policy](../../frontend/electron/main/admin-policy.ts)                                                              |
| Booking application, map and Control Center                                      | [frontend](../../frontend/README.md), [AdminApp](../../frontend/src/admin/AdminApp.tsx), [AgentGraph](../../frontend/src/admin/AgentGraph.tsx), [Timeline](../../frontend/src/admin/Timeline.tsx), [admin API client](../../frontend/src/admin/api.ts)                                  |
| FastAPI, authentication, booking API and admin observability REST/WS             | [application](../../backend/app/main.py), [dependencies](../../backend/app/api/dependencies.py), [routes](../../backend/app/api/routes.py), [observability API](../../backend/app/observability/api.py)                                                                                 |
| Authoritative priorities, approvals, attempts and final state                    | [BookingExecutionService](../../backend/app/services/execution.py), [negotiation policy](../../backend/app/services/negotiation.py), [confirmation verification](../../backend/app/services/verification.py)                                                                            |
| Booking graph, typed roles, contracts, scoped tools and prompts                  | [AIRuntime](../../backend/app/ai/runtime.py), [agents](../../backend/app/ai/agents.py), [contracts](../../backend/app/ai/contracts.py), [tools](../../backend/app/ai/tools.py), [versioned prompts](../../backend/app/ai/prompts/)                                                      |
| Default AI simulation and optional extraction                                    | [AISimulationCallProvider](../../backend/app/ai/simulation.py), [extraction](../../backend/app/ai/extraction.py)                                                                                                                                                                        |
| Live audio, short delegation graph, telephony and isolated gateway               | [LiveSession](../../backend/app/voice/live.py), [VoiceDelegationService](../../backend/app/voice/delegation.py), [TwilioCallProvider](../../backend/app/voice/telephony.py), [gateway](../../backend/app/voice/gateway.py), [sandbox](../../backend/app/voice/sandbox.py)               |
| SQLAlchemy business records, events, graph versions and permitted projections    | [business models](../../backend/app/models.py), [AI models](../../backend/app/ai/models.py), [observability models](../../backend/app/observability/models.py), [recorder](../../backend/app/observability/recorder.py), [admin projections](../../backend/app/observability/center.py) |
| Manual OSM import, cached browsing and licensed image identity                   | [Overpass adapter](../../backend/app/providers/overpass.py), [image providers](../../backend/app/providers/images.py), [catalog documentation](../../backend/docs/restaurant-catalog.md)                                                                                                |

## Actual responsibilities and routing

| Conceptual role  | Responsibility in this implementation                                                                                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Planning         | Builds the structured plan and voice briefing from booking requirements.                                                                                                                                                                          |
| Supervisor       | Reads persisted backend state, selects the next priority through scoped tools, and routes to contact, approval, pause or completion.                                                                                                              |
| Research         | Reads stored restaurant facts and expiring historical observations. Current availability remains `UNKNOWN`; it does not perform a live availability search.                                                                                       |
| Voice Session    | The booking node calls the scoped `persist_call_outcome` tool, which advances one attempt through the execution service. The selected provider handles contact; the real voice connector can delegate structured decisions while audio continues. |
| Negotiation      | Uses `NegotiationPolicyService` to evaluate terms during contact. The outer `negotiation` node subsequently reviews the stored offer; it does not conduct a second conversation.                                                                  |
| Verification     | Uses `ReservationVerificationService` to check explicit, matching confirmation evidence. The outer `verification` node reviews saved evidence after contact.                                                                                      |
| Memory & Summary | Summarizes persisted outcomes and saves expiring restaurant observations after completion. It does not train a model.                                                                                                                             |
| Evaluation       | Checks objective execution invariants and stores a quality report. It is not an LLM judge.                                                                                                                                                        |

The outer graph is `START → load → planning → supervisor`. Its `call` branch is `research → prepare_call → voice_session → negotiation → verification → supervisor`. The `approval` and `pause` branches interrupt and return to Supervisor after resumption. The `finish` branch is `memory → evaluation → END`. Failure or interruption can prevent later nodes from running; this is a definition of routes, not a claim about every execution.

Default `ai_simulation` performs direct nested `NegotiationAgent` / `VerificationAgent` evaluations against fixtures. The simulation note beneath Voice Session refers to these direct checks. The adjacent **Voice delegation** specialists and their double-headed conditional connectors describe the separate voice-provider request/decision return, not a recorded simulation handoff. Its deterministic extractor can optionally be replaced by Responses extraction when explicitly configured; this optional external path is documented here instead of adding another connector to the architecture illustration.

For voice delegation, `LiveSession` calls `VoiceDelegationService`. A separate short graph routes a proposal to `negotiate`, confirmation evidence to `verify`, requirements to `requirements`, no availability/refusal to `decline`, and unclear input to `clarify`. Each route ends; the service returns its result to the ongoing voice session. The return connector is a service response, not a LangGraph edge back to an audio-processing node. Audio packets do not pass through LangGraph.

### Exact decisions and completion rules

`NegotiationPolicyService` returns `ACCEPTABLE`, `UNACCEPTABLE`, `REQUIRES_USER_APPROVAL` or `INSUFFICIENT_INFORMATION`. An alternative is checked against date, party size, time flexibility, mandatory requirements, strict budget and financial obligations. An acceptable offer still needs explicit confirmation evidence. Voice can ask for clarification or another proposal; a completed insufficient/incompatible simulated offer cannot be accepted.

`VerificationResult.status` is `CONFIRMED`, `REJECTED`, `PENDING`, `AMBIGUOUS` or `NEEDS_USER_ACTION`. Verification checks source attempt, restaurant identity, booking name, authorized terms, explicit confirmation, contradictions and pending action. These verification values are distinct from booking and attempt statuses.

Only `BookingExecutionService` persists the final confirmation. A valid result sets booking `CONFIRMED` and stops contacting restaurants. No availability, a rejected offer or a safely completed unsuccessful contact can advance to the next priority. Missing/contradictory evidence after acceptance, or uncertain transport state, can set booking `FAILED` and require reconciliation; they do not authorize an automatic redial. `EXHAUSTED` and `CANCELLED` are other supported terminal booking states. Transport safety gates apply before another real call can start.

Approval is persisted through the versioned booking decision API. Approval resumes the same attempt; rejection can advance to the next safe priority. A LangGraph resume command wakes the graph and is not itself approval. A real-call approval deadline may expire and stop execution.

## Boundaries and validation status

- **External voice:** the repository contains an OpenAI **Live** connector (`/v1/live/sessions`, client delegation), optional Responses extraction, Twilio REST/status callbacks and WSS Media Streams. `TwilioCallProvider` and the separately hosted media gateway communicate through the existing shared application-SQLite mailbox; signed callback/stream authentication scopes their access. The diagram uses the connector's actual name; it does not claim equivalence with another API or validate configured model aliases. Fixture/protocol checks do not establish real provider compatibility, audio quality or telephone acceptance. See [voice acceptance](../../backend/VOICE_ACCEPTANCE.md) and [telephony setup](../../backend/TELEPHONY_SETUP.md). No paid audio or real calls were made for these diagrams.
- **Local storage:** business data, favorites, queue, offers, confirmations, tool operations and observed events share application SQLite. `AsyncSqliteSaver` uses the sibling `<DATABASE_FILE>.ai-checkpoints.sqlite` with synchronous graph durability for booking and phone delegation. This is not an atomic transaction spanning the two files. Standalone voice sandbox checkpoint storage is ephemeral; do not infer durable booking history from it.
- **Observability:** correlated events, graph/prompt/model metadata, recorded usage, available voice timestamps and permitted I/O support historical replay and analytics through authenticated admin REST/WS. Replay never reruns agents. Audio and full transcripts are not stored by default, and unavailable evidence or metrics remain unavailable. Retention can remove history.
- **Administration:** the admin bearer is independent of the local bearer and remains in Main. Historical projections and Settings are read-only. The separate `POST /playground/runs` path writes new, clearly identified deterministic fixture simulations; it is not historical replay and cannot initiate paid calls. This is a local application boundary, not multiuser authentication.
- **Maps and catalog:** MapLibre can load OpenFreeMap assets directly in the renderer. The IPC boundary represents application API requests, not every map-tile request. Research/browsing use the cached catalog; OSM import is manual. Images require an explicitly verified identity/rights manifest or remain unavailable. No extra image provider or live restaurant availability service is implied.

## Regenerate and review

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -B docs/architecture/generate.py
node docs/architecture/render.mjs
```

Any Python 3.12+ installation can run `generate.py`; it uses only the standard library. Edit the two layout sources and shared vocabulary, then regenerate the SVGs. The generator reads the runtime AST without importing or starting the backend, checks graph nodes, fixed edges, Supervisor routes, voice-delegation targets and exact policy/verification status contracts, and writes [source-check.json](source-check.json). A mismatch requires reviewing the documentation against the changed implementation, not blindly changing the expected values.

PNG rendering uses the frontend's existing Playwright dependency (`npm ci` in `frontend` if absent), with installed Edge or the existing Remotion Chromium. It neither downloads a browser nor starts the app. `render.mjs` exports **1920 × 840, 960 × 420 and 800 × 350** previews of each SVG. It writes [render-check.json](render-check.json), checks native text widths, canvas/card bounds, text-to-text overlaps and strict crossings of orthogonal connector segments, and fails on detected issues. These geometry checks do not establish semantic correctness or visual quality on their own. On another OS, supply a Chromium path with `ARCHITECTURE_BROWSER` or install the Playwright browser first.

Automatic geometry checks are followed by visual inspection of the actual rendered PNGs. See [validation record](validation.md). Open the full-size SVG when presenting or inspecting detailed contract labels in a narrow README view.
