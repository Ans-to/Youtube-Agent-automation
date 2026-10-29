# REVIEW — Why the Dollar Rules the World (v1)

Checked against `hyperframes check` (0 errors; 8 `timeline_track_too_dense`
advisories accepted — one file per chapter is already the split the warning asks
for, and the HUD's eight clips are one coherent overlay) and the
`snapshot --review` set in `snapshots/review/`.

## What was inspected
- Beat frames at every chapter start +0.3 s and mid-chapter (15 frames).
- 5-frame strips around all six seams (blur-swap over the continuous 3D ground:
  no blank frames, no jump cuts in the globe/coin layer).
- Phone-width sheet: hero lines (RULES THE WORLD / 89% / BUY ENERGY? / manifesto)
  stay readable; source micro-lines go small — accepted for the 16:9 master.
  A 9:16 cut should reflow type bigger per chapter, not crop this master.

## Fixes made from frame inspection (v1 → v3 snapshots)
1. Hero coin rebuilt from planar faces (cylinder caps rendered the `$` sideways);
   warm fill light replaced the green point light that turned the coin lime.
2. Hero/finale coin moved from z=1.8 to z=2.55 — it was inside the globe's dark
   core sphere (r=2.17) and rendered as a black disc.
3. Chapter coins parked in verified safe corners; S6 decline labels re-seated
   above their points with dots on the line; S3 card label set on one line;
   oil droplet corner sharpened.

## Known limits (deliberate, v1)
- **No recorded voiceover.** The kinetic type carries the full script and the
  score marks every cut. `SCRIPT.md` + `captions.srt/.vtt` are timed for a
  drop-in voice take (see README) — next step if the channel wants narration.
- Chapter coins edge-on at some rotations read as thin gold slivers for a few
  frames. In motion this is the spin; frozen frames exaggerate it.
- The dot globe is a stylized Fibonacci sphere, not a landmass map — a deliberate
  graphic-novel choice (no map asset, no licence, consistent at every angle).
- Sandbox renders use screenshot capture (SwiftShader); CI renders with the
  official chrome-headless-shell for the delivery file.
