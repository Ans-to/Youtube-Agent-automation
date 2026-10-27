# Nokia, the film

**7:51 · 53 shots · 1920×1080 · 24 fps · 1.4 Mbps · drawn entirely in code.** No footage, no
stills, no stock type. Every frame in it is painted by `video_studio/films/nokia_full.mjs`
and graded by `motion/kit/optics.mjs`.

The 67-second cut that was signed off in round 8i is the *opening* of this film.
It was not rewritten: the ten approved shots are imported from
`films/nokia_atlas.mjs`, and they keep their locked durations (5.8 / 4.2 / 5.9 /
7.0 / 5.8 / 7.7 / 6.0 / 7.6 / 8.7 / 8.5 s) and their locked joins. What changed is
where they sit: the mill now stands in 1865, where a paper mill belongs, instead
of standing in for "history" in a trailer.

## The shape

| act | time | shots | what it does |
|---|---|---|---|
| cold open | 0:00 – 0:10 | 2 | one in three phones, six years later none |
| overture | 0:10 – 0:42 | 5 | the phone in the world: a dark room, a hundred countries, a turn |
| i · the works | 0:42 – 1:24 | 5 | paper 1865, timber, rubber 1898, cable 1912, the 1967 merger |
| ii · the network | 1:24 – 2:24 | 6 | car phones, NMT, the first GSM call, phones outnumber paper |
| iii · the decade | 2:24 – 3:54 | 9 | the pocket, the tune, 250 million of one model, 65 % of smartphones |
| iv · the turn | 3:54 – 5:03 | 7 | one button, forty keys, a free competitor, a burning platform |
| v · the fall | 5:03 – 6:03 | 7 | a third to a twentieth, €3 bn lost, 18,000 jobs, the sale |
| vi · what remained | 6:03 – 7:15 | 8 | the radios, Bell Labs, the patents, the name licensed out |
| coda | 7:15 – 7:51 | 4 | five businesses, the usual lesson, and the correction |

Fifty-two joins: 41 cuts and 11 accents (2 dissolve, 2 fade-through-paper, 2 iris,
2 wipe, 2 push, 1 rack). The accents are act boundaries; everything inside an act
cuts, because a dissolve between two shots that belong together says they do not.

## Grammar

Every shot is built from the same seven builders — `typeShot`, `objectShot`,
`chartShot`, `mapShot`, `bandsShot`, `compareShot`, `endShot` — so no shot can
invent its own house style. Each of the twelve worlds (`sepia`, `bone`, `copper`,
`cobalt`, `steel`, `amber`, `teal`, `gold`, `graphite`, `ember`, `cold`, `ash`)
carries its own palette, its own optics (bloom / halation / grain / vignette) and
its own grade. A chart in the gold decade and a chart in the ash of 2013 are the
same chart with different light.

## Rebuilding it

```bash
cd video_studio

# 1. the script, as lines the voice can read
node films/nokia_full.mjs --lines /tmp/lines.json

# 2. the voice  (kokoro, bm_george, 'calm', rate 0.95)
.venv/bin/python narrate.py synth --lines /tmp/lines.json --out /tmp/vo \
  --voice bm_george --rate 0.95 --profile calm

# 3. the clock: shot durations are the voice's own lengths + lead + pad
node films/nokia_full.mjs --starts /tmp/starts.json

# 4. the score, with one sound per join read off the starts file
.venv/bin/python score.py --seconds 471.5 --sections "$SECTIONS" \
  --starts /tmp/starts.json --out /tmp/score.wav

# 5. voice over score, ducked, −16 LUFS
.venv/bin/python narrate.py mix --vo /tmp/vo --score /tmp/score.wav \
  --starts /tmp/starts.json --duck 0.34 --out /tmp/master.wav

# 6. picture: raw RGBA into ffmpeg, in chunks (see note)
node films/nokia_full.mjs --pipe --scale 1.5 --fps 24 --from 0 --to 200 \
  | ffmpeg -f rawvideo -pixel_format rgba -video_size 1920x1080 -framerate 24 \
      -i pipe:0 -an -c:v libx264 -preset faster -crf 17 -pix_fmt yuv420p seg000.mp4
```

Two format notes, both learned the hard way and both worth keeping:

* **Render in chunks of ~200 frames per process.** `canvas.data()` and
  `getImageData` both leave a native allocation per call that V8 does not
  collect; a single 1080p process dies at 176 frames (1.4 GB resident).
  Caching the bright-pass canvases in `optics.mjs` cut the leak from 21 MB to
  ~9.5 MB per frame, which is why 200-frame chunks are comfortable.
* **Pipe the frames; do not write PNGs.** PNG encoding cost 1.25 s per frame at
  1080p. Raw RGBA through a pipe costs 0.24 s, and the write is awaited so a
  slow encoder applies backpressure instead of killing the render with an
  `EAGAIN` half a frame before the end of a chunk.

## What the film does not claim

The numbers are the public ones: 250 million of the 1100, Symbian at about two
thirds of smartphones in 2007, Nokia at one phone in three, net sales of €51 bn
in 2007, the €5.4 bn sale to Microsoft, ~€1.4 bn a year of licensing. Where a
figure is contested or was never published, the line says the thing that is not
contested instead.
