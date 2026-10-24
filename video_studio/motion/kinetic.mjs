/**
 * Kinetic type: words that arrive, rather than a line that fades in.
 *
 * The owner's note on the first cut was "there is no kinetic typography". What
 * the film had was a whole line sliding up as one object, which reads as a
 * caption appearing, not as type performing. Kinetic type is set word by word:
 * each word is masked to its own box and rises into it, the words stagger, and
 * the emphasis lands a beat after the rest.
 *
 * Two rules keep it professional rather than cheap:
 *   * the mask is exact. A word never fades through the line above it, so type
 *     cannot overlap type - the failure the owner found twice.
 *   * nothing shakes. No jitter, no random rotation, no bounce past the resting
 *     position. Movement is one direction, eased out, and then still.
 */
import { clamp, ease, UI } from './ui.mjs';

/** Measure one word with the same font settings used to draw it. */
function wordWidth(ctx, word, { size, weight, family, tracking }) {
  ctx.save();
  ctx.font = `${weight} ${size}px "${family}"`;
  const width = ctx.measureText(word).width + tracking * Math.max(0, word.length - 1);
  ctx.restore();
  return width;
}

const spaceWidth = (ctx, { size, weight, family, gap }) => {
  ctx.save();
  ctx.font = `${weight} ${size}px "${family}"`;
  const width = gap ?? ctx.measureText(' ').width;
  ctx.restore();
  return width;
};

/**
 * Lay a phrase out word by word, each one rising into its own mask.
 *
 * ``start`` is the local time of the first word; the rest follow at
 * ``stagger``. Words land in reading order, which is the order the eye moves,
 * and each one is finished before the next begins.
 */
export function kineticWords(ctx, {
  text, x, y, size = 120, weight = 700, family = 'Space Grotesk',
  colour = UI.white, emphasis = {}, align = 'left', start = 0, local = 0,
  stagger = 0.075, duration = 0.5, tracking = 0, gap = null, maxWidth = null,
}) {
  const words = String(text).split(/\s+/).filter(Boolean);
  if (!words.length) return { width: 0, done: false };
  const options = { size, weight, family, tracking };
  const widths = words.map((word) => wordWidth(ctx, word, options));
  const space = spaceWidth(ctx, { size, weight, family, gap });
  const natural = widths.reduce((sum, width) => sum + width, 0) + space * (words.length - 1);
  const scale = maxWidth && natural > maxWidth ? maxWidth / natural : 1;
  const total = natural * scale;
  let cursor = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;

  words.forEach((word, index) => {
    const at = start + index * stagger;
    const p = clamp((local - at) / duration);
    if (p <= 0) {
      cursor += (widths[index] + space) * scale;
      return;
    }
    const e = ease.outQuint(p);
    const width = widths[index] * scale;
    // The mask is one word tall plus a little air, so a rising word never shows
    // through the line above it.
    const maskTop = y - size * 1.02;
    const maskHeight = size * 1.34;

    ctx.save();
    ctx.beginPath();
    ctx.rect(cursor - 8, maskTop, width + 16, maskHeight);
    ctx.clip();
    const rise = (1 - e) * size * 0.92;
    const colourFor = emphasis[index] ?? colour;
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2.4);
    ctx.translate(cursor, y + rise);
    ctx.font = `${weight} ${size * scale}px "${family}"`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    // Tracking settles from open to tight as the word lands: the one detail that
    // makes a single word read as type rather than as an image of type.
    const spacing = tracking * (1 - e) + tracking * 0.35;
    ctx.fillStyle = colourFor;
    let offset = 0;
    for (const character of word) {
      ctx.fillText(character, offset, 0);
      offset += ctx.measureText(character).width + spacing;
    }
    ctx.restore();

    cursor += (widths[index] + space) * scale;
  });

  const lastAt = start + (words.length - 1) * stagger + duration;
  return { width: total, done: local >= lastAt };
}

/**
 * A blunt underline that draws itself on underneath a finished phrase.
 *
 * Kinetic type needs one hard accent to close a beat; a rule that draws on is
 * that accent, and unlike a slash it can never cross a word.
 */
export function kineticRule(ctx, {
  x, y, width, colour = UI.red, thickness = 14, start = 0, local = 0, duration = 0.45,
}) {
  const p = clamp((local - start) / duration);
  if (p <= 0) return 0;
  const e = ease.outQuint(p);
  ctx.save();
  ctx.fillStyle = colour;
  ctx.fillRect(x, y, width * e, thickness);
  ctx.restore();
  return e;
}
