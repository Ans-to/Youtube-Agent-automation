# Why the Dollar Rules the World — 60-second HyperFrames film

A premium motion-graphic explainer built with the **HyperFrames** skill
(HTML + GSAP + Three.js rendered deterministically to MP4). A continuous 3D
world — dot globe, gold dollar coin, igniting trade arcs — carries seven
kinetic-typography chapters: the hook, Bretton Woods 1944, the 89% network,
the petrodollar loop, the Treasury vault, the sanctions switch, and the
punchline: *not backed by gold — backed by trust, habit, and 80 years of network.*

- **Format:** 1920×1080 · 30 fps · 60.0 s · H.264 + synthesized score
- **Edit surface:** every chapter is one readable file in `compositions/`
- **Design law:** [SPEC.md](SPEC.md) · words + sources: [SCRIPT.md](SCRIPT.md) ·
  frame-by-frame review: [REVIEW.md](REVIEW.md)

## Commands (Node 22+ and FFmpeg on PATH)

```bash
cd video_studio/hyperframes/dollar-world-currency
npm run dev        # live Studio preview (edit text/timing in the browser)
npm run check      # lint + runtime + layout gate (must pass before render)
npm run render     # delivery render -> renders/*.mp4
```

One-offs:

```bash
npx hyperframes snapshot --review -o snapshots/review   # beat/seam/phone stills
npx hyperframes render --quality draft -o renders/draft.mp4
```

**Delivery render (channel policy in `/Skill.md`):** push and run the
**Render Dollar HyperFrames film** GitHub Actions workflow — it checks,
snapshots and renders on a runner and uploads the MP4 + contact sheet as a
downloadable artifact. Nothing is auto-published to YouTube.

## Project map

| Path | What it is |
|---|---|
| `index.html` | Root composition `main` (60 s): mounts the 3D world, 7 chapters, HUD, score |
| `compositions/world3d.html` | Three.js globe + coin + arcs, pure `renderAt(t)` from `hf-seek` (+2D fallback) |
| `compositions/s1-hook.html` … `s7-finale.html` | Kinetic-type chapters (one entrance system each) |
| `compositions/hud.html` | Corner frame, chapter labels 01–07, progress bar, vignette |
| `assets/audio/score.mp3` | Synthesized score — `python3 tools/make_score.py` regenerates the WAV |
| `assets/fonts/` | Inter + Space Grotesk (local; no CDN anywhere in this project) |
| `lib/` | Vendored GSAP 3.15 + Three.js r149 |
| `captions.srt` / `captions.vtt` | YouTube-ready captions, timed to the chapter cuts |
| `upload-pack.md` | Title, description, tags, pinned comment |
| `thumbnail.jpg` | 1280×720 thumbnail from the hook frame |

## Add a voiceover (drop-in, no re-edit)

1. Record `SCRIPT.md` (≈155 words) to `assets/audio/voiceover.mp3`, keeping
   each chapter inside its time window.
2. Add under the score in `index.html`:
   `<audio id="voiceover" class="clip" src="assets/audio/voiceover.mp3" data-start="0" data-duration="60" data-track-index="4" data-volume="1"></audio>`
3. Lower the score to `data-volume="0.35"` so it ducks under the voice,
   then re-check and re-render.

## Facts on screen

89% FX share — BIS Triennial 2025 · ≈57% reserves (EUR 20 / JPY 6 / GBP 5 /
CNY 2) — IMF COFER ≈2025 · 72% in 2001 — IMF COFER history · 1944, 44 nations,
$35/oz — Bretton Woods Agreements. Full notes in [SCRIPT.md](SCRIPT.md).
