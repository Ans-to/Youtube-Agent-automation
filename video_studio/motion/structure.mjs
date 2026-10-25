/**
 * The structure layer: pictures made of shapes.
 *
 * Every template the studio had before this file was type with a plate behind
 * it. A list was rows of words, a number was a numeral, a comparison was two
 * headings. It read as a caption track with a background, which is a
 * presentation, not a designed film.
 *
 * A diagram says something type cannot: *how much*, *in what order*, *which way
 * it forks*, *what is missing*. So these templates draw the structure of the
 * sentence - a rail divided 40/10/10, a ring sweeping to 60, a fork into two
 * dead ends, a grid of three checks - and the words are labels on it, kept short,
 * never carrying the meaning on their own.
 *
 * Four rules hold across everything here, because the gates measure them:
 *
 *   - every mark is drawn inside the box it was handed, and nothing enters the
 *     caption band;
 *   - every motion is one direction, eased, and finishes; nothing shakes, spins
 *     idly or pulses;
 *   - every shape appears when its words are spoken, not on an even clock, so
 *     the structure builds in the order the narrator builds it;
 *   - every label comes from the narration. The build refuses one that does not.
 */
import { UI, clamp, span, ease, text, measure, panel, roundRect } from './ui.mjs';

const hair = (alpha = 0.16) => `rgba(18,35,63,${alpha})`;
const tint = (alpha) => `rgba(18,35,63,${alpha})`;

/** Shrink a label until it fits, never below the floor. */
function fit(ctx, value, { maxWidth, cap, floor = 16, family = 'Inter', weight = 600, tracking = 0 }) {
  let size = Math.round(cap);
  while (size > floor && measure(ctx, value, { size, weight, family, tracking }) > maxWidth) size -= 2;
  return size;
}


/** Break a label into at most `max` lines that each fit `maxWidth`. */
function wrapTo(ctx, value, { maxWidth, size, weight = 600, family = 'Inter', tracking = 0, max = 2 }) {
  const words = String(value).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (measure(ctx, next, { size, weight, family, tracking }) <= maxWidth || !line) {
      line = next;
    } else {
      lines.push(line);
      line = word;
      if (lines.length === max - 1) break;
    }
  }
  if (line && lines.length < max) lines.push(line);
  const rest = words.slice(lines.join(' ').split(/\s+/).filter(Boolean).length);
  if (rest.length) lines[lines.length - 1] += '…';
  return lines;
}

/** A label block: wrapped, fitted, never wider than its box. */
function labelBlock(ctx, value, x, y, {
  maxWidth, cap, minSize = 18, colour, align = 'center', max = 2, weight = 700,
  family = 'Space Grotesk', tracking = 1, lineGap = 1.18, alpha = 1,
}) {
  let size = Math.round(cap);
  let lines = [];
  while (size >= minSize) {
    lines = wrapTo(ctx, value, { maxWidth, size, weight, family, tracking, max });
    const widest = Math.max(...lines.map((l) => measure(ctx, l, { size, weight, family, tracking })));
    if (widest <= maxWidth && lines.length <= max) break;
    size -= 2;
  }
  if (size < minSize) return 0;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  lines.forEach((line, i) => {
    text(ctx, String(line).toUpperCase(), x, y + i * size * lineGap, {
      size, weight, family, color: colour, align, tracking,
    });
  });
  ctx.restore();
  return lines.length;
}

/** A soft slab: the unit this film's diagrams are built from. */
function slab(ctx, { x, y, w, h, r = 14, fill, stroke = null, alpha = 1 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  roundRect(ctx, x, y, w, h, r);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke(); }
  ctx.restore();
}

/** A tick mark on a rail, at a fraction of its length. */
function tick(ctx, x, y, h, { colour, alpha = 0.5 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  ctx.fillStyle = colour;
  ctx.fillRect(x, y, Math.max(2, h * 0.06), h);
  ctx.restore();
}

/** Small caps label, the way the film labels a part of a diagram. */
function label(ctx, value, x, y, { size, colour, align = 'left', tracking = 1.5, weight = 600, alpha = 1 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  text(ctx, String(value).toUpperCase(), x, y, {
    size, weight, family: 'Inter', color: colour, align, tracking,
  });
  ctx.restore();
}

/* ------------------------------------------------------------- fork paths */

/**
 * One thing splitting into two.
 *
 * Drawn as a real diagram: a source block on the left, two paths that draw
 * themselves out of it, and two terminal blocks whose shape says what the branch
 * means - one closed, one open. The labels sit at the terminals, small, because
 * the shape is the argument.
 */
function forkPaths(ctx, {
  box, local, seconds, left = '', right = '', colour = UI.white, accent = UI.gold,
}) {
  const midY = box.y + box.h * 0.50;
  const sourceW = box.w * 0.18;
  const sourceH = box.h * 0.34;
  const source = { x: box.x + box.w * 0.01, y: midY - sourceH / 2, w: sourceW, h: sourceH };
  const branchX = source.x + source.w;
  const endX = box.x + box.w * 0.58;
  const endW = box.w * 0.38;
  const endH = box.h * 0.22;
  const topY = box.y + box.h * 0.02;
  const bottomY = box.y + box.h * 0.66;
  const draw = ease.outCubic(clamp(local / Math.min(0.9, seconds * 0.4)));

  // The source: a stack of three short bars, the thing being decided about.
  slab(ctx, { ...source, r: 16, fill: tint(0.06), stroke: hair(0.2), alpha: span(local, 0, 0.22) });
  for (let i = 0; i < 3; i += 1) {
    const appear = span(local, 0.06 + i * 0.05, 0.16 + i * 0.05);
    slab(ctx, {
      x: source.x + source.w * 0.16, y: source.y + source.h * (0.24 + i * 0.2),
      w: source.w * (0.62 - i * 0.1), h: source.h * 0.09, r: 4,
      fill: colour, alpha: appear * 0.55,
    });
  }

  [0, 1].forEach((branch) => {
    const y = branch === 0 ? topY : bottomY;
    const endY = y + endH * 0.5;
    const at = 0.18 + branch * 0.16;
    const p = span(local, at, at + Math.min(0.6, seconds * 0.3));
    if (p <= 0) return;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.85;
    ctx.strokeStyle = branch === 0 ? accent : colour;
    ctx.lineWidth = Math.max(3, box.h * 0.012);
    ctx.lineCap = 'round';
    ctx.beginPath();
    const c1 = branchX + (endX - branchX) * 0.55;
    // A path, not a swoosh: it leaves the source, bends once, and lands square.
    const steps = 26;
    for (let i = 0; i <= steps; i += 1) {
      const t = (i / steps) * p;
      const x = (1 - t) * (1 - t) * branchX + 2 * (1 - t) * t * c1 + t * t * endX;
      const yy = (1 - t) * (1 - t) * midY + 2 * (1 - t) * t * (midY + (endY - midY) * 0.15) + t * t * endY;
      if (i === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
    }
    ctx.stroke();
    // The travelling marker: where the decision currently is.
    const t = p;
    const mx = (1 - t) * (1 - t) * branchX + 2 * (1 - t) * t * c1 + t * t * endX;
    const my = (1 - t) * (1 - t) * midY + 2 * (1 - t) * t * (midY + (endY - midY) * 0.15) + t * t * endY;
    ctx.globalAlpha = 1;
    ctx.fillStyle = branch === 0 ? accent : colour;
    ctx.beginPath();
    ctx.arc(mx, my, Math.max(4, box.h * 0.016), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  });

  // The two terminals. Closed on top, open below: the shapes say it before the
  // words do.
  [0, 1].forEach((branch) => {
    const y = (branch === 0 ? topY : bottomY) + endH * 0.5;
    const at = 0.45 + branch * 0.14;
    const p = span(local, at, at + Math.min(0.5, seconds * 0.26));
    if (p <= 0) return;
    const e = ease.outCubic(p);
    const x = endX + (1 - e) * box.w * 0.04;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * e;
    if (branch === 0) {
      // Closed: a solid block, shut. The tick says the branch ends here.
      slab(ctx, { x, y: y - endH / 2, w: endW, h: endH, r: 12, fill: tint(0.12), stroke: hair(0.34) });
      slab(ctx, { x: x + endW * 0.72, y: y - endH * 0.34, w: endW * 0.22, h: endH * 0.68, r: 6, fill: accent });
      ctx.save();
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = Math.max(3, endH * 0.09);
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x + endW * 0.78, y);
      ctx.lineTo(x + endW * 0.83, y + endH * 0.14);
      ctx.lineTo(x + endW * 0.92, y - endH * 0.16);
      ctx.stroke();
      ctx.restore();
    } else {
      // Open: a bracket that never closes, with the slab falling out of it.
      ctx.strokeStyle = colour;
      ctx.lineWidth = Math.max(3, box.h * 0.01);
      ctx.beginPath();
      ctx.moveTo(x, y - endH / 2);
      ctx.lineTo(x + endW * 0.08, y - endH / 2);
      ctx.moveTo(x, y + endH / 2);
      ctx.lineTo(x + endW * 0.08, y + endH / 2);
      ctx.moveTo(x, y - endH / 2);
      ctx.lineTo(x, y + endH / 2);
      ctx.stroke();
      // Open: a slab sliding out of a bracket that has stopped holding it.
      const fall = ease.outCubic(clamp((local - at) / 0.6));
      slab(ctx, {
        x: x + endW * 0.10 + fall * endW * 0.16, y: y - endH * 0.28,
        w: endW * 0.34, h: endH * 0.56, r: 10, fill: tint(0.08), stroke: hair(0.3),
      });
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * 0.7;
      ctx.strokeStyle = colour;
      ctx.lineWidth = Math.max(3, endH * 0.06);
      ctx.beginPath();
      ctx.moveTo(x + endW * 0.52, y);
      ctx.lineTo(x + endW * 0.92, y);
      ctx.moveTo(x + endW * 0.84, y - endH * 0.10);
      ctx.lineTo(x + endW * 0.92, y);
      ctx.lineTo(x + endW * 0.84, y + endH * 0.10);
      ctx.stroke();
      ctx.restore();
    }
    const value = branch === 0 ? left : right;
    // The label sits under the terminal, not inside it: a terminal block that
    // has to grow to hold a sentence stops being a terminal block.
    labelBlock(ctx, value, x + endW * 0.5, y + endH * 0.5 + box.h * 0.13, {
      maxWidth: endW * 0.96, cap: box.h * 0.115, minSize: 22, colour, align: 'center', max: 2,
    });
    ctx.restore();
  });
}

/* ------------------------------------------------------------- matrix grid */

/**
 * Two to four things, as a grid of tiles that fills in the spoken order.
 *
 * Each tile carries a number, a drawn glyph and a short label. The connector
 * draws between tiles as they arrive, so the beat is a structure being built,
 * not a list being read out.
 */
function matrixGrid(ctx, {
  box, local, seconds, items = [], slots, colour = UI.white, accent = UI.gold,
}) {
  const rows = items.map((item) => (typeof item === 'string' ? { name: item } : item));
  if (!rows.length) return;
  const count = Math.max(rows.length, Number(slots) || 0);
  const columns = count <= 3 ? count : 2;
  const gridRows = Math.ceil(count / columns);
  const gapX = box.w * 0.035;
  const gapY = box.h * 0.10;
  const tileW = (box.w - gapX * (columns - 1)) / columns;
  // Tiles are a card, not a wall: capped in height and centred in the region, so
  // a wide region gives a row of tiles with air around them rather than three
  // tall empty panels.
  const tileH = Math.min((box.h - gapY * (gridRows - 1)) / gridRows, box.h * 0.62);
  const top = box.y + (box.h - (tileH * gridRows + gapY * (gridRows - 1))) / 2;
  const positions = rows.map((row, i) => ({
    x: box.x + (i % columns) * (tileW + gapX),
    y: top + Math.floor(i / columns) * (tileH + gapY),
  }));

  // The spine: a hairline that draws under the grid as the tiles land.
  const spineP = ease.outCubic(clamp(local / Math.min(1.0, seconds * 0.5)));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.5;
  ctx.fillStyle = hair(0.5);
  ctx.fillRect(box.x, top + tileH * gridRows + gapY * 0.4, box.w * spineP, Math.max(2, box.h * 0.008));
  ctx.restore();

  rows.forEach((row, i) => {
    const at = typeof row.at === 'number' ? row.at : (seconds * 0.55) * (i / Math.max(count, 1));
    const p = span(local, at, at + Math.min(0.5, seconds * 0.24));
    if (p <= 0) return;
    const e = ease.outCubic(p);
    const { x, y } = positions[i];
    const lift = (1 - e) * tileH * 0.22;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 1.6);
    slab(ctx, {
      x, y: y + lift, w: tileW, h: tileH, r: 18,
      fill: i === rows.length - 1 ? 'rgba(180,118,42,0.12)' : 'rgba(255,255,255,0.55)',
      stroke: i === rows.length - 1 ? accent : hair(0.22),
    });
    // The number chip, set in the corner like a plate number.
    const chip = Math.min(tileW, tileH) * 0.20;
    slab(ctx, {
      x: x + tileW * 0.06, y: y + lift + tileH * 0.10, w: chip, h: chip, r: 6,
      fill: accent, alpha: 0.9,
    });
    text(ctx, String(i + 1).padStart(2, '0'), x + tileW * 0.06 + chip / 2, y + lift + tileH * 0.10 + chip * 0.72, {
      size: Math.round(chip * 0.62), weight: 700, family: 'Space Grotesk', color: '#FFFFFF', align: 'center',
    });
    // The glyph: three different figures, one per tile, drawn as progress.
    const gx = x + tileW * 0.84;
    const gy = y + lift + tileH * 0.82;
    const gr = Math.min(tileW, tileH) * 0.11;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp((p - 0.15) / 0.7);
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(3, gr * 0.3);
    ctx.beginPath();
    if (i % 3 === 0) {
      // A segment of a ring: a check without a tick mark.
      ctx.arc(gx, gy, gr, -Math.PI * 0.5, -Math.PI * 0.5 + Math.PI * 1.2);
    } else if (i % 3 === 1) {
      // Three rising bars: run it.
      ctx.stroke();
      for (let b = 0; b < 3; b += 1) {
        const bh = gr * (0.8 + b * 0.5);
        ctx.fillStyle = accent;
        ctx.fillRect(gx - gr + b * gr * 0.8, gy + gr - bh, gr * 0.36, bh);
      }
      ctx.beginPath();
    } else {
      // A chevron into a bracket: ask what it refuses.
      ctx.moveTo(gx - gr, gy - gr * 0.7);
      ctx.lineTo(gx, gy);
      ctx.lineTo(gx - gr, gy + gr * 0.7);
    }
    ctx.stroke();
    ctx.restore();

    const value = row.name ?? row.text ?? '';
    labelBlock(ctx, value, x + tileW * 0.06, y + lift + tileH * 0.46, {
      maxWidth: tileW * 0.86, cap: tileH * 0.155, minSize: 20, colour, align: 'left', max: 3,
      lineGap: 1.10,
    });
    ctx.restore();
  });

  // Connectors: one short rule between each pair that has landed.
  for (let i = 1; i < rows.length; i += 1) {
    const prev = positions[i - 1];
    const next = positions[i];
    const at = typeof rows[i].at === 'number' ? rows[i].at : 0;
    const p = span(local, at, at + 0.35);
    if (p <= 0) continue;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * p * 0.7;
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, box.h * 0.006);
    ctx.beginPath();
    if (prev.y === next.y) {
      ctx.moveTo(prev.x + tileW + 4, prev.y + tileH * 0.5);
      ctx.lineTo(prev.x + tileW + 4 + (next.x - prev.x - tileW - 8) * p, next.y + tileH * 0.5);
    } else {
      ctx.moveTo(prev.x + tileW * 0.5, prev.y + tileH + 3);
      ctx.lineTo(next.x + tileW * 0.5, prev.y + tileH + 3 + (next.y - prev.y - tileH) * p);
    }
    ctx.stroke();
    ctx.restore();
  }
}

/* -------------------------------------------------------------- ring gauge */

/**
 * One figure, drawn as a measured ring.
 *
 * The numeral is inside a dial with ticks around it, and the dial sweeps to the
 * figure while the number counts. The unit is set as a label on the ring, not as
 * another headline, so a number reads as a measurement rather than a claim.
 */
function ringGauge(ctx, {
  box, local, seconds, value = 60, label: unit = '', text: big = null,
  colour = UI.white, accent = UI.gold,
}) {
  const cx = box.x + box.w * 0.50;
  const cy = box.y + box.h * 0.52;
  // The dial plus its ticks and scale has to fit the region height: 0.36 of the
  // box radius, ticks at 1.08, scale at 1.18 - 0.85 of the box, inside it.
  const r = Math.min(box.h * 0.36, box.w * 0.22);
  const sweep = ease.outCubic(clamp(local / Math.min(seconds * 0.7, 1.6)));

  // Ticks: sixty of them, so the ring reads as a measure and not an ornament.
  const ticks = 60;
  for (let i = 0; i < ticks; i += 1) {
    const on = i / ticks <= sweep;
    const a = -Math.PI * 0.5 + (i / ticks) * Math.PI * 2;
    const len = i % 5 === 0 ? r * 0.10 : r * 0.055;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (on ? 0.9 : 0.28);
    ctx.fillStyle = i % 5 === 0 && on ? accent : colour;
    ctx.translate(cx + Math.cos(a) * (r + r * 0.10), cy + Math.sin(a) * (r + r * 0.10));
    ctx.rotate(a + Math.PI / 2);
    ctx.fillRect(-1.5, -len, Math.max(2, r * 0.018), len);
    ctx.restore();
  }

  // The arc that fills as the count runs.
  ctx.save();
  ctx.strokeStyle = accent;
  ctx.lineWidth = Math.max(8, r * 0.075);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(cx, cy, r, -Math.PI * 0.5, -Math.PI * 0.5 + Math.PI * 2 * sweep);
  ctx.stroke();
  ctx.restore();

  // A thin inner ring, drawn just behind the number, for depth without noise.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.5;
  ctx.strokeStyle = hair(0.3);
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.74, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  const counted = Math.round(value * sweep);
  const numberSize = Math.round(r * 0.62);
  text(ctx, String(counted), cx, cy + numberSize * 0.32, {
    size: numberSize, weight: 700, family: 'Space Grotesk', color: colour, align: 'center', tracking: 0,
  });
  if (unit) {
    label(ctx, unit, cx, cy + r * 0.62, {
      size: Math.round(r * 0.15), colour: accent, align: 'center', tracking: 4, alpha: clamp(sweep * 1.4),
    });
  }

  // The scale, written around the dial: zero, half, full. A gauge without a scale
  // is an ornament; the three numbers are what make it a measurement.
  [[0, '0'], [0.5, String(Math.round(value / 2))], [1, String(value)]].forEach(([fraction, text0]) => {
    const a = -Math.PI * 0.5 + Math.PI * 2 * fraction;
    const rr = r + r * 0.18;
    const on = sweep >= fraction - 0.02;
    label(ctx, text0, cx + Math.cos(a) * rr, cy + Math.sin(a) * rr + r * 0.05, {
      size: Math.round(r * 0.13), colour: on ? accent : tint(0.45), align: 'center', tracking: 1,
      alpha: on ? 0.95 : 0.6,
    });
  });

  // The reading, as a line of text under the dial rather than a second chart:
  // the beat is one measurement, and one measurement is one picture.
  if (big) {
    labelBlock(ctx, big, box.x + box.w * 0.5, cy + r * 0.96, {
      maxWidth: box.w * 0.5, cap: box.h * 0.12, minSize: 22, colour, align: 'center', max: 1,
    });
  }
}

/* -------------------------------------------------------------- budget rail */

/**
 * A span of time, divided.
 *
 * The rail is the whole budget; each segment is the part of it a step takes, and
 * the segments arrive as their sentences are spoken. A playhead sweeps across at
 * the speed of the film, so the rail is also the progress of the section.
 */
function budgetRail(ctx, {
  box, local, seconds, segments = [], total = null, colour = UI.white, accent = UI.gold,
}) {
  const rows = segments.map((item) => (typeof item === 'object' ? item : { label: '', value: Number(item) }));
  if (!rows.length) return;
  const sum = rows.reduce((acc, row) => acc + (Number(row.value) || 0), 0) || 1;
  const scale = Number(total) || sum;
  const railY = box.y + box.h * 0.56;
  const railH = box.h * 0.26;
  const x0 = box.x;
  const usable = box.w * 0.94;

  // Baseline and ticks: the measure the blocks sit on.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.55;
  ctx.fillStyle = hair(0.45);
  ctx.fillRect(x0, railY + railH + box.h * 0.03, usable, Math.max(2, box.h * 0.006));
  ctx.restore();
  const steps = 12;
  for (let i = 0; i <= steps; i += 1) {
    const x = x0 + (usable * i) / steps;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.5;
    ctx.fillStyle = hair(0.5);
    ctx.fillRect(x, railY + railH + box.h * 0.03, 2, box.h * (i % 3 === 0 ? 0.05 : 0.028));
    ctx.restore();
  }

  let cursor = x0;
  let lastAt = 0;
  rows.forEach((row, i) => {
    const width = (usable * (Number(row.value) || 0)) / scale;
    const at = typeof row.at === 'number' ? row.at : 0;
    lastAt = at;
    const p = span(local, at, at + Math.min(0.55, Math.max(0.3, (seconds * 0.6) / rows.length)));
    if (p <= 0) { cursor += width; return; }
    const e = ease.outCubic(p);
    const h = railH * (0.72 + (i % 2) * 0.24);
    const y = railY + railH - h;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2.2);
    // Grown from the left: the block takes its part of the rail.
    slab(ctx, {
      x: cursor, y, w: Math.max(4, width * e), h, r: 10,
      fill: i === 0 ? accent : tint(0.30 + Math.min(0.34, (i - 1) * 0.12)),
      alpha: i === 0 ? 0.92 : 1,
    });
    const value = Math.round(Number(row.value) || 0);
    text(ctx, String(value), cursor + width * 0.5, y - box.h * 0.055, {
      size: Math.round(Math.min(box.h * 0.13, width * 0.42)), weight: 700, family: 'Space Grotesk',
      color: colour, align: 'center',
    });
    // A label only goes on the rail if it fits its own segment. A ten-second
    // segment on a sixty-second rail is a sixth of the width: "Ten seconds
    // running it" is four times too long for it, and squeezing it in prints a
    // second, unreadable copy of the sentence the caption is already saying. The
    // rail's job is proportion; the words belong to the band.
    // A label only goes on the rail if its segment can hold it. A ten-second
    // segment on a sixty-second rail is a sixth of the width; "Ten seconds
    // running it" is four times too long for that, and squeezing it in prints a
    // second, unreadable copy of the sentence the caption is already saying. The
    // rail's job is proportion; the words belong to the band.
    if (row.label && width > box.w * 0.22) {
      labelBlock(ctx, row.label, cursor + width * 0.02, railY + railH + box.h * 0.18, {
        maxWidth: width * 0.92, cap: box.h * 0.095, minSize: 20, colour: tint(0.72),
        align: 'left', max: 2, weight: 600, family: 'Inter', lineGap: 1.15,
      });
    }
    ctx.restore();
    cursor += width;
  });

  // The playhead: where the film is on the rail right now.
  const playX = x0 + usable * clamp(local / Math.max(0.001, seconds));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.9;
  ctx.fillStyle = colour;
  ctx.fillRect(playX - 1.5, railY - box.h * 0.10, 3, railH + box.h * 0.18);
  ctx.beginPath();
  ctx.arc(playX, railY - box.h * 0.10, box.h * 0.022, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/* ----------------------------------------------------------- command console */

/**
 * A command, run.
 *
 * The command types into a console with a frame around it, and the frame carries
 * the result: a row of check blocks that fill one by one as the run proceeds.
 * The window is the structure; the command is the label on it.
 */
function commandConsole(ctx, {
  box, local, seconds, lines = [], colour = UI.white, accent = UI.gold,
}) {
  if (!lines.length) return;
  const win = {
    x: box.x, y: box.y + box.h * 0.06,
    w: box.w * 0.92, h: Math.min(box.h * 0.6, box.h - box.h * 0.06),
  };
  const appear = ease.outCubic(clamp(local / 0.4));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * appear;
  panel(ctx, {
    x: win.x, y: win.y, w: win.w, h: win.h, r: 22,
    fill: 'rgba(255,255,255,0.82)', stroke: hair(0.28),
  });
  // Title bar with three dots: the window is a device the viewer recognises, and
  // it says "this is running" without a word.
  ctx.fillStyle = hair(0.12);
  ctx.fillRect(win.x, win.y, win.w, win.h * 0.18);
  ['#C4553B', '#C99A33', '#3F7F5A'].forEach((dot, i) => {
    ctx.fillStyle = dot;
    ctx.globalAlpha = 0.8 * appear;
    ctx.beginPath();
    ctx.arc(win.x + win.w * (0.035 + i * 0.028), win.y + win.h * 0.09, win.h * 0.028, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = appear;
  ctx.restore();

  // The command, typed.
  const command = String(lines[0]);
  const typedP = clamp((local - 0.18) / Math.max(0.4, Math.min(1.4, seconds * 0.45)));
  const typed = Math.floor(command.length * ease.outCubic(typedP));
  const shown = command.slice(0, typed);
  const size = fit(ctx, command, { maxWidth: win.w * 0.8, cap: win.h * 0.2, floor: 20, family: 'Inter', weight: 600 });
  const baseY = win.y + win.h * 0.52;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * clamp(typedP * 3);
  // The prompt: a chevron, drawn as a shape rather than a typed character.
  ctx.strokeStyle = accent;
  ctx.lineWidth = Math.max(3, size * 0.1);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(win.x + win.w * 0.06, baseY - size * 0.42);
  ctx.lineTo(win.x + win.w * 0.06 + size * 0.3, baseY - size * 0.22);
  ctx.lineTo(win.x + win.w * 0.06, baseY - size * 0.02);
  ctx.stroke();
  text(ctx, shown, win.x + win.w * 0.06 + size * 0.55, baseY, {
    size, weight: 600, family: 'Inter', color: colour,
  });
  if (typed < command.length || Math.floor(local * 3) % 2 === 0) {
    const caretX = win.x + win.w * 0.06 + size * 0.55
      + measure(ctx, shown, { size, weight: 600, family: 'Inter' }) + size * 0.08;
    ctx.fillStyle = accent;
    ctx.fillRect(caretX, baseY - size * 0.8, Math.max(3, size * 0.08), size);
  }
  ctx.restore();

  // The run: check blocks filling along the base of the window.
  const blocks = 6;
  const runStart = 0.55;
  const blockY = win.y + win.h * 0.74;
  const bw = (win.w * 0.86) / blocks;
  for (let i = 0; i < blocks; i += 1) {
    const at = runStart + (i / blocks) * Math.max(0.5, seconds * 0.34);
    const p = span(local, at, at + 0.22);
    const done = p > 0;
    slab(ctx, {
      x: win.x + win.w * 0.07 + i * bw, y: blockY, w: bw * 0.86, h: win.h * 0.135, r: 6,
      fill: done ? accent : tint(0.08), stroke: done ? null : hair(0.25), alpha: done ? 0.9 : 1,
    });
    if (done) {
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * p;
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = Math.max(2, win.h * 0.012);
      ctx.lineCap = 'round';
      ctx.beginPath();
      const cx = win.x + win.w * 0.07 + i * bw + bw * 0.43;
      const cy = blockY + win.h * 0.05;
      ctx.moveTo(cx - bw * 0.12, cy);
      ctx.lineTo(cx - bw * 0.02, cy + bw * 0.12);
      ctx.lineTo(cx + bw * 0.16, cy - bw * 0.12);
      ctx.stroke();
      ctx.restore();
    }
  }
}

/* --------------------------------------------------------------- registration */

/**
 * The structure templates, in the library's own format.
 *
 * They are registered beside the type templates, so a brief chooses between
 * them by situation and the chooser scores them the same way. Nothing here
 * overrides the library's contract: same props discipline, same duration bands,
 * same regions.
 */
export const STRUCTURES = [
  {
    id: 'fork-paths',
    name: 'Fork paths',
    purpose: 'One thing splitting into two outcomes, drawn as a source and two branches.',
    when: ['make-a-comparison', 'state-the-thesis', 'before-and-after'],
    avoid: [
      'Two things that do not come from the same source: the fork would be a lie.',
      'More than two branches: it becomes spaghetti.',
    ],
    minSeconds: 2.5,
    maxSeconds: 8.0,
    needs: ['left', 'right'],
    regions: ['spread', 'split', 'stage'],
    cost: 'medium',
    sample: { left: 'Rubber stamp', right: 'Rewrite the whole thing' },
    draw: forkPaths,
  },
  {
    id: 'matrix-grid',
    name: 'Matrix grid',
    purpose: 'Two to four things as tiles that fill in the order they are spoken.',
    when: ['show-a-sequence', 'show-criteria', 'recap', 'build-an-argument'],
    avoid: [
      'One item: that is a headline, not a grid.',
      'Five or more: the labels stop being readable at a glance.',
    ],
    minSeconds: 2.0,
    maxSeconds: 9.0,
    needs: ['items'],
    regions: ['wide', 'spread', 'stage', 'split'],
    cost: 'medium',
    sample: { items: ['Read the diff, not the summary', 'Run it once yourself', 'Ask what it does not handle'] },
    draw: matrixGrid,
  },
  {
    id: 'ring-gauge',
    name: 'Ring gauge',
    purpose: 'A claimed number as a dial that sweeps to it, with the unit on the ring.',
    when: ['explain-a-number', 'name-the-thing'],
    avoid: [
      'A number the narration does not say: the dial would be decoration.',
      'Two numbers on one beat: one dial, one figure.',
    ],
    minSeconds: 2.0,
    maxSeconds: 7.0,
    needs: ['value'],
    regions: ['spread', 'wide', 'stage', 'hero', 'split'],
    cost: 'low',
    sample: { value: 60, label: 'Seconds' },
    draw: ringGauge,
  },
  {
    id: 'budget-rail',
    name: 'Budget rail',
    purpose: 'A span of time divided into the parts the narration says it is spent on.',
    when: ['show-the-mechanism', 'explain-a-number', 'show-a-sequence'],
    avoid: [
      'Parts that do not sum to the whole being explained.',
      'More than four segments: the labels collide on the rail.',
    ],
    minSeconds: 3.0,
    maxSeconds: 10.0,
    needs: ['segments'],
    regions: ['wide', 'spread', 'split', 'stage'],
    cost: 'low',
    sample: { segments: [{ label: 'Forty seconds reading the diff', value: 40 }, { label: 'Ten seconds running it', value: 10 }, { label: 'Ten seconds asking what it refuses', value: 10 }], total: 60 },
    draw: budgetRail,
  },
  {
    id: 'command-console',
    name: 'Command console',
    purpose: 'A window that types one command and shows the run finishing, block by block.',
    when: ['show-the-command', 'show-the-mechanism'],
    avoid: [
      'More than one command: the window holds one line.',
      'Code the film does not otherwise mention.',
    ],
    minSeconds: 2.5,
    maxSeconds: 7.0,
    needs: ['lines'],
    regions: ['wide', 'spread', 'stage', 'split'],
    cost: 'medium',
    sample: { lines: ['npm test'] },
    draw: commandConsole,
  },
];
