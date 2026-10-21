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

## Design rules the code enforces

- **One space.** `solve()` applies the root scale to every length and offset;
  artwork sizes itself from the *solved* lengths, never the authored table. Mixing
  the two silently produced NaN geometry and detached limbs during development.
- **Feet are planted, not drawn.** `plantFoot()` solves the ankle from the ground
  line and clamps when the target is out of reach instead of teleporting the foot.
- **Deterministic.** The same `t` always yields the same pose, so frames can be
  rendered out of order, retried, or split across CI jobs.
- **Lip-sync is a timeline.** `sampleVisemes()` eases between named mouth shapes
  and closes consonants; it is not a random mouth flap.

## What this is not yet

- No deformation mesh or skinning: limbs are rigid capsules, so elbows and knees
  read as joints rather than flesh.
- No head turn beyond a few degrees; the face is front-on by construction.
- Visemes are timed from text, not from actual audio. Wiring a local phoneme
  aligner would make the mouth follow a real voice track.
- One character. Two characters interacting needs a second rig instance and
  occlusion handling.
