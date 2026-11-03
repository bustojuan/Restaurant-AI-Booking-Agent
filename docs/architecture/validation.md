# Light architecture redesign — validation record

Reviewed on 2026-11-03. Scope: both architecture illustrations, editable vector
sources, regenerated PNG previews and documentation in BARIA_GITHUB.

| Check              | Result                                                                                                                                                                      |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reference fidelity | White background, navy text, pale blue cards, green backend/contact, lavender storage and amber human intervention; consistent original line icons.                         |
| Source contracts   | AST verification passed for 12 booking nodes, 12 fixed edges, four Supervisor routes, five delegation targets, four negotiation decisions and five verification statuses.   |
| Workflow note      | The external-voice acceptance footer, its superscript and the corresponding sentence in the accessible SVG description are absent.                                          |
| SVG format         | Both parse as native vectors with a 1920 × 840 viewBox, accessible titles/descriptions and no embedded raster images.                                                       |
| Rendering          | Both exported in installed Chromium at 1920 × 840, 960 × 420 and 800 × 350, device scale factor 1.                                                                          |
| Text geometry      | Zero width issues, canvas overflows, card-bound violations or overlapping text for either diagram.                                                                          |
| Connectors         | Zero strict horizontal/vertical connector crossings. Labels use native text without opaque masking rectangles.                                                              |
| Visual inspection  | Viewed both final diagrams at full resolution and 800 px. Checked text, cards, contrast, arrowheads, the Research → Voice link, specialist returns and saved-review routes. |
| Source checks      | Ruff lint and formatting passed for the generator and diagram sources.                                                                                                      |
| Asset inventory    | Current SVG sizes and SHA-256 values are recorded in ../validation/assets.json.                                                                                             |

System Architecture retains the separate voice gateway and shared SQLite
mailbox. Application DB and Event Store share one physical application SQLite
file; checkpoints use a second file. Observability is a backend subsystem.

Multi-Agent Workflow keeps checks during contact distinct from subsequent
reviews of saved results. Conditional paths do not represent agent concurrency
or activity in a historical replay. The Backend Decision panel is explanatory,
not an additional LangGraph node.

The supporting descriptions are 22–27 px in the full-size SVG (approximately
9.2–11.3 px at 800 px width); main node labels and headings are larger. Use the
full-size SVG for detailed presentation.

- Architecture: [SVG](system-architecture.svg), [full PNG](system-architecture.png),
  [800 px preview](system-architecture-800.png).
- Workflow: [SVG](agent-workflow.svg), [full PNG](agent-workflow.png),
  [800 px preview](agent-workflow-800.png).

Application code, booking policies, providers and agent orchestration were not
changed. No paid audio or telephone call was performed. This documentation-only
revision uses source, XML, lint, geometry and visual checks; it does not claim
application or provider acceptance testing.
