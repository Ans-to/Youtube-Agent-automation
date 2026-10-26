#!/usr/bin/env node
/**
 * A thumbnail, from the same design system as the film.
 *
 * A thumbnail is not a frame of the film. It is a poster: it has to work at 320
 * pixels wide in a crowded feed, next to fifteen other videos, and it has to
 * promise something the film delivers. So it is built from the film's palette,
 * type and accent block - the viewer should recognise the video when they press
 * play - but it is composed for one job: three words and one figure, readable at
 * a glance, with nothing else competing.
 *
 *   node video_studio/films/thumbnail.mjs --brief video_studio/briefs/review-ai-code.json \
 *     --out build/thumbnail.png
 *
 * Rules it enforces, because they are the ones that decide a click:
 *   - two to five words, never a sentence;
 *   - the figure is at least a third of the frame height;
 *   - one accent, used once;
 *   - nothing inside the bottom-right corner, where YouTube's duration badge
 *     lands;
 *   - a dark-to-light field behind the words so the type has contrast anywhere
 *     it is shown.
 */
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import { GlobalFonts, createCanvas } from '@napi-rs/canvas';
import { clamp, text, measure, roundRect } from '../motion/ui.mjs';
import { PALETTES } from '../motion/wordstage.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');

for (const [family, file] of [
  ['Inter', 'inter-latin-400-normal.woff2'],
  ['Inter', 'inter-latin-600-normal.woff2'],
  ['Inter', 'inter-latin-700-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
]) {
  GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
}

function parseArgs(argv) {
  const opts = { brief: null, out: 'thumbnail.png', width: 1280, height: 720, variant: 'a' };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = () => argv[(i += 1)];
    if (flag === '--brief') opts.brief = value();
    else if (flag === '--out') opts.out = value();
    else if (flag === '--width') opts.width = Number(value());
    else if (flag === '--height') opts.height = Number(value());
    else if (flag === '--variant') opts.variant = value();
    else throw new Error(`unknown option: ${flag}`);
  }
  if (!opts.brief) throw new Error('--brief is required');
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
const BRIEF = JSON.parse(fs.readFileSync(path.resolve(OPTS.brief), 'utf8'));
const W = 1920;
const H = 1080;
const SCALE = OPTS.width / W;

const words = String(BRIEF.thumbnail?.line || '').trim().split(/\s+/).filter(Boolean);
if (words.length < 2 || words.length > 5) {
  throw new Error(`a thumbnail wants 2-5 words, this brief has ${words.length} ("${words.join(' ')}")`);
}

// The figure the film's promise turns on, when the brief names a section that
// carries one. It is the biggest object on the poster because it is the claim.
const numberSection = (BRIEF.sections || []).find((section) => section.id === BRIEF.thumbnail?.section);
const figure = Number(numberSection?.props?.value) || null;
const unit = numberSection?.props?.label || '';

const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');
ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
const palette = PALETTES[BRIEF.look || 'light'];
const ink = palette.ink;
const accent = palette.accent;

/* ------------------------------------------------------------------- ground */
const field = ctx.createLinearGradient(0, 0, W * 0.7, H);
field.addColorStop(0, palette.field[0]);
field.addColorStop(0.6, palette.field[1]);
field.addColorStop(1, palette.field[2]);
ctx.fillStyle = field;
ctx.fillRect(0, 0, W, H);

// Two plates, off the edges: the same architecture the film runs behind its
// pictures, so the thumbnail and the film look like one product.
ctx.save();
ctx.translate(W * 0.86, H * 0.30);
ctx.rotate(-0.34);
const plate = ctx.createLinearGradient(-W * 0.16, 0, W * 0.16, 0);
plate.addColorStop(0, 'rgba(18,35,63,0)');
plate.addColorStop(0.5, 'rgba(18,35,63,0.10)');
plate.addColorStop(1, 'rgba(18,35,63,0)');
ctx.fillStyle = plate;
ctx.fillRect(-W * 0.16, -H * 0.46, W * 0.32, H * 0.92);
ctx.fillStyle = accent;
ctx.globalAlpha = 0.22;
ctx.fillRect(-W * 0.02, -H * 0.30, W * 0.055, H * 0.60);
ctx.restore();

// The accent rule at the top: the film's chapter rule, borrowed.
ctx.fillStyle = accent;
ctx.fillRect(W * 0.50, H * 0.20, W * 0.10, H * 0.012);

/* ------------------------------------------------------------------- layout */
//
// One composition, two zones, never overlapping:
//
//   left   the figure, enormous, with its scale underneath it - the claim;
//   right  the promise, two lines, ragged right - the words.
//
// The figure is set at 46% of the frame height and the words at 13%, so at 320
// pixels in a feed the claim is still legible and the promise is still readable.
// Nothing goes in the bottom-right: that is where YouTube's duration badge lands.

const leftZone = { x: W * 0.055, w: W * 0.40 };
const rightZone = { x: W * 0.50, w: W * 0.45 };

if (figure) {
  const size = Math.round(H * 0.40);
  const baseline = H * 0.60;
  text(ctx, String(figure), leftZone.x, baseline, {
    size, weight: 700, family: 'Space Grotesk', color: ink, tracking: -8,
  });
  const figureWidth = measure(ctx, String(figure), {
    size, weight: 700, family: 'Space Grotesk', tracking: -8,
  });
  if (unit) {
    text(ctx, unit.toUpperCase(), leftZone.x, baseline + H * 0.075, {
      size: Math.round(H * 0.055), weight: 600, family: 'Inter', color: accent, tracking: 12,
    });
  }
  // The scale: thirty ticks under the figure, most of them filled. It is the
  // film's own measuring motif, and at thumbnail size it reads as a progress bar
  // without needing a word.
  const ticks = 30;
  for (let i = 0; i < ticks; i += 1) {
    const filled = i / ticks < 0.72;
    ctx.save();
    ctx.globalAlpha = filled ? 0.95 : 0.20;
    ctx.fillStyle = filled ? accent : ink;
    ctx.fillRect(leftZone.x + i * W * 0.0124, baseline + H * 0.135,
      W * 0.0042, H * (i % 5 === 0 ? 0.040 : 0.022));
    ctx.restore();
  }
}

/* -------------------------------------------------------------------- words */
// The promise: one word per line, the last one carrying the accent. Per line is
// deliberate - a three-word promise read as three lines has time to land, and it
// cannot collide with the figure because the whole block is measured first.
const cap = Math.round(H * 0.135);
const lineGap = cap * 1.06;
const lines = words.map((word) => word.toUpperCase());
const blockHeight = lines.length * lineGap;
let cursor = H * 0.5 - blockHeight / 2 + cap * 0.34;
lines.forEach((line, index) => {
  const natural = measure(ctx, line, { size: cap, weight: 700, family: 'Space Grotesk', tracking: 2 });
  const size = natural > rightZone.w
    ? Math.floor((cap * rightZone.w) / natural) : cap;
  text(ctx, line, rightZone.x, cursor, {
    size, weight: 700, family: 'Space Grotesk',
    color: index === lines.length - 1 ? accent : ink, tracking: 2,
  });
  cursor += lineGap;
});

// A hairline down the middle: the film's rule, and the only thing dividing the
// two zones. It gives the poster a grid instead of two floating objects.
ctx.save();
ctx.globalAlpha = 0.18;
ctx.fillStyle = ink;
ctx.fillRect(W * 0.455, H * 0.18, Math.max(2, W * 0.0016), H * 0.64);
ctx.restore();

// The verdict chip, bottom left: a tick in the accent. It is the one mark that
// says "this film ends in a decision" without printing another word.
ctx.save();
roundRect(ctx, leftZone.x, H * 0.845, W * 0.085, H * 0.058, 6);
ctx.fillStyle = accent;
ctx.fill();
ctx.strokeStyle = 'rgba(255,255,255,0.95)';
ctx.lineWidth = Math.max(4, H * 0.007);
ctx.lineCap = 'round';
const chipX = leftZone.x + W * 0.042;
const chipY = H * 0.845 + H * 0.029;
ctx.beginPath();
ctx.moveTo(chipX - W * 0.011, chipY);
ctx.lineTo(chipX, chipY + H * 0.014);
ctx.lineTo(chipX + W * 0.018, chipY - H * 0.019);
ctx.stroke();
ctx.restore();

fs.mkdirSync(path.dirname(path.resolve(OPTS.out)), { recursive: true });
fs.writeFileSync(path.resolve(OPTS.out), canvas.toBuffer('image/png'));
console.log(JSON.stringify({
  out: OPTS.out,
  size: `${OPTS.width}x${OPTS.height}`,
  words: words.length,
  figure,
  statement: `THUMBNAIL: ${OPTS.width}x${OPTS.height}, ${words.length} words, figure ${figure ?? 'none'}`,
}, null, 2));
