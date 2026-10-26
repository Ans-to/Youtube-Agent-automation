# The motion kit

Everything the studio can draw, and how a shot is assembled from it.
Run `node video_studio/motion/kit/gallery.mjs --out DIR` for contact sheets of
every item, and `node video_studio/motion/kit/verify.mjs` to check that each one
actually puts ink on the canvas (245 checks).

## Vocabulary

| family | count | file |
|---|---|---|
| shapes — geometry / object / data / diagram | 51 | `motion/kit/shapes.mjs` |
| props — documents, desks, devices, transport, industry, people | 24 | `motion/kit/props.mjs` |
| charts — heatmap, waterfall, radar, box, histogram, Gantt, bump, slope | 8 | `motion/kit/charts.mjs` |
| kinetic typography moves | 15 | `motion/kit/type.mjs` |
| cards — lower third, quote, chapter, stat, end card, ticker | 6 | `motion/kit/cards.mjs` |
| entrances / behaviours / exits | 12 / 8 / 5 | `motion/kit/motion.mjs` |
| transitions | 14 | `motion/kit/transitions.mjs` |
| the world — continents, projections, pins, arcs | 1 map, 25 cities | `motion/kit/world.mjs` |

## Putting them together

- `camera.mjs` — shot sizes as a transform, depth-scaled for parallax.
- `light.mjs` — vignette, bloom, grain, tone, real depth of field.
- `stage.mjs` — a shot is data: layers with depth, in-point, entrance,
  behaviour, exit. `renderShot()` draws any shot at any time;
  `auditShotList()` checks the pacing rules before anything is encoded.
- `score.py` — a synthesised score: pads, pulse, arpeggio, risers, stingers,
  limited to about -14 LUFS and -1.5 dBTP.

## A worked example

`films/nokia_opening.mjs` is the opening fifty seconds as eight shots, built
only from the above. `--stills DIR` renders a contact sheet, `--frames DIR`
writes a PNG sequence at 30 fps.
