# Desktop release verification

The current executed evidence is [TEST_REPORT.md](../../TEST_REPORT.md). It covers
independent installation, TypeScript/build, unit and actual Electron flows, SQLite
simulation, administrator authentication, graph, inspector, timeline, replay,
Playground and desktop layout capture.

The source UI is English. Original restaurant/address names and user-provided
content keep their language. See [English UI](english-ui.md) and
[Control Center](control-center.md).

Curated actual isolated-demo captures are included in the public release:

- [Booking application / explorer](../../docs/screenshots/booking-application.png)
- [Booking configuration](../../docs/screenshots/booking-configuration.png)
- [Call history](../../docs/screenshots/call-history.png)
- [Agent graph](../../docs/screenshots/agent-graph.png)
- [Execution timeline](../../docs/screenshots/execution-timeline.png)
- [Analytics](../../docs/screenshots/analytics.png)

The E2E suite additionally regenerates diagnostic captures under ignored
`frontend/docs/screenshots/` at 1440×900 and 1920×1080, and exercises the existing
main-app desktop sizes. These runtime captures are not copied from a private
application profile. The optional OSM snapshot test requires an explicitly
supplied public catalog cache; the release starts with mock restaurant fixtures.

Tests use deterministic scenarios and mocked provider transports. They do not
validate real telephone audio. See [real-call readiness](../../REAL_CALL_READINESS.md).
