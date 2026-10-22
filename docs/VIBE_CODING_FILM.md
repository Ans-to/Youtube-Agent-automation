# Vibe Coding on Arena, through GitHub — the long film

An 11-minute 30-second instructional film with no character, no footage and no
screenshots. Every frame is drawn by `video_studio/films/vibe_coding.mjs`, and
the GitHub and Arena interfaces in it are vector mockups built from rectangles
and type in `video_studio/motion/ui.mjs`.

That is a deliberate constraint, not a shortcut:

- **A mockup can show the moment that matters.** A real screenshot cannot show a
  pointer landing on *Create repository*, a diff line arriving as it is spoken, or
  a check turning from red to green. This film shows the action, not a picture of
  the aftermath.
- **A mockup never goes stale.** No redesign breaks it, because there is nothing
  to re-capture.
- **Nothing is licensed.** No stock, no music library, no font that is not
  already bundled, no traced art. The narration is synthesised on the machine.

## Watch it

The film is **11:29** at 1920×1080, 30 fps, with the narration mixed under a
synthesised bed, burned-in captions, and a sidecar `captions.srt`.

- **Master (upload this one):** `workspace/generated/vibe-coding/film-1080p.mp4`
  — 742 MB, CRF 21. YouTube accepts it as is.
- **Preview in this repository:** [docs/media/vibe-coding-preview.mp4](media/vibe-coding-preview.mp4)
  — 720p, 46 MB, the same cut, small enough to live in git.
- **Upload package:** [docs/media/vibe-coding-youtube.json](media/vibe-coding-youtube.json)
  — title, description and the 17 chapters, generated from the film's own scene
  table by `tools/youtube_package.py`.

[![Contact sheet of the film](preview/vibe-coding-contact-sheet.jpg)](media/vibe-coding-preview.mp4)

## The scenes

| Chapter | What it shows | Length |
| --- | --- | --- |
| Intro | The promise: a real app, described not typed | 23 s |
| 01 The idea | Intention instead of syntax, and the three rules | 38 s |
| 02 The loop | Six nodes: prompt, plan, branch, diff, checks, merge | 30 s |
| Step 01 GitHub | Sign up, create the repository, name the four parts of the page | 58 s |
| Step 02 Connect | Authorise GitHub, choose one repository, check the name | 45 s |
| Step 03 The prompt | A weak prompt struck out, then a real one written line by line | 61 s |
| Step 04 The branch | The agent's work shown as steps, ending in a pull request | 42 s |
| Step 05 The diff | A real diff, revealed line by line, with the three usual problems | 46 s |
| Step 06 Checks | Rows turning green, and the failing log read properly | 43 s |
| Step 07 Ship | Merge, confirm, then the deployed site | 39 s |
| Step 08 Again | A second feature, small and fast, merged in minutes | 47 s |
| Step 09 Recovery | A revert, and why nothing is ever lost | 41 s |
| Step 10 Patterns | Five prompt patterns, each with one example | 47 s |
| Step 11 Secrets | Secrets in settings, and the leaked value struck out | 32 s |
| Step 12 Habits | Five habits that keep the loop fast | 41 s |
| The whole loop | The seven steps, once more | 35 s |
| Start | Three lines: one page, one prompt, one pull request | 17 s |

The narration is 151 lines; every line is owned by exactly one scene, and the
film refuses to render if a line is left unclaimed or claimed twice
(`buildScenes()` throws). Timings are read from the synthesised audio, so the
picture, the highlights and the captions follow the voice.

## Rendering it

```bash
python3 tools/render_authored_film.py --script video_studio/films/vibe_coding.mjs \
  --out workspace/generated/vibe-coding --width 1920 --height 1080 --skip-4k \
  --slice-frames 2200
```

That one command narrates the script, draws 20,698 frames, synthesises the bed,
ducks it under the voice, validates every frame, encodes, measures motion, runs
the content audit, and writes the contact sheet.

`--slice-frames` matters on a small machine. A canvas renderer allocates native
pixel buffers that the V8 heap never sees, so the collector has no reason to run
and a 20,000-frame film climbs to several gigabytes and then stops. Slicing runs
the film in fresh processes that each write their own index range into the same
directory, which puts a ceiling on memory without changing the encode.

## What moves

Every scene is shot, not displayed:

- **A re-frame on every line, and halfway through it.** The frame eases 58 units
  sideways and 13 down, then holds. Two beats per sentence means the picture is
  never still for more than about two seconds.
- **A dot field drifting behind every scene**, 70 units a second on the pale
  stage, in gold on the dark one.
- **A sheen crossing the whole frame** on a 7.5 s cycle, so a held panel is lit
  rather than frozen.
- **Grain on every frame**, generated from four noise tiles at a different offset
  each frame: 3-pixel blocks at 10% over the frame.

Measured on the delivered file, the same way the character film was measured:
**mean frame deltas 1.71** between consecutive frames (the reference baseline is
0.82) and **0.1% near-static frames** (limit 50%). The content audit finds five
holds of about three seconds each, all of them a sentence being read on a screen
that is otherwise being re-framed; there are no strobe, black-frame or dead-air
findings.

## File sizes

The film compresses badly, and that is expected: per-frame grain is exactly what
a video codec is built to throw away. CRF 21 keeps it and costs 742 MB; CRF 27
smooths most of it and costs 97 MB, which also drops the measured motion below
the gate. The master is the CRF 21 encode; the repository carries a 720p copy.

Regenerate the narration alone:

```bash
python3 video_studio/voiceover.py --script video_studio/films/vibe_coding.voice.json \
  --out workspace/generated/vibe-coding/voice
```

## The gate this film declares

`film.json` carries `motion_gate: {min_mean: 0.8, max_static: 0.5}` — the same bar
the other films in this repository use, measured on the delivered file. It passes
at 1.71 / 0.1%.

That number is worth reading honestly: most of it comes from the grain, not from
the diagrams. Structure alone — a panel held while a sentence is read — measures
0.16 to 0.24 on this material. The grain is what keeps a screen-teaching film
from being a slideshow, which is why it is a deliberate part of the look and why
it is described above rather than hidden in an encoder flag.

## Publishing it

```bash
python3 tools/youtube_package.py --film workspace/generated/vibe-coding/film.json \
  --title "Vibe Coding on Arena, through GitHub" \
  --description "How to build and ship an app by describing it." \
  --tags "vibe coding,github,arena ai,no code,beginner" \
  --site "github.com/Ans-to/Youtube-Agent-automation"
```

`tools/youtube_package.py` writes `youtube.json` with a title, a description, and
a chapter list built from the film's own scene table. It refuses to write a
chapter list YouTube would ignore: the first chapter must be at `00:00`, every
chapter must be at least ten seconds long, and there must be at least three.

Nothing uploads anything. The package is a file a person reads before pasting.

## Checks

`tests/test_youtube_package.py` covers the package rules. `python3 -m pytest` and
`python3 tools/run_quality_gate.py` cover the rest of the repository.
