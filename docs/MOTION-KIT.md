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

## The no-repeat rule

No transition, entrance, behaviour, exit or type move appears twice anywhere in
a film. This is enforced, not remembered:

- `motion/kit/budget.mjs` expands each technique into its genuinely distinct
  parameterisations - a wipe at eight angles is eight joins, blinds at four
  strip counts is four - and deals them across the whole film. It insists on a
  different *family* first (two lumas at different cell sizes are the same idea
  twice) and only falls back to a second parameterisation when every family is
  spent.
- If the film needs more techniques than the vocabulary holds, `allocate` throws
  with the exact shortfall rather than quietly reusing one.
- `verify.mjs` runs `auditNoRepeat` over the cut film and fails the build on any
  repeat.

Pool sizes today: transitions 45 joins across 16 kinds, entrances 27,
behaviours 16, exits 8, type moves 15.

## Joins

`motion/kit/timeline.mjs` renders the film, not the shots: at a boundary the
outgoing shot is held on its last frame and the incoming shot is revealed by the
transition over the first half-second of its own life. The join plays *after* the
cut, because a join that straddles the boundary puts the incoming shot on screen
before it has begun - and since every shot animates up from nothing, that half
second was an empty frame punched into a full one.

## Voice

`narrate.py` synthesises the narration first (Kokoro, `am_michael`) and measures
it; the film's shot durations come from those measurements plus a floor, so the
cut follows the voice. `mix` lays the voice over `score.py`'s bed with the music
ducked 7 dB under each line, limited to about -14 LUFS and -1.5 dBTP.
