/**
 * Cards: the typographic furniture of a film.
 *
 * A lower third, a chapter card, a quote, a single statistic, an end card and a
 * ticker. These are not "type moves" - a move animates a line, a card is a
 * whole arrangement with a rule, a label, a value and a place to sit. Every
 * documentary needs all six, and every one of them was being rebuilt by hand.
 *
 *     drawCard(ctx, 'lower-third', { x, y, w, text: '...', label: '...', p })
 */

import { text } from '../ui.mjs';
import { clamp, lerp } from '../ui.mjs';

const EASE = (t) => 1 - Math.pow(1 - clamp(t), 3);

function setText(ctx, size, weight, family, colour, align) {
  ctx.font = `${weight} ${size}px ${family}`;
  ctx.fillStyle = colour;
  ctx.textAlign = align;
  ctx.textBaseline = 'alphabetic';
}

/** The largest size, at or below `max`, at which the string fits `maxWidth`. */
export function fitText(ctx, value, maxWidth, max, weight = 700, family = 'Inter') {
  let size = max;
  ctx.font = `${weight} ${size}px ${family}`;
  while (size > 10 && ctx.measureText(value).width > maxWidth) {
    size -= 1;
    ctx.font = `${weight} ${size}px ${family}`;
  }
  return size;
}

/** Break a string into lines that fit `maxWidth`, at a given font. */
export function wrap(ctx, value, maxWidth) {
  const words = String(value).split(/\s+/);
  const lines = [];
  let line = '';
  words.forEach((w) => {
    const next = line ? `${line} ${w}` : w;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = w;
    } else {
      line = next;
    }
  });
  if (line) lines.push(line);
  return lines;
}

export const cards = {
  /** Lower third: who is speaking, what they do. The most-used card in film. */
  'lower-third': (ctx, { x, y, w, text: value = '', label = '', palette = {}, p = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    const k = EASE(p);
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y - 40, w * k, 110);
    ctx.clip();
    // The bar: sits behind the name, gives it weight without a box.
    ctx.fillStyle = accent;
    ctx.globalAlpha = 0.9;
    ctx.fillRect(x, y, Math.max(3, w * 0.012), 44);
    ctx.globalAlpha = 1;
    if (label) {
      setText(ctx, 12, 700, 'Inter', accent, 'left');
      ctx.globalAlpha = clamp((p - 0.3) / 0.4);
      ctx.fillText(String(label).toUpperCase(), x + 18, y + 12);
      ctx.globalAlpha = 1;
    }
    setText(ctx, 26, 700, 'Inter', ink, 'left');
    ctx.fillText(value, x + 18 * clamp(p * 2), y + 40);
    // A second line, the rule under the name.
    ctx.strokeStyle = ink;
    ctx.globalAlpha = 0.25 * clamp((p - 0.55) / 0.45);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + 18, y + 54);
    ctx.lineTo(x + 18 + 120 * clamp((p - 0.55) / 0.45), y + 54);
    ctx.stroke();
    ctx.restore();
  },

  /** A quote, with the mark that makes it one. */
  quote: (ctx, { x, y, w, text: value = '', source = '', palette = {}, p = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    ctx.save();
    setText(ctx, 64, 700, 'Georgia', accent, 'left');
    ctx.globalAlpha = clamp(p * 2) * 0.5;
    ctx.fillText('\u201C', x, y + 20);
    ctx.globalAlpha = 1;
    setText(ctx, 30, 500, 'Inter', ink, 'left');
    const lines = wrap(ctx, value, w);
    lines.forEach((line, i) => {
      const appear = clamp((p - i * 0.09) * 3);
      if (appear <= 0) return;
      ctx.globalAlpha = appear;
      ctx.fillText(line, x + 34, y + 34 + i * 40);
    });
    ctx.globalAlpha = 1;
    if (source) {
      const k = clamp((p - 0.4 - lines.length * 0.09) * 3);
      ctx.globalAlpha = k;
      ctx.strokeStyle = accent;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + 34, y + 54 + lines.length * 40);
      ctx.lineTo(x + 34 + 28 * k, y + 54 + lines.length * 40);
      ctx.stroke();
      setText(ctx, 14, 700, 'Inter', accent, 'left');
      ctx.fillText(String(source).toUpperCase(), x + 72, y + 59 + lines.length * 40);
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  },

  /** A chapter card: the number, the title, the film's punctuation. */
  chapter: (ctx, { x, y, w, number = '01', text: value = '', palette = {}, p = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    ctx.save();
    // The number sits above the title, small and tracked.
    setText(ctx, 14, 700, 'Inter', accent, 'left');
    ctx.globalAlpha = clamp(p * 3);
    ctx.fillText(String(number).padStart(2, '0'), x, y);
    ctx.globalAlpha = 1;
    // Rule growing out from the number.
    ctx.strokeStyle = hardLine(accent);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x + 34, y - 5);
    ctx.lineTo(x + 34 + Math.min(w * 0.18, 90) * clamp((p - 0.15) / 0.5), y - 5);
    ctx.stroke();
    const size = fitText(ctx, value, w, 52);
    setText(ctx, size, 700, 'Inter', ink, 'left');
    const k = clamp((p - 0.2) / 0.5);
    // The band spans the glyphs from ascender to descender. Clipping from
    // y-90 to y+20 cut every title down to its top edge.
    ctx.beginPath();
    ctx.rect(x - 4, y - 60, (w + 8) * EASE(k), 110);
    ctx.clip();
    ctx.fillText(value, x, y + 46);
    ctx.restore();
  },

  /** One number, huge, with its unit and its claim beneath. */
  stat: (ctx, { x, y, w, text: value = '', label = '', palette = {}, p = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    ctx.save();
    const size = fitText(ctx, value, w + 8, 92);
    setText(ctx, size, 700, 'Inter', ink, 'left');
    const k = EASE(clamp(p * 1.3));
    ctx.beginPath();
    ctx.rect(x - 6, y - size * 1.02, (w + 12) * k, size * 1.36);
    ctx.clip();
    ctx.fillText(value, x, y);
    ctx.restore();
    ctx.save();
    setText(ctx, 15, 600, 'Inter', accent, 'left');
    ctx.globalAlpha = clamp((p - 0.45) / 0.4);
    const lines = wrap(ctx, label, w);
    lines.forEach((line, i) => ctx.fillText(line.toUpperCase(), x, y + 34 + i * 22));
    ctx.restore();
  },

  /** End card: the closing claim and where to go next. */
  'end-card': (ctx, { x, y, w, text: value = '', cta = '', palette = {}, p = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    ctx.save();
    const size = fitText(ctx, value, w, 44);
    setText(ctx, size, 700, 'Inter', ink, 'center');
    const k = clamp(p * 1.6);
    ctx.globalAlpha = k;
    ctx.fillText(value, x + w / 2, y);
    ctx.globalAlpha = 1;
    if (cta) {
      const c = clamp((p - 0.35) / 0.4);
      const bw = Math.min(w * 0.5, 260);
      const bh = 46;
      ctx.strokeStyle = accent;
      ctx.lineWidth = 1.6;
      ctx.globalAlpha = c;
      ctx.beginPath();
      const bx = x + (w - bw) / 2;
      const by = y + 28;
      ctx.roundRect ? ctx.roundRect(bx, by, bw, bh, bh / 2) : ctx.rect(bx, by, bw, bh);
      ctx.stroke();
      setText(ctx, 15, 700, 'Inter', accent, 'center');
      ctx.fillText(String(cta).toUpperCase(), x + w / 2, by + 29);
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  },

  /** A ticker: a band of headlines running past, for a montage or an era. */
  ticker: (ctx, { x, y, w, text: value = '', palette = {}, p = 1, speed = 1 }) => {
    const ink = palette.text || '#12233F';
    const accent = palette.caption || '#B4762A';
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y - 26, w, 40);
    ctx.clip();
    ctx.globalAlpha = 0.10;
    ctx.fillStyle = accent;
    ctx.fillRect(x, y - 26, w, 40);
    ctx.globalAlpha = 1;
    setText(ctx, 15, 700, 'Inter', ink, 'left');
    const measure = ctx.measureText(value).width;
    const offset = -((p * 1.4 * speed) % 1) * (measure + 60);
    for (let i = 0; i < 3; i += 1) {
      ctx.fillText(value, x + offset + i * (measure + 60), y);
    }
    ctx.restore();
  },
};

/** A colour that still reads as itself at 1px - accents are not lines. */
function hardLine(colour) {
  return colour;
}

export const CARD_IDS = Object.keys(cards);
export default cards;
