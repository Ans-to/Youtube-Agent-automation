---
name: hyperframes
description: Use HyperFrames (HTML + GSAP + Three.js rendered to MP4) for premium motion graphics, 3D animation and advanced kinetic typography in this repository. Holds the install steps, the render contract we follow, and the worked example film.
---

# HyperFrames skill (repo pointer)

HyperFrames by HeyGen renders HTML compositions to deterministic MP4 by
seeking a paused GSAP timeline frame by frame in headless Chrome and encoding
with FFmpeg. This file is the repository's own contract for using it; the
upstream skill pack itself is **not vendored** here (it ships helper scripts
that reference paid hosted APIs, which this repo's North Star invariants
forbid). Install the official skills on your machine instead:

```sh
npx skills add heygen-com/hyperframes      # interactive skill picker
# or, non-interactive:
npx hyperframes skills update              # core set: /hyperframes, /hyperframes-cli, /hyperframes-registry, /media-use
npx hyperframes init my-video              # scaffold a composition project
```

Requirements: Node.js 22+, FFmpeg. In restricted sandboxes without apt or
Chrome downloads, static builds work: FFmpeg from PyPI (`imageio-ffmpeg`),
Chromium from the npm-bundled `@sparticuz/chromium` (point
`HYPERFRAMES_BROWSER_PATH` at it, add its `al2023` libs to `LD_LIBRARY_PATH`),
and GSAP/Three.js vendored locally from npm — never from a CDN.

## The contract we author to (summary of the upstream `/hyperframes` skill)

1. `index.html` is the root composition; it mounts **one sub-composition per
   scene** from `compositions/`; media and fonts live in `assets/`.
2. Every timed element: `class="clip"` + `data-start` + `data-duration`
   (seconds). Paint order is `z-index`; `data-track-index` is only a lane.
3. Each composition builds **one paused timeline** and registers it last:
   `window.__timelines["<data-composition-id>"] = tl`. Host id, scene
   composition id and timeline key must match.
4. Deterministic only: no `Date.now()`, unseeded `Math.random()`, network
   fetches, timers, or `repeat: -1`. Everything visible is a function of
   timeline time. 3D/canvas draws from `e.detail.time` in an `hf-seek`
   listener (`renderAt(t)` is pure).
5. Animate children of a `.clip` (or its opacity), never `display` /
   `visibility`; no CSS `transform` on anything GSAP transforms; animate
   transforms, not layout properties (letter-spacing tweens snap and fail).
6. Fonts other than the bundled set need `@font-face` to a file in
   `assets/fonts/`. Asset paths are `assets/...` with no leading slash.
7. Motion craft: arrivals `expo.out` / `power4.out`, exits `power3.in` at
   40–50% of entrance length, word stagger 60–120 ms, readable lines hold
   ≥ 0.5 s + 0.3 s/word, landed titles stay dead still. No uniform
   fade-and-slide, no breathing loops, no crossfading worlds.
8. Work loop: `npx hyperframes check` (fix every error) →
   `npx hyperframes snapshot --review` (look at beats, seams, phone width) →
   Studio preview → render. **Delivery renders run in GitHub Actions**
   (repo `/Skill.md`), producing the MP4 as a downloadable artifact.

## Worked example in this repo

`video_studio/hyperframes/dollar-world-currency/` — *Why the Dollar Rules
the World*, a 60-second 1920×1080 film: a continuous Three.js world
(dot globe + gold coin + trade arcs) under seven kinetic-typography chapters,
each with a different entrance system, plus a synthesized score. Read its
`SPEC.md` (every adjective as a number), `SCRIPT.md` (words + sources) and
`REVIEW.md` (what frame inspection caught) before starting a new film, and
copy its structure rather than inventing a new one.
