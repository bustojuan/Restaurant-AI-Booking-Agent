# Third-party notices and media provenance

The project's original code is Apache-2.0. Dependencies and third-party content
keep their own licenses; installing them does not transfer their ownership to
BARIA. Exact versions are recorded in `backend/uv.lock`,
`backend/requirements-dev.lock.txt`, `frontend/package-lock.json` and
`video/package-lock.json`. Dependency distributions include their license texts.

## Application software

Python packages include FastAPI, Pydantic, SQLAlchemy, Alembic, LangGraph,
LangChain Core, OpenAI SDK, Twilio SDK and their transitive dependencies.
The desktop uses Electron, React, TypeScript, Vite, MapLibre GL JS, React Flow,
TanStack Query, Recharts, Motion and Lucide. License metadata from the actual
installed locked distributions is included under `docs/licenses/`; it is an
inventory, not a replacement for each upstream license.

Inter is installed through `@fontsource-variable/inter`, under SIL Open Font
License 1.1. Its license is retained in `docs/licenses/`. Lucide's ISC license
and MapLibre's BSD license are likewise retained. No operating-system font
binary is bundled. The diagram and video use installed Segoe UI/Arial fallbacks.

## Maps and restaurant data

Map images in the demo are captures of BARIA rendering OpenFreeMap's public
styles and OpenStreetMap data. Attribution remains part of the UI/captures:
**OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors**.

- [OpenFreeMap](https://openfreemap.org/) and its [terms](https://openfreemap.org/terms/).
- [OpenStreetMap copyright and ODbL](https://www.openstreetmap.org/copyright).
- [OpenMapTiles attribution](https://openmaptiles.org/).

No bulk tile cache or original developer catalog snapshot is distributed.
Optional Overpass imports remain subject to source data licensing and service
usage policies. The immediately usable catalog consists of explicitly simulated
restaurant fixtures. No real restaurant photographs, ratings or phone records
have been invented or included. The optional image manifest provider requires
verified identity, source, license and attribution; no photo coverage is assumed.

## Product demo and architecture

`docs/media/ai-restaurant-booker-demo.mp4` is the owner's approved product demo,
distributed unchanged at the owner's request. Its footage and accompanying
`video/public/review/` screenshots were captured from an isolated simulation
environment using fictional booking identities. They are not customer records.
The animation of live contact/delegation is explicitly illustrative; the
recorded UI investigation uses persisted simulation events.

Narration is scripted offline Windows English TTS, not restaurant conversation,
microphone recordings, a cloned voice or a paid API response. The Windows speech
engine itself is not distributed. There is no music, stock photography or
commercial sound-effect library in the project. The BARIA-authored narration,
editorial source and diagram sources are included; captured third-party map
content retains the attribution above.

Remotion packages use their **own license**, not Apache-2.0. Review the
[Remotion license and terms](https://www.remotion.dev/docs/license) for your
organization/use before running the video pipeline. The pinned runtime is
reinstalled from npm; no runtime binaries are committed. The repository does
not assert that every downstream commercial user qualifies for a free license.

No external design reference screenshot, example architecture diagram, third-party
brand logo, private customer audio or personal development database is bundled.
