# Long videos

An offline renderer that writes every frame to disk before encoding works for a
30-second clip and fails at 20 minutes. The numbers are not close:

| | 20-second clip | 20-minute film |
| --- | --- | --- |
| frames at 30 fps | 600 | 36,000 |
| 1080p PNGs on disk | ~4 GB | ~220 GB |
| if it crashes at 95% | lose 20 seconds | lose the film |

So long films are rendered in **slices**, and the disk cost stops depending on
how long the video is.

## How a sliced render works

1. The storyboard's own scene lengths decide the frame counts, exactly as the
   renderer computes them.
2. The film is cut into slices (default **60 seconds** each). A smaller slice is
   honoured exactly as asked, even one frame — it costs encode overhead, not
   correctness, and the run says so.
3. For each slice, `video_studio/render.js` is asked for one frame range:
   `--from-frame=N --frame-count=M`. It can start mid-film because a frame is a
   pure function of its index — nothing before it needs rendering.
4. The slice is checked for missing, misnumbered or wrong-sized frames **while
   its frames are still on disk**.
5. FFmpeg encodes that slice to its own MP4 part.
6. The slice's PNGs are deleted before the next slice begins.
7. At the end the parts are concatenated with `-c:v copy` — no second encode, no
   quality loss — and the audio is muxed once.

Disk now peaks at one slice, whatever the length of the film. A 20-minute 1080p
film needs about 2 GB of temporary space instead of 220 GB.

## Using it

The normal render command does it automatically. Above 30,000 frames (about
16.7 minutes at 30 fps) `video_studio/studio.py` switches to sliced rendering and
says so:

```
python video_studio/studio.py --storyboard film.json --output film.mp4 --with-voice
```

Force it for a short film, or choose the slice size:

```
python video_studio/studio.py --storyboard trailer.json --output trailer.mp4 --long-form --segment-seconds 30
```

Or drive the renderer on its own, which is useful on a slow machine because it
can be stopped and restarted:

```
python tools/long_form.py --storyboard film.json --output film.mp4 --plan-only
python tools/long_form.py --storyboard film.json --output film.mp4 --audio narration.wav
```

## Resuming

Every finished slice leaves `part-NNN.mp4` and a small record saying which frame
range it contains. Run the same command again and those slices are reused
without touching the browser. A part whose record disagrees with the plan is
**not** trusted — it is re-rendered. That is the difference between resuming and
guessing.

## What is guaranteed

- **The requested quality is never changed.** Resolution, frame rate and CRF are
  passed through exactly. Slicing changes how the work is scheduled, not what
  comes out.
- **A slice that does not match its plan is refused**, not stitched into the
  film: the frame count, the first frame number and the frame dimensions are all
  checked.
- **The output is one file**, with audio muxed once at the end.

## What it honestly costs

- **Long films are slow.** A 20-minute 1080p motion-graphics film is roughly
  36,000 browser framebuffer captures. On a 4-core desktop expect hours, not
  minutes. On a two-core laptop, plan for a long render and use the default
  slice size so a crash costs a minute rather than the film.
- **Slices are re-encoded boundaries.** Concat is a copy, so there is no visible
  seam, but a slice boundary is a keyframe — that is the same as any normal
  encode.
- **Very small slices are slower.** Every slice is an encode and a concat entry.
  One frame per slice works and is exact, but 60-second slices finish sooner.
- **The per-call ceiling is unchanged.** One renderer call still renders at most
  30,000 frames and 1,000 seconds. The *film* has no such limit, because the
  limits now apply to a slice.

## Verifying it

```
python -m unittest tests.test_long_form -v
```

That covers the frame arithmetic, slice planning, resume rules, the failure
paths, and that a bad slice is stopped before it is encoded. CI additionally
renders a real six-slice film with a real browser and real FFmpeg, then measures
the concatenated duration with `ffprobe`.
