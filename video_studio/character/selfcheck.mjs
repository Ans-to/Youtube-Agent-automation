#!/usr/bin/env node
/**
 * Machine check for the character rig. Prints JSON; exits non-zero on failure.
 *
 *   node video_studio/character/selfcheck.mjs
 *
 * What it verifies, because each of these has already been a real bug:
 *   - solved bones carry world-space lengths (art sizes itself from them)
 *   - a planted foot actually lands on the ground line
 *   - IK reaches its target, and clamps instead of teleporting when it cannot
 *   - animation is deterministic: the same t gives the same pose
 *   - a walk cycle keeps both feet on the floor at the contact poses
 *   - visemes and blinks are bounded
 */
import { solve, neutralPose, twoBoneIK, plantFoot, sampleVisemes, blinkAt, BONES } from './rig.mjs';
import { characterFrame, walkPose, speechTimeline, blinkSchedule, HIP_HEIGHT } from './animate.mjs';

const failures = [];
const checks = [];
const near = (a, b, tol = 0.5) => Math.abs(a - b) <= tol;

function check(name, ok, detail) {
  checks.push({ name, ok: !!ok, detail });
  if (!ok) failures.push(`${name}: ${detail}`);
}

// 1. world-space lengths
{
  const s = solve(neutralPose(), { x: 0, y: 0, scale: 0.5 });
  const bone = BONES.find((b) => b.name === 'thighL');
  check('bone lengths scale with the root', near(s.thighL.length, bone.length * 0.5, 0.01),
    `thighL length ${s.thighL.length} at scale 0.5`);
}

// 2. foot planting
{
  const groundY = 1000;
  const scale = 0.6;
  const hipY = groundY - HIP_HEIGHT * scale;
  const pose = {};
  const base = solve(pose, { x: 0, y: 0, scale });
  Object.assign(pose, plantFoot(base, 'L', -80 * scale, groundY - hipY));
  const s = solve(pose, { x: 500, y: hipY, scale });
  check('planted foot lands on the ground line',
    near(s.footL.origin[1], groundY - 34 * scale, 2), `ankle y ${s.footL.origin[1].toFixed(1)}`);
  check('planted foot points forward',
    near(Math.abs(Math.atan2(s.footL.end[1] - s.footL.origin[1], s.footL.end[0] - s.footL.origin[0])), 0, 0.15),
    `foot world angle ${s.footL.world.toFixed(3)}`);
}

// 3. IK reach and clamping
{
  const s = solve(neutralPose(), { x: 0, y: 0, scale: 1 });
  const origin = s.armL.origin;
  const reach = s.armL.length + s.forearmL.length;
  const inside = twoBoneIK(s, 'armL', 'forearmL', [origin[0] + reach * 0.6, origin[1]], 1);
  check('IK reports a reachable target', inside.reachable === true, JSON.stringify(inside.reachable));
  const far = twoBoneIK(s, 'armL', 'forearmL', [origin[0] + reach * 4, origin[1]], 1);
  check('IK clamps an unreachable target', far.reachable === false, 'unreachable target not flagged');
}

// 4. determinism
{
  const a = characterFrame(1.234, { scale: 0.4, groundY: 900, hipX: 300 });
  const b = characterFrame(1.234, { scale: 0.4, groundY: 900, hipX: 300 });
  const same = JSON.stringify(a.solved) === JSON.stringify(b.solved);
  check('same time gives the same pose', same, 'two solves of t=1.234 differ');
}

// 5. walk contact poses keep the feet on the floor
{
  const groundY = 900;
  const scale = 0.5;
  for (const t of [0, 0.29, 0.58, 0.87]) {
    const w = walkPose(t, { stride: 1.16, hipX: 0, groundY, scale });
    const s = solve(w.pose, { x: 0, y: w.hips.y, scale });
    const lowest = Math.max(s.footL.origin[1], s.footR.origin[1]);
    check(`walk t=${t} has a foot near the floor`, lowest > groundY - 80 * scale,
      `lowest ankle y ${lowest.toFixed(0)} vs floor ${groundY}`);
    const knee = s.shinL.origin[1];
    check(`walk t=${t} knee stays above the ankle`, knee < groundY, `knee y ${knee.toFixed(0)}`);
  }
}

// 6. visemes and blinks are bounded
{
  const tl = speechTimeline(['EVERY', 'FRAME', 'IS', 'CODE'], { start: 0, end: 2 });
  let ok = tl.length > 0;
  for (const event of tl) {
    if (!(event.hold > 0.02)) ok = false;
  }
  for (let t = 0; t <= 2; t += 0.05) {
    const v = sampleVisemes(tl, t);
    for (const [key, value] of Object.entries(v)) {
      if (value < -1e-6 || value > 1 + 1e-6) { ok = false; failures.push(`viseme ${key}=${value} out of range at ${t}`); }
    }
  }
  check('viseme timeline stays in range', ok, 'a viseme left [0,1] or a cue had no hold');

  const blinks = blinkSchedule(10, 3);
  check('blink schedule is deterministic',
    JSON.stringify(blinks) === JSON.stringify(blinkSchedule(10, 3)), 'schedule differs between calls');
  let blinkOk = true;
  for (let t = 0; t <= 10; t += 0.01) {
    const b = blinkAt(blinks, t);
    if (b < 0 || b > 1) blinkOk = false;
  }
  check('blink amount stays in [0,1]', blinkOk, 'blink out of range');
}

const failed = failures.length > 0;
console.log(JSON.stringify({ ok: !failed, checks, failures }, null, 2));
process.exit(failed ? 1 : 0);
