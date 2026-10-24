# What `howardc38/motion-fx-lab` gives this film, and what it cannot

Read on 2026-10-24 at the owner's suggestion ("it covers almost any type of
graphics techniques"). Cloned to `/tmp`, read, and never committed here: it is
somebody else's repository, not an asset of ours.

## What it is

A browser-based effects lab. 125 JavaScript files under `fx/`, 18 `pack-*.js`
modules, 43 demos in one shared catalogue, plus families with their own guides
(studio, materials, fluid, design, signals, character, dialogue, plush, stacks,
mechanical, graphic). Layers: HTML, CSS, SVG, Canvas 2D, three.js r128/r180 with
GLSL, PixiJS for one filter pipeline, Matter.js and Rapier for rigid bodies,
Flubber for contour morphs. Its own render pipeline is Playwright over four
Chromium instances, writing screenshots through ffmpeg.

It is broad in the sense the owner meant. Materials and light, 3D space and
particles, physics and growth, characters, motion and timing, backgrounds, UI and
data, type — thirty-odd families, each a real effect rather than a preset.

## The parts that transfer to us

Our renderer is not a browser. `video_studio/films/*.mjs` draws every frame in
Node through `@napi-rs/canvas` and pipes JPEGs to ffmpeg. Offline, CPU only,
Windows PowerShell on a low-end machine, no CDN at render time. That rules out
large parts of the lab, and it leaves the parts that matter most to this film.

| Technique in the lab | What it is | Where it would go in our film |
|---|---|---|
| `chars` (per-character choreography) | letters animated individually on a stagger rather than a block moving | the three one-word hero phrases ("INTENTION,", "NOT SYNTAX", "BUILD IT") - gives a single word internal motion instead of one settle |
| `mark` (highlighter) | a filled band drawn behind the emphasised word | the quiet left column at 0:06, where the phrase has landed and only the settle is moving |
| `sweep` (light sweep) | one pass of light across a surface | the commit pill on the card as it lands - it marks the moment the agent saved, which the sentence is about |
| `scan` / `ring` / `count` | measured reveal, countdown, counting number | the checks and merge scenes later in the film, not the first thirty seconds |
| `whip` (velocity-derived stretch) | letter deform derived from its own speed | a slower version on word arrival; the lab's version overshoots and shakes, which the owner has rejected twice, so only the stretch is usable |
| House duration table (`DEFAULT_DUR`) | one timing per primitive, 0.34-0.9 s, shared by every film | our motion library has per-template timings but no single table; worth adopting so "no effect longer than 0.7 s" is enforced in one place |
| Wipe with a visible edge | the boundary line rides the wipe | already ours: `motion/transitions.mjs` draws a 10-pixel accent band on the leading edge |

## The parts that do not transfer

Named so nobody proposes them again as though they were free:

- **Every shader family.** Optical (moiré, caustics, foil), fluid, plush fur, the
  mechanical assembly and cutaway, GPGPU particles, volumetric smoke. These need
  a GPU and a browser. Our render is headless CPU canvas so it runs on the
  owner's machine offline. Adding Chromium plus WebGL to the toolchain would
  break the low-end and offline mandates for a look the film does not need.
- **The runtime libraries.** three.js, PixiJS, Matter.js, Rapier, Flubber are
  loaded from CDNs. New third-party runtime dependencies, network at render
  time, and licence surface we do not need.
- **Its 103 MB of assets.** Footage, bakes, CJK glyph outlines, textures.
- **Its recorder.** Playwright and four browsers to solve a browser problem we
  do not have.

## The one practice worth taking immediately

The lab renders **every frame twice, in two different browsers, and compares
them**, and refuses to publish if they disagree. We had nothing equivalent, and
we depend on the property it protects: our film is rendered in `--from/--to`
chunks, so the same frame number has to produce the same pixels in any process
and after any amount of lead-in. Nothing enforced that.

`tools/check_determinism.py` now does. It renders one window three times - twice
identically, once behind a longer lead-in - and compares the bytes of every
frame. It is wired into `tools/run_quality_gate.py`, so it runs with the rest of
the gate rather than when someone remembers.

Verified on 2026-10-24, `vibe_coding.mjs`, window 600-629 and 330-359:

- two separate processes: identical, every frame;
- a 90-frame window against a 60-frame window: identical, every frame;
- positive control, a deliberate `Math.random()` in the field: the check fails
  and names every frame (60 disagreements over 30 frames).

The first control attempt was worthless and is recorded here so it is not
repeated: injecting a 12-pixel strip of the same gradient changed nothing that
survived JPEG, so the check passed and proved nothing. A control has to be
visible in the output, not just present in the source.

## What was checked and does not apply

The lab reports that ffmpeg's defaults write untagged HD video, which browsers
then read as BT.709 while the encoder used BT.601 - the example given is
`#ff90e8` playing as `#ff9fe8`. Our pipeline also writes no colour tags, so this
looked like a live defect in every file we publish.

Measured instead of assumed: one of our frames encoded with no tags and with
explicit BT.709 tags, decoded back, compared to the source JPEG. Mean absolute
difference 1.15 levels untagged, 1.45 tagged; the pale field `[227,236,241]`
decoded as `[227,235,242]`. Our palette is low-saturation and the shift does not
survive the round trip, so the encoder is left alone. The finding is real for
saturated colour; it is not real for this film, and adding tags would have been
a change justified by somebody else's measurements rather than ours.
