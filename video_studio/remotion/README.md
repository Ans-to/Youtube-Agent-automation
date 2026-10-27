# Stop coding blind — Remotion composition

A 10-second, 1080×1920, 30 fps motion-graphics composition. The isometric workspace, keyboard, terminal and grid are SVG/CSS geometry, not photographs or image backplates. The camera is locked. The short headline uses the bundled Space Grotesk house font and a separate, eased mask for each word. [View the draft preview and its technical report](../../docs/media/remotion/stop-coding-blind.md).

## Run

Node.js 20+ is recommended. From this directory:

```bash
npm ci
npm run typecheck
npm test
npm run studio           # interactive Remotion Studio
npm run render           # out/stop-coding-blind.mp4
```

The rendered picture is exactly 300 frames (10 seconds). If an MP4 with an exactly 10.000-second container is required, use a system FFmpeg to copy the rendered video and encode the original soundtrack with a 10-second playback duration:

```bash
ffmpeg -i out/stop-coding-blind.mp4 -i public/audio/stop-coding-blind-120bpm.wav \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k \
  -af 'pan=stereo|c0=0.70710678*c0|c1=0.70710678*c0,atrim=duration=10' \
  -t 10 -movflags +faststart out/stop-coding-blind-exact.mp4
```

Remotion may download a compatible Chrome headless shell on first use. The component is [src/StopCodingBlind.tsx](src/StopCodingBlind.tsx); [src/Root.tsx](src/Root.tsx) registers the portrait composition and its exact duration.

## Beat and audio

The bundled instrumental is an original procedural track, generated from scratch by `npm run audio`; it uses no external samples. It is 48 kHz PCM with a 120 BPM beat grid beginning at time zero. The type entrances start exactly on successive beats:

| Word | Time | Frame (30 fps) |
|---|---:|---:|
| Stop | 0.5 s | 15 |
| coding | 1.0 s | 30 |
| blind. | 1.5 s | 45 |

Each word rises into its own mask and settles within 0.2 seconds; the full phrase remains visible. The title gently makes room for the terminal and returns for the ending. The terminal types and its inspection line moves in-frame, with no camera shake. An understated red rim pulses on the same beat grid. The clip contains music only, not spoken narration or subtitles.

`StopCodingBlind` accepts `audioSrc?: string | null`. Omit it to use the included track; pass a Remotion `staticFile(...)` URL to substitute another track, or `null` for silence. A replacement must be **120 BPM with its first beat at 0 seconds** for the existing type cues to stay synchronized; the component does not detect a track's tempo or compensate for a musical lead-in. If using the component in another Remotion project, also copy the `public/audio` and `public/fonts` files, and register it at the dimensions, frame rate and duration above.

The repository's only file named `SKILL.md` concerns response formatting, not video styling. This composition follows the applicable studio guidance in [PRO_MOTION_DIRECTOR.md](../skills/PRO_MOTION_DIRECTOR.md), [MOTION_DESIGN_SYSTEM.md](../../agents/MOTION_DESIGN_SYSTEM.md) and the masked word-reveal rules in [kinetic.mjs](../motion/kinetic.mjs). The supplied red accent takes precedence over the default lime accent. Technical verification does not replace watching and listening to the rendered file.
