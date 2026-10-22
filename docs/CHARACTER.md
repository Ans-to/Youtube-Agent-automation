# The character

The channel's on-screen character is a **stickman, drawn in code**. There is no
art file in this repository: the figure is a circle, a set of tapered strokes and
a handful of joint discs, generated from the animation rig every frame.

That is a copyright decision as much as a design one. Nothing is traced, bought,
licensed or attributable, so there is nothing to strike.

## Watch it

`docs/media/stickman-film.mp4` — a 28-second cut, 1080p, with a spoken
voice-over, rendered by `tools/render_authored_film.py` from
`video_studio/films/character_speaks.mjs` and its companion
`character_speaks.voice.json`.

[![Contact sheet of the film](preview/stickman-film-contact-sheet.jpg)](media/stickman-film.mp4)

The figure walks in, speaks ten lines with a mouth driven by the measured audio,
changes expression on every line, shifts its weight and lifts its free arm on the
stresses, raises an arm to wave, and walks out. Every frame of it is code, and the
voice is synthesised on the machine — no cloud, no samples, no API key.

### The voice

`video_studio/espeak_lib.py` loads a speech engine from a Python wheel, so the
narration needs no system package, no download and no administrator. `voiceover.py`
reads `character_speaks.voice.json` (the line text, the pause after each line, a
rate per line), synthesises each line, then runs high-pass, de-ess, presence lift,
compression and a −1.5 dBFS normalise before it mixes. Timings come from the
rendered audio, so the picture, the captions, the visemes and the expression cues
all follow the voice rather than a table typed by hand.

Re-narrate without a download:

```bash
python3 -c "import sys; sys.path.insert(0,'video_studio'); import voiceover; from pathlib import Path; print(voiceover.build(Path('video_studio/films/character_speaks.voice.json'), Path('out'), allow_download=False))"
```

![Pose sheet](preview/stickman-poses.png)

*(Three standing poses and a four-frame walk cycle. Regenerate with
`node video_studio/character/_preview.mjs --style stick --boil 1 --out out.png`.)*

## What "two values" means

| | Value | Use |
|---|---|---|
| Paper | `#F2F2F2` | background, the inside of the head |
| Ink | `#121212` | every stroke, every joint, the face |
| Cape | `#787878` | the cloth, and nothing else |
| Accent | `#B3151F` | the cape lining, and nothing else |

The figure is two values plus one mid grey for the cloth. A cape filled with ink
is not a drawing, it is a blob: the arms vanish into it. A light grey keeps the
silhouette readable and leaves the black limbs on top of it.

`resolveInk()` **throws** if a colour is not exactly neutral grey, and **throws**
if an accent is supplied without `allowAccent: true`. Only one accent is ever
allowed — `#B3151F`, the lining at the hem. The pen refuses the accent on skin:
an earlier cut outlined the head in red, which read as an injury. Colour is
enforced in code, not remembered by whoever writes the next scene.

The film behind the figure follows the same palette: on `--style stick` the
backdrop, floor and vignette all switch to paper and ink, and every accent
colour in the scene goes through one helper. A test decodes a rendered frame and
fails if the accent covers more than 2% of it.

The frame itself is lifted from the reference video: black bands top and bottom,
a pale stage between them, and the caption set in gold (`#F2C230`) inside the top
band with a red slash in front of it. The bands are not decoration — they give the
type somewhere to live that cannot collide with the figure, which is what made
the old mid-frame captions unreadable as soon as a close-up put the cape behind
them.

## Why it does not look like a diagram

Four habits, all of them in `video_studio/character/stick.mjs`:

1. **Tapered strokes.** Every limb is thickest at the body and thinnest at the
   extremity, as a brush is. Weights are fractions of the solved bone, so the
   figure keeps its proportions at any scale.
2. **A frame, not a pile of sticks.** Sloping shoulder bridges from the base of
   the neck, and a pelvis band that sags slightly, join the limbs into one
   figure. Straight bars look like a coat hanger; this is the difference.
3. **A face that acts.** Ten named expressions in `expression.mjs` — rest, talk,
   smile, grin, question, think, surprise, stern, worry, emphatic. Each one is a
   set of numbers (brow height, brow angle, lid opening, squint, mouth curve,
   mouth width, head tilt, chin pitch), and the film picks one per spoken line and
   blends between them in a third of a second. The brows carry the meaning: the
   inner ends lift for a question, drop and close in for a hard line. On top of
   that, the mouth opening and width come from the viseme the voice layer measured
   in the rendered audio, so the lips match the syllables instead of guessing.
4. **A body that acts.** The same cue table drives weight shifts, nods and leans,
   scaled by how hard a line is stressed, and the free arm lifts on the beat. The
   figure is never perfectly still while it talks — a still figure with a moving
   mouth reads as a puppet.
5. **Line boil.** A deterministic per-bone, per-frame wobble, off by default
   (`--boil 1` for the hand-inked look). Deterministic means frame 40 renders
   identically every time — the wobble moves between frames, never within one.

## Using it

```bash
cd video_studio
node films/character_speaks.mjs --out frames --width 1920 --style stick --boil 1
node films/character_speaks.mjs --out stills --width 1280 --still 4.5,9.0
node character/_preview.mjs --style stick --boil 1 --out poses.png
node films/character_speaks.mjs --plan     # the caption plan as JSON, no rendering
```

`--plan` exists so no test or tool has to keep its own copy of the film's caption
count; the tests read the plan from the film itself.

`--style design` still renders the original illustrated figure, and
`--style stick` is the default: the channel look should not depend on remembering
a flag.

Both choices are written into `film.json` under `character`, so a downstream tool
can refuse to publish a colour frame to a monochrome channel without opening an
image:

```json
"character": {
  "style": "stick",
  "boil": 1,
  "ink": { "paper": "#F2F2F2", "ink": "#121212", "accent": null },
  "palette": "monochrome",
  "monochrome": true
}
```

## How it is checked

`node video_studio/character/selfcheck.mjs` prints JSON and exits non-zero on
failure. Seventy-nine checks, thirteen of which are about the pen:

- the default palette is two greys and no accent
- a warm paper, a tinted ink, or an unapproved accent is refused
- stroke weights and head radius are fractions of the solved bones, and double
  when the root doubles
- every colour the pen paints is greyscale
- the same frame and the same boil draw the same picture; with boil off, the
  picture does not depend on the frame number at all; with boil on, neighbouring
  frames differ
- the head is centred on the head bone, overlaps the neck, and no stroke reaches
  above the top of the head
- the figure is taller than it is wide
- every frame has a foot on the ground line, no ankle goes below it, the feet take
  turns and at least one is always down
- the stride follows the ground travelled, not the clock
- a swinging leg is drawn shorter than a standing one; a standing figure has both
  legs at full length
- no bone jumps between frames, and acceleration stays continuous — including
  across the walk-to-stand fade

And these are about the acting:

- there is more than one expression, and every expression defines every field
- a question is asked with the brows, not the mouth, and a flat statement is not
  given a question face
- the face is continuous across a cue boundary — no expression pops in a frame
- the body never stands perfectly still inside a phrase, and the acting does not
  jump between frames
- the cape is drawn behind the limbs, carries the single accent, and a violent
  sway cannot fly it off the figure

`tests/test_character_rig.py` runs that file through Node, requires all fifty-four
checks, and adds film-level tests: a default render is grey to the last pixel,
`--style design` still works, and an unknown pen or a negative boil is rejected
with a readable message.

## The walk

The rig is drawn front-on, so the walk is a front-view step cycle, not the side-on
cycle most rigs use. A side-on cycle — feet trading places fore and aft — scissors
the two legs through each other when the figure faces the camera, and a stick
figure has no silhouette to hide that.

Three things make it read as walking rather than as posed:

1. **Distance drives the cycle, not the clock.** A full cycle is four steps of
   ground, so the cadence follows the speed the body is actually moving at. Driven
   by time, the legs kept cycling at a fixed rate while the body eased in and out,
   and a "planted" foot slid along the floor at up to 45 design px per frame — 23
   px per frame at 1080p. That was the skate, and it is gone.
2. **A swinging foot is drawn, not solved.** In a flat front view a bent leg has
   nowhere to go but sideways: aiming the IK at a raised foot bowed the knee out to
   44% of the thigh, which reads as knock-knees. Both feet are therefore solved to
   the floor and the swinging leg is *shortened about its hip* by the drawing, which
   is the same shortcut a 2D animator takes to push a leg toward the camera.
3. **The transition is blended.** Walking and standing are cross-faded over a third
   of a second. A hard switch pops every joint in one frame, and blending only the
   pelvis height dropped twenty pixels of side-to-side travel into a single frame.
   Both axes are blended, and so is the leg shortening.

Hip height comes from the supporting leg rather than a sine wave: the body is
lowest when both feet are down, and the solver is settled against the property that
a standing leg is straight, so a knee never has to bend to make the numbers fit.

## Camera

The camera is aimed from the solved skeleton rather than from a hard-coded
height. Each shot declares its headroom, and the pivot is solved so the top of
the head lands on that line at that zoom:

```
screen(y) = pivot + (y - pivot) * zoom      ⇒  pivot = (H·headroom − headTop·zoom) / (1 − zoom)
```

Zoom values are chosen so the bottom edge of frame lands where a camera would put
it — the full figure, just above the knee, then the waist. An intermediate zoom
slices through a shin, which reads as a mistake.

## Still to do

- The figure is in `films/character_speaks.mjs`. The other films still use the
  illustrated character and have not been re-cut with the stickman.
- The wave lifts the arm beside the head; the forearm still grazes the head circle
  at the widest point of the arc.
- Elbows and knees are only visible when the limb is bent; the idle pose keeps
  them almost straight. A resting bend in the neutral pose would read better.
- No side or three-quarter view: the rig is built for a front-on presenter.
