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

## The palette was one colour, and alpha leaked

Two defects made every frame look the same and half of them look washed out.

**One palette, eight shots.** Cream paper and navy ink, applied to the whole film.
Every shot looked like the same poster. There are two palettes now, `PAPER` and
`INK`, a shot declares which it is printed in, and `nokia_theme.mjs` swaps the
live palette through a hook in the stage before each shot draws. That is one line
per shot instead of rewriting forty `PALETTE.text` call sites, and it gives the
film a tonal rhythm: ink for the dark-room opening, paper for the map, ink for the
held stat, paper for the two handsets, ink for the phone alone.

**Alpha multiplied, then divided by something else.** Three shapes did this:

```js
ctx.globalAlpha *= 0.06 + 0.07 * clamp(p);   // draw at one alpha
ctx.fill();                                   // ...leaving another behind
ctx.globalAlpha /= 0.22 + 0.3 * clamp(p);
```

The divide did not match the multiply, so the context stayed wrong for every mark
drawn afterwards. The phone's body washed out to grey and each keypad key came out
brighter than the one before it. All three are `save()` / `restore()` now. It is
worth grepping for `globalAlpha /=` in any new code: in a 2D context there is no
reason to restore alpha by hand when the context can do it.

**Print texture.** `grade()` ends with a `riso()` pass: a 45° dot screen multiplied
into the picture and a soft-light paper tooth over it. Without it the frames read
as vector art on a clean field; with it they read as printed.

**Text on artwork.** Two labels sat on top of the handset that carried them. Their
baselines were two pixels above the phone's bottom edge, and on a dark palette the
label disappeared into it completely. Labels now sit on the paper below the
artwork, at 30 px, on one line, where nothing can cover them.

## Two clocks is one too many

The film and its narration were each adding up their own gaps. The picture used
`vo + PAD` per shot; the voice track used a 0.30 s lead and a 0.35 s gap between
lines. By the eighth shot the voice was **1.05 s** behind the picture, and at 33 s
the picture had cut to the trades while the previous line was still being spoken.
Measured drift across eight shots: -0.73 s to +1.05 s.

There is one clock now, and it is the film's:

- a shot's length is `lead + vo + breath`, so the lead is reserved *inside* the
  shot — a line can never outlive its cut;
- `shotStarts()` publishes `voStart` for every shot;
- `narrate.py mix --starts` reads that number and does not keep a copy of it.

`tests/test_sync.py` re-derives the whole thing from both files and fails if either
side ever keeps a private clock again. Measured on the finished master, every
line lands within 0.02 s of its cut.

## Transitions have a reason, or they are noise

The film was dealt transitions from a pool of sixteen. The pool cannot know what a
cut is *for*, so it deals novelty, and novelty is what reads as amateur: horizontal
blinds, a luma-keyed grid of cells, a two-panel split.

`motion/kit/direction.mjs` is the grammar. A shot declares a **role**, and a role
names the transitions an editor would use for that reason:

| role | why | kinds |
| --- | --- | --- |
| `beat` | something changes | cut |
| `time` | time passes in the same place | dissolve |
| `chapter` | a new section begins | dip to paper |
| `era` | a period opens | iris |
| `motion` | the film continues in one direction | wipe, push |
| `rack` | the camera moves while the subject changes | zoom dissolve |
| `momentum` | the film pushes on | push |

`direct()` takes the next unused kind, so the owner's rule — never the same
technique twice — still holds, and now it holds *inside* a professional
vocabulary instead of across sixteen gimmicks. The kit keeps all sixteen; the
director only chooses from the seven an editor would.

This film's seven joins, each with its reason: **rack** (the camera pulls back
from one handset to every country it was sold in), **dissolve** (the same map,
held), **fade-paper** (a new chapter), **cut** (the hardest line in the film),
**iris** (1865 opens), **wipe-left** (four industries travel), **push-left** (the
film pushes on into the rise).

## Type was never installed

Every `family: 'Inter'` and `family: 'Space Grotesk'` call in the kit was
rendering as **DejaVu Sans**, because there was no font file in the repo and no
`assets/fonts` directory for the renderer to load. The whole studio has been
setting its type in a Linux default.

`assets/fonts/` now ships 13 woff2 files (240 KB, from npm `@fontsource`, all
OFL): Inter 400–900, Space Grotesk 400/500/700, Anton, Instrument Serif, Archivo
800/900. The renderers register everything in that directory at startup.

## Three art directions, not three tints

`films/style_probe.mjs` renders the same six seconds three ways, so a direction
can be chosen by eye:

    node films/style_probe.mjs --style signal --frames /tmp/sig --fps 30

- **SIGNAL** — a two-colour poster. Near-black ground, cream, one signal orange.
  Anton at 190 px, hard edges, no texture, cuts on the beat.
- **MONOLITH** — dark and expensive. True black, old gold, hairline rules,
  Instrument Serif. Small subject, vast space, slow push.
- **STANZA** — kinetic type. Light ground, black type, one red. The words are the
  picture; the phone and the map are secondary marks that move on their own clock.

Each is a different *genre*, not a palette swap of one house style.

## The object has to be built, not iconified

`phone-classic` is a rounded rectangle with a grid: an icon. Any film made of
icons reads as a slide deck however well it is timed. `motion/kit/product.mjs`
models the handset instead — a tapered slab shaded across its width, a specular
band that slides with the camera, a recessed display with glass and bloom, keys
with bevelled caps and real labels, a contact shadow, and a floor reflection
mirrored about the point where the object meets the ground (mirroring about the
horizon makes a standing object hover).

`drawStudio()` builds the room: gradient wall, floor plane, a practical lamp
behind the subject, a soft light shaft, dust that drifts deterministically in
`t`, and one gold hairline on the horizon.

`films/studio_hero.mjs` is twenty seconds of that craft: three beats, a tripod
camera that moves once per shot, and type in Instrument Serif with tracked Inter
caps. `node films/studio_hero.mjs --frames /tmp/room --fps 30`.

The rule this establishes for the rest of the kit: **if it appears on screen for
more than two seconds and it is a real object, it gets modelled.**

## Eight shots, eight worlds

The film was rejected because it was one palette and one house style carried
through every shot, with the same two glyphs doing all the work. `films/nokia_atlas.mjs`
is the same eight lines on the same clock, drawn as eight separate worlds:

| shot | world | subject |
|---|---|---|
| hook-01 | deep cobalt room | the handset, ringing, reflected in the floor |
| hook-02 | amber dusk | a city in three depths, backlit |
| hook-03 | deep teal | the world, one in three |
| hook-04 | graphite / paper | the phone and the computer, either side of a seam |
| hook-05 | near-black | the object alone, on a shelf, lying down |
| history-01 | sepia dusk | a mill, turning wheel, smoke, pines |
| history-02 | bone | paper, rubber, cable, chip, each on its own plinth |
| history-03 | gold on black | a chart that ends in a handset |

`motion/kit/objects.mjs` is the accessory library they all draw on: skyline,
smartphone, pine, mill, paper ream, rubber sheet, cable drum, chip, plinth and
contact shadow. Same idiom as `product.mjs` — shaded across the form, highlight
on the lit side, shadow on the far side.

## Two bugs that made the film look worse than it was

**Every shot opened empty.** `stage.mjs` skipped any layer at `p <= 0`, so the
first frame of every shot - including the first frame of the film, which is the
frame YouTube shows - was bare background. A layer present from the start of a
shot now draws on the shot's first frame; a layer that enters later still waits.

**Every join had the same reason.** The director reads `shot.transitionRole`.
The new film set `shot.role`, so all eight fell through to the default and the
log printed "something changes" eight times. There is now a test that fails if a
shot declares a role the director does not know.

## Type, in one place

`motion/kit/fonts.mjs` loads the shipped faces and aliases them: @fontsource
names the 400 weight of Space Grotesk "Space Grotesk Light", so registering the
file as-is left the family unresolvable and every call fell back to DejaVu
again. Weights registered under one alias merge into one family.

## The narration was overacting, and it was in the direction

"Too dramatic" was not the model's fault alone. The read was being *directed*
like a trailer:

| | before | now |
|---|---|---|
| last phrase of a sentence | 6 % slower | 0.5 % slower |
| first phrase | 3 % slower | 1.0 (neutral) |
| pause at a full stop | 420 ms | 286 ms |
| pause at a comma | 140 ms | 95 ms |
| compressor | 2.5:1, +4 dB makeup | 1.8:1, +1.6 dB |

Both performances are kept, as profiles: `dramatic` is the old read, `calm` is
the documentary read. `narrate.py synth --profile calm` selects one.

Picking the voice was a measurement rather than a preference. Five candidates,
same two lines, same profile, scored on pitch spread, pace and pause total:

| voice | wpm | f0 | pitch spread | pauses |
|---|---|---|---|---|
| am_echo | 146.8 | 112 Hz | 6.15 st | 0.98 s |
| bm_fable | 139.0 | 118 Hz | 7.46 st | 2.17 s |
| am_onyx | 158.2 | 86 Hz | 4.12 st | 0.95 s |
| bf_emma | 169.6 | 180 Hz | 3.48 st | 0.63 s |
| bm_george (old) | 147.5 | 150 Hz | 5.63 st | 0.70 s |

`am_echo` is the neutral-broadcast read; `bm_fable` was the most theatrical of
the set. The full audition is `docs/media/nokia/voice-audition.mp3`, in that
order.

## Conforming a voice to a locked picture

`films/nokia_atlas.lock.json` holds the duration of every shot in the approved
cut. With it present, `retime()` keeps those durations and refuses to build if a
new line no longer fits - instead of silently re-cutting the film around a
shorter read. A picture nobody complained about should not change because the
narrator did.

`node reframe.mjs --film films/nokia_atlas.mjs --frames /tmp/atlas-frames \
  --from 26.4 --to 32.4` re-renders one shot into an existing frame directory, so
a single shot can be improved after delivery without re-rendering the film.

## Optics: the difference between a drawing and a photograph

The film was clean in the wrong way. Every edge was a hard vector edge, every
highlight stopped dead at the colour it was given, and the frame had no light in
it beyond what each layer painted. That is a rendering problem, and no number of
extra props fixes it.

`motion/kit/optics.mjs` runs on the finished frame:

- **bloom** — a bright pass at quarter resolution (a bloom is a low-frequency
  effect; paying for it at full resolution buys detail nobody can see), blurred,
  added back with `lighter`.
- **halation** — the same energy blurred wider and pushed warm, because that is
  what scatters off the back of film.
- **falloff** — an optical vignette, not a linear ramp.
- **grain** — a tile of deterministic noise drawn with `overlay`, offset per
  frame, so it moves. It sits in the mid-tones and leaves black alone.

Each shot declares its own light: the mill and the city bloom hard and warm
because they are lit windows at dusk; the trades on bone barely bloom at all.

**The blur is hand-written.** `ctx.filter = 'blur(...)'` does nothing in this
canvas build — it assigns, it does not throw, and the frame comes out unchanged.
That is the third time this studio has been bitten by a library failing quietly,
so `tests/test_optics.py` measures the effect: a patch of black beside a
highlight must get lighter, the corner must be dimmer than the centre, and the
grain must differ between two frames.

## 1080p, and why it got faster

`stage.mjs` and `timeline.mjs` take a `scale`: every coordinate stays in design
pixels and the context is scaled once, so a 1080p frame is a 1080p drawing rather
than a 720p drawing enlarged. Join buffers are device-sized too, or every cut
would drop to the design resolution for half a second.

The first attempt rendered 1716 PNGs to disk and had ffmpeg read them back: four
gigabytes of still-image encoding for frames that were about to be thrown away.
`render_to_video.mjs` pipes raw frames into the encoder instead.

| | frames/min |
|---|---|
| 1080p PNGs to disk | 18 |
| 1080p piped to x264 | 340 |

The mill was also rebuilt. At thumbnail size it was a grey box with a triangle
on it; at 1080p it had to be a building — board walls, a roof with two planes and
an eave that throws a shadow, a stone foot, chimney courses, windows set back
behind reveals with light spilling under the sills, a door with a lamp, and water
that catches the wheel.

## The film was a slideshow, and every review missed it

The cut that shipped before this one passed the gate, the coverage audit, the
optics test and a visual review of eight stills. Then the frames were measured
against each other: of 859 frames, **596 changed by less than 0.4 out of 255**
from the frame before, and the median change was **0.27**. Only five moments in
fifty-seven seconds moved: the five transitions.

The cause was not a bug. Every shot was built to *enter* — the type rises, the
objects land, the map draws itself — and then to hold. A hold is a still
photograph. Eight still photographs with cuts between them is a slideshow, and no
amount of better artwork fixes it.

**The breath.** `stage.mjs` now moves every shot for its whole life: a push, a
pull, or a drift across, of four and a half percent over the shot, direction taken
from a hash of the shot's id so no two neighbours travel the same way. A shot can
opt out with `drift: false` and set its own amount with `driftAmount`.

The first version used two percent, and it measured as nothing. Two percent of a
frame over five seconds is under the noise floor of a 640-pixel measurement, and
under the threshold at which a viewer sees a camera move at all — it was a camera
move in the code and a still frame on the screen. **A move has to be measured at
the size it will be seen at, and against the thing it is meant to defeat.**

**The air.** `drawMotes()` puts drifting dust in five shots, lit only inside the
key light, and `drawBreathe()` makes a practical lamp change brightness by two
percent on a cycle nothing else in the frame shares. Neither is visible on its
own. Together they are the difference between a frame that is waiting and a frame
that is alive.

**The measurement that matters.** The mean difference over a whole frame is the
wrong instrument: a wheel turning in the corner of a dark room barely moves it. The
gate in `tests/test_film_motion_and_dynamics.py` uses the **busiest tile** — the
frame cut into 144 tiles, the 90th-percentile tile's mean change — because that is
what "something is moving on screen" means numerically.

| cut | median frame | frames < 0.4 | busiest-tile median |
|---|---|---|---|
| shipped, `f147421` | 0.31 | 529 / 859 | 0.37 |
| breath at 2 % | 0.35 | 479 / 859 | 0.63 |
| breath at 4.5 %, moving light | 0.51 | 263 / 857 | 1.06 |

## Fifty-seven seconds of music at one volume

The same audit, run on the sound, found the other half of the problem: the score's
RMS never left a seven-decibel window for the whole film. Every section had its
own harmony, its own pulse and its own brightness, and all of it arrived at the
master at the same loudness — because `score.build()` normalised the finished
render to one target and then soft-limited the peaks. Normalising a film's music
to a single number is a decision that music has no dynamics.

Sections now carry a **level** of their own, in decibels relative to the loudest
one: `calm` −6, `moving` −1, `tense` −2.5, `sparse` −6 (the beat where the phone
is alone, and the score all but leaves), `build` 0, `resolve` −1.5. The
normaliser still runs on the finished mix, so the film sits at −16 LUFS with the
peaks where they were — but it is level *structure* that survives the trip now,
not just level.

| master | 2-second RMS range | short-term p5–p95 |
|---|---|---|
| shipped, `f147421` | 7.2 dB | 12.6 dB |
| this cut | 11.5 dB | 14.4 dB |

The narration is re-rendered from `films/nokia_vo.json` on every build
(`narrate.py synth --voice am_michael --profile calm`), so the mix is reproducible
from the repository rather than from a stem that existed on one machine for an
afternoon. `narrate.py mix --starts` places each line on the film's own clock, so
a read that comes out a few hundred milliseconds shorter cannot move the picture:
the cut is locked by `nokia_atlas.lock.json` and the lock is binding.

## Four defects a thumbnail cannot show

The stills for this pass were reviewed at 1080p and at the size the film is
watched at, which is where these came from:

- **The shadow pool was painted after the headline**, in the same layer, so it lay
  over the words it existed to separate them from the city. It is under the type
  now, and stronger, and the city falls away into it.
- **A gold seam ran through the middle of a word.** The turn's headline was
  centred on the divide. The sentence breaks across it now — old world left, new
  world right — which is the shot's own idea, drawn in type.
- **A caption crossed a parapet of lit windows** and half of it disappeared into
  the city. It sits on the dark ground below the skyline, in the only part of the
  frame that had nothing in it.
- **The mill's five windows were one brightness and one size.** No working mill
  has five identical lamps: one is out, one is dim, and the rest vary. The water
  under each one carries a broken column of its light.

## A join is a sound event too

The film already knew what kind of join it was making at every boundary — `cut`,
`rack`, `dissolve`, `fade-paper`, `iris`, `wipe-left`, `push-left` — because the
director picked one for a reason. The soundtrack read a list a person had typed
by hand, which is the second source of truth this studio keeps deleting: change
the transition and the sound no longer matches the picture, and nobody notices
until it is rendered.

`score.py --starts <the film's starts.json>` now derives one effect per join from
the transition itself:

| join | sound | what it is |
|---|---|---|
| `cut` | tick | 55 ms of felt and a small thud. A transient, not a boom |
| `rack` | pull | dark noise closing from 2.2 kHz to 520 Hz — a focus pulling |
| `dissolve` | bloom | a held chord that opens; it starts 1.9 s early and peaks on the cut |
| `fade-paper` | rustle | three page grains, all under 3.4 kHz |
| `iris` | close | a tone falling 132 → 56 Hz under a thud: the light leaving |
| `wipe-left` / `push-left` | whoosh | noise opening and closing, panned left |
| `wipe-right` / `push-right` | whoosh | the same, panned right |

Three things make this work rather than merely exist:

- **The table records where the energy peaks, not where the file starts.** A
  whoosh peaks 356 ms into its own sweep; placed on the cut, it would arrive a
  third of a second late, after the new shot had already landed by itself. The
  offsets are measured from the effects (`tick` 7 ms, `pull` 124 ms, `rustle`
  162 ms, `close` 132 ms, `bloom` 1861 ms, `whoosh` 356 ms), so every effect's
  loudest moment falls within 45 ms of its frame — measured on the delivered
  film at +33, +5, +45, 0, −10 and −10 ms. (The dissolve reads +265 ms in that
  measurement, but the cue bus puts its peak exactly on the cut: the difference is
  the master's limiter shaving a 3.4 s swell, not the placement.)
- **Effects are normalised one by one, not as a bus.** Normalising the bus made
  the iris peak 12 dB above the dissolve — the balance was an artefact of how long
  each effect happened to be.
- **The bed leaves room.** Limiting the sum meant every effect at every join was
  squashed by the music it was meant to punctuate: a −17 dBFS tick arrived 14 dB
  quieter than it was rendered. The bed is limited on its own and the effects are
  added after it.

`tests/test_join_sound.py` gates all of it: one sound per join, every peak within
two frames of its cut, every effect pre-lapped (the sound starts before the cut),
a wipe panned and a cut not, the effects within 8 dB of each other, and an unknown
join name failing rather than falling back to silence.
