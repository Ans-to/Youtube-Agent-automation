# SPEC — Why the Dollar Rules the World (60-second HyperFrames film)

Every adjective as a number. If a choice is not listed here, it is not in the film.

## Format
- 1920×1080, 30 fps, 60.0 s (1800 frames), H.264 MP4 + AAC score.
- One root composition (`main`) mounting 9 sub-compositions: `world3d`, `s1-hook` … `s7-finale`, `hud`.
- No network assets. GSAP 3.15 + Three.js r149 vendored in `lib/`; fonts in `assets/fonts/`.

## Look (repo Skill.md + MOTION_DESIGN_SYSTEM compliant)
- Ground `#0b0f19`, ink `#f4f2ec`, muted `#a7a7b3`, grid `#24242c`.
- Dollar green `#2ee66b` (hero accent), gold `#ffd166` (coin / gold facts), cyan `#4cc9f0` (data), red `#ff4d6d` (power / decline only).
- Display: Space Grotesk 700 (kinetic headlines, 64–148 px = 6–14 % of frame height).
- Text: Inter 400/600/800 (labels 26–34 px, kickers 28 px letter-spaced 0.32 em).
- Glass cards: fill `rgba(16,22,38,.78)`, 1 px border `rgba(244,242,236,.16)`, radius 20 px, no backdrop-filter (screenshot-capture cost).
- Vignette: one radial-gradient overlay div at 22 % edge darken. No CSS grade filters on footage (there is no footage).

## 3D world (`world3d`, Three.js, pure `renderAt(t)` from `hf-seek`)
- Dot globe R=2.2 (≈2 400 seeded Fibonacci points) + wire icosphere at 14 % opacity + 3 orbital rings.
- Gold coin: cylinder R=0.85 h=0.14, CanvasTexture `$` face, MeshPhongMaterial (warm key + cool rim, per 3d.md).
- 14 trade arcs (seeded city pairs), `drawRange` ignites 14–22 s, recolour toward red 41–49 s.
- 900 seeded stars. Camera: 9 keyframes, smoothstep-interpolated (coin close-up z=4.0 → globe wide z=8.2 → dive z=5.0 → hero return z=4.4). No wall clock, no `Math.random` (mulberry32).
- Fallback: if WebGL is unavailable, a 2D projected dot-globe draws the same choreography on the same canvas timings.

## Shots by time (all entrances land, then hold dead still — motion.md)
| # | Time | Kinetic type system | On-screen claim | Sound |
|---|------|--------------------|-----------------|-------|
| S1 | 0–6 s | word slam (scale 2.2→1, blur 14→0, 0.09 s stagger) | ONE PIECE OF PAPER / RULES THE WORLD | boom + coin shing 1.15 s |
| S2 | 6–14 s | year odometer 1900→1944, timeline rule, peg equation card | 44 nations · currencies → dollar → gold ($35/oz) | Dm→B♭, pulse starts |
| S3 | 14–23 s | count-up 0→89 %, SVG ring draw, slot-word roll | 89 % of FX trades touch USD (BIS 2025) | riser 13.45 s, ticks |
| S4 | 23–32 s | 1974 stamp (rotate −8° slam), 3-node loop diagram | Oil is priced in dollars → earn dollars first | boom, low pad |
| S5 | 32–41 s | bars scaleY stagger 0.07 s, word stack DEEP/LIQUID/TRUSTED | ≈57 % of FX reserves in USD (IMF COFER) | riser 31.45 s |
| S6 | 41–50 s | network nodes cut red sequentially, decline line draw | 72 % (2001) → 57 % today · rivals, no successor | tension pad |
| S7 | 50–60 s | per-word blur-in manifesto, final lockup `back.out(1.4)` | NOT GOLD. TRUST + HABIT + 80 YEARS OF NETWORK | riser, final hit 56.8 s |

- Holds: every readable line ≥ 0.5 s + 0.3 s/word; final lockup holds ≥ 3 s. Exits: blur+fade 0.2 s at each seam; the 3D ground never cuts.
- Eases by role: arrivals `expo.out`/`power4.out`, camera/colour `power2.inOut`, exits `power3.in`. No `power2.out 0.5s` anywhere. Linear only for the HUD progress bar and globe spin.
- HUD (0–60 s): corner frame, `60-SECOND MONEY STORIES` bug, chapter label per scene, progress bar scaleX 0→1 linear. Key text inside 80 % title-safe.

## Sound
- `assets/audio/score.mp3`, 60.0 s, synthesized by `tools/make_score.py` (seed 1944): chapter booms on cuts, 100 BPM pulse 6–50 s, data ticks 14–41 s, coin shings, risers before 14/32/50/56.8 s. RMS ≈ −15.6 dBFS pre-normalize, peak 0.88.
- Narration is written (`SCRIPT.md`) and captioned (`captions.srt/.vtt`) but not recorded in v1: the kinetic type carries the story word-for-word. Drop a voice take at `assets/audio/voiceover.mp3` and add one `<audio>` line in `index.html` (see README) — timings already match.

## Banned by name (defaults that look generated — motion.md)
Breathing/pulsing title loops · uniform fade+slide-up entrances · crossfading worlds · bounce on UI · unseeded randomness · CDN scripts · invented statistics (every number carries its source on screen and in SCRIPT.md).
