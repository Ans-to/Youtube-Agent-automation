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
  drawSkyline, drawSmartphone, drawMill, drawPine, drawPaperReam,
  drawRubberSheet, drawCableDrum, drawChip, drawPlinth, contact,
} from '../motion/kit/objects.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { direct } from '../motion/kit/direction.mjs';
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
  const k = ease.outQuint(clamp(p));
  ctx.save();
  const w = 1200;
  const x0 = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x - 24;
  ctx.beginPath();
  ctx.rect(x0, y - size * 1.18, w, size * 1.32);
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
    palette: { paper: P.cobalt.ground },
    role: 'beat',
    seconds: 3.2,
    background: P.cobalt.ground,
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.05, at: [0.5, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.5, grainAmount: 0.22, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'room', depth: 1,
        draw: (ctx, { t }) => {
          /* a dark room, lit by one practical, and a handset standing in it */
          const g = ctx.createLinearGradient(0, 0, 0, H * 0.86);
          g.addColorStop(0, P.cobalt.ground);
          g.addColorStop(1, P.cobalt.mid);
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
          drawStudio(ctx, { w: W, h: H, t, horizon: 0.86, intensity: 1.0 });
          const pw = 200;
          const ph = pw * 1.87;
          const bx = W * 0.605;
          const by = H * 0.895;
          const px = bx - pw / 2;
          const py = by - ph;
          const o = { facing: -0.35 + 0.5 * (t / 6), screen: 'ring', glow: 1 };
          drawReflection(ctx, () => drawHandset(ctx, { x: px, y: py, w: pw, h: ph, ...o, shadow: false }),
            { h: H, mirrorAt: by, alpha: 0.16 });
          drawHandset(ctx, { x: px, y: py, w: pw, h: ph, ...o });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, 'ESPOO · FINLAND', W * 0.075, H * 0.30, span(p, 0.10, 0.5));
          rise(ctx, 'It starts', W * 0.072, H * 0.44, span(p, 0.14, 0.62), { size: 84 });
          rise(ctx, 'with a phone.', W * 0.072, H * 0.555, span(p, 0.24, 0.72), { size: 84 });
          rule(ctx, W * 0.075, H * 0.625, W * 0.13, span(p, 0.45, 0.85));
          caps(ctx, '1994', W * 0.075, H * 0.685, span(p, 0.55, 0.95), { size: 11, colour: 'rgba(237,233,223,0.45)' });
        },
      },
    ],
  },

  /* 2 ------------------------------------------------------------------- */
  {
    id: 'hook-02-cities',
    palette: { paper: P.amber.ground },
    role: 'rack',
    seconds: 4,
    background: P.amber.ground,
    camera: (t, dur) => ({ zoom: 1.04 - (t / dur) * 0.06, at: [0.58, 0.52], rotate: 0 }),
    grade: { vignetteStrength: 0.44, grainAmount: 0.22, paper: false, riso: 0, tooth: 0.04 },
    layers: [
      {
        id: 'city', depth: 1,
        draw: (ctx, { p, t }) => {
          const sky = ctx.createLinearGradient(0, 0, 0, H * 0.78);
          sky.addColorStop(0, '#0B0705');
          sky.addColorStop(0.30, '#4A2312');
          sky.addColorStop(0.62, '#A34A1C');
          sky.addColorStop(1, '#D9762E');
          ctx.fillStyle = sky;
          ctx.fillRect(0, 0, W, H);
          /* a low sun behind the skyline */
          const sunX = W * 0.30;
          const sunY = H * 0.70;
          const halo = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, H * 0.52);
          halo.addColorStop(0, 'rgba(255,214,140,0.72)');
          halo.addColorStop(0.26, 'rgba(250,176,90,0.26)');
          halo.addColorStop(1, 'rgba(224,140,60,0)');
          ctx.fillStyle = halo;
          ctx.fillRect(0, 0, W, H);
          ctx.save();
          ctx.globalCompositeOperation = 'lighter';
          ctx.fillStyle = 'rgba(244,196,120,0.10)';
          ctx.fillRect(0, H * 0.735, W, 2);
          ctx.restore();
          /* three depths of city, each arriving on its own easing */
          drawSkyline(ctx, { x: -40, y: H * 0.40, w: W * 1.08, h: H * 0.60, seed: 7, layers: 3, p: span(p, 0.02, 0.5), near: '#090604', far: '#241109', window: '#FFC46A' });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          caps(ctx, 'AT THE SAME MOMENT', W * 0.075, H * 0.215, span(p, 0.08, 0.45), { colour: P.amber.gold });
          rise(ctx, 'a hundred', W * 0.072, H * 0.345, span(p, 0.12, 0.55), { size: 92, colour: P.amber.ink });
          rise(ctx, 'countries', W * 0.072, H * 0.455, span(p, 0.22, 0.68), { size: 92, colour: P.amber.ink });
          /* the type sits in a pool of shadow that darkens the sky under it, so
             it keeps its contrast without a visible rectangle over the city */
          ctx.save();
          const sc = ctx.createRadialGradient(W * 0.06, H * 0.36, 0, W * 0.10, H * 0.40, W * 0.56);
          sc.addColorStop(0, 'rgba(10,6,3,0.72)');
          sc.addColorStop(0.55, 'rgba(10,6,3,0.30)');
          sc.addColorStop(1, 'rgba(10,6,3,0)');
          ctx.fillStyle = sc;
          ctx.fillRect(0, 0, W * 0.72, H);
          ctx.restore();
        },
      },
      {
        id: 'pocket', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          rule(ctx, W * 0.075, H * 0.535, W * 0.21, span(p, 0.55, 0.9), P.amber.gold);
          caps(ctx, 'IN SOMEONE’S POCKET', W * 0.075, H * 0.60, span(p, 0.62, 1), {
            size: 12, colour: 'rgba(244,231,210,0.62)',
          });
        },
      },
    ],
  },

  /* 3 ------------------------------------------------------------------- */
  {
    id: 'hook-03-world',
    palette: { paper: P.teal.ground },
    role: 'time',
    seconds: 4,
    background: P.teal.ground,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.05, at: [0.5, 0.48], rotate: 0 }),
    grade: { vignetteStrength: 0.46, grainAmount: 0.18, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'world', depth: 1,
        draw: (ctx, { p }) => {
          const g = ctx.createRadialGradient(W * 0.5, H * 0.45, 0, W * 0.5, H * 0.5, H * 0.95);
          g.addColorStop(0, P.teal.mid);
          g.addColorStop(1, P.teal.ground);
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
          drawMap(ctx, {
            x: W * 0.10, y: H * 0.14, w: W * 0.80, h: H * 0.58, p: span(p, 0.02, 0.42),
            projection: 'winkel', graticule: true,
            graticuleColour: 'rgba(233,240,230,0.055)',
            land: 'rgba(30,110,104,0.92)', landEdge: 'rgba(120,200,190,0.55)',
            palette: { land: 'rgba(30,110,104,0.92)', landEdge: 'rgba(120,200,190,0.55)', text: P.teal.ink, caption: P.teal.gold },
            pins: [
              { lon: 23.76, lat: 61.5, r: 5.5, colour: P.teal.gold },
              { lon: -0.13, lat: 51.5, r: 4.5, colour: P.teal.gold },
              { lon: 77.2, lat: 28.6, r: 4.5, colour: P.teal.gold },
              { lon: -46.6, lat: -23.5, r: 4.2, colour: P.teal.gold },
              { lon: 151.2, lat: -33.9, r: 4.2, colour: P.teal.gold },
            ],
          });
        },
      },
      {
        id: 'stat', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* the number, enormous, knocked out of the bottom of the frame */
          caps(ctx, 'SOLD ANYWHERE ON EARTH', W * 0.5, H * 0.115, span(p, 0.3, 0.62), {
            align: 'center', colour: 'rgba(233,240,230,0.66)',
          });
          rise(ctx, 'one in three', W * 0.5, H * 0.855, span(p, 0.42, 0.86), {
            size: 104, align: 'center', colour: P.teal.ink,
          });
          rule(ctx, W * 0.5 - W * 0.10, H * 0.885, W * 0.20, span(p, 0.6, 0.95), P.teal.gold);
        },
      },
    ],
  },

  /* 4 ------------------------------------------------------------------- */
  {
    id: 'hook-04-turn',
    palette: { paper: P.graphite.ground },
    role: 'chapter',
    seconds: 4.6,
    background: P.graphite.ground,
    camera: (t, dur) => ({ zoom: 1.0, at: [0.5 + (t / dur) * 0.03, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.30, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
    layers: [
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
          rise(ctx, 'Then it stopped', W * 0.5, H * 0.090, span(p, 0.26, 0.62), {
            size: 36, align: 'center', colour: P.graphite.ink,
          });
          rise(ctx, 'being a phone.', W * 0.5, H * 0.163, span(p, 0.36, 0.74), {
            size: 36, align: 'center', colour: P.graphite.gold,
          });
        },
      },
    ],
  },

  /* 5 ------------------------------------------------------------------- */
  {
    id: 'hook-05-alone',
    palette: { paper: '#060607' },
    role: 'beat',
    seconds: 3.4,
    background: '#060607',
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.03, at: [0.46, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.62, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
    layers: [
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
          rise(ctx, 'It answered', W * 0.955, H * 0.40, span(p, 0.34, 0.74), {
            size: 76, align: 'right', colour: '#EDEAE2',
          });
          rise(ctx, 'too late.', W * 0.955, H * 0.515, span(p, 0.46, 0.86), {
            size: 76, align: 'right', colour: 'rgba(237,234,226,0.55)',
          });
          caps(ctx, 'NOKIA · 2007 — 2013', W * 0.955, H * 0.60, span(p, 0.62, 1), {
            align: 'right', size: 11, colour: 'rgba(237,234,226,0.35)', from: 3, to: 8,
          });
        },
      },
    ],
  },

  /* 6 ------------------------------------------------------------------- */
  {
    id: 'history-01-mill',
    palette: { paper: P.sepia.ground },
    role: 'era',
    seconds: 4.6,
    background: P.sepia.ground,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.06, at: [0.52, 0.54], rotate: 0 }),
    grade: { vignetteStrength: 0.42, grainAmount: 0.26, paper: false, riso: 0, tooth: 0.05 },
    layers: [
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
          drawPine(ctx, { x: W * 0.015, y: H * 0.20, w: 128, h: H * 0.62, colour: '#0F1D17' });
          drawPine(ctx, { x: W * 0.115, y: H * 0.33, w: 96, h: H * 0.47, colour: '#132419' });
          drawPine(ctx, { x: W * 0.86, y: H * 0.26, w: 110, h: H * 0.55, colour: '#0F1D17' });
          contact(ctx, W * 0.55, H * 0.955, W * 0.30, H * 0.026, 0.55);
          drawMill(ctx, { x: W * 0.24, y: H * 0.16, w: W * 0.58, h: H * 0.80, t, smoke: k, wheel: k });
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          /* the year, enormous, behind the mill - it is a date, not a caption */
          ctx.save();
          ctx.globalAlpha *= 0.085 * clamp(span(p, 0.15, 0.6));
          text(ctx, '1865', W * 0.52, H * 0.505, {
            size: 300, family: SERIF, colour: '#F2E6CC', align: 'center',
          });
          ctx.restore();
          caps(ctx, 'TAMPERE · FINLAND', W * 0.075, H * 0.175, span(p, 0.22, 0.55), { colour: P.sepia.gold });
          rise(ctx, 'It began with', W * 0.072, H * 0.255, span(p, 0.28, 0.66), { size: 50, colour: P.sepia.ink });
          rise(ctx, 'a paper mill.', W * 0.072, H * 0.335, span(p, 0.38, 0.76), { size: 50, colour: P.sepia.ink });
        },
      },
    ],
  },

  /* 7 ------------------------------------------------------------------- */
  {
    id: 'history-02-trades',
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
        draw: (ctx, { p }) => {
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
            contact(ctx, cx, top + size + 16, size * 0.62, 12, 0.16);
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
    palette: { paper: P.rise.ground },
    role: 'momentum',
    seconds: 4.4,
    background: P.rise.ground,
    camera: (t, dur) => ({ zoom: 1.06 - (t / dur) * 0.06, at: [0.55, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0.40, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
    layers: [
      {
        id: 'bars', depth: 1,
        draw: (ctx, { p }) => {
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
  const framesDir = flag('--frames');
  const stills = flag('--stills');
  const startsPath = flag('--starts');

  if (startsPath) {
    const rows = shotStarts().map((row, i) => ({ ...row, vo: (readTiming() || [])[i]?.vo ?? null }));
    fs.writeFileSync(path.resolve(startsPath), JSON.stringify(rows, null, 2));
    console.log(`wrote ${startsPath} (${totalSeconds().toFixed(1)}s total)`);
  }

  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background });

  if (stills) {
    fs.mkdirSync(stills, { recursive: true });
    const rows = shotStarts();
    rows.forEach((row, i) => {
      const t = row.start + (row.end - row.start) * 0.78;
      ctx.clearRect(0, 0, W, H);
      renderer.render(ctx, t);
      fs.writeFileSync(path.join(stills, `${String(i).padStart(2, '0')}-${FILM[i].id}.png`), canvas.toBuffer('image/png'));
    });
    console.log(`wrote ${rows.length} stills to ${stills}`);
    return;
  }

  if (framesDir) {
    fs.mkdirSync(framesDir, { recursive: true });
    const total = Math.round(renderer.duration * fps);
    for (let i = 0; i < total; i += 1) {
      ctx.clearRect(0, 0, W, H);
      renderer.render(ctx, i / fps);
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
