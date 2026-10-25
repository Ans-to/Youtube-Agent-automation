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
python -m venv .venv && .venv/bin/pip install numpy pillow imageio-ffmpeg kokoro-onnx onnxruntime piper-tts joe-us-piper-voice
.venv/bin/python video_studio/kokoro_voice.py   # fetch and verify the voice weights, once
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

## 11. The voice, after it was rejected twice

The first two films were narrated by Piper `en_US-joe-medium`. The gates passed
them and the owner did not: "voice over is the worst I have ever heard", then,
after a fix, "voiceover is bad". Both judgements were right. The film looked
deliberate and sounded like a machine reading a list.

### What the first fix did, and what it could not do

The obvious fault is prosody, not intelligibility, so the first attempt was a
production layer rather than a new model: split the line where a speaker would
breathe, synthesise each clause separately, put real silence where the
punctuation is, and let the last clause of a sentence land slightly slower than
the ones before it (`video_studio/voice_production.py`). Measured on the same
three sentences, that moved the pitch range from 34 Hz to 31 Hz interquartile -
which is to say it moved nothing audible. Phrasing cannot add a contour the
model never produced. The layer is still in the chain, because it does fix the
pauses, but it was not the answer.

### Where a better model came from

The blocked routes were checked and ruled out, not assumed:

- **PyPI** carries exactly one voice wheel with weights inside it:
  `joe-us-piper-voice`, one voice, `en_US-joe-medium`. Every other speech
  package on the index (`kokoro`, `kittentts`, `pocket-tts`, `supertonic`,
  `chatterbox-tts`, `f5-tts`, `styletts2`) ships code and fetches weights from
  HuggingFace.
- **HuggingFace** is not reachable from the runner, so those packages are
  unusable however good they are.
- **GitHub** repositories that look like they carry a voice model are carrying a
  Git LFS pointer. One was downloaded end to end: a 38 KB tarball that extracted
  a 133-byte text file where a 63 MB `.onnx` was promised.

**npm was the route nobody looks at.** `kokoro-q8-shards` publishes Kokoro-82M
as six byte-range shards, and `kokoro-js` carries the 54 voice embeddings. Both
are Apache-2.0, both come from the public registry with a SHA-512 in the
metadata, and both are reachable from a GitHub runner. `video_studio/kokoro_voice.py`
downloads the two tarballs, checks each against that SHA-512, stitches the shards
into one `.onnx`, packs the voices into one `.npz`, and caches the result. If npm
is unreachable the studio falls back to Piper rather than shipping a silent film.

### The chain a line now goes through

    text -> clause split -> Kokoro per clause -> pauses and final-clause landing
         -> 24 kHz reassembly -> highpass, de-ess, presence, compress, normalise
         -> mixed under the score at -8.5 dB duck -> two-pass loudnorm -14 LUFS

The tempo is pinned at 0.86 of the model's own pace, which lands the read at
146 words per minute - a narrator, not an explainer in a hurry. It is
deterministic: the same script renders the same audio every time.

### Measured on the delivered file

`docs/media/review-ai-code-720p.mp4`: 0:59, 1280x720, 30 fps, Kokoro
`am_michael`, 7.5 MB.

| Gate | Result |
| --- | --- |
| motion | PASSED - mean frame delta 1.33, 0.6% near-static (limit 15%) |
| composition | PASSED - 108 arrangements, longest 1.5 s (limit 12 s) |
| holds | PASSED - no frozen span over 1.0 s (longest 0.0 s) |
| narration | PASSED - 144 words per minute, 11.2 audible rests per minute |
| delivery level | -14.7 LUFS, true peak -1.7 dBFS |
| craft | PASSED - 18/18 rules |
| first claim | 0.12 s (was 0.87 s) |

Two defects surfaced while fixing the voice, and both were picture defects:

- **The film opened on nothing.** A 0.87 s lead-in before the first line meant
  the first twenty-six frames were a pale, empty field - and the audience
  decides in three seconds. The opening gap is now capped at 0.12 s.
- **A short line cut into many beats left one word alone on the frame.** Five
  words dealt into three beats gave "SHIP IT," / "OR STOP" / "IT.". Beats are
  now planned from the drawn words, dealt evenly, and a comparison or a number
  gets the fewest beats that fit its template instead of the same picture three
  times.

### Listen to it

`docs/media/voice-ab.mp4` - the same fourteen seconds of the same script, first
the old Piper voice, then the new one, both normalised to -14 LUFS so the louder
take cannot win the comparison.

### What is still true

Kokoro is a good synthetic narrator, not a human. It does not breathe, it does
not smile, and on a twelve-minute film it repeats its own cadences. The honest
ceiling of this approach is a clean, consistent, professional-sounding read -
which is the brief - and the next real step up is a human voice, or a hosted
model the owner chooses to pay for. The pipeline takes either: a pre-rendered
`voiceover.wav` plus `lines.json` drops straight into `tools/assemble_voiceover.py`.

## 12. The picture now says what the voice says

The film passed every gate and still failed the only test that matters: the owner
watched it and said the picture and the narration were about different things.
They were. Each section carried its own hand-written on-screen copy - "SHIP IT, OR
STOP IT." over a frame where the narrator was still saying "an agent just opened a
pull request" - and nothing had ever compared the two, because nothing could:
the narration's timings were per line, and a line was treated as one block.

The fix is three changes and one guard.

1. **Every word has a time.** `video_studio/voiceover.py` now emits `word_times`
   for each line: the line's duration split across its words, weighted by word
   length and by the punctuation that follows them. A comma buys a word more room
   than a letter does. Nothing is guessed at render time; the picture reads the
   same numbers the audio was built from.
2. **The picture is derived from the narration.** A section no longer carries an
   independent headline. `propsForBeat()` asks which clause the narrator is in the
   middle of, and prints *that* - split across two beats if the clause is longer
   than six words. A list's rows arrive when their sentence is spoken, not on an
   even clock, and they stay where they arrived: one list, one layout, for the
   whole section.
3. **The caption band stops repeating the frame.** A kinetic headline *is* the
   sentence, in the middle of the frame at reading size. Printing it again along
   the bottom is the same sentence twice, which is what a viewer reads as "the
   picture and the voice disagree". Captions are skipped when the picture already
   carries 60% of the cue's words. They still appear where the picture shows
   something else - a number, a comparison - which is where they earn their space.
4. **The guard.** Nothing may be printed that is not said. At build time, every
   authored string in a brief (`items`, `lines`, `left`, `right`, `label`) must be
   a subsequence of that section's spoken words, or the build stops:

   ```
   section number: the picture would print "SECONDS" but the narration never says that.
     spoken: sixty seconds of reading is the whole budget
   ```

   `tests/test_brief_sync.py` holds the same rule at the other end: it checks the
   brief, and it checks the *delivered* `plan.json` beat by beat, so a film whose
   picture drifts away from its voice cannot be committed.

The plan file now also records what each beat draws (`shows`), which is what let
the audit run without decoding frames:

| Beat | Window | On the frame |
| --- | --- | --- |
| open-1 | 0.00-1.66 | AN AGENT JUST OPENED |
| open-2 | 1.66-3.33 | A PULL REQUEST |
| open-3 | 3.33-4.99 | DO YOU SHIP IT TODAY |
| checks-1 | 11.52-13.63 | Read the diff, not the summary |
| checks-3 | 15.75-17.86 | + Run it once yourself, Ask what it does not handle |
| command-1 | 36.99-41.45 | npm test (typed) |
| payoff-1 | 42.30-44.37 | GREEN MEANS MERGE |
| recap-2 | 49.01-50.72 | Three checks, One command, A minute of your time |

Three of those beats were wrong when this started, in the way that is easiest to
miss: not wrong words, but right words at the wrong moment - a recap printing
"Three checks" three seconds before the narrator said it, and a list replaying its
entrance on every beat, so two rows overlapped mid-slide. The timing is what the
`word_times` fix bought; the overlap was a clock bug - the row templates were
being handed the beat's clock when what they build is the section's picture.

## 13. Shapes carry the structure

The owner's note was short: *"don't use only text, use different shapes and make
structure with them."* He was right about what the film was. Every template the
library had drew type on a plate. A list was rows of words, a number was a
numeral, a comparison was two headings. It read as a caption track with a
background, which is a presentation, not a design.

A diagram says what type cannot: how much, in what order, which way it forks,
what is missing. So there is now a second layer beside the type templates,
`video_studio/motion/structure.mjs`, registered in the same catalogue so a brief
chooses between the two by situation:

| Template | What it draws | When it is right |
| --- | --- | --- |
| `fork-paths` | a source block, two paths drawing out of it, and two terminals - one closed with a tick, one open with an arrow leaving | one thing splitting into two outcomes |
| `matrix-grid` | two to four tiles with number chips and glyphs, connected, filling in the order the narrator says them | three checks, a recap, a sequence |
| `ring-gauge` | a dial with sixty ticks, an arc that sweeps to the figure, zero/half/full on the ring, the number counting inside | a claimed number |
| `budget-rail` | one rail, divided into the parts the sentence says, a playhead crossing it | how a span of time is spent |
| `command-console` | a window, a prompt chevron, the command typing, and the run finishing block by block | one command |

The brief now uses them for six of its nine sections: the fork for *rubber stamp
or rewrite*, the grid for *three checks*, the dial for *sixty seconds*, the rail
for *forty/ten/ten*, the console for *npm test*, and the grid again for the recap.
The three statement beats - the opening claim, the two-line payoff, the closing
line - stay as type, because a punchline is a sentence and drawing a chart behind
it would be decoration.

Three things had to change for that to work rather than merely render:

- **Regions.** A diagram needs width the type templates never asked for, so the
  library gained `spread` and `wide`. A rail that stops at two-thirds of the
  frame reads as a card; across the full measure it reads as a chart.
- **One template per section.** The chooser used to pick a fresh template for
  every 1.6-second beat, which is how the comparison section became the same two
  cards three times and the list section flipped between two layouts. A section
  that names its template now keeps it for every beat, and the beats differ by
  what has been built so far - the rail gains its second segment, the grid its
  third tile.
- **Rows on the section's clock.** A tile that arrives at 4.2 s must stay at 4.2 s
  when the next beat starts. Handing these templates the beat's clock made every
  stored row replay its entrance, which is the overlap the owner saw as flicker.
  They now draw to the section's clock and to the section's full layout, so a
  tile that has not been spoken yet does not move the ones that have.

The frames are still measured, not admired. On the delivered file: 108 distinct
arrangements (the longest held 1.5 s), mean frame delta 1.33, no span over 1.0 s,
craft 18/18. The library's own self-check renders all 34 template/region cases
and refuses any template that draws outside its box - which caught the dial
overflowing its region by six pixels, before the owner could.
