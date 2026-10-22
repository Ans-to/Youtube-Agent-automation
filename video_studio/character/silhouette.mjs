/**
 * The figure, drawn as a solid silhouette.
 *
 * `stick.mjs` builds the character out of tapered *strokes* with joint dots and
 * an outlined head. That is a diagram of a skeleton: it reads as a template no
 * matter how carefully the strokes are shaped, because an outline says "drawing
 * of a thing" rather than "thing".
 *
 * This pen draws the same solved skeleton as *filled volumes* — a chest mass, a
 * waist, a seat, capsules for the limbs, a shoe for the foot, a solid disc for
 * the head — with no outlines and no joint dots. Overlapping opaque shapes merge
 * into one body, which is what makes a shadow read as a person. The face is cut
 * out of the head in paper, the way the reference figure is cut out of the stage.
 *
 * Everything is still generated per frame from the rig. There is no art file.
 */
import { resolveInk } from './stick.mjs';
import { EXPRESSIONS } from './expression.mjs';

/** Widths as fractions of the bone that carries them. */
export const SIL = {
  torso: 0.10,
  neck: 0.055,
  arm: 0.050,
  forearm: 0.044,
  thigh: 0.078,
  shin: 0.064,
  shoe: 0.074,
  /** Head radius as a fraction of the head bone.
   *
   * At 1.12 the head is a third of the body height and the figure reads as a
   * doll. The reference figure is about five heads tall: a big, round, readable
   * head with no neck to speak of.
   */
  head: 0.70,
  /** How far the far side is lifted toward white. */
  farLift: 0.16,
  /** Cape reach below the hip, as a fraction of the leg length. */
  capeReach: 0.92,
};

const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
const perp = (a, b) => {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  return [-dy / len, dx / len];
};

/** Mix a hex colour toward white — the far side of the figure. */
function farTone(hex, amount) {
  const value = String(hex).replace('#', '');
  const channel = (index) => {
    const part = parseInt(value.slice(index * 2, index * 2 + 2), 16);
    return Math.round(part + (255 - part) * amount);
  };
  return `rgb(${channel(0)},${channel(1)},${channel(2)})`;
}

/**
 * A tapered capsule as a closed path.
 *
 * Built from sample points rather than `arc()`: canvas arc direction depends on
 * winding, and getting it wrong on one of four caps turns a limb inside out. Two
 * half-circles walked in order cannot be wound wrong.
 */
export function capsulePath(ctx, a, b, ra, rb, steps = 10) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) {
    ctx.beginPath();
    ctx.arc(a[0], a[1], Math.max(ra, rb), 0, Math.PI * 2);
    return;
  }
  const ux = dx / len;
  const uy = dy / len;
  const nx = -uy;
  const ny = ux;
  ctx.beginPath();
  for (let i = 0; i <= steps; i += 1) {
    const phi = -Math.PI / 2 + (Math.PI * i) / steps;
    const c = Math.cos(phi);
    const s = Math.sin(phi);
    ctx.lineTo(b[0] + rb * (c * ux + s * nx), b[1] + rb * (c * uy + s * ny));
  }
  for (let i = 0; i <= steps; i += 1) {
    const phi = Math.PI / 2 + (Math.PI * i) / steps;
    const c = Math.cos(phi);
    const s = Math.sin(phi);
    ctx.lineTo(a[0] + ra * (c * ux + s * nx), a[1] + ra * (c * uy + s * ny));
  }
  ctx.closePath();
}

/** Fill a tapered capsule between two joints. */
export function limbFill(ctx, a, b, ra, rb, colour) {
  if (!a || !b) return;
  capsulePath(ctx, a, b, ra, rb);
  ctx.fillStyle = colour;
  ctx.fill();
}

/**
 * The torso, as overlapping solid masses rather than one welded outline.
 *
 * An outline that walks neck → shoulders → waist → hips has to cross itself at
 * the waist to stay narrow, and a crossed path leaves white triangles on the
 * chest. Shapes filled in the same ink merge into one body with no seam and
 * cannot invert.
 */
export function torsoMass(ctx, s, w, colour) {
  const chest = s.chest.end;
  const hip = s.spine.origin;
  const shL = s.armL.origin;
  const shR = s.armR.origin;
  const hipL = s.thighL.origin;
  const hipR = s.thighR.origin;
  const shoulderHalf = dist(shL, shR) * 0.50 + w.arm * 0.75;
  const hipHalf = dist(hipL, hipR) * 0.44 + w.thigh * 0.5;
  const waistHalf = Math.max(w.torso * 1.05, hipHalf * 0.96);
  ctx.fillStyle = colour;

  // Chest: one wide mass across both shoulders.
  // The chest ellipse is anchored below the neck join: centred any higher it
  // bulges above the shoulders and the body reads as a gourd.
  const chestTop = s.neck ? s.neck.end[1] : chest[1];
  const chestRadius = Math.abs(chest[1] - hip[1]) * 0.30 + w.arm * 1.05;
  ctx.beginPath();
  ctx.ellipse((shL[0] + shR[0]) / 2, Math.max(chest[1] + w.arm * 0.35, chestTop + chestRadius * 0.55),
    shoulderHalf, chestRadius, 0, 0, Math.PI * 2);
  ctx.fill();

  // Waist: a capsule so the body narrows without a pinch.
  limbFill(ctx, [chest[0], chest[1] + w.arm * 0.4], [hip[0], hip[1] - w.thigh * 0.2],
    waistHalf, hipHalf * 0.97, colour);

  // Seat.
  ctx.beginPath();
  ctx.ellipse(hip[0], hip[1] + w.thigh * 0.15, hipHalf, w.thigh * 0.95, 0, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * The cape: a hooked blade.
 *
 * Built by walking a curved spine and offsetting a width profile along it —
 * wide at the shoulder, swelling behind the hip, tapering to a point. Two
 * hand-placed bezier edges are all but impossible to keep from crossing, and a
 * crossing edge turns the cloak into a spike.
 */
export function capePath(ctx, s, w, { sway = 0, reach = 1, samples = 22 } = {}) {
  const shoulder = s.armR.origin;
  const hip = s.spine.origin;
  const legLength = s.thighL.length + s.shinL.length;
  const swing = clamp(sway, -0.55, 0.55);
  // Hung off the shoulder, not the neck: a cloak that starts at the collar
  // swallows the chin.
  const anchorX = shoulder[0] - w.torso * 1.1;
  const anchorY = shoulder[1] + w.torso * 0.55;
  const drop = legLength * SIL.capeReach * reach;
  const tipX = anchorX - w.torso * (2.0 + reach * 0.6) + swing * legLength * 0.34;
  const tipY = hip[1] + drop * (0.52 + reach * 0.16);
  const ctrlX = anchorX - w.torso * (2.2 + swing * 2);
  const ctrlY = anchorY + drop * 0.34;

  const spine = [];
  const widths = [];
  // Width is a fraction of the shoulder span, not of the page: a fixed number
  // made the same cloak a blade on a close-up and a blob in a wide shot.
  const maxWidth = Math.max(w.torso * 2.6, dist(s.armL.origin, s.armR.origin) * 0.86);
  for (let i = 0; i <= samples; i += 1) {
    const u = i / samples;
    const a = (1 - u) * (1 - u);
    const b = 2 * (1 - u) * u;
    const c = u * u;
    spine.push([
      a * anchorX + b * ctrlX + c * tipX,
      a * anchorY + b * ctrlY + c * tipY,
    ]);
    // A cloth hook: already wide where it leaves the shoulder, swelling just
    // behind the hip, then narrowing all the way to a point. Starting the profile
    // at zero made the collar a needle and the whole cape a blade.
    const profile = Math.sin(Math.PI * clamp(0.18 + u * 0.82, 0, 1)) ** 0.8 * (1 - u * 0.15) * (1 - u) ** 0.35;
    widths.push(Math.max(w.torso * 0.12, maxWidth * profile + w.torso * 0.10));
  }

  const left = [];
  const right = [];
  for (let i = 0; i <= samples; i += 1) {
    const prev = spine[Math.max(0, i - 1)];
    const next = spine[Math.min(samples, i + 1)];
    const n = perp(prev, next);
    const half = widths[i] / 2;
    left.push([spine[i][0] + n[0] * half, spine[i][1] + n[1] * half]);
    right.push([spine[i][0] - n[0] * half, spine[i][1] - n[1] * half]);
  }

  const trace = (side) => {
    const edge = side === 'left' ? left : right;
    ctx.beginPath();
    ctx.moveTo(edge[0][0], edge[0][1]);
    for (let i = 1; i <= samples; i += 1) ctx.lineTo(edge[i][0], edge[i][1]);
    for (let i = samples; i >= 0; i -= 1) {
      // The band is a sliver at the shoulder and widens toward the tip, so the
      // colour gathers at the point of the hook instead of flooding the cloth.
      const band = 0.80 + 0.06 * (1 - i / samples);
      const inner = left[i][0] + (right[i][0] - left[i][0]) * band;
      const innerY = left[i][1] + (right[i][1] - left[i][1]) * band;
      ctx.lineTo(inner, innerY);
    }
    ctx.closePath();
  };

  ctx.beginPath();
  ctx.moveTo(left[0][0], left[0][1]);
  for (let i = 1; i <= samples; i += 1) ctx.lineTo(left[i][0], left[i][1]);
  for (let i = samples; i >= 0; i -= 1) ctx.lineTo(right[i][0], right[i][1]);
  ctx.closePath();
  return { spine, widths, trace };
}

/** The face, cut out of the head in paper. */
export function faceCut(ctx, s, ink, opts, radius) {
  const head = s.head;
  const cx = head.end[0];
  const cy = head.end[1];
  const tilt = (s.head.world || 0) + Math.PI / 2;
  const expression = opts.expression || EXPRESSIONS.rest;
  const open = opts.viseme ? clamp(opts.viseme.open || 0, 0, 1) : 0;
  const blink = clamp(opts.blink || 0, 0, 1);
  const browRaise = clamp(opts.browRaise || 0, -1, 1);

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(tilt);
  ctx.fillStyle = ink.paper;
  ctx.strokeStyle = ink.paper;
  ctx.lineCap = 'round';

  const eyeX = radius * 0.30;
  const eyeY = -radius * 0.12;
  const eyeW = radius * 0.105;
  const eyeOpen = clamp(expression.eyeOpen * (1 - blink), 0.06, 1.4) * (1 - expression.squint * 0.55);
  const eyeH = Math.max(radius * 0.020, radius * 0.115 * eyeOpen);

  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.ellipse(side * eyeX, eyeY, eyeW, eyeH, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  // Brows carry the performance: at this size the eyes are nearly featureless,
  // so the angle above them says whether the line is a question or a fact.
  const browLift = radius * (0.30 + expression.brow * 0.10 - browRaise * 0.08);
  const browAngle = expression.browAngle * 0.55;
  ctx.lineWidth = radius * 0.055;
  for (const side of [-1, 1]) {
    const innerX = side * (eyeX - eyeW * 1.15);
    const outerX = side * (eyeX + eyeW * 1.45);
    // `browAngle` positive drops the inner ends (a hard look); negative lifts
    // them (a question). The sign flips per side because the inner end of each
    // brow is on the opposite side of the face.
    const innerY = -browLift - browAngle * radius * 0.30 * side;
    const outerY = -browLift + browAngle * radius * 0.14 * side;
    ctx.beginPath();
    ctx.moveTo(innerX, innerY);
    ctx.lineTo(outerX, outerY);
    ctx.stroke();
  }

  // Mouth: a lens whose height is the viseme and whose curve is the expression.
  const mouthW = radius * (0.34 + expression.wide * 0.22);
  const mouthY = radius * 0.34;
  const smile = expression.smile * radius * 0.16;
  const closed = radius * 0.028;
  const height = closed + open * radius * 0.20;
  ctx.beginPath();
  ctx.moveTo(-mouthW / 2, mouthY + smile * 0.35);
  ctx.quadraticCurveTo(0, mouthY + smile + height * 1.2, mouthW / 2, mouthY + smile * 0.35);
  ctx.quadraticCurveTo(0, mouthY + smile - height * 0.3, -mouthW / 2, mouthY + smile * 0.35);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/**
 * Draw the figure.
 *
 * `opts` accepts the same acting channels as `drawStick`: expression, viseme,
 * blink, browRaise, cape, capeSway, capeLift, legShorten, frame.
 */
export function drawSilhouette(ctx, solved, opts = {}) {
  const ink = resolveInk(opts);
  const s = solved;
  const scale = (s.hips && s.hips.scale) || 1;
  const w = {
    torso: s.spine.length * SIL.torso,
    neck: (s.neck ? s.neck.length : 60 * scale) * SIL.neck * 1.9,
    arm: s.armL.length * SIL.arm,
    forearm: s.forearmL.length * SIL.forearm,
    thigh: s.thighL.length * SIL.thigh,
    shin: s.shinL.length * SIL.shin,
    shoe: s.thighL.length * SIL.shoe,
  };

  // A swinging leg is drawn foreshortened: both segments are pulled toward the
  // hip by the same factor, which lifts the foot without bending the knee.
  const shorten = opts.legShorten || {};
  const squash = (side) => {
    const k = shorten[side];
    return typeof k === 'number' && k > 0 && k < 1 ? k : 1;
  };
  const pulled = (side) => {
    const k = squash(side);
    if (k === 1) return s;
    const anchor = s[side === 'L' ? 'thighL' : 'thighR'].origin;
    const move = (b) => (b ? {
      ...b,
      origin: [anchor[0] + (b.origin[0] - anchor[0]) * k, anchor[1] + (b.origin[1] - anchor[1]) * k],
      end: [anchor[0] + (b.end[0] - anchor[0]) * k, anchor[1] + (b.end[1] - anchor[1]) * k],
    } : b);
    return {
      ...s,
      [side === 'L' ? 'thighL' : 'thighR']: move(s[side === 'L' ? 'thighL' : 'thighR']),
      [side === 'L' ? 'shinL' : 'shinR']: move(s[side === 'L' ? 'shinL' : 'shinR']),
      [side === 'L' ? 'footL' : 'footR']: move(s[side === 'L' ? 'footL' : 'footR']),
    };
  };
  const nearView = pulled('L');
  const farView = pulled('R');

  ctx.save();
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  // Cloth behind everything.
  if (opts.cape !== false) {
    const reach = 1 + (opts.capeLift ? Math.abs(opts.capeLift) * 0.2 : 0);
    const sway = opts.capeSway || 0;
    const cloth = capePath(ctx, s, w, { sway, reach });
    ctx.fillStyle = ink.ink;
    ctx.fill();
    // Lining: a band along the inner edge of the cloth, not an outline of it.
    // Stroking the whole path in the accent drew two red lines around a black
    // crescent, which reads as a neon sign rather than a cloak. The band is a
    // second, narrower crescent on the body-facing side, clipped to the cloth so
    // the colour cannot spill onto the stage.
    ctx.save();
    capePath(ctx, s, w, { sway, reach });
    ctx.clip();
    cloth.trace('right');
    ctx.fillStyle = ink.accent;
    ctx.fill();
    ctx.restore();
  }

  // Far side first, as a lighter flat tone: transparency would let the cape show
  // through a limb, which reads as a hole rather than depth.
  const farInk = farTone(ink.ink, SIL.farLift);
  limbFill(ctx, farView.armR.origin, farView.armR.end, w.arm, w.forearm, farInk);
  limbFill(ctx, farView.forearmR.origin, farView.forearmR.end, w.forearm, w.forearm * 0.85, farInk);
  limbFill(ctx, farView.thighR.origin, farView.thighR.end, w.thigh, w.shin, farInk);
  limbFill(ctx, farView.shinR.origin, farView.shinR.end, w.shin, w.shoe * 0.8, farInk);
  limbFill(ctx, farView.footR.origin, farView.footR.end, w.shoe * 0.8, w.shoe * 1.05, farInk);

  // Torso and neck as one solid mass.
  torsoMass(ctx, s, w, ink.ink);
  limbFill(ctx, s.neck.origin, s.neck.end, w.neck * 0.8, w.neck, ink.ink);

  // Head: solid, joined to the neck, no outline.
  const head = s.head;
  const radius = head.length * SIL.head;
  ctx.fillStyle = ink.ink;
  ctx.beginPath();
  ctx.arc(head.end[0], head.end[1], radius, 0, Math.PI * 2);
  ctx.fill();

  // Near leg, then the near arm over the torso.
  limbFill(ctx, nearView.thighL.origin, nearView.thighL.end, w.thigh, w.shin, ink.ink);
  limbFill(ctx, nearView.shinL.origin, nearView.shinL.end, w.shin, w.shoe * 0.8, ink.ink);
  limbFill(ctx, nearView.footL.origin, nearView.footL.end, w.shoe * 0.8, w.shoe * 1.05, ink.ink);
  limbFill(ctx, s.armL.origin, s.armL.end, w.arm * 1.15, w.forearm * 0.95, ink.ink);
  limbFill(ctx, s.forearmL.origin, s.forearmL.end, w.forearm * 0.95, w.forearm * 0.72, ink.ink);

  faceCut(ctx, s, ink, opts, radius);
  ctx.restore();
  return { radius, widths: w };
}

export default drawSilhouette;
