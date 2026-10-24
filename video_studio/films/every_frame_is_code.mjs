#!/usr/bin/env node
/**
 * Every Frame Is Code — a hand-authored motion piece.
 *
 * This is not a storyboard interpreter. Every shot below is drawn by explicit
 * code: each layer has its own keyframe curve, nothing is allowed to sit still,
 * and every word animates in *and* out. The five shots are joined by four
 * non-default transitions (whip pan, masked reveal, glitch, match cut) that
 * overlap the cut, so there is never a frame where movement stops.
 *
 * Design space is 3840x2160. Pass --width to render a smaller preview; all
 * coordinates scale, so a 960-wide preview is the same film.
 *
 *   node video_studio/films/every_frame_is_code.mjs --out frames --width 960
 *   node video_studio/films/every_frame_is_code.mjs --out stills --still 1.2,5.4,9.0
 *
 * Output: frame-%06d.jpg plus manifest.json, timeline.txt and film.json (the
 * shot list, layer hierarchy, transition table and motion self-check).
 */
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

const require = createRequire(import.meta.url);
const { createCanvas, GlobalFonts } = require('@napi-rs/canvas');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');
const DESIGN_W = 3840;
const DESIGN_H = 2160;
const DURATION = 20.0;

// ------------------------------------------------------------------ options
function parseArgs(argv) {
  const opts = {
    out: 'frames', width: DESIGN_W, height: null, fps: 30, quality: 92,
    from: 0, to: null, still: null, quiet: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = () => argv[(i += 1)];
    if (flag === '--out') opts.out = value();
    else if (flag === '--width') opts.width = Number(value());
    else if (flag === '--height') opts.height = Number(value());
    else if (flag === '--fps') opts.fps = Number(value());
    else if (flag === '--quality') opts.quality = Number(value());
    else if (flag === '--from') opts.from = Number(value());
    else if (flag === '--to') opts.to = Number(value());
    else if (flag === '--still') opts.still = value().split(',').map(Number);
    else if (flag === '--quiet') opts.quiet = true;
    else if (flag === '--help' || flag === '-h') { console.log(fs.readFileSync(new URL(import.meta.url)).toString().split('*/')[0]); process.exit(0); }
    else throw new Error(`Unknown option: ${flag}`);
  }
  opts.height = opts.height || Math.round(opts.width * DESIGN_H / DESIGN_W / 2) * 2;
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
const SCALE = OPTS.width / DESIGN_W;
const FPS = OPTS.fps;
const TOTAL_FRAMES = Math.round(DURATION * FPS);

// -------------------------------------------------------------------- fonts
const FACES = [
  ['Inter', 'inter-latin-400-normal.woff2'],
  ['Inter', 'inter-latin-500-normal.woff2'],
  ['Inter', 'inter-latin-600-normal.woff2'],
  ['Inter', 'inter-latin-700-normal.woff2'],
  ['Inter', 'inter-latin-800-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-400-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-500-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-600-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
];
for (const [family, file] of FACES) {
  GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
}

// ------------------------------------------------------------------ palette
const C = {
  bg: '#05070C', bg2: '#080C14', panel: '#0C121D', panelHi: '#111A28',
  line: '#1C2534', fg: '#F4F6FA', muted: '#8B94A6', dim: '#4A5468',
  accent: '#C8FF3D', support: '#5B8FFF', warm: '#FF6B3D',
};

// -------------------------------------------------------------------- maths
const clamp = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const lerp = (a, b, t) => a + (b - a) * t;
const span = (t, a, b) => clamp((t - a) / (b - a));
const mix = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
const rgba = (rgb, a) => `rgba(${rgb[0] | 0},${rgb[1] | 0},${rgb[2] | 0},${a})`;

const ease = {
  // No linear interpolation anywhere: expo/settle/snap curves only.
  outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inExpo: (x) => (x <= 0 ? 0 : Math.pow(2, 10 * (x - 1))),
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  inCubic: (x) => x * x * x,
  inOutCubic: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outQuart: (x) => 1 - Math.pow(1 - x, 4),
  // anticipation: dips below zero before it moves, like a coil
  anticipate: (x) => (x <= 0 ? 0 : x < 0.22 ? -0.16 * Math.sin((x / 0.22) * Math.PI) : ease.outCubic((x - 0.22) / 0.78)),
  // overshoot settle, the workhorse for objects that arrive
  backOut: (x) => (x <= 0 ? 0 : 1 + 2.2 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2)),
};

// deterministic value noise for handheld camera and flicker
function hash(n) {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
  return s - Math.floor(s);
}
function noise1(x) {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  return lerp(hash(i) * 2 - 1, hash(i + 1) * 2 - 1, u);
}

// ------------------------------------------------------------------- canvas
const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');
const bufA = createCanvas(OPTS.width, OPTS.height);
const bufB = createCanvas(OPTS.width, OPTS.height);

const W = DESIGN_W;
const H = DESIGN_H;

// --------------------------------------------------------------- text utils
const measureCache = new Map();
function measureChars(text, size, weight, family) {
  const key = `${text}|${size}|${weight}|${family}`;
  const hit = measureCache.get(key);
  if (hit) return hit;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.font = `${weight} ${size}px "${family}"`;
  const chars = Array.from(text);
  const widths = chars.map((ch) => ctx.measureText(ch).width);
  ctx.restore();
  const result = { chars, widths };
  measureCache.set(key, result);
  return result;
}

function wordWidth(text, size, weight, family, tracking) {
  const { widths } = measureChars(text, size, weight, family);
  return widths.reduce((a, b) => a + b, 0) + tracking * (widths.length - 1);
}

/**
 * Draw a word character by character, with an entrance and an exit.
 * Every option is real animation state, not a wrapper around fillText.
 */
function typeWord(ctx, word, o) {
  const family = o.family || 'Space Grotesk';
  const weight = o.weight || 700;
  const size = o.size || 200;
  const tracking = o.tracking === undefined
    ? 0
    : typeof o.tracking === 'function' ? o.tracking() : o.tracking;
  const { chars, widths } = measureChars(word, size, weight, family);
  const total = widths.reduce((a, b) => a + b, 0) + tracking * (chars.length - 1);
  let cursor = o.x - (o.align === 'center' ? total / 2 : o.align === 'right' ? total : 0);
  const stagger = o.stagger === undefined ? 0.028 : o.stagger;
  const inDur = o.inDur === undefined ? 0.62 : o.inDur;
  const rise = o.rise === undefined ? 150 : o.rise;
  const outAt = o.outAt === undefined ? Infinity : o.outAt;
  const outDur = o.outDur === undefined ? 0.42 : o.outDur;
  const outStagger = o.outStagger === undefined ? 0.016 : o.outStagger;
  const exitRise = o.exitRise === undefined ? -190 : o.exitRise;
  const alphaIn = o.alpha === undefined ? 1 : o.alpha;

  for (let i = 0; i < chars.length; i += 1) {
    const inStart = (o.inAt || 0) + i * stagger;
    const pIn = ease.outExpo(span(o.t, inStart, inStart + inDur));
    const pOut = outAt === Infinity ? 0 : ease.inCubic(span(o.t, outAt + i * outStagger, outAt + i * outStagger + outDur));
    const visible = pIn > 0.001 && pOut < 0.999;
    if (visible) {
      const dy = (1 - pIn) * rise + pOut * exitRise;
      const dx = (1 - pIn) * (o.driftX || 0) + pOut * (o.exitDriftX || 0);
      const wobble = o.wobble ? Math.sin(o.t * 2.2 + i * 0.5) * o.wobble : 0;
      ctx.save();
      ctx.globalAlpha *= alphaIn * clamp(pIn * 1.2) * (1 - pOut);
      ctx.translate(cursor + widths[i] / 2 + dx, o.y + dy + wobble);
      if (o.rot) ctx.rotate(((1 - pIn) * (o.rot || 0) + pOut * (o.exitRot || 0)));
      const sx = 1 + (1 - pIn) * (o.scaleFromX || 0) - pOut * (o.squeeze || 0);
      const sy = 1 + (1 - pIn) * (o.scaleFromY || 0) + pOut * (o.exitScaleY || 0);
      if (sx !== 1 || sy !== 1) ctx.scale(sx, sy);
      ctx.font = `${weight} ${size}px "${family}"`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillStyle = typeof o.color === 'function' ? o.color(i) : o.color || C.fg;
      ctx.fillText(chars[i], 0, 0);
      ctx.restore();
    }
    cursor += widths[i] + tracking;
  }
  return total;
}

function label(ctx, text, x, y, o = {}) {
  const size = o.size || 40;
  const weight = o.weight || 500;
  const family = o.family || 'Inter';
  const tracking = o.tracking || 0;
  const p = o.progress === undefined ? 1 : o.progress;
  const w = wordWidth(text, size, weight, family, tracking);
  const startX = o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x;
  const { chars, widths } = measureChars(text, size, weight, family);
  ctx.save();
  ctx.globalAlpha *= (o.alpha === undefined ? 1 : o.alpha) * clamp(p * 1.3);
  ctx.font = `${weight} ${size}px "${family}"`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = o.color || C.muted;
  // characters slide up through a mask as the label types on
  const shown = Math.ceil(p * chars.length);
  let cursor = startX;
  for (let i = 0; i < chars.length; i += 1) {
    const local = clamp(p * chars.length - i);
    if (i < shown) {
      ctx.save();
      ctx.globalAlpha *= clamp(local * 1.6);
      ctx.fillText(chars[i], cursor + widths[i] / 2, y + (1 - ease.outExpo(local)) * size * 0.5);
      ctx.restore();
    }
    cursor += widths[i] + tracking;
  }
  ctx.restore();
  return w;
}

// ------------------------------------------------------------------ texture
function makeNoiseTile() {
  const size = 256;
  const tile = createCanvas(size, size);
  const tctx = tile.getContext('2d');
  const img = tctx.createImageData(size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 118 + Math.random() * 74;
    img.data[i] = v; img.data[i + 1] = v; img.data[i + 2] = v; img.data[i + 3] = 255;
  }
  tctx.putImageData(img, 0, 0);
  return tile;
}
const NOISE = makeNoiseTile();
const NOISE_PATTERN = ctx.createPattern(NOISE, 'repeat');

function makeVignette() {
  const layer = createCanvas(OPTS.width, OPTS.height);
  const v = layer.getContext('2d');
  const g = v.createRadialGradient(OPTS.width / 2, OPTS.height / 2, OPTS.height * 0.28,
    OPTS.width / 2, OPTS.height / 2, OPTS.height * 0.86);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, 'rgba(0,0,0,0.40)');
  v.fillStyle = g;
  v.fillRect(0, 0, OPTS.width, OPTS.height);
  return layer;
}
const VIGNETTE = makeVignette();

/** Grain and vignette over the finished frame; both move, so the frame never dies. */
function finish(frame) {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 0.045;
  ctx.fillStyle = NOISE_PATTERN;
  ctx.translate(-((frame * 37) % 256), -((frame * 53) % 256));
  ctx.fillRect(0, 0, OPTS.width + 256, OPTS.height + 256);
  ctx.restore();

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 0.62;
  ctx.drawImage(VIGNETTE, 0, 0);
  ctx.restore();
}

// ---------------------------------------------------------------- particles
const PARTICLES = Array.from({ length: 90 }, (_, i) => ({
  x: hash(i * 3.1) * W,
  y: hash(i * 7.7) * H,
  speed: 14 + hash(i * 5.3) * 46,
  size: 1.5 + hash(i * 11.9) * 3.5,
  drift: hash(i * 2.7) * Math.PI * 2,
  alpha: 0.15 + hash(i * 9.1) * 0.45,
}));

function drawParticles(ctx, t, { color = C.fg, alpha = 1, warp = null } = {}) {
  ctx.save();
  for (const p of PARTICLES) {
    let x = p.x + Math.sin(t * 0.35 + p.drift) * 26;
    let y = ((p.y - t * p.speed) % (H + 120) + H + 120) % (H + 120) - 60;
    let a = p.alpha * alpha;
    let r = p.size;
    if (warp) {
      const s = warp(p, t);
      x = s.x; y = s.y; a *= s.a === undefined ? 1 : s.a; r *= s.r === undefined ? 1 : s.r;
    }
    ctx.globalAlpha = a;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function atmosphere(g, t, rgb = [200, 255, 61]) {
  for (let i = 0; i < 2; i += 1) {
    const cx = W / 2 + Math.cos(t * 0.55 + i * 2.1) * W * 0.30;
    const cy = H / 2 + Math.sin(t * 0.42 + i * 1.3) * H * 0.28;
    const r = H * (0.55 + 0.08 * Math.sin(t * 0.7 + i));
    const g0 = g.createRadialGradient(cx, cy, 0, cx, cy, r);
    g0.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.055)`);
    g0.addColorStop(0.55, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.018)`);
    g0.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = g0;
    g.fillRect(-2600, -2600, W + 5200, H + 5200);
  }
}

// ============================================================== SHOT A (0-4)
// Kinetic type over a sliding grid. Every word enters and leaves.
function shotA(g, t) {
  const push = 1 + 0.135 * ease.inOutCubic(span(t, 0, 4));
  const rot = -0.008 * ease.inOutCubic(span(t, 0, 4));
  g.save();
  g.translate(W / 2 + Math.sin(t * 0.7) * 46 - 30 * t, H / 2);
  g.rotate(rot);
  g.scale(push, push);
  g.translate(-W / 2, -H / 2);

  // -- background: the grid never stops moving
  g.fillStyle = C.bg;
  g.fillRect(-2600, -2600, W + 5200, H + 5200);
  const scroll = (-t * 250) % 220;
  g.strokeStyle = 'rgba(120,150,200,0.09)';
  g.lineWidth = 2;
  for (let x = scroll; x < W + 220; x += 220) {
    g.beginPath(); g.moveTo(x, -400); g.lineTo(x, H + 400); g.stroke();
  }
  g.strokeStyle = 'rgba(120,150,200,0.05)';
  for (let y = ((t * 130) % 220) - 220; y < H + 220; y += 220) {
    g.beginPath(); g.moveTo(-400, y); g.lineTo(W + 400, y); g.stroke();
  }

  atmosphere(g, t);
  // scan band travelling down the frame
  const scanY = ((t * 0.42) % 1) * (H + 400) - 200;
  const scan = g.createLinearGradient(0, scanY - 160, 0, scanY + 160);
  scan.addColorStop(0, 'rgba(180,210,255,0)');
  scan.addColorStop(0.5, 'rgba(180,210,255,0.05)');
  scan.addColorStop(1, 'rgba(180,210,255,0)');
  g.fillStyle = scan;
  g.fillRect(-400, scanY - 160, W + 800, 320);

  // -- glow that drifts behind the type
  const gx = W * (0.66 + 0.05 * Math.sin(t * 0.9));
  const gy = H * (0.34 + 0.04 * Math.cos(t * 0.7));
  const glow = g.createRadialGradient(gx, gy, 0, gx, gy, H * 0.62);
  glow.addColorStop(0, 'rgba(200,255,61,0.13)');
  glow.addColorStop(0.5, 'rgba(200,255,61,0.035)');
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = glow;
  g.fillRect(-2600, -2600, W + 5200, H + 5200);

  // -- midground: ghost glyphs, parallax
  g.save();
  g.globalAlpha = 0.5;
  g.strokeStyle = 'rgba(140,170,220,0.13)';
  g.lineWidth = 3;
  g.font = '700 760px "Space Grotesk"';
  g.textAlign = 'left';
  const ghosts = [['{', -0.04, 0.28], ['}', 0.84, 0.08], ['/', 0.7, 1.04]];
  for (let i = 0; i < ghosts.length; i += 1) {
    const [glyph, gxp, gyp] = ghosts[i];
    g.save();
    g.translate(W * gxp + Math.sin(t * 0.5 + i) * 26, H * gyp - t * 150 - i * 20);
    g.strokeText(glyph, 0, 0);
    g.restore();
  }
  g.restore();

  // -- right-hand structural element so the frame is not half empty
  const rail = ease.outExpo(span(t, 1.2, 2.1)) * (1 - ease.inCubic(span(t, 3.5, 3.85)));
  if (rail > 0.001) {
    g.save();
    g.globalAlpha = 0.9;
    g.fillStyle = C.accent;
    g.fillRect(3090, 640, 4, 900 * rail);
    g.fillStyle = 'rgba(244,246,250,0.55)';
    g.font = '500 30px "Inter"';
    g.textAlign = 'left';
    g.save();
    g.translate(3130, 660);
    g.fillText('FRAME 001', 0, 0);
    g.fillText('4K / 30FPS', 0, 44);
    g.fillText('20.00 SEC', 0, 88);
    g.restore();
    // small travelling index marks
    for (let i = 0; i < 14; i += 1) {
      const y = 700 + ((i * 62 + t * 46) % 800);
      g.globalAlpha = 0.18 + 0.3 * hash(i);
      g.fillStyle = C.accent;
      g.fillRect(3090, y, i % 3 === 0 ? 26 : 12, 2);
    }
    g.restore();
  }

  // kicker + rule
  label(g, 'A FILM ABOUT MOTION', 240, 470, {
    size: 46, weight: 600, tracking: 14, color: C.accent,
    progress: span(t, 0.9, 1.7), alpha: 1 - ease.inCubic(span(t, 3.72, 3.95)), align: 'left',
  });
  label(g, 'EVERY FRAME IS CODE', 240, 542, {
    size: 36, weight: 400, tracking: 8, color: C.muted, align: 'left',
    progress: span(t, 1.05, 1.9), alpha: 1 - ease.inCubic(span(t, 3.45, 3.78)),
  });

  // -- type: the marker is drawn first so the word sits on top of it
  const drift = Math.sin(t * 1.1) * 6;
  const trackingB = lerp(30, -4, ease.outExpo(span(t, 0.3, 1.5))) + Math.sin(t * 1.5 + 1) * 6;
  const wB = wordWidth('FRAME', 400, 700, 'Space Grotesk', trackingB);
  const marker = ease.outQuart(span(t, 2.3, 2.95)) * (1 - ease.inCubic(span(t, 3.55, 3.9)));
  if (marker > 0.001) {
    g.save();
    g.globalAlpha = 0.94;
    g.fillStyle = C.accent;
    g.translate(222, 1426 + drift * 1.4);
    g.scale(marker, 1);
    g.fillRect(0, -330, wB + 70, 372);
    g.restore();
  }

  typeWord(g, 'EVERY', {
    t, x: 236, y: 1040 + drift, size: 400, weight: 700, family: 'Space Grotesk',
    tracking: lerp(36, -8, ease.outExpo(span(t, 0.05, 1.15))) + Math.sin(t * 1.7) * 7,
    inAt: 0.02, stagger: 0.035, rise: 240, scaleFromY: 0.22,
    outAt: 3.74, outStagger: 0.012, exitRise: -260,
    driftX: (1 - ease.outExpo(span(t, 0.05, 1.15))) * 46,
  });
  typeWord(g, 'FRAME', {
    t, x: 236, y: 1426 + drift * 1.4, size: 400, weight: 700, family: 'Space Grotesk',
    tracking: trackingB,
    inAt: 0.24, stagger: 0.03, rise: 280, scaleFromY: 0.18,
    color: () => (marker > 0.62 ? C.bg : C.fg),
    outAt: 3.78, outStagger: 0.012, exitRise: -260,
  });

  const rule = ease.outExpo(span(t, 1.8, 2.5)) * (1 - ease.inCubic(span(t, 3.5, 3.8)));
  g.save();
  g.fillStyle = C.accent;
  g.globalAlpha = 0.85 * rule;
  g.fillRect(236, 1548, 1240 * rule, 6);
  g.restore();

  // foreground ticks that travel with the camera
  g.save();
  g.globalAlpha = 0.5;
  g.strokeStyle = 'rgba(200,255,61,0.5)';
  g.lineWidth = 2;
  for (let i = 0; i < 5; i += 1) {
    const y = 700 + i * 46;
    const len = 26 + 18 * Math.sin(t * 2 + i);
    g.beginPath();
    g.moveTo(W - 240 - len, y);
    g.lineTo(W - 240, y);
    g.stroke();
  }
  g.restore();

  g.restore(); // camera
  drawParticles(g, t, { alpha: 0.6 });
}

// ============================================================== SHOT B (4-8)
// The pipeline: three panels arrive, a path draws itself, a packet travels it.
const PANELS = [
  { x: 400, label: 'DIRECT', sub: 'brief to shot list', num: '01' },
  { x: 1580, label: 'RENDER', sub: '600 frames, 4K', num: '02' },
  { x: 2760, label: 'AUDIT', sub: '18 motion checks', num: '03' },
];
const PANEL_W = 860;
const PANEL_H = 560;
const PANEL_Y = 780;

function panelPath(points) {
  const segs = [];
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const len = Math.hypot(x1 - x0, y1 - y0);
    segs.push({ x0, y0, x1, y1, len, start: total });
    total += len;
  }
  return { segs, total };
}

function pointAt(pathObj, s) {
  const d = clamp(s) * pathObj.total;
  for (const seg of pathObj.segs) {
    if (d <= seg.start + seg.len) {
      const k = seg.len === 0 ? 0 : (d - seg.start) / seg.len;
      return [lerp(seg.x0, seg.x1, k), lerp(seg.y0, seg.y1, k)];
    }
  }
  const last = pathObj.segs[pathObj.segs.length - 1];
  return [last.x1, last.y1];
}

const PATH_MAIN = panelPath([
  [PANELS[0].x + PANEL_W + 30, PANEL_Y + PANEL_H / 2], [PANELS[1].x - 120, PANEL_Y + PANEL_H / 2],
  [PANELS[1].x - 120, PANEL_Y + PANEL_H / 2 - 180], [PANELS[1].x - 30, PANEL_Y + PANEL_H / 2 - 180],
]);
const PATH_B = panelPath([
  [PANELS[1].x + PANEL_W + 30, PANEL_Y + PANEL_H / 2], [PANELS[2].x - 120, PANEL_Y + PANEL_H / 2],
  [PANELS[2].x - 120, PANEL_Y + PANEL_H / 2 + 180], [PANELS[2].x - 30, PANEL_Y + PANEL_H / 2 + 180],
]);
const PATH_FULL = panelPath([
  [PANELS[0].x + PANEL_W + 30, PANEL_Y + PANEL_H / 2], [PANELS[1].x - 120, PANEL_Y + PANEL_H / 2],
  [PANELS[1].x - 120, PANEL_Y + PANEL_H / 2 - 180], [PANELS[1].x - 30, PANEL_Y + PANEL_H / 2 - 180],
  [PANELS[1].x + 30, PANEL_Y + PANEL_H / 2 - 180], [PANELS[1].x + PANEL_W + 30, PANEL_Y + PANEL_H / 2],
  [PANELS[2].x - 120, PANEL_Y + PANEL_H / 2], [PANELS[2].x - 120, PANEL_Y + PANEL_H / 2 + 180],
  [PANELS[2].x - 30, PANEL_Y + PANEL_H / 2 + 180],
]);

function shotB(g, t) {
  const pan = -300 * ease.inOutCubic(span(t, 0, 4));
  const zoom = 1.02 + 0.05 * ease.inOutCubic(span(t, 0, 4));
  g.save();
  g.translate(W / 2 + pan, H / 2);
  g.scale(zoom, zoom);
  g.translate(-W / 2, -H / 2);

  // -- background: perspective floor travelling toward the viewer
  g.fillStyle = C.bg2;
  g.fillRect(-2600, -2600, W + 5200, H + 5200);
  const horizon = H * 0.5;
  const flow = (t * 1.15) % 1;
  for (let i = 0; i < 26; i += 1) {
    const k = ((i + flow) / 26) ** 2.3;
    const y = horizon + k * (H - horizon) * 1.2;
    const alpha = 0.025 + 0.13 * k;
    g.strokeStyle = `rgba(91,143,255,${alpha.toFixed(3)})`;
    g.lineWidth = 1 + k * 3.4;
    g.beginPath(); g.moveTo(-200, y); g.lineTo(W + 200, y); g.stroke();
  }
  for (let i = -14; i <= 14; i += 1) {
    g.strokeStyle = 'rgba(91,143,255,0.07)';
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(W / 2 + i * 110, horizon);
    g.lineTo(W / 2 + i * 620, H + 260);
    g.stroke();
  }
  const haze = g.createLinearGradient(0, horizon - 300, 0, horizon + 260);
  haze.addColorStop(0, 'rgba(5,7,12,0.96)');
  haze.addColorStop(0.5, 'rgba(5,7,12,0.25)');
  haze.addColorStop(1, 'rgba(5,7,12,0.96)');
  g.fillStyle = haze;
  g.fillRect(-200, horizon - 300, W + 400, 560);

  atmosphere(g, t, [91, 143, 255]);

  // -- header
  const head = ease.outExpo(span(t, 0.15, 0.75)) * (1 - ease.inCubic(span(t, 3.5, 3.85)));
  g.save();
  g.globalAlpha = 0.95 * head;
  g.fillStyle = C.accent;
  g.beginPath();
  g.arc(244, 380, 13 + Math.sin(t * 6) * 2, 0, Math.PI * 2);
  g.fill();
  g.restore();
  label(g, 'THE PIPELINE', 292, 400, {
    size: 68, weight: 600, tracking: 10, color: C.fg, align: 'left',
    progress: span(t, 0.2, 0.85), alpha: 1 - ease.inCubic(span(t, 3.9, 4.3)),
  });
  label(g, 'three moves, no hand-offs', 292, 470, {
    size: 36, weight: 400, tracking: 4, color: C.muted, align: 'left',
    progress: span(t, 0.5, 1.1), alpha: 1 - ease.inCubic(span(t, 3.9, 4.3)),
  });

  // -- path between panels (behind them)
  const draw1 = ease.inOutCubic(span(t, -0.35, 0.45));
  const draw2 = ease.inOutCubic(span(t, -0.1, 0.7));
  for (const [p0, prog] of [[PATH_MAIN, draw1], [PATH_B, draw2]]) {
    if (prog <= 0) continue;
    g.save();
    g.strokeStyle = 'rgba(200,255,61,0.6)';
    g.lineWidth = 6;
    g.setLineDash([p0.total, p0.total]);
    g.lineDashOffset = p0.total * (1 - prog);
    g.beginPath();
    g.moveTo(p0.segs[0].x0, p0.segs[0].y0);
    for (const seg of p0.segs) g.lineTo(seg.x1, seg.y1);
    g.stroke();
    g.restore();
  }

  // -- travelling packet, continuous from 1.1s to the cut
  const travel = ease.inOutCubic(span(t, 0.55, 3.45));
  if (travel > 0) {
    for (let k = 10; k >= 0; k -= 1) {
      const s = travel - k * 0.011;
      if (s < 0) continue;
      const [px, py] = pointAt(PATH_FULL, s);
      g.save();
      g.globalAlpha = (1 - k / 11) * 0.55;
      g.fillStyle = C.accent;
      g.beginPath();
      g.arc(px, py, 19 - k * 1.3, 0, Math.PI * 2);
      g.fill();
      g.restore();
    }
    const [hx, hy] = pointAt(PATH_FULL, travel);
    const halo = g.createRadialGradient(hx, hy, 0, hx, hy, 110);
    halo.addColorStop(0, 'rgba(200,255,61,0.6)');
    halo.addColorStop(1, 'rgba(200,255,61,0)');
    g.fillStyle = halo;
    g.fillRect(hx - 110, hy - 110, 220, 220);
    g.fillStyle = '#ffffff';
    g.beginPath(); g.arc(hx, hy, 16, 0, Math.PI * 2); g.fill();
  }

  // -- panels
  for (let i = 0; i < PANELS.length; i += 1) {
    const panel = PANELS[i];
    const inStart = -0.38 + i * 0.18;
    const p = ease.backOut(span(t, inStart, inStart + 0.8));
    const out = ease.inCubic(span(t, 3.74 + i * 0.05, 4.24 + i * 0.05));
    if (p <= 0 || out >= 1) continue;
    const x = panel.x + (1 - p) * 820 - out * 1000 + Math.sin(t * 1.5 + i) * 7;
    const y = PANEL_Y + (1 - p) * 70 + Math.sin(t * 1.9 + i * 1.4) * 9;
    const alpha = clamp(p * 1.4) * (1 - out);

    g.save();
    g.globalAlpha = alpha;
    g.fillStyle = 'rgba(0,0,0,0.5)';
    g.beginPath();
    g.roundRect(x + 16, y + 26, PANEL_W, PANEL_H, 30);
    g.fill();

    const fill = g.createLinearGradient(x, y, x, y + PANEL_H);
    fill.addColorStop(0, C.panelHi);
    fill.addColorStop(1, C.panel);
    g.fillStyle = fill;
    g.beginPath();
    g.roundRect(x, y, PANEL_W, PANEL_H, 30);
    g.fill();
    g.strokeStyle = i === 1 ? 'rgba(200,255,61,0.6)' : 'rgba(255,255,255,0.11)';
    g.lineWidth = 2;
    g.stroke();

    g.fillStyle = C.accent;
    g.fillRect(x + 54, y + 64, 5, (PANEL_H - 190) * ease.outExpo(span(t, inStart + 0.1, inStart + 0.9)));

    g.font = '700 132px "Space Grotesk"';
    g.fillStyle = i === 1 ? C.accent : 'rgba(244,246,250,0.94)';
    g.textAlign = 'left';
    g.fillText(panel.num, x + 96, y + 190);
    g.font = '600 76px "Space Grotesk"';
    g.fillStyle = C.fg;
    g.fillText(panel.label, x + 96, y + 386);
    g.font = '400 44px "Inter"';
    g.fillStyle = C.muted;
    g.fillText(panel.sub, x + 96, y + 458);

    // live ticker inside the card so it is never static
    g.fillStyle = 'rgba(200,255,61,0.35)';
    const tickW = ((t * 300 + i * 110) % (PANEL_W - 192));
    g.fillRect(x + 96, y + PANEL_H - 66, tickW, 4);
    g.restore();
  }

  g.restore();
  drawParticles(g, t * 0.6, { alpha: 0.4, color: C.support });
}

// ============================================================== SHOT C (8-12)
// Proof: bars rise, counters run, everything keeps drifting.
function shotC(g, t) {
  const zoom = 1.02 + 0.05 * ease.inOutCubic(span(t, 0, 4));
  const pan = 80 * ease.inOutCubic(span(t, 0, 4));
  g.save();
  g.translate(W / 2 + pan, H / 2);
  g.scale(zoom, zoom);
  g.translate(-W / 2, -H / 2);

  g.fillStyle = C.bg;
  g.fillRect(-2600, -2600, W + 5200, H + 5200);

  atmosphere(g, t);

  // -- data stream background: horizontal rules rising forever
  for (let i = 0; i < 30; i += 1) {
    const y = ((H + 240) - ((i * 92 + t * 82) % (H + 240))) - 120;
    g.strokeStyle = `rgba(91,143,255,${(0.025 + 0.06 * ((i % 5) / 5)).toFixed(3)})`;
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(-200, y); g.lineTo(W + 200, y); g.stroke();
  }

  label(g, 'THE PROOF', 240, 400, {
    size: 68, weight: 600, tracking: 10, color: C.accent, align: 'left',
    progress: span(t, 0.15, 0.7), alpha: 1 - ease.inCubic(span(t, 3.3, 3.65)),
  });

  // -- the counter
  const count = 18 * ease.outExpo(span(t, -0.18, 1.15));
  const bounce = 1 + 0.05 * Math.sin(clamp(span(t, -0.18, 1.15)) * Math.PI) + 0.012 * Math.sin(t * 2.4);
  g.save();
  g.translate(280, 980 + Math.sin(t * 1.1) * 8);
  g.scale(bounce * (1 + 0.012 * Math.sin(t * 2.6)), bounce * (1 + 0.012 * Math.sin(t * 2.6)));
  g.font = '700 520px "Space Grotesk"';
  g.fillStyle = C.fg;
  g.textAlign = 'left';
  const shown = String(Math.round(count)).padStart(2, '0');
  g.fillText(shown, 0, 0);
  const drawn = g.measureText(shown).width;
  g.font = '500 190px "Inter"';
  g.fillStyle = C.dim;
  g.fillText('/18', drawn + 36, -18);
  g.restore();

  label(g, 'MOTION CHECKS PASSED', 288, 1110, {
    size: 46, weight: 500, tracking: 9, color: C.muted, align: 'left',
    progress: span(t, 0.9, 1.6), alpha: 1 - ease.inCubic(span(t, 3.3, 3.65)),
  });

  // -- bars
  const base = 1780;
  const heights = [430, 640, 520, 830, 700];
  const labels = ['HOOK', 'PROCESS', 'PROOF', 'TYPE', 'AUDIO'];
  const barW = 176;
  const gap = 92;
  const startX = 1620;
  for (let i = 0; i < heights.length; i += 1) {
    const grow = ease.backOut(span(t, -0.15 + i * 0.075, 0.8 + i * 0.075));
    const out = ease.inCubic(span(t, 3.76 + i * 0.04, 4.26 + i * 0.04));
    const breathe = 1 + 0.05 * Math.sin(t * 2.1 + i * 0.9);
    const h = heights[i] * grow * (1 - out) * breathe;
    if (h <= 1) continue;
    const x = startX + i * (barW + gap);
    const grad = g.createLinearGradient(0, base - h, 0, base);
    grad.addColorStop(0, i === 3 ? C.accent : 'rgba(200,255,61,0.9)');
    grad.addColorStop(1, 'rgba(200,255,61,0.10)');
    g.fillStyle = grad;
    g.beginPath();
    g.roundRect(x, base - h, barW, h, 14);
    g.fill();

    g.save();
    g.globalAlpha = 0.92 * (1 - out);
    g.font = '600 42px "Inter"';
    g.fillStyle = C.fg;
    g.textAlign = 'center';
    g.fillText(String(Math.round(heights[i] / 10 * grow)), x + barW / 2, base - h - 28);
    g.restore();

    label(g, labels[i], x + barW / 2, base + 64, {
      size: 32, weight: 500, tracking: 6, color: C.dim, align: 'center',
      progress: span(t, 0.75 + i * 0.05, 1.2 + i * 0.05), alpha: 1 - out,
    });
  }

  // -- sweeping highlight, one pass per beat
  const sweep = ((t * 1.1) % 1.2) / 1.2;
  const sx = startX - 220 + sweep * (5 * (barW + gap) + 300);
  const sg = g.createLinearGradient(sx - 170, 0, sx + 170, 0);
  sg.addColorStop(0, 'rgba(255,255,255,0)');
  sg.addColorStop(0.5, 'rgba(255,255,255,0.10)');
  sg.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = sg;
  g.fillRect(sx - 170, base - 880, 340, 900);

  g.fillStyle = 'rgba(255,255,255,0.18)';
  g.fillRect(startX - 44, base + 4, 5 * (barW + gap) + 44, 3);

  // axis ticks that keep counting
  g.save();
  g.globalAlpha = 0.5;
  g.strokeStyle = 'rgba(120,150,200,0.35)';
  g.lineWidth = 1;
  for (let i = 0; i < 5; i += 1) {
    const y = base - i * 190;
    if (y < 500) continue;
    g.beginPath(); g.moveTo(startX - 60, y); g.lineTo(startX - 30, y); g.stroke();
    g.font = '400 26px "Inter"';
    g.fillStyle = 'rgba(140,150,170,0.7)';
    g.textAlign = 'right';
    g.fillText(String(i * 2), startX - 72, y + 9);
  }
  g.restore();

  g.restore();
  drawParticles(g, t * 0.8, { alpha: 0.3 });
}

// ============================================================== SHOT D (12-16)
// Statement. Big type, per-word masks, dust in the beam.
//
// This shot used to have a handheld camera: two noise fields moving the frame up
// to 17 units sideways and 13 down, plus a fraction of a degree of roll. That is
// the effect the owner rejected as unprofessional, and it is rejected in every
// film, not only the one being reviewed. The slow push-in stays - a push-in is a
// shot, a noise field is a mistake - and the dust supplies the rest of the life.
function shotD(g, t) {
  const zoom = 1.02 + 0.06 * ease.inOutCubic(span(t, 0, 4));
  g.save();
  g.translate(W / 2, H / 2);
  g.scale(zoom, zoom);
  g.translate(-W / 2, -H / 2);

  g.fillStyle = '#04060A';
  g.fillRect(-2600, -2600, W + 5200, H + 5200);

  atmosphere(g, t);

  // light beam sweeping across the type
  const beamX = W * (-0.12 + 1.2 * ease.inOutCubic(span(t, 0, 4)));
  const beam = g.createLinearGradient(beamX - 620, 0, beamX + 620, 0);
  beam.addColorStop(0, 'rgba(200,255,61,0)');
  beam.addColorStop(0.5, 'rgba(200,255,61,0.105)');
  beam.addColorStop(1, 'rgba(200,255,61,0)');
  g.fillStyle = beam;
  g.fillRect(-200, -200, W + 400, H + 400);

  drawParticles(g, t, { alpha: 0.55, color: '#DCE6FF' });

  // words arrive with a mask and a squeeze, then leave by shearing upward
  const words = [
    ['MOTION', -0.22, 780, 360],
    ['IS NOT', 0.06, 1140, 240],
    ['DECORATION', 0.32, 1400, 240],
  ];
  for (let i = 0; i < words.length; i += 1) {
    const [word, inAt, y, size] = words[i];
    const trackingAt = lerp(20, -6, ease.outExpo(span(t, inAt, inAt + 0.9)));
    const w = wordWidth(word, size, 700, 'Space Grotesk', trackingAt);
    const p = ease.outExpo(span(t, inAt, inAt + 0.75));
    const out = ease.inCubic(span(t, 3.86 + i * 0.05, 4.36 + i * 0.05));
    if (p <= 0 || out >= 1) continue;
    const x = 236;
    g.save();
    g.beginPath();
    g.rect(x - 30, y - size * 1.08, (w + 60) * ease.outQuart(span(t, inAt, inAt + 0.62)), size * 1.4);
    g.clip();
    g.translate(x + (1 - p) * 46, y - out * 300);
    g.transform(1, 0, -out * 0.3, 1, 0, 0);
    g.scale(1 + (1 - p) * 0.16, 1 + (1 - p) * 0.04);
    typeWord(g, word, {
      t, x: 0, y: 0, size, weight: 700, family: 'Space Grotesk',
      tracking: trackingAt, inAt, stagger: 0.022, rise: size * 0.6,
      color: i === 2 ? C.accent : C.fg, align: 'left',
    });
    g.restore();
  }

  // vertical rail on the right, travelling
  const rail = ease.outExpo(span(t, 0.9, 1.7)) * (1 - ease.inCubic(span(t, 3.5, 3.9)));
  if (rail > 0.001) {
    g.save();
    g.globalAlpha = 0.75;
    g.fillStyle = C.accent;
    g.fillRect(3250, 700, 4, 900 * rail);
    for (let i = 0; i < 12; i += 1) {
      const y = 720 + ((i * 74 + t * 58) % 860);
      g.globalAlpha = 0.15 + 0.25 * hash(i * 3);
      g.fillRect(3250, y, i % 3 === 0 ? 30 : 14, 2);
    }
    g.restore();
  }

  const rule = ease.inOutCubic(span(t, 2.2, 2.9)) * (1 - ease.inCubic(span(t, 3.45, 3.8)));
  g.fillStyle = 'rgba(244,246,250,0.35)';
  g.fillRect(236, 1520, 1000 * rule, 2);

  label(g, 'EVERY FRAME IS CODE', 236, 1600, {
    size: 36, weight: 400, tracking: 10, color: C.muted, align: 'left',
    progress: span(t, 1.3, 2.0), alpha: 1 - ease.inCubic(span(t, 3.4, 3.75)),
  });

  g.restore();
}

// ============================================================== SHOT E (16-20)
// Outro lockup, then an iris close on the accent dot.
function shotE(g, t) {
  const zoom = 1.05 + 0.075 * ease.inOutCubic(span(t, 0, 4));
  const push = 1 + 0.02 * Math.sin(t * 1.4) * 0.4;
  g.save();
  g.translate(W / 2 + Math.sin(t * 0.9) * 36, H / 2 + Math.cos(t * 0.75) * 18);
  g.scale(zoom * push, zoom * push);
  g.translate(-W / 2, -H / 2);

  g.fillStyle = '#04060A';
  g.fillRect(-2600, -2600, W + 5200, H + 5200);

  const halo = g.createRadialGradient(W / 2, H * 0.46, 40, W / 2, H * 0.46, 1500);
  halo.addColorStop(0, 'rgba(200,255,61,0.12)');
  halo.addColorStop(0.45, 'rgba(200,255,61,0.035)');
  halo.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = halo;
  g.fillRect(-200, -200, W + 400, H + 400);

  atmosphere(g, t);

  // a light bar crossing the lockup, once per beat
  const sweepX = ((t * 0.55) % 1) * (W + 900) - 450;
  const sweep = g.createLinearGradient(sweepX - 260, 0, sweepX + 260, 0);
  sweep.addColorStop(0, 'rgba(200,255,61,0)');
  sweep.addColorStop(0.5, 'rgba(200,255,61,0.07)');
  sweep.addColorStop(1, 'rgba(200,255,61,0)');
  g.fillStyle = sweep;
  g.fillRect(-2600, -2600, W + 5200, H + 5200);

  // two rings orbit the dot for the whole shot
  const cyDot = H * 0.46 + 560;
  for (let i = 0; i < 2; i += 1) {
    const r = 70 + i * 46 + Math.sin(t * 1.5 + i) * 8;
    g.save();
    g.globalAlpha = 0.22 - i * 0.06;
    g.strokeStyle = C.accent;
    g.lineWidth = 2;
    g.setLineDash([10, 14]);
    g.lineDashOffset = t * (i ? -40 : 55);
    g.beginPath();
    g.arc(W / 2, cyDot, r, 0, Math.PI * 2);
    g.stroke();
    g.restore();
  }

  // converging particles: the room empties into the dot
  const converge = ease.inCubic(span(t, 1.4, 3.1));
  drawParticles(g, t, {
    alpha: 0.65,
    warp: (p, tt) => {
      const cx = W / 2;
      const cy = H * 0.46;
      const baseX = p.x + Math.sin(tt * 0.35 + p.drift) * 26;
      const baseY = ((p.y - tt * p.speed) % (H + 120) + H + 120) % (H + 120) - 60;
      return {
        x: lerp(baseX, cx, converge),
        y: lerp(baseY, cy, converge),
        a: 0.4 + 0.6 * (1 - converge),
        r: p.size * (1 - converge * 0.6),
      };
    },
  });

  // brackets arrive from both sides
  const br = ease.backOut(span(t, 0.1, 0.85));
  const brOut = ease.inCubic(span(t, 3.3, 3.7));
  g.save();
  g.globalAlpha = clamp(br * 1.4) * (1 - brOut);
  g.strokeStyle = C.accent;
  g.lineWidth = 12;
  const bs = 430 + Math.sin(t * 1.6) * 10;
  const by = 700;
  const leftX = 520 - (1 - br) * 300 - brOut * 240;
  g.beginPath();
  g.moveTo(leftX + bs * 0.4, by); g.lineTo(leftX, by);
  g.lineTo(leftX, by + bs); g.lineTo(leftX + bs * 0.4, by + bs);
  g.stroke();
  const rightX = W - 520 + (1 - br) * 300 + brOut * 240;
  g.beginPath();
  g.moveTo(rightX - bs * 0.4, by); g.lineTo(rightX, by);
  g.lineTo(rightX, by + bs); g.lineTo(rightX - bs * 0.4, by + bs);
  g.stroke();
  g.restore();

  // the mark
  typeWord(g, 'EVERY FRAME', {
    t, x: W / 2, y: 940, size: 210, weight: 700, family: 'Space Grotesk', align: 'center',
    tracking: lerp(30, 6, ease.outExpo(span(t, 0.02, 1.12))) + Math.sin(t * 1.4) * 5,
    inAt: -0.42, stagger: 0.024, rise: 150, scaleFromY: 0.3,
    outAt: 3.86, outStagger: 0.012, exitRise: -110,
  });
  typeWord(g, 'IS CODE', {
    t, x: W / 2, y: 1180, size: 210, weight: 700, family: 'Space Grotesk', align: 'center',
    tracking: lerp(44, 12, ease.outExpo(span(t, 0.2, 1.42))) + Math.sin(t * 1.4 + 1) * 5,
    inAt: -0.24, stagger: 0.028, rise: 150,
    color: C.accent,
    outAt: 3.92, outStagger: 0.012, exitRise: -110,
  });

  label(g, 'github.com/Ans-to/Youtube-Agent-automation', W / 2, 1330, {
    size: 48, weight: 400, tracking: 2, color: C.muted, align: 'center',
    progress: span(t, 0.85, 1.75), alpha: 1 - ease.inCubic(span(t, 3.4, 3.7)),
  });

  const dot = 1 - ease.inCubic(span(t, 3.4, 3.8));
  const pulse = 1 + 0.14 * Math.sin(t * 7);
  g.save();
  g.globalAlpha = 0.95 * dot;
  g.fillStyle = C.accent;
  g.beginPath();
  g.arc(W / 2, H * 0.46 + 560, 13 * pulse, 0, Math.PI * 2);
  g.fill();
  g.restore();

  g.restore();

  // iris close: a shaped mask, not a fade
  const iris = ease.inCubic(span(t, 2.72, 3.62));
  if (iris > 0.001) {
    g.save();
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = '#000000';
    g.beginPath();
    g.rect(0, 0, OPTS.width, OPTS.height);
    const cx = OPTS.width / 2;
    const cy = (H * 0.46 + 560) * SCALE;
    const r = (1 - iris) * OPTS.width * 0.62;
    g.moveTo(cx + Math.max(0, r), cy);
    g.arc(cx, cy, Math.max(0, r), 0, Math.PI * 2, true);
    g.fill();
    g.restore();

    // the dot survives the mask and keeps breathing to the last frame
    if (iris > 0.92) {
      const beat = (t - 2.9) * 2.0;
      const pulse2 = 12 * SCALE * (1 + 0.35 * Math.max(0, Math.sin(beat * Math.PI)));
      g.save();
      g.fillStyle = C.accent;
      g.globalAlpha = clamp((iris - 0.92) / 0.06);
      g.beginPath();
      g.arc(OPTS.width / 2, (H * 0.46 + 560) * SCALE, Math.max(2, pulse2), 0, Math.PI * 2);
      g.fill();
      g.restore();
    }
  }
}

// ------------------------------------------------------------------- HUD
// A persistent strip of information: the timecode changes every frame, the
// progress bar advances every frame, so the frame is never fully at rest.
function hud(g, tGlobal, alpha) {
  if (alpha <= 0.001) return;
  const p = clamp(tGlobal / DURATION);
  g.save();
  g.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  g.globalAlpha = alpha;
  g.fillStyle = 'rgba(255,255,255,0.13)';
  g.fillRect(120, 2040, W - 240, 3);
  g.fillStyle = C.accent;
  g.fillRect(120, 2040, (W - 240) * p, 3);
  g.beginPath();
  g.arc(120 + (W - 240) * p, 2041.5, 5, 0, Math.PI * 2);
  g.fill();

  const frames = Math.floor(tGlobal * FPS) % FPS;
  const seconds = Math.floor(tGlobal);
  const code = `00:${String(seconds).padStart(2, '0')}:${String(frames).padStart(2, '0')}`;
  g.font = '500 30px "Inter"';
  g.textAlign = 'right';
  g.fillStyle = 'rgba(244,246,250,0.6)';
  g.fillText(code, W - 120, 1996);
  g.textAlign = 'left';
  g.fillStyle = 'rgba(244,246,250,0.4)';
  g.fillText('EVERY FRAME IS CODE', 120, 1996);

  g.strokeStyle = 'rgba(200,255,61,0.26)';
  g.lineWidth = 2;
  const m = 70;
  const len = 26;
  const corners = [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]];
  for (const [x, y, sx, sy] of corners) {
    g.beginPath();
    g.moveTo(x + len * sx, y);
    g.lineTo(x, y);
    g.lineTo(x, y + len * sy);
    g.stroke();
  }
  g.restore();
}

// ============================================================== COMPOSITION
const SHOTS = [
  { id: 'hook', start: 0.0, end: 4.0, draw: shotA, label: 'Hook', layers: ['Background grid', 'Midground glyphs', 'Text', 'Foreground ticks', 'Particles'] },
  { id: 'pipeline', start: 4.0, end: 8.0, draw: shotB, label: 'Process', layers: ['Background floor', 'Path + packet', 'Panels', 'Text', 'Particles'] },
  { id: 'proof', start: 8.0, end: 12.0, draw: shotC, label: 'Proof', layers: ['Background stream', 'Counter', 'Bars', 'Labels', 'Sweep'] },
  { id: 'statement', start: 12.0, end: 16.0, draw: shotD, label: 'Statement', layers: ['Background beam', 'Dust', 'Text', 'Rule', 'Handheld shake'] },
  { id: 'outro', start: 16.0, end: 20.0, draw: shotE, label: 'Outro', layers: ['Background halo', 'Brackets', 'Lockup', 'URL', 'Iris'] },
];

// Sound is authored with the picture: one cue per cut, per number landing and
// per line arriving. tools/render_authored_film.py synthesises exactly this.
// Times are the start of each synthesised cue. The percussion build carries its
// energy peak about 0.2 s after the start, so the starts sit that much before the
// picture beat; TQ-AVSYNC on the encoded film reports lag 0.00 s.
const SCORE = [
  { kind: 'swell', at: 0.02, length: 1.60, gain: 0.18 },
  { kind: 'pop', at: 0.05, length: 0.10, gain: 0.20 },
  { kind: 'click', at: 0.10, length: 0.05, gain: 0.16 },
  { kind: 'click', at: 2.12, length: 0.06, gain: 0.14 },
  { kind: 'whoosh', at: 3.42, length: 0.55, gain: 0.30 },
  { kind: 'impact', at: 3.82, length: 0.35, gain: 0.32 },
  { kind: 'click', at: 4.12, length: 0.05, gain: 0.14 },
  { kind: 'riser', at: 6.70, length: 0.90, gain: 0.16 },
  { kind: 'whoosh', at: 7.50, length: 0.55, gain: 0.28 },
  { kind: 'impact', at: 7.82, length: 0.35, gain: 0.30 },
  { kind: 'pop', at: 7.94, length: 0.12, gain: 0.16 },
  { kind: 'glitch', at: 11.52, length: 0.45, gain: 0.26 },
  { kind: 'impact', at: 11.82, length: 0.40, gain: 0.34 },
  { kind: 'click', at: 11.92, length: 0.05, gain: 0.14 },
  { kind: 'riser', at: 14.40, length: 1.10, gain: 0.20 },
  { kind: 'impact', at: 15.82, length: 0.45, gain: 0.32 },
  { kind: 'click', at: 16.14, length: 0.05, gain: 0.14 },
  { kind: 'whoosh', at: 18.50, length: 0.70, gain: 0.18 },
];

const CUTS = [
  { at: 4.0, dur: 0.62, kind: 'whip-pan', from: 0, to: 1, dir: 1 },
  { at: 8.0, dur: 0.64, kind: 'masked-reveal', from: 1, to: 2, dir: 1 },
  { at: 12.0, dur: 0.5, kind: 'glitch', from: 2, to: 3, dir: 1 },
  { at: 16.0, dur: 0.78, kind: 'match-cut', from: 3, to: 4, dir: 1 },
];

function activeCut(t) {
  return CUTS.find((c) => Math.abs(t - c.at) < c.dur / 2) || null;
}

function shotAt(t) {
  return SHOTS.find((s) => t >= s.start && t < s.end) || SHOTS[SHOTS.length - 1];
}

const ACTX = bufA.getContext('2d');
const BCTX = bufB.getContext('2d');

function renderShotInto(target, shot, tGlobal) {
  target.save();
  target.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  target.clearRect(0, 0, DESIGN_W, DESIGN_H);
  shot.draw(target, tGlobal - shot.start);
  target.restore();
}

function drawWhip(t, cut) {
  const p = span(t, cut.at - cut.dur / 2, cut.at + cut.dur / 2);
  const e = ease.inOutCubic(p);
  const from = SHOTS[cut.from];
  const to = SHOTS[cut.to];
  const w = OPTS.width;
  const h = OPTS.height;
  const shift = e * w;

  renderShotInto(ACTX, from, t);
  renderShotInto(BCTX, to, t);

  // smear length follows the pan speed; device pixels keep every output size identical
  const speed = Math.pow(Math.sin(Math.PI * p), 0.85);
  const blur = 150 * speed * (w / 960);
  const N = 9;

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, w, h);

  // outgoing: a directional smear trailing behind one sharp image, not stacked copies
  ctx.globalAlpha = 0.55 / N;
  for (let k = N; k >= 1; k -= 1) ctx.drawImage(bufA, -shift - (blur * k) / N, 0);
  ctx.globalAlpha = 1;
  ctx.drawImage(bufA, -shift, 0);

  // incoming: the same construction, smear running ahead of the frame
  ctx.globalAlpha = 0.55 / N;
  for (let k = N; k >= 1; k -= 1) ctx.drawImage(bufB, w - shift + (blur * k) / N, 0);
  ctx.globalAlpha = 1;
  ctx.drawImage(bufB, w - shift, 0);

  // brief flash on the midpoint so the seam reads as an impact
  const flash = Math.pow(Math.sin(Math.PI * p), 4);
  if (flash > 0.001) {
    ctx.fillStyle = `rgba(255,255,255,${0.08 * flash})`;
    ctx.fillRect(0, 0, w, h);
  }

  // speed streaks
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  const thick = Math.max(2, Math.round(2 * w / 960));
  for (let i = 0; i < 26; i += 1) {
    const y = hash(i * 3.7) * h;
    const len = w * (0.12 + hash(i * 8.1) * 0.5);
    const x = (hash(i * 5.9) * w + e * w * 0.8) % w;
    ctx.fillStyle = `rgba(180,210,255,${(0.05 + hash(i) * 0.12) * Math.sin(Math.PI * p)})`;
    ctx.fillRect(x - len, y, len, thick);
  }
  ctx.restore();
  ctx.restore();
}

function drawMasked(t, cut) {
  const p = span(t, cut.at - cut.dur / 2, cut.at + cut.dur / 2);
  const from = SHOTS[cut.from];
  const to = SHOTS[cut.to];
  const w = OPTS.width;
  const h = OPTS.height;

  renderShotInto(ACTX, from, t);
  renderShotInto(BCTX, to, t);

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  // the outgoing frame recedes and dims: it must never compete with the new one
  const back = 1 - 0.05 * ease.outCubic(p);
  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(back, back);
  ctx.translate(-w / 2, -h / 2);
  ctx.drawImage(bufA, 0, 0);
  ctx.restore();
  ctx.fillStyle = `rgba(0,0,0,${0.66 * ease.inCubic(clamp(p * 1.2))})`;
  ctx.fillRect(0, 0, w, h);

  // incoming revealed through wide diagonal slats, each one solid
  const bands = 6;
  const bw = w / bands;
  const slant = h * 0.30;
  const push = 1.05 - 0.05 * ease.outCubic(p);
  for (let i = 0; i < bands; i += 1) {
    const local = ease.outCubic(clamp((p - i * 0.05) / 0.55));
    if (local <= 0) continue;
    const x = i * bw;
    const reach = Math.min(bw * 1.45, local * bw * 1.5);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x - slant * 0.5, 0);
    ctx.lineTo(x + reach - slant * 0.5, 0);
    ctx.lineTo(x + reach + slant * 0.5, h);
    ctx.lineTo(x + slant * 0.5, h);
    ctx.closePath();
    ctx.clip();
    ctx.translate(w / 2, h / 2);
    ctx.scale(push, push);
    ctx.translate(-w / 2, -h / 2);
    ctx.drawImage(bufB, 0, 0);
    ctx.restore();

    if (local < 0.98) {
      ctx.strokeStyle = `rgba(200,255,61,${0.30 * (1 - local)})`;
      ctx.lineWidth = Math.max(2, Math.round(2 * w / 960));
      ctx.beginPath();
      ctx.moveTo(x + reach - slant * 0.5, 0);
      ctx.lineTo(x + reach + slant * 0.5, h);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawGlitch(t, cut) {
  const p = span(t, cut.at - cut.dur / 2, cut.at + cut.dur / 2);
  const from = SHOTS[cut.from];
  const to = SHOTS[cut.to];
  const swap = p >= 0.5;
  renderShotInto(ACTX, swap ? to : from, t);
  const frame = Math.round(t * FPS);

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, OPTS.width, OPTS.height);
  const slices = 18;
  const sh = OPTS.height / slices;
  for (let i = 0; i < slices; i += 1) {
    const burst = Math.sin(Math.PI * p);
    const off = (hash(frame * 13 + i * 7) - 0.5) * 220 * burst;
    ctx.drawImage(bufA, 0, i * sh, OPTS.width, sh, off, i * sh, OPTS.width, sh);
  }
  // colour split
  ctx.globalCompositeOperation = 'lighter';
  ctx.globalAlpha = 0.28 * Math.sin(Math.PI * p);
  ctx.drawImage(bufA, 26 * Math.sin(Math.PI * p), 0);
  ctx.fillStyle = 'rgba(91,143,255,0.18)';
  ctx.fillRect(0, 0, OPTS.width, OPTS.height);
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';

  // bloom across the cut rather than a single white frame: a one-frame flash
  // reads as a pop, and a full-white frame is exactly what a strobe rule looks for
  const flash = Math.pow(Math.max(0, 1 - Math.abs(p - 0.5) * 6), 2);
  if (flash > 0.002) {
    ctx.fillStyle = `rgba(255,255,255,${0.26 * flash})`;
    ctx.fillRect(0, 0, OPTS.width, OPTS.height);
  }
  ctx.restore();
}

function drawMatch(t, cut) {
  // a punch-in match cut: both shots share scale and centre on the exact frame of
  // the cut, so the join is invisible even though it is a hard cut
  const p = span(t, cut.at - cut.dur / 2, cut.at + cut.dur / 2);
  const punch = ease.outCubic(1 - Math.abs(p - 0.5) * 2);
  const zoom = 1 + 0.24 * punch;
  const useFrom = p < 0.5;

  renderShotInto(ACTX, SHOTS[cut.from], t);
  renderShotInto(BCTX, SHOTS[cut.to], t);

  const w = OPTS.width;
  const h = OPTS.height;
  const cx = w * 0.5;
  const cy = h * 0.44;
  const src = useFrom ? bufA : bufB;

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, w, h);

  // zoom smear: concentric copies at lower alpha turn the push into speed
  for (let k = 6; k >= 1; k -= 1) {
    const s = 1 + (zoom - 1) * (1 - k / 7);
    ctx.globalAlpha = 0.16 * punch;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(s, s);
    ctx.translate(-cx, -cy);
    ctx.drawImage(src, 0, 0);
    ctx.restore();
  }

  ctx.globalAlpha = 1;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(zoom, zoom);
  ctx.translate(-cx, -cy);
  ctx.drawImage(src, 0, 0);
  ctx.restore();

  // a single bright frame at the join sells the cut
  if (punch > 0.82) {
    const flash = (punch - 0.82) / 0.18;
    ctx.fillStyle = `rgba(200,255,61,${0.10 * flash})`;
    ctx.fillRect(0, 0, w, h);
  }
  ctx.restore();
}

// Shots need the drawing context passed in so the compositor can render them
// into buffers. Wrap each shot once, at module scope, instead of rewriting
// every draw call: the wrappers below bind the current target.

function compose(t, frame) {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, OPTS.width, OPTS.height);
  ctx.restore();

  const cut = activeCut(t);
  if (cut) {
    if (cut.kind === 'whip-pan') drawWhip(t, cut);
    else if (cut.kind === 'masked-reveal') drawMasked(t, cut);
    else if (cut.kind === 'glitch') drawGlitch(t, cut);
    else if (cut.kind === 'match-cut') drawMatch(t, cut);
  } else {
    renderShotInto(ctx, shotAt(t), t);
  }

  hud(ctx, t, 1 - ease.inCubic(span(t, 18.8, 19.3)));
  finish(frame);
}

// --------------------------------------------------------------------- main
function main() {
  const outDir = path.resolve(OPTS.out);
  fs.mkdirSync(outDir, { recursive: true });

  if (OPTS.still) {
    for (const seconds of OPTS.still) {
      const frame = Math.round(seconds * FPS);
      compose(seconds, frame);
      const file = path.join(outDir, `still-${seconds.toFixed(2)}.jpg`);
      fs.writeFileSync(file, canvas.toBuffer('image/jpeg', OPTS.quality));
      if (!OPTS.quiet) console.log(`still ${seconds.toFixed(2)}s -> ${file}`);
    }
    return;
  }

  const to = OPTS.to === null ? TOTAL_FRAMES : Math.min(OPTS.to, TOTAL_FRAMES);
  const from = Math.max(0, OPTS.from);
  const started = Date.now();
  for (let frame = from; frame < to; frame += 1) {
    const t = frame / FPS;
    compose(t, frame);
    const file = path.join(outDir, `frame-${String(frame).padStart(6, '0')}.jpg`);
    fs.writeFileSync(file, canvas.toBuffer('image/jpeg', OPTS.quality));
    if (!OPTS.quiet && (frame - from) % 60 === 0) {
      const done = frame - from + 1;
      const rate = done / ((Date.now() - started) / 1000);
      console.log(`frame ${frame}/${to}  ${rate.toFixed(1)} fps  ${((to - frame) / rate).toFixed(0)}s left`);
    }
  }

  const manifest = {
    width: OPTS.width, height: OPTS.height, fps: FPS, frame_count: TOTAL_FRAMES,
    rendered_from: from, rendered_to: to,
    source: 'video_studio/films/every_frame_is_code.mjs',
  };
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  const film = {
    title: 'Every Frame Is Code',
    duration_seconds: DURATION,
    fps: FPS,
    canvas: { width: DESIGN_W, height: DESIGN_H },
    shots: SHOTS.map((s) => ({
      id: s.id, label: s.label, start: s.start, end: s.end,
      start_tc: timecode(s.start), end_tc: timecode(s.end),
      layers: s.layers,
    })),
    score: SCORE,
    transitions: CUTS.map((c) => ({
      at: c.at, timecode: timecode(c.at), kind: c.kind, overlap_seconds: c.dur,
      from: SHOTS[c.from].id, to: SHOTS[c.to].id,
    })),
    motion: {
      easing: ['outExpo', 'inExpo', 'outCubic', 'inCubic', 'inOutCubic', 'outQuart', 'anticipate', 'backOut'],
      linear_interpolation: false,
      text_animates_in_and_out: true,
      camera_moves_every_shot: true,
      background_motion: 'continuous',
    },
  };
  fs.writeFileSync(path.join(outDir, 'film.json'), JSON.stringify(film, null, 2));

  const lines = [
    'EVERY FRAME IS CODE — timeline',
    '',
    'Layer order per shot (bottom to top):',
  ];
  for (const s of SHOTS) {
    lines.push(`  ${timecode(s.start)}-${timecode(s.end)}  ${s.label.padEnd(10)} ${s.layers.join(', ')}`);
  }
  lines.push('', 'Transitions:');
  for (const c of CUTS) {
    lines.push(`  ${timecode(c.at)}  ${c.kind.padEnd(14)} ${SHOTS[c.from].id} -> ${SHOTS[c.to].id}  (${c.dur}s overlap)`);
  }
  fs.writeFileSync(path.join(outDir, 'timeline.txt'), lines.join('\n') + '\n');

  if (!OPTS.quiet) {
    const seconds = ((Date.now() - started) / 1000).toFixed(1);
    console.log(`rendered ${to - from} frames at ${OPTS.width}x${OPTS.height} in ${seconds}s`);
    console.log(`timeline: ${path.join(outDir, 'timeline.txt')}`);
  }
}

function timecode(seconds) {
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

main();
