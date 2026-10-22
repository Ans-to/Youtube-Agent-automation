# Dashboard interface

The dashboard at `http://127.0.0.1:8765` is a single-page command deck with seven
working areas. It is served from [`web/deck.html`](../web/deck.html) and reads its
state from `/api/state`; it posts to the same routes as before, so no backend
contract changed when the interface was replaced.

## Views

| Key | View | What it is for |
| --- | --- | --- |
| `1` | Overview | One active production, the queue, system activity and generated outputs |
| `2` | Tasks | New-task form and the full local queue |
| `3` | Video studio | Production brief for the CEO, with a live brief preview |
| `4` | CEO pipeline | Free-form goal, context file, delegation map, last run |
| `5` | Products | Digital-product brief and the last package |
| `6` | Roster | Every configured role profile, filterable by department |
| `7` | Outputs | Files written by finished tasks |

Keyboard `1`–`7` switches views from anywhere except a text field. The command bar
at the bottom accepts `video`, `queue`, `pipeline`, `product`, `roster`, `outputs`
and `home`. The URL hash (`#tasks`, `#roster`, …) tracks the current view, so the
browser back button works.

## Data flow

```text
web/deck.html  --fetch /api/state (every 4s)-->  dashboard.task_state()
     |
     +--POST /add, /run, /refresh, /generate-video,
              /build-product, /run-pipeline  -->  existing handlers
```

`/api/state` is the only data source. Every count, queue row, progress bar and
output link is rendered from it; nothing in the page is hard-coded sample data.
A running task's saved `pipeline-progress.json` drives the five-stage strip.

## Design constraints

- **Loopback only.** `dashboard.py` refuses to bind anywhere else and validates
  `Host`/`Origin` on every POST.
- **No network fetches.** Fonts are system stacks, stills are local JPEGs, and the
  film-grain texture is an inline SVG data URI. `tests/test_dashboard.py` fails if a
  remote `src`, `href`, `url(...)` or `@import` appears.
- **Monochrome with one accent.** Neutrals carry the interface; record red marks
  only what is live (recording, current stage, progress, selected row).
- **Reduced motion respected.** Every animation is disabled under
  `prefers-reduced-motion`.
- **Output is never injected as HTML.** Task titles, kinds and paths are escaped
  before rendering, and `/output` still serves preformatted Markdown.

## Editing the interface

- Markup and styling: `web/deck.html` (one file, no build step).
- Stills: `web/stills/*.jpg`, served from the fixed asset allowlist in
  `dashboard.py`. To use a real thumbnail, replace a file and keep the name, or add
  a route and entry to that allowlist — arbitrary paths are deliberately not served.
- Adding a view: add the section, a `.nav` button with `data-go`, and the id to the
  `VIEWS` array in the page script.
