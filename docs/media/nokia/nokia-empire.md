# Nokia: the rise and fall of a $300 billion empire

**28:35 · 137 shots · 1920×1080 · 24 fps · drawn entirely in code**, and the first
film in this studio written from somebody else's script rather than the agent's
own. The narration is the author's, word for word — 3,116 words across thirteen
scenes, split at sentence boundaries so each beat can have its own frame and
nothing is dropped, re-ordered or rewritten to fit a picture.

Source: `video_studio/films/empire_narration.json` (the script, verbatim) and
`video_studio/films/nokia_empire.mjs` (the picture).

**Release status:** this is the existing long cut, not the requested approximately
15-minute final. A [72-shot review video](nokia-15-minute-review.mp4) and its
[proposed script](nokia-15-minute-script-draft.md) have been prepared, but the
video failed strict technical QA and no final cut has been approved. See the
[Nokia music and release audit](nokia-release-audit.md) for the five music styles,
production commands, required evidence, and unresolved reviews.

## Why it is 28 minutes and not 15

The script's scene headings total 15:00, and its narration does not fit in it:
3,116 words at the studio's calm narration pace (145 wpm) is **21 minutes of
speech before a single shot change**. Add the beat each shot holds before its
line starts and the film lands at 28:35.

Keeping every word was the deliberate choice. Cutting to fifteen minutes means
deleting about 1,200 words of the author's prose, which is an editorial decision
that belongs to the author, not to the renderer. If a 15-minute cut is wanted it
is a rewrite of the script, not a setting on the film.

## The shape

| scene | time | shots | says |
|---|---|---|---|
| 1 | 0:00 – 1:46 | 17 | the empire that lost the future (cold open and falling all-phone share) |
| 2 | 1:46 – 3:49 | 14 | paper mill 1865 → three trades → the 1967 merger |
| 3 | 3:49 – 6:02 | 9 | the mobile age: car phones, Cityman 1987, the first GSM call |
| 4 | 6:02 – 8:59 | 11 | the 1011, the 3210, the 3310, and how far it spread |
| 5 | 8:59 – 11:22 | 11 | the peak: 40 % of the market, €51 bn, 2007 |
| 6 | 11:22 – 13:35 | 10 | January 2007, and what a touchscreen changed |
| 7 | 13:35 – 15:58 | 10 | Android, given away |
| 8 | 15:58 – 18:30 | 10 | the software problem, and the memo that followed |
| 9 | 18:30 – 20:52 | 10 | the burning platform, Lumia, and a platform with no scale |
| 10 | 20:52 – 23:17 | 10 | €5.44 bn / $7.2 bn, and what was kept |
| 11 | 23:17 – 25:50 | 11 | the five reasons, one per shot |
| 12 | 25:50 – 27:23 | 7 | what Nokia became instead |
| 13 | 27:23 – 28:35 | 7 | the lesson, and the closing card |

136 joins: 112 cuts and 24 accents (11 fades through paper, 5 wipes, 4 pushes,
3 irises, 1 rack). The accents fall on scene boundaries and on the five reasons —
the places where the argument turns.

## Grammar

Nothing was re-implemented. The film imports the seven shot builders
(`typeShot`, `objectShot`, `chartShot`, `mapShot`, `bandsShot`, `compareShot`,
`endShot`), the type helpers, the join constructors and the twelve worlds from
`films/nokia_full.mjs`, which is the house style established by the previous
film. Every chart in this film is drawn by the same function, so a chart in the
gold of the peak and a chart in the ash of the sale cannot drift apart.

One helper is new: `handset()`, which puts a drawn phone on the studio floor with
its own contact shadow, so four decades of hardware can be staged in the same
room without copying the staging code eight times.

## Rebuilding it

Use the [music and release workflow](nokia-release-audit.md) rather than a fixed
1,715-second score or an undefined section list. The current clock still reflects
the existing narration; a new, author-approved edit must be synthesized and
retimed before a shorter picture, music, and mix can be built. Rendering a slice
is not a finished film and does not constitute approval.

## Three things that had to change to make a 28-minute film

All three are silent failures — nothing throws, nothing logs, the output is just
wrong — and all three were found by measuring the file rather than trusting it.

1. **The score's reverb and filters were killed by the OOM reaper.** A single FFT
   over a 28-minute signal is a 134-million-point complex spectrum, twice. The
   reverb is now overlap-add over 2^18 blocks and the filters are a blockwise
   spectral mask with half a second of context; the result is the same filter
   (−48 dB error against a whole-array transform) in bounded memory.
2. **The WAV writer assumed the wrong array layout.** `build()` returns
   frames-first and the writer assumed channels-first, so the stereo file was
   assembled from two different parts of the timeline: measured, the level
   alternated every four seconds. The layout is now read from the array's shape.
3. **`narrate.mix` and `voice.normalise` allocated a copy per arithmetic step.**
   At 28 minutes that is 330 MB each. Both are in place now, and the
   K-weighting filters used for loudness are blockwise too.

The pictures are cheap to check and the audio is not, which is why the score and
the master are measured for holes, dynamic span, level before every cut and the
last 300 ms before anything is muxed.
