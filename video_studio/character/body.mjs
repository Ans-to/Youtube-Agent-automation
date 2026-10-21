/**
 * Vector artwork for the rig.
 *
 * Everything is drawn from primitives — capsules, arcs, rounded polygons — so the
 * character carries no external asset and no licence. Thickness is derived from
 * the solved bone lengths rather than hard-coded, so re-proportioning the
 * skeleton in `rig.mjs` re-proportions the art automatically.
 */

import { VISEMES, clamp01, lerp } from './rig.mjs';

export const LOOK = {
  skin: '#F0BC92',
  skinShade: '#D2976B',
  skinLine: '#B87F57',
  hair: '#241B19',
  hairLight: '#3B2B27',
  shirt: '#E9EEF4',
  jacket: '#16323C',
  jacketShade: '#0F242C',
  trim: '#C8FF3D',
  pants: '#1A2230',
  pantsShade: '#121926',
  shoe: '#0B1017',
  eye: '#1A1F27',
  mouth: '#6E2A30',
  teeth: '#F7FAFD',
  blush: 'rgba(215,120,110,0.20)',
};

/** Thickness as a fraction of the bone that carries it. */
const R = {
  upperArm: [0.205, 0.170],
  forearm: [0.170, 0.132],
  thigh: [0.155, 0.124],
  shin: [0.126, 0.098],
  neck: 0.40,
};

function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

/** Tapered capsule from p0 (radius w0) to p1 (radius w1). */
export function taperedLimb(ctx, p0, p1, w0, w1, fill) {
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  ctx.beginPath();
  ctx.moveTo(p0[0] + nx * w0, p0[1] + ny * w0);
  ctx.lineTo(p1[0] + nx * w1, p1[1] + ny * w1);
  ctx.lineTo(p1[0] - nx * w1, p1[1] - ny * w1);
  ctx.lineTo(p0[0] - nx * w0, p0[1] - ny * w0);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(p0[0], p0[1], w0, 0, Math.PI * 2);
  ctx.arc(p1[0], p1[1], w1, 0, Math.PI * 2);
  ctx.fill();
}

function shadowEdge(ctx, p0, p1, w, fill) {
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const off = w * 0.55;
  taperedLimb(
    ctx,
    [p0[0] + nx * off, p0[1] + ny * off],
    [p1[0] + nx * off * 0.65, p1[1] + ny * off * 0.65],
    w * 0.26, w * 0.18, fill,
  );
}

/** Shoulder cap: an ellipse over the joint so the arm grows out of the torso. */
function drawDeltoid(ctx, arm, fill, width) {
  const angle = Math.atan2(arm.end[1] - arm.origin[1], arm.end[0] - arm.origin[0]);
  ctx.save();
  ctx.translate(arm.origin[0], arm.origin[1]);
  ctx.rotate(angle);
  ctx.beginPath();
  ctx.ellipse(0, 0, width * 1.02, width * 1.10, 0, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.restore();
}

// ------------------------------------------------------------------- pieces
function drawFarArm(ctx, s, look) {
  const w0 = s.armR.length * R.upperArm[0];
  const w1 = s.armR.length * R.upperArm[1];
  const f0 = s.forearmR.length * R.forearm[0];
  const f1 = s.forearmR.length * R.forearm[1];
  drawDeltoid(ctx, s.armR, look.jacketShade, w0);
  taperedLimb(ctx, s.armR.origin, s.armR.end, w0, w1, look.jacketShade);
  taperedLimb(ctx, s.forearmR.origin, s.forearmR.end, f0, f1, look.jacketShade);
  taperedLimb(ctx, s.forearmR.end, s.handR.end, f1 * 0.95, f1 * 0.80, look.skinShade);
}

function drawNearArm(ctx, s, look) {
  const w0 = s.armL.length * R.upperArm[0];
  const w1 = s.armL.length * R.upperArm[1];
  const f0 = s.forearmL.length * R.forearm[0];
  const f1 = s.forearmL.length * R.forearm[1];
  drawDeltoid(ctx, s.armL, look.jacket, w0);
  taperedLimb(ctx, s.armL.origin, s.armL.end, w0, w1, look.jacket);
  shadowEdge(ctx, s.armL.origin, s.armL.end, w0, 'rgba(0,0,0,0.20)');
  taperedLimb(ctx, s.forearmL.origin, s.forearmL.end, f0, f1, look.jacket);

  // cuff: a short band of accent at the wrist
  const wrist = s.handL.origin;
  const elbow = s.forearmL.origin;
  const ux = wrist[0] - elbow[0];
  const uy = wrist[1] - elbow[1];
  const ulen = Math.hypot(ux, uy) || 1;
  const band = f1 * 0.7;
  taperedLimb(
    ctx,
    [wrist[0] - (ux / ulen) * band, wrist[1] - (uy / ulen) * band],
    [wrist[0] - (ux / ulen) * band * 0.15, wrist[1] - (uy / ulen) * band * 0.15],
    f1 * 1.06, f1 * 1.02, look.trim,
  );
  taperedLimb(ctx, s.handL.origin, s.handL.end, f1 * 0.92, f1 * 0.78, look.skin);
  drawHand(ctx, s.handL, look, f1);
}

function drawHand(ctx, hand, look, size) {
  const angle = Math.atan2(hand.end[1] - hand.origin[1], hand.end[0] - hand.origin[0]);
  ctx.save();
  ctx.translate(hand.end[0], hand.end[1]);
  ctx.rotate(angle);
  ctx.beginPath();
  ctx.ellipse(size * 0.35, 0, size * 1.15, size * 0.92, 0, 0, Math.PI * 2);
  ctx.fillStyle = look.skin;
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(-size * 0.15, size * 0.62, size * 0.52, size * 0.40, -0.5, 0, Math.PI * 2);
  ctx.fillStyle = look.skinShade;
  ctx.fill();
  ctx.restore();
}

function drawShoe(ctx, foot, fill, alpha = 1) {
  const len = foot.length * 1.35;
  const height = foot.length * 0.40;
  const angle = Math.atan2(foot.end[1] - foot.origin[1], foot.end[0] - foot.origin[0]);
  ctx.save();
  ctx.globalAlpha *= alpha;
  ctx.translate(foot.origin[0], foot.origin[1]);
  ctx.rotate(angle);
  roundRect(ctx, -len * 0.12, -height / 2, len, height, height / 2);
  ctx.fillStyle = fill;
  ctx.fill();
  roundRect(ctx, -len * 0.12, height * 0.10, len, height * 0.26, height * 0.13);
  ctx.fillStyle = 'rgba(255,255,255,0.10)';
  ctx.fill();
  ctx.restore();
}

function drawFarLeg(ctx, s, look) {
  taperedLimb(ctx, s.thighR.origin, s.thighR.end,
    s.thighR.length * R.thigh[0], s.thighR.length * R.thigh[1], look.pantsShade);
  taperedLimb(ctx, s.shinR.origin, s.shinR.end,
    s.shinR.length * R.shin[0], s.shinR.length * R.shin[1], look.pantsShade);
  drawShoe(ctx, s.footR, look.shoe, 0.85);
}

function drawNearLeg(ctx, s, look) {
  const t0 = s.thighL.length * R.thigh[0];
  taperedLimb(ctx, s.thighL.origin, s.thighL.end, t0, s.thighL.length * R.thigh[1], look.pants);
  shadowEdge(ctx, s.thighL.origin, s.thighL.end, t0 * 0.9, 'rgba(0,0,0,0.28)');
  taperedLimb(ctx, s.shinL.origin, s.shinL.end,
    s.shinL.length * R.shin[0], s.shinL.length * R.shin[1], look.pants);
  drawShoe(ctx, s.footL, look.shoe);
}

function drawTorso(ctx, s, look, breathe = 1) {
  const hip = s.hips.origin;
  const chestTop = s.chest.end;
  const widthHip = s.chest.length * 0.34 * breathe;
  const widthChest = s.chest.length * 0.44 * breathe;
  const shoulderY = chestTop[1] + s.chest.length * 0.14;

  ctx.beginPath();
  ctx.moveTo(hip[0] - widthHip, hip[1] + 34);
  ctx.quadraticCurveTo(hip[0] - widthChest * 0.98, shoulderY + s.chest.length * 0.22,
    hip[0] - widthChest, shoulderY);
  ctx.quadraticCurveTo(hip[0] - widthChest * 0.62, chestTop[1] - s.chest.length * 0.05,
    hip[0], chestTop[1] - s.chest.length * 0.03);
  ctx.quadraticCurveTo(hip[0] + widthChest * 0.62, chestTop[1] - s.chest.length * 0.05,
    hip[0] + widthChest, shoulderY);
  ctx.quadraticCurveTo(hip[0] + widthChest * 0.98, shoulderY + s.chest.length * 0.22,
    hip[0] + widthHip, hip[1] + 34);
  ctx.quadraticCurveTo(hip[0], hip[1] + 74, hip[0] - widthHip, hip[1] + 34);
  ctx.closePath();
  ctx.fillStyle = look.jacket;
  ctx.fill();

  // open jacket: shirt panel down the middle
  const nx = widthChest * 0.30;
  ctx.beginPath();
  ctx.moveTo(hip[0] - nx, chestTop[1] + s.chest.length * 0.02);
  ctx.quadraticCurveTo(hip[0], chestTop[1] + s.chest.length * 0.12, hip[0] + nx, chestTop[1] + s.chest.length * 0.02);
  ctx.lineTo(hip[0] + widthHip * 0.58, hip[1] + 34);
  ctx.quadraticCurveTo(hip[0], hip[1] + 56, hip[0] - widthHip * 0.58, hip[1] + 34);
  ctx.closePath();
  ctx.fillStyle = look.shirt;
  ctx.fill();

  // collar
  const cw = widthChest * 0.30;
  ctx.beginPath();
  ctx.moveTo(hip[0] - cw, chestTop[1] + 6);
  ctx.lineTo(hip[0], chestTop[1] + s.chest.length * 0.15);
  ctx.lineTo(hip[0] + cw, chestTop[1] + 6);
  ctx.lineTo(hip[0] + cw * 0.6, chestTop[1] - 4);
  ctx.lineTo(hip[0], chestTop[1] + s.chest.length * 0.10);
  ctx.lineTo(hip[0] - cw * 0.6, chestTop[1] - 4);
  ctx.closePath();
  ctx.fillStyle = look.jacketShade;
  ctx.fill();

  // zip pull in the accent colour
  ctx.beginPath();
  ctx.ellipse(hip[0], hip[1] - s.chest.length * 0.24, widthHip * 0.055, widthHip * 0.15, 0, 0, Math.PI * 2);
  ctx.fillStyle = look.trim;
  ctx.fill();
}

function drawHead(ctx, s, look, blink, viseme, browRaise) {
  const head = s.head;
  const cx = head.origin[0] + Math.cos(head.world) * 112 * (head.scale || 1);
  const cy = head.origin[1] + Math.sin(head.world) * 112 * (head.scale || 1);
  const rot = head.world + Math.PI / 2;
  // head art is authored against a 272-tall face; scale it with the bone
  const k = head.length / 240;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(rot);
  ctx.scale(k, k);

  // neck
  roundRect(ctx, -54, 84, 108, 130, 40);
  ctx.fillStyle = look.skinShade;
  ctx.fill();

  // ears
  ctx.beginPath();
  ctx.ellipse(-112, 12, 20, 30, 0.1, 0, Math.PI * 2);
  ctx.ellipse(112, 12, 20, 30, -0.1, 0, Math.PI * 2);
  ctx.fillStyle = look.skinShade;
  ctx.fill();

  // face
  ctx.beginPath();
  ctx.moveTo(-98, -66);
  ctx.quadraticCurveTo(-118, 38, -82, 98);
  ctx.quadraticCurveTo(-44, 142, 0, 144);
  ctx.quadraticCurveTo(44, 142, 82, 98);
  ctx.quadraticCurveTo(118, 38, 98, -66);
  ctx.quadraticCurveTo(80, -146, 0, -146);
  ctx.quadraticCurveTo(-80, -146, -98, -66);
  ctx.closePath();
  ctx.fillStyle = look.skin;
  ctx.fill();

  // hair: a cap that follows the skull, with a swept fringe
  ctx.beginPath();
  ctx.moveTo(-100, -20);
  ctx.quadraticCurveTo(-114, -138, -6, -156);
  ctx.quadraticCurveTo(108, -166, 102, -28);
  ctx.quadraticCurveTo(98, -70, 66, -86);
  ctx.quadraticCurveTo(44, -54, 6, -78);
  ctx.quadraticCurveTo(-32, -98, -60, -70);
  ctx.quadraticCurveTo(-86, -50, -100, -20);
  ctx.closePath();
  ctx.fillStyle = look.hair;
  ctx.fill();
  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(side * 98, -36);
    ctx.quadraticCurveTo(side * 106, 6, side * 94, 28);
    ctx.quadraticCurveTo(side * 86, 0, side * 90, -32);
    ctx.closePath();
    ctx.fillStyle = look.hair;
    ctx.fill();
  }
  ctx.beginPath();
  ctx.moveTo(-56, -124);
  ctx.quadraticCurveTo(0, -146, 58, -120);
  ctx.quadraticCurveTo(2, -128, -56, -124);
  ctx.fillStyle = look.hairLight;
  ctx.fill();

  // brows
  const raise = browRaise || 0;
  for (const side of [-1, 1]) {
    ctx.save();
    ctx.translate(side * 48, -56 - raise * 14);
    ctx.rotate(side * (0.10 + raise * 0.12));
    roundRect(ctx, -22, -5, 44, 10, 5);
    ctx.fillStyle = look.hair;
    ctx.fill();
    ctx.restore();
  }

  // eyes
  const openness = 1 - clamp01(blink);
  for (const side of [-1, 1]) {
    const ex = side * 48;
    const ey = 4;
    const halfW = 28;
    const halfH = 20 * openness + 1.5;
    ctx.beginPath();
    ctx.moveTo(ex - halfW, ey);
    ctx.quadraticCurveTo(ex, ey - halfH * 2.1, ex + halfW, ey);
    ctx.quadraticCurveTo(ex, ey + halfH * 1.7, ex - halfW, ey);
    ctx.closePath();
    ctx.fillStyle = '#FCFEFF';
    ctx.fill();
    if (openness > 0.10) {
      ctx.save();
      ctx.clip();
      ctx.beginPath();
      ctx.arc(ex + side * 3, ey + 2, 13 * Math.min(1, openness * 1.6), 0, Math.PI * 2);
      ctx.fillStyle = look.eye;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(ex + side * 3 - 5, ey - 1, 4.8, 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.fill();
      ctx.restore();
    }
    ctx.beginPath();
    ctx.moveTo(ex - halfW, ey);
    ctx.quadraticCurveTo(ex, ey - halfH * 2.1, ex + halfW, ey);
    ctx.strokeStyle = look.hair;
    ctx.lineWidth = 6;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  // nose
  ctx.beginPath();
  ctx.moveTo(3, 24);
  ctx.quadraticCurveTo(12, 54, -3, 60);
  ctx.strokeStyle = look.skinLine;
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';
  ctx.stroke();
  ctx.beginPath();
  ctx.ellipse(0, 62, 12, 6, 0, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(184,127,87,0.35)';
  ctx.fill();

  // blush
  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.ellipse(side * 72, 50, 26, 15, 0, 0, Math.PI * 2);
    ctx.fillStyle = look.blush;
    ctx.fill();
  }

  drawMouth(ctx, 0, 84, viseme, look);

  // jaw shading gives the head a light direction
  ctx.beginPath();
  ctx.moveTo(-92, 22);
  ctx.quadraticCurveTo(-76, 108, 0, 142);
  ctx.quadraticCurveTo(-34, 104, -62, 8);
  ctx.closePath();
  ctx.fillStyle = 'rgba(184,127,87,0.14)';
  ctx.fill();

  ctx.restore();
}

/** Mouth shaped by the current viseme. */
export function drawMouth(ctx, cx, cy, viseme, look) {
  const v = viseme || VISEMES.REST;
  const width = lerp(50, 84, v.wide) * lerp(1, 0.62, v.round);
  const height = lerp(5, 60, v.open);
  const radius = lerp(6, width / 2, v.round);

  if (v.press > 0.6) {
    ctx.beginPath();
    ctx.moveTo(cx - width * 0.44, cy);
    ctx.quadraticCurveTo(cx, cy + 7, cx + width * 0.44, cy);
    ctx.strokeStyle = look.skinLine;
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.stroke();
    return;
  }

  ctx.beginPath();
  if (radius >= height) {
    ctx.ellipse(cx, cy, radius, Math.max(height, radius * 0.5), 0, 0, Math.PI * 2);
  } else {
    ctx.moveTo(cx - width / 2, cy);
    ctx.quadraticCurveTo(cx, cy - height * 0.55, cx + width / 2, cy);
    ctx.quadraticCurveTo(cx, cy + height, cx - width / 2, cy);
    ctx.closePath();
  }
  ctx.fillStyle = look.mouth;
  ctx.fill();

  if (v.teeth > 0.15 && height > 8) {
    const tw = width * 0.84;
    const th = Math.min(height * 0.40, 16) * v.teeth;
    roundRect(ctx, cx - tw / 2, cy - height * 0.28, tw, th, 4);
    ctx.fillStyle = look.teeth;
    ctx.fill();
  }
  ctx.beginPath();
  ctx.moveTo(cx - width / 2, cy + 2);
  ctx.quadraticCurveTo(cx, cy + height + 7, cx + width / 2, cy + 2);
  ctx.strokeStyle = 'rgba(120,60,60,0.35)';
  ctx.lineWidth = 4;
  ctx.stroke();
}

/**
 * Draw the whole character.
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} s solved skeleton
 * @param {object} opts {look, viseme, blink, browRaise, breathe}
 */
export function drawCharacter(ctx, s, opts = {}) {
  const look = opts.look || LOOK;
  const viseme = opts.viseme || VISEMES.REST;
  const breathe = opts.breathe === undefined ? 1 : opts.breathe;

  ctx.save();
  ctx.lineJoin = 'round';
  drawFarArm(ctx, s, look);
  drawFarLeg(ctx, s, look);
  drawTorso(ctx, s, look, breathe);
  drawNearLeg(ctx, s, look);
  drawHead(ctx, s, look, opts.blink || 0, viseme, opts.browRaise || 0);
  drawNearArm(ctx, s, look);
  ctx.restore();
}
