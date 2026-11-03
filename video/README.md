# BARIA product demo - Remotion source

The approved export is [docs/media/ai-restaurant-booker-demo.mp4](../docs/media/ai-restaurant-booker-demo.mp4),
with English burned-in subtitles and SRT/WebVTT sidecars. It is preserved byte for
byte from the owner-approved version: 1920 x 1080, 30 fps, 5,850 frames, 195 seconds,
H.264/AAC. No re-edit or new render was performed for GitHub packaging.

## Preview and reproduce

Install Node.js 24 and run `npm.cmd ci` here, or `scripts/setup.ps1 -WithVideo`
from the repository root. Then:

```powershell
npm.cmd run check
npm.cmd run studio
node scripts/validate.mjs ../docs/media/ai-restaurant-booker-demo.mp4
```

The **RestaurantBooker** composition reads the included captured clips, fitted
narration and 46 aligned subtitle cues. Rendering existing material does not
require the backend or provider keys. Remotion may download its browser on first
render. `npm.cmd run render` creates a new local export under ignored `out/`;
it does not replace the approved `docs/media/` file.

## Included source assets

- `src/timeline.json`: scene timing and approved narration.
- `src/editorial.ts`: product headings and explanatory callouts.
- `src/Video.tsx`, `src/Subtitles.tsx`: composition and synchronized subtitles.
- `public/footage/`: actual Electron captures from an isolated simulation.
- `public/review/`: actual screenshot checks; `playground.png` supplies the result hold.
- `public/audio/`: seven offline scripted narration tracks, original source tracks,
  tempo metadata and aligned word boundaries.
- `public/assets.json`, `public/captions.en.json`: media references and cue data.

The opening explains that users provide a priority list and booking requirements
and BARIA contacts restaurants for them. The Control Center section explains each
agent's actions, timing and sequence. Live contact and Voice -> Negotiation -> Voice
are explicitly labelled illustrations; recorded booking history remains simulation.
There is no real restaurant audio or customer booking history.

## Optional fresh demo capture

The original production tools remain included. With independently installed
backend/frontend dependencies, `npm.cmd run demo:prepare` generates an isolated
archive under ignored `private/demo/`; it uses the real deterministic engine,
never paid providers. `demo:start` serves that archive and `capture` automates the
actual Electron window. The production generator records 297 baseline attempts;
the captured hero adds three. It also shifts the new synthetic archive into a
disclosed demo calendar. This is presentation data, not historical customer usage.

The simpler release generator in [INSTALLATION.md](../INSTALLATION.md) produces
1-100 bookings / 3-300 attempts without calendar shifts and is preferable for
exploring the application. No existing private production DB is distributed.

Capture needs a graphical Windows session. Narration regeneration needs the
installed Windows David English speech engine; it is not bundled. Captions use
the original engine's word events, exact source PCM and fitted tempo; do not reuse
that alignment blindly after changing voices. Rendering the included tracks does
not require that engine. No music or external font binary is included.

See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for map attribution,
narration provenance and Remotion's separate licensing. Review Remotion's terms
for your own organization before using the pipeline.
