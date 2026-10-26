/**
 * The room: one handset, one light, twenty seconds.
 *
 * This is not a style test - it is the craft level the film should be built at.
 * The object is modelled (see motion/kit/product.mjs): shaded across its width,
 * specular band, recessed display, bevelled keys, contact shadow, and a floor
 * reflection that multiplies with distance. The camera is a tripod, not a hand:
 * it moves once per shot, slowly, and never shakes.
 *
 *   node films/studio_hero.mjs --frames /tmp/room --fps 30
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { drawHandset, drawStudio, drawReflection } from '../motion/kit/product.mjs';
import { clamp, lerp, span, ease } from '../motion/ui.mjs';

const W = 1280;
const H = 720;
const HERE = path.dirname(fileURLToPath(import.meta.url));

const INK = '#E8E3D6';
const DIM = 'rgba(232,227,214,0.52)';
const GOLD = '#C9A227';
const HORIZON = 0.845;
const FLOOR = H * HORIZON;

const SERIF = 'Instrument Serif';
const SANS = 'Inter';

function text(ctx, value, x, y, {
  size = 40, weight = 400, family = SERIF, colour = INK, align = 'left',
  tracking = 0, alpha = 1, baseline = 'alphabetic',
} = {}) {
  ctx.save();
  ctx.globalAlpha *= clamp(alpha);
  ctx.font = `${weight} ${size}px "${family}"`;
  ctx.fillStyle = colour;
  ctx.textBaseline = baseline;
  if (!tracking) {
    ctx.textAlign = align;
    ctx.fillText(value, x, y);
  } else {
    const chars = [...value];
    const widths = chars.map((c) => ctx.measureText(c).width + tracking);
    const total = widths.reduce((a, b) => a + b, 0) - tracking;
    let cx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
    ctx.textAlign = 'left';
    chars.forEach((c, i) => { ctx.fillText(c, cx, y); cx += widths[i]; });
  }
  ctx.restore();
}

/** Caps line whose letters spread apart as it arrives. */
function capsLine(ctx, value, x, y, p, { size = 13, colour = GOLD, align = 'left', from = 2, to = 7 } = {}) {
  const k = ease.outCubic(clamp(p));
  text(ctx, value, x, y, {
    size, weight: 600, family: SANS, colour, align,
    tracking: lerp(from, to, k), alpha: clamp(p * 1.8),
  });
}

/** A line of type that rises behind a mask, so it is never seen half-drawn. */
function rise(ctx, value, x, y, p, opts = {}) {
  const { size = 72, family = SERIF, colour = INK, weight = 400, align = 'left', mask = true } = opts;
  const k = ease.outQuint(clamp(p));
  ctx.save();
  if (mask) {
    const w = align === 'center' ? 900 : 1100;
    const x0 = align === 'center' ? x - w / 2 : x - 20;
    ctx.beginPath();
    ctx.rect(x0, y - size * 1.16, w, size * 1.30);
    ctx.clip();
  }
  ctx.globalAlpha *= clamp(p * 2.2);
  ctx.translate(0, (1 - k) * size * 1.12);
  text(ctx, value, x, y, { size, family, colour, weight, align });
  ctx.restore();
}

/* ------------------------------------------------------------- the shots ---- */

/** Where the handset stands, and how big, on a given beat. */
const BEATS = [
  {
    id: 'room', dur: 7.0,
    base: { x: 0.565, y: 0.885, w: 236 },
    push: [1.00, 1.055],
    facing: [-0.55, 0.35],
    screen: 'menu',
    glow: [0.5, 1.0],
  },
  {
    id: 'ring', dur: 6.6,
    base: { x: 0.740, y: 0.885, w: 268 },
    push: [1.05, 1.00],
    facing: [0.45, 0.05],
    screen: 'ring',
    glow: [1.0, 1.0],
  },
  {
    id: 'wide', dur: 6.4,
    base: { x: 0.545, y: 0.885, w: 158 },
    push: [1.14, 1.00],
    facing: [0.15, -0.35],
    screen: 'menu',
    glow: [0.9, 0.5],
  },
];

export const DURATION = BEATS.reduce((a, b) => a + b.dur, 0);

export function drawRoom(ctx, t) {
  let start = 0;
  let beat = BEATS[0];
  let local = 0;
  for (const b of BEATS) {
    if (t >= start && t < start + b.dur) { beat = b; local = t - start; break; }
    start += b.dur;
    local = t - start;
  }
  const p = clamp(local / beat.dur);

  /* the room, lit slightly differently in each beat */
  const roomT = t;
  drawStudio(ctx, {
    w: W, h: H, t: roomT, horizon: HORIZON,
    intensity: beat.id === 'wide' ? 1.25 : beat.id === 'ring' ? 0.9 : 1.0,
  });

  /* camera: one slow move per beat, eased at both ends, never a shake */
  const zoom = beat.push[0] + (beat.push[1] - beat.push[0]) * ease.inOutCubic(p);
  const pw = beat.base.w * zoom;
  const ph = pw * 1.87;
  const cx = W * beat.base.x;
  const baseY = H * beat.base.y;
  const px = cx - pw / 2;
  const py = baseY - ph;
  const facing = lerp(beat.facing[0], beat.facing[1], ease.inOutCubic(p));
  const glow = lerp(beat.glow[0], beat.glow[1], p);

  /* the subject, then its reflection, then a little haze over both */
  const subject = (withShadow) => drawHandset(ctx, {
    x: px, y: py, w: pw, h: ph, facing, screen: beat.screen, glow, shadow: withShadow,
  });
  drawReflection(ctx, () => drawHandset(ctx, {
    x: px, y: py, w: pw, h: ph, facing, screen: beat.screen, glow, shadow: false,
  }), { h: H, mirrorAt: baseY, alpha: 0.17, fadeTo: 1.0 });
  subject(true);

  /* --------------------------------------------------------- the words --- */
  if (beat.id === 'room') {
    const a = span(local, 0.35, 2.6);
    const b = span(local, 1.15, 3.4);
    capsLine(ctx, 'ESPOO · FINLAND', W * 0.08, H * 0.255, a);
    rise(ctx, 'It started', W * 0.078, H * 0.365, span(local, 0.5, 2.4), { size: 86 });
    rise(ctx, 'with a phone.', W * 0.078, H * 0.475, span(local, 0.78, 2.7), { size: 86 });
    /* hairline that draws itself outward */
    const k = ease.outCubic(span(local, 2.2, 3.6));
    ctx.save();
    ctx.fillStyle = GOLD;
    ctx.globalAlpha *= 0.85 * k;
    ctx.fillRect(W * 0.08, H * 0.545, W * 0.16 * k * (1 - b * 0.3), 1);
    ctx.restore();
    capsLine(ctx, '1994', W * 0.08, H * 0.60, span(local, 2.9, 4.0), { size: 12, colour: DIM });
  }

  if (beat.id === 'ring') {
    /* the number, left, against the handset on the right */
    capsLine(ctx, 'ONE IN THREE', W * 0.075, H * 0.30, span(local, 0.3, 1.8), { size: 12 });
    rise(ctx, 'phones', W * 0.072, H * 0.44, span(local, 0.55, 2.2), { size: 104 });
    rise(ctx, 'on earth', W * 0.072, H * 0.565, span(local, 0.85, 2.6), { size: 104, colour: GOLD });
    const k = ease.outCubic(span(local, 1.9, 3.2));
    ctx.save();
    ctx.fillStyle = 'rgba(232,227,214,0.35)';
    ctx.fillRect(W * 0.075, H * 0.655, W * 0.26 * k, 1);
    ctx.restore();
    capsLine(ctx, 'SOLD · 2007', W * 0.075, H * 0.715, span(local, 2.4, 3.6), { size: 12, colour: DIM });
  }

  if (beat.id === 'wide') {
    /* pull back, and let the room be the sentence */
    const a = span(local, 0.6, 2.8);
    capsLine(ctx, 'NOKIA · THE OPENING', W * 0.5, H * 0.235, a, { align: 'center', size: 13 });
    rise(ctx, 'Every pocket', W * 0.5, H * 0.335, span(local, 0.9, 2.9), { size: 62, align: 'center' });
    rise(ctx, 'on earth', W * 0.5, H * 0.408, span(local, 1.15, 3.1), { size: 62, align: 'center', colour: GOLD });
  }

  /* vignette, and a very slight bloom over the whole frame */
  const v = ctx.createRadialGradient(W * 0.5, H * 0.45, H * 0.20, W * 0.5, H * 0.5, H * 0.95);
  v.addColorStop(0, 'rgba(0,0,0,0)');
  v.addColorStop(1, 'rgba(0,0,0,0.62)');
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, W, H);
}

const main = () => {
  const args = process.argv.slice(2);
  const flag = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
  const fonts = loadFonts();
  const fps = Number(flag('--fps') || 30);
  const out = flag('--frames');
  console.log(`room: ${DURATION.toFixed(1)}s, ${fonts} fonts`);
  if (!out) return;
  fs.mkdirSync(out, { recursive: true });
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');
  const total = Math.round(DURATION * fps);
  for (let i = 0; i < total; i += 1) {
    ctx.clearRect(0, 0, W, H);
    drawRoom(ctx, i / fps);
    fs.writeFileSync(path.join(out, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
  }
  console.log(`wrote ${total} frames to ${out}`);
};

if (import.meta.url === `file://${process.argv[1]}`) main();
