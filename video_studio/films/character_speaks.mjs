#!/usr/bin/env node
/**
 * "Every Frame Is Code" — the character cut.
 *
 * A 12-second authored scene that puts the rig on screen: the character walks in,
 * speaks a line with viseme-driven lip-sync, gestures, and reacts, over the same
 * graphic language as the motion piece (grid, HUD, accent type).
 *
 * Everything is drawn per frame; nothing is a sequence of pre-rendered images.
 *
 *   node video_studio/films/character_speaks.mjs --out frames --width 1920
 *   node video_studio/films/character_speaks.mjs --out stills --still 1.2,5.0,9.5
 */
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

import { GlobalFonts, createCanvas } from '@napi-rs/canvas';
import { characterFrame, speechTimeline, blinkSchedule, noise1, HIP_HEIGHT } from '../character/animate.mjs';
import { drawCharacter, LOOK } from '../character/body.mjs';
import { drawStick, resolveInk, INK } from '../character/stick.mjs';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');

const DESIGN_W = 3840;
const DESIGN_H = 2160;
const DURATION_SECONDS = 12;   // only used when no voice track is supplied

// ------------------------------------------------------------------ options
function parseArgs(argv) {
  const opts = {
    out: 'frames', width: DESIGN_W, height: null, fps: 30, quality: 92,
    from: 0, to: null, still: null, quiet: false,
    voiceLines: null, voiceEnvelope: null, style: 'stick', boil: 1,
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
    else if (flag === '--voice-lines') opts.voiceLines = value();
    else if (flag === '--voice-envelope') opts.voiceEnvelope = value();
    else if (flag === '--style') opts.style = value();
    else if (flag === '--boil') opts.boil = Number(value());
    else throw new Error(`Unknown option: ${flag}`);
  }
  opts.height = opts.height || Math.round((opts.width * DESIGN_H) / DESIGN_W / 2) * 2;
  if (!['stick', 'design'].includes(opts.style)) {
    throw new Error(`Unknown --style ${opts.style} (expected stick or design)`);
  }
  if (!Number.isFinite(opts.boil) || opts.boil < 0) throw new Error('--boil must be a number >= 0');
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
const STYLE = OPTS.style;
const BOIL = OPTS.boil;
const SCALE = OPTS.width / DESIGN_W;
const FPS = OPTS.fps;
const W = DESIGN_W;
const H = DESIGN_H;

// -------------------------------------------------------------------- fonts
const FACES = [
  ['Inter', 'inter-latin-400-normal.woff2'],
  ['Inter', 'inter-latin-600-normal.woff2'],
  ['Inter', 'inter-latin-700-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-600-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
];
for (const [family, file] of FACES) {
  GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
}

// -------------------------------------------------------------------- scene
// The palette follows the pen. A stickman is drawn in ink on paper, so the film
// behind it has to be paper too — otherwise the figure is black on black. Both
// palettes are monochrome-plus-one-accent, so the channel look does not change,
// only its value.
const PALETTE = {
  design: {
    bg: '#05070C', bg2: '#0A0F18', panel: '#0C121D', fg: '#F4F6FA',
    muted: '#8B94A6', accent: '#C8FF3D', support: '#5B8FFF',
  },
  stick: {
    bg: '#F2F2F2', bg2: '#E7E7E7', panel: '#EDEDED', fg: '#121212',
    muted: '#6E6E6E', accent: '#121212', support: '#3A3A3A',
  },
};
const C = PALETTE[STYLE] || PALETTE.stick;

// Every accent in the film goes through one helper. In ink mode the accent is
// the ink colour, so no stray lime can survive into a black-and-white channel
// upload — the tint was visible as an olive wash over the paper background.
const accentRGBA = (alpha) => (STYLE === 'stick'
  ? `rgba(18,18,18,${alpha})`
  : `rgba(200,255,61,${alpha})`);
const supportRGBA = (alpha) => (STYLE === 'stick'
  ? `rgba(58,58,58,${alpha})`
  : `rgba(91,143,255,${alpha})`);

// --------------------------------------------------------------- measurement
/**
 * Vertical extent of the drawn figure, measured from the solved bones.
 *
 * The camera used to assume a fixed height (1810 units), which was true for the
 * illustrated character and false for the stickman: its head is drawn 1.05x the
 * head bone, so it sat above the assumed top and the frame cropped it. Measuring
 * means the two pens frame correctly without either being special-cased.
 */
function figureBounds(solved) {
  let top = Infinity;
  let bottom = -Infinity;
  for (const bone of Object.values(solved)) {
    for (const p of [bone.origin, bone.end]) {
      if (p[1] < top) top = p[1];
      if (p[1] > bottom) bottom = p[1];
    }
  }
  if (solved.head) {
    // The head is a circle centred on the head bone's end, not a bone segment.
    const r = solved.head.length * (STYLE === 'stick' ? 1.05 : 0.62);
    top = Math.min(top, solved.head.end[1] - r);
  }
  return { top, bottom, height: bottom - top };
}

/** How much of the frame above the head a shot keeps, per shot id. */
const HEADROOM = { W: 0.20, M: 0.16, C: 0.14, W2: 0.20 };

/**
 * Vertical pivot for a shot, solved so the top of the head lands on the
 * headroom line after the zoom is applied.
 *
 *   screen(y) = pivot + (y - pivot) * zoom
 *
 * Setting `screen(headTop) = H * headroom` and solving for pivot gives the
 * expression below. At zoom 1 the pivot does not matter, so we centre the
 * figure instead of dividing by zero.
 */
function cameraPivotY(headTop, groundY, zoom, headroom) {
  if (Math.abs(zoom - 1) < 1e-6) return (headTop + groundY) / 2;
  return (H * headroom - headTop * zoom) / (1 - zoom);
}

const clamp = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const lerp = (a, b, t) => a + (b - a) * t;
const span = (t, a, b) => clamp((t - a) / (b - a));
const ease = {
  outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inCubic: (x) => x * x * x,
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  inOutCubic: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outBack: (x) => (x <= 0 ? 0 : 1 + 2.4 * Math.pow(x - 1, 3) + 1.6 * Math.pow(x - 1, 2)),
};

// 0-3 walk in | 3-8 speak with gestures | 8-12 react, wave, walk out
const AUTHORED_LINES = [
  { text: 'EVERY FRAME', start: 2.9, end: 4.5 },
  { text: 'IS DRAWN TWICE', start: 4.9, end: 6.6 },
  { text: 'ONCE IN BONES', start: 7.0, end: 8.4 },
  { text: 'ONCE IN CODE', start: 8.7, end: 10.2 },
];

/**
 * Read the voice track's own timings. When a real voiceover exists the picture
 * follows the audio: every cut, caption and gesture is placed on the syllable it
 * belongs to, instead of on numbers typed in by hand.
 */
function loadVoice(linesPath, envelopePath) {
  if (!linesPath) return null;
  const source = path.resolve(linesPath);
  const data = JSON.parse(fs.readFileSync(source, 'utf8'));
  const raw = Array.isArray(data) ? data : data.lines;
  if (!Array.isArray(raw) || raw.length !== AUTHORED_LINES.length) {
    throw new Error(`--voice-lines needs ${AUTHORED_LINES.length} lines to match the captions, got ${raw && raw.length}`);
  }
  const lines = raw.map((line, index) => {
    const start = Number(line.start);
    const end = Number(line.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      throw new Error(`voice line ${index + 1} has an unusable time range`);
    }
    return { id: line.id || `L${index + 1}`, start, end, spoken: line.spoken || line.text || '' };
  });

  const envSource = envelopePath
    ? path.resolve(envelopePath)
    : path.join(path.dirname(source), 'envelope.json');
  let envelope = null;
  if (fs.existsSync(envSource)) {
    const env = JSON.parse(fs.readFileSync(envSource, 'utf8'));
    const frames = new Map();
    for (const item of env.lines || []) {
      frames.set(item.id, { fps: Number(item.fps) || FPS, openness: item.openness || [] });
    }
    envelope = { fps: Number(env.fps) || FPS, frames };
  }
  return { lines, envelope, path: source };
}

const VOICE = loadVoice(OPTS.voiceLines, OPTS.voiceEnvelope);
const LINES = AUTHORED_LINES.map((line, index) => (
  VOICE ? { ...line, start: VOICE.lines[index].start, end: VOICE.lines[index].end } : line
));

/** Mouth amplitude from the rendered audio: 0 shut, 1 on the loudest syllable. */
function envelopeAt(seconds) {
  if (!VOICE || !VOICE.envelope) return 1;
  const index = LINES.findIndex((line) => seconds >= line.start - 0.18 && seconds <= line.end + 0.12);
  if (index < 0) return 0;
  const entry = VOICE.envelope.frames.get(VOICE.lines[index].id);
  if (!entry || !entry.openness.length) return 1;
  const local = Math.floor((seconds - LINES[index].start) * entry.fps);
  if (local < 0) return 0;
  return entry.openness[Math.min(local, entry.openness.length - 1)] || 0;
}

const SPEECH = LINES.flatMap((line) =>
  speechTimeline(line.text.split(' '), { start: line.start, end: line.end, seed: line.start }));

const LAST_END = LINES[LINES.length - 1].end;
// A voice-driven cut ends when the voice does, plus room for the wave and exit.
const DURATION = VOICE
  ? Math.ceil((LAST_END + 1.75) * FPS) / FPS
  : DURATION_SECONDS;
const TOTAL_FRAMES = Math.round(DURATION * FPS);
const BLINKS = blinkSchedule(DURATION, 7);

const GROUND_Y = 2010;
// The figure is sized to the frame, not to a magic constant. The shot list and
// the ground line were composed for a figure 1600 design units tall, so the pen
// is scaled to hit that height exactly — otherwise the stickman (whose solved
// skeleton is 1850 units at scale 0.95) sits under the top HUD in the wide shot
// and blows past the bottom of frame in the medium.
const FIG_TARGET_HEIGHT = 1600;
const FIG_SCALE = (() => {
  const probe = characterFrame(1, { mode: 'idle', scale: 1, groundY: 0, x: 0 });
  const b = figureBounds(probe.solved);
  return FIG_TARGET_HEIGHT / (b.bottom - b.top);
})();

/**
 * Coverage. A dialogue scene is cut, not held: wide to establish, medium to
 * talk, close for the line that matters, wide again to leave. `zoom` multiplies
 * the figure's scale, `anchor` is where the figure sits across the frame.
 */
const WALK_IN_END = Math.max(0.9, LINES[0].start - 0.35);
const WALK_OUT_START = Math.min(LAST_END + 0.30, DURATION - 0.9);
const WAVE_AT = Math.min(LINES[LINES.length - 1].start + 0.45, DURATION - 1.75);

const COVERAGE = [
  // Zoom values are chosen so the frame edge lands somewhere a camera would put
  // it: the full figure, just above the knee, then the waist. Intermediate
  // values slice through a shin, which reads as a mistake rather than a choice.
  { id: 'W', start: 0.0, end: LINES[0].start + 0.55, zoom: 1.00, anchor: 0.40, note: 'wide, walk-in' },
  { id: 'M', start: LINES[0].start + 0.55, end: (LINES[1].end + LINES[2].start) / 2, zoom: 1.45, anchor: 0.40, note: 'medium, first two lines' },
  { id: 'C', start: (LINES[1].end + LINES[2].start) / 2, end: LINES[2].end + 0.5, zoom: 1.95, anchor: 0.40, note: 'close, the turn' },
  { id: 'W2', start: LINES[2].end + 0.5, end: DURATION, zoom: 1.00, anchor: 0.45, note: 'wide, wave and exit' },
];

function coverageAt(seconds) {
  return COVERAGE.find((shot) => seconds >= shot.start && seconds < shot.end) || COVERAGE[COVERAGE.length - 1];
}


/** Where the character stands/walks, in design pixels. */
function figureAt(t) {
  const walkIn = ease.inOutCubic(span(t, 0.0, WALK_IN_END));
  const walkOut = ease.inOutCubic(span(t, WALK_OUT_START, DURATION));
  const x = lerp(300, 1240, walkIn) + walkOut * 1300;
  const walking = (t < WALK_IN_END && t > 0.05) || t > WALK_OUT_START;
  return { x, walking };
}

function drawBackground(ctx, t) {
  const shot = coverageAt(t);
  // slow environmental pan: everything in the world drifts, the camera stays put
  ctx.save();
  ctx.translate(-((t * 34) % 160) * shot.zoom, 0);
  const g = ctx.createLinearGradient(0, 0, W * 0.4, H);
  g.addColorStop(0, C.bg);
  g.addColorStop(1, C.bg2);
  ctx.fillStyle = g;
  ctx.fillRect(-2600, -2600, W + 5200, H + 5200);

  // drifting grid, denser toward the floor so it reads as perspective
  ctx.save();
  ctx.strokeStyle = supportRGBA(0.16);
  ctx.lineWidth = 2;
  const drift = (t * 60) % 160;
  for (let x = -200 + drift; x < W + 200; x += 160) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x + 240, H);
    ctx.stroke();
  }
  for (let i = 0; i < 26; i += 1) {
    const p = (i + (t * 0.12) % 1) / 26;
    const y = H * 0.42 + Math.pow(p, 2.2) * H * 0.62;
    ctx.strokeStyle = supportRGBA((0.05 + 0.14 * p).toFixed(3));
    ctx.beginPath();
    ctx.moveTo(-100, y);
    ctx.lineTo(W + 100, y);
    ctx.stroke();
  }
  ctx.restore();

  // orbiting ring behind the figure: large, slow, always moving
  const { x } = figureAt(t);
  for (let i = 0; i < 2; i += 1) {
    const r = 760 + i * 210 + Math.sin(t * 0.7 + i) * 30;
    ctx.save();
    ctx.globalAlpha = 0.14 - i * 0.05;
    ctx.strokeStyle = C.accent;
    ctx.lineWidth = 3;
    ctx.setLineDash([16, 26]);
    ctx.lineDashOffset = t * (i ? -70 : 110);
    ctx.beginPath();
    ctx.arc(x, H * 0.5, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  // drifting motes, depth-sorted by parallax so the frame has a foreground
  for (let i = 0; i < 42; i += 1) {
    const seed = i * 7.13;
    const px = ((Math.sin(seed) * 0.5 + 0.5) * W + t * (40 + (i % 5) * 26)) % W;
    const py = ((Math.cos(seed * 1.7) * 0.5 + 0.5) * H + Math.sin(t * 0.6 + seed) * 40) % H;
    const size = 2 + (i % 4) * 2.4;
    ctx.globalAlpha = 0.10 + (i % 3) * 0.05;
    ctx.fillStyle = i % 7 === 0 ? C.accent : '#DCE6FF';
    ctx.beginPath();
    ctx.arc(px, py, size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // a warm pool of light behind the character, moving with them
  const pool = ctx.createRadialGradient(x, H * 0.52, 0, x, H * 0.52, 1500);
  pool.addColorStop(0, accentRGBA(0.10));
  pool.addColorStop(0.5, accentRGBA(0.03));
  pool.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = pool;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

function drawFloor(ctx, t, showShadow = true) {
  const shade = ctx.createLinearGradient(0, GROUND_Y - 60, 0, H);
  // A light floor on paper: the same gradient with the values swapped, so the
  // figure still gains contrast against it instead of sinking into it.
  shade.addColorStop(0, STYLE === 'stick' ? 'rgba(210,210,210,0.0)' : 'rgba(10,15,24,0.0)');
  shade.addColorStop(1, STYLE === 'stick' ? 'rgba(198,198,198,0.95)' : 'rgba(4,6,10,0.95)');
  ctx.fillStyle = shade;
  ctx.fillRect(0, GROUND_Y - 60, W, H - GROUND_Y + 60);

  ctx.strokeStyle = STYLE === 'stick' ? 'rgba(18,18,18,0.35)' : 'rgba(200,255,61,0.35)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, GROUND_Y);
  ctx.lineTo(W, GROUND_Y);
  ctx.stroke();

  // Contact shadow under the feet. Only when the ground line is on screen: a
  // push-in crops the floor away, and the shadow's own top edge then floated in
  // the bottom of a waist-up shot with no feet to cast it.
  if (!showShadow) return;
  const { x } = figureAt(t);
  const shadow = ctx.createRadialGradient(x, GROUND_Y + 8, 0, x, GROUND_Y + 8, 520);
  shadow.addColorStop(0, 'rgba(0,0,0,0.62)');
  shadow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = shadow;
  ctx.beginPath();
  ctx.ellipse(x, GROUND_Y + 8, 480, 60, 0, 0, Math.PI * 2);
  ctx.fill();
}

/** A caption that arrives word by word and leaves the same way. */
function drawCaption(ctx, t, line, index) {
  const inAt = line.start - 0.25;
  const outAt = line.end + 0.35;
  const p = ease.outExpo(span(t, inAt, inAt + 0.5));
  const out = ease.inCubic(span(t, outAt, outAt + 0.4));
  if (p <= 0 || out >= 1) return;

  const words = line.text.split(' ');
  const size = 148;
  ctx.save();
  ctx.font = `700 ${size}px "Space Grotesk"`;
  const widths = words.map((w) => ctx.measureText(w).width);
  const gap = size * 0.26;
  const total = widths.reduce((a, b) => a + b, 0) + gap * (words.length - 1);
  const shot = coverageAt(t);
  let x = shot.id === 'C' ? W * 0.60 : W * 0.62;
  const y = shot.id === 'C' ? 900 : 620;

  // accent rule that draws on with the line
  ctx.fillStyle = accentRGBA(0.85);
  ctx.fillRect(W * 0.62 - 8, y + 96, (total + 16) * ease.outCubic(span(t, inAt, inAt + 0.7)), 5);

  words.forEach((word, i) => {
    const per = span(t, inAt + i * 0.09, inAt + i * 0.09 + 0.5);
    const e = ease.outBack(per);
    const alpha = clamp(per * 3) * (1 - out);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = i === words.length - 1 ? C.accent : C.fg;
    const dy = (1 - e) * 90 + out * -70;
    ctx.fillText(word, x, y + dy);
    ctx.restore();
    x += widths[i] + gap;
  });

  // index marker, so the caption is part of the design language
  ctx.globalAlpha = clamp(p * 2) * (1 - out);
  ctx.font = '600 46px "Inter"';
  ctx.fillStyle = C.muted;
  ctx.fillText(`0${index + 1} / 0${LINES.length}`, W * 0.62, y - 150);
  ctx.restore();
}

function drawHud(ctx, t) {
  const p = clamp(t / DURATION);
  ctx.save();
  ctx.font = '600 42px "Inter"';
  ctx.fillStyle = C.muted;
  ctx.globalAlpha = clamp(t / 0.35);
  ctx.fillText('CHARACTER / EVERY FRAME IS CODE', 180, 150);
  ctx.globalAlpha = 1;

  // opening beat: a rule sweeps across the top of frame, so frame 1 has motion
  const intro = ease.outCubic(span(t, 0, 0.9));
  if (intro > 0 && intro < 1) {
    ctx.fillStyle = accentRGBA(0.75);
    ctx.fillRect(180, 200, (W - 360) * intro, 4);
  }

  ctx.fillStyle = 'rgba(255,255,255,0.10)';
  ctx.fillRect(180, H - 150, 900, 4);
  ctx.fillStyle = C.accent;
  ctx.fillRect(180, H - 150, 900 * p, 4);

  const total = Math.round(t * FPS);
  const timecode = `${String(Math.floor(total / (FPS * 60))).padStart(2, '0')}:${String(Math.floor(total / FPS) % 60).padStart(2, '0')}:${String(total % FPS).padStart(2, '0')}`;
  ctx.fillStyle = C.muted;
  ctx.textAlign = 'right';
  ctx.fillText(timecode, W - 180, H - 120);
  ctx.fillText('3840 x 2160 / 30 FPS', W - 180, 150);
  ctx.restore();
}

// ------------------------------------------------------------------- canvas
const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');

function render(t) {
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.clearRect(0, 0, W, H);

  drawBackground(ctx, t);
  drawFloor(ctx, t, coverageAt(t).zoom <= 1.05);

  const { x, walking } = figureAt(t);
  // gesture on the free arm for each line: down between lines, lifting on the beat
  let gesture = 0;
  for (const line of LINES) {
    const up = ease.outCubic(span(t, line.start - 0.1, line.start + 0.35))
      * (1 - ease.inCubic(span(t, line.end - 0.1, line.end + 0.35)));
    gesture = Math.max(gesture, up);
  }

  const frame = characterFrame(t, {
    mode: walking ? 'walk' : 'idle',
    scale: FIG_SCALE,
    groundY: GROUND_Y,
    hipX: x,
    stride: 1.05,
    speech: t > LINES[0].start - 0.12 && t < LAST_END + 0.25
      ? { timeline: SPEECH, envelope: envelopeAt }
      : null,
    blinks: BLINKS,
    wave: t > WAVE_AT - 0.05 && t < WAVE_AT + 1.75 ? { at: WAVE_AT, dur: 1.7 } : null,
    gesture,
  });

  // camera: framing comes from the current shot size, movement from the dolly,
  // the push and a handheld layer, so no frame is ever identical to the last
  const shot = coverageAt(t);
  const shotAge = t - shot.start;
  const shotProgress = clamp((t - shot.start) / (shot.end - shot.start));
  const dolly = ease.inOutCubic(shotProgress) * 150;
  const push = 1 + 0.05 * shotProgress + 0.012 * Math.sin(t * 0.9);
  const shakeX = noise1(t * 0.9) * 12 + noise1(t * 3.1 + 11) * 4;
  const shakeY = noise1(t * 1.1 + 5) * 9 + noise1(t * 2.7 + 23) * 3;

  // The camera is aimed at the figure, not at a hard-coded height. The old code
  // assumed a 1810-unit figure, which was true of the illustrated character and
  // false of the stickman: its head is drawn 1.05x the head bone, so the top of
  // the head sat above the assumed top and every push-in cropped it.
  //
  // Each shot declares how much headroom the head gets. The camera then solves
  // for the pivot that puts the top of the head on that line at that zoom, which
  // means a close shot crops at the thigh (as a real camera does) and never
  // slices the head.
  const bounds = figureBounds(frame.solved);
  const focusX = W * shot.anchor + dolly;
  const focusY = cameraPivotY(bounds.top, GROUND_Y, shot.zoom, HEADROOM[shot.id] ?? 0.16);
  ctx.save();
  ctx.translate(focusX + shakeX, focusY + shakeY);
  ctx.scale(shot.zoom * push, shot.zoom * push);
  ctx.translate(-focusX, -focusY);
  // The pen is a channel decision, not a per-film one: the default is the
  // monochrome stickman so every upload looks like the same channel. `--style
  // design` keeps the original illustrated figure available.
  if (STYLE === 'stick') {
    drawStick(ctx, frame.solved, {
      viseme: frame.viseme,
      blink: frame.blink,
      browRaise: frame.browRaise,
      boil: BOIL,
      frame: Math.round(t * FPS),
    });
  } else {
    drawCharacter(ctx, frame.solved, {
      viseme: frame.viseme,
      blink: frame.blink,
      browRaise: frame.browRaise,
      breathe: frame.breath,
      look: LOOK,
    });
  }
  ctx.restore();

  // a short dissolve-out at the very top of each shot sells the cut without
  // cross-fading the whole film: 2 frames of accent flash
  if (shotAge < 0.07) {
    const flash = 1 - shotAge / 0.07;
    ctx.fillStyle = accentRGBA(`${0.10 * flash}`);
    ctx.fillRect(0, 0, W, H);
  }

  // One caption at a time. Two adjacent lines overlapped during a cross-fade and
  // printed on top of each other, which is unreadable even though neither line
  // was wrong on its own.
  const captionIndex = LINES.reduce((found, line, index) => (
    t >= line.start - 0.25 && t <= line.end + 0.75 ? index : found
  ), -1);
  if (captionIndex >= 0) drawCaption(ctx, t, LINES[captionIndex], captionIndex);
  drawHud(ctx, t);

  // foreground bokeh: big, soft, and moving faster than the world behind it
  for (let i = 0; i < (STYLE === 'stick' ? 0 : 7); i += 1) {
    const seed = i * 2.718;
    const speed = 90 + i * 26;
    const bx = ((Math.sin(seed) * 0.5 + 0.5) * W * 1.4 + t * speed) % (W * 1.4) - W * 0.2;
    const by = H * (0.12 + 0.14 * ((i * 0.37) % 1)) + Math.sin(t * 0.8 + seed) * 40;
    const r = 90 + (i % 4) * 70;
    const halo = ctx.createRadialGradient(bx, by, 0, bx, by, r);
    halo.addColorStop(0, accentRGBA(`${0.05 + (i % 3) * 0.02}`));
    halo.addColorStop(1, accentRGBA(0));
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(bx, by, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // a soft light band sweeping the frame, so the whole image breathes
  const sweepX = (((t * 0.22) % 1) * (W + 2200)) - 1100;
  const sweep = ctx.createLinearGradient(sweepX - 700, 0, sweepX + 700, H * 0.5);
  sweep.addColorStop(0, supportRGBA(0));
  sweep.addColorStop(0.5, supportRGBA(0.055));
  sweep.addColorStop(1, supportRGBA(0));
  ctx.fillStyle = sweep;
  ctx.fillRect(0, 0, W, H);

  // vignette + grain, deterministic per frame
  const vig = ctx.createRadialGradient(W / 2, H / 2, H * 0.32, W / 2, H / 2, H * 0.95);
  vig.addColorStop(0, 'rgba(0,0,0,0)');
  vig.addColorStop(1, STYLE === 'stick' ? 'rgba(120,120,120,0.10)' : 'rgba(0,0,0,0.55)');
  ctx.fillStyle = vig;
  ctx.fillRect(0, 0, W, H);

  const frameIndex = Math.round(t * FPS);
  ctx.globalAlpha = 0.035;
  ctx.fillStyle = '#ffffff';
  for (let i = 0; i < 120; i += 1) {
    const hx = Math.abs(Math.sin((i * 12.9898 + frameIndex * 78.233) * 43758.5453));
    const hy = Math.abs(Math.sin((i * 39.3467 + frameIndex * 11.135) * 24634.6345));
    ctx.fillRect((hx % 1) * W, (hy % 1) * H, 3, 3);
  }
  ctx.globalAlpha = 1;
}

// -------------------------------------------------------------------- output
const timecode = (seconds) => {
  const total = Math.round(seconds * FPS);
  return `${String(Math.floor(total / (FPS * 60))).padStart(2, '0')}:${String(Math.floor(total / FPS) % 60).padStart(2, '0')}:${String(total % FPS).padStart(2, '0')}`;
};

function writeFilm(outDir) {
  const film = {
    title: 'Every Frame Is Code (character cut)',
    duration_seconds: Math.round(DURATION * 1000) / 1000,
    fps: FPS,
    canvas: { width: W, height: H },
    shots: [
      { id: 'A', label: 'walk-in', start: 0, end: WALK_IN_END, layers: ['background', 'grid', 'floor', 'character', 'hud'] },
      { id: 'B', label: 'speech', start: WALK_IN_END, end: WALK_OUT_START, layers: ['background', 'grid', 'floor', 'character', 'captions', 'hud'] },
      { id: 'C', label: 'wave-out', start: WALK_OUT_START, end: DURATION, layers: ['background', 'grid', 'floor', 'character', 'captions', 'hud', 'vignette'] },
    ],
    motion: {
      rig: 'two-bone IK, spring settle, viseme timeline',
      linear_interpolation: false,
      text_animates_in_and_out: true,
      camera_moves_every_shot: true,
      background_motion: 'continuous',
    },
    score: [
      { kind: 'swell', at: 0.05, length: 1.6, gain: 0.16 },
      { kind: 'click', at: 0.35, length: 0.05, gain: 0.14 },
      ...(VOICE ? [{ kind: 'swell', at: COVERAGE[2].start, length: 1.2, gain: 0.05 }] : []),
      { kind: 'whoosh', at: Math.max(0.1, WALK_OUT_START - 0.15), length: 0.7, gain: 0.2 },
      { kind: 'impact', at: Math.max(0.1, DURATION - 0.18), length: 0.4, gain: 0.26 },
    ],
    speech: LINES,
    lip_sync: VOICE
      ? { events: SPEECH.length, source: 'audio envelope x viseme timeline', envelope: true }
      : { events: SPEECH.length, source: 'viseme timeline' },
    voice: VOICE
      ? { timing_source: path.basename(VOICE.path), duration_seconds: Math.round(LAST_END * 100) / 100, lip_sync: 'measured', envelope: !!VOICE.envelope }
      : null,
    // A dialogue scene moves less than a kinetic type piece: the figure holds
    // frame while the mouth and the camera work. The gate is declared here so it
    // is visible in the artifact, not quietly relaxed inside the driver.
    motion_gate: { min_mean: 0.8, max_static: 0.5 },
    // The look is declared in the artifact, not inferred from the frames: a
    // downstream tool can refuse to publish a colour frame to a monochrome
    // channel without opening a single image.
    character: {
      style: STYLE,
      boil: BOIL,
      ink: STYLE === 'stick' ? resolveInk() : null,
      palette: STYLE === 'stick' ? 'monochrome' : 'dark-tech',
      monochrome: STYLE === 'stick',
    },
  };
  fs.writeFileSync(path.join(outDir, 'film.json'), JSON.stringify(film, null, 2));

  const lines = ['EVERY FRAME IS CODE (character cut) — timeline', ''];
  for (const shot of film.shots) {
    lines.push(`  ${timecode(shot.start)}-${timecode(shot.end)}  ${shot.label.padEnd(10)} ${shot.layers.join(', ')}`);
  }
  lines.push('', 'Lines:');
  for (const line of LINES) lines.push(`  ${line.start.toFixed(1)}-${line.end.toFixed(1)}s  ${line.text}`);
  fs.writeFileSync(path.join(outDir, 'timeline.txt'), lines.join('\n') + '\n');
  return film;
}

function main() {
  const outDir = path.resolve(OPTS.out);
  fs.mkdirSync(outDir, { recursive: true });

  const from = Math.max(0, Math.round(OPTS.from));
  const to = Math.min(TOTAL_FRAMES, OPTS.to === null ? TOTAL_FRAMES : Math.round(OPTS.to));
  const started = Date.now();

  // Stills are how a look is judged, so they carry the same metadata as a render:
  // a rejected still and a shipped frame are described by the same artifact.
  if (OPTS.still) {
    for (const seconds of OPTS.still) {
      render(seconds);
      const file = path.join(outDir, `still-${seconds.toFixed(2)}.jpg`);
      fs.writeFileSync(file, canvas.toBuffer('image/jpeg', OPTS.quality));
      if (!OPTS.quiet) console.log(`still ${seconds.toFixed(2)}s -> ${file}`);
    }
    writeFilm(outDir);
    return;
  }

  for (let frame = from; frame < to; frame += 1) {
    render(frame / FPS);
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
    source: 'video_studio/films/character_speaks.mjs',
  };
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  writeFilm(outDir);

  if (!OPTS.quiet) {
    console.log(`rendered ${to - from} frames at ${OPTS.width}x${OPTS.height} in ${((Date.now() - started) / 1000).toFixed(1)}s`);
  }
}

main();
