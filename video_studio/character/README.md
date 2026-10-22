# Character rig (2D, local, no assets)

A skeletal 2D character: bones, analytic two-bone IK, springs, viseme lip-sync
and a procedural vector body. No sprite sheets, no purchased rig, no motion
capture, no GPU.

```
rig.mjs        skeleton, solve(), twoBoneIK(), plantFoot(), springs, visemes, blinks
body.mjs       the artwork: capsules and curves, sized from the solved bones
animate.mjs    idle, walk (planted feet), gestures, wave, speech layer, composition
selfcheck.mjs  machine check: lengths, grounding, IK reach, determinism, bounds
_preview.mjs   pose sheet + walk strip for eyeballing changes
```

```bash
cd video_studio
node character/_preview.mjs --out /tmp/char.png   # pose sheet
node character/selfcheck.mjs                      # JSON, non-zero on failure
node films/character_speaks.mjs --out /tmp/frames --width 1920
```

## The two films

```
films/character_speaks.mjs     12 s dialogue vignette: walk in, four lines, wave
films/character_ships_it.mjs   32 s, eight chapters, one instrument panel each
```

The long cut is the one to study for framing: its camera takes the solved
skeleton's bounding box every frame, clamps the chapter's zoom to it and scales
about the soles, so a raised hand is never cropped and the figure never floats
above the floor line. `GROUND.sole` in `animate.mjs` is the offset that keeps the
*shoe* — not the ankle — on the ground.

## Design rules the code enforces

- **One space.** `solve()` applies the root scale to every length and offset;
  artwork sizes itself from the *solved* lengths, never the authored table. Mixing
  the two silently produced NaN geometry and detached limbs during development.
- **Feet are planted, not drawn.** `plantFoot()` solves the ankle from the ground
  line and clamps when the target is out of reach instead of teleporting the foot.
  The ankle sits one *sole* above the line, because the artwork draws a shoe that
  wraps the ankle; standing the hips exactly `HIP_HEIGHT` above the floor buried
  the soles into the ground.
- **Deterministic.** The same `t` always yields the same pose, so frames can be
  rendered out of order, retried, or split across CI jobs.
- **Lip-sync is a timeline, gated by audio.** `sampleVisemes()` eases between
  named mouth shapes and closes consonants; `speechLayer()` then multiplies that
  openness by the measured envelope of the real voice track, so the mouth shuts in
  every pause instead of puppeting through it.

## Voice

The dialogue cut is narrated locally by Piper (`video_studio/voiceover.py`) and
mixed with `video_studio/voice_mix.py`. The film reads the voice's own timings:

```
node films/character_speaks.mjs --out /tmp/frames --width 1920 \
  --voice-lines /tmp/voice/lines.json        # retimes cuts, captions, exits
```

Four audio lines are required, one per caption, so picture and voice cannot drift
apart silently — the film refuses a mismatched track instead of guessing.

## What this is not yet

- No deformation mesh or skinning: limbs are rigid capsules, so elbows and knees
  read as joints rather than flesh.
- No head turn beyond a few degrees; the face is front-on by construction.
- Mouth *shapes* still come from a text-derived viseme timeline; only the
  *amplitude* is measured from the audio. A phoneme aligner would make each shape
  follow the actual phone, not just the energy.
- One character. Two characters interacting needs a second rig instance and
  occlusion handling.
