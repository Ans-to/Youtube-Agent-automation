/**
 * Ink-and-paper character artwork.
 *
 * A second drawing style for the same rig. Nothing here changes the skeleton,
 * the timing or the lip sync: `drawSketchCharacter` takes the same solved
 * skeleton and the same viseme the old painter took, and draws it as a bold
 * marker doodle — white fills, wobbly black outlines, an oversized head, a
 * spiky fringe, big eyes, a grin, stick-thin limbs and a single orange accent.
 *
 * Two rules keep it looking hand-drawn rather than vector-perfect:
 *
 *  - every outline is built from points that are nudged by a *deterministic*
 *    hash, so the same frame always draws the same wobble (a render is
 *    reproducible frame by frame, and re-renders match), and
 *  - outlines are stroked twice at slightly different offsets, the way a marker
 *    overlaps its own first pass.
 *
 * Limbs use a cheap trick that avoids seams at the elbows and knees: stroke the
 * whole shoulder-to-wrist chain wide in ink, then again narrower in paper. The
 * coloured stroke covers the middle of the ink stroke and leaves a clean
 * outline around the union, so no line cuts across a joint.
 */

import { VISEMES, clamp01, lerp } from './rig.mjs';

export const SKETCH = {
  style: 'sketch',
  ink: '#151416',
  inkSoft: 'rgba(21,20,22,0.42)',
  paper: '#FFFFFF',
  paperShade: '#F1EFEA',
  skin: '#FFFFFF',
  cheek: 'rgba(240,150,130,0.22)',
  tie: '#F2960C',
  tieShade: '#D07C00',
  shoe: '#151416',
  mouth: '#1A1214',
  tongue: '#E4695E',
  teeth: '#FFFFFF',
  trim: '#C8FF3D',
};

const INK = 9.5;          // silhouette line weight, in rig units
const INK_DETAIL = 7.0;   // face details

/** Deterministic pseudo-random in [-1, 1). Same input, same wobble, forever. */
function noise(seed) {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return (x - Math.floor(x)) * 2 - 1;
}

/** Push a point off its true position by a little, reproducibly. */
function wobble(point, seed, amount) {
  return [point[0] + noise(seed) * amount, point[1] + noise(seed + 0.517) * amount];
}

/** A circle as a closed polyline, so it can be wobbled like everything else. */
function ring(cx, cy, rx, ry, steps = 38) {
  const points = [];
  for (let i = 0; i < steps; i += 1) {
    const a = (i / steps) * Math.PI * 2;
    points.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return points;
}

function tracePath(ctx, points, seed, amount, closed = true, smooth = false) {
  const placed = points.map((point, index) => (
    amount ? wobble(point, seed + index * 1.7, amount) : point
  ));
  ctx.beginPath();
  if (smooth && placed.length > 3) {
    // Quadratic midpoint smoothing: each control point pulls the curve through
    // the halfway mark between its neighbours, which rounds a polygon into a
    // drawn line without the cost of a full spline.
    const n = placed.length;
    const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const start = closed ? mid(placed[n - 1], placed[0]) : placed[0];
    ctx.moveTo(start[0], start[1]);
    const last = closed ? n : n - 1;
    for (let i = 0; i < last; i += 1) {
      const current = placed[i];
      const next = placed[(i + 1) % n];
      const end = mid(current, next);
      ctx.quadraticCurveTo(current[0], current[1], end[0], end[1]);
    }
    if (closed) ctx.closePath();
    else ctx.lineTo(placed[n - 1][0], placed[n - 1][1]);
    return;
  }
  placed.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (closed) ctx.closePath();
}

/** Fill a shape with paper and give it an inked, twice-stroked outline. */
function inkShape(ctx, points, seed, opts = {}) {
  const fill = opts.fill === undefined ? SKETCH.paper : opts.fill;
  const width = opts.width === undefined ? INK : opts.width;
  const amount = opts.wobble === undefined ? 1.5 : opts.wobble;
  const smooth = opts.smooth !== false;

  tracePath(ctx, points, seed, amount, true, smooth);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.strokeStyle = opts.stroke || SKETCH.ink;
  ctx.lineWidth = width;
  ctx.stroke();
  if (opts.double !== false) {
    // the second pass is the marker overlapping its own first line
    tracePath(ctx, points, seed + 91.3, amount + 0.6, true, smooth);
    ctx.lineWidth = width * 0.55;
    ctx.strokeStyle = SKETCH.inkSoft;
    ctx.stroke();
  }
}

/**
 * A limb drawn as one continuous outline.
 *
 * Stroking the chain twice — wide in ink, then narrow in paper — leaves a
 * single clean border around the union of the segments, so an elbow or knee
 * never gets a line drawn across it.
 */
function inkLimb(ctx, points, radius, seed, fill = SKETCH.paper) {
  const jittered = points.map((point, index) => wobble(point, seed + index * 3.1, 1.2));
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  jittered.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.strokeStyle = SKETCH.ink;
  ctx.lineWidth = radius * 2 + INK * 2;
  ctx.stroke();
  ctx.strokeStyle = fill;
  ctx.lineWidth = radius * 2;
  ctx.stroke();
}

function inkBlob(ctx, cx, cy, rx, ry, seed, fill = SKETCH.paper) {
  inkShape(ctx, ring(cx, cy, rx, ry), seed, { fill, wobble: 1.1 });
}

// ------------------------------------------------------------------ skeleton
function segmentEnd(bone) {
  return bone && bone.end ? bone.end : [0, 0];
}

// ---------------------------------------------------------------------- limbs
function drawFarArm(ctx, s) {
  inkLimb(ctx, [s.armR.origin, segmentEnd(s.armR), segmentEnd(s.forearmR), segmentEnd(s.handR)],
    17, 3.4);
  drawMitten(ctx, s.handR, 30, 7.7);
}

function drawNearArm(ctx, s) {
  inkLimb(ctx, [s.armL.origin, segmentEnd(s.armL), segmentEnd(s.forearmL), segmentEnd(s.handL)],
    18, 5.9);
  drawMitten(ctx, s.handL, 32, 8.3);
}

function drawMitten(ctx, hand, radius, seed) {
  const tip = hand.end;
  inkShape(ctx, ring(tip[0], tip[1], radius, radius * 0.94, 22), seed, { wobble: 1.0 });
  // thumb: a small bump so the hand is not a bare circle
  const angle = Math.atan2(tip[1] - hand.origin[1], tip[0] - hand.origin[0]);
  const tx = tip[0] + Math.cos(angle + 1.9) * radius * 0.85;
  const ty = tip[1] + Math.sin(angle + 1.9) * radius * 0.85;
  inkShape(ctx, ring(tx, ty, radius * 0.38, radius * 0.5, 14), seed + 2.2, { wobble: 0.7 });
}

function drawLegs(ctx, s) {
  // far leg first, so the near one inks over it
  inkLimb(ctx, [s.thighR.origin, segmentEnd(s.thighR), segmentEnd(s.shinR), segmentEnd(s.footR)],
    23, 11.1);
  inkShoe(ctx, s.footR, 12.5);
  inkLimb(ctx, [s.thighL.origin, segmentEnd(s.thighL), segmentEnd(s.shinL), segmentEnd(s.footL)],
    24, 13.7);
  inkShoe(ctx, s.footL, 14.9);
}

function inkShoe(ctx, foot, seed) {
  const length = foot.length * 1.6;
  const height = foot.length * 0.62;
  const angle = Math.atan2(foot.end[1] - foot.origin[1], foot.end[0] - foot.origin[0]);
  ctx.save();
  // Centre the shoe between the ankle and the toe. Anchoring it on the toe
  // tip made a long white slab sticking out in front of the leg.
  ctx.translate((foot.origin[0] + foot.end[0]) / 2, (foot.origin[1] + foot.end[1]) / 2);
  ctx.rotate(angle);
  const outline = [];
  for (let i = 0; i <= 14; i += 1) {
    const a = (i / 14) * Math.PI * 2;
    outline.push([Math.cos(a) * length * 0.52, Math.sin(a) * height * 0.5]);
  }
  // Paper with an ink edge, like everything else; a filled black shoe would
  // disappear into the dark studio floor.
  inkShape(ctx, outline, seed, { fill: SKETCH.paper, wobble: 1.1, double: false });
  inkShape(ctx, [
    [-length * 0.50, height * 0.16],
    [length * 0.50, height * 0.16],
    [length * 0.50, height * 0.48],
    [-length * 0.50, height * 0.48],
  ], seed + 2.1, { fill: SKETCH.shoe, wobble: 0.8, double: false, smooth: false });
  ctx.restore();
}

// ---------------------------------------------------------------------- torso
function drawTorso(ctx, s) {
  const hip = s.hips.origin;
  const neck = s.chest.end;
  const lean = s.spine.world + Math.PI / 2;
  const cos = Math.cos(-lean);
  const sin = Math.sin(-lean);
  const toLocal = (point) => [
    (point[0] - hip[0]) * cos - (point[1] - hip[1]) * sin,
    (point[0] - hip[0]) * sin + (point[1] - hip[1]) * cos,
  ];
  const neckLocal = toLocal(neck);
  const shoulderL = toLocal(s.shoulderL.end);
  const shoulderR = toLocal(s.shoulderR.end);
  const bodyHeight = Math.max(120, Math.abs(neckLocal[1]));
  const chest = Math.max(Math.abs(shoulderL[0]), Math.abs(shoulderR[0])) * 1.02;
  const hipWidth = chest * 0.80;

  ctx.save();
  ctx.translate(hip[0], hip[1]);
  ctx.rotate(lean);

  // one white shirt body: square shoulders, a waist, and a seat. Drawn as a
  // smoothed outline so the silhouette reads as a single pen line.
  const body = [];
  const top = -bodyHeight;
  body.push([-chest * 0.34, top * 1.04]);
  body.push([-chest * 0.80, top * 0.98]);   // shoulder slope
  body.push([-chest * 1.00, top * 0.76]);
  body.push([-hipWidth * 1.02, top * 0.26]);
  body.push([-hipWidth, 42]);
  body.push([0, 58]);
  body.push([hipWidth, 42]);
  body.push([hipWidth * 1.02, top * 0.26]);
  body.push([chest * 1.00, top * 0.76]);
  body.push([chest * 0.80, top * 0.98]);
  body.push([chest * 0.34, top * 1.04]);
  inkShape(ctx, body, 17.3, { wobble: 1.4, smooth: true });

  // collar: a V opening, drawn as two short flicks so the shirt reads as a
  // shirt and the tie has somewhere to come out of
  for (const side of [-1, 1]) {
    tracePath(ctx, [
      [side * chest * 0.36, top * 1.00],
      [side * chest * 0.16, top * 0.88],
      [0, top * 0.81],
    ], 21.5 + side, 0.8, false, false);
    ctx.strokeStyle = SKETCH.ink;
    ctx.lineWidth = INK_DETAIL;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  }

  drawTie(ctx, chest, bodyHeight);

  ctx.restore();
}

/** The one colour accent on the figure, and the thing the eye lands on. */
function drawTie(ctx, chest, bodyHeight) {
  const top = -bodyHeight;
  const knotY = top * 0.80;
  const knot = chest * 0.15;
  inkShape(ctx, [
    [-knot, knotY], [knot, knotY],
    [knot * 0.78, knotY + knot * 1.45], [-knot * 0.78, knotY + knot * 1.45],
  ], 31.1, { fill: SKETCH.tieShade, wobble: 0.5, smooth: false });

  const blade = chest * 0.26;
  const length = bodyHeight * 0.40;
  inkShape(ctx, [
    [-blade * 0.72, knotY + knot * 1.3],
    [blade * 0.72, knotY + knot * 1.3],
    [blade * 1.05, knotY + length * 0.62],
    [0, knotY + length],
    [-blade * 1.05, knotY + length * 0.62],
  ], 33.9, { fill: SKETCH.tie, wobble: 0.7, double: false, smooth: false });
}

// ----------------------------------------------------------------------- head
function drawHead(ctx, s, viseme, blink, browRaise) {
  const head = s.head;
  const k = (head.length / 240) * 1.16;
  // 160 rather than 118: with the bigger head art, centring it lower buried the
  // chin in the collar and the figure read as a head stuck on a nightgown.
  const cx = head.origin[0] + Math.cos(head.world) * 160 * k;
  const cy = head.origin[1] + Math.sin(head.world) * 160 * k;
  const rot = head.world + Math.PI / 2;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(rot);
  ctx.scale(k, k);

  // neck: short and thick, so the head sits on the shoulders
  inkLimb(ctx, [[-4, 168], [0, 208], [4, 246]], 24, 41.3);

  // ears
  for (const side of [-1, 1]) {
    inkShape(ctx, ring(side * 165, 8, 26, 32, 18), 43.1 + side, { wobble: 1.0 });
  }

  // face
  const face = ring(0, 0, 168, 176, 44);
  inkShape(ctx, face, 47.9, { wobble: 1.6 });

  drawHair(ctx);
  drawEyes(ctx, blink, browRaise);
  drawNose(ctx);
  drawGrin(ctx, 0, 96, viseme);

  ctx.restore();
}

function drawHair(ctx) {
  // One hair mass with a swept fringe, not a ring of separate spikes: the
  // reference's hair reads as a single shape whose top edge happens to be
  // jagged, sitting on the same face outline as the jaw.
  const sweep = [
    [-168, -26],                       // left temple
    [-152, -96], [-118, -150],         // up the left side
    [-96, -196], [-58, -150],          // first spike
    [-26, -214], [10, -156],           // second, taller
    [58, -204], [86, -146],            // third
    [126, -168], [150, -104],          // fourth, smaller
    [168, -34],                        // right temple
    [128, -88], [86, -104],            // fringe: a ragged hairline
    [42, -88], [-2, -108],
    [-46, -90], [-96, -104],
    [-136, -84],
  ];
  inkShape(ctx, sweep, 51.7, { wobble: 1.3, smooth: true });
}

function drawEyes(ctx, blink, browRaise) {
  const openness = 1 - clamp01(blink) * 0.94;
  for (const side of [-1, 1]) {
    const ex = side * 66;
    const ey = -2;
    const rx = 45;
    const ry = 53 * openness;

    if (openness < 0.16) {
      // a shut eye is a single happy curve, not a squashed ellipse
      tracePath(ctx, [[ex - rx, ey], [ex, ey + 14], [ex + rx, ey]], 71.1 + side, 0.8, false, true);
      ctx.strokeStyle = SKETCH.ink;
      ctx.lineWidth = INK + 2;
      ctx.lineCap = 'round';
      ctx.stroke();
    } else {
      inkShape(ctx, ring(ex, ey, rx, ry, 30), 73.7 + side, { wobble: 1.2 });
      // pupil sits slightly high and inward, which is what makes a doodle read
      // as looking at the viewer rather than through them
      inkShape(ctx, ring(ex + side * 4, ey + 8, 19, 19 * Math.min(1, openness + 0.2), 20),
        77.9 + side, { fill: SKETCH.ink, stroke: SKETCH.ink, wobble: 0.9, double: false });
      inkShape(ctx, ring(ex + side * 4 + 6, ey, 5.5, 5.5, 10), 79.3 + side,
        { fill: SKETCH.teeth, stroke: null, wobble: 0.4, double: false });
    }

    // brow: a bold arc, lifted by the acting layer
    const raise = clamp01(browRaise || 0) * 16;
    const by = ey - ry - 20 - raise;
    tracePath(ctx, [
      [ex - 38, by + 9 - side * 2],
      [ex, by - 7],
      [ex + 38, by + 3 + side * 2],
    ], 83.1 + side, 1.0, false, true);
    ctx.strokeStyle = SKETCH.ink;
    ctx.lineWidth = INK + 1.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  }
}

function drawNose(ctx) {
  tracePath(ctx, [[10, -6], [-4, 40], [26, 44]], 87.7, 0.9, false);
  ctx.strokeStyle = SKETCH.ink;
  ctx.lineWidth = INK_DETAIL;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();
}

/**
 * The grin, driven by the same viseme channels as the old mouth: `open` drops
 * the jaw, `wide`/`round` shape it, `press` closes it, `teeth` shows the band.
 */
function drawGrin(ctx, cx, cy, viseme) {
  const v = viseme || VISEMES.REST;
  const open = clamp01(v.open === undefined ? 0.05 : v.open);
  const wide = clamp01(v.wide === undefined ? 0.3 : v.wide);
  const round = clamp01(v.round === undefined ? 0.1 : v.round);
  const press = clamp01(v.press === undefined ? 0 : v.press);
  const teeth = clamp01(v.teeth === undefined ? 0 : v.teeth);

  const halfWidth = lerp(96, 168, wide) * lerp(1, 0.74, round);
  const depth = lerp(6, 116, Math.pow(open, 0.85));

  if (press > 0.55 && open < 0.12) {
    // lips together: one firm line with the corners turned down a touch
    tracePath(ctx, [
      [cx - halfWidth * 0.62, cy - 2],
      [cx, cy + 6],
      [cx + halfWidth * 0.62, cy - 2],
    ], 91.3, 1.1, false);
    ctx.strokeStyle = SKETCH.ink;
    ctx.lineWidth = INK + 2;
    ctx.lineCap = 'round';
    ctx.stroke();
    return;
  }

  // mouth outline: a smile that opens into a lens as the jaw drops
  const shape = [
    [cx - halfWidth, cy - 10],
    [cx - halfWidth * 0.42, cy - 6],
    [cx, cy - 2],
    [cx + halfWidth * 0.42, cy - 6],
    [cx + halfWidth, cy - 10],
    [cx + halfWidth * 0.62, cy + depth * 0.72],
    [cx, cy + depth],
    [cx - halfWidth * 0.62, cy + depth * 0.72],
  ];
  inkShape(ctx, shape, 93.7, { fill: SKETCH.mouth, wobble: 1.0, double: false });

  if (open > 0.2) {
    // teeth band across the top of the opening — the reference's grin
    const band = Math.min(depth * 0.42, 30);
    ctx.save();
    tracePath(ctx, shape, 93.7, 0, true);
    ctx.clip();
    const tw = halfWidth * 1.6;
    inkShape(ctx, [
      [cx - tw / 2, cy - 14],
      [cx + tw / 2, cy - 14],
      [cx + tw / 2, cy - 14 + band],
      [cx - tw / 2, cy - 14 + band],
    ], 95.1, { fill: SKETCH.teeth, stroke: null, wobble: 0, double: false });
    if (teeth > 0.3 && open > 0.45) {
      // tongue, only on the wide-open shapes
      inkShape(ctx, ring(cx, cy + depth * 0.62, halfWidth * 0.42, depth * 0.3, 18),
        97.3, { fill: SKETCH.tongue, stroke: null, wobble: 0.8, double: false });
    }
    ctx.restore();
  }

  // smile corners: two short flicks that turn the lens into a grin
  for (const side of [-1, 1]) {
    tracePath(ctx, [
      [cx + side * halfWidth * 0.99, cy - 10],
      [cx + side * (halfWidth + 16), cy - 26],
    ], 99.1 + side, 0.8, false);
    ctx.strokeStyle = SKETCH.ink;
    ctx.lineWidth = INK_DETAIL;
    ctx.lineCap = 'round';
    ctx.stroke();
  }
}

// ------------------------------------------------------------------- assembly
export function drawSketchCharacter(ctx, s, opts = {}) {
  const viseme = opts.viseme || VISEMES.REST;
  ctx.save();
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  drawFarArm(ctx, s);
  drawLegs(ctx, s);
  drawTorso(ctx, s);
  drawHead(ctx, s, viseme, opts.blink || 0, opts.browRaise || 0);
  drawNearArm(ctx, s);
  ctx.restore();
}
