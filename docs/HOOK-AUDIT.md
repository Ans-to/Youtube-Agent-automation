# The hook: what the evidence says, and what this film was doing

Fifty-seven seconds of film stand or fall on the first two. This is an audit of
the opening — 0 to 18.7 s, the three shots before the turn — against published
retention research, with the numbers measured on the delivered file rather than
recalled.

## What the research actually says

| Claim | Source |
|---|---|
| **71 % of viewers make a keep-or-leave decision in the first 3 seconds**; the intro window (first 30 s) is the steepest drop on every retention curve | [Tukey AI](https://tukey.ai/blog/the-youtube-hook-formula-that-stops-the-scroll-in-3-seconds-here-is-the-data) |
| Meta's 2025 attention study puts the decision at **1.3 seconds** — "the first frame matters more than the first sentence" | [Mean CEO, hook statistics](https://blog.mean.ceo/video-hook-retention-statistics/) |
| Hooks with **3+ cuts in the first 5 seconds have 12 % lower retention at 0:30** than hooks with 0–1 cuts | [YT SEO Architect](https://yt-seo-architect.vercel.app/blog/youtube-intro-hook-first-3-seconds) |
| High-retention openers share three things: cuts shorter than the rest of the video, **sound rising into the first full beat within 2–3 s**, and **visible motion in the first frame** rather than a static establishing shot | [Increditors](https://increditors.com/video-intro-length/) |
| The first audible event must do a job — signal, proof, or tension — and silence is only justified when it asks a question | [Kabo, sound as a hook](https://kabo.sh/guides/how-to-use-sound-as-a-video-hook) |
| The first 30 s should be the **most information-dense** part of a film, not the least; a documentary hook runs *concrete entry 0–5 s → tension and context 5–20 s → credible destination 20–30 s* | [Onira](https://onira.studio/guides/youtube-documentary-hooks), [YT SEO Architect](https://yt-seo-architect.vercel.app/blog/youtube-retention-graph-explained-2026) |
| Music for a calm narrative section sits 20–25 dB under the voice; a music bed that is too quiet creates "a jarring silence before the first spoken word" | [air.io](https://air.io/en/youtube-hacks/advanced-retention-editing-cutting-patterns-that-keep-viewers-past-minute-8), [Increditors](https://increditors.com/video-intro-length/) |
| Silence gaps over 200 ms at key moments read as slow | [AutoShorts](https://www.autoshorts.app/en/blog/sound-design-shorts-audio-tricks) |

Two of these cut against the instinct that the opening should simply be *fast*:

- **More cuts is not the answer.** Three or more cuts inside five seconds measured
  *worse* at 30 seconds than one. What holds is a single frame that is already
  moving.
- **A quiet opening is not the answer either.** Our score opened at −30 dBFS and
  faded in from nothing, which is the "jarring silence before the first word" the
  evidence warns about, not restraint.

## What the film was actually doing

Measured on the delivered mp4 (motion: busiest-tile 90th percentile per second,
the metric that corresponds to "something is moving on screen"; level: half-second
RMS).

| second | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| busiest tile | **0.18** | 0.80 | 1.30 | 0.85 | 0.64 | 0.36 | 5.39 | 7.71 |
| level dBFS | **−29.5** | −17.9 | −20.7 | −19.1 | −17.7 | **−29.1** | −19.4 | −17.0 |

Four faults, in order of how early a viewer meets them:

1. **The stillest second of the entire film was the first one** (0.18 — a fifth of
   the film's median). The shot faded up on a dark room with a phone in it and
   nothing moved until the type arrived at 0.8 s, which is after the 1.3-second
   decision.
2. **The quietest moment outside the "too late" beat was also the first.** The
   score faded in from 0.4 s of silence to −29.5 dBFS. The first sound a viewer
   heard was a ringtone arriving at half a second, alone.
3. **A 1.2-second hole in the sound before the film's first cut** (4.7–5.9 s at
   −29 dBFS): the line had finished, the pulse had not been written into the
   `calm` section, and the ear read it as the film stopping.
4. **The first cut was at 5.9 s**, after which the opening settled into 5.8–7.7 s
   shots. The film's densest thirty seconds were its last.

## What was changed

Nothing here moves the clock: the cut is locked and the lock is binding.

- **The phone rings on screen.** The display and the key light pulse at 3.03 Hz
  while the ringtone plays (`ringPulse()`), starting at 0.12 s. The ringtone was
  the first sound and had no picture; now the first audible event *is* the first
  visible event, which is the one job the evidence asks of an opening sound.
- **The breath starts at full speed.** The stage's drift was a smoothstep, which
  begins at zero velocity — so the first half second of every shot was a still
  frame inside a slow move. Two thirds of the travel is now constant-rate.
- **Type arrives at 0.03 s**, not 0.83 s.
- **The score is present from the first frame** (`calm` at −2 dB instead of −6,
  a 0.62/s pulse written into the section, fade-in 0.4 s → 0.12 s) and **a riser
  runs into the first cut**, because `moving` was missing from the rise list.

| | before | after |
|---|---|---|
| motion, second 0 | 0.18 | **1.75** |
| motion, second 1 | 0.80 | **3.14** |
| level, second 0 | −29.5 dBFS | **−22.0** |
| level, 4.0–5.5 s | −18 … −29 | **−15 … −24** |
| whole-film dynamic range | 11.3 dB | 11.3 dB (unchanged) |

## What is still wrong, in the order I would fix it

1. **The first cut is still at 5.9 s.** The strongest remaining lever, and the one
   thing that needs a re-cut rather than a patch: four beats in the first 13
   seconds (concrete entry → place → scale), with the lines shortened from
   twenty-three words to eight. That also puts the film's densest stretch at the
   front, where the evidence says it belongs.
2. **Seconds 2–5 are a held shot** (0.7–0.9 on the motion metric). The ring has
   stopped by 2 s and the frame goes back to drifting. A second visible event
   between 2 and 5 s — the screen resolving from CALLING… to a missed call, the
   key light breathing out — would carry the shot to its cut.
3. **The ringtone is the only diegetic sound in the film.** A film about a device
   with exactly one device sound runs 57 seconds of music and voice. Two more
   (a keypress at the turn, a paper sound at the mill) would cost nothing and
   make the joins feel like they belong to a world.
4. **Nothing on screen says what the next fifty seconds are about.** The opening
   states a subject ("It starts with a phone") but not a stake. The strongest
   documentary cold opens raise a question in the first ten seconds that only the
   rest of the film can close — here the natural one is the collapse, and the
   film withholds it until 48.7 s.

## Reproducing this cut

```bash
node video_studio/films/nokia_atlas.mjs --starts /tmp/starts.json
python video_studio/score.py --seconds 57.2 \
  --sections "calm:0:5.9,moving:5.9:12.9,tense:12.9:18.7,tense:18.7:26.4,sparse:26.4:32.4,history:32.4:40,build:40:48.7,resolve:48.7:57.2" \
  --cues "0.12:ring" --starts /tmp/starts.json --out /tmp/score.wav
python video_studio/narrate.py synth --lines video_studio/films/nokia_vo.json \
  --out /tmp/vo --voice am_michael --profile calm
python video_studio/narrate.py mix --vo /tmp/vo --score /tmp/score.wav \
  --starts /tmp/starts.json --out /tmp/master.wav
FFMPEG=<ffmpeg> node video_studio/render_to_video.mjs \
  --film ./video_studio/films/nokia_atlas.mjs --out /tmp/film.mp4 --scale 1.5 --fps 30 --crf 17
ffmpeg -i /tmp/film.mp4 -i /tmp/master.wav -c:v libx264 -crf 21 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart docs/media/nokia/nokia-atlas.mp4
```

---

# The cold open (round 8h)

The audit above was written against the 57.2-second cut, and its fourth fault was
the one that mattered: *"Nothing on screen says what the next fifty seconds are
about... the natural question is the collapse, and the film withholds it until
48.7 s."*

That was accurate, and the conclusion drawn from it — improve the opening in
place — was wrong. **A film opening and a YouTube hook are different jobs.** The
opening we shipped does the opening's job: it establishes a subject, a place, a
mood, and hands off to a story. A hook has to state the stake before the viewer
has decided whether there is one. Polishing the opening could never fix that,
because the opening was correct.

So the opening is now the *body*, and a cold open is prepended to it.

## The two beats

| # | shot | in | VO |
|---|---|---|---|
| 0 | `hook-00-claim` | 0.00–5.80 | *"In two thousand and seven, one in three phones on earth was a Nokia."* |
| 1 | `hook-00-fall` | 5.80–10.00 | *"Six years later, it was gone."* |

Then the existing eight shots run unchanged from 10.00 s, so the film is 67.2 s
and nothing in the body was re-written to make room. The ending is stated first —
the collapse, as a datum, with the collapse's own image — and the rest of the film
is the answer to *how*.

**Claim (0–5.8 s).** Ten marks on a single baseline, three lit. Frame one already
holds the three gold marks at full height: they *settle* into place rather than
grow from nothing, the seven grey ones cascade in behind them, and the legend
"THREE OF EVERY TEN" draws under the datum. The sentence is set to the right of
the marks it describes — the data on the left, the words on the right, nothing on
top of anything.

**Fall (5.8–10.0 s).** The same handset the body opens on, lit by a warm key from
upper left, its LCD going out across the shot while the words land. The object is
lit *before* the screen dies; a silhouette in a void reads as a missing render.

## Why it is not four quick cuts

The research table's counter-evidence was the constraint here: three or more cuts
inside five seconds measured **12 % lower retention at 0:30** than zero or one.
The hook therefore carries **one** cut and one change of world (gold-on-black
datum → warm-black object), not a montage. Density comes from what happens inside
the frames — a settle, a cascade, a rule, four lines of type, a screen dying, dust
and a slow push — not from more edits.

## What is measured

Motion here is the busiest-tile metric (8×8 tiles on a 320×176 luma reduction, max
tile, mean per second), computed on the delivered mp4 with `ffmpeg` + `numpy`.

| second | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| busiest tile, 57.2 s cut | 5.04 | 5.78 | 2.56 | 1.90 | 1.69 | 1.48 |
| busiest tile, 67.2 s cut | **4.92** | 2.34 | 1.85 | 1.86 | 1.57 | 1.14 |

Whole film: 0.54 mean / 3.03 busiest on the delivered file, against 0.63 / 4.06
for the 57.2 s cut — lower because two of the ten shots are now quiet datum
frames rather than a lit room with a moving light. That trade was taken
deliberately: the opening second now *states the stake*.

Second 0 is unchanged in density — but it is now density on a *composed* frame
carrying the film's claim, rather than a light blooming in an empty room. What
the old second 1 had was a full-frame light shaft; what the new one has is the
tail of the cascade and the type arriving. That is the honest comparison, and it
is the one place the new cut is weaker: **seconds 1–2 are the flattest in the
hook**, and a second visible event there (the grey marks resolving their count,
the year ticking 2007 → 2013) is the next thing I would add.

## Sound

The score is rebuilt on the new clock: `build` runs 0–5.8 s, an **impact lands on
the cut** into the fall at 5.8 s, `tense` carries the collapse, and the ringtone
is still cued where the phone in the body shot rings (10.12 s). The first audible
event is now the bed itself, not a ringtone arriving alone.

| | measured |
|---|---|
| integrated loudness | **−16.0 LUFS** |
| true peak | **−2.3 dBFS** |
| first half second | **−20.2 dBFS RMS** (target was ≥ −22.0) |
| 2-second RMS span | **11.4 dB** |
| spoken | 41.8 s across 10 lines |

## What the cold open cost

- The lock gained two rows (`cut`, `cut`), so this cut now has ten joins sharing
  seven transition kinds. The director used to throw `out of transitions` once
  every kind was spent; it now re-deals the least-used kind and says why. The
  one-kind-per-film rule itself is unchanged and still tested — `direction.mjs`
  is held to it against the eight-shot `nokia_opening.mjs`, where seven joins
  still have seven kinds; only a ten-join cut has to reuse one, and the lock
  records which join was approved so the reuse is a decision rather than a
  leftover.
- A shot with no row in `vo-timing.json` must not lose its duration: `TIMED`
  falls back to the locked duration for the two hook shots.
- The lock's `transition` overrides whatever the director dealt, so conforming to
  picture and dealing joins stay separate concerns.

## Reproducing this cut

```bash
node video_studio/films/nokia_atlas.mjs --starts /tmp/starts.json
python video_studio/score.py --seconds 67.2 \
  --sections "build:0:5.8,tense:5.8:10,calm:10:15.9,moving:15.9:22.9,tense:22.9:28.7,tense:28.7:36.4,sparse:36.4:42.4,history:42.4:50,build:50:58.7,resolve:58.7:67.2" \
  --cues "5.8:impact:1.15,10.12:ring" --out /tmp/score.wav
python video_studio/narrate.py synth --lines video_studio/films/nokia_vo.json \
  --out /tmp/vo --voice am_michael --profile calm
python video_studio/narrate.py mix --vo /tmp/vo --score /tmp/score.wav \
  --starts /tmp/starts.json --out /tmp/master.wav
FFMPEG=<ffmpeg> node video_studio/render_to_video.mjs \
  --film ./video_studio/films/nokia_atlas.mjs --out /tmp/film.mp4 --scale 1.5 --fps 30 --crf 17
ffmpeg -i /tmp/film.mp4 -i /tmp/master.wav -c:v libx264 -preset slow -crf 21 \
  -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -shortest \
  -movflags +faststart docs/media/nokia/nokia-atlas.mp4
```
