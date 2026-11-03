# English desktop interface

The booking application and AI Control Center use `en-GB`. Shared labels and
errors are centralized in `src/i18n/en.ts`; both renderers and Electron Main use
those approved strings. Dates retain day/month/year display, reservation time is
Europe/Madrid, and available prices use euros.

Restaurant names, addresses, Madrid/Navarra and user-entered notes are original
content. Recorded evidence is not translated or reconstructed for replay. Missing
transcripts remain explicitly unavailable; simulation and illustrative media are
identified as such.

The release preserves the approved renderer/Main/preload source. Packaging does
not redesign or relabel either window. Actual installation and UI validation are
recorded in [TEST_REPORT.md](../../TEST_REPORT.md); curated captures are linked
from [desktop verification](verification.md).
