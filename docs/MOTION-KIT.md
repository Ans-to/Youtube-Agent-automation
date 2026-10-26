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

## The world map is real geometry now

`motion/kit/world.mjs` used to draw the continents from twelve to forty hand-placed
points each. It looked like it: Europe was a lump, India was a spike, and every
coast had six vertices. The film's most important shot — a company that sold to a
hundred and thirty countries — was drawn from guesswork.

It now decodes Natural Earth 110m land from `motion/kit/data/land-110m.json`
(public domain, 55 KB, shipped in the repo, read from disk so a render never
touches the network): about five thousand points across a hundred and twenty-eight
rings. Two geometry defects came out of putting real data in:

- **The antimeridian.** Natural Earth closes Russia with an edge from +180 to
  −180. Projected flat, that edge is a horizontal line across the whole frame.
  Rings are now cut at the seam and each piece is closed against the map edge.
- **Antarctica.** Its bounding box spans every longitude, so a clip-and-fill
  reveal painted a full-width band. The reveal fill is now clamped to the map box
  vertically, and land outside the crop is skipped before it is drawn.

`drawMap` now takes its land colours from the film's `palette` unless told
otherwise. It also **throws on an unknown option key**. That is not pedantry: a
caller passed `kind:` instead of `projection:` and silently got a plausible
equirectangular map for weeks.

## Two new gates, because the old ones could not fail

**`node motion/kit/coverage.mjs <frames-dir>`** reads the rendered pixels and
reports, every half second, the share of the frame that is not its own background,
plus its contrast range. It found three effectively empty moments in the 48-second
cut (3.2 % ink at 34 s) that all two hundred and forty-seven structural checks had
passed.

**`tests/test_audio_bands.py`** renders the score and refuses broadband
brightness: no quarter-second window above 15 % of its energy above 4 kHz, no
centroid above 3 kHz, and an unknown section name must fail rather than fall back
to `calm`. The rejected film's worst window was 81 % at an 11.5 kHz centroid.

Neither is a quality score. Coverage does not make a shot good and a band limit
does not make a cue musical. They are floors, and the floor was missing.

## A join is not a fade-out and a fade-in

Two defects sat in the joins, and neither was visible in the shot list.

**The incoming shot painted its own background.** Every shot fills its paper across
the whole frame before drawing layers. During a join that opaque fill covered the
outgoing shot entirely, so the transition was compositing against nothing. The
frame now paints the paper once and each shot contributes only content
(`renderShot(..., { paintBackground: false })`).

**`fade` showed one shot at a time.** Before its midpoint it drew only the outgoing
shot, after it only the incoming one — and every shot in the studio animates up
from nothing, so the second half was a blank page with a wash over it. It is now a
real crossfade: outgoing stays underneath, incoming fades up over it, and a paper
dip rides on top capped at 55 %.

Result: `coverage.mjs` went from "3 empty moments, minimum 0.0 % ink" to
**0 empty frames, minimum 9.2 % ink**.

## The kit is 83 shapes, 12 cards, 15 type moves, 16 transitions

Added this pass, because a documentary needs things, not only diagrams: 24 props
(document, signature, handshake, desk, chair, door, window, envelope, banknote,
calendar, newspaper, television, radio, laptop, tablet, watch, satellite,
network cloud, crowd, flag, trophy, gear, conveyor, cable coil, rubber sheet,
paper roll, rocket, container, truck, ship), 8 data marks (heatmap, waterfall,
radar, boxplot, histogram, gantt, bump, slope) and 6 type compositions
(lower-third, quote, chapter, stat, end card, ticker).

Four of them were drawn wrong the first time and fixed after looking: `radar` walked
its axes with sine of an index and produced a scribble, `satellite` was three
rectangles in a row, `rubber-sheet` was a grey blob with a circle beside it, and
`ticker` ran its copies together so the band read as one line printed twice. This is why the gallery exists and
why it is not optional: none of those four failed a test.
