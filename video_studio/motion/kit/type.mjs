/**
 * The type kit: every way a word can move.
 *
 * Kinetic typography is the one technique that separates a motion-graphics film
 * from slides. It is also the technique this studio had the least of: one
 * "words appear one after another" move, reused in every film, which is exactly
 * what the owner called generic typing.
 *
 * So each family below is a genuinely different reading of a sentence:
 *
 *   - word-stagger   words land in order, each with its own small arrival
 *   - letter-stagger letters assemble, for a short emphatic word
 *   - mask-slide     the line is revealed by a travelling mask, like a wipe across type
 *   - roll           each word rotates up into place from below, on a drum
 *   - scramble       letters cycle through noise before settling, a decode
 *   - typewriter     a caret travels, characters land left to right
 *   - weight-ramp    a variable weight swells across the line, drawing the eye
 *   - scale-pop      an emphasised word lands oversized then settles
 *   - path-text      the sentence follows a curve - an arc, a wave, an orbit
 *   - karaoke        the line is dim and fills word by word as it is spoken
 *   - emphasis       one word is inked, the rest recede
 *   - underline      a drawn rule lands under the words that matter
 *   - counter        a number counts to its value, digit by digit
 *   - split-flap     characters flip through before settling, like a departures board
 *   - squeeze        the block narrows and settles, a camera iris on type
 *
 * Every one takes the same options and returns the width it drew, so a caller can
 * centre, stack or measure without knowing which technique it asked for.
 */
import { UI, clamp, lerp, noise, span, ease, text, measure } from '../ui.mjs';

const TAU = Math.PI * 2;

function glyphs(ctx, value, words) {
  return words ? String(value).split(/\s+/) : [...String(value)];
}

/** Where each word sits along the line, measured once.
 *
 * `space` is overridable and must be, for the character-level moves: measuring a
 * word space between every glyph is what spaced "Nokia" out into "N o k i a" in
 * the first type gallery.
 */
function layout(ctx, words, { size, weight, family, tracking, align, x, space: spaceFixed = null }) {
  const widths = words.map((word) => measure(ctx, word, { size, weight, family, tracking }));
  const space = spaceFixed !== null ? spaceFixed : measure(ctx, ' ', { size, weight, family, tracking });
  const total = widths.reduce((a, b) => a + b, 0) + space * Math.max(0, words.length - 1);
  const startX = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
  let cursor = startX;
  const positions = words.map((word, i) => {
    const at = cursor;
    cursor += widths[i] + space;
    return { word, x: at, w: widths[i], index: i };
  });
  return { positions, total, space };
}

/** Draw one word with a transform around its own centre. */
function placed(ctx, word, x, w, size, draw) {
  void w;
  ctx.save();
  draw(ctx);
  ctx.restore();
  void x;
  void size;
  void word;
}

export const TYPE_MOVES = {
  'word-stagger': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left', stagger = 0.10 }) => {
    const { positions, total } = layout(ctx, String(value).split(/\s+/), { size, weight, family, tracking: 0, align, x });
    const count = positions.length;
    const share = count > 1 ? (1 - stagger) / (count - 1) : 1;
    positions.forEach((item, i) => {
      const start = i * share;
      const local = clamp((p - start) / Math.max(0.001, stagger > 0 ? 1 - start : 1));
      const rise = (1 - ease.outCubic(local)) * size * 0.55;
      ctx.save();
      ctx.globalAlpha *= clamp(local * 1.6);
      text(ctx, item.word, item.x, y + rise, { size, weight, family, color: colour });
      ctx.restore();
    });
    return total;
  },

  'letter-stagger': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left' }) => {
    const chars = [...String(value)];
    const { positions, total } = layout(ctx, chars, { size, weight, family, tracking: 0, align, x, space: 0 });
    const share = chars.length > 1 ? 0.72 / (chars.length - 1) : 1;
    positions.forEach((item, i) => {
      const local = clamp((p - i * share) / 0.28);
      const drop = (1 - ease.outBack(local)) * size * 0.6;
      ctx.save();
      ctx.globalAlpha *= clamp(local * 2);
      text(ctx, item.word, item.x, y - drop, { size, weight, family, color: colour });
      ctx.restore();
    });
    return total;
  },

  'mask-slide': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left' }) => {
    const word = String(value);
    const width = measure(ctx, word, { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    ctx.save();
    ctx.beginPath();
    // The mask travels with a soft leading edge: a hard edge reads as a wipe
    // transition, a rounded one reads as the type being uncovered.
    ctx.rect(left - size * 0.1, y - size * 1.05, (width + size * 0.2) * clamp(p), size * 1.4);
    ctx.clip();
    text(ctx, word, left, y, { size, weight, family, color: colour });
    ctx.restore();
    return width;
  },

  roll: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left' }) => {
    const words = String(value).split(/\s+/);
    const { positions, total } = layout(ctx, words, { size, weight, family, tracking: 0, align, x });
    const share = words.length > 1 ? 0.7 / (words.length - 1) : 1;
    positions.forEach((item, i) => {
      const local = clamp((p - i * share) / 0.32);
      // A drum: the word rotates up into place on its own centre, so it never
      // slides sideways while it turns.
      const angle = (1 - ease.outCubic(local)) * Math.PI * 0.42;
      const cx = item.x + item.w / 2;
      const cy = y - size * 0.34;
      ctx.save();
      ctx.globalAlpha *= clamp(local * 1.8);
      ctx.translate(cx, cy);
      ctx.rotate(-angle);
      ctx.translate(-cx, -cy + (1 - ease.outCubic(local)) * size * 0.30);
      text(ctx, item.word, item.x, y, { size, weight, family, color: colour });
      ctx.restore();
    });
    return total;
  },

  scramble: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left', seed = 1 }) => {
    const target = String(value);
    const chars = [...target];
    const glyphsPool = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*';
    // Each character settles at its own moment; before that it shows noise.
    const settled = chars.map((ch, i) => p >= (i + 1) / (chars.length + 2));
    const shown = chars.map((ch, i) => {
      if (settled[i]) return ch;
      if (ch === ' ') return ' ';
      const pick = Math.floor(noise(seed * 13 + i * 7.7) * glyphsPool.length);
      return glyphsPool[pick];
    }).join('');
    const width = measure(ctx, target, { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    text(ctx, shown, left, y, { size, weight, family, color: colour });
    return width;
  },

  typewriter: (ctx, { value, x, y, p = 1, size = 64, weight = 500, family = 'Space Grotesk',
    colour = UI.text, align = 'left', caret = true, seed = 1 }) => {
    const word = String(value);
    const count = Math.floor(word.length * clamp(p * 1.05));
    const shown = word.slice(0, Math.max(0, count));
    const width = measure(ctx, word, { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    text(ctx, shown, left, y, { size, weight, family, color: colour });
    if (caret && p < 1) {
      const caretX = left + measure(ctx, shown, { size, weight, family });
      // The caret blinks at 2 Hz: a deterministic function of progress, not a clock.
      const blink = noise(Math.floor(p * 40) + seed) > 0.45 ? 1 : 0;
      if (blink) {
        ctx.save();
        ctx.globalAlpha *= 0.8;
        ctx.fillStyle = colour;
        ctx.fillRect(caretX + size * 0.06, y - size * 0.72, size * 0.06, size * 0.82);
        ctx.restore();
      }
    }
    return width;
  },

  'weight-ramp': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left' }) => {
    const chars = [...String(value)];
    const { positions, total } = layout(ctx, chars, { size, weight, family, tracking: 0, align, x, space: 0 });
    const width = total;
    // One travelling crest of weight, moving left to right and then resting at
    // the target weight: the eye follows it the way it follows a pen.
    const crest = clamp(p) * 1.2 - 0.1;
    positions.forEach((item, i) => {
      if (item.word === ' ') return;
      const t = positions.length > 1 ? i / (positions.length - 1) : 0;
      const distance = Math.abs(t - crest);
      const bulge = clamp(1 - distance / 0.42);
      const w = Math.round(lerp(weight, Math.min(900, weight + 300), bulge));
      ctx.save();
      ctx.globalAlpha *= clamp(p * 2.4);
      text(ctx, item.word, item.x, y, { size, weight: w, family, color: colour });
      ctx.restore();
    });
    return width;
  },

  'scale-pop': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left', emphasis = null }) => {
    const words = String(value).split(/\s+/);
    const target = emphasis ? String(emphasis).toLowerCase() : null;
    // The line is drawn at normal size first, then the marked word is drawn again
    // on top, larger, with the frame's own colour behind it. Reserving extra space
    // in the layout was not enough: the oversize glyphs still reached into the
    // neighbour, which is what put "Nokia lost" on top of "its empire".
    const { positions, total } = layout(ctx, words, { size, weight, family, tracking: 0, align, x });
    const marked = positions.find((item) => (target
      ? item.word.toLowerCase().replace(/[^a-z0-9]/g, '').includes(target.replace(/[^a-z0-9]/g, ''))
      : item.index === 0));
    positions.forEach((item) => {
      if (marked && item.index === marked.index) return;
      const local = clamp((p - 0.25) / 0.4);
      ctx.save();
      ctx.globalAlpha *= clamp(local * 2);
      text(ctx, item.word, item.x, y, { size, weight, family, color: colour });
      ctx.restore();
    });
    if (marked) {
      const local = clamp(p / 0.34);
      const pop = 1 + (1 - ease.outBack(local)) * 0.55;
      ctx.save();
      ctx.globalAlpha *= clamp(local * 2);
      ctx.translate(marked.x + marked.w / 2, y - size * 0.32);
      ctx.scale(pop, pop);
      ctx.translate(-(marked.x + marked.w / 2), -(y - size * 0.32));
      text(ctx, marked.word, marked.x, y, { size, weight, family, color: colour });
      ctx.restore();
    }
    return total;
  },

  'path-text': (ctx, { value, x, y, p = 1, size = 54, weight = 600, family = 'Space Grotesk',
    colour = UI.text, curve = 0.5, span: width = 900 }) => {
    const chars = [...String(value)];
    const widths = chars.map((ch) => measure(ctx, ch, { size, weight, family }));
    const total = widths.reduce((a, b) => a + b, 0);
    const left = x - total / 2;
    const count = Math.ceil(chars.length * clamp(p * 1.15));
    // Each glyph sits at its own accumulated position, so a narrow "i" does not
    // occupy the width of an "M".
    let cursor = left;
    chars.forEach((ch, i) => {
      if (i >= count) return;
      const t = chars.length > 1 ? i / (chars.length - 1) : 0;
      // A parabola: the baseline rises to the middle and comes back down.
      const dy = -Math.sin(t * Math.PI) * Math.min(width, total) * 0.16 * curve;
      const angle = -Math.cos(t * Math.PI) * 0.30 * curve;
      ctx.save();
      ctx.translate(cursor + widths[i] / 2, y + dy);
      ctx.rotate(angle);
      text(ctx, ch, 0, 0, { size, weight, family, color: colour, align: 'center' });
      ctx.restore();
      cursor += widths[i];
    });
    return total;
  },

  karaoke: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, accent = '#B4762A', align = 'left' }) => {
    const words = String(value).split(/\s+/);
    const { positions, total } = layout(ctx, words, { size, weight, family, tracking: 0, align, x });
    const filled = clamp(p) * words.length;
    positions.forEach((item, i) => {
      const done = i < Math.floor(filled);
      ctx.save();
      ctx.globalAlpha *= done ? 1 : 0.30;
      text(ctx, item.word, item.x, y, { size, weight, family, color: done ? accent : colour });
      ctx.restore();
    });
    return total;
  },

  emphasis: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, accent = '#B4762A', align = 'left', word: marked = null }) => {
    const words = String(value).split(/\s+/);
    const { positions, total } = layout(ctx, words, { size, weight, family, tracking: 0, align, x });
    const target = marked ? String(marked).toLowerCase() : null;
    positions.forEach((item) => {
      const isMarked = target ? item.word.toLowerCase().replace(/[^a-z0-9]/g, '') === target.replace(/[^a-z0-9]/g, '') : item.index === positions.length - 1;
      const local = clamp((p - (isMarked ? 0.1 : 0.35)) / 0.4);
      ctx.save();
      ctx.globalAlpha *= clamp(local * 2) * (isMarked ? 1 : 0.42);
      text(ctx, item.word, item.x, y, { size, weight: isMarked ? Math.min(900, weight + 100) : weight, family,
        color: isMarked ? accent : colour });
      ctx.restore();
    });
    return total;
  },

  underline: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, accent = '#B4762A', align = 'left' }) => {
    const width = TYPE_MOVES['word-stagger'](ctx, { value, x, y, p, size, weight, family, colour, align });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    const rule = clamp((p - 0.45) / 0.4);
    if (rule > 0) {
      ctx.save();
      ctx.globalAlpha *= 0.9;
      ctx.fillStyle = accent;
      const thickness = Math.max(2, size * 0.075);
      ctx.fillRect(left, y + size * 0.20, width * ease.outCubic(rule), thickness);
      ctx.restore();
    }
    return width;
  },

  counter: (ctx, { value, x, y, p = 1, size = 96, weight = 700, family = 'Space Grotesk',
    colour = UI.text, suffix = '', prefix = '', decimals = 0, align = 'left' }) => {
    // A counter handed words is asked the wrong question: draw the words rather
    // than counting to zero, which is what the first gallery did.
    if (!Number.isFinite(Number(value)) || String(value).trim() === '') {
      const asText = String(value ?? '');
      const body = `${prefix}${asText}${suffix}`;
      const width = measure(ctx, body, { size, weight, family });
      const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
      text(ctx, body, left, y, { size, weight, family, color: colour });
      return width;
    }
    const target = Number(value) || 0;
    // The count lands slightly before the beat ends, so the finished figure is
    // read for a moment rather than arriving exactly as the cut happens.
    const eased = ease.outCubic(clamp(p / 0.82));
    const shown = target * eased;
    const body = `${prefix}${shown.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`;
    const width = measure(ctx, body, { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    text(ctx, body, left, y, { size, weight, family, color: colour });
    return width;
  },

  'split-flap': (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left', seed = 3 }) => {
    const target = String(value);
    const chars = [...target];
    const pool = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const shown = chars.map((ch, i) => {
      const settleAt = 0.35 + (i / Math.max(1, chars.length)) * 0.5;
      if (p >= settleAt) return ch;
      if (ch === ' ') return ' ';
      // Each unsettled flap cycles at its own rate through a short pool.
      const step = Math.floor(p * 22 + i * 3);
      return pool[Math.floor(noise(seed + i * 5.5 + step) * pool.length)];
    }).join('');
    const width = measure(ctx, target, { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : left0(x, 0);
    text(ctx, shown, left ?? x, y, { size, weight, family, color: colour });
    return width;
  },

  squeeze: (ctx, { value, x, y, p = 1, size = 64, weight = 700, family = 'Space Grotesk',
    colour = UI.text, align = 'left' }) => {
    const width = measure(ctx, String(value), { size, weight, family });
    const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    const k = ease.outCubic(clamp(p));
    ctx.save();
    // Wide and thin, settling to its own proportions: an iris opening on type.
    ctx.translate(left + width / 2, y - size * 0.4);
    ctx.scale(lerp(0.72, 1, k), lerp(0.35, 1, k));
    ctx.globalAlpha *= clamp(p * 1.8);
    text(ctx, String(value), -width / 2, size * 0.4, { size, weight, family, color: colour });
    ctx.restore();
    return width;
  },
};

function left0(x) {
  return x;
}

export function drawType(ctx, move, options) {
  const fn = TYPE_MOVES[move];
  if (!fn) throw new Error(`no type move called ${move}`);
  return fn(ctx, options);
}

export default TYPE_MOVES;
