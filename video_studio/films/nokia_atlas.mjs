/**
 * Nokia: the opening. Second cut.
 *
 * The first cut was rejected for its look, and the look was one palette and one
 * house style carried through eight shots. This is the same eight lines on the
 * same clock, drawn differently: every shot has its own colour world and its own
 * subject, and every subject is modelled rather than iconified.
 *
 *   1  dark cobalt room      a handset, ringing                     (the hook)
 *   2  amber dusk            a city, in three depths                (a hundred countries)
 *   3  deep teal             the world, one in three               (the claim)
 *   4  graphite / paper      the phone, then the computer           (the turn)
 *   5  near-black            one handset, too much space            (too late)
 *   6  sepia dusk            a mill, a wheel, smoke                 (1865)
 *   7  bone                  four objects on four plinths           (four industries)
 *   8  gold on black         a chart that ends in a handset         (2007)
 *
 * The clock is the film's, not the mixer's: durations come from the voice
 * lengths in vo-timing.json, and `--starts` publishes where every line begins.
 *
 *   node films/nokia_atlas.mjs --frames /tmp/atlas --fps 30 --starts /tmp/st.json
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { drawHandset, drawStudio, drawReflection } from '../motion/kit/product.mjs';
import {
  drawCityscape, drawRooftop, drawSmartphone, drawMill, drawPine, drawPaperReam,
  drawRubberSheet, drawCableDrum, drawChip, drawPlinth, contact,
  drawMotes, drawBreathe,
} from '../motion/kit/objects.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { direct } from '../motion/kit/direction.mjs';
import { optics, frameBuffer, opticsFor } from '../motion/kit/optics.mjs';
import { clamp, lerp, span, ease, noise } from '../motion/ui.mjs';

const W = 1280;
const H = 720;
const HERE = path.dirname(fileURLToPath(import.meta.url));

const SERIF = 'Instrument Serif';
const SANS = 'Inter';
const POSTER = 'Anton';

/* ---------------------------------------------------------------- type ---- */

function text(ctx, value, x, y, {
  size = 40, weight = 400, family = SERIF, colour = '#fff', align = 'left',
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

/**
 * The ring, made visible.
 *
 * The soundtrack rings for the first two seconds. The picture did not: the
 * display was a lit rectangle at a fixed brightness, so the first two seconds of
 * the film were the stillest two seconds in it, over the sound of a phone
 * ringing in a dark room. The screen and the key light now pulse with the tone
 * the score is playing, which is also the cheapest way to say "this is a phone,
 * and it is ringing" before anybody has said a word.
 */
function ringPulse(t) {
  if (t < 0.12 || t > 1.95) return 0;
  const k = Math.max(0, Math.sin((t - 0.12) * Math.PI * 2 * 3.03));
  return k * k;
}

/** A caps line that opens its tracking as it arrives. */
function caps(ctx, value, x, y, p, { size = 12, colour = '#C9A227', align = 'left', from = 2, to = 7 } = {}) {
  const k = ease.outCubic(clamp(p));
  text(ctx, value, x, y, {
    size, weight: 600, family: SANS, colour, align,
    tracking: lerp(from, to, k), alpha: clamp(p * 1.8),
  });
}

/** A display line that rises behind a mask, so it is never caught half-drawn. */
function rise(ctx, value, x, y, p, {
  size = 76, family = SERIF, colour = '#fff', weight = 400, align = 'left', from = 1.1,
} = {}) {
  // A line of type that stops dead at its final position looks pasted on. Two
  // percent of overshoot and a settle reads as weight, and nothing else in the
  // frame has to move for it.
  const x0 = clamp(p);
  const back = 1.7;
  const k = x0 <= 0 ? 0 : x0 >= 1 ? 1
    : 1 + (back + 1) * Math.pow(x0 - 1, 3) + back * Math.pow(x0 - 1, 2);
  ctx.save();
  const w = 1200;
  const left = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x - 24;
  ctx.beginPath();
  ctx.rect(left, y - size * 1.18, w, size * 1.32);
  ctx.clip();
  ctx.globalAlpha *= clamp(p * 2.2);
  ctx.translate(0, (1 - k) * size * from);
  text(ctx, value, x, y, { size, family, colour, weight, align });
  ctx.restore();
}

/** A hairline that draws itself from `x` to `x + len`. */
function rule(ctx, x, y, len, p, colour = '#C9A227', thickness = 1) {
  const k = ease.outCubic(clamp(p));
  ctx.save();
  ctx.fillStyle = colour;
  ctx.globalAlpha *= clamp(p * 2);
  ctx.fillRect(x, y, len * k, thickness);
  ctx.restore();
}

/** Mix two hex colours; used for a liquid-crystal panel going dark. */
function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const v = pa.map((x, i) => Math.round(x + (pb[i] - x) * clamp(t)));
  return `#${v.map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}

/* ------------------------------------------------------------- palette ---- */

const P = {
  cobalt: { ground: '#070C18', mid: '#0D1730', hot: '#2B4A8C', ink: '#EDE9DF', gold: '#C9A227' },
  amber: { ground: '#1A0F0A', mid: '#3E1E12', hot: '#C4571F', ink: '#F4E7D2', gold: '#F0B44A' },
  teal: { ground: '#05100F', mid: '#0B2224', hot: '#1E6E68', ink: '#E9F0E6', gold: '#D8B24A' },
  graphite: { ground: '#0E1013', mid: '#1B1E23', hot: '#2E333B', ink: '#EDEAE2', gold: '#C9A227' },
  bone: { ground: '#EFE9DB', mid: '#DED6C4', hot: '#B8452A', ink: '#16130F', gold: '#B8452A' },
  sepia: { ground: '#191309', mid: '#3A2C16', hot: '#8A6A2A', ink: '#F2E6CC', gold: '#E0B45C' },
  rise: { ground: '#08090B', mid: '#14161A', hot: '#7A5E1C', ink: '#F3EEE2', gold: '#E2B94F' },
};

/* --------------------------------------------------------------- shots ---- */

const LEAD = 0.3;
const LEAD_FIRST = 0.55;
const PAD = { 'hook-01-ringing': 1.4, 'hook-05-alone': 1.5, 'history-02-trades': 1.0, 'history-03-rise': 1.0 };

const SCRIPT = [
  /* 1 ------------------------------------------------------------------- */
  {
    id: 'hook-01-ringing',
    optics: { bloom: 0.55, halation: 0.42, grain: 0.22, vignette: 0.30, threshold: 0.52 },
    palette: { paper: P.cobalt.ground },
    role: 'beat',
    seconds: 3.2,
    background: P.cobalt.ground,
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.05, at: [0.5, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.5, grainAmount: 0.22, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'atmosphere', depth: 1,
        draw: (ctx, { t }) => {
          drawMotes(ctx, { w: W, h: H, t, count: 120, seed: 5, strength: 1.0, focusX: 0.60, focusY: 0.42, focusR: 0.55 });
          drawBreathe(ctx, { w: W, h: H, t, amount: 0.030, cx: 0.52, cy: 0.34, r: 0.62 });
        },
      },
      {
        id: 'room', depth: 1,
        draw: (ctx, { t }) => {
          /* a dark room, lit by one practical, and a handset standing in it */
          const g = ctx.createLinearGradient(0, 0, 0, H * 0.86);
          g.addColorStop(0, P.cobalt.ground);
          g.addColorStop(1, P.cobalt.mid);
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
          drawStudio(ctx, { w: W, h: H, t, horizon: 0.86, intensity: 1.0 + 0.22 * ringPulse(t) });
          const pw = 200;
          const ph = pw * 1.87;
          const bx = W * 0.605;
          const by = H * 0.895;
          const px = bx - pw / 2;
          const py = by - ph;
          const o = { facing: -0.35 + 0.5 * (t / 6), screen: 'ring', glow: 0.82 + 0.55 * ringPulse(t) };
          drawReflection(ctx, () => drawHandset(ctx, { x: px, y: py, w: pw, h: ph, ...o, shadow: false }),
            { h: H, mirrorAt: by, alpha: 0.16 });
          drawHandset(ctx, { x: px, y: py, w: pw, h: ph, ...o });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* The first frame of the film is the most expensive frame it has: a
             viewer decides in about a second and a half. The type used to arrive
             at 0.8 s, which is after the decision. It is on screen by 0.25 s. */
          caps(ctx, 'ESPOO · FINLAND', W * 0.075, H * 0.30, span(p, 0.005, 0.28));
          rise(ctx, 'It starts', W * 0.072, H * 0.44, span(p, 0.01, 0.40), { size: 84 });
          rise(ctx, 'with a phone.', W * 0.072, H * 0.555, span(p, 0.10, 0.55), { size: 84 });
          rule(ctx, W * 0.075, H * 0.625, W * 0.13, span(p, 0.45, 0.85));
          caps(ctx, '1994', W * 0.075, H * 0.685, span(p, 0.55, 0.95), { size: 11, colour: 'rgba(237,233,223,0.45)' });
        },
      },
    ],
  },

  /* 2 ------------------------------------------------------------------- */
  {
    id: 'hook-02-cities',
    optics: { bloom: 0.62, halation: 0.55, grain: 0.24, vignette: 0.26, threshold: 0.44, tint: { r: 1.0, g: 0.62, b: 0.34 } },
    palette: { paper: P.amber.ground },
    role: 'rack',
    seconds: 4,
    background: P.amber.ground,
    camera: (t, dur) => ({ zoom: 1.03 - (t / dur) * 0.05, at: [0.54, 0.52], rotate: 0 }),
    grade: { vignetteStrength: 0.36, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'city', depth: 1,
        draw: (ctx, { p, t, dur }) => {
          /* A city with depth, and a roof to look past.
             The old version was four grey rectangles; at 1080p that read as a bar
             chart on its side. Five layers, each hazier and slower than the one
             in front of it, plus a foreground parapet, is what makes the frame
             have air in it. */
          ctx.fillStyle = P.amber.ground;
          ctx.fillRect(0, 0, W, H);
          drawCityscape(ctx, {
            x: 0, y: 0, w: W, h: H,
            seed: 7,
            p: span(p, 0.02, 0.46),
            t,
            /* the camera drifts right; the near layers go with it */
            parallax: -0.035 * (t / dur),
            layers: 5,
            near: '#0A0604',
            haze: '#8C4A20',
            window: '#FFC46A',
            lit: 0.52,
            horizon: 0.64,
          });
          drawRooftop(ctx, { x: 0, y: 0, w: W, h: H * 0.13, baseline: H * 0.87 });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* The shadow pool was painted *after* the type, in the same layer, so
             it lay over the words and greyed them - and it was too weak to do
             the job it was added for. On screen the headline sat across a lit
             tower and the caption crossed a parapet of lit windows. It is under
             the words now, from the left edge, and the city falls away into it. */
          const sc = ctx.createLinearGradient(0, 0, W * 0.62, 0);
          sc.addColorStop(0, 'rgba(12,7,3,0.90)');
          sc.addColorStop(0.45, 'rgba(12,7,3,0.66)');
          sc.addColorStop(1, 'rgba(12,7,3,0)');
          ctx.fillStyle = sc;
          ctx.fillRect(0, 0, W * 0.62, H);
          const scv = ctx.createLinearGradient(0, 0, 0, H);
          scv.addColorStop(0, 'rgba(12,7,3,0.18)');
          scv.addColorStop(0.62, 'rgba(12,7,3,0)');
          scv.addColorStop(1, 'rgba(12,7,3,0.55)');
          ctx.fillStyle = scv;
          ctx.fillRect(0, 0, W * 0.62, H);

          caps(ctx, 'AT THE SAME MOMENT', W * 0.075, H * 0.215, span(p, 0.08, 0.45), { colour: '#F0B44A' });
          rise(ctx, 'a hundred', W * 0.072, H * 0.345, span(p, 0.12, 0.55), { size: 92, colour: P.amber.ink });
          rise(ctx, 'countries', W * 0.072, H * 0.455, span(p, 0.22, 0.68), { size: 92, colour: P.amber.ink });
        },
      },
      {
        id: 'pocket', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* The caption used to cross a row of lit windows at the foot of the
             towers, where half of it disappeared into the city. It sits on the
             dark ground below the skyline now, which is also the only part of
             the frame that had nothing in it. */
          rule(ctx, W * 0.075, H * 0.755, W * 0.21, span(p, 0.55, 0.9), P.amber.gold);
          caps(ctx, 'IN SOMEONE’S POCKET', W * 0.075, H * 0.815, span(p, 0.62, 1), {
            size: 12, colour: 'rgba(244,231,210,0.72)',
          });
        },
      },
    ],
  },

  /* 3 ------------------------------------------------------------------- */
  {
    id: 'hook-03-world',
    optics: { bloom: 0.40, halation: 0.20, grain: 0.18, vignette: 0.34, threshold: 0.60 },
    palette: { paper: P.teal.ground },
    role: 'time',
    seconds: 4,
    background: P.teal.ground,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.045, at: [0.5, 0.47], rotate: 0 }),
    grade: { vignetteStrength: 0.40, grainAmount: 0.14, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'ocean', depth: 1,
        draw: (ctx) => {
          /* Deep water: a lit centre, dark edges, and a faint band structure -
             a flat teal field made the continents look pasted on. */
          const g = ctx.createRadialGradient(W * 0.46, H * 0.40, 0, W * 0.5, H * 0.5, H * 1.05);
          g.addColorStop(0, '#0E2B2A');
          g.addColorStop(0.45, '#0A2020');
          g.addColorStop(1, '#040F0F');
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
          ctx.save();
          ctx.globalCompositeOperation = 'lighter';
          for (let i = 0; i < 5; i += 1) {
            const yy = H * (0.24 + i * 0.12);
            const lg = ctx.createLinearGradient(0, yy - H * 0.05, 0, yy + H * 0.05);
            lg.addColorStop(0, 'rgba(56,150,140,0)');
            lg.addColorStop(0.5, `rgba(56,150,140,${0.030 - i * 0.004})`);
            lg.addColorStop(1, 'rgba(56,150,140,0)');
            ctx.fillStyle = lg;
            ctx.fillRect(0, yy - H * 0.05, W, H * 0.10);
          }
          ctx.restore();
        },
      },
      {
        id: 'world', depth: 1,
        draw: (ctx, { p }) => {
          drawMap(ctx, {
            x: W * 0.085, y: H * 0.185, w: W * 0.83, h: H * 0.52, p: span(p, 0.02, 0.40),
            projection: 'winkel', graticule: true,
            graticuleColour: 'rgba(120,200,190,0.055)',
            land: 'rgba(32,116,108,0.90)', landEdge: 'rgba(150,224,208,0.62)',
            palette: { land: 'rgba(32,116,108,0.90)', landEdge: 'rgba(150,224,208,0.62)', text: P.teal.ink, caption: P.teal.gold },
            /* the network: every line runs home to Espoo, and they arrive in
               their own time, so the claim is something you can watch happen */
            arcs: [
              { from: 'espoo', to: 'london', t: span(p, 0.34, 0.62), colour: 'rgba(216,178,74,0.55)', width: 1.4, head: false },
              { from: 'espoo', to: 'newyork', t: span(p, 0.40, 0.70), colour: 'rgba(216,178,74,0.50)', width: 1.4, head: false },
              { from: 'espoo', to: 'saopaulo', t: span(p, 0.46, 0.76), colour: 'rgba(216,178,74,0.45)', width: 1.3, head: false },
              { from: 'espoo', to: 'delhi', t: span(p, 0.52, 0.82), colour: 'rgba(216,178,74,0.50)', width: 1.3, head: false },
              { from: 'espoo', to: 'beijing', t: span(p, 0.56, 0.86), colour: 'rgba(216,178,74,0.45)', width: 1.3, head: false },
              { from: 'espoo', to: 'sydney', t: span(p, 0.62, 0.92), colour: 'rgba(216,178,74,0.40)', width: 1.2, head: false },
            ],
            pins: [
              { at: 'espoo', t: span(p, 0.30, 0.50), colour: '#F0C463' },
              { at: 'london', t: span(p, 0.38, 0.56) },
              { at: 'newyork', t: span(p, 0.44, 0.62) },
              { at: 'saopaulo', t: span(p, 0.50, 0.68) },
              { at: 'delhi', t: span(p, 0.56, 0.74) },
              { at: 'beijing', t: span(p, 0.60, 0.78) },
              { at: 'sydney', t: span(p, 0.66, 0.84) },
            ],
          });
        },
      },
      {
        id: 'stat', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, 'SOLD ANYWHERE ON EARTH', W * 0.5, H * 0.115, span(p, 0.3, 0.62), {
            align: 'center', colour: 'rgba(233,240,230,0.62)',
          });
          rise(ctx, 'one in three', W * 0.5, H * 0.845, span(p, 0.42, 0.86), {
            size: 104, align: 'center', colour: P.teal.ink,
          });
          rule(ctx, W * 0.5 - W * 0.10, H * 0.875, W * 0.20, span(p, 0.6, 0.95), P.teal.gold);
        },
      },
    ],
  },

  /* 4 ------------------------------------------------------------------- */
  {
    id: 'hook-04-turn',
    optics: { bloom: 0.48, halation: 0.24, grain: 0.20, vignette: 0.30, threshold: 0.55 },
    palette: { paper: P.graphite.ground },
    role: 'chapter',
    seconds: 4.6,
    background: P.graphite.ground,
    camera: (t, dur) => ({ zoom: 1.0, at: [0.5 + (t / dur) * 0.03, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.30, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'atmosphere', depth: 1,
        draw: (ctx, { t }) => {
          drawMotes(ctx, { w: W, h: H, t, count: 80, seed: 9, strength: 0.7, focusX: 0.5, focusY: 0.45, focusR: 0.7 });
        },
      },
      {
        id: 'fields', depth: 1,
        draw: (ctx) => {
          /* a hard seam down the middle: the old world, the new one */
          ctx.fillStyle = P.graphite.ground;
          ctx.fillRect(0, 0, W, H);
          const g = ctx.createLinearGradient(W * 0.5, 0, W, 0);
          g.addColorStop(0, '#241F1A');
          g.addColorStop(1, '#0B0A09');
          ctx.fillStyle = g;
          ctx.fillRect(W * 0.5, 0, W * 0.5, H);
          ctx.fillStyle = 'rgba(201,162,39,0.55)';
          ctx.fillRect(W * 0.5 - 1, 0, 2, H);
        },
      },
      {
        id: 'old', depth: 1,
        draw: (ctx, { p, t }) => {
          const pw = 236;
          const ph = pw * 1.87;
          const px = W * 0.5 - pw - W * 0.04;
          const py = H * 0.235 + Math.sin(t * 1.1) * 2;
          drawHandset(ctx, { x: px, y: py, w: pw, h: ph, facing: 0.35, screen: 'menu', glow: 0.8 });
          caps(ctx, 'A PHONE', px + 4, H * 0.885, span(p, 0.20, 0.55), { size: 12, colour: 'rgba(237,234,226,0.55)' });
        },
      },
      {
        id: 'new', depth: 1,
        draw: (ctx, { p }) => {
          const pw = 208;
          const ph = pw * 2.03;
          const px = W * 0.5 + W * 0.045;
          const py = H * 0.215;
          const k = ease.outCubic(span(p, 0.10, 0.55));
          ctx.save();
          ctx.globalAlpha *= clamp(k * 1.6);
          ctx.translate(0, (1 - k) * 40);
          drawSmartphone(ctx, { x: px, y: py, w: pw, h: ph, glow: 1 });
          ctx.restore();
          caps(ctx, 'A COMPUTER', px + 4, H * 0.885, span(p, 0.28, 0.62), { size: 12, colour: P.graphite.gold });
        },
      },
      {
        id: 'line', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* The seam ran straight through the headline - a gold rule through
             the middle of a word. The line breaks across it now: the old
             sentence to the left of the divide, the new one to the right, which
             is the same idea the shot is about, made in type. */
          rise(ctx, 'Then it stopped', W * 0.5 - 26, H * 0.090, span(p, 0.26, 0.62), {
            size: 36, align: 'right', colour: P.graphite.ink,
          });
          rise(ctx, 'being a phone.', W * 0.5 + 26, H * 0.163, span(p, 0.36, 0.74), {
            size: 36, align: 'left', colour: P.graphite.gold,
          });
        },
      },
    ],
  },

  /* 5 ------------------------------------------------------------------- */
  {
    id: 'hook-05-alone',
    optics: { bloom: 0.40, halation: 0.30, grain: 0.26, vignette: 0.46, threshold: 0.48 },
    palette: { paper: '#060607' },
    role: 'beat',
    seconds: 3.4,
    background: '#060607',
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.03, at: [0.46, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.62, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'atmosphere', depth: 1,
        draw: (ctx, { t }) => {
          drawMotes(ctx, { w: W, h: H, t, count: 60, seed: 13, strength: 0.55, focusX: 0.28, focusY: 0.62, focusR: 0.5 });
        },
      },
      {
        id: 'void', depth: 1,
        draw: (ctx) => {
          ctx.fillStyle = '#060607';
          ctx.fillRect(0, 0, W, H);
          const g = ctx.createRadialGradient(W * 0.30, H * 0.42, 0, W * 0.34, H * 0.5, H * 0.72);
          g.addColorStop(0, 'rgba(74,72,66,0.70)');
          g.addColorStop(1, 'rgba(6,6,7,0)');
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
        },
      },
      {
        id: 'shelf', depth: 1,
        draw: (ctx, { p, t }) => {
          /* Lying on its side on a shelf: the object that was the whole film, now
             just an object.

             The shot used to be a still of that idea for six seconds. It has a
             beat now, and the beat is the line: the display dims, and goes out
             before the cut. A phone answering too late is a screen with nothing
             left on it. */
          const pw = 196;
          const ph = pw * 1.87;
          const px = W * 0.145;
          const py = H * 0.665;
          /* settles the last two degrees, rather than sitting dead still */
          const settle = Math.PI / 2 - 0.035 * (1 - ease.outCubic(clamp(p * 3)));
          const dying = clamp(span(p, 0.34, 0.94));
          const glow = 0.45 * (1 - dying);
          const lcd = mix('#8FA88A', '#151A16', dying);
          ctx.save();
          ctx.globalAlpha *= clamp(p * 3);
          contact(ctx, px + ph / 2, H * 0.945, ph * 0.60, H * 0.030, 0.60);
          ctx.translate(px + ph / 2, py);
          ctx.rotate(-settle);
          drawHandset(ctx, {
            x: -pw / 2, y: -ph / 2, w: pw, h: ph, facing: 0.2,
            screen: 'menu', glow, lcd, shadow: false,
          });
          ctx.restore();
          rule(ctx, W * 0.115, H * 0.958, W * 0.34, span(p, 0.3, 0.8), 'rgba(237,234,226,0.18)');

          /* the room loses its key light as the screen does, so the shot is
             darker at its cut than at its start without anything moving */
          const dim = dying * 0.42;
          if (dim > 0) {
            ctx.save();
            ctx.globalAlpha *= dim;
            ctx.fillStyle = '#04040A';
            ctx.fillRect(-W, -H, W * 3, H * 3);
            ctx.restore();
          }
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          rise(ctx, 'It answered', W * 0.928, H * 0.40, span(p, 0.34, 0.74), {
            size: 76, align: 'right', colour: '#EDEAE2',
          });
          rise(ctx, 'too late.', W * 0.928, H * 0.515, span(p, 0.46, 0.86), {
            size: 76, align: 'right', colour: 'rgba(237,234,226,0.55)',
          });
          caps(ctx, 'NOKIA · 2007 — 2013', W * 0.928, H * 0.60, span(p, 0.62, 1), {
            align: 'right', size: 11, colour: 'rgba(237,234,226,0.35)', from: 3, to: 8,
          });
        },
      },
    ],
  },

  /* 6 ------------------------------------------------------------------- */
  {
    id: 'history-01-mill',
    optics: { bloom: 0.58, halation: 0.50, grain: 0.26, vignette: 0.34, threshold: 0.42, tint: { r: 1.0, g: 0.66, b: 0.36 } },
    palette: { paper: P.sepia.ground },
    role: 'era',
    seconds: 4.6,
    background: P.sepia.ground,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.06, at: [0.52, 0.54], rotate: 0 }),
    grade: { vignetteStrength: 0.42, grainAmount: 0.26, paper: false, riso: 0, tooth: 0.05 },
    layers: [
      {
        id: 'atmosphere', depth: 1,
        draw: (ctx, { t }) => {
          drawMotes(ctx, { w: W, h: H, t, count: 70, seed: 21, strength: 0.55, focusX: 0.55, focusY: 0.62, focusR: 0.55 });
          drawBreathe(ctx, { w: W, h: H, t, amount: 0.022, colour: '255,196,120', cx: 0.52, cy: 0.66, r: 0.5 });
        },
      },
      {
        id: 'dusk', depth: 1,
        draw: (ctx, { p, t }) => {
          const sky = ctx.createLinearGradient(0, 0, 0, H);
          sky.addColorStop(0, '#120D07');
          sky.addColorStop(0.55, P.sepia.mid);
          sky.addColorStop(1, '#0D0906');
          ctx.fillStyle = sky;
          ctx.fillRect(0, 0, W, H);
          /* a cold moon, low, behind the trees */
          const mx = W * 0.14;
          const my = H * 0.20;
          const mg = ctx.createRadialGradient(mx, my, 0, mx, my, H * 0.30);
          mg.addColorStop(0, 'rgba(240,232,210,0.50)');
          mg.addColorStop(0.12, 'rgba(240,232,210,0.18)');
          mg.addColorStop(1, 'rgba(240,232,210,0)');
          ctx.fillStyle = mg;
          ctx.fillRect(0, 0, W, H);

          const k = span(p, 0.0, 0.55);
          /* Three pines of one shape at three sizes read as a wallpaper, and a
             print of one at the edge of the frame crossed the headline. The
             treeline is now a far one - small, hazed, six of them, no two the
             same height or lean - and the only near tree is off the frame edge
             on the right, where the type cannot reach it. */
          const far = [
            [W * -0.04, H * 0.345, 74, H * 0.40, 4, -0.02],
            [W * 0.045, H * 0.315, 88, H * 0.44, 5, 0.016],
            [W * 0.60, H * 0.345, 76, H * 0.40, 6, 0.02],
            [W * 0.655, H * 0.30, 90, H * 0.45, 4, -0.014],
            [W * 0.905, H * 0.325, 96, H * 0.43, 5, 0.012],
            [W * 0.985, H * 0.365, 68, H * 0.36, 6, 0.0],
          ];
          for (const [tx, ty, tw, th, tiers, lean] of far) {
            drawPine(ctx, {
              x: tx, y: ty, w: tw, h: th, tiers, lean,
              colour: '#191309', dark: '#0C0904', rim: 'rgba(196,182,150,0.05)',
            });
          }
          contact(ctx, W * 0.55, H * 0.955, W * 0.30, H * 0.026, 0.55);
          drawMill(ctx, { x: W * 0.24, y: H * 0.16, w: W * 0.58, h: H * 0.80, t, smoke: k, wheel: k });
        },
      },
      {
        id: 'near', depth: 2,
        draw: (ctx, { p, t }) => {
          /* The foreground. Until this existed the mill floated: the frame had
             sky, building and water, and nothing between the lens and the
             subject. Mist sits on the water at the building's foot and a bank of
             reeds crosses the bottom corner - two more planes, and the shot has
             depth without the building moving a pixel. */
          ctx.save();
          const mist = ctx.createLinearGradient(0, H * 0.78, 0, H * 0.96);
          mist.addColorStop(0, 'rgba(196,170,140,0)');
          mist.addColorStop(0.55, 'rgba(196,170,140,0.10)');
          mist.addColorStop(1, 'rgba(150,132,112,0.16)');
          ctx.fillStyle = mist;
          ctx.fillRect(0, H * 0.78, W, H * 0.20);
          ctx.globalCompositeOperation = 'lighter';
          for (let i = 0; i < 7; i += 1) {
            const yy = H * (0.82 + i * 0.021);
            const drift = Math.sin(t * 0.22 + i * 1.3) * W * 0.02;
            const g = ctx.createLinearGradient(0, yy - H * 0.02, 0, yy + H * 0.02);
            g.addColorStop(0, 'rgba(226,196,158,0)');
            g.addColorStop(0.5, `rgba(226,196,158,${0.035 - i * 0.003})`);
            g.addColorStop(1, 'rgba(226,196,158,0)');
            ctx.fillStyle = g;
            ctx.fillRect(drift - W * 0.05, yy - H * 0.02, W * 1.1, H * 0.04);
          }
          ctx.restore();

          /* the bank itself: a dark mass, soft at its top edge, reeds against
             the water light */
          ctx.save();
          const bank = ctx.createLinearGradient(0, H * 0.955, 0, H);
          bank.addColorStop(0, 'rgba(5,5,4,0)');
          bank.addColorStop(0.45, 'rgba(5,5,4,0.55)');
          bank.addColorStop(1, 'rgba(3,3,3,0.92)');
          ctx.fillStyle = bank;
          ctx.fillRect(0, H * 0.94, W, H * 0.06);
          const grow = ease.outCubic(clamp(p * 2.2));
          ctx.strokeStyle = 'rgba(6,6,5,0.9)';
          for (let i = 0; i < 44; i += 1) {
            const r = noise(i * 7.7 + 3);
            const rx = (i < 26 ? 0.63 + r * 0.40 : -0.01 + r * 0.07) * W;
            const rh = H * (0.05 + r * 0.13);
            const tip = H * 0.985 - rh * grow;
            ctx.lineWidth = 1 + r * 1.6;
            ctx.beginPath();
            ctx.moveTo(rx, H * 1.005);
            ctx.quadraticCurveTo(rx + (r - 0.5) * 26, H * 0.985 - rh * 0.5 * grow, rx + (r - 0.5) * 52, tip);
            ctx.stroke();
            /* a head, so it is a reed and not a scratch */
            if (r > 0.55) {
              ctx.fillStyle = 'rgba(6,6,5,0.85)';
              ctx.beginPath();
              ctx.ellipse(rx + (r - 0.5) * 52, tip, 1.6 + r * 1.4, 5 + r * 5, (r - 0.5) * 0.4, 0, Math.PI * 2);
              ctx.fill();
              ctx.strokeStyle = 'rgba(6,6,5,0.9)';
            }
          }
          ctx.restore();
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, 'TAMPERE · FINLAND', W * 0.075, H * 0.175, span(p, 0.22, 0.55), { colour: P.sepia.gold });
          /* The year is set, not sprayed over the picture. As a 300px ghost it
             covered the roof and made the building look like a mistake. */
          rise(ctx, '1865', W * 0.074, H * 0.795, span(p, 0.30, 0.68), {
            size: 46, colour: P.sepia.gold,
          });
          rise(ctx, 'It began with', W * 0.072, H * 0.255, span(p, 0.28, 0.66), { size: 50, colour: P.sepia.ink });
          rise(ctx, 'a paper mill.', W * 0.072, H * 0.335, span(p, 0.38, 0.76), { size: 50, colour: P.sepia.ink });
        },
      },
    ],
  },

  /* 7 ------------------------------------------------------------------- */
  {
    id: 'history-02-trades',
    optics: { bloom: 0.22, halation: 0.10, grain: 0.16, vignette: 0.18, threshold: 0.72 },
    palette: { paper: P.bone.ground },
    role: 'motion',
    seconds: 4.6,
    background: P.bone.ground,
    camera: (t, dur) => ({ zoom: 1.02, at: [0.5, 0.52], rotate: 0 }),
    grade: { vignetteStrength: 0.16, grainAmount: 0.10, paper: false, riso: 0, tooth: 0.05 },
    layers: [
      {
        id: 'wall', depth: 1,
        draw: (ctx) => {
          ctx.fillStyle = P.bone.ground;
          ctx.fillRect(0, 0, W, H);
          const g = ctx.createLinearGradient(0, 0, 0, H);
          g.addColorStop(0, 'rgba(0,0,0,0.06)');
          g.addColorStop(0.5, 'rgba(255,255,255,0)');
          g.addColorStop(1, 'rgba(0,0,0,0.10)');
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
        },
      },
      {
        id: 'objects', depth: 1,
        draw: (ctx, { p, t }) => {
          /* A row of objects on plinths is a still life, and a still life on
             screen is a photograph of a still life unless the light moves. The
             shadows lean as the key light crosses the wall, and a soft shaft
             travels with it - thirty seconds of nothing else moving would be a
             pause in the film, not a shot in it. */
          const sweep = 0.30 + 0.45 * (t / 6);
          ctx.save();
          ctx.globalCompositeOperation = 'lighter';
          const shaft = ctx.createLinearGradient(W * (sweep - 0.22), H * 0.10, W * (sweep + 0.18), H * 0.95);
          shaft.addColorStop(0, 'rgba(255,244,220,0)');
          shaft.addColorStop(0.5, 'rgba(255,244,220,0.055)');
          shaft.addColorStop(1, 'rgba(255,244,220,0)');
          ctx.fillStyle = shaft;
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
          const items = [
            ['PAPER', (x, y, w, h) => drawPaperReam(ctx, { x, y, w, h })],
            ['RUBBER', (x, y, w, h) => drawRubberSheet(ctx, { x, y, w, h })],
            ['CABLE', (x, y, w, h) => drawCableDrum(ctx, { x, y, w, h })],
            ['ELECTRONICS', (x, y, w, h) => drawChip(ctx, { x, y, w, h })],
          ];
          items.forEach(([label, draw], i) => {
            const k = ease.outCubic(clamp(span(p, 0.10 + i * 0.11, 0.46 + i * 0.11)));
            const cx = W * (0.155 + i * 0.23);
            const size = 136;
            const top = H * 0.30;
            ctx.save();
            ctx.globalAlpha *= clamp(k * 1.5);
            contact(ctx, cx + Math.sin(t * 0.45 + i * 0.9) * 7, top + size + 16, size * 0.64, 12, 0.16);
            ctx.translate(cx, top + size / 2 + (1 - k) * 26);
            draw(-size / 2, -size / 2, size, size);
            ctx.restore();
            /* the plinth line and the label */
            rule(ctx, cx - size * 0.62, top + size + 22, size * 1.24, span(p, 0.16 + i * 0.11, 0.5 + i * 0.11),
              'rgba(22,19,15,0.35)');
            text(ctx, label, cx, top + size + 56, {
              size: 11, weight: 700, family: SANS, colour: 'rgba(22,19,15,0.62)',
              align: 'center', tracking: 3.4, alpha: clamp(span(p, 0.2 + i * 0.11, 0.55 + i * 0.11) * 1.6),
            });
          });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, '1865 — 1990', W * 0.5, H * 0.115, span(p, 0.05, 0.35), {
            align: 'center', colour: 'rgba(184,69,42,0.85)',
          });
          rise(ctx, 'Four industries. One company.', W * 0.5, H * 0.90, span(p, 0.55, 0.95), {
            size: 40, align: 'center', colour: 'rgba(22,19,15,0.86)',
          });
        },
      },
    ],
  },

  /* 8 ------------------------------------------------------------------- */
  {
    id: 'history-03-rise',
    optics: { bloom: 0.66, halation: 0.42, grain: 0.20, vignette: 0.28, threshold: 0.46, tint: { r: 1.0, g: 0.74, b: 0.40 } },
    palette: { paper: P.rise.ground },
    role: 'momentum',
    seconds: 4.4,
    background: P.rise.ground,
    camera: (t, dur) => ({ zoom: 1.06 - (t / dur) * 0.06, at: [0.55, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.40, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'atmosphere', depth: 1,
        draw: (ctx, { t }) => {
          drawMotes(ctx, { w: W, h: H, t, count: 55, seed: 27, strength: 0.45, focusX: 0.6, focusY: 0.5, focusR: 0.6 });
        },
      },
      {
        id: 'bars', depth: 1,
        draw: (ctx, { p, t }) => {
          const g = ctx.createLinearGradient(0, 0, 0, H);
          g.addColorStop(0, P.rise.ground);
          g.addColorStop(1, '#101216');
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);

          const floorY = H * 0.86;
          const bars = [0.10, 0.16, 0.24, 0.33, 0.46, 0.62, 0.80];
          const bw = W * 0.072;
          const gap = W * 0.021;
          const total = bars.length * bw + (bars.length - 1) * gap;
          const x0 = W * 0.5 - total / 2 + W * 0.06;
          for (let i = 0; i < bars.length; i += 1) {
            const k = ease.outCubic(clamp(span(p, 0.04 + i * 0.075, 0.44 + i * 0.075)));
            const bh = (floorY - H * 0.20) * bars[i] * k;
            const bx = x0 + i * (bw + gap);
            const by = floorY - bh;
            const bg = ctx.createLinearGradient(bx, by, bx + bw, by);
            bg.addColorStop(0, 'rgba(226,185,79,0.95)');
            bg.addColorStop(0.55, 'rgba(160,118,32,0.95)');
            bg.addColorStop(1, 'rgba(96,70,18,0.95)');
            ctx.fillStyle = bg;
            ctx.fillRect(bx, by, bw, bh);
            /* cap light on each bar */
            ctx.fillStyle = 'rgba(255,232,170,0.55)';
            ctx.fillRect(bx, by, bw, 2);
            /* and a highlight travelling across the face of the bar, out of
               step with its neighbour, so a chart that has finished growing is
               still a surface with light on it */
            const sweepX = bx + bw * (0.15 + 0.7 * (0.5 + 0.5 * Math.sin(t * 0.55 + i * 0.8)));
            const sw = ctx.createLinearGradient(sweepX - bw * 0.35, 0, sweepX + bw * 0.35, 0);
            sw.addColorStop(0, 'rgba(255,236,180,0)');
            sw.addColorStop(0.5, 'rgba(255,236,180,0.16)');
            sw.addColorStop(1, 'rgba(255,236,180,0)');
            ctx.fillStyle = sw;
            ctx.fillRect(bx, by, bw, bh);
          }
          /* the baseline */
          ctx.fillStyle = 'rgba(243,238,226,0.16)';
          ctx.fillRect(x0 - W * 0.02, floorY, total + W * 0.04, 1);
          /* the last bar carries the handset */
          const lastX = x0 + (bars.length - 1) * (bw + gap);
          const k = ease.outCubic(clamp(span(p, 0.52, 0.86)));
          ctx.save();
          ctx.globalAlpha = k;
          const pw = 74;
          const ph = pw * 1.87;
          drawHandset(ctx, {
            x: lastX + bw / 2 - pw / 2, y: floorY - (floorY - H * 0.20) * 0.80 - ph - 14,
            w: pw, h: ph, facing: 0.25, screen: 'menu', glow: 0.9, shadow: false,
          });
          ctx.restore();
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, 'BY 2007', W * 0.075, H * 0.185, span(p, 0.05, 0.35), { colour: P.rise.gold });
          rise(ctx, 'the largest', W * 0.072, H * 0.315, span(p, 0.10, 0.48), { size: 78, colour: P.rise.ink });
          rise(ctx, 'phone maker', W * 0.072, H * 0.425, span(p, 0.20, 0.60), { size: 78, colour: P.rise.ink });
          rise(ctx, 'on earth.', W * 0.072, H * 0.535, span(p, 0.30, 0.70), { size: 78, colour: P.rise.gold });
        },
      },
    ],
  },
];

/* ----------------------------------------------------------- the clock ---- */

function readTiming() {
  try {
    return JSON.parse(fs.readFileSync(new URL('./vo-timing.json', import.meta.url), 'utf8'));
  } catch {
    return null;
  }
}

/**
 * The picture can be locked.
 *
 * `nokia_atlas.lock.json` records the duration of every shot in a cut that has
 * already been approved. When it is present, a re-recorded voice is *conformed*
 * to that cut instead of re-cutting the film around the new read - which is what
 * happens in a real edit, and what stops a calmer narrator from silently
 * changing the pacing of a picture nobody complained about.
 *
 * A line that no longer fits the locked shot is an error, not a warning: the
 * alternative is a cut that lands in the middle of a word.
 */
function readLock() {
  try {
    const rows = JSON.parse(fs.readFileSync(new URL('./nokia_atlas.lock.json', import.meta.url), 'utf8'));
    return Object.fromEntries(rows.map((r) => [r.id, r.dur]));
  } catch {
    return null;
  }
}

function retime(shots, timing) {
  if (!timing) return shots;
  const lock = readLock();
  const spoken = Object.fromEntries(timing.map((r) => [r.shot, r.vo]));
  return shots.map((shot, i) => {
    const vo = spoken[shot.id];
    if (vo === undefined) return shot;
    const lead = i === 0 ? LEAD_FIRST : LEAD;
    const natural = Math.max(shot.seconds, lead + vo + (PAD[shot.id] ?? 1.2));
    if (lock && lock[shot.id] !== undefined) {
      const dur = lock[shot.id];
      if (lead + vo > dur + 1e-6) {
        throw new Error(
          `${shot.id}: the line needs ${(lead + vo).toFixed(2)}s but the locked shot is ${dur.toFixed(2)}s`,
        );
      }
      return { ...shot, dur, conformed: true };
    }
    return { ...shot, dur: Math.round(natural * 10) / 10 };
  });
}

const TIMED = retime(SCRIPT, readTiming());

/**
 * Joins come from the director, not from a pool: a cut where something changes,
 * a dissolve where the same frame is held, an iris where a period opens, a
 * push where the film travels. The rule is still one technique per film.
 */
export const FILM = direct(TIMED.map((s) => ({ ...s, transitionRole: s.role }))).map((s) => ({
  ...s,
  transitionInLabel: s.transition ? s.transition.label : 'cut',
}));

export function shotStarts(shots = FILM) {
  let at = 0;
  return shots.map((s, i) => {
    const row = {
      id: s.id,
      start: Math.round(at * 1000) / 1000,
      end: Math.round((at + s.dur) * 1000) / 1000,
      voStart: Math.round((at + (i === 0 ? LEAD_FIRST : LEAD)) * 1000) / 1000,
      transition: s.transitionInLabel || 'cut',
      transitionWhy: s.transitionWhy || '',
    };
    at += s.dur;
    return row;
  });
}

/** The shot that owns time `t`, for per-shot light. */
export function shotAt(t, shots = FILM) {
  let at = 0;
  for (const shot of shots) {
    if (t < at + shot.dur) return shot;
    at += shot.dur;
  }
  return shots[shots.length - 1];
}

export function totalSeconds(shots = FILM) {
  return shots.reduce((a, s) => a + s.dur, 0);
}

/* ---------------------------------------------------------------- size ---- */

export const SIZE = { W, H };

const main = () => {
  const args = process.argv.slice(2);
  const flag = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
  const fonts = loadFonts();
  const fps = Number(flag('--fps') || 30);
  const scale = Number(flag('--scale') || 1);
  const framesDir = flag('--frames');
  const stills = flag('--stills');
  const startsPath = flag('--starts');
  const dw = Math.round(W * scale);
  const dh = Math.round(H * scale);

  if (startsPath) {
    const rows = shotStarts().map((row, i) => ({ ...row, vo: (readTiming() || [])[i]?.vo ?? null }));
    fs.writeFileSync(path.resolve(startsPath), JSON.stringify(rows, null, 2));
    console.log(`wrote ${startsPath} (${totalSeconds().toFixed(1)}s total)`);
  }

  const canvas = createCanvas(dw, dh);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background, scale });
  /* The optics need the finished frame to measure; this buffer is that copy. */
  const fb = frameBuffer(dw, dh);

  const paint = (t) => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, dw, dh);
    renderer.render(ctx, t);
    fb.ctx.setTransform(1, 0, 0, 1, 0, 0);
    fb.ctx.clearRect(0, 0, dw, dh);
    fb.ctx.drawImage(canvas, 0, 0);
    const shot = shotAt(t);
    optics(ctx, {
      source: fb.canvas, w: dw, h: dh, frame: Math.round(t * fps),
      ...opticsFor(shot),
    });
  };

  if (stills) {
    fs.mkdirSync(stills, { recursive: true });
    const rows = shotStarts();
    rows.forEach((row, i) => {
      const t = row.start + (row.end - row.start) * 0.78;
      paint(t);
      fs.writeFileSync(path.join(stills, `${String(i).padStart(2, '0')}-${FILM[i].id}.png`), canvas.toBuffer('image/png'));
    });
    console.log(`wrote ${rows.length} stills to ${stills}`);
    return;
  }

  if (framesDir) {
    fs.mkdirSync(framesDir, { recursive: true });
    const total = Math.round(renderer.duration * fps);
    for (let i = 0; i < total; i += 1) {
      paint(i / fps);
      fs.writeFileSync(path.join(framesDir, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
    }
    console.log(`wrote ${total} frames to ${framesDir}`);
    return;
  }

  const conformed = FILM.filter((s) => s.conformed).length;
  console.log(
    `${FILM.length} shots, ${totalSeconds().toFixed(1)}s, ${fonts} fonts` +
    (conformed ? ` (${conformed} conformed to the locked picture)` : ''),
  );
  shotStarts().forEach((s) => console.log(
    `  ${s.start.toFixed(1)}s  ${s.id.padEnd(20)} ${(s.end - s.start).toFixed(1)}s  [${s.transition}] ${s.transitionWhy}`,
  ));
};

if (import.meta.url === `file://${process.argv[1]}`) main();
