# The motion-graphics studio: plan

**Goal.** Any topic, written down as a short brief, becomes a finished YouTube
video: motion graphics only, real narration, music, captions, thumbnail and
upload pack. It runs on GitHub and costs nothing: no API key, no hosted service,
no credit card. The only requirement is a public repository.

**Why GitHub.** A public repo's standard runner is free and unlimited, with
4 cores and 16 GB of RAM, 6 hours per job and 10 GB per artifact
([GitHub docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[limits](https://docs.github.com/en/actions/reference/limits)). That 16 GB is
the point: the 1080p master that runs out of memory on a laptop renders
comfortably in CI.

---

## 1. What the system takes in

One JSON file. No prompt engineering, no model call, no key.

```jsonc
{
  "slug": "vibe-coding",
  "title": "Vibe Coding, Start to Finish",      // ≤ 60 chars, promise first
  "promise": "You will ship a real app without writing the code.",  // the hook
  "hookType": "result",                          // result|question|proof|cliffhanger|teaser
  "audience": "developers who have never shipped",
  "thumbnail": { "line": "NO CODE. SHIPPED.", "frame": "recap" },
  "sections": [
    {
      "id": "open", "kind": "hook", "heading": "The situation",
      "situation": "opening-claim", "template": "kinetic-headline",
      "props": { "text": "SHIP IT, OR STOP IT." },
      "lines": [{ "text": "An agent just opened a pull request. Do you ship it today?" }]
    }
  ]
}
```

A section names a **situation**, not a layout: `opening-claim`, `show-a-sequence`,
`explain-a-number`, `recap` and eleven others. The library's chooser turns that,
the beat length and the props the brief carries into a template. `props` are the
template's own inputs (`text`, `items`, `value`, `left`/`right`, `lines`,
`labels`/`values`); a brief that names a template without its props is refused
before a frame is drawn, with the missing prop named.

`lines` is narration, one sentence each — it is both what the voice reads and
what the captions show. `template` may be omitted, in which case the library's
own chooser picks one for the situation, beat length and region
(`video_studio/motion/choose.mjs`).

## 2. What it produces

| Artifact | Purpose |
| --- | --- |
| `master-1080p.mp4` | The film, H.264 high profile, `+faststart` |
| `web-720p.mp4` | < 100 MB copy that can live inside a repo and be linked from GitHub |
| `.srt` / `.vtt` | Captions, generated from the same narration with the same timings |
| `thumbnail-1280x720.jpg` | A real frame from the film plus 2–5 words |
| `upload-pack.md` | Title, description, chapters, tags, pinned comment, gate verdicts |
| `craft-report.json` | Every number in `docs/youtube-craft.md`, measured |

## 3. The pipeline

```
brief.json
   │  validate (words, hook type, chapter plan)      craft.py
   ▼
voiceover  ── Piper neural voice, offline ─────────►  voiceover.wav, lines.json
   │                                                  (timings ARE the clock)
   ▼
picture    ── films/from_brief.mjs ─────────────────►  30 fps JPEG frames
   │           template + kinetic type + transition
   ▼
sound      ── audio_design.py (score, sfx, ducking)─►  mix.wav at −14.6 LUFS
   ▼
encode     ── ffmpeg two-pass ─────────────────────►  master, web copy, srt, thumb
   ▼
gates      ── composition · repeat · motion · craft · narration
   │           any failure = no ship, with the number that failed printed
   ▼
ship       ── artifact + optional commit of the web copy to docs/media
```

The voice is the clock. Every scene's length comes from the audio that was
actually produced, so picture, highlights and captions cannot drift apart. That
also means changing the voice retimes the film instead of desyncing it.

## 4. What is already built, what this change adds

Already in the repo and working: the Canvas2D renderer, the motion library with
its contracts, the template chooser, the kinetic-type stage, transitions, second
unit, audio design with ducking, the Piper voiceover path, the composition and
repeat gates, the subtitle writer and the upload pack.

This change adds:

1. `video_studio/films/from_brief.mjs` — a film driven by a brief rather than by
   4,700 hand-written lines. Same renderer, same library.
2. `video_studio/craft.py` + `tools/check_craft.py` — the rules in
   `docs/youtube-craft.md`, measured on the real narration and captions.
3. `tools/make_thumbnail.py` — a real frame, safe-area text, contrast checked.
4. `.github/workflows/motion-studio.yml` — the zero-key build of all of it.
5. Tests for each new rule, so a rule cannot silently stop being enforced.

## 5. Gates (a film does not ship unless all pass)

| Gate | Checks | Source of truth |
| --- | --- | --- |
| composition | no composition held > 12 s | `tools/check_composition.py` |
| repeat | no frozen span > 1.0 s | `tools/check_repeat_frames.py` |
| motion | per-second delta ≥ threshold, near-static share ≤ 2.5% | renderer's own frame audit |
| craft | hook, pacing, interrupts, captions, chapters, packaging | `tools/check_craft.py` |
| narration | WPM, pauses, breaths, loudness, peak | `tools/check_narration.py` |

## 6. Running it

Locally (needs Node + Python + FFmpeg):

```bash
python -m venv .venv && .venv/bin/pip install numpy pillow imageio-ffmpeg piper-tts joe-us-piper-voice
npm --prefix video_studio ci
.venv/bin/python tools/render_brief.py --brief video_studio/briefs/demo.json --out build/demo
```

On GitHub: **Actions → Motion graphics studio → Run workflow**, pick the brief.
No secret has to exist. Nothing to pay for.

## 7. Cost table

| Item | Cost |
| --- | --- |
| Runner minutes (public repo) | £0 |
| Voice (Piper, PyPI) | £0 |
| Music and SFX (procedural, our code) | £0 |
| Templates, type, fonts (in repo) | £0 |
| Storage (artifact / `docs/media`) | £0 for a public repo |
| API keys | none exist |

## 8. Limits stated honestly

- 1080p authored render needs the CI runner's RAM; a 4 GB laptop will need
  `--delivery-height 720`.
- A 20-minute 1080p master is ~500 MB, over the 100 MB single-file limit for
  git; the master stays an artifact, the 720p web copy goes in the repo.
- The system cannot invent a good idea. It enforces that the idea is expressed
  with a hook, a stake, a payoff and a rhythm, and it shows the owner the
  numbers.
- Thumbnail A/B testing and retention feedback need a real YouTube channel
  connection; the pipeline produces the variants, the owner publishes them.

## 9. The first generated film, measured

`video_studio/briefs/review-ai-code.json` produced
`docs/media/review-ai-code-720p.mp4`: 0:51, 1280x720, 30 fps, Piper
`en_US-joe-medium`, 720p delivery at -14.3 LUFS.

| Gate | Result |
| --- | --- |
| motion | PASSED - mean frame delta 1.20, 2.1% near-static (limit 15%) |
| composition | PASSED - 78 arrangements, longest 2.0 s (limit 12 s) |
| holds | PASSED - no frozen span over 1.0 s |
| narration | PASSED - 160 words per minute |
| craft | PASSED - 18/18 rules |

The first cut of the same brief failed three of those gates: 89% near-static
frames, one 17-second arrangement, and a 3.8-second frozen span. The fix was not
a threshold. It was shorter beats (1.8 s instead of 3.1 s), a different template
on each beat chosen by the library's own chooser, a plate and an accent block
that move with the beat, and a second motion unit: a progress arc, a travelling
cursor with a soft column of light, a tick rail, and dust. Every number in the
table above is measured on the delivered file, not targeted.

## 10. What the studio still cannot do

- It cannot write the idea. A brief is still written by a person.
- The thumbnail step is specified and not yet built; the current film ships with
  a thumbnail line in the brief and no rendered image.
- The upload pack for generated films is not written yet; the long film has one
  by hand.
- The look is deliberately spare. It passes its gates and it is not yet as
  designed as the hand-authored long film, which had weeks of iteration per
  scene. The generator is the thing that scales; the scenes it composes come from
  a library of eight templates and will only get richer as more are added.
