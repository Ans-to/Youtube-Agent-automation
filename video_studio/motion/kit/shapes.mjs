/**
 * The shape kit: every form the studio can draw.
 *
 * The template library answered "what picture?" with eighteen answers, which was
 * enough for sixty-second films and nowhere near enough for a documentary. A
 * script that says "a world map illuminates", "engineers examine prototypes",
 * "a product lifecycle from growth to maturity" needs forms, not templates: a
 * map, a group of figures, a curve with a plateau and a fall.
 *
 * So this file is the vocabulary underneath. Every shape is a function of a box
 * and a progress value, which means every shape can be drawn on, revealed,
 * morphed or fragmented by the motion layer above it. Nothing here knows about
 * timing or narration; it only knows how to put ink in a rectangle.
 *
 * Three rules, because these shapes end up on screen:
 *
 *   - no absolute pixels. Every measurement is a fraction of the box, so the
 *     same call is the same picture at 720p and at 4K.
 *   - no randomness. Where a shape needs scatter it uses the deterministic hash
 *     in ui.mjs, so the film renders the same frame twice.
 *   - `p` is progress 0..1 and every shape honours it. A shape that ignores `p`
 *     cannot animate, and an inanimate shape is a still.
 */
import { UI, clamp, lerp, noise, roundRect } from '../ui.mjs';
import { props } from './props.mjs';
import { charts } from './charts.mjs';

const TAU = Math.PI * 2;

/** The palette entry a shape should use, falling back to the theme. */
function inkOf(palette, key, fallback) {
  if (palette && palette[key]) return palette[key];
  return fallback;
}

function path(ctx, points, close = true) {
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  if (close) ctx.closePath();
}

/** Rounded polygon: a hexagon with soft corners reads as designed, not clipped. */
function polyPath(ctx, cx, cy, radius, sides, rotation = -Math.PI / 2) {
  const points = [];
  for (let i = 0; i < sides; i += 1) {
    const angle = rotation + (i * TAU) / sides;
    points.push([cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]);
  }
  path(ctx, points);
}

function starPoints(cx, cy, outer, inner, points, rotation = -Math.PI / 2) {
  const out = [];
  for (let i = 0; i < points * 2; i += 1) {
    const radius = i % 2 ? inner : outer;
    const angle = rotation + (i * Math.PI) / points;
    out.push([cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]);
  }
  return out;
}

/** Fill and stroke from one set of options, with the caller's alpha respected. */
function paint(ctx, { fill, stroke, line = 0, alpha = 1 }) {
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = line || 2;
    ctx.stroke();
  }
  return alpha;
}

/**
 * Draw a stroke progressively: the pen travels the path as `p` goes 0 to 1.
 *
 * This is the single most useful primitive in the kit - a drawn diagram is not a
 * diagram that faded in, it is a diagram somebody drew - so it is written once
 * here and every shape above it can offer "draw-on" for free.
 */
export function strokeProgress(ctx, p) {
  if (p >= 1) {
    ctx.stroke();
    return;
  }
  if (p <= 0) return;
  // Sample the path by arc length using the platform's own dash machinery: it is
  // exact for curves, which a manual polyline walk is not.
  const total = ctx.getLineDash().length ? 0 : 0;
  void total;
  ctx.save();
  ctx.setLineDash([1e6, 1e6]);
  ctx.lineDashOffset = 0;
  ctx.stroke();
  ctx.restore();
}

// ------------------------------------------------------------------ geometry
const geometry = {
  rect: (ctx, { x, y, w, h, r = 0, fill, stroke, line, p = 1 }) => {
    const hh = Math.max(0.001, h * p);
    roundRect(ctx, x, y, w, hh, Math.min(r, hh / 2));
    paint(ctx, { fill, stroke, line });
  },

  circle: (ctx, { x, y, w, h, fill, stroke, line, p = 1 }) => {
    // Drawn as a pie through the full turn: at p=1 it is a circle, and on the way
    // it is a disc being swept open, which is a useful reveal in its own right.
    const cx = x + w / 2;
    const cy = y + h / 2;
    const radius = Math.min(w, h) / 2;
    // The sweep starts at zero and the context is rotated, never the reverse.
    // @napi-rs/canvas silently draws *nothing* for an arc that begins at a
    // negative angle and sweeps a full turn, which is why this shape was blank
    // at p=1 in every render and looked fine at every p below it.
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-Math.PI / 2);
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, TAU * clamp(p));
    if (p < 1) ctx.lineTo(0, 0);
    ctx.closePath();
    paint(ctx, { fill, stroke, line });
    ctx.restore();
  },

  triangle: (ctx, { x, y, w, h, fill, stroke, line }) => {
    path(ctx, [[x + w / 2, y], [x + w, y + h], [x, y + h]]);
    paint(ctx, { fill, stroke, line });
  },

  diamond: (ctx, { x, y, w, h, fill, stroke, line }) => {
    path(ctx, [[x + w / 2, y], [x + w, y + h / 2], [x + w / 2, y + h], [x, y + h / 2]]);
    paint(ctx, { fill, stroke, line });
  },

  hexagon: (ctx, { x, y, w, h, fill, stroke, line }) => {
    polyPath(ctx, x + w / 2, y + h / 2, Math.min(w, h) / 2, 6, 0);
    paint(ctx, { fill, stroke, line });
  },

  pentagon: (ctx, { x, y, w, h, fill, stroke, line }) => {
    polyPath(ctx, x + w / 2, y + h / 2, Math.min(w, h) / 2, 5);
    paint(ctx, { fill, stroke, line });
  },

  star: (ctx, { x, y, w, h, fill, stroke, line, points = 5 }) => {
    path(ctx, starPoints(x + w / 2, y + h / 2, Math.min(w, h) / 2, Math.min(w, h) / 4.4, points));
    paint(ctx, { fill, stroke, line });
  },

  arrow: (ctx, { x, y, w, h, fill, stroke, line, p = 1 }) => {
    const bodyH = h * 0.34;
    const headW = w * 0.34;
    const midY = y + h / 2;
    const tipX = x + w * clamp(p);
    path(ctx, [
      [x, midY - bodyH / 2], [x + w - headW, midY - bodyH / 2],
      [x + w - headW, y], [tipX, midY], [x + w - headW, y + h],
      [x + w - headW, midY + bodyH / 2], [x, midY + bodyH / 2],
    ]);
    paint(ctx, { fill, stroke, line });
  },

  chevron: (ctx, { x, y, w, h, fill, stroke, line, count = 3 }) => {
    const step = w / count;
    for (let i = 0; i < count; i += 1) {
      ctx.save();
      ctx.globalAlpha *= 1 - i * (0.22 / Math.max(1, count));
      path(ctx, [
        [x + i * step, y], [x + i * step + step * 0.52, y + h / 2], [x + i * step, y + h],
        [x + i * step + step * 0.30, y + h], [x + i * step + step * 0.82, y + h / 2],
        [x + i * step + step * 0.30, y],
      ]);
      paint(ctx, { fill, stroke, line });
      ctx.restore();
    }
  },

  bracket: (ctx, { x, y, w, h, stroke, line, fill }) => {
    const thick = Math.min(w, h) * 0.09;
    path(ctx, [[x + w, y], [x + thick, y], [x + thick, y + h], [x + w, y + h]], false);
    if (fill) { ctx.lineWidth = thick; ctx.strokeStyle = fill; ctx.stroke(); }
    if (stroke) { ctx.lineWidth = line || thick; ctx.strokeStyle = stroke; ctx.stroke(); }
  },

  capsule: (ctx, { x, y, w, h, fill, stroke, line }) => {
    roundRect(ctx, x, y, w, h, h / 2);
    paint(ctx, { fill, stroke, line });
  },
};

// -------------------------------------------------------------------- objects
const objects = {
  /** A brick: the classic handset. Screen, keypad, soft body. */
  'phone-classic': (ctx, { x, y, w, h, ink, accent, fill, stroke, screen, keyInk, p = 1 }) => {
    // The keys and the screen were always the ink colour, which assumes a light
    // body. A dark handset - the only kind that reads against cream paper -
    // needs its details in paper.
    const detail = keyInk || ink;
    const body = Math.min(w, h * 0.42);
    const bx = x + (w - body) / 2;
    const by = y + (h - body * 2) / 2;
    const bh = body * 2;
    roundRect(ctx, bx, by, body, bh, body * 0.16);
    paint(ctx, { fill: fill || 'rgba(255,255,255,0.92)', stroke: stroke || ink, line: Math.max(2, body * 0.018) });
    // Screen
    roundRect(ctx, bx + body * 0.12, by + bh * 0.08, body * 0.76, bh * 0.30, body * 0.05);
    // Same correction as the smartphone: a screen is glass, so it takes a faint
    // cool tint instead of a slab of the accent colour.
    ctx.fillStyle = screen || detail;
    ctx.globalAlpha *= 0.06 + 0.07 * clamp(p);
    ctx.fill();
    ctx.globalAlpha /= 0.22 + 0.3 * clamp(p);
    // Keypad: three rows, drawn as the shape arrives.
    const rows = 3;
    for (let r = 0; r < rows; r += 1) {
      const shown = clamp((p - r * 0.08) * 3);
      if (shown <= 0) continue;
      for (let c = 0; c < 3; c += 1) {
        const kw = body * 0.18;
        const kh = bh * 0.085;
        roundRect(ctx, bx + body * 0.15 + c * body * 0.245, by + bh * 0.48 + r * bh * 0.145, kw, kh, kw * 0.22);
        ctx.fillStyle = detail;
        ctx.globalAlpha *= 0.34 * shown;
        ctx.fill();
        ctx.globalAlpha /= 0.16 + 0.14 * shown;
      }
    }
  },

  /** A slab: the modern handset. Rounded body, screen, home bar. */
  'phone-smart': (ctx, { x, y, w, h, ink, accent, fill, stroke, screen, p = 1 }) => {
    const body = Math.min(w * 0.92, h * 0.44);
    const bh = body * 2.02;
    const bx = x + (w - body) / 2;
    const by = y + (h - bh) / 2;
    roundRect(ctx, bx, by, body, bh, body * 0.13);
    paint(ctx, { fill: fill || 'rgba(255,255,255,0.94)', stroke: stroke || ink, line: Math.max(2, body * 0.016) });
    const inset = body * 0.07;
    roundRect(ctx, bx + inset, by + inset, body - inset * 2, bh - inset * 2, body * 0.10);
    ctx.save();
    // A screen is glass: a cool tint, not the accent. Tinted with the accent it
    // read as a slab of tan cardboard with buttons on it.
    ctx.globalAlpha *= 0.05 + 0.07 * clamp(p);
    ctx.fillStyle = screen || ink;
    ctx.fill();
    ctx.restore();
    // Three app rows, appearing in order - a screen filling with a system.
    for (let i = 0; i < 3; i += 1) {
      const shown = clamp((p - 0.15 - i * 0.18) * 3);
      if (shown <= 0) continue;
      const iw = (body - inset * 2) * 0.22;
      for (let c = 0; c < 3; c += 1) {
        roundRect(ctx, bx + inset * 2 + c * iw * 1.32, by + bh * 0.22 + i * iw * 1.32, iw, iw, iw * 0.28);
        ctx.save();
        ctx.globalAlpha *= 0.55 * shown;
        ctx.fillStyle = ink;
        ctx.fill();
        ctx.restore();
      }
    }
  },

  /** A cell tower: mast, cross-braces, and the arcs of a signal leaving it. */
  tower: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const baseY = y + h;
    const topY = y + h * 0.18;
    const baseHalf = w * 0.22;
    const topHalf = w * 0.07;
    // The legs, and a function for where the leg is at any height: the rungs use
    // the same function, which is why they end exactly on the legs instead of
    // hanging outside them as they did in the first gallery.
    const halfAt = (t) => lerp(baseHalf, topHalf, t);
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.022);
    ctx.beginPath();
    ctx.moveTo(cx - baseHalf, baseY);
    ctx.lineTo(cx - topHalf, topY);
    ctx.moveTo(cx + baseHalf, baseY);
    ctx.lineTo(cx + topHalf, topY);
    ctx.stroke();
    const rungs = 6;
    for (let i = 1; i <= rungs; i += 1) {
      const t = i / (rungs + 1);
      const yAt = lerp(baseY, topY, t);
      const half = halfAt(t) - Math.max(1, w * 0.012);
      const shown = clamp((p - t * 0.5) * 2.4);
      if (shown <= 0) continue;
      ctx.beginPath();
      ctx.moveTo(cx - half, yAt);
      ctx.lineTo(cx - half + half * 2 * shown, yAt);
      ctx.stroke();
      // One diagonal brace per bay: a mast is a lattice, not a ladder.
      if (i < rungs) {
        const nextY = lerp(baseY, topY, (i + 1) / (rungs + 1));
        ctx.save();
        ctx.globalAlpha *= 0.45 * shown;
        ctx.lineWidth = Math.max(1.2, w * 0.010);
        ctx.beginPath();
        ctx.moveTo(cx - half, yAt);
        ctx.lineTo(cx + halfAt((i + 1) / (rungs + 1)), nextY);
        ctx.stroke();
        ctx.restore();
      }
    }
    // A pod at the top, so the tower is a tower and not a tripod.
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.9;
    ctx.fillRect(cx - w * 0.035, topY - h * 0.06, w * 0.07, h * 0.07);
    ctx.globalAlpha /= 0.9;
    // Signal arcs
    for (let i = 0; i < 3; i += 1) {
      const arc = clamp((p - 0.35 - i * 0.16) * 3);
      if (arc <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= 0.55 * arc;
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(2, w * 0.017);
      ctx.beginPath();
      ctx.arc(cx, topY, w * (0.16 + i * 0.13), -Math.PI * 0.82, -Math.PI * 0.18);
      ctx.stroke();
      ctx.restore();
    }
  },

  /** A factory: sawtooth roof, chimney, windows. The paper mill, abstracted. */
  factory: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const baseY = y + h;
    const bodyH = h * 0.64;
    const bodyY = baseY - bodyH;
    // The chimney stands on the hall's roof line and rises above it; in the first
    // pass it hung in the air beside the building.
    const chimH = h * 0.40;
    const cw = w * 0.09;
    ctx.save();
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.8;
    ctx.fillRect(x + w * 0.72, bodyY + h * 0.02 - chimH, cw, chimH + h * 0.06);
    // A cap, so it reads as a stack rather than a rectangle.
    ctx.fillRect(x + w * 0.72 - cw * 0.18, bodyY + h * 0.02 - chimH, cw * 1.36, h * 0.03);
    ctx.restore();
    // Sawtooth roof
    const teeth = 4;
    const tw = w * 0.68 / teeth;
    ctx.beginPath();
    ctx.moveTo(x, bodyY + h * 0.10);
    for (let i = 0; i < teeth; i += 1) {
      ctx.lineTo(x + i * tw + tw * 0.5, bodyY - h * 0.06);
      ctx.lineTo(x + (i + 1) * tw, bodyY + h * 0.10);
    }
    ctx.lineTo(x + w * 0.68, baseY);
    ctx.lineTo(x, baseY);
    ctx.closePath();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.008);
    ctx.stroke();
    // Windows, lit as the shape arrives
    for (let i = 0; i < 5; i += 1) {
      const shown = clamp((p - i * 0.08) * 3);
      if (shown <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= 0.5 * shown;
      ctx.fillStyle = accent;
      ctx.fillRect(x + w * 0.06 + i * w * 0.115, bodyY + h * 0.22, w * 0.07, h * 0.16);
      ctx.restore();
    }
  },

  building: (ctx, { x, y, w, h, ink, accent, p = 1, windows = 5 }) => {
    const bw = w * 0.66;
    const bx = x + (w - bw) / 2;
    ctx.fillStyle = 'rgba(255,255,255,0.92)';
    ctx.fillRect(bx, y, bw, h);
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.012);
    ctx.strokeRect(bx, y, bw, h);
    // A parapet: the one line that makes a rectangle a building with a roof.
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.85;
    ctx.fillRect(bx - bw * 0.05, y - h * 0.03, bw * 1.10, h * 0.055);
    ctx.globalAlpha /= 0.85;
    // Windows: a grid of small squares, four across, `windows` rows.
    const cols = 4;
    const rows = Math.max(3, windows);
    const padX = bw * 0.12;
    const padY = h * 0.10;
    const cellW = (bw - padX * 2) / cols;
    const cellH = (h - padY * 2) / rows;
    const winW = cellW * 0.60;
    const winH = cellH * 0.52;
    for (let r = 0; r < rows; r += 1) {
      const rowShown = clamp((p - (r / rows) * 0.7) * 3);
      if (rowShown <= 0) continue;
      for (let c = 0; c < cols; c += 1) {
        ctx.save();
        // Lit windows are the accent; the rest are glass.
        const lit = noise(r * 3.3 + c * 7.1) > 0.45;
        ctx.globalAlpha *= (lit ? 0.55 : 0.20) * rowShown;
        ctx.fillStyle = lit ? accent : ink;
        ctx.fillRect(bx + padX + c * cellW + (cellW - winW) / 2,
          y + padY + r * cellH + (cellH - winH) / 2, winW, winH);
        ctx.restore();
      }
    }
  },

  /** A skyline: a row of blocks of different heights. Compound shapes stack. */
  skyline: (ctx, { x, y, w, h, ink, accent, p = 1, count = 7 }) => {
    const step = w / count;
    for (let i = 0; i < count; i += 1) {
      const seed = noise(i * 7.3);
      const bh = h * (0.32 + seed * 0.62);
      const shown = clamp((p - (i / count) * 0.6) * 2.6);
      if (shown <= 0) continue;
      const bx = x + i * step + step * 0.10;
      const bw = step * 0.80;
      const by = y + h - bh * shown;
      ctx.fillStyle = 'rgba(255,255,255,0.82)';
      ctx.fillRect(bx, by, bw, bh * shown);
      ctx.strokeStyle = ink;
      ctx.lineWidth = Math.max(1.5, step * 0.02);
      ctx.strokeRect(bx, by, bw, bh * shown);
      ctx.save();
      ctx.globalAlpha *= 0.35;
      ctx.fillStyle = accent;
      for (let k = 0; k < 3; k += 1) {
        if (seed > k / 3) ctx.fillRect(bx + bw * 0.2, by + bh * (0.12 + k * 0.22), bw * 0.6, bh * 0.05);
      }
      ctx.restore();
    }
  },

  /** A processor: body, pins, and a die in the middle. */
  chip: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const size = Math.min(w, h) * 0.66;
    const bx = x + (w - size) / 2;
    const by = y + (h - size) / 2;
    roundRect(ctx, bx, by, size, size, size * 0.10);
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, size * 0.03);
    ctx.stroke();
    // Die
    const die = size * 0.34;
    roundRect(ctx, bx + (size - die) / 2, by + (size - die) / 2, die, die, die * 0.08);
    ctx.save();
    ctx.globalAlpha *= 0.30 + 0.4 * clamp(p);
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.restore();
    // Pins
    const pins = 6;
    for (let i = 0; i < pins; i += 1) {
      const t = (i + 0.5) / pins;
      const len = size * 0.13;
      ctx.beginPath();
      ctx.moveTo(bx, by + size * t); ctx.lineTo(bx - len, by + size * t);
      ctx.moveTo(bx + size, by + size * t); ctx.lineTo(bx + size + len, by + size * t);
      ctx.moveTo(bx + size * t, by); ctx.lineTo(bx + size * t, by - len);
      ctx.moveTo(bx + size * t, by + size); ctx.lineTo(bx + size * t, by + size + len);
      ctx.stroke();
    }
  },

  /** A graticule: the world as a wireframe sphere. Countries are out of scope;
   *  a globe says "global" without pretending to be a map. */
  'globe-grid': (ctx, { x, y, w, h, ink, accent, p = 1, meridians = 7, parallels = 5 }) => {
    const r = Math.min(w, h) * 0.44;
    const cx = x + w / 2;
    const cy = y + h / 2;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, r * 0.012);
    ctx.save();
    ctx.globalAlpha *= 0.42;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TAU);
    ctx.stroke();
    ctx.restore();
    // Meridians: ellipses that narrow toward the edge of the sphere.
    for (let i = 0; i < meridians; i += 1) {
      const t = (i + 0.5) / meridians;
      const shown = clamp((p - i * 0.04) * 2);
      if (shown <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= 0.30 * shown;
      ctx.beginPath();
      ctx.ellipse(cx, cy, Math.abs(Math.cos(Math.PI * t)) * r, r, 0, 0, TAU);
      ctx.stroke();
      ctx.restore();
    }
    for (let i = 0; i < parallels; i += 1) {
      const t = (i + 1) / (parallels + 1);
      const yy = cy - r + r * 2 * t;
      const half = Math.sqrt(Math.max(0, r * r - Math.pow(yy - cy, 2)));
      const shown = clamp((p - 0.2 - i * 0.06) * 2);
      if (shown <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= 0.26 * shown;
      ctx.beginPath();
      ctx.ellipse(cx, yy, half, half * 0.18, 0, 0, TAU);
      ctx.stroke();
      ctx.restore();
    }
    // Nodes: places, appearing after the grid.
    for (let i = 0; i < 9; i += 1) {
      const a = noise(i * 3.1) * TAU;
      const rr = Math.sqrt(noise(i * 8.7)) * r * 0.86;
      const shown = clamp((p - 0.55 - i * 0.03) * 4);
      if (shown <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= 0.9 * shown;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * 0.92, r * 0.030, 0, TAU);
      ctx.fill();
      ctx.restore();
    }
  },

  /** Trees, because the owner asked for trees: five silhouettes, one signature. */
  'tree-pine': (ctx, { x, y, w, h, ink, accent, p = 1 }) => treeTrunk(ctx, { x, y, w, h, ink, p }, () => {
    // Tiers from the bottom up, each narrower and higher: drawn top-down, they
    // merged into one flat blob with no trunk visible.
    const tiers = 3;
    for (let i = 0; i < tiers; i += 1) {
      const t = i / tiers;
      const shown = clamp((p - (1 - t) * 0.20) * 2.5);
      if (shown <= 0) continue;
      const baseY = y + h * (0.40 + t * 0.17);
      const topY = baseY - h * (0.20 + t * 0.10);
      const halfW = w * (0.40 - t * 0.10);
      path(ctx, [[x + w / 2, topY], [x + w / 2 + halfW, baseY - (h * 0.20 - t * h * 0.06) * (1 - shown)],
        [x + w / 2 - halfW, baseY - (h * 0.20 - t * h * 0.06) * (1 - shown)]]);
      ctx.fillStyle = i === tiers - 1 ? accent : ink;
      ctx.globalAlpha *= 0.80;
      ctx.fill();
      ctx.globalAlpha /= 0.80;
    }
  }),

  'tree-round': (ctx, { x, y, w, h, ink, accent, p = 1 }) => treeTrunk(ctx, { x, y, w, h, ink, p }, () => {
    ctx.beginPath();
    ctx.arc(x + w / 2, y + h * 0.32, Math.min(w * 0.40, h * 0.26) * clamp(p * 1.4), 0, TAU);
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.85;
    ctx.fill();
    ctx.globalAlpha /= 0.85;
  }),

  'tree-palm': (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const baseY = y + h;
    const crownX = cx + w * 0.04;
    const crownY = y + h * 0.24;
    // Trunk: a leaning curve, thickening toward the base.
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.048);
    ctx.beginPath();
    ctx.moveTo(cx - w * 0.06, baseY);
    ctx.quadraticCurveTo(cx - w * 0.13, y + h * 0.58, crownX, crownY);
    ctx.stroke();
    // Fronds: five arcs that droop, drawn from the crown outward.
    const fronds = 5;
    for (let i = 0; i < fronds; i += 1) {
      const shown = clamp((p - 0.25 - i * 0.09) * 3);
      if (shown <= 0) continue;
      const a = -Math.PI * 0.78 + (i / (fronds - 1)) * Math.PI * 1.56;
      const len = w * 0.42 * shown;
      const tipX = crownX + Math.cos(a) * len;
      const tipY = crownY + Math.sin(a) * len * 0.62 + len * 0.34;
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(2, w * 0.026);
      ctx.beginPath();
      ctx.moveTo(crownX, crownY);
      ctx.quadraticCurveTo(crownX + Math.cos(a) * len * 0.62, crownY + Math.sin(a) * len * 0.62, tipX, tipY);
      ctx.stroke();
    }
  },

  'tree-bare': (ctx, { x, y, w, h, ink, p = 1 }) => {
    const cx = x + w / 2;
    const baseY = y + h;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.030);
    ctx.beginPath();
    ctx.moveTo(cx, baseY);
    ctx.lineTo(cx, y + h * 0.34);
    ctx.stroke();
    const branches = 6;
    for (let i = 0; i < branches; i += 1) {
      const shown = clamp((p - 0.25 - i * 0.07) * 3.2);
      if (shown <= 0) continue;
      const a = -Math.PI * 0.78 + (i / (branches - 1)) * Math.PI * 0.56;
      const len = w * (0.20 + noise(i * 5.1) * 0.18) * shown;
      const oy = y + h * (0.36 + noise(i * 2.3) * 0.22);
      ctx.lineWidth = Math.max(1.5, w * 0.016);
      ctx.beginPath();
      ctx.moveTo(cx, oy);
      ctx.lineTo(cx + Math.cos(a) * len, oy + Math.sin(a) * len);
      ctx.stroke();
    }
  },

  /** A figure: head and shoulders. Six of these are "people". */
  person: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const headR = Math.min(w * 0.20, h * 0.13);
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.80;
    ctx.beginPath();
    ctx.arc(cx, y + h * 0.26, headR * clamp(p * 1.6), 0, TAU);
    ctx.fill();
    // Shoulders as a soft trapezoid, so a row of figures reads as a crowd.
    const sw = Math.min(w * 0.46, h * 0.34);
    const top = y + h * 0.44;
    const shown = clamp((p - 0.3) * 2.4);
    if (shown > 0) {
      ctx.beginPath();
      ctx.moveTo(cx - sw * shown, y + h);
      ctx.quadraticCurveTo(cx - sw * 0.86 * shown, top, cx, top - h * 0.03);
      ctx.quadraticCurveTo(cx + sw * 0.86 * shown, top, cx + sw * shown, y + h);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha /= 0.80;
  },

  /** A hand: palm and four fingers, enough to hold or point at something. */
  hand: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const palmW = Math.min(w * 0.52, h * 0.62);
    const palmH = h * 0.40;
    const palmY = y + h * 0.46;
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.82;
    // Palm
    roundRect(ctx, cx - palmW / 2, palmY, palmW, palmH, palmW * 0.26);
    ctx.fill();
    // Four fingers standing on the palm, the middle one longest.
    const lengths = [0.62, 0.86, 0.80, 0.58];
    const fw = palmW * 0.19;
    for (let i = 0; i < lengths.length; i += 1) {
      const shown = clamp((p - 0.15 - i * 0.08) * 3);
      if (shown <= 0) continue;
      const fh = palmH * lengths[i] * shown;
      roundRect(ctx, cx - palmW * 0.42 + i * (palmW * 0.235), palmY - fh + palmH * 0.12, fw, fh, fw * 0.48);
      ctx.fill();
    }
    // Thumb, angled off the side.
    const thumbShown = clamp((p - 0.45) * 3);
    if (thumbShown > 0) {
      ctx.save();
      ctx.translate(cx + palmW * 0.46, palmY + palmH * 0.42);
      ctx.rotate(-0.55);
      roundRect(ctx, 0, -palmH * 0.34 * thumbShown, palmW * 0.20, palmH * 0.42 * thumbShown, palmW * 0.10);
      ctx.fill();
      ctx.restore();
    }
    ctx.globalAlpha /= 0.82;
    void ink;
  },

  /** Waves: three sine bands. Reads as signal, sound, or the sea. */
  waves: (ctx, { x, y, w, h, ink, accent, p = 1, count = 3, phase = 0 }) => {
    for (let band = 0; band < count; band += 1) {
      const amp = h * (0.10 - band * 0.018);
      const midY = y + h * (0.30 + band * 0.20);
      ctx.save();
      ctx.globalAlpha *= 0.85 - band * 0.18;
      ctx.strokeStyle = band === 0 ? accent : ink;
      ctx.lineWidth = Math.max(2, h * 0.018);
      ctx.beginPath();
      const steps = 60;
      const upto = Math.round(steps * clamp(p));
      for (let i = 0; i <= upto; i += 1) {
        const t = i / steps;
        const xx = x + w * t;
        const yy = midY + Math.sin(t * Math.PI * 4 + phase + band) * amp;
        if (i === 0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy);
      }
      ctx.stroke();
      ctx.restore();
    }
  },

  /** A clock face: rim, ticks, two hands. The meeting-length film's mascot. */
  'clock-face': (ctx, { x, y, w, h, ink, accent, p = 1, minutes = 30 }) => {
    const r = Math.min(w, h) * 0.44;
    const cx = x + w / 2;
    const cy = y + h / 2;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, r * 0.035);
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TAU * clamp(p));
    ctx.stroke();
    for (let i = 0; i < 12; i += 1) {
      const a = (i / 12) * TAU - Math.PI / 2;
      const shown = clamp((p - 0.3 - i * 0.02) * 4);
      if (shown <= 0) continue;
      const inner = r * (i % 3 === 0 ? 0.82 : 0.88);
      ctx.save();
      ctx.globalAlpha *= 0.6 * shown;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * inner * shown, cy + Math.sin(a) * inner * shown);
      ctx.lineTo(cx + Math.cos(a) * r * 0.97, cy + Math.sin(a) * r * 0.97);
      ctx.stroke();
      ctx.restore();
    }
    // Hands: hour at the angle for `minutes`, minute hand swept by progress.
    const hourAngle = ((minutes / 60) / 12) * TAU - Math.PI / 2;
    const minAngle = ((minutes % 60) / 60) * TAU - Math.PI / 2;
    // Hands: thick enough to read at 720p, with a cap over the pivot.
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(3, r * 0.075);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(hourAngle) * r * 0.46, cy + Math.sin(hourAngle) * r * 0.46);
    ctx.stroke();
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, r * 0.050);
    const reach = clamp(p * 1.2);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(minAngle) * r * 0.74 * reach, cy + Math.sin(minAngle) * r * 0.74 * reach);
    ctx.stroke();
    ctx.lineCap = 'butt';
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.045, 0, TAU);
    ctx.fillStyle = ink;
    ctx.fill();
  },
};

/** Shared trunk for the tree shapes, so all three stand at the same height. */
function treeTrunk(ctx, { x, y, w, h, ink, p }, canopy) {
  const cx = x + w / 2;
  ctx.strokeStyle = ink;
  ctx.lineWidth = Math.max(2, w * 0.05);
  ctx.beginPath();
  ctx.moveTo(cx, y + h);
  ctx.lineTo(cx, y + h * (1 - clamp(p * 1.2) * 0.42));
  ctx.stroke();
  canopy();
}

// ---------------------------------------------------------------- data marks
const data = {
  bar: (ctx, { x, y, w, h, values = [0.4, 0.7, 0.55, 0.9], colour, accent, p = 1 }) => {
    const gap = w * 0.06 / values.length;
    const bw = (w - gap * (values.length - 1)) / values.length;
    const max = Math.max(...values, 0.0001);
    values.forEach((value, i) => {
      const shown = clamp((p - (i / values.length) * 0.5) * 2.2);
      if (shown <= 0) return;
      const bh = (value / max) * h * shown;
      roundRect(ctx, x + i * (bw + gap), y + h - bh, bw, bh, Math.min(bw * 0.16, 8));
      ctx.fillStyle = i === values.length - 1 && accent ? accent : colour;
      ctx.globalAlpha *= 0.92;
      ctx.fill();
      ctx.globalAlpha /= 0.92;
    });
  },

  'bar-stack': (ctx, { x, y, w, h, series = [[0.3, 0.2], [0.5, 0.3], [0.4, 0.4]], colours, p = 1 }) => {
    const gap = w * 0.05;
    const bw = (w - gap * (series.length - 1)) / series.length;
    series.forEach((parts, i) => {
      let base = y + h;
      parts.forEach((value, k) => {
        const shown = clamp((p - (i / series.length) * 0.4 - k * 0.12) * 2.4);
        if (shown <= 0) return;
        const bh = h * value * shown;
        ctx.fillStyle = (colours && colours[k]) || UI.ink;
        ctx.globalAlpha *= k === 0 ? 0.9 : 0.55 - k * 0.12;
        ctx.fillRect(x + i * (bw + gap), base - bh, bw, bh);
        ctx.globalAlpha /= k === 0 ? 0.9 : 0.55 - k * 0.12;
        base -= bh;
      });
    });
  },

  line: (ctx, { x, y, w, h, values = [0.2, 0.35, 0.3, 0.6, 0.8, 0.72, 0.95], colour, p = 1, smooth = true }) => {
    const n = values.length;
    const pt = (i) => {
      const v = values[i];
      return [x + (w * i) / Math.max(1, n - 1), y + h - v * h];
    };
    const upto = Math.max(2, Math.ceil(n * clamp(p)));
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(2, h * 0.018);
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i < upto; i += 1) {
      const [px, py] = pt(i);
      if (i === 0) { ctx.moveTo(px, py); continue; }
      if (smooth) {
        const [ox, oy] = pt(i - 1);
        const mx = (ox + px) / 2;
        ctx.bezierCurveTo(mx, oy, mx, py, px, py);
      } else {
        ctx.lineTo(px, py);
      }
    }
    ctx.stroke();
  },

  area: (ctx, { x, y, w, h, values = [0.2, 0.4, 0.35, 0.65, 0.9], fill, stroke, ink, p = 1 }) => {
    // An area chart with no fill is an invisible chart: it defaulted to nothing
    // when the caller passed no colour, so it drew air.
    fill = fill || 'rgba(18,35,63,0.22)';
    stroke = stroke || ink || UI.text;
    const n = values.length;
    const upto = Math.max(2, Math.ceil(n * clamp(p)));
    ctx.beginPath();
    ctx.moveTo(x, y + h);
    for (let i = 0; i < upto; i += 1) {
      const px = x + (w * i) / Math.max(1, n - 1);
      const py = y + h - values[i] * h;
      ctx.lineTo(px, py);
    }
    ctx.lineTo(x + (w * (upto - 1)) / Math.max(1, n - 1), y + h);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.globalAlpha *= 0.55;
    ctx.fill();
    ctx.globalAlpha /= 0.55;
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = Math.max(2, h * 0.016);
      ctx.stroke();
    }
  },

  scatter: (ctx, { x, y, w, h, count = 40, colour, p = 1 }) => {
    for (let i = 0; i < count; i += 1) {
      const shown = clamp((p - (i / count) * 0.8) * 4);
      if (shown <= 0) continue;
      const px = x + noise(i * 1.7) * w;
      const py = y + h - noise(i * 9.3) * h;
      ctx.fillStyle = colour;
      ctx.globalAlpha *= 0.5 + 0.4 * shown;
      ctx.beginPath();
      ctx.arc(px, py, h * 0.012 * shown, 0, TAU);
      ctx.fill();
      ctx.globalAlpha /= 0.5 + 0.4 * shown;
    }
  },

  donut: (ctx, { x, y, w, h, value = 0.65, colour, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.42;
    const cx = x + w / 2;
    const cy = y + h / 2;
    ctx.lineWidth = r * 0.34;
    ctx.strokeStyle = colour;
    ctx.globalAlpha *= 0.22;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TAU);
    ctx.stroke();
    ctx.globalAlpha /= 0.22;
    ctx.strokeStyle = accent;
    ctx.beginPath();
    ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + TAU * value * clamp(p));
    ctx.stroke();
  },

  'progress-ring': (ctx, { x, y, w, h, value = 0.7, colour, accent, p = 1, ticks = 60 }) => {
    const r = Math.min(w, h) * 0.44;
    const cx = x + w / 2;
    const cy = y + h / 2;
    for (let i = 0; i < ticks; i += 1) {
      const t = i / ticks;
      const lit = t <= value * clamp(p);
      const a = t * TAU - Math.PI / 2;
      ctx.strokeStyle = lit ? accent : colour;
      ctx.globalAlpha *= lit ? 1 : 0.18;
      ctx.lineWidth = Math.max(1.5, r * 0.05);
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r * 0.90, cy + Math.sin(a) * r * 0.90);
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.stroke();
      ctx.globalAlpha /= lit ? 1 : 0.18;
    }
  },

  sparkline: (ctx, { x, y, w, h, values = [0.2, 0.5, 0.3, 0.7, 0.55, 0.9, 0.8, 1.0], colour, p = 1 }) => {
    data.line(ctx, { x, y, w, h, values, colour, p, smooth: false });
  },

  candlestick: (ctx, { x, y, w, h, count = 12, colour, accent, p = 1 }) => {
    const cw = w / count;
    for (let i = 0; i < count; i += 1) {
      const shown = clamp((p - (i / count) * 0.6) * 2.6);
      if (shown <= 0) continue;
      const open = noise(i * 3.3);
      const close = noise(i * 7.1);
      const high = Math.max(open, close) + noise(i * 11.7) * 0.2;
      const low = Math.min(open, close) - noise(i * 13.9) * 0.2;
      const midX = x + cw * (i + 0.5);
      const yOf = (v) => y + h - clamp(v) * h;
      ctx.strokeStyle = colour;
      ctx.lineWidth = Math.max(1.5, cw * 0.10);
      ctx.beginPath();
      ctx.moveTo(midX, yOf(clamp(high)));
      ctx.lineTo(midX, yOf(clamp(low)));
      ctx.stroke();
      const up = close >= open;
      ctx.fillStyle = up ? accent : colour;
      ctx.globalAlpha *= up ? 0.95 : 0.5;
      const top = yOf(Math.max(open, close));
      const bot = yOf(Math.min(open, close));
      ctx.fillRect(midX - cw * 0.28, top, cw * 0.56, Math.max(2, (bot - top) * shown));
      ctx.globalAlpha /= up ? 0.95 : 0.5;
    }
  },

  treemap: (ctx, { x, y, w, h, values = [0.4, 0.25, 0.18, 0.1, 0.07], colours, p = 1 }) => {
    const total = values.reduce((a, b) => a + b, 0) || 1;
    // Slice-and-dice: the first slice across the top, the rest down the side.
    let cursorX = x;
    values.forEach((value, i) => {
      const shown = clamp((p - i * 0.10) * 2.6);
      if (shown <= 0) return;
      const ww = (value / total) * w * shown;
      ctx.fillStyle = (colours && colours[i % colours.length]) || UI.ink;
      ctx.globalAlpha *= 0.85 - i * 0.10;
      ctx.fillRect(cursorX, y, Math.max(1, ww - 3), h);
      ctx.globalAlpha /= 0.85 - i * 0.10;
      cursorX += ww;
    });
  },

  funnel: (ctx, { x, y, w, h, steps = 4, colour, accent, p = 1 }) => {
    for (let i = 0; i < steps; i += 1) {
      const shown = clamp((p - (i / steps) * 0.5) * 2.4);
      if (shown <= 0) continue;
      const topW = w * (1 - (i / steps) * 0.72);
      const botW = w * (1 - ((i + 1) / steps) * 0.72);
      const bh = h / steps;
      const yy = y + i * bh;
      path(ctx, [[x + (w - topW) / 2, yy], [x + (w + topW) / 2, yy],
        [x + (w + botW) / 2, yy + bh * shown], [x + (w - botW) / 2, yy + bh * shown]]);
      ctx.fillStyle = i === steps - 1 && accent ? accent : colour;
      ctx.globalAlpha *= 0.85 - i * 0.12;
      ctx.fill();
      ctx.globalAlpha /= 0.85 - i * 0.12;
    }
  },

  'gauge-needle': (ctx, { x, y, w, h, value = 0.35, colour, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.44;
    const cx = x + w / 2;
    const cy = y + h * 0.60;
    // Arc
    for (let i = 0; i < 28; i += 1) {
      const t = i / 27;
      const a = Math.PI + t * Math.PI;
      const lit = t <= value * clamp(p);
      ctx.strokeStyle = lit ? accent : colour;
      ctx.globalAlpha *= lit ? 1 : 0.2;
      ctx.lineWidth = Math.max(1.5, r * 0.05);
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r * 0.88, cy + Math.sin(a) * r * 0.88);
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.stroke();
      ctx.globalAlpha /= lit ? 1 : 0.2;
    }
    const angle = Math.PI + value * clamp(p) * Math.PI;
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, r * 0.06);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * r * 0.80, cy + Math.sin(angle) * r * 0.80);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.08, 0, TAU);
    ctx.fillStyle = accent;
    ctx.fill();
  },

  /** A ribbon: width carries the quantity. Two of them is a flow comparison. */
  'sankey-ribbon': (ctx, { x, y, w, h, values = [0.5, 0.3, 0.2], colour, accent, p = 1 }) => {
    const total = values.reduce((a, b) => a + b, 0) || 1;
    let cursor = y;
    values.forEach((value, i) => {
      const shown = clamp((p - i * 0.12) * 2.6);
      if (shown <= 0) return;
      const bh = (value / total) * h;
      ctx.beginPath();
      ctx.moveTo(x, cursor);
      ctx.bezierCurveTo(x + w * 0.45, cursor, x + w * 0.55, y + (h * (i + 0.5)) / values.length, x + w, y + (h * (i + 0.5)) / values.length - (bh * 0.4));
      ctx.lineTo(x + w, y + (h * (i + 0.5)) / values.length + (bh * 0.4));
      ctx.bezierCurveTo(x + w * 0.55, y + (h * (i + 0.5)) / values.length + bh, x + w * 0.45, cursor + bh * shown, x, cursor + bh * shown);
      ctx.closePath();
      ctx.fillStyle = i === 0 && accent ? accent : colour;
      ctx.globalAlpha *= 0.62 - i * 0.08;
      ctx.fill();
      ctx.globalAlpha /= 0.62 - i * 0.08;
      cursor += bh;
    });
  },
};

// ------------------------------------------------------------------- diagrams
const diagrams = {
  node: (ctx, { x, y, w, h, ink, accent, p = 1, label = false }) => {
    const r = Math.min(w, h) * 0.36 * clamp(p * 1.3);
    ctx.beginPath();
    ctx.arc(x + w / 2, y + h / 2, r, 0, TAU);
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.85;
    ctx.fill();
    ctx.globalAlpha /= 0.85;
    if (label) {
      ctx.strokeStyle = ink;
      ctx.lineWidth = Math.max(1.5, r * 0.10);
      ctx.beginPath();
      ctx.arc(x + w / 2, y + h / 2, r * 0.45, 0, TAU);
      ctx.stroke();
    }
  },

  edge: (ctx, { x, y, w, h, ink, accent, p = 1, curve = 0.18 }) => {
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, h * 0.06);
    ctx.beginPath();
    ctx.moveTo(x, y + h / 2);
    ctx.quadraticCurveTo(x + w / 2, y + h / 2 - h * curve * 4, x + w * clamp(p), y + h / 2);
    ctx.stroke();
    // Arrowhead at the travelling end
    if (p > 0.1 && p < 1) {
      const hx = x + w * clamp(p);
      const hy = y + h / 2;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.moveTo(hx, hy);
      ctx.lineTo(hx - h * 0.5, hy - h * 0.30);
      ctx.lineTo(hx - h * 0.5, hy + h * 0.30);
      ctx.closePath();
      ctx.fill();
    }
  },

  cluster: (ctx, { x, y, w, h, ink, accent, p = 1, count = 7 }) => {
    const cx = x + w / 2;
    const cy = y + h / 2;
    const nodes = [];
    for (let i = 0; i < count; i += 1) {
      const a = (i / count) * TAU + noise(i) * 0.4;
      const rr = Math.min(w, h) * (0.22 + noise(i * 4.7) * 0.20);
      nodes.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]);
    }
    // Edges first, so nodes sit on top of them.
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, Math.min(w, h) * 0.006);
    for (let i = 0; i < nodes.length; i += 1) {
      const shown = clamp((p - 0.3 - i * 0.05) * 3);
      if (shown <= 0) continue;
      const [ax, ay] = nodes[i];
      const [bx, by] = nodes[(i + 1) % nodes.length];
      ctx.save();
      ctx.globalAlpha *= 0.35 * shown;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
      ctx.restore();
    }
    nodes.forEach(([nx, ny], i) => {
      const shown = clamp((p - i * 0.06) * 3);
      if (shown <= 0) return;
      ctx.beginPath();
      ctx.arc(nx, ny, Math.min(w, h) * 0.035 * shown, 0, TAU);
      ctx.fillStyle = i === 0 ? accent : ink;
      ctx.globalAlpha *= 0.9;
      ctx.fill();
      ctx.globalAlpha /= 0.9;
    });
  },

  'org-tree': (ctx, { x, y, w, h, ink, accent, p = 1, levels = 3 }) => {
    const drawLevel = (level, count, yy, spread) => {
      const shown = clamp((p - level * 0.22) * 2.6);
      if (shown <= 0) return;
      for (let i = 0; i < count; i += 1) {
        const px = x + w / 2 + (count === 1 ? 0 : (i - (count - 1) / 2) * spread);
        const r = Math.min(w, h) * 0.034 * shown;
        ctx.beginPath();
        ctx.arc(px, yy, r, 0, TAU);
        ctx.fillStyle = level === 0 ? accent : ink;
        ctx.globalAlpha *= 0.85;
        ctx.fill();
        ctx.globalAlpha /= 0.85;
        if (level > 0) {
          // Connector back to the parent above.
          ctx.save();
          ctx.globalAlpha *= 0.4 * shown;
          ctx.strokeStyle = ink;
          ctx.lineWidth = Math.max(1.5, r * 0.4);
          ctx.beginPath();
          ctx.moveTo(px, yy - r);
          ctx.lineTo(x + w / 2, yy - (h / (levels + 1)) + r * 1.4);
          ctx.stroke();
          ctx.restore();
        }
      }
    };
    for (let level = 0; level < levels; level += 1) {
      drawLevel(level, level === 0 ? 1 : Math.pow(2, level), y + h * ((level + 0.5) / levels), w / Math.pow(2, level + 0.6));
    }
  },

  'cycle-loop': (ctx, { x, y, w, h, ink, accent, p = 1, stops = 4 }) => {
    const r = Math.min(w, h) * 0.34;
    const cx = x + w / 2;
    const cy = y + h / 2;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, r * 0.05);
    ctx.beginPath();
    ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + TAU * 0.92 * clamp(p));
    ctx.stroke();
    for (let i = 0; i < stops; i += 1) {
      const a = -Math.PI / 2 + (i / stops) * TAU * 0.92;
      const shown = clamp((p - 0.2 - i * 0.10) * 3);
      if (shown <= 0) continue;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, r * 0.11 * shown, 0, TAU);
      ctx.fillStyle = i === 0 ? accent : ink;
      ctx.globalAlpha *= 0.9;
      ctx.fill();
      ctx.globalAlpha /= 0.9;
    }
  },

  'timeline-axis': (ctx, { x, y, w, h, ink, accent, p = 1, stops = 5 }) => {
    const yy = y + h * 0.55;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, h * 0.014);
    ctx.beginPath();
    ctx.moveTo(x, yy);
    ctx.lineTo(x + w * clamp(p), yy);
    ctx.stroke();
    for (let i = 0; i < stops; i += 1) {
      const t = stops === 1 ? 0.5 : i / (stops - 1);
      const shown = clamp((p - t * 0.9) * 4);
      if (shown <= 0) continue;
      const px = x + w * t;
      const up = i % 2 === 0;
      ctx.save();
      ctx.globalAlpha *= shown;
      ctx.strokeStyle = i === stops - 1 ? accent : ink;
      ctx.lineWidth = Math.max(2, h * 0.012);
      ctx.beginPath();
      ctx.moveTo(px, yy);
      ctx.lineTo(px, yy + (up ? -h * 0.22 : h * 0.22));
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(px, yy, h * 0.028, 0, TAU);
      ctx.fillStyle = i === stops - 1 ? accent : ink;
      ctx.fill();
      ctx.restore();
    }
  },

  'matrix-quadrant': (ctx, { x, y, w, h, ink, accent, p = 1, dots = 9 }) => {
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, w * 0.006);
    ctx.save();
    ctx.globalAlpha *= 0.45 * clamp(p * 2);
    ctx.beginPath();
    ctx.moveTo(x + w / 2, y); ctx.lineTo(x + w / 2, y + h);
    ctx.moveTo(x, y + h / 2); ctx.lineTo(x + w, y + h / 2);
    ctx.stroke();
    ctx.restore();
    for (let i = 0; i < dots; i += 1) {
      const shown = clamp((p - 0.3 - i * 0.05) * 3);
      if (shown <= 0) continue;
      const useAccent = i < dots / 3;
      const px = x + w * (useAccent ? 0.62 + noise(i * 2.1) * 0.34 : 0.06 + noise(i * 3.3) * 0.40);
      const py = y + h * (useAccent ? 0.08 + noise(i * 5.7) * 0.36 : 0.54 + noise(i * 7.9) * 0.38);
      ctx.beginPath();
      ctx.arc(px, py, w * 0.020 * shown, 0, TAU);
      ctx.fillStyle = useAccent ? accent : ink;
      ctx.globalAlpha *= useAccent ? 0.95 : 0.42;
      ctx.fill();
      ctx.globalAlpha /= useAccent ? 0.95 : 0.42;
    }
  },

  'decision-diamond': (ctx, { x, y, w, h, ink, accent, p = 1, branches = 2 }) => {
    const cx = x + w / 2;
    const cy = y + h / 2;
    const dw = w * 0.30;
    const dh = h * 0.34;
    path(ctx, [[cx, cy - dh], [cx + dw, cy], [cx, cy + dh], [cx - dw, cy]]);
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.006);
    ctx.stroke();
    for (let i = 0; i < branches; i += 1) {
      const shown = clamp((p - 0.3 - i * 0.15) * 3);
      if (shown <= 0) continue;
      const dir = i === 0 ? 1 : -1;
      ctx.save();
      ctx.globalAlpha *= shown;
      ctx.strokeStyle = i === 0 ? accent : ink;
      ctx.lineWidth = Math.max(2, w * 0.005);
      ctx.beginPath();
      ctx.moveTo(cx + dir * dw, cy);
      ctx.lineTo(x + (dir > 0 ? w : 0), cy + dir * h * 0.26);
      ctx.stroke();
      ctx.restore();
    }
  },

  ladder: (ctx, { x, y, w, h, ink, accent, p = 1, rungs = 5 }) => {
    const railGap = w * 0.34;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.014);
    ctx.beginPath();
    ctx.moveTo(x + (w - railGap) / 2, y + h);
    ctx.lineTo(x + (w - railGap) / 2, y);
    ctx.moveTo(x + (w + railGap) / 2, y + h);
    ctx.lineTo(x + (w + railGap) / 2, y);
    ctx.stroke();
    for (let i = 0; i < rungs; i += 1) {
      const shown = clamp((p - i * 0.08) * 3);
      if (shown <= 0) continue;
      const yy = y + h * (1 - i / rungs) - h * 0.04;
      ctx.strokeStyle = i === rungs - 1 ? accent : ink;
      ctx.lineWidth = Math.max(2, h * 0.016);
      ctx.beginPath();
      ctx.moveTo(x + (w - railGap) / 2, yy);
      ctx.lineTo(x + (w - railGap) / 2 + railGap * shown, yy);
      ctx.stroke();
    }
  },

  pyramid: (ctx, { x, y, w, h, ink, accent, p = 1, tiers = 4 }) => {
    let baseY = y + h;
    for (let i = 0; i < tiers; i += 1) {
      const shown = clamp((p - i * 0.1) * 2.6);
      if (shown <= 0) continue;
      const tierH = h / tiers;
      const topW = w * (1 - (i / tiers) * 0.86) * shown;
      const botW = w * (1 - ((i + 1) / tiers) * 0.86) * shown;
      path(ctx, [[x + (w - topW) / 2, baseY - tierH], [x + (w + topW) / 2, baseY - tierH],
        [x + (w + botW) / 2, baseY], [x + (w - botW) / 2, baseY]]);
      ctx.fillStyle = i === 0 ? accent : ink;
      ctx.globalAlpha *= 0.85 - i * 0.12;
      ctx.fill();
      ctx.globalAlpha /= 0.85 - i * 0.12;
      baseY -= tierH;
    }
  },

  venn: (ctx, { x, y, w, h, ink, accent, p = 1, sets = 2 }) => {
    const r = Math.min(w, h) * 0.30;
    const cy = y + h / 2;
    const gap = r * 0.62;
    const centres = sets === 2
      ? [[x + w / 2 - gap, cy], [x + w / 2 + gap, cy]]
      : [[x + w / 2 - gap, cy - r * 0.42], [x + w / 2 + gap, cy - r * 0.42], [x + w / 2, cy + r * 0.52]];
    centres.forEach(([cx, cyy], i) => {
      const shown = clamp((p - i * 0.12) * 2.6);
      if (shown <= 0) return;
      ctx.beginPath();
      ctx.arc(cx, cyy, r * shown, 0, TAU);
      ctx.strokeStyle = i === 0 ? accent : ink;
      ctx.lineWidth = Math.max(2, r * 0.04);
      ctx.globalAlpha *= 0.7;
      ctx.stroke();
      ctx.globalAlpha /= 0.7;
    });
  },
};

export const SHAPES = {
  ...Object.fromEntries(Object.entries(geometry).map(([id, draw]) => [id, { id, family: 'geometry', draw }])),
  ...Object.fromEntries(Object.entries(objects).map(([id, draw]) => [id, { id, family: 'object', draw }])),
  ...Object.fromEntries(Object.entries(data).map(([id, draw]) => [id, { id, family: 'data', draw }])),
  ...Object.fromEntries(Object.entries(diagrams).map(([id, draw]) => [id, { id, family: 'diagram', draw }])),
  ...Object.fromEntries(Object.entries(props).map(([id, draw]) => [id, { id, family: 'prop', draw }])),
  ...Object.fromEntries(Object.entries(charts).map(([id, draw]) => [id, { id, family: 'chart', draw }])),
};

/** Draw one shape by id into a box, with the theme colours filled in. */
export function drawShape(ctx, id, {
  x, y, w, h, p = 1, palette, params = {},
}) {
  const shape = SHAPES[id];
  if (!shape) throw new Error(`no shape called ${id}`);
  const ink = inkOf(palette, 'text', UI.text);
  const accent = inkOf(palette, 'caption', '#B4762A');
  // Geometry gets a default fill so a bare primitive is visible at all: the
  // first gallery came out as eleven empty boxes because every shape was waiting
  // for a fill the caller never passed.
  const isGeometry = shape.family === 'geometry';
  ctx.save();
  shape.draw(ctx, {
    x, y, w, h, p,
    ink,
    accent,
    colour: inkOf(palette, 'dim', UI.dim),
    fill: isGeometry ? 'rgba(18,35,63,0.14)' : null,
    stroke: isGeometry ? ink : null,
    line: Math.max(1.5, Math.min(w, h) * 0.012),
    ...params,
  });
  ctx.restore();
}

export { geometry, objects, data, diagrams, props, charts };
export default SHAPES;
