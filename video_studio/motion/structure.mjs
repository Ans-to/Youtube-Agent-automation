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

/** Solid greys, mixed against the light field, for shapes that must stay opaque. */
const SOLID = {
  ink35: '#B9C2CC',
  ink70: '#78848F',
  paper: 'rgba(255,255,255,0.9)',
};

const hair = (alpha = 0.16) => `rgba(18,35,63,${alpha})`;

/**
 * A colour, as an rgba string, mixed toward paper by `lighten` (0 = the colour
 * itself, 1 = white). The terminals in a fork are the one place in this film
 * where a diagram carries a verdict, and a verdict drawn as a grey wash is a
 * verdict nobody reads: "Green means merge" was printed beside a colourless box.
 */
function mixToWhite(hex, lighten, alpha = 1) {
  const text = String(hex || '#78848F').replace('#', '');
  const full = text.length === 3 ? text.split('').map((c) => c + c).join('') : text;
  const parts = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  const mixed = parts.map((value) => Math.round(value + (255 - value) * lighten));
  return `rgba(${mixed.join(',')},${alpha})`;
}
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
    text(ctx, String(line), x, y + i * size * lineGap, {
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
  leftColour = null, rightColour = null,
}) {
  const midY = box.y + box.h * 0.50;
  const sourceW = box.w * 0.18;
  const sourceH = box.h * 0.34;
  const source = { x: box.x + box.w * 0.01, y: midY - sourceH / 2, w: sourceW, h: sourceH };
  const branchX = source.x + source.w;
  const endX = box.x + box.w * 0.58;
  const endW = box.w * 0.38;
  const endH = box.h * 0.22;
  const topY = box.y + box.h * 0.06;
  const bottomY = box.y + box.h * 0.62;
  const draw = ease.outCubic(clamp(local / Math.min(0.9, seconds * 0.4)));

  // The source: a diamond with the two branch edges leaving its points. A
  // rounded box says "card"; a diamond says "a decision is made here", which is
  // what the sentence is about, and it is what makes the drawing read as a
  // diagram rather than as two labels with a line between them.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * span(local, 0, 0.24);
  const dw = source.w * 0.52;
  const dh = source.h * 0.58;
  const dcx = source.x + source.w * 0.5;
  ctx.beginPath();
  ctx.moveTo(dcx - dw, midY);
  ctx.lineTo(dcx, midY - dh);
  ctx.lineTo(dcx + dw, midY);
  ctx.lineTo(dcx, midY + dh);
  ctx.closePath();
  ctx.fillStyle = tint(0.08);
  ctx.fill();
  ctx.strokeStyle = hair(0.4);
  ctx.lineWidth = Math.max(2, box.h * 0.006);
  ctx.stroke();
  // Three bars inside it: the diff being decided about.
  ctx.fillStyle = colour;
  for (let i = 0; i < 3; i += 1) {
    ctx.globalAlpha = ctx.globalAlpha * 0;
  }
  ctx.restore();
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * span(local, 0.06, 0.30);
  ctx.fillStyle = colour;
  for (let i = 0; i < 3; i += 1) {
    const w = dw * (0.9 - i * 0.2);
    ctx.globalAlpha = ctx.globalAlpha;
    ctx.fillRect(dcx - w / 2, midY - dh * 0.42 + i * dh * 0.30, w, Math.max(2, dh * 0.10));
  }
  ctx.restore();

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
    const terminal = branch === 0 ? (leftColour || accent) : (rightColour || colour);
    if (branch === 0) {
      // Closed: a solid plate in the verdict's own colour, shut. The tint is the
      // colour, not a grey wash: the sentence says "green means merge" and the
      // picture has to be green, or the words are doing all the work.
      slab(ctx, { x, y: y - endH / 2, w: endW, h: endH, r: 12,
        fill: mixToWhite(terminal, 0.78), stroke: mixToWhite(terminal, 0.30) });
      slab(ctx, { x: x + endW * 0.72, y: y - endH * 0.34, w: endW * 0.22, h: endH * 0.68, r: 6,
        fill: terminal });
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
        w: endW * 0.34, h: endH * 0.56, r: 10,
        fill: mixToWhite(terminal, 0.80), stroke: mixToWhite(terminal, 0.34),
      });
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * 0.7;
      ctx.strokeStyle = terminal;
      ctx.lineWidth = Math.max(3, endH * 0.06);
      // The arrow is drawn on the plate that is falling out of the bracket, so it
      // never runs off the end of the terminal and into the background.
      const ax = x + endW * 0.10 + fall * endW * 0.16;
      ctx.beginPath();
      ctx.moveTo(ax + endW * 0.12, y);
      ctx.lineTo(ax + endW * 0.30, y);
      ctx.moveTo(ax + endW * 0.24, y - endH * 0.10);
      ctx.lineTo(ax + endW * 0.30, y);
      ctx.lineTo(ax + endW * 0.24, y + endH * 0.10);
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
  tile: tileColour,
}) {
  const tile = tileColour || 'rgba(255,255,255,0.55)';
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
  // Tiles fill most of the region's height. At 62% of it, a three-column row on a
  // 1080p frame left the cards 228 px tall with 35 px labels - readable on a
  // monitor, a caption-sized blur on a phone. The cards are the picture; let them
  // be the picture.
  const tileH = Math.min((box.h - gapY * (gridRows - 1)) / gridRows, box.h * 0.76);
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

  // Which tile the narration is on. The grid is not three equal cards: the tile
  // being spoken is lifted and inked, the ones already spoken have stepped back,
  // and the ones not yet said are waiting. That focus shift is what makes a
  // three-second hold on a grid still be a new arrangement every second.
  let active = 0;
  rows.forEach((row, i) => {
    const at = typeof row.at === 'number' ? row.at : (seconds * 0.55) * (i / Math.max(count, 1));
    if (local >= at) active = i;
  });
  rows.forEach((row, i) => {
    const at = typeof row.at === 'number' ? row.at : (seconds * 0.55) * (i / Math.max(count, 1));
    const p = Math.min(1, span(local, at, at + Math.min(0.5, seconds * 0.24)));
    if (p <= 0) return;
    const e = ease.outCubic(p);
    const { x, y } = positions[i];
    const lift = (1 - e) * tileH * 0.22;
    // Spoken tiles stay at full strength - a recap is three things, not one
    // thing and two ghosts. The tile being spoken is the one that takes the
    // accent, and it hands the accent on as the narration moves.
    const focus = i === active ? 1 : 0.9;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 1.6) * focus;
    slab(ctx, {
      x, y: y + lift, w: tileW, h: tileH, r: 18,
      fill: i === active ? 'rgba(180,118,42,0.14)' : tile,
      stroke: i === active ? accent : hair(0.22),
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
      maxWidth: tileW * 0.84, cap: tileH * 0.18, minSize: 20, colour, align: 'left', max: 3,
      lineGap: 1.08,
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
  const cy = box.y + box.h * 0.48;
  // The dial plus its ticks and scale has to fit the region height: 0.36 of the
  // box radius, ticks at 1.08, scale at 1.18 - 0.85 of the box, inside it.
  // The whole gauge, including the scale numbers outside the ticks, spans about
  // 2.9r vertically, so r is bounded by the *region height* - and the self-check
  // fails the template if its ink leaves the region, which is what caught this
  // when the number sizes were raised.
  const r = Math.min(box.h * 0.325, box.w * 0.22);
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

  // The scale, written around the dial: half and full.
  //
  // There used to be three labels, and the first one was printed on top of the
  // last: a full turn starts and ends at the top of the ring, so "0" and "60"
  // landed in the same place as two illegible specks. What is left is the two
  // number a viewer can actually use - halfway, and the whole - set at a size
  // that survives being scaled down to a phone.
  // The scale numbers sit clear of the ticks. At r*1.20 they were printed on top
  // of them - a "60" over the top of the ring is a smudge, not a measurement.
  [[0.5, String(Math.round(value / 2))], [1, String(value)]].forEach(([fraction, text0]) => {
    const a = -Math.PI * 0.5 + Math.PI * 2 * fraction;
    const rr = r + r * 0.34;
    const on = sweep >= fraction - 0.02;
    label(ctx, text0, cx + Math.cos(a) * rr, cy + Math.sin(a) * rr + r * 0.06, {
      size: Math.round(r * 0.17), colour: on ? accent : tint(0.45), align: 'center', tracking: 1,
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
  // The rail sits above the middle of its region, not below it: at 56% of the
  // height the bar left a third of the frame empty above it and the whole picture
  // read as low and unbalanced. The room that frees up is not left empty - it
  // carries the dimension line, which is what turns a bar into a measurement.
  const railY = box.y + box.h * 0.40;
  const railH = box.h * 0.30;
  const x0 = box.x;
  const usable = box.w * 0.94;

  // The spent band: a low, wide wash behind the rail that fills from the left as
  // the section runs. It is the one thing on this picture that changes over a
  // large area at speech pace, and it says what the section is about - how much
  // of the minute has been spent by the time the narrator has finished talking.
  // Without it the rail is a static bar with a thin playhead, and the arrangement
  // measurement read the whole chapter as one held composition.
  const spent = clamp(local / Math.max(0.001, seconds));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.30;
  const spentGrad = ctx.createLinearGradient(x0, 0, x0 + usable, 0);
  spentGrad.addColorStop(0, 'rgba(180,118,42,0.20)');
  spentGrad.addColorStop(1, 'rgba(180,118,42,0.02)');
  ctx.fillStyle = spentGrad;
  ctx.fillRect(x0, railY - box.h * 0.12, usable * spent, railH + box.h * 0.24);
  ctx.restore();

  // The dimension: a line across the whole span with an end cap at each end and
  // the total set on it. A division of a minute only means something if the
  // minute itself is drawn, so the rail now has a header that states the whole.
  const dimY = box.y + box.h * 0.16;
  const dimP = ease.outCubic(clamp(local / 0.5));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.9 * dimP;
  ctx.fillStyle = hair(0.55);
  ctx.fillRect(x0, dimY, usable * dimP, Math.max(2, box.h * 0.004));
  [0, 1].forEach((end) => {
    const x = x0 + usable * end * dimP;
    ctx.fillRect(Math.min(x, x0 + usable * dimP), dimY - box.h * 0.035, Math.max(2, box.h * 0.006),
      box.h * 0.07);
  });
  ctx.restore();
  if (scale) {
    // Left end of the dimension, not the middle: the readout below it is the big
    // figure, and the two collided when the whole were set centred over the rail.
    labelBlock(ctx, `${Math.round(scale)} seconds, all in`, x0, box.y + box.h * 0.12, {
      maxWidth: usable * 0.34, cap: box.h * 0.092, minSize: 16, colour: tint(0.80),
      align: 'left', max: 1, weight: 600, family: 'Inter', lineGap: 1.1, alpha: dimP,
    });
  }

  // Baseline and ticks: the measure the blocks sit on.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.55;
  ctx.fillStyle = hair(0.45);
  ctx.fillRect(x0, railY + railH + box.h * 0.03, usable, Math.max(2, box.h * 0.006));
  ctx.restore();
  // The scale: one tick per second of the whole the rail divides.
  //
  // It was twelve coarse ticks, which said "there are some divisions" and nothing
  // more. Sixty ticks say the actual thing - this is a minute, and it is being
  // spent - and the ticks fill behind the playhead, so the picture keeps changing
  // every second without anything moving in and out. A gauge needs a scale; a
  // caption does not need to be drawn on top of one.
  const ticks = Math.max(8, Math.round(scale));
  const played = clamp(local / Math.max(0.001, seconds));
  for (let i = 0; i <= ticks; i += 1) {
    const x = x0 + (usable * i) / ticks;
    const major = i % Math.max(1, Math.round(ticks / 6)) === 0;
    const filled = i / ticks <= played;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (filled ? 0.85 : 0.30);
    ctx.fillStyle = filled ? accent : hair(0.5);
    ctx.fillRect(x, railY + railH + box.h * 0.03, 2,
      box.h * (major ? 0.055 : 0.030));
    ctx.restore();
  }

  let cursor = x0;
  let lastAt = 0;
  let activeIndex = 0;
  const lastCentres = [];
  // When the brief does not say when each part of the minute is discussed, the
  // parts arrive in order across the first two thirds of the section - the same
  // convention the grid uses. Without this every segment carried `at: 0`, so the
  // rail finished building in the first second and then held one arrangement for
  // seven, which the composition measurement reports as a held composition.
  const rowAts = rows.map((row, i) => (typeof row.at === 'number' ? row.at
    : (seconds * 0.62) * (i / Math.max(1, rows.length - 1))));
  rowAts.forEach((at, i) => {
    if (local >= at) activeIndex = i;
  });
  rows.forEach((row, i) => {
    const width = (usable * (Number(row.value) || 0)) / scale;
    const at = rowAts[i];
    lastAt = at;
    const p = Math.min(1, span(local, at, at + Math.min(0.55, Math.max(0.3, (seconds * 0.6) / rows.length))));
    if (p <= 0) { cursor += width; return; }
    const e = ease.outCubic(p);
    // The segment being spoken is the tallest thing on the rail; the others sit
    // back. Listening to the narration and watching the bar agree is the point.
    const nextAt = i + 1 < rowAts.length ? rowAts[i + 1] : Infinity;
    const isActive = local >= at && local < nextAt;
    const h = railH * (isActive ? 1.0 : 0.68);
    const y = railY + railH - h;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2.2);
    // Grown from the left: the block takes its part of the rail. Spoken
    // segments are the accent and unspoken ones are a grey outline, so the rail
    // reads as how far the minute has been spent, as well as how it is divided.
    // The biggest share keeps the accent - it is what the sentence is about -
    // and the segment being spoken is inked in, so the rail reads as a division
    // of the minute and as where the narration has got to, without either one
    // washing the other out.
    slab(ctx, {
      x: cursor, y, w: Math.max(4, width * e), h, r: 10,
      fill: i === 0 ? accent : (isActive ? SOLID.ink70 : SOLID.ink35),
      alpha: 1,
    });
    // The value is not printed over its own segment any more. Three numbers on a
    // rail a sixth of a segment wide either collide ("10 10" reads as "1010") or
    // have to shrink to a whisper; the figure is drawn once, large, above
    // whichever segment the narrator is on. That readout also gives the picture
    // its arrangement change: the number is 120 px tall and it steps across the
    // rail every time the narration moves on.
    lastCentres[i] = cursor + width * 0.5;
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
      // Inked, not tinted: this label sits over whatever the frame's light is
      // doing, and a 72% grey over a passing shadow is unreadable.
      labelBlock(ctx, row.label, cursor + width * 0.02, railY + railH + box.h * 0.18, {
        maxWidth: width * 0.92, cap: box.h * 0.095, minSize: 20, colour,
        align: 'left', max: 2, weight: 600, family: 'Inter', lineGap: 1.15,
      });
    }
    ctx.restore();
    cursor += width;
  });

  // The readout. One figure, set large, over the segment the sentence is on: it
  // steps from the forty to the first ten to the second ten, so the number the
  // narrator is saying is the biggest object on the frame, and the arrangement
  // changes whenever the argument moves rather than when a decoration does.
  const readoutIndex = Math.min(activeIndex, Math.max(0, lastCentres.length - 1));
  if (lastCentres.length) {
    // Anchored at the right end of the rail, clear of the dimension's own label on
    // the left. The figure is what changes, not its position - and a number that
    // swaps under the sentence is a cleaner event than one that slides about.
    const rx = x0 + usable;
    const size = Math.round(box.h * 0.155);
    // The figure, and the part it counts, on one line: "40 seconds". A big number
    // with a small word under it ran into the dimension line and read as two
    // objects; on one baseline it reads as a measurement.
    const value = String(Math.round(Number(rows[readoutIndex].value) || 0));
    text(ctx, value + ' seconds', rx, box.y + box.h * 0.335, {
      size, weight: 700, family: 'Space Grotesk', color: accent, align: 'right', tracking: -1,
    });
  }

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
  paper = 'rgba(255,255,255,0.82)',
}) {
  if (!lines.length) return;
  // A terminal is a tall object, not a search bar. At 0.6 of the region's height
  // the window was 1280 by 220 - wide, flat, and with a third of the region empty
  // underneath it. At 0.80 with a narrower width it reads as a window, which is
  // what the sentence ("make it one command") is showing.
  const win = {
    x: box.x, y: box.y + box.h * 0.04,
    w: box.w * 0.82, h: Math.min(box.h * 0.80, box.h - box.h * 0.04),
  };
  const appear = ease.outCubic(clamp(local / 0.4));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * appear;
  panel(ctx, {
    x: win.x, y: win.y, w: win.w, h: win.h, r: 22,
    fill: paper, stroke: hair(0.28),
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
      // The tick is sized to the block that holds it, not to the block's width.
      // It used to be drawn from the block's width - which on a wide window is
      // several times the block's height - so every tick overflowed its block and
      // the run read as a row of scribbles.
      const bh = win.h * 0.135;
      const cx = win.x + win.w * 0.07 + i * bw + bw * 0.43;
      const cy = blockY + bh * 0.52;
      const unit = bh * 0.30;
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = Math.max(2, bh * 0.16);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(cx - unit, cy);
      ctx.lineTo(cx - unit * 0.25, cy + unit);
      ctx.lineTo(cx + unit * 1.05, cy - unit);
      ctx.stroke();
      ctx.restore();
    }
  }
}

/* ------------------------------------------------------------------- stamp */

/**
 * A phrase impressed onto the frame, like a stamp on a page.
 *
 * The film opens by naming the rubber stamp as its villain: "most teams rubber
 * stamp the diff". The closing card is the same object, earned this time - the
 * method, stamped. That is a callback doing structural work rather than a
 * decoration: the shape of the ending answers the shape of the opening.
 *
 * It lands hard and then is still. The rotation settles from five degrees to
 * two and a half, the scale comes down from 1.14 to 1, and the ink arrives last,
 * so the motion reads as pressure applied and released. No bounce, no wobble.
 */
function stampLockup(ctx, {
  box, local, seconds, text: value = '', kicker: over = '',
  colour = UI.white, accent = UI.gold,
}) {
  if (!value) return;
  const land = clamp(local / Math.min(0.42, seconds * 0.3));
  const e = ease.outCubic(land);
  const press = 1 + (1 - e) * 0.14;
  const tilt = -0.05 + (1 - e) * 0.03;
  const padX = box.w * 0.045;
  const padY = box.h * 0.115;
  // Sized for the press: the object arrives 14% oversized while it lands, so
  // its resting size has to leave that room inside the region.
  const w = box.w * 0.70;
  const h = box.h * 0.74;
  const cx = box.x + box.w * 0.5;
  const cy = box.y + box.h * 0.5;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(tilt);
  ctx.scale(press, press);
  ctx.globalAlpha = ctx.globalAlpha * clamp(land * 1.6);

  // Two rules: the outer is the object, the inner is its impression.
  const weight = Math.max(3, H_UNIT(box) * 0.012);
  ctx.strokeStyle = colour;
  ctx.lineWidth = weight;
  roundRect(ctx, -w / 2, -h / 2, w, h, 10);
  ctx.stroke();
  ctx.strokeStyle = accent;
  ctx.lineWidth = Math.max(2, weight * 0.55);
  roundRect(ctx, -w / 2 + padX * 0.55, -h / 2 + padY * 0.55,
    w - padX * 1.1, h - padY * 1.1, 6);
  ctx.stroke();

  // The phrase, set in the object's own measure.
  const lines = wrapTo(ctx, value, {
    maxWidth: w - padX * 1.6, size: Math.round(h * 0.2), weight: 700,
    family: 'Space Grotesk', tracking: 6, max: 2,
  });
  const size = fit(ctx, lines.join(' '), {
    maxWidth: w - padX * 1.9, cap: h * (lines.length > 1 ? 0.21 : 0.26),
    floor: 20, family: 'Space Grotesk', weight: 700, tracking: 6,
  });
  const lineH = size * 1.12;
  const top = -((lines.length - 1) * lineH) / 2;
  lines.forEach((line, i) => {
    text(ctx, String(line).toUpperCase(), 0, top + i * lineH + size * 0.36, {
      size, weight: 700, family: 'Space Grotesk', color: colour, align: 'center', tracking: 6,
    });
  });

  // Three ticks along the bottom rule: the impression's own counter-mark.
  const marks = 3;
  for (let i = 0; i < marks; i += 1) {
    const appear = clamp((land - 0.3 - i * 0.08) / 0.4);
    if (appear <= 0) continue;
    ctx.globalAlpha = ctx.globalAlpha * appear;
    ctx.fillStyle = accent;
    ctx.fillRect(-w * 0.06 + i * w * 0.05, h / 2 - padY * 0.9, w * 0.026, weight * 1.6);
    ctx.globalAlpha = ctx.globalAlpha / Math.max(appear, 1e-6);
  }
  ctx.restore();

  if (over) {
    const size = fit(ctx, over, {
      maxWidth: box.w * 0.7, cap: box.h * 0.075, floor: 16,
      family: 'Inter', weight: 600, tracking: 5,
    });
    label(ctx, over, cx, box.y + box.h + box.h * 0.02, {
      size, colour: tint(0.65), align: 'center', tracking: 5, alpha: clamp((land - 0.4) * 2),
    });
  }
}

/** A unit of height that a template can measure against, from its own box. */
function H_UNIT(box) {
  return box.h * 4;
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
/**
 * A proportion as countable marks.
 *
 * The dial says "twenty percent"; this says "four of twenty", and the viewer can
 * count them. That is the difference between a number that is asserted and a
 * number that is shown - and it is the one picture in this library where the
 * *quantity of ink* is the message.
 */
function dotGauge(ctx, {
  box, local, seconds, value = 2, of = 20, caption = '', colour = UI.text, accent = UI.gold,
}) {
  const total = Math.max(2, Math.min(40, Math.round(of)));
  const lit = Math.max(0, Math.min(total, Math.round(value)));
  const cols = total <= 10 ? total : total <= 20 ? 10 : Math.ceil(total / 4);
  const rows = Math.ceil(total / cols);
  // A cell is capped in both directions: twenty discs across the whole frame read
  // as decoration, a grid you can take in at a glance reads as a quantity.
  const cellW = Math.min(box.w / cols, box.h * 0.30);
  const cellH = Math.min(box.h * 0.55 / rows, cellW * 1.30);
  const r = Math.min(cellW * 0.40, cellH * 0.44);
  const gridW = cols * cellW;
  const x0 = box.x + (box.w - gridW) / 2 + cellW / 2;
  const y0 = box.y + box.h * 0.05 + cellH / 2;
  const land = Math.min(seconds * 0.62, 1.5);
  for (let i = 0; i < total; i += 1) {
    const cx = x0 + (i % cols) * cellW;
    const cy = y0 + Math.floor(i / cols) * cellH;
    const on = i < lit;
    const arrive = ease.outCubic(clamp((local - (i / total) * land * 0.8) / 0.18));
    ctx.save();
    if (on) {
      ctx.globalAlpha = ctx.globalAlpha * arrive;
      ctx.fillStyle = i >= lit - 1 ? accent : colour;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.globalAlpha = ctx.globalAlpha * 0.30 * ease.outCubic(clamp(local / 0.3));
      ctx.strokeStyle = hair(0.55);
      ctx.lineWidth = Math.max(1.5, r * 0.14);
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.92, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }
  // The count, spelled the way it is spoken. Every size here is a fraction of the
  // region: an absolute pixel ceiling is a two-percent label on a 4K master, which
  // is what the first stills looked like.
  const countSize = Math.round(box.h * 0.20);
  const countY = box.y + box.h * (caption ? 0.80 : 0.92);
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * span(local, 0.16, 0.42);
  text(ctx, `${lit} of ${total}`, box.x + box.w * 0.5, countY, {
    size: countSize, weight: 700, family: 'Space Grotesk', color: colour, align: 'center', tracking: 0.5,
  });
  ctx.restore();
  if (caption) {
    const size = Math.round(box.h * 0.12);
    labelBlock(ctx, String(caption), box.x + box.w * 0.5, box.y + box.h * 0.95, {
      maxWidth: box.w * 0.9, cap: size, minSize: Math.round(size * 0.7), colour, max: 1,
      alpha: span(local, 0.30, 0.60),
    });
  }
}

/**
 * A sequence on one axis.
 *
 * Time is the one structure a list cannot draw: four rows say "these things
 * exist", a rail says "in this order, this far apart". The marker travels to the
 * last stop with the sentence, and the rail fills behind it, so the picture is
 * never a finished diagram being held.
 */
function timelineRail(ctx, {
  box, local, seconds, stops = [], colour = UI.text, accent = UI.gold,
}) {
  const list = (Array.isArray(stops) ? stops : []).slice(0, 6);
  if (!list.length) return;
  const count = list.length;
  const y = box.y + box.h * 0.52;
  // Labels are centred on their tick, so the rail starts and ends a label's
  // half-width inside the region; without that inset the ends hang off the edge.
  const inset = Math.min(box.w * 0.13, box.w * 0.30);
  const left = box.x + inset;
  const right = box.x + box.w - inset;
  const railW = right - left;
  const grow = ease.outCubic(clamp(local / Math.min(seconds * 0.4, 0.9)));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * span(local, 0, 0.22);
  ctx.fillStyle = hair(0.30);
  ctx.fillRect(left, y - Math.max(1.5, box.h * 0.006) / 2, railW, Math.max(1.5, box.h * 0.006));
  ctx.restore();
  const atOf = (stop, i) => (typeof stop.at === 'number' ? clamp(stop.at) : count === 1 ? 0.5 : i / (count - 1));
  list.forEach((stop, i) => {
    const at = atOf(stop, i);
    const x = left + railW * at * grow;
    if (i < count - 1) {
      const next = atOf(list[i + 1], i + 1);
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * 0.75;
      ctx.fillStyle = accent;
      ctx.fillRect(x, y - Math.max(1.5, box.h * 0.006) * 1.6,
        Math.max(0, railW * (next - at) * grow), Math.max(3, box.h * 0.012));
      ctx.restore();
    }
    // A rail that fills in one second and then sits is a diagram; on a section
    // clock it should arrive as the narrator reaches each stop.
    const arrive = ease.outCubic(clamp((local - (i / count) * Math.min(seconds * 0.62, 8)) / 0.2));
    const up = i % 2 === 0;
    const stem = box.h * 0.085;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * arrive;
    ctx.fillStyle = i === count - 1 ? accent : colour;
    ctx.fillRect(x - Math.max(1.5, box.h * 0.005), up ? y - stem : y, Math.max(3, box.h * 0.010), stem);
    ctx.beginPath();
    ctx.arc(x, y, Math.max(4, box.h * 0.016), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    // A centred label on the last stop runs off the frame edge, so the block is
    // clamped back inside the region and the type is sized to the slot, not the
    // region: three stops on one rail want a third of the rail each.
    const labelW = Math.min(railW / Math.max(2, count) * 1.45, box.w * 0.30);
    const labelY = up ? y - stem - box.h * 0.085 : y + stem + box.h * 0.185;
    const cap = Math.round(box.h * 0.175);
    const labelX = Math.max(box.x + labelW * 0.5, Math.min(x, box.x + box.w - labelW * 0.5));
    labelBlock(ctx, stop.label || '', labelX, labelY, {
      maxWidth: labelW, cap, minSize: Math.round(cap * 0.62), colour, max: 2, alpha: arrive,
    });
  });
}

/**
 * Two things with a shared middle.
 *
 * A comparison with no overlap is two cards. The lens is the point: what the two
 * have in common is drawn, hatched, and named, and the circles move into each
 * other as the sentence gets to the overlap.
 */
function overlapPair(ctx, {
  box, local, seconds, left = '', right = '', shared = '', colour = UI.text, accent = UI.gold,
}) {
  const r = Math.min(box.h * 0.36, box.w * 0.19);
  const gap = r * 0.55;          // centre-to-centre is twice this: a lens, not a kiss
  const cx = box.x + box.w * 0.5;
  const cy = box.y + box.h * 0.42;
  const draw = ease.outCubic(clamp(local / Math.min(seconds * 0.5, 1.2)));
  const ax = cx - gap * draw;
  const bx = cx + gap * draw;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.50;
  ctx.strokeStyle = hair(0.75);
  ctx.lineWidth = Math.max(2, r * 0.035);
  for (const x of [ax, bx]) {
    ctx.beginPath();
    ctx.arc(x, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
  // The lens: each circle clipped to the other, hatched once the two have met.
  const hatch = span(draw, 0.6, 1);
  if (hatch > 0) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(ax, cy, r, 0, Math.PI * 2);
    ctx.clip();
    ctx.beginPath();
    ctx.arc(bx, cy, r, 0, Math.PI * 2);
    ctx.clip();
    ctx.globalAlpha = ctx.globalAlpha * 0.75 * hatch;
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, r * 0.03);
    for (let k = -r; k < r * 2; k += Math.max(7, r * 0.062)) {
      ctx.beginPath();
      ctx.moveTo(cx - r + k, cy - r);
      ctx.lineTo(cx - r + k + r * 1.6, cy + r);
      ctx.stroke();
    }
    ctx.restore();
  }
  // The labels live *outside* the circles, with a leader into the lobe. Centred
  // inside the lobes, a word like "Simple interest" either overflowed or shrank
  // past the legibility floor and vanished.
  const size = Math.round(box.h * 0.155);
  const sideW = Math.min(box.w * 0.30, (box.w - 2 * r * 1.55) * 0.5);
  const leader = Math.max(10, box.w * 0.012);
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.42 * span(local, 0.2, 0.5);
  ctx.strokeStyle = hair(0.8);
  ctx.lineWidth = Math.max(2, r * 0.012);
  ctx.beginPath();
  ctx.moveTo(ax - r, cy - size * 0.35);
  ctx.lineTo(ax - r - leader, cy - size * 0.35);
  ctx.moveTo(bx + r, cy - size * 0.35);
  ctx.lineTo(bx + r + leader, cy - size * 0.35);
  ctx.stroke();
  ctx.restore();
  labelBlock(ctx, left, ax - r - leader, cy - size * 0.9, {
    maxWidth: sideW, cap: size, minSize: Math.round(size * 0.62), colour, align: 'right', max: 2,
  });
  labelBlock(ctx, right, bx + r + leader, cy - size * 0.9, {
    maxWidth: sideW, cap: size, minSize: Math.round(size * 0.62), colour, align: 'left', max: 2,
  });
  if (shared) {
    labelBlock(ctx, shared, cx, cy + r + box.h * 0.16, {
      maxWidth: box.w * 0.7, cap: Math.round(size * 0.82), minSize: Math.round(size * 0.52),
      colour, max: 1, alpha: span(local, 0.5, 0.9),
    });
  }
}

/**
 * A whole taken apart.
 *
 * The exploded assembly: the layers separate as the narration names them, each
 * with a leader line to its label. It is the one picture here that says "this
 * thing is made of these", which is what a mechanism beat is always saying.
 */
function explodedStack(ctx, {
  box, local, seconds, layers = [], colour = UI.text, accent = UI.gold,
}) {
  const list = (Array.isArray(layers) ? layers : []).slice(0, 4);
  if (!list.length) return;
  const count = list.length;
  // Narrower than the region on purpose: a stack of wide thin bars is a bar
  // chart, and the layer that has to be read here is the *thickness* of each
  // slab - that is what makes it an object taken apart.
  const plateW = box.w * 0.32;
  const plateH = Math.min(box.h * 0.19, (box.h * 0.78) / (count + (count - 1) * 0.95));
  const x = box.x + box.w * 0.02;
  const open = ease.outCubic(clamp((local - 0.10) / Math.min(seconds * 0.60, 4.0)));
  const spread = plateH * 0.95 * open;
  const stackH = plateH * count + spread * (count - 1);
  const top = box.y + (box.h - stackH) / 2;
  const labelX = x + plateW + box.w * 0.07;
  // The spine every exploded drawing has: one line the parts were taken off, so
  // the picture reads as one object in pieces rather than three loose cards.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.55 * open;
  ctx.strokeStyle = hair(0.9);
  ctx.lineWidth = Math.max(2, plateH * 0.035);
  ctx.beginPath();
  ctx.moveTo(x + plateW * 0.08, top - plateH * 0.22);
  ctx.lineTo(x + plateW * 0.08, top + stackH + plateH * 0.22);
  ctx.stroke();
  ctx.restore();
  list.forEach((label, i) => {
    const y = top + i * (plateH + spread);
    const arrive = ease.outCubic(clamp((local - (i / count) * Math.min(seconds * 0.55, 3.0)) / 0.30));
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * arrive;
    // A stepped edge: each layer sits a hair further in than the one below, so
    // the stack reads as a drawing of an object rather than a bar chart.
    const insetX = i * plateW * 0.035;
    roundRect(ctx, x + insetX, y, plateW - insetX, plateH, 12);
    ctx.fillStyle = i === count - 1 ? 'rgba(180,118,42,0.16)' : 'rgba(255,255,255,0.86)';
    ctx.fill();
    ctx.strokeStyle = i === count - 1 ? accent : hair(0.36);
    ctx.lineWidth = 2;
    ctx.stroke();
    // The cut edge: a heavier line along the bottom of each plate, which is what
    // makes a flat rectangle read as a slab with thickness.
    ctx.beginPath();
    ctx.moveTo(x + insetX + 10, y + plateH - 3);
    ctx.lineTo(x + plateW - 10, y + plateH - 3);
    ctx.strokeStyle = i === count - 1 ? accent : hair(0.55);
    ctx.lineWidth = Math.max(2, plateH * 0.045);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + plateW + 2, y + plateH * 0.5);
    ctx.lineTo(labelX - box.w * 0.015, y + plateH * 0.5);
    ctx.strokeStyle = hair(0.42);
    ctx.lineWidth = Math.max(1.5, plateH * 0.024);
    ctx.stroke();
    ctx.restore();
    const cap = Math.round(plateH * 0.52);
    labelBlock(ctx, label, labelX, y + plateH * 0.5 - plateH * 0.18, {
      maxWidth: box.w * 0.40, cap, minSize: Math.round(cap * 0.62), colour, align: 'left', max: 2,
      alpha: arrive,
    });
  });
}

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
    when: ['explain-a-number'],
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
    id: 'stamp-lockup',
    name: 'Stamp lockup',
    purpose: 'Impresses the closing phrase onto the frame as a stamped object.',
    when: ['punchline'],
    avoid: [
      'A long sentence: a stamp holds four or five words, not a clause.',
      'Anywhere but the end of an argument: a stamp is a verdict.',
    ],
    minSeconds: 1.6,
    maxSeconds: 5.0,
    needs: ['text'],
    regions: ['statement', 'title', 'hero'],
    cost: 'low',
    sample: { text: 'That is the method', kicker: 'the method' },
    draw: stampLockup,
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
  {
    id: 'dot-gauge',
    name: 'Dot gauge',
    purpose: 'A proportion as countable marks: the lit dots are the part the narration names.',
    when: ['explain-a-number', 'show-criteria', 'name-the-thing'],
    avoid: [
      'A proportion too large to count: over forty marks and the dots read as texture.',
      'Two proportions on one beat: one grid, one part.',
    ],
    minSeconds: 1.8,
    maxSeconds: 7.0,
    needs: ['value', 'of'],
    regions: ['spread', 'wide', 'stage', 'hero', 'split'],
    cost: 'low',
    sample: { value: 2, of: 20, caption: 'two in twenty' },
    draw: dotGauge,
  },
  {
    id: 'timeline-rail',
    name: 'Timeline rail',
    purpose: 'A sequence of moments on one axis, with a marker that arrives where the narration arrives.',
    when: ['show-a-sequence', 'before-and-after', 'show-the-mechanism', 'recap'],
    avoid: [
      'Moments that are not in time order: the rail would be a list in disguise.',
      'More than six stops: the labels collide.',
    ],
    minSeconds: 2.0,
    maxSeconds: 9.0,
    needs: ['stops'],
    regions: ['wide', 'spread', 'stage', 'split', 'floor'],
    cost: 'low',
    sample: { stops: [{ label: 'Opened' }, { label: 'Read' }, { label: 'Checked' }, { label: 'Sent' }] },
    draw: timelineRail,
  },
  {
    id: 'overlap-pair',
    name: 'Overlap pair',
    purpose: 'Two things that share a middle, drawn as two circles whose overlap is hatched.',
    when: ['make-a-comparison', 'state-the-thesis', 'before-and-after'],
    avoid: [
      'Two things with nothing in common: the lens would be empty.',
      'Three or more sets: two circles are the most this picture holds.',
    ],
    minSeconds: 2.0,
    maxSeconds: 7.0,
    needs: ['left', 'right'],
    regions: ['spread', 'stage', 'split', 'wide'],
    cost: 'low',
    sample: { left: 'Cheap cable', right: 'Old cell', shared: 'both drop the voltage' },
    draw: overlapPair,
  },
  {
    id: 'exploded-stack',
    name: 'Exploded stack',
    purpose: 'A whole taken apart into the layers it is made of, each labelled as it separates.',
    when: ['show-the-mechanism', 'build-an-argument', 'show-criteria'],
    avoid: [
      'Layers that are not parts of one whole.',
      'More than four layers: the labels run out of room.',
    ],
    minSeconds: 2.0,
    maxSeconds: 9.0,
    needs: ['layers'],
    regions: ['wide', 'spread', 'split', 'stage'],
    cost: 'medium',
    sample: { layers: ['The claim', 'The evidence', 'The decision'] },
    draw: explodedStack,
  },
];
