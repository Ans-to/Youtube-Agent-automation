/**
 * Nokia: the film. Cold open, seven acts, one coda.
 *
 * The 67-second cut was the opening of this film, not the film. It states the
 * ending (one phone in three, then none), establishes the town that made paper,
 * and stops. This is the whole argument, told in the same grammar: every shot
 * its own world, one subject per shot, nothing photographed, everything drawn.
 *
 * The ten approved shots are imported rather than rewritten. They keep their
 * locked durations and their joins; they are re-sequenced into the acts where
 * they belong, so the mill sits in 1865 where the mill belongs instead of
 * standing in for history in a trailer. Everything else is new.
 *
 *   node films/nokia_full.mjs                     # the shot list
 *   node films/nokia_full.mjs --starts /tmp/st.json
 *   node films/nokia_full.mjs --stills /tmp/st --scale 1.5
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { drawHandset, drawStudio } from '../motion/kit/product.mjs';
import {
  drawCityscape, drawRooftop, drawSmartphone, drawMill, drawPine, drawPaperReam,
  drawRubberSheet, drawCableDrum, drawChip, drawPlinth, contact,
  drawMotes, drawBreathe,
} from '../motion/kit/objects.mjs';
import { drawMap, CITIES } from '../motion/kit/world.mjs';
import { optics, frameBuffer, opticsFor } from '../motion/kit/optics.mjs';
import { clamp, lerp, span, ease, noise } from '../motion/ui.mjs';
import { FILM as OPENING } from './nokia_atlas.mjs';

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
  size = 68, family = SERIF, colour = '#fff', weight = 400, align = 'left', from = 1.1,
} = {}) {
  const x0 = clamp(p);
  const back = 1.7;
  const k = x0 <= 0 ? 0 : x0 >= 1 ? 1
    : 1 + (back + 1) * Math.pow(x0 - 1, 3) + back * Math.pow(x0 - 1, 2);
  ctx.save();
  const w = 1400;
  const left = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x - 24;
  ctx.beginPath();
  /* the mask must clear the descenders, or the reveal slices letters */
  ctx.rect(left, y - size * 1.18, w, size * 1.52);
  ctx.clip();
  ctx.globalAlpha *= clamp(p * 2.2);
  ctx.translate(0, (1 - k) * size * from);
  text(ctx, value, x, y, { size, family, colour, weight, align });
  ctx.restore();
}

/** A hairline that draws itself. */
function rule(ctx, x, y, len, p, colour = '#C9A227', thickness = 1) {
  const k = ease.outCubic(clamp(p));
  ctx.save();
  ctx.fillStyle = colour;
  ctx.globalAlpha *= clamp(p * 2);
  ctx.fillRect(x, y, len * k, thickness);
  ctx.restore();
}

/* ------------------------------------------------------------- palette ---- */

/**
 * One world per act, and within an act one world per shot where the subject
 * changes. A film that carries one palette for eight minutes is one poster.
 */
const P = {
  sepia: { ground: '#191309', mid: '#3A2C16', hot: '#8A6A2A', ink: '#F2E6CC', gold: '#E0B45C' },
  bone: { ground: '#E9E3D4', mid: '#D6CEBC', hot: '#B8452A', ink: '#141210', gold: '#9C6B1E' },
  copper: { ground: '#12100C', mid: '#2A2118', hot: '#C4692E', ink: '#F1E7D6', gold: '#E08A3C' },
  cobalt: { ground: '#070C18', mid: '#0D1730', hot: '#2B4A8C', ink: '#EDE9DF', gold: '#C9A227' },
  steel: { ground: '#0B0E12', mid: '#1A2028', hot: '#3E4E60', ink: '#E8EDF2', gold: '#C8B36A' },
  amber: { ground: '#1A0F0A', mid: '#3E1E12', hot: '#C4571F', ink: '#F4E7D2', gold: '#F0B44A' },
  teal: { ground: '#05100F', mid: '#0B2224', hot: '#1E6E68', ink: '#E9F0E6', gold: '#D8B24A' },
  gold: { ground: '#08090B', mid: '#14161A', hot: '#7A5E1C', ink: '#F3EEE2', gold: '#E2B94F' },
  graphite: { ground: '#0E1013', mid: '#1B1E23', hot: '#2E333B', ink: '#EDEAE2', gold: '#C9A227' },
  ember: { ground: '#0D0705', mid: '#2A0F08', hot: '#C2410C', ink: '#F6E6D6', gold: '#E8A33D' },
  cold: { ground: '#0A0C10', mid: '#151A20', hot: '#46525E', ink: '#E6EAEE', gold: '#9FB0C0' },
  ash: { ground: '#0B0B0C', mid: '#171718', hot: '#3A3A3C', ink: '#E9E7E2', gold: '#A9A49A' },
};

const OPTICS = {
  sepia: { bloom: 0.58, halation: 0.50, grain: 0.26, vignette: 0.34, threshold: 0.42, tint: { r: 1.0, g: 0.66, b: 0.36 } },
  bone: { bloom: 0.16, halation: 0.08, grain: 0.12, vignette: 0.14, threshold: 0.76, tint: { r: 1.0, g: 0.97, b: 0.92 } },
  copper: { bloom: 0.46, halation: 0.38, grain: 0.22, vignette: 0.30, threshold: 0.50, tint: { r: 1.0, g: 0.74, b: 0.46 } },
  cobalt: { bloom: 0.55, halation: 0.42, grain: 0.22, vignette: 0.30, threshold: 0.52, tint: { r: 0.86, g: 0.94, b: 1.0 } },
  steel: { bloom: 0.40, halation: 0.26, grain: 0.18, vignette: 0.28, threshold: 0.58, tint: { r: 0.92, g: 0.96, b: 1.0 } },
  amber: { bloom: 0.60, halation: 0.52, grain: 0.24, vignette: 0.32, threshold: 0.44, tint: { r: 1.0, g: 0.80, b: 0.56 } },
  teal: { bloom: 0.44, halation: 0.30, grain: 0.20, vignette: 0.26, threshold: 0.54, tint: { r: 0.84, g: 1.0, b: 0.96 } },
  gold: { bloom: 0.44, halation: 0.26, grain: 0.18, vignette: 0.34, threshold: 0.56, tint: { r: 1.0, g: 0.86, b: 0.58 } },
  graphite: { bloom: 0.34, halation: 0.20, grain: 0.16, vignette: 0.26, threshold: 0.62, tint: { r: 0.96, g: 0.98, b: 1.0 } },
  ember: { bloom: 0.62, halation: 0.54, grain: 0.26, vignette: 0.36, threshold: 0.42, tint: { r: 1.0, g: 0.62, b: 0.34 } },
  cold: { bloom: 0.28, halation: 0.16, grain: 0.16, vignette: 0.32, threshold: 0.66, tint: { r: 0.86, g: 0.92, b: 1.0 } },
  ash: { bloom: 0.22, halation: 0.12, grain: 0.18, vignette: 0.30, threshold: 0.70, tint: { r: 0.96, g: 0.96, b: 0.96 } },
};

const GRADE = {
  sepia: { vignetteStrength: 0.42, grainAmount: 0.26, paper: false, riso: 0, tooth: 0.05 },
  bone: { vignetteStrength: 0.14, grainAmount: 0.10, paper: false, riso: 0, tooth: 0.05 },
  copper: { vignetteStrength: 0.34, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.04 },
  cobalt: { vignetteStrength: 0.44, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
  steel: { vignetteStrength: 0.32, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
  amber: { vignetteStrength: 0.38, grainAmount: 0.22, paper: false, riso: 0, tooth: 0.03 },
  teal: { vignetteStrength: 0.30, grainAmount: 0.20, paper: false, riso: 0, tooth: 0.03 },
  gold: { vignetteStrength: 0.40, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
  graphite: { vignetteStrength: 0.30, grainAmount: 0.14, paper: false, riso: 0, tooth: 0.03 },
  ember: { vignetteStrength: 0.44, grainAmount: 0.26, paper: false, riso: 0, tooth: 0.04 },
  cold: { vignetteStrength: 0.36, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
  ash: { vignetteStrength: 0.34, grainAmount: 0.16, paper: false, riso: 0, tooth: 0.03 },
};

/* -------------------------------------------------------------- pieces ---- */

/** The lit field every shot stands in: a radial pool and a floor line. */
function fieldLayer(world, { cx = 0.45, cy = 0.44, r = 0.85, floor = 0 } = {}) {
  return {
    id: 'field', depth: 1,
    draw: (ctx, { t }) => {
      ctx.fillStyle = world.ground;
      ctx.fillRect(0, 0, W, H);
      const g = ctx.createRadialGradient(W * cx, H * cy, 0, W * 0.5, H * 0.5, W * r);
      g.addColorStop(0, `${world.mid}`);
      g.addColorStop(0.55, `${world.mid}cc`);
      g.addColorStop(1, `${world.ground}00`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      if (floor) {
        const f = ctx.createLinearGradient(0, H * floor, 0, H);
        f.addColorStop(0, 'rgba(0,0,0,0)');
        f.addColorStop(1, 'rgba(0,0,0,0.55)');
        ctx.fillStyle = f;
        ctx.fillRect(0, H * floor, W, H * (1 - floor));
      }
      const breath = 0.5 + 0.5 * Math.sin(t * 0.7);
      const warm = ctx.createRadialGradient(W * cx, H * cy, 0, W * cx, H * cy, W * 0.6);
      warm.addColorStop(0, `rgba(255,226,170,${0.02 + 0.022 * breath})`);
      warm.addColorStop(1, 'rgba(255,226,170,0)');
      ctx.fillStyle = warm;
      ctx.fillRect(0, 0, W, H);
    },
  };
}

function airLayer(seed = 3, strength = 0.8, focus = [0.45, 0.5]) {
  return {
    id: 'air', depth: 1,
    draw: (ctx, { t }) => {
      drawMotes(ctx, {
        w: W, h: H, t, count: 64, seed, strength,
        focusX: focus[0], focusY: focus[1], focusR: 0.7,
      });
    },
  };
}

/** A shot scaffold: world, subject layers, and a words layer supplied by the caller. */
function scene(worldId, { t = 0 } = {}) {
  const world = P[worldId];
  return {
    world,
    optics: OPTICS[worldId],
    grade: GRADE[worldId],
    palette: { paper: world.ground },
    background: world.ground,
  };
}

/** The mask-safe words layer. */
function words(fn) {
  return { id: 'words', screen: true, depth: 1, draw: fn };
}

/* ------------------------------------------------------------- builders ---- */

/** Big statement type on a lit field. The film's rest beat. */
function typeShot(worldId, { kicker, lines, x = 0.075, top = 0.36, size = 66, note, seed = 7 } = {}) {
  const s = scene(worldId);
  const world = s.world;
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.055, at: [0.5, 0.5], rotate: 0 }),
    layers: [
      fieldLayer(world, { floor: 0.8 }),
      airLayer(seed, 0.7),
      words((ctx, { p }) => {
        let y = top;
        if (kicker) {
          caps(ctx, kicker, W * x, H * (top - 0.09), span(p, 0.02, 0.30), { colour: world.gold });
        }
        for (const line of lines) {
          rise(ctx, line.text, W * x, H * y, span(p, line.at ?? 0.10, (line.at ?? 0.10) + 0.30), {
            size: line.size || size, colour: line.colour || world.ink,
          });
          y += line.gap || 0.105;
        }
        if (note) {
          rise(ctx, note, W * x, H * (y + 0.02), span(p, 0.34, 0.62), {
            size: 26, colour: 'rgba(243,238,226,0.62)',
          });
        }
      }),
    ],
  };
}

/** A product on a plinth in a lit room. One object, one light, one idea. */
function objectShot(worldId, { draw, floor = 0.86, caption, kicker, seed = 11, glow = 1 } = {}) {
  const s = scene(worldId);
  const world = s.world;
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1.01 + (t / dur) * 0.07, at: [0.48, 0.52], rotate: 0 }),
    layers: [
      fieldLayer(world, { floor }),
      {
        id: 'plinth', depth: 1,
        draw: (ctx, { p }) => {
          const k = ease.outCubic(clamp(p * 3));
          ctx.save();
          ctx.globalAlpha *= k;
          drawPlinth(ctx, { x: 0, y: H * floor, w: W, h: H * (1 - floor) * 1.1, colour: 'rgba(255,255,255,0.035)' });
          ctx.restore();
        },
      },
      {
        id: 'subject', depth: 1,
        draw: (ctx, { p, t }) => {
          ctx.save();
          ctx.globalAlpha *= clamp(p * 3.2);
          draw(ctx, { p, t, glow });
          ctx.restore();
        },
      },
      airLayer(seed, 0.8, [0.48, 0.55]),
      words((ctx, { p }) => {
        if (kicker) caps(ctx, kicker, W * 0.072, H * 0.20, span(p, 0.06, 0.34), { colour: world.gold });
        if (caption) {
          rise(ctx, caption, W * 0.072, H * 0.80, span(p, 0.20, 0.52), { size: 46, colour: world.ink });
        }
      }),
    ],
  };
}

/**
 * Data on a field: bars that grow from a baseline, a value on the tallest, and
 * a caption under the axis. Every number in this film is placed by this one
 * builder, so the charts cannot drift into different house styles.
 */
function chartShot(worldId, {
  kicker, caption, note, bars, scaleMax, x = 0.10, base = 0.74, height = 0.34,
  lit = 0.0, seed = 5, align = 'left',
} = {}) {
  const s = scene(worldId);
  const world = s.world;
  const n = bars.length;
  const span01 = 0.86 / Math.max(1, n);
  const bw = span01 * W * 0.56;
  const gapx = span01 * W;
  const max = scaleMax ?? Math.max(...bars.map((b) => b.value)) * 1.06;
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.06, at: [0.48, 0.52], rotate: 0 }),
    layers: [
      fieldLayer(world, { floor: 0.88 }),
      airLayer(seed, 0.6),
      {
        id: 'bars', depth: 1,
        draw: (ctx, { p }) => {
          const w = 13 * (W / 1280);
          bars.forEach((bar, i) => {
            const k = ease.outCubic(clamp((p - 0.06 - i * 0.045) / 0.34));
            if (k <= 0) return;
            const h = (bar.value / max) * H * height * k;
            const bx = W * x + i * gapx;
            const hot = bar.hot ?? (i / Math.max(1, n - 1) >= lit);
            if (hot) {
              const g = ctx.createLinearGradient(0, H * base - h, 0, H * base);
              g.addColorStop(0, 'rgba(240,198,96,0.98)');
              g.addColorStop(1, 'rgba(150,104,26,0.98)');
              ctx.fillStyle = g;
            } else {
              ctx.fillStyle = 'rgba(240,238,230,0.22)';
            }
            ctx.fillRect(bx, H * base - h, w, h);
            if (bar.value > 0) {
              ctx.fillStyle = hot ? 'rgba(255,238,196,0.72)' : 'rgba(243,238,226,0.30)';
              ctx.fillRect(bx, H * base - h, w, 2);
            }
            if (bar.label) {
              text(ctx, bar.label, bx + w / 2, H * base + H * 0.052, {
                size: 17, family: SANS, weight: 500, align: 'center',
                colour: hot ? 'rgba(243,238,226,0.80)' : 'rgba(243,238,226,0.42)',
                alpha: clamp(k * 1.6),
              });
            }
          });
          const rk = ease.outCubic(clamp(p * 2.2));
          ctx.fillStyle = `rgba(243,238,226,${0.20 * rk})`;
          ctx.fillRect(W * x - W * 0.012, H * base, (gapx * (n - 1) + W * 0.012) * rk, 1);
        },
      },
      words((ctx, { p }) => {
        if (kicker) caps(ctx, kicker, W * x, H * 0.20, span(p, 0.02, 0.28), { colour: world.gold });
        if (caption) {
          rise(ctx, caption, W * (x + 0.02), H * 0.34, span(p, 0.10, 0.42), { size: 54, colour: world.ink });
        }
        if (note) {
          rise(ctx, note, W * (x + 0.02), H * 0.44, span(p, 0.22, 0.54), { size: 26, colour: 'rgba(243,238,226,0.64)' });
        }
      }),
    ],
  };
}

/** The world, with the network drawn on it. */
function mapShot(worldId, {
  projection = 'winkel', kicker, caption, note, arcs = [], pins = [], box = [0.085, 0.20, 0.83, 0.50],
  land = null, landEdge = null, seed = 9,
} = {}) {
  const s = scene(worldId);
  const world = s.world;
  const landColour = land || `${world.hot}`;
  const edge = landEdge || 'rgba(220,244,236,0.55)';
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.05, at: [0.5, 0.46], rotate: 0 }),
    layers: [
      fieldLayer(world, { cx: 0.5, cy: 0.42, r: 0.9 }),
      airLayer(seed, 0.5, [0.5, 0.45]),
      {
        id: 'map', depth: 1,
        draw: (ctx, { p }) => {
          drawMap(ctx, {
            x: W * box[0], y: H * box[1], w: W * box[2], h: H * box[3],
            p: span(p, 0.02, 0.34), projection, graticule: true,
            graticuleColour: 'rgba(150,220,210,0.05)',
            land: landColour, landEdge: edge,
            palette: { land: landColour, landEdge: edge, text: world.ink, caption: world.gold },
            pins, arcs,
          });
        },
      },
      words((ctx, { p }) => {
        if (kicker) caps(ctx, kicker, W * 0.075, H * 0.155, span(p, 0.26, 0.54), { colour: world.gold });
        if (caption) {
          rise(ctx, caption, W * 0.075, H * 0.79, span(p, 0.30, 0.60), { size: 50, colour: world.ink });
        }
        if (note) {
          rise(ctx, note, W * 0.075, H * 0.865, span(p, 0.40, 0.70), { size: 24, colour: 'rgba(243,238,226,0.62)' });
        }
      }),
    ],
  };
}

/** Horizontal bands: four industries, five businesses. A list you can watch. */
function bandsShot(worldId, { kicker, bands, caption, seed = 13 } = {}) {
  const s = scene(worldId);
  const world = s.world;
  const top = 0.30;
  const bandH = Math.min(0.10, 0.40 / bands.length);
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1.0 + (t / dur) * 0.05, at: [0.5, 0.5], rotate: 0 }),
    layers: [
      fieldLayer(world, { floor: 0.9 }),
      airLayer(seed, 0.6),
      {
        id: 'bands', depth: 1,
        draw: (ctx, { p }) => {
          bands.forEach((band, i) => {
            const at = 0.08 + i * 0.10;
            const k = ease.outCubic(clamp((p - at) / 0.30));
            if (k <= 0) return;
            const y = H * (top + i * bandH);
            const wide = (W * 0.80) * k;
            const g = ctx.createLinearGradient(W * 0.08, 0, W * 0.08 + wide, 0);
            g.addColorStop(0, band.colour || world.hot);
            g.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.save();
            ctx.globalAlpha *= 0.55;
            ctx.fillStyle = g;
            ctx.fillRect(W * 0.08, y, wide, H * bandH * 0.52);
            ctx.restore();
            ctx.fillStyle = `rgba(243,238,226,${0.22 * k})`;
            ctx.fillRect(W * 0.08, y, wide, 1);
            text(ctx, band.label, W * 0.085, y + H * bandH * 0.40, {
              size: 30, family: SERIF, colour: world.ink, alpha: k,
            });
            if (band.sub) {
              text(ctx, band.sub, W * 0.085 + 250, y + H * bandH * 0.40, {
                size: 15, family: SANS, weight: 500, colour: 'rgba(243,238,226,0.52)',
                tracking: 2.4, alpha: k,
              });
            }
          });
        },
      },
      words((ctx, { p }) => {
        if (kicker) caps(ctx, kicker, W * 0.08, H * 0.22, span(p, 0.02, 0.28), { colour: world.gold });
        if (caption) {
          rise(ctx, caption, W * 0.08, H * 0.88, span(p, 0.42, 0.72), { size: 38, colour: world.ink });
        }
      }),
    ],
  };
}

/** Two objects and a seam: the comparison shot. */
function compareShot(worldId, { left, right, kicker, caption, leftLabel, rightLabel, seed = 17 } = {}) {
  const s = scene(worldId);
  const world = s.world;
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1.02, at: [0.5, 0.52], rotate: 0 }),
    layers: [
      fieldLayer(world, { floor: 0.86 }),
      {
        id: 'halves', depth: 1,
        draw: (ctx, { p }) => {
          const k = ease.outCubic(clamp(p * 2));
          ctx.save();
          ctx.globalAlpha *= 0.5 * k;
          ctx.fillStyle = 'rgba(255,255,255,0.03)';
          ctx.fillRect(0, 0, W * 0.5, H);
          ctx.restore();
          ctx.fillStyle = `rgba(243,238,226,${0.16 * k})`;
          ctx.fillRect(W * 0.5, H * 0.14, 1, H * 0.72);
        },
      },
      {
        id: 'left', depth: 1,
        draw: (ctx, { p, t }) => { ctx.save(); ctx.globalAlpha *= clamp((p - 0.05) * 3); left(ctx, { p, t }); ctx.restore(); },
      },
      {
        id: 'right', depth: 1,
        draw: (ctx, { p, t }) => { ctx.save(); ctx.globalAlpha *= clamp((p - 0.18) * 3); right(ctx, { p, t }); ctx.restore(); },
      },
      airLayer(seed, 0.6),
      words((ctx, { p }) => {
        if (kicker) caps(ctx, kicker, W * 0.5, H * 0.185, span(p, 0.10, 0.36), { colour: world.gold, align: 'center' });
        if (caption) {
          rise(ctx, caption, W * 0.5, H * 0.84, span(p, 0.30, 0.60), { size: 44, colour: world.ink, align: 'center' });
        }
        if (leftLabel) {
          text(ctx, leftLabel, W * 0.27, H * 0.775, { size: 14, family: SANS, weight: 600, align: 'center', colour: 'rgba(243,238,226,0.45)', tracking: 3, alpha: clamp(p * 2) });
        }
        if (rightLabel) {
          text(ctx, rightLabel, W * 0.73, H * 0.775, { size: 14, family: SANS, weight: 600, align: 'center', colour: 'rgba(243,238,226,0.45)', tracking: 3, alpha: clamp(p * 2) });
        }
      }),
    ],
  };
}

/** The last card. */
function endShot(worldId, { lines, small } = {}) {
  const s = scene(worldId);
  const world = s.world;
  return {
    ...s,
    camera: (t, dur) => ({ zoom: 1 + (t / dur) * 0.02, at: [0.5, 0.5], rotate: 0 }),
    layers: [
      fieldLayer(world, { cx: 0.5, cy: 0.5, r: 0.8 }),
      airLayer(23, 0.5),
      words((ctx, { p }) => {
        let y = 0.40;
        for (const line of lines) {
          rise(ctx, line.text, W * 0.5, H * y, span(p, line.at ?? 0.08, (line.at ?? 0.08) + 0.26), {
            size: line.size || 62, colour: line.colour || world.ink, align: 'center',
          });
          y += line.gap || 0.12;
        }
        if (small) {
          caps(ctx, small, W * 0.5, H * 0.78, span(p, 0.46, 0.74), { colour: world.gold, align: 'center' });
        }
      }),
    ],
  };
}

/* --------------------------------------------------------------- exports ---- */

export { P, W, H };

/* ---------------------------------------------------------------- joins ---- */

/**
 * A join, as the renderer wants it: a kind and the options that parameterise it.
 * Handing the renderer a label string instead is what silently turned every
 * non-cut join in the short cut into a hard cut.
 */
function T(kind, options = {}) {
  const label = kind === 'fade' ? `fade-${options.dip || 'paper'}`
    : (kind === 'wipe' || kind === 'push') ? `${kind}-${options.direction || 'left'}`
      : kind;
  return { kind, label, options };
}

const LEAD = 0.3;
const LEAD_FIRST = 0.30;
const PAD = 2.1;

/** A duration to stand on before the voice exists. */
function estimate(text) {
  const words = text.trim().split(/\s+/).length;
  return Math.round((LEAD + words / 2.35 + PAD) * 10) / 10;
}

/** The approved ten already have a script; it lives beside their timings. */
const VO_TEXT = (() => {
  try {
    const rows = JSON.parse(fs.readFileSync(new URL('./nokia_vo.json', import.meta.url), 'utf8'));
    return Object.fromEntries(rows.map((r) => [r.shot, r.text]));
  } catch {
    return {};
  }
})();

function readTiming() {
  try {
    return JSON.parse(fs.readFileSync(new URL('./nokia_full-timing.json', import.meta.url), 'utf8'));
  } catch {
    return null;
  }
}

/* --------------------------------------------------------------- script ---- */

const NEW = [
  /* ACT I — the works (1865-1967) ---------------------------------------- */
  {
    id: 'mill-rubber',
    text: 'Rubber came next. Boots, tyres, and groundsheets for a country that is mostly forest.',
    shot: typeShot('copper', {
      kicker: '1898 · THE SECOND PRODUCT',
      lines: [
        { text: 'Boots.', size: 58, at: 0.05, gap: 0.11 },
        { text: 'Tyres.', size: 58, at: 0.16, colour: 'rgba(246,232,214,0.82)' },
        { text: 'Groundsheets.', size: 58, at: 0.27, colour: 'rgba(246,232,214,0.64)' },
      ],
      top: 0.34,
      note: 'A country that is mostly forest.',
    }),
  },
  {
    id: 'mill-cable',
    text: 'Then cable: copper wire, and the networks a town needs before it needs a telephone.',
    shot: objectShot('steel', {
      kicker: 'THE THIRD PRODUCT',
      caption: 'Cable.',
      draw: (ctx, { p }) => {
        contact(ctx, W * 0.5, H * 0.85, W * 0.19, H * 0.024, 0.55);
        drawCableDrum(ctx, { x: W * 0.345, y: H * 0.44, w: W * 0.31, h: H * 0.40 });
      },
    }),
  },

  /* ACT II — the network (1981-1998) -------------------------------------- */
  {
    id: 'carphone-1982',
    text: 'Before the pocket there was the car: a box in the boot, a handset beside the seat, and a radio licence.',
    shot: objectShot('cobalt', {
      kicker: '1982 · THE CAR PHONE',
      caption: 'Forty-five thousand of them in the first decade.',
      draw: (ctx, { p, glow }) => {
        contact(ctx, W * 0.5, H * 0.845, W * 0.22, H * 0.026, 0.6);
        drawHandset(ctx, {
          x: W * 0.415, y: H * 0.30, w: W * 0.17, h: H * 0.525, facing: 0.34,
          screen: 'menu', glow: 0.5 * glow, body: ['#5A6068', '#1B1F24', '#343A42'], bezel: '#0C0E11',
        });
      },
    }),
  },
  {
    id: 'network-nmt',
    text: 'Finland built one of the first mobile networks in the world, and Nokia built the phones to use it.',
    shot: mapShot('cobalt', {
      kicker: '1981 · THE NORDIC NETWORK',
      caption: 'A country of five million, wired first.',
      projection: 'mercator',
      box: [0.30, 0.22, 0.42, 0.52],
      land: 'rgba(34,72,132,0.85)',
      landEdge: 'rgba(150,196,240,0.55)',
      arcs: [
        { from: 'helsinki', to: 'stockholm', t: 0.5, colour: 'rgba(201,162,39,0.65)', width: 1.6, head: false },
        { from: 'helsinki', to: 'moscow', t: 0.62, colour: 'rgba(201,162,39,0.45)', width: 1.3, head: false },
        { from: 'helsinki', to: 'london', t: 0.72, colour: 'rgba(201,162,39,0.40)', width: 1.2, head: false },
      ],
    }),
  },
  {
    id: 'gsm-1991',
    text: 'In nineteen ninety-one, the first call on the new European standard was placed on a Nokia handset, in a park in Helsinki.',
    shot: typeShot('steel', {
      kicker: '1 JULY 1991 · HELSINKI',
      lines: [
        { text: 'The first GSM call.', size: 76, at: 0.06, gap: 0.14 },
        { text: 'A standard, not a product.', size: 32, at: 0.22, colour: 'rgba(232,237,242,0.66)' },
      ],
      top: 0.40,
    }),
  },
  {
    id: 'outnumbered',
    text: 'Six years later the phones outnumbered the paper, the boots and the cables put together.',
    shot: bandsShot('steel', {
      kicker: '1997 · BY REVENUE',
      bands: [
        { label: 'Phones', sub: 'and networks', colour: 'rgba(200,179,106,0.75)' },
        { label: 'Cable', sub: 'industrial', colour: 'rgba(150,150,160,0.50)' },
        { label: 'Rubber', sub: 'industrial', colour: 'rgba(196,105,46,0.45)' },
        { label: 'Paper', sub: 'industrial', colour: 'rgba(224,180,92,0.35)' },
      ],
      caption: 'The tail became the company.',
    }),
  },
  {
    id: 'largest-1998',
    text: 'By nineteen ninety-eight it sold more phones than any company on earth, and it had done it in six years.',
    shot: chartShot('steel', {
      kicker: 'MOBILE PHONES SOLD, MILLIONS',
      caption: 'The largest maker in the world.',
      bars: [
        { label: '1992', value: 2 },
        { label: '1994', value: 21 },
        { label: '1996', value: 41 },
        { label: '1997', value: 63 },
        { label: '1998', value: 91, hot: true },
      ],
      lit: 0.9,
    }),
  },

  /* ACT III — the decade (1998-2007) -------------------------------------- */
  {
    id: 'week-charge',
    text: 'The phones were cheap, hard to break, and lasted a week on a charge. That was the whole pitch.',
    shot: objectShot('amber', {
      kicker: '1999 · THE POCKET',
      caption: 'A week on a charge.',
      draw: (ctx, { p, glow }) => {
        contact(ctx, W * 0.5, H * 0.845, W * 0.16, H * 0.024, 0.55);
        drawHandset(ctx, {
          x: W * 0.42, y: H * 0.26, w: W * 0.16, h: H * 0.56, facing: 0.18,
          screen: 'menu', glow: 0.85 * glow, body: ['#6B6153', '#242019', '#4A4438'], bezel: '#100E0C',
        });
      },
    }),
  },
  {
    id: 'model-1100',
    text: 'In two thousand and three, one model sold two hundred and fifty million units. No phone has sold more since.',
    shot: chartShot('gold', {
      kicker: 'UNITS SOLD, ONE MODEL',
      caption: 'Two hundred and fifty million.',
      note: 'The best-selling phone ever made.',
      bars: [
        { label: '3210', value: 160 },
        { label: '3310', value: 126 },
        { label: '1100', value: 250, hot: true },
        { label: 'iPhone', value: 220 },
      ],
      lit: 0.5,
    }),
  },
  {
    id: 'peak-revenue',
    text: 'Between nineteen ninety-eight and two thousand and seven, net sales went from thirteen billion euros to fifty-one.',
    shot: chartShot('gold', {
      kicker: 'NET SALES, BILLIONS OF EUROS',
      caption: 'Ten years, four times the size.',
      bars: [
        { label: '1998', value: 13 },
        { label: '2000', value: 30 },
        { label: '2003', value: 29 },
        { label: '2005', value: 34 },
        { label: '2007', value: 51, hot: true },
      ],
      lit: 0.9,
    }),
  },
  {
    id: 'symbian',
    text: 'Its software ran on two thirds of the world\'s smartphones, in the years before anyone agreed what a smartphone was.',
    shot: chartShot('teal', {
      kicker: 'SMARTPHONE OPERATING SYSTEMS · 2007',
      caption: 'Symbian, sixty-five percent.',
      bars: [
        { label: 'Symbian', value: 65, hot: true },
        { label: 'RIM', value: 11 },
        { label: 'Windows', value: 12 },
        { label: 'iPhone', value: 3 },
        { label: 'Other', value: 9 },
      ],
      lit: 0.0,
    }),
  },
  {
    id: 'factories',
    text: 'Nine factories ran day and night, and one phone in every three sold anywhere in the world came out of them.',
    shot: typeShot('gold', {
      kicker: '2007',
      lines: [
        { text: 'One in three.', size: 104, at: 0.06, colour: '#E2B94F', gap: 0.17 },
        { text: 'Nine factories. Fifty thousand people.', size: 32, at: 0.22, colour: 'rgba(243,238,226,0.68)' },
      ],
      top: 0.42,
    }),
  },

  /* ACT IV — the turn (2007-2010) ----------------------------------------- */
  {
    id: 'iphone-2007',
    text: 'In January two thousand and seven, a phone was announced that was almost entirely screen.',
    shot: objectShot('graphite', {
      kicker: '9 JANUARY 2007',
      caption: 'One button.',
      draw: (ctx, { p, glow }) => {
        contact(ctx, W * 0.5, H * 0.855, W * 0.13, H * 0.02, 0.5);
        drawSmartphone(ctx, { x: W * 0.425, y: H * 0.20, w: W * 0.15, h: H * 0.63, glow });
      },
    }),
  },
  {
    id: 'forty-keys',
    text: 'It had one button. A Nokia had forty, and software written separately for every model it shipped.',
    shot: compareShot('graphite', {
      kicker: 'TWO IDEAS OF A PHONE',
      leftLabel: 'NOKIA · 40 KEYS',
      rightLabel: '2007 · 1 BUTTON',
      caption: 'The difference was not the button.',
      left: (ctx) => {
        drawHandset(ctx, { x: W * 0.20, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.14, screen: 'menu', glow: 0.5, body: ['#5E5A52', '#211E1A', '#413D36'] });
      },
      right: (ctx, { glow }) => {
        drawSmartphone(ctx, { x: W * 0.66, y: H * 0.28, w: W * 0.10, h: H * 0.46, glow });
      },
    }),
  },
  {
    id: 'android-2008',
    text: 'A year later a second system arrived, free, for any manufacturer who wanted it.',
    shot: mapShot('graphite', {
      kicker: '2008 · THE SECOND SYSTEM',
      caption: 'Given away.',
      land: 'rgba(70,78,88,0.80)',
      landEdge: 'rgba(180,190,200,0.45)',
      arcs: [
        { from: 'cupertino', to: 'newyork', t: 0.42, colour: 'rgba(210,220,230,0.40)', width: 1.3, head: false },
        { from: 'cupertino', to: 'london', t: 0.52, colour: 'rgba(210,220,230,0.34)', width: 1.2, head: false },
        { from: 'cupertino', to: 'seoul', t: 0.60, colour: 'rgba(210,220,230,0.34)', width: 1.2, head: false },
        { from: 'cupertino', to: 'beijing', t: 0.68, colour: 'rgba(210,220,230,0.30)', width: 1.2, head: false },
        { from: 'cupertino', to: 'delhi', t: 0.74, colour: 'rgba(210,220,230,0.30)', width: 1.2, head: false },
      ],
    }),
  },
  {
    id: 'hardware',
    text: 'Nokia answered with better hardware. Better cameras, better screens, better build. The problem was never the hardware.',
    shot: typeShot('graphite', {
      kicker: '2008-2010',
      lines: [
        { text: 'It kept winning', size: 64, at: 0.06, gap: 0.12 },
        { text: 'the wrong contest.', size: 64, at: 0.20, colour: 'rgba(237,234,226,0.72)' },
      ],
      top: 0.40,
    }),
  },
  {
    id: 'burning-platform',
    text: 'In twenty ten a new chief executive wrote a memo to his own staff. He said the company was standing on a burning platform.',
    transition: T('fade', { dip: 'paper' }),
    shot: typeShot('ember', {
      kicker: 'FEBRUARY 2011 · THE MEMO',
      lines: [
        { text: 'A burning platform.', size: 78, at: 0.06, colour: '#F6E6D6', gap: 0.15 },
        { text: 'His words, to his own engineers.', size: 30, at: 0.24, colour: 'rgba(246,230,214,0.66)' },
      ],
      top: 0.42,
    }),
  },
  {
    id: 'microsoft',
    text: 'Six months later, Nokia abandoned its own operating system for one owned by Microsoft.',
    shot: typeShot('ember', {
      kicker: '2011 · THE PLATFORM CHANGES',
      lines: [
        { text: 'Symbian out.', size: 66, at: 0.06, gap: 0.12 },
        { text: 'Windows Phone in.', size: 66, at: 0.18, colour: 'rgba(246,230,214,0.70)' },
      ],
      top: 0.42,
    }),
  },

  /* ACT V — the fall (2011-2013) ------------------------------------------ */
  {
    id: 'share-fall',
    text: 'The share of phones sold fell from a third to a twentieth in three years.',
    shot: chartShot('cold', {
      kicker: 'SHARE OF PHONES SOLD, PERCENT',
      caption: 'A third, then almost nothing.',
      bars: [
        { label: '2007', value: 33, hot: true },
        { label: '2009', value: 30 },
        { label: '2011', value: 15 },
        { label: '2012', value: 6 },
        { label: '2013', value: 3 },
      ],
      lit: 0.0,
    }),
  },
  {
    id: 'smartphones-sold',
    text: 'In twenty eleven it sold a hundred million smartphones. Two years later, thirty million.',
    shot: chartShot('cold', {
      kicker: 'SMARTPHONES SOLD, MILLIONS',
      caption: 'Three years of subtraction.',
      bars: [
        { label: '2010', value: 100 },
        { label: '2011', value: 77 },
        { label: '2012', value: 35 },
        { label: '2013', value: 30, hot: true },
      ],
      lit: 0.9,
      scaleMax: 120,
    }),
  },
  {
    id: 'share-price',
    text: 'The share price fell by ninety percent, and the value that had been in the phones went with it.',
    shot: chartShot('cold', {
      kicker: 'SHARE PRICE, INDEXED TO THE PEAK',
      caption: 'Ninety percent, gone.',
      bars: [
        { label: '2000', value: 100, hot: true },
        { label: '2007', value: 46 },
        { label: '2011', value: 12 },
        { label: '2013', value: 8 },
      ],
      lit: 0.0,
      scaleMax: 110,
    }),
  },
  {
    id: 'jobs',
    text: 'Factories closed, and eighteen thousand people lost their jobs.',
    shot: bandsShot('ash', {
      kicker: '2011-2013 · CLOSURES',
      bands: [
        { label: 'Salo', sub: 'FINLAND', colour: 'rgba(200,205,210,0.22)' },
        { label: 'Cluj', sub: 'ROMANIA', colour: 'rgba(200,205,210,0.18)' },
        { label: 'Masdar', sub: 'UAE', colour: 'rgba(200,205,210,0.15)' },
        { label: 'Ulm', sub: 'GERMANY', colour: 'rgba(200,205,210,0.12)' },
      ],
      caption: '18,000 jobs.',
    }),
  },
  {
    id: 'sale-2013',
    text: 'In September twenty thirteen, the phone business was sold to Microsoft for five and a half billion euros.',
    transition: T('iris'),
    shot: typeShot('ash', {
      kicker: '3 SEPTEMBER 2013',
      lines: [
        { text: '€5.4 billion.', size: 92, at: 0.06, colour: '#E9E7E2', gap: 0.16 },
        { text: 'Devices and services, sold.', size: 30, at: 0.22, colour: 'rgba(233,231,226,0.62)' },
      ],
      top: 0.42,
    }),
  },
  {
    id: 'stopped',
    text: 'The company that had made one phone in three stopped making phones.',
    shot: objectShot('ash', {
      kicker: '2014',
      caption: 'Nothing on the plinth.',
      draw: (ctx) => {
        contact(ctx, W * 0.5, H * 0.845, W * 0.16, H * 0.02, 0.35);
      },
    }),
  },

  /* ACT VI — what remained (2014-2025) ------------------------------------ */
  {
    id: 'networks',
    text: 'What was left was the part nobody had photographed: the networks.',
    transition: T('dissolve'),
    shot: mapShot('teal', {
      kicker: 'WHAT REMAINED',
      caption: 'The radio.',
      land: 'rgba(28,96,92,0.85)',
      landEdge: 'rgba(150,224,208,0.50)',
      arcs: [
        { from: 'helsinki', to: 'london', t: 0.40, colour: 'rgba(216,178,74,0.50)', width: 1.4, head: false },
        { from: 'helsinki', to: 'newyork', t: 0.48, colour: 'rgba(216,178,74,0.46)', width: 1.4, head: false },
        { from: 'helsinki', to: 'delhi', t: 0.56, colour: 'rgba(216,178,74,0.44)', width: 1.3, head: false },
        { from: 'helsinki', to: 'tokyo', t: 0.64, colour: 'rgba(216,178,74,0.40)', width: 1.3, head: false },
        { from: 'helsinki', to: 'saopaulo', t: 0.72, colour: 'rgba(216,178,74,0.38)', width: 1.2, head: false },
      ],
    }),
  },
  {
    id: 'alcatel',
    text: 'It bought Alcatel-Lucent, and became one of three companies that build the world\'s radio networks.',
    shot: chartShot('teal', {
      kicker: 'RADIO ACCESS NETWORKS · SHARE',
      caption: 'Three companies, most of the world.',
      bars: [
        { label: 'Huawei', value: 31 },
        { label: 'Nokia', value: 22, hot: true },
        { label: 'Ericsson', value: 18 },
        { label: 'ZTE', value: 11 },
        { label: 'Others', value: 18 },
      ],
      lit: 0.0,
    }),
  },
  {
    id: 'patents',
    text: 'It licenses the patents it filed while it was making phones. About a billion euros a year, for doing nothing.',
    shot: chartShot('teal', {
      kicker: 'LICENSING REVENUE, BILLIONS OF EUROS',
      caption: 'The phone paid twice.',
      bars: [
        { label: '2016', value: 0.8 },
        { label: '2019', value: 1.1 },
        { label: '2021', value: 1.3 },
        { label: '2023', value: 1.4, hot: true },
      ],
      lit: 0.9,
    }),
  },
  {
    id: 'hmd',
    text: 'In twenty sixteen the name was licensed to another company. Nokia does not make those phones.',
    shot: typeShot('teal', {
      kicker: '2016 · THE NAME',
      lines: [
        { text: 'Licensed,', size: 72, at: 0.06, gap: 0.12 },
        { text: 'not manufactured.', size: 72, at: 0.18, colour: 'rgba(233,240,230,0.72)' },
      ],
      top: 0.42,
      note: 'HMD Global builds them. The patents are still Nokia\'s.',
    }),
  },

  /* ACT VII — coda --------------------------------------------------------- */
  {
    id: 'five-businesses',
    text: 'Paper, rubber, cable, phones, networks. Five businesses in one hundred and sixty years.',
    transition: T('wipe', { direction: 'left' }),
    shot: bandsShot('gold', {
      kicker: '1865-2025',
      bands: [
        { label: 'Paper', sub: '1865', colour: 'rgba(226,185,79,0.70)' },
        { label: 'Rubber', sub: '1898', colour: 'rgba(196,105,46,0.60)' },
        { label: 'Cable', sub: '1912', colour: 'rgba(150,150,160,0.50)' },
        { label: 'Phones', sub: '1981', colour: 'rgba(120,160,210,0.50)' },
        { label: 'Networks', sub: '2016', colour: 'rgba(80,190,175,0.55)' },
      ],
      caption: 'One of them is still running.',
    }),
  },
  {
    id: 'lesson',
    text: 'The lesson usually drawn is that Nokia missed the smartphone.',
    shot: typeShot('gold', {
      lines: [{ text: 'The usual lesson:', size: 44, at: 0.08, colour: 'rgba(243,238,226,0.55)', gap: 0.11 },
        { text: 'Nokia missed', size: 78, at: 0.16, gap: 0.13 },
        { text: 'the smartphone.', size: 78, at: 0.30, colour: '#E2B94F' }],
      top: 0.36,
    }),
  },
  {
    id: 'counter',
    text: 'It did. It also built the networks that the smartphones ran on.',
    shot: mapShot('gold', {
      kicker: 'BOTH THINGS ARE TRUE',
      caption: 'The call and the road it ran on.',
      land: 'rgba(120,100,52,0.55)',
      landEdge: 'rgba(226,185,79,0.40)',
      arcs: [
        { from: 'helsinki', to: 'london', t: 0.42, colour: 'rgba(226,185,79,0.50)', width: 1.4, head: false },
        { from: 'helsinki', to: 'newyork', t: 0.50, colour: 'rgba(226,185,79,0.46)', width: 1.4, head: false },
        { from: 'helsinki', to: 'beijing', t: 0.58, colour: 'rgba(226,185,79,0.42)', width: 1.3, head: false },
        { from: 'helsinki', to: 'sydney', t: 0.66, colour: 'rgba(226,185,79,0.38)', width: 1.3, head: false },
      ],
    }),
  },
  {
    id: 'close',
    text: 'In two thousand and seven, one in three phones on earth was a Nokia. That company is still alive. It just stopped making the phone.',
    transition: T('push', { direction: 'left' }),
    shot: endShot('gold', {
      lines: [
        { text: '2007', size: 132, at: 0.10, colour: '#E2B94F' },
      ],
      small: 'FIVE BUSINESSES, ONE HUNDRED AND SIXTY YEARS',
    }),
  },

  {
    id: 'forest-1865',
    text: 'The river carried the wood to the mill, and the mill turned it into paper.',
    shot: mapShot('sepia', {
      kicker: '1865 · THE TIMBER TRADE',
      caption: 'Wood went out. Paper came back.',
      box: [0.26, 0.22, 0.48, 0.50],
      land: 'rgba(96,74,44,0.55)',
      landEdge: 'rgba(226,190,130,0.42)',
      arcs: [{ from: 'helsinki', to: 'stockholm', t: 0.55, colour: 'rgba(226,190,130,0.30)', width: 1.2, head: false }],
    }),
  },
  {
    id: 'nmt-timeline',
    text: 'Forty years of standards, each one faster: N M T, then G S M, then three G, then four.',
    shot: bandsShot('cobalt', {
      kicker: 'STANDARDS',
      bands: [
        { label: 'NMT', sub: '1981 · ANALOGUE', colour: 'rgba(120,160,210,0.55)' },
        { label: 'GSM', sub: '1991 · DIGITAL', colour: 'rgba(150,180,220,0.52)' },
        { label: '3G', sub: '2001 · DATA', colour: 'rgba(190,180,120,0.50)' },
        { label: '4G', sub: '2009 · EVERYTHING', colour: 'rgba(210,160,90,0.52)' },
      ],
      caption: 'One company in every generation of that list.',
    }),
  },
  {
    id: 'first-handset',
    text: 'By nineteen eighty-seven the phone had shrunk to something you could carry. It weighed eight hundred grams.',
    shot: objectShot('cobalt', {
      kicker: '1987 · THE FIRST HANDHELD',
      caption: 'Eight hundred grams.',
      draw: (ctx, { p, glow }) => {
        contact(ctx, W * 0.5, H * 0.845, W * 0.17, H * 0.024, 0.55);
        drawHandset(ctx, {
          x: W * 0.405, y: H * 0.24, w: W * 0.19, h: H * 0.58, facing: 0.26,
          screen: 'menu', glow: 0.55 * glow, body: ['#6E6656', '#241F18', '#4C4638'], bezel: '#100E0C',
        });
      },
    }),
  },
  {
    id: 'design',
    text: 'Four phones, four moments, one shape language: a screen, a keypad, and a rim you could hold in the dark.',
    shot: bandsShot('amber', {
      kicker: 'THE SHAPE LANGUAGE',
      bands: [
        { label: 'Cityman', sub: '1987', colour: 'rgba(196,105,46,0.42)' },
        { label: '2110', sub: '1994', colour: 'rgba(224,180,92,0.48)' },
        { label: '3210', sub: '1999', colour: 'rgba(200,190,150,0.42)' },
        { label: '1100', sub: '2003', colour: 'rgba(160,180,200,0.38)' },
      ],
      caption: 'Nobody had to be taught it.',
    }),
  },
  {
    id: 'ringtone',
    text: 'The ringtone was a fragment of a guitar piece from nineteen-oh-two. For a decade it was the most played music on earth.',
    shot: typeShot('amber', {
      kicker: 'THE TUNE',
      lines: [
        { text: 'Gran Vals.', size: 70, at: 0.06, gap: 0.14 },
        { text: '1902, and then four billion times.', size: 30, at: 0.22, colour: 'rgba(243,238,226,0.66)' },
      ],
      top: 0.42,
    }),
  },
  {
    id: 'dev-split',
    text: 'Symbian had sixty versions in the wild, and a company had to write its application again for each one.',
    shot: chartShot('graphite', {
      kicker: 'PLATFORM FRAGMENTATION · 2007',
      caption: 'Sixty variants of one system.',
      bars: [
        { label: 'Symbian', value: 60, hot: true },
        { label: 'iPhone', value: 1 },
        { label: 'Android', value: 1 },
      ],
      lit: 0.0,
    }),
  },
  {
    id: 'app-store',
    text: 'By twenty eleven the competing store had half a million applications. Nokia\'s had a fraction, and its developers had begun to leave.',
    shot: chartShot('graphite', {
      kicker: 'APPLICATIONS AVAILABLE · 2011',
      caption: 'The developers left first.',
      bars: [
        { label: 'App Store', value: 500, hot: true },
        { label: 'Android', value: 300 },
        { label: 'Ovi', value: 50 },
      ],
      lit: 0.0,
    }),
  },
  {
    id: 'loss-2012',
    text: 'In twenty twelve the company lost three billion euros, and sold its headquarters to stay liquid.',
    shot: typeShot('cold', {
      kicker: '2012 · THE WORST YEAR',
      lines: [
        { text: '€3 billion,', size: 70, at: 0.06, colour: '#E9EDF2', gap: 0.14 },
        { text: 'lost in a year.', size: 70, at: 0.18, colour: 'rgba(233,237,242,0.66)' },
      ],
      top: 0.42,
      note: 'Then it sold its own head office.',
    }),
  },
  {
    id: 'five-g',
    text: 'The radios it kept are the ones the next decade runs on. The name on the mast is still Nokia.',
    shot: mapShot('teal', {
      kicker: '2020 · 5G',
      caption: 'The road, not the car.',
      land: 'rgba(26,88,86,0.85)',
      landEdge: 'rgba(150,224,208,0.48)',
      arcs: [
        { from: 'helsinki', to: 'newyork', t: 0.40, colour: 'rgba(216,178,74,0.52)', width: 1.5, head: false },
        { from: 'helsinki', to: 'saopaulo', t: 0.48, colour: 'rgba(216,178,74,0.48)', width: 1.4, head: false },
        { from: 'helsinki', to: 'delhi', t: 0.56, colour: 'rgba(216,178,74,0.46)', width: 1.4, head: false },
        { from: 'helsinki', to: 'tokyo', t: 0.64, colour: 'rgba(216,178,74,0.42)', width: 1.3, head: false },
        { from: 'helsinki', to: 'sydney', t: 0.72, colour: 'rgba(216,178,74,0.38)', width: 1.3, head: false },
      ],
    }),
  },
  {
    id: 'elop-quote',
    text: 'The memo was written for his own staff. It was public within a day.',
    shot: typeShot('ember', {
      kicker: 'THE LEAK',
      lines: [
        { text: 'Not meant', size: 58, at: 0.06, gap: 0.12 },
        { text: 'to be read.', size: 58, at: 0.18, colour: 'rgba(246,230,214,0.70)' },
      ],
      top: 0.40,
      note: 'Eleven thousand people worked there.',
    }),
  },
  {
    id: 'bell-labs',
    text: 'With the purchase came Bell Labs, the laboratory that invented the transistor, the solar cell, and the laser.',
    shot: typeShot('teal', {
      kicker: '2016 · BELL LABS',
      lines: [
        { text: 'The transistor.', size: 54, at: 0.06, gap: 0.10 },
        { text: 'The solar cell.', size: 54, at: 0.16, colour: 'rgba(233,240,230,0.80)' },
        { text: 'The laser.', size: 54, at: 0.26, colour: 'rgba(233,240,230,0.62)' },
      ],
      top: 0.42,
    }),
  },
  {
    id: 'nokia-today',
    text: 'Today it employs seventy-seven thousand people, and sells radios to telephone companies in every country on earth.',
    shot: typeShot('teal', {
      kicker: '2025',
      lines: [
        { text: '77,000 people.', size: 62, at: 0.06, gap: 0.13 },
        { text: 'No phones on the plinth.', size: 62, at: 0.18, colour: 'rgba(233,240,230,0.68)' },
      ],
      top: 0.42,
      note: 'Revenue: about twenty billion euros a year.',
    }),
  },
];

/* --------------------------------------------------------------- timing ---- */

function withDuration(shots) {
  const timing = readTiming();
  const spoken = timing
    ? Object.fromEntries(timing.filter((r) => r.shot).map((r) => [r.shot, r.vo]))
    : {};
  return shots.map((shot) => {
    if (shot.fixed && shot.dur) return shot;
    const vo = spoken[shot.id];
    if (vo === undefined) return { ...shot, dur: estimate(shot.text) };
    return { ...shot, dur: Math.round((LEAD + vo + PAD) * 10) / 10 };
  });
}

const OPEN = OPENING;
const CLAIM = OPEN[0];
const FALL = OPEN[1];
const RINGING = OPEN[2];
const CITIES_SHOT = OPEN[3];
const WORLD = OPEN[4];
const TURN = OPEN[5];
const ALONE = OPEN[6];
const MILL = OPEN[7];
const TRADES = OPEN[8];
const RISE = OPEN[9];

const byId = Object.fromEntries(NEW.map((entry) => [entry.id, entry]));

/**
 * The film, in order.
 *
 * Two things are fixed here. The cold open runs before anything else, because a
 * hook that arrives after the opening is a hook nobody reaches. And the ten
 * approved shots keep their own durations and their own joins: they are the
 * picture that was signed off, re-sequenced into the acts where they belong.
 */
const ORDER = [
  /* cold open ------------------------------------------------------------ */
  ['hook-00-claim', CLAIM, { fixed: true }],
  ['hook-00-fall', FALL, { fixed: true }],
  /* overture: the phone in the world ------------------------------------ */
  ['hook-01-ringing', RINGING, { fixed: true }],
  ['hook-02-cities', CITIES_SHOT, { fixed: true }],
  ['hook-03-world', WORLD, { fixed: true }],
  ['hook-04-turn', TURN, { fixed: true }],
  ['hook-05-alone', ALONE, { fixed: true }],
  /* act i — the works, 1865-1967 --------------------------------------- */
  ['history-01-mill', MILL, { fixed: true }],
  ['forest-1865', byId['forest-1865']],
  ['mill-rubber', byId['mill-rubber']],
  ['mill-cable', byId['mill-cable']],
  ['history-02-trades', TRADES, { fixed: true }],
  /* act ii — the network, 1981-1998 ------------------------------------ */
  ['carphone-1982', byId['carphone-1982']],
  ['nmt-timeline', byId['nmt-timeline']],
  ['first-handset', byId['first-handset']],
  ['gsm-1991', byId['gsm-1991']],
  ['outnumbered', byId['outnumbered']],
  ['largest-1998', byId['largest-1998']],
  /* act iii — the decade, 1998-2007 ------------------------------------ */
  ['week-charge', byId['week-charge']],
  ['design', byId['design']],
  ['ringtone', byId['ringtone']],
  ['model-1100', byId['model-1100']],
  ['peak-revenue', byId['peak-revenue']],
  ['symbian', byId['symbian']],
  ['dev-split', byId['dev-split']],
  ['factories', byId['factories']],
  ['history-03-rise', RISE, { fixed: true }],
  /* act iv — the turn, 2007-2011 --------------------------------------- */
  ['iphone-2007', byId['iphone-2007']],
  ['forty-keys', byId['forty-keys']],
  ['android-2008', byId['android-2008']],
  ['app-store', byId['app-store']],
  ['hardware', byId['hardware']],
  ['burning-platform', byId['burning-platform']],
  ['elop-quote', byId['elop-quote']],
  ['microsoft', byId['microsoft']],
  /* act v — the fall, 2011-2014 ---------------------------------------- */
  ['share-fall', byId['share-fall']],
  ['smartphones-sold', byId['smartphones-sold']],
  ['share-price', byId['share-price']],
  ['loss-2012', byId['loss-2012']],
  ['jobs', byId['jobs']],
  ['sale-2013', byId['sale-2013']],
  ['stopped', byId['stopped']],
  /* act vi — what remained, 2014-2025 ---------------------------------- */
  ['networks', byId['networks']],
  ['alcatel', byId['alcatel']],
  ['bell-labs', byId['bell-labs']],
  ['patents', byId['patents']],
  ['five-g', byId['five-g']],
  ['hmd', byId['hmd']],
  /* coda --------------------------------------------------------------- */
  ['nokia-today', byId['nokia-today']],
  ['five-businesses', byId['five-businesses']],
  ['lesson', byId['lesson']],
  ['counter', byId['counter']],
  ['close', byId['close']],
];

/* The script, as the voice will read it: id, text, picture. */
const SCRIPT = ORDER.map(([id, entry, extra]) => {
  // A new shot arrives as {id, text, shot}; an approved one *is* the shot.
  const picture = entry.shot || entry;
  return {
    ...picture,
    ...extra,
    id,
    text: entry.text || VO_TEXT[id] || '',
    transition: (extra && extra.transition) || entry.transition || picture.transition || null,
  };
});

export const FILM = withDuration(SCRIPT).map((shot, i, all) => {
  const token = shot.transition;
  const paper = (i > 0 ? all[i - 1] : shot).palette?.paper || 'rgba(241,231,212,1)';
  const ground = (i > 0 ? all[i - 1] : shot).background || paper;
  if (!token) return { ...shot, transition: { kind: 'cut', label: 'cut', options: {} } };
  if (token.kind === 'fade') {
    return { ...shot, transition: { ...token, options: { ...token.options, colour: ground } } };
  }
  return shot;
});

export function totalSeconds(shots = FILM) {
  return shots.reduce((a, s) => a + s.dur, 0);
}

export function shotStarts(shots = FILM) {
  let at = 0;
  return shots.map((s, i) => {
    const row = {
      id: s.id,
      start: Math.round(at * 1000) / 1000,
      end: Math.round((at + s.dur) * 1000) / 1000,
      voStart: Math.round((at + (i === 0 ? LEAD_FIRST : LEAD)) * 1000) / 1000,
      transition: (s.transition && s.transition.label) || 'cut',
    };
    at += s.dur;
    return row;
  });
}

export function shotAt(t, shots = FILM) {
  let at = 0;
  for (const shot of shots) {
    if (t < at + shot.dur) return shot;
    at += shot.dur;
  }
  return shots[shots.length - 1];
}

/* ----------------------------------------------------------------- main ---- */

async function main() {
  const args = process.argv.slice(2);
  const flag = (k, d = null) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
  loadFonts();
  const fps = Number(flag('--fps') || 30);
  const scale = Number(flag('--scale') || 1);
  const framesDir = flag('--frames');
  const stills = flag('--stills');
  const startsPath = flag('--starts');
  const linesPath = flag('--lines');
  const dw = Math.round(W * scale);
  const dh = Math.round(H * scale);

  if (linesPath) {
    fs.writeFileSync(path.resolve(linesPath), JSON.stringify(
      FILM.map((s) => ({ shot: s.id, text: s.text })).filter((l) => l.text), null, 2,
    ));
    console.log(`wrote ${linesPath}`);
    return;
  }

  if (startsPath) {
    fs.writeFileSync(path.resolve(startsPath), JSON.stringify(shotStarts(), null, 2));
    console.log(`wrote ${startsPath} (${totalSeconds().toFixed(1)}s total)`);
  }

  const canvas = createCanvas(dw, dh);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background, scale });
  const fb = frameBuffer(dw, dh);
  const paint = (t) => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, dw, dh);
    renderer.render(ctx, t);
    fb.ctx.setTransform(1, 0, 0, 1, 0, 0);
    fb.ctx.clearRect(0, 0, dw, dh);
    fb.ctx.drawImage(canvas, 0, 0);
    optics(ctx, { source: fb.canvas, w: dw, h: dh, frame: Math.round(t * fps), ...opticsFor(shotAt(t)) });
  };

  if (stills) {
    fs.mkdirSync(stills, { recursive: true });
    shotStarts().forEach((row, i) => {
      const t = row.start + (row.end - row.start) * 0.78;
      paint(t);
      fs.writeFileSync(path.join(stills, `${String(i).padStart(2, '0')}-${FILM[i].id}.png`), canvas.toBuffer('image/png'));
    });
    console.log(`wrote ${FILM.length} stills to ${stills}`);
    return;
  }

  if (flag('--pipe')) {
    const total = Math.round(renderer.duration * fps);
    const from = Number(flag('--from', 0));
    const to = Math.min(total, Number(flag('--to', total)));
    for (let i = from; i < to; i += 1) {
      paint(i / fps);
      // `getImageData` leaks its backing store here - 176 frames into a 1080p
      // render the process is 1.4 GB resident and the OOM reaper kills it.
      // `canvas.data()` hands back a Buffer that can be written and dropped.
      // `getImageData` leaks its backing store here - 176 frames into a 1080p
      // render the process is 1.4 GB resident and the OOM reaper kills it.
      // `canvas.data()` hands back a Buffer, and the write is asynchronous so a
      // slow encoder gets backpressure instead of an EAGAIN that kills the render
      // half a frame before the end of a chunk.
      const data = canvas.data();
      let off = 0;
      while (off < data.length) {
        const chunk = data.subarray(off);
        off += chunk.length;
        if (!process.stdout.write(chunk)) {
          await new Promise((resolve) => process.stdout.once('drain', resolve));
        }
      }
    }
    return;
  }

  if (framesDir) {
    fs.mkdirSync(framesDir, { recursive: true });
    const total = Math.round(renderer.duration * fps);
    const from = Number(flag('--from', 0));
    const to = Math.min(total, Number(flag('--to', total)));
    for (let i = from; i < to; i += 1) {
      paint(i / fps);
      fs.writeFileSync(path.join(framesDir, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
    }
    console.log(`wrote frames ${from}-${to} of ${total}`);
    return;
  }

  console.log(`${FILM.length} shots, ${totalSeconds().toFixed(1)}s`);
  shotStarts().forEach((s) => console.log(
    `  ${s.start.toFixed(1)}s  ${s.id.padEnd(22)} ${(s.end - s.start).toFixed(1)}s  [${s.transition}]`,
  ));
}

if (import.meta.url === `file://${process.argv[1]}`) main();
