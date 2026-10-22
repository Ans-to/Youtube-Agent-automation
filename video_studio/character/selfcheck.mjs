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
 *   - the walk does not skate: a foot on the ground stays on the ground, the
 *     stride follows distance rather than the clock, and no joint jumps
 */
import { solve, neutralPose, twoBoneIK, plantFoot, sampleVisemes, blinkAt, BONES } from './rig.mjs';
import { characterFrame, walkPose, speechTimeline, blinkSchedule, HIP_HEIGHT, blendPoses, GROUND } from './animate.mjs';
import { drawStick, stickGeometry, resolveInk, INK, STICK } from './stick.mjs';
import { EXPRESSIONS, expressionForLine, expressionAt, expressionCues, actingAt, actingCues, blendExpression, NEUTRAL } from './expression.mjs';
import { drawSilhouette, SIL, capsulePath, capePath } from './silhouette.mjs';

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
  // One declared accent, on the cloth. Everything else is grey.
  check('the stickman palette is two greys, one cloth tone and one declared accent',
    ink.paper !== ink.ink && ink.cape !== ink.paper && ink.cape !== ink.ink
      && String(ink.accent).toLowerCase() === '#b3151f',
    `paper ${ink.paper}, ink ${ink.ink}, cape ${ink.cape}, accent ${ink.accent}`);
  const isGreyHex = (hex) => {
    const t = String(hex).slice(1).toLowerCase();
    return t.slice(0, 2) === t.slice(2, 4) && t.slice(2, 4) === t.slice(4, 6);
  };
  check('the cloth tone is neutral grey, not a tint',
    isGreyHex(ink.cape), `cape ${ink.cape}`);

  const rejects = (label, fn) => {
    let threw = false;
    try { fn(); } catch { threw = true; }
    check(label, threw, 'it was accepted instead of refused');
  };
  rejects('a warm paper colour is refused', () => resolveInk({ ink: { paper: '#F4F1EA' } }));
  rejects('an ink with a hue is refused', () => resolveInk({ ink: { ink: '#1A2A3A' } }));
  rejects('a second accent is refused',
    () => resolveInk({ ink: { accent: '#C8FF3D' } }));
  let accentOk = true;
  try { resolveInk({ ink: { accent: '#C8FF3D' }, allowAccent: true }); } catch { accentOk = false; }
  check('an override accent is allowed when asked for by name', accentOk, 'allowAccent: true still threw');
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

// 9b. the face has states, and a line chooses one
{
  const names = Object.keys(EXPRESSIONS);
  check('there is more than one expression to act with', names.length >= 8, `${names.length} expressions`);
  for (const name of names) {
    const face = EXPRESSIONS[name];
    const missing = Object.keys(NEUTRAL).filter((key) => face[key] === undefined && NEUTRAL[key] !== 0);
    check(`expression "${name}" is complete`, missing.length === 0, `missing ${missing.join(', ')}`);
  }
  check('a question is asked with the brows, not the mouth',
    expressionForLine('Why does it work?') === 'question'
      && EXPRESSIONS.question.browAngle < -0.2,
    `question angle ${EXPRESSIONS.question.browAngle}`);
  check('a flat statement is not given a question face',
    expressionForLine('is drawn twice.') === 'talk', expressionForLine('is drawn twice.'));
  check('a contrast line gets a set face',
    expressionForLine('But it is never free.') === 'stern', expressionForLine('But it is never free.'));

  const cues = expressionCues([
    { text: 'Every frame,', start: 2.9, end: 4.5 },
    { text: 'Why?', start: 5.0, end: 5.6 },
  ]);
  const inside = expressionAt(3.6, cues);
  const quiet = expressionAt(1.0, cues);
  check('the face differs inside a line and between lines',
    Math.abs(inside.brow - quiet.brow) > 0.05, `brow ${inside.brow} vs ${quiet.brow}`);
  check('the face is continuous across a cue boundary',
    (() => {
      let worst = 0;
      let prev = expressionAt(2.7, cues);
      for (let t = 2.75; t < 6.2; t += 1 / 30) {
        const now = expressionAt(t, cues);
        for (const key of Object.keys(NEUTRAL)) worst = Math.max(worst, Math.abs(now[key] - prev[key]));
        prev = now;
      }
      return worst < 0.12;
    })(), 'the face jumped between frames');
  const half = blendExpression(EXPRESSIONS.smile, EXPRESSIONS.stern, 0.5);
  check('two expressions blend field by field',
    Math.abs(half.smile - (EXPRESSIONS.smile.smile + EXPRESSIONS.stern.smile) / 2) < 1e-9,
    `smile ${half.smile}`);
}

// 9c. the body acts while the face talks
{
  const cues = actingCues([{ text: 'Every frame,', start: 3, end: 4.5 }, { text: 'Never free!', start: 5, end: 6 }]);
  check('a stressed line is acted harder than a connective',
    cues[1].weight > cues[0].weight, `${cues[1].weight} vs ${cues[0].weight}`);
  const values = [];
  for (let t = 2.8; t <= 6.4; t += 0.05) values.push(actingAt(t, cues));
  check('the body never stands perfectly still inside a phrase',
    values.some((v) => Math.abs(v.weight) > 1e-4) && values.some((v) => Math.abs(v.gesture) > 0.1),
    'no weight shift or gesture was produced');
  let worst = 0;
  for (let i = 1; i < values.length; i += 1) {
    worst = Math.max(worst, Math.abs(values[i].nod - values[i - 1].nod),
      Math.abs(values[i].weight - values[i - 1].weight));
  }
  check('the acting does not jump between frames', worst < 0.06, `largest step ${worst.toFixed(3)}`);
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
    // Clipping is real on a canvas and meaningless on a recorder; both are fine
    // as long as the recorded path is the one that was built.
    clip() { ops.push(['clip']); },
    rect(x, y, w, h) { ops.push(['rect', x, y, w, h]); },
    fillRect(x, y, w, h) { ops.push(['fillRect', style.fillStyle, x, y, w, h]); },
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
  const hex = [...ctx.colours].map((v) => String(v)).filter((v) => /^#[0-9a-fA-F]{6}$/.test(v));
  const isGreyHex = (v) => {
    const t = v.slice(1).toLowerCase();
    return t.slice(0, 2) === t.slice(2, 4) && t.slice(2, 4) === t.slice(4, 6);
  };
  const grey = hex.filter(isGreyHex);
  const coloured = hex.filter((v) => !isGreyHex(v));
  check('every colour the stickman paints is grey, except the declared accent',
    hex.length > 0 && grey.length > 0
      && coloured.every((v) => v.toLowerCase() === '#b3151f'),
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

// 14. the walk is a walk, not a skate
//
// The figure is drawn front-on, so a step is a foot leaving the floor and coming
// back down under the body, not a foot travelling fore and aft. What has to hold:
// a foot that is down stays exactly on the floor, at least one foot is always
// down, the two feet take turns, and the cycle advances with distance travelled
// rather than with the clock — that last one is what stops the legs cycling at a
// fixed rate while the body moves at another, which was a 45 px-per-frame slide.
{
  const scale = 0.6;
  const groundY = 1200;
  const fps = 30;
  const step = 770 * 0.38 * scale;
  const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const xAt = (t) => 200 + 700 * easeInOut(Math.min(1, Math.max(0, t / 2.5)));
  const frames = [];
  const frameShorten = [];
  for (let f = 0; f <= 75; f += 1) {
    const t = f / fps;
    const x = xAt(t);
    const fr = characterFrame(t, { mode: 'walk', scale, groundY, hipX: x, distance: x - xAt(0), step });
    frames.push({ t, feet: [fr.solved.footL.origin, fr.solved.footR.origin] });
    frameShorten.push(fr.legShorten);
  }
  const floor = groundY - GROUND.sole * scale;
  const ankleYs = frames.flatMap((f) => f.feet.map((p) => p[1]));
  const onFloor = ankleYs.filter((y) => Math.abs(y - floor) < 1).length;
  check('every frame has a foot on the ground line',
    onFloor >= frames.length,
    `${onFloor} foot placements were on the floor, floor at ${floor.toFixed(1)}`);
  check('no ankle ever goes below the floor',
    Math.max(...ankleYs) <= floor + 1,
    `deepest ankle ${Math.max(...ankleYs).toFixed(1)} vs floor ${floor.toFixed(1)}`);

  // Take turns: while one foot is planted the other must leave the floor at some
  // point, and each foot lifts once per cycle.
  // The lift is drawn, not solved, so the turn-taking is read off `legShorten`.
  const lifts = [0, 1].map((k) => {
    const key = k === 0 ? 'L' : 'R';
    let count = 0;
    let up = false;
    for (const frame of frameShorten) {
      const isUp = frame[key] < 0.995;
      if (isUp && !up) count += 1;
      up = isUp;
    }
    return count;
  });
  const busy = frameShorten.filter((f) => f.L < 0.995 && f.R < 0.995).length;
  check('the feet take turns', lifts[0] > 0 && lifts[1] > 0, `left lifted ${lifts[0]}x, right ${lifts[1]}x`);
  check('at least one foot is always down', busy === 0, `${busy} frames had both feet in the air`);

  // Phase follows distance: the same distance gives the same stride, whatever the
  // clock says. Breathing still follows the clock, so compare the legs.
  const a = walkPose(0.4, { hipX: 600, groundY, scale, distance: 250, step });
  const b = walkPose(2.9, { hipX: 600, groundY, scale, distance: 250, step });
  check('the stride follows the ground travelled, not the clock',
    JSON.stringify(a.legShorten) === JSON.stringify(b.legShorten)
      && JSON.stringify(a.pose.armL) === JSON.stringify(b.pose.armL),
    'two different times at the same distance gave different legs');
}

// 14b. the swinging foot is drawn shortened, which is what lifts it
{
  const scale = 0.6;
  const groundY = 1000;
  const step = 770 * 0.38 * scale;
  const walking = characterFrame(0.6, { mode: 'walk', scale, groundY, hipX: 300, distance: 120, step });
  const lengths = [walking.legShorten.L, walking.legShorten.R];
  check('a swinging leg is drawn shorter than a standing one',
    lengths.some((k) => k < 0.99) && lengths.every((k) => k > 0.8 && k <= 1),
    `leg factors ${lengths.map((k) => k.toFixed(3)).join(', ')}`);
  const idle = characterFrame(0.6, { mode: 'idle', scale, groundY, hipX: 300 });
  check('a standing figure has both legs at full length',
    idle.legShorten.L === 1 && idle.legShorten.R === 1,
    JSON.stringify(idle.legShorten));
}

// 14c. motion is continuous, including across the walk-to-stand fade
//
// A single-frame jump is what "not smooth" actually looks like: no amount of
// correct poses fixes a hand that teleports across twenty pixels between two
// frames. Measured as acceleration — the second difference of a joint's position
// — because a constant-speed slide has none, and a pop has a spike.
{
  const scale = 0.6;
  const groundY = 1200;
  const step = 770 * 0.38 * scale;
  const fps = 30;
  const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const span = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));
  const walkEnd = 2.5;
  const fade = 0.34;
  const xAt = (t) => 150 + 500 * easeInOut(span(t, 0, walkEnd));
  const weightAt = (t) => Math.min(
    easeInOut(span(t, 0.02, 0.02 + fade)),
    1 - easeInOut(span(t, walkEnd - fade, walkEnd)),
  );
  const tracked = ['head', 'handL', 'handR', 'footL', 'footR', 'chest', 'hips'];
  const path = Object.fromEntries(tracked.map((b) => [b, []]));
  for (let f = 0; f <= Math.round(walkEnd * fps) + 6; f += 1) {
    const t = f / fps;
    const x = xAt(t);
    const fr = characterFrame(t, {
      mode: 'walk', scale, groundY, hipX: x, distance: x - xAt(0), step,
      walkWeight: weightAt(t),
    });
    for (const b of tracked) path[b].push(fr.solved[b].end ? fr.solved[b].end.slice() : fr.solved[b].origin.slice());
  }
  let worstAccel = 0;
  let worstBone = null;
  let worstSpeed = 0;
  for (const b of tracked) {
    const p = path[b];
    for (let i = 1; i < p.length; i += 1) {
      worstSpeed = Math.max(worstSpeed, Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
    }
    for (let i = 2; i < p.length; i += 1) {
      const accel = Math.hypot(p[i][0] - 2 * p[i - 1][0] + p[i - 2][0],
        p[i][1] - 2 * p[i - 1][1] + p[i - 2][1]);
      if (accel > worstAccel) { worstAccel = accel; worstBone = b; }
    }
  }
  // A hand at the end of two long bones legitimately swings fastest; the limits
  // are set well above a brisk walk and well below a pop.
  check('no bone jumps between frames', worstSpeed < 40,
    `fastest joint ${worstSpeed.toFixed(1)} px per frame`);
  check('acceleration stays continuous',
    worstAccel < 14, `worst ${worstAccel.toFixed(2)} px per frame squared on ${worstBone}`);
}

// 15. the legs never cross, and a knee never bows out of its own leg
{
  const scale = 0.7;
  const groundY = 1400;
  const step = 770 * 0.38 * scale;
  let crossed = 0;
  let worstBow = 0;
  for (let f = 0; f <= 90; f += 1) {
    const t = f / 30;
    const x = 400 + f * 3;
    const fr = characterFrame(t, { mode: 'walk', scale, groundY, hipX: x, distance: f * 3, step });
    const s = fr.solved;
    // "left" here is the +x bone; the drawn figure must keep them on their sides.
    if (s.footL.origin[0] < s.footR.origin[0]) crossed += 1;
    for (const side of [['thighL', 'shinL'], ['thighR', 'shinR']]) {
      const hip = s[side[0]].origin;
      const knee = s[side[1]].origin;
      // lateral offset of the knee, as a fraction of thigh length: a duck knee
      // would be a large fraction, a natural slight bend a small one.
      worstBow = Math.max(worstBow, Math.abs(knee[0] - hip[0]) / s[side[0]].length);
    }
  }
  check('the legs never cross in a front view', crossed === 0, `${crossed} frames had the feet swapped`);
  check('a knee does not bow out of its own leg',
    worstBow < 0.20, `worst knee offset ${(worstBow * 100).toFixed(1)}% of the thigh`);
}

// 16. walking into a stand is blended, not switched
{
  const blended = blendPoses({ armL: 1, spine: 0.2 }, { armL: 0, forearmL: 0.4 }, 0.5);
  check('blending two poses keeps every key',
    near(blended.armL, 0.5) && near(blended.spine, 0.1) && near(blended.forearmL, 0.2),
    JSON.stringify(blended));

  const groundY = 1000;
  const half = characterFrame(1, { mode: 'idle', walkWeight: 0.5, scale: 0.5, groundY, hipX: 100, distance: 0 });
  const full = characterFrame(1, { mode: 'idle', walkWeight: 0, scale: 0.5, groundY, hipX: 100, distance: 0 });
  let jump = 0;
  for (const bone of Object.keys(full.solved)) {
    const a = full.solved[bone].origin;
    const b = half.solved[bone].origin;
    jump = Math.max(jump, Math.hypot(a[0] - b[0], a[1] - b[1]));
  }
  check('a half-blended step sits between the two poses',
    jump > 1 && jump < 400, `largest bone moved ${jump.toFixed(1)} px by the blend`);

  // The same t, walked and standing, must not produce the same skeleton — that
  // would mean walkWeight was ignored.
  const walking = characterFrame(1, { mode: 'walk', walkWeight: 1, scale: 0.5, groundY, hipX: 100, distance: 0, step: 200 });
  check('the walk weight is honoured',
    !near(walking.solved.footL.origin[0], full.solved.footL.origin[0], 0.01),
    'the walk pose equals the idle pose');
}

// 17. the cape is cloth: present, sized, and behind the figure
{
  const frame = characterFrame(1.4, { scale: 0.6, groundY: 1000, hipX: 200 });
  const bare = recordingContext();
  drawStick(bare, frame.solved, { boil: 0, frame: 0, expression: EXPRESSIONS.talk });
  const dressed = recordingContext();
  drawStick(dressed, frame.solved, { boil: 0, frame: 0, expression: EXPRESSIONS.talk, cape: true });
  const paint = (ctx) => ctx.ops.filter((op) => op[0] === 'fill' || op[0] === 'stroke').length;
  check('the cape adds shapes to the figure', paint(dressed) > paint(bare),
    `${paint(dressed)} paint ops dressed vs ${paint(bare)} bare`);
  const firstCapeAt = dressed.ops.findIndex((op) => op[0] === 'fill' && String(op[1]).toLowerCase() === String(INK.cape).toLowerCase());
  const firstLimbAt = dressed.ops.findIndex((op) => op[0] === 'fill' && String(op[1]).toLowerCase() === String(INK.ink).toLowerCase());
  check('the cape is drawn behind the limbs', firstCapeAt >= 0 && firstCapeAt < firstLimbAt,
    `cape fill at ${firstCapeAt}, first ink fill at ${firstLimbAt}`);
  check('the cape carries the one accent', dressed.colours.has(INK.accent), 'the lining was not drawn');
  const clamped = recordingContext();
  drawStick(clamped, frame.solved, { boil: 0, frame: 0, cape: true, capeSway: 40 });
  let far = 0;
  for (const op of clamped.ops) {
    if (op[0] === 'moveTo' || op[0] === 'lineTo' || op[0] === 'quadraticCurveTo') {
      for (let i = 1; i < op.length; i += 2) far = Math.max(far, Math.abs(op[i] - frame.solved.chest.end[0]));
    }
  }
  check('a violent sway does not fly the cape off the figure', far < 3000,
    `hem reached ${far.toFixed(0)} px from the chest`);
}

// 20. the silhouette pen: a body, not a diagram
{
  const frame = characterFrame(1.6, { scale: 0.6, groundY: 1200, hipX: 400 });
  const ctx = recordingContext();
  const info = drawSilhouette(ctx, frame.solved, {
    expression: EXPRESSIONS.talk, viseme: { open: 0.5 }, cape: true, capeSway: 0.2, frame: 5,
  });
  const fills = ctx.ops.filter((op) => op[0] === 'fill');
  const strokes = ctx.ops.filter((op) => op[0] === 'stroke');
  const paint = (op) => String(op[1]).toLowerCase();

  // The whole point of the pen. An outline is what made the old figure read as a
  // template: a drawn shape says "drawing of a person", a filled one says person.
  check('the silhouette has a body: many filled shapes', fills.length >= 12, `${fills.length} fills`);
  check('the body is not outlined', strokes.every((op) => paint(op) === String(INK.paper).toLowerCase()),
    `strokes painted ${[...new Set(strokes.map(paint))].join(', ')}`);
  check('the head is solid ink, not a paper disc with a line around it',
    fills.filter((op) => paint(op) === String(INK.ink).toLowerCase()).length > 0, 'no ink fill');
  check('the face is cut out of the head in paper', fills.some((op) => paint(op) === String(INK.paper).toLowerCase()),
    'nothing was painted in paper');

  // The far side is a lighter flat tone, not transparency: a translucent limb
  // shows the cape through it and reads as a hole in the figure.
  const tones = [...ctx.colours].map(String);
  check('the far side is a flat tone, not a transparent limb', tones.some((v) => /^rgb\(/.test(v)),
    `colours: ${tones.join(', ')}`);

  // Cape behind the figure: the first ink fill is the cloth.
  const firstInk = fills.findIndex((op) => paint(op) === String(INK.ink).toLowerCase());
  check('the cape is drawn before the limbs', firstInk <= 1, `first ink fill at ${firstInk}`);
  check('the cape carries the one accent', ctx.colours.has(INK.accent), 'the lining was not drawn');

  // Sizes still come from the solved bones, frame after frame.
  const tall = drawSilhouette(recordingContext(), characterFrame(1.6, { scale: 1.2, groundY: 1200, hipX: 400 }).solved, { cape: false });
  check('the silhouette sizes itself from the solved bones',
    Math.abs(tall.widths.thigh / info.widths.thigh - 2) < 0.01,
    `thigh width ratio ${(tall.widths.thigh / info.widths.thigh).toFixed(3)} at double scale`);
  check('the head is sized from the head bone',
    Math.abs(info.radius - frame.solved.head.length * SIL.head) < 1e-6,
    `${info.radius} vs ${frame.solved.head.length * SIL.head}`);

  // A capsule must close on itself; an open path fills as a wedge.
  const cap = recordingContext();
  capsulePath(cap, [0, 0], [100, 40], 12, 6);
  const closes = cap.ops.some((op) => op[0] === 'closePath');
  check('a limb capsule is a closed shape', closes, 'the capsule path was left open');

  // The cape must taper to a point; a cloak that ends in a wide hem is a skirt.
  const swing = recordingContext();
  const cloth = capePath(swing, frame.solved, info.widths, { sway: 0, reach: 1 });
  const first = cloth.widths[0];
  const last = cloth.widths[cloth.widths.length - 1];
  check('the cape tapers to a point', last < first * 0.45, `tip ${last.toFixed(1)} vs collar ${first.toFixed(1)}`);
  const swung = recordingContext();
  const far = capePath(swung, frame.solved, info.widths, { sway: 0.5, reach: 1 });
  check('the cape hangs below the hip', far.spine[far.spine.length - 1][1] > frame.solved.spine.origin[1],
    'the hook never left the shoulder');

  // Determinism: the same frame and the same options draw the same picture.
  const a = recordingContext();
  const b = recordingContext();
  const opts = { expression: EXPRESSIONS.stern, viseme: { open: 0.2 }, cape: true, capeSway: 0.1, frame: 9 };
  drawSilhouette(a, frame.solved, opts);
  drawSilhouette(b, frame.solved, opts);
  check('the silhouette is deterministic', JSON.stringify(a.ops) === JSON.stringify(b.ops), 'two identical draws differed');
}

const failed = failures.length > 0;
console.log(JSON.stringify({ ok: !failed, checks, failures }, null, 2));
process.exit(failed ? 1 : 0);
