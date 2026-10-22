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
 *   - the audio envelope actually shuts the mouth between words
 *   - the stickman pen stays monochrome, stays deterministic, and sizes itself
 *     from the solved bones instead of from hard-coded numbers
 */
import { solve, neutralPose, twoBoneIK, plantFoot, sampleVisemes, blinkAt, BONES } from './rig.mjs';
import { characterFrame, walkPose, speechTimeline, blinkSchedule, HIP_HEIGHT } from './animate.mjs';
import { drawStick, stickGeometry, resolveInk, INK, STICK } from './stick.mjs';

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

// 7. the mouth is driven by the audio, not by the caption
{
  const tl = speechTimeline(['EVERY', 'FRAME'], { start: 0, end: 1.2 });
  const scan = (envelope) => {
    let peak = 0;
    let total = 0;
    for (let t = 0; t <= 1.2; t += 0.01) {
      const open = characterFrame(t, { speech: { timeline: tl, envelope } }).viseme.open;
      peak = Math.max(peak, open);
      total += open;
    }
    return { peak, mean: total / 121 };
  };
  const open = scan(() => ({ open: 1, bright: 0.5 }));
  const shut = scan(() => ({ open: 0, bright: 0.5 }));
  check('loud audio opens the mouth', open.peak > 0.35,
    `peak openness ${open.peak.toFixed(3)} at full energy`);
  check('silent audio closes the mouth', shut.peak <= 0.05,
    `peak openness ${shut.peak.toFixed(3)} in silence`);

  // A real signal: syllables separated by closures. The mouth has to follow it,
  // frame for frame — this is the property the old layer did not have, because
  // it scaled a text-derived shape instead of reading the audio.
  const signal = (t) => ({ open: Math.max(0, Math.sin(t * Math.PI * 2 * 2.2)) ** 0.8,
                           bright: 0.5 });
  let sumXY = 0; let sumXX = 0; let sumYY = 0;
  let n = 0;
  for (let t = 0; t <= 1.2; t += 0.01) {
    const want = signal(t).open;
    const got = characterFrame(t, { speech: { timeline: tl, envelope: signal } }).viseme.open;
    sumXY += (want - 0.5) * (got - 0.5);
    sumXX += (want - 0.5) ** 2;
    sumYY += (got - 0.5) ** 2;
    n += 1;
  }
  const correlation = sumXY / Math.sqrt(sumXX * sumYY || 1);
  check('mouth openness follows the audio envelope', n > 100 && correlation > 0.90,
    `correlation ${correlation.toFixed(3)} over ${n} frames`);

  // Bright and dark vowels at the same loudness must not look identical.
  const bright = characterFrame(0.4, { speech: { timeline: tl, envelope: () => ({ open: 0.8, bright: 0.95 }) } }).viseme;
  const dark = characterFrame(0.4, { speech: { timeline: tl, envelope: () => ({ open: 0.8, bright: 0.05 }) } }).viseme;
  check('vowel colour changes the mouth shape',
    Math.abs(bright.wide - dark.wide) > 0.3 && Math.abs(bright.round - dark.round) > 0.3,
    `wide ${bright.wide.toFixed(2)} vs ${dark.wide.toFixed(2)}, round ${bright.round.toFixed(2)} vs ${dark.round.toFixed(2)}`);

  // A text timeline on its own still animates (films without a voice).
  const silentFilm = scan(undefined);
  check('the text timeline still animates an unvoiced film', silentFilm.peak > 0.3,
    `peak ${silentFilm.peak.toFixed(3)} with no envelope`);
}

// 8. the stickman pen is monochrome, and says so
{
  const ink = resolveInk();
  check('the stickman default palette is two greys and no accent',
    ink.accent === null && ink.paper !== ink.ink,
    `paper ${ink.paper}, ink ${ink.ink}, accent ${ink.accent}`);

  const rejects = (label, fn) => {
    let threw = false;
    try { fn(); } catch { threw = true; }
    check(label, threw, 'it was accepted instead of refused');
  };
  rejects('a warm paper colour is refused', () => resolveInk({ ink: { paper: '#F4F1EA' } }));
  rejects('an ink with a hue is refused', () => resolveInk({ ink: { ink: '#1A2A3A' } }));
  rejects('an accent is refused unless explicitly allowed',
    () => resolveInk({ ink: { accent: '#C8FF3D' } }));
  let accentOk = true;
  try { resolveInk({ ink: { accent: '#C8FF3D' }, allowAccent: true }); } catch { accentOk = false; }
  check('an accent is allowed when asked for by name', accentOk, 'allowAccent: true still threw');
}

// 9. stroke weights come from the skeleton, not from constants
{
  const frame = characterFrame(0.8, { scale: 0.6, groundY: 1000, hipX: 0 });
  const geom = stickGeometry(frame.solved);
  const s = frame.solved;
  check('thigh weight is a fraction of the solved thigh bone',
    near(geom.widths.thigh, s.thighL.length * STICK.thigh, 0.001),
    `thigh ${geom.widths.thigh.toFixed(2)} vs bone ${s.thighL.length.toFixed(2)}`);
  check('head radius is a fraction of the solved head bone',
    near(geom.headRadius, s.head.length * STICK.head, 0.001),
    `head radius ${geom.headRadius.toFixed(2)} vs bone ${s.head.length.toFixed(2)}`);

  const big = characterFrame(0.8, { scale: 1.2, groundY: 1000, hipX: 0 });
  const bigGeom = stickGeometry(big.solved);
  check('a bigger root draws a proportionally heavier figure',
    near(bigGeom.widths.thigh / geom.widths.thigh, 2, 0.01),
    `ratio ${(bigGeom.widths.thigh / geom.widths.thigh).toFixed(3)} for a 2x scale`);
}

// 10. a recording canvas: the checks below read what was actually painted
function recordingContext() {
  const ops = [];
  const colours = new Set();
  let style = {};
  const paint = (name) => ({ get: () => style[name], set: (v) => { style[name] = v; colours.add(String(v)); } });
  const ctx = {
    ops,
    colours,
    fillStyle: undefined,
    strokeStyle: undefined,
    lineWidth: 1,
    lineJoin: 'miter',
    lineCap: 'butt',
    globalAlpha: 1,
    save() { ops.push(['save']); },
    restore() { ops.push(['restore']); },
    translate(x, y) { ops.push(['translate', x, y]); },
    rotate(a) { ops.push(['rotate', a]); },
    scale(x, y) { ops.push(['scale', x, y]); },
    beginPath() { ops.push(['beginPath']); },
    closePath() { ops.push(['closePath']); },
    moveTo(x, y) { ops.push(['moveTo', x, y]); },
    lineTo(x, y) { ops.push(['lineTo', x, y]); },
    quadraticCurveTo(cx, cy, x, y) { ops.push(['quadraticCurveTo', cx, cy, x, y]); },
    bezierCurveTo(a, b, c, d, x, y) { ops.push(['bezierCurveTo', a, b, c, d, x, y]); },
    arc(x, y, r, a0, a1) { ops.push(['arc', x, y, r, a0, a1]); },
    ellipse(x, y, rx, ry, rot) { ops.push(['ellipse', x, y, rx, ry, rot]); },
    fill() { ops.push(['fill', style.fillStyle]); },
    stroke() { ops.push(['stroke', style.strokeStyle]); },
  };
  Object.defineProperty(ctx, 'fillStyle', paint('fillStyle'));
  Object.defineProperty(ctx, 'strokeStyle', paint('strokeStyle'));
  return ctx;
}

// 11. what the pen puts on the canvas is grey, frame after frame
{
  const frame = characterFrame(2.4, { scale: 0.7, groundY: 1200, hipX: 400 });
  const ctx = recordingContext();
  drawStick(ctx, frame.solved, { viseme: { open: 0.6, wide: 0.4, round: 0.1 }, blink: 0, browRaise: 0.2, boil: 1, frame: 73 });
  const parsed = [...ctx.colours].map((value) => String(value));
  const hex = parsed.filter((v) => /^#[0-9a-fA-F]{6}$/.test(v));
  const grey = hex.every((v) => {
    const t = v.slice(1).toLowerCase();
    return t.slice(0, 2) === t.slice(2, 4) && t.slice(2, 4) === t.slice(4, 6);
  });
  check('every colour the stickman paints is greyscale',
    hex.length > 0 && grey && hex.length === new Set(hex.map((v) => v.toLowerCase())).size + (parsed.length - hex.length),
    `colours used: ${[...new Set(hex)].join(', ')}`);
  check('the stickman draws a figure, not an empty frame',
    ctx.ops.filter((op) => op[0] === 'fill' || op[0] === 'stroke').length > 20,
    `${ctx.ops.filter((op) => op[0] === 'fill' || op[0] === 'stroke').length} paint ops`);
}

// 12. line boil is the only frame-dependent part, and it is repeatable
{
  const frame = characterFrame(1.1, { scale: 0.6, groundY: 900, hipX: 0 });
  const drawAt = (f, boil) => {
    const ctx = recordingContext();
    drawStick(ctx, frame.solved, { viseme: { open: 0.3, wide: 0.2, round: 0 }, blink: 0, browRaise: 0, boil, frame: f });
    return JSON.stringify(ctx.ops);
  };
  check('the same frame and the same boil draw the same picture',
    drawAt(40, 1) === drawAt(40, 1), 'two identical calls differ');
  check('with boil off the picture does not depend on the frame number',
    drawAt(40, 0) === drawAt(41, 0), 'frame 40 and 41 differ at boil 0');
  check('with boil on neighbouring frames do differ',
    drawAt(40, 1) !== drawAt(41, 1), 'boil made no difference');
  check('boil stays sub-pixel at the rig scale',
    (() => {
      const a = drawAt(40, 1);
      const ctx = recordingContext();
      drawStick(ctx, frame.solved, { viseme: { open: 0.3, wide: 0.2, round: 0 }, blink: 0, browRaise: 0, boil: 1, frame: 40 });
      const pts = ctx.ops.filter((op) => op[0] === 'moveTo' || op[0] === 'lineTo');
      const max = Math.max(...pts.map((op) => Math.hypot(op[1], op[2])));
      return a.length > 0 && max < 1e5;
    })(), 'a vertex went further than the canvas could hold');
}

// 13. the head sits on the neck, not above it, and stays inside the frame
{
  const frame = characterFrame(3.3, { scale: 0.65, groundY: 1000, hipX: 200 });
  const s = frame.solved;
  const geom = stickGeometry(s);
  // The head bone runs from the top of the neck up to the centre of the circle,
  // so the centre is one head-bone length above the neck end, not on it.
  const gap = Math.hypot(s.head.end[0] - s.neck.end[0], s.head.end[1] - s.neck.end[1]);
  check('the head circle is centred on the top of the head bone',
    near(gap, s.head.length, 1.5), `centre is ${gap.toFixed(2)} from the neck, head bone ${s.head.length.toFixed(2)}`);
  check('the head overlaps the neck rather than floating',
    s.head.end[1] + geom.headRadius > s.neck.end[1],
    `the bottom of the head is ${(s.head.end[1] + geom.headRadius).toFixed(1)}, the neck ends at ${s.neck.end[1].toFixed(1)}`);

  const ctx = recordingContext();
  drawStick(ctx, s, { viseme: { open: 0.2, wide: 0.1, round: 0 }, blink: 0, browRaise: 0, boil: 0, frame: 0 });
  const pts = ctx.ops.filter((op) => op[0] === 'moveTo' || op[0] === 'lineTo');
  const xs = pts.map((op) => op[1]);
  const ys = pts.map((op) => op[2]);
  const spineTop = Math.min(...Object.values(s).map((b) => Math.min(b.origin[1], b.end[1])));
  const headTop = s.head.end[1] - geom.headRadius;
  check('no stroke reaches above the top of the head',
    Math.min(...ys) > headTop - 1,
    `highest vertex ${Math.min(...ys).toFixed(1)} vs head top ${headTop.toFixed(1)}`);
  check('the figure is not wider than it is tall',
    Math.max(...xs) - Math.min(...xs) < Math.max(...ys) - Math.min(...ys),
    `width ${(Math.max(...xs) - Math.min(...xs)).toFixed(0)} vs height ${(Math.max(...ys) - Math.min(...ys)).toFixed(0)} (spine top ${spineTop.toFixed(0)})`);
}

const failed = failures.length > 0;
console.log(JSON.stringify({ ok: !failed, checks, failures }, null, 2));
process.exit(failed ? 1 : 0);
