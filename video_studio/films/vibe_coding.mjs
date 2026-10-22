#!/usr/bin/env node
/**
 * Vibe Coding on Arena, through GitHub — a long-form motion-graphics film.
 *
 * No character, no footage, no screenshots: every frame is drawn. The GitHub
 * and Arena "screens" are interfaces built from rectangles and type in
 * `video_studio/motion/ui.mjs`, so the film can show a click, a diff, a failing
 * check or a merge at any resolution, and can never drift out of date with a
 * screenshot of a product that shipped a redesign.
 *
 * The narration is the clock. Each scene owns a range of spoken lines, and the
 * timings come from the audio the synthesiser actually produced, so the picture,
 * the highlights and the burned-in captions follow the voice rather than a table
 * typed by hand.
 *
 *   node video_studio/films/vibe_coding.mjs --out frames --width 1920 --voice-lines voice/lines.json
 *   node video_studio/films/vibe_coding.mjs --out stills --width 1280 --still 40,120,300
 *   node video_studio/films/vibe_coding.mjs --plan
 */
import { createRequire } from 'module';
import v8 from 'v8';
import vm from 'vm';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

import { GlobalFonts, createCanvas } from '@napi-rs/canvas';
import {
  UI, clamp, lerp, span, ease, noise, text, wordsIn, panel, browser, cursor, measure,
  clickRing, codeBlock, checkRow, chip, rule, slash, speedLines, shards,
  rainbowStreak, roundRect,
} from '../motion/ui.mjs';

// Collectors for native canvas memory, requested from inside the script so a
// render does not depend on the caller remembering to pass node flags.
let forceGC = global.gc;
if (!forceGC) {
  v8.setFlagsFromString('--expose_gc');
  forceGC = vm.runInNewContext('gc');
}

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');

const DESIGN_W = 3840;
const DESIGN_H = 2160;
const FALLBACK_SECONDS = 690;

// ------------------------------------------------------------------ options
function parseArgs(argv) {
  const opts = {
    out: 'frames', width: 1920, height: null, fps: 30, quality: 90,
    from: 0, to: null, still: null, quiet: false, plan: false,
    voiceLines: null, voiceScript: null,
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
    else if (flag === '--plan') opts.plan = true;
    else if (flag === '--voice-lines') opts.voiceLines = value();
    else if (flag === '--voice-script') opts.voiceScript = value();
    else if (flag === '--help' || flag === '-h') {
      console.log(fs.readFileSync(new URL(import.meta.url)).toString().split('*/')[0]);
      process.exit(0);
    } else throw new Error(`Unknown option: ${flag}`);
  }
  opts.height = opts.height || Math.round((opts.width * DESIGN_H) / DESIGN_W / 2) * 2;
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
const FPS = OPTS.fps;
const W = DESIGN_W;
const H = DESIGN_H;

const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');
const SCALE = OPTS.width / W;

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

// ------------------------------------------------------------------- script
/**
 * The scene table.
 *
 * `takes` says how many narration lines the scene owns; they are consumed in
 * order, so the narration and the picture cannot drift apart — a line added to
 * the script is claimed by a scene or the film refuses to render.
 */
const SCENES = [
  { id: 'open', kind: 'title', takes: 4, chapter: 'VIBE CODING', dark: true,
    title: 'BUILD IT\nBY DESCRIBING IT',
    note: 'A real app, a real repository, no typing.' },
  { id: 'define', kind: 'statement', takes: 9, chapter: '01 / THE IDEA',
    title: 'INTENTION,\nNOT SYNTAX',
    rules: ['SMALL STEPS', 'READ THE DIFF', 'KEEP IT IN GIT'],
    note: 'Three rules carry the rest of this film.' },
  { id: 'loop', kind: 'pipeline', takes: 7, chapter: '02 / THE LOOP',
    title: 'THE LOOP', steps: ['PROMPT', 'PLAN', 'BRANCH', 'DIFF', 'CHECKS', 'MERGE'],
    note: 'Six parts, repeated until it is a product.' },
  { id: 'github', kind: 'github', takes: 12, chapter: 'STEP 01 / GITHUB',
    title: 'ONE EMPTY REPOSITORY' },
  { id: 'connect', kind: 'connect', takes: 10, chapter: 'STEP 02 / CONNECT',
    title: 'GIVE THE AGENT ONE REPO' },
  { id: 'prompt', kind: 'prompt', takes: 13, chapter: 'STEP 03 / THE PROMPT',
    title: 'SAY WHAT DONE LOOKS LIKE' },
  { id: 'agent', kind: 'agent', takes: 8, chapter: 'STEP 04 / THE BRANCH',
    title: 'IT WORKS IN A BRANCH' },
  { id: 'diff', kind: 'diff', takes: 10, chapter: 'STEP 05 / THE DIFF',
    title: 'READ EVERY LINE' },
  { id: 'checks', kind: 'checks', takes: 10, chapter: 'STEP 06 / CHECKS',
    title: 'WAIT FOR GREEN' },
  { id: 'merge', kind: 'merge', takes: 9, chapter: 'STEP 07 / SHIP',
    title: 'MERGE, THEN LIVE' },
  { id: 'feature', kind: 'feature', takes: 10, chapter: 'STEP 08 / AGAIN',
    title: 'ONE MORE FEATURE' },
  { id: 'mistakes', kind: 'revert', takes: 9, chapter: 'STEP 09 / RECOVERY',
    title: 'WHEN IT BREAKS' },
  { id: 'patterns', kind: 'patterns', takes: 11, chapter: 'STEP 10 / PATTERNS',
    title: 'PROMPTS THAT WORK' },
  { id: 'safety', kind: 'safety', takes: 7, chapter: 'STEP 11 / SECRETS',
    title: 'NOTHING SECRET IN GIT' },
  { id: 'habits', kind: 'habits', takes: 10, chapter: 'STEP 12 / HABITS',
    title: 'KEEP IT FAST' },
  { id: 'recap', kind: 'recap', takes: 8, chapter: 'THE WHOLE LOOP',
    title: 'SEVEN STEPS' },
  { id: 'outro', kind: 'outro', takes: 4, chapter: 'START', dark: true,
    title: 'ONE PAGE.\nONE PROMPT.\nONE PULL REQUEST.' },
];

// -------------------------------------------------------------- voice input
/**
 * Timings. Without a voice track the film still renders: every scene gets a
 * reading pace, so a silent preview is possible. With a track, the audio wins.
 */
function loadVoice(linesPath, scriptPath) {
  const narrationPath = scriptPath
    ? path.resolve(scriptPath)
    : path.join(HERE, 'vibe_coding.voice.json');
  const narration = JSON.parse(fs.readFileSync(narrationPath, 'utf8'));

  if (!linesPath) return { lines: null, narration, path: narrationPath };

  const data = JSON.parse(fs.readFileSync(path.resolve(linesPath), 'utf8'));
  const raw = Array.isArray(data) ? data : data.lines;
  if (!Array.isArray(raw) || raw.length !== narration.lines.length) {
    throw new Error(`--voice-lines has ${raw && raw.length} lines; the film expects `
      + `${narration.lines.length}. Picture and voice would drift apart.`);
  }
  const lines = raw.map((line, index) => {
    const start = Number(line.start);
    const end = Number(line.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      throw new Error(`voice line ${index + 1} has an unusable time range`);
    }
    return {
      id: line.id || `L${index + 1}`,
      text: narration.lines[index].text,
      scene: narration.lines[index].scene,
      start,
      end,
    };
  });
  return { lines, narration, path: narrationPath };
}

const VOICE = loadVoice(OPTS.voiceLines, OPTS.voiceScript);

/** Attach each scene to its slice of the narration. */
function buildScenes(lines) {
  let cursorLine = 0;
  const built = SCENES.map((scene) => {
    const owned = lines.slice(cursorLine, cursorLine + scene.takes);
    cursorLine += scene.takes;
    if (owned.length !== scene.takes) {
      throw new Error(`scene ${scene.id} claims ${scene.takes} lines but only ${owned.length} are left`);
    }
    return {
      ...scene,
      lines: owned,
      start: owned[0].start - 0.55,
      end: owned[owned.length - 1].end + 0.5,
    };
  });
  if (cursorLine !== lines.length) {
    throw new Error(`${lines.length - cursorLine} narration lines were never given a scene`);
  }
  // Scenes must not overlap: an overlap would flash two pictures at once.
  for (let i = 1; i < built.length; i += 1) {
    if (built[i].start < built[i - 1].end - 0.001) built[i].start = built[i - 1].end;
  }
  return built;
}

/** Silent fallback: a reading pace per line, so stills and previews work. */
function silentLines() {
  let t = 3.0;
  return VOICE.narration.lines.map((line) => {
    const words = String(line.text).split(/\s+/).length;
    const duration = Math.max(2.2, words / 3.0);
    const entry = { id: line.id, text: line.text, scene: line.scene, start: t, end: t + duration };
    t += duration + 0.42;
    return entry;
  });
}

const LINES = VOICE.lines || silentLines();
const SHOTS = buildScenes(LINES);
const TOTAL_SECONDS = SHOTS[SHOTS.length - 1].end + 2.6;
const TOTAL_FRAMES = Math.round(TOTAL_SECONDS * FPS);

const sceneAt = (t) => SHOTS.find((scene) => t >= scene.start && t < scene.end) || SHOTS[SHOTS.length - 1];
const lineIndexAt = (scene, t) => scene.lines.findIndex((line) => t >= line.start && t <= line.end + 0.35);

if (OPTS.plan) {
  console.log(JSON.stringify({
    fps: FPS,
    duration_seconds: Math.round(TOTAL_SECONDS * 1000) / 1000,
    frames: TOTAL_FRAMES,
    scenes: SHOTS.map((scene) => ({
      id: scene.id, kind: scene.kind, start: +scene.start.toFixed(2), end: +scene.end.toFixed(2),
      lines: scene.lines.length,
    })),
  }, null, 2));
  process.exit(0);
}

// ------------------------------------------------------------------ texture
function stageField(ctx, t, dark = false) {
  if (dark) {
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, '#0B0B0C');
    g.addColorStop(0.6, '#141417');
    g.addColorStop(1, '#0A0A0B');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    const glow = ctx.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, H * 0.85);
    glow.addColorStop(0, 'rgba(242,194,48,0.10)');
    glow.addColorStop(1, 'rgba(242,194,48,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);

    const step = 120;
    const ox = (t * 18) % step;
    const oy = (t * 11) % step;
    ctx.fillStyle = 'rgba(242,194,48,0.14)';
    for (let gx = -step; gx < W + step; gx += step) {
      for (let gy = -step; gy < H + step; gy += step) {
        ctx.fillRect(gx + ox, gy + oy, 7, 7);
      }
    }
    return;
  }
  const g = ctx.createLinearGradient(0, 0, W * 0.3, H);
  g.addColorStop(0, '#E2E2E6');
  g.addColorStop(0.55, UI.stage);
  g.addColorStop(1, UI.stage2);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  // A dot field drifting across the stage. It is nearly invisible on its own and
  // it is the reason the pale scenes are never a dead white field: the whole
  // frame moves, even while a diagram holds.
  const step = 96;
  const ox = (t * DOT_SPEED) % step;
  const oy = (t * DOT_SPEED * 0.55) % step;
  ctx.fillStyle = `rgba(20,20,26,${DOT_ALPHA})`;
  for (let gx = -step; gx < W + step; gx += step) {
    for (let gy = -step; gy < H + step; gy += step) {
      ctx.fillRect(gx + ox, gy + oy, DOT_SIZE, DOT_SIZE);
    }
  }

  // a slow pool of light that keeps the flat stage alive behind a still card
  const x = W * (0.5 + Math.sin(t * 0.07) * 0.18);
  const glow = ctx.createRadialGradient(x, H * 0.45, 0, x, H * 0.45, H * 0.9);
  glow.addColorStop(0, 'rgba(255,255,255,0.30)');
  glow.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
}

const GRAIN_ALPHA = Number(process.env.VC_GRAIN_ALPHA || 0.10);
const GRAIN_BLOCK = Number(process.env.VC_GRAIN_BLOCK || 3);
const DOT_ALPHA = Number(process.env.VC_DOT_ALPHA || 0.18);
const DOT_SIZE = Number(process.env.VC_DOT_SIZE || 9);
const DOT_SPEED = Number(process.env.VC_DOT_SPEED || 70);

// Grain is generated once as a few noise tiles and then cycled, so a 1080p film
// does not spend its whole render budget making random numbers. Every frame gets
// a different tile at a different offset: that is what film grain does.
const GRAIN_TILES = [];
function grainTiles() {
  if (GRAIN_TILES.length) return GRAIN_TILES;
  for (let n = 0; n < 4; n += 1) {
    const tile = createCanvas(256, 256);
    const tctx = tile.getContext('2d');
    const image = tctx.createImageData(256, 256);
    const block = GRAIN_BLOCK;
    for (let y = 0; y < 256; y += 1) {
      for (let x = 0; x < 256; x += 1) {
        const cell = (Math.floor(x / block) + Math.floor(y / block) * 97) * 0.731;
        const v = noise(cell * 0.017 + n * 91.7) * 255;
        const i = (y * 256 + x) * 4;
        image.data[i] = v;
        image.data[i + 1] = v;
        image.data[i + 2] = v;
        image.data[i + 3] = 255;
      }
    }
    tctx.putImageData(image, 0, 0);
    GRAIN_TILES.push(tile);
  }
  return GRAIN_TILES;
}

function grain(ctx, frameIndex, amount = GRAIN_ALPHA) {
  const tiles = grainTiles();
  ctx.save();
  ctx.globalCompositeOperation = 'overlay';
  ctx.globalAlpha = amount;
  // two passes at different scales so the pattern never repeats visibly
  for (let layer = 0; layer < 2; layer += 1) {
    const tile = tiles[(frameIndex * 3 + layer) % tiles.length];
    const ox = -((frameIndex * 137 + layer * 91) % 256);
    const oy = -((frameIndex * 71 + layer * 53) % 256);
    for (let x = ox; x < W; x += 256) {
      for (let y = oy; y < H; y += 256) {
        ctx.drawImage(tile, x, y);
      }
    }
  }
  ctx.restore();
}

/** The reference film's bands: a chapter on the left, a clock on the right. */
function bands(ctx, scene, t) {
  const topH = 108;
  const botH = 96;
  ctx.save();
  ctx.fillStyle = '#0A0A0A';
  ctx.fillRect(0, 0, W, topH);
  ctx.fillRect(0, H - botH, W, botH);

  text(ctx, scene.chapter, 150, topH / 2 + 16, {
    size: 40, weight: 700, family: 'Inter', color: UI.gold, tracking: 6,
  });
  const total = Math.round(t * FPS);
  const clock = `${String(Math.floor(total / (FPS * 60))).padStart(2, '0')}:${String(Math.floor(total / FPS) % 60).padStart(2, '0')}`;
  text(ctx, clock, W - 150, topH / 2 + 16, {
    size: 38, weight: 600, color: 'rgba(242,242,242,0.55)', align: 'right', tracking: 3,
  });

  // progress rule across the bottom band, so a long film has a sense of place
  const p = clamp(t / TOTAL_SECONDS);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(150, H - botH / 2 - 2, W - 300, 5);
  ctx.fillStyle = UI.gold;
  ctx.fillRect(150, H - botH / 2 - 2, (W - 300) * p, 5);

  // The current spoken line, as a broadcast subtitle.
  //
  // It is wrapped rather than truncated: a sentence that runs off the right edge
  // is a reading error the viewer has to absorb, and clipping it at sixteen words
  // cut some lines mid-thought. Two lines of at most 56 characters fit the frame
  // at this size on every scene, dark or pale.
  const line = LINES.find((l) => t >= l.start - 0.15 && t <= l.end + 0.4);
  if (line) {
    const limit = 56;
    const words = String(line.text).split(/\s+/);
    const rows = [];
    let row = '';
    for (const word of words) {
      if ((row + ' ' + word).trim().length > limit && row) {
        rows.push(row.trim());
        row = word;
      } else {
        row = (row + ' ' + word).trim();
      }
    }
    if (row) rows.push(row);
    const top = H - botH - 34 - (rows.length - 1) * 54;
    rows.slice(-2).forEach((value, i) => {
      text(ctx, value, W / 2, top + i * 54, {
        size: 44, weight: 600,
        // On a dark scene the caption is light; dark grey on near-black was
        // technically present and practically unreadable.
        color: scene.dark ? 'rgba(242,242,242,0.82)' : 'rgba(12,12,14,0.66)',
        align: 'center',
      });
    });
  }
  ctx.restore();
}

/** A chapter card overlay: the number and the idea, slammed in. */
function chapterOverlay(ctx, scene, local) {
  const p = span(local, 0, 0.5);
  if (p <= 0 || local > 2.4) return;
  const out = span(local, 1.7, 2.4);
  ctx.save();
  ctx.globalAlpha = 1 - out;
  ctx.translate(W / 2, H / 2);
  const zoom = lerp(1.18, 1, ease.outExpo(p));
  ctx.scale(zoom, zoom);
  ctx.translate(-W / 2, -H / 2);
  ctx.fillStyle = 'rgba(10,10,10,0.86)';
  ctx.fillRect(0, 0, W, H);
  text(ctx, scene.chapter, W / 2, H / 2 - 90, {
    size: 52, weight: 700, color: UI.gold, align: 'center', tracking: 10,
  });
  text(ctx, scene.title, W / 2, H / 2 + 60, {
    size: 150, weight: 700, family: 'Space Grotesk', color: UI.white, align: 'center',
  });
  rule(ctx, W / 2 - 300, H / 2 + 120, 600, { progress: ease.outCubic(p), colour: UI.red, thickness: 10 });
  ctx.restore();
}

// ------------------------------------------------------------------- scenes
/** A dark title card: kinetic words, a slash, and a hit. */
function drawTitle(ctx, scene, t, local) {
  stageField(ctx, t, true);
  const total = scene.end - scene.start;
  speedLines(ctx, { x: W / 2, y: H / 2, w: W * 1.4, h: H, progress: 1, count: 26, colour: '#FFFFFF', alpha: 0.05, angle: -0.2 });

  const p = span(local, 0.1, 2.2);
  const lines = scene.title.split('\n');
  lines.forEach((line, i) => {
    const lp = span(local, 0.15 + i * 0.22, 1.4 + i * 0.22);
    const e = ease.outExpo(lp);
    ctx.save();
    ctx.globalAlpha = clamp(lp * 2);
    text(ctx, line, W / 2 + (1 - e) * 120, H / 2 - 120 + i * 190, {
      size: i === 0 ? 190 : 190, weight: 700, family: 'Space Grotesk',
      color: i === lines.length - 1 ? UI.gold : UI.white, align: 'center',
    });
    ctx.restore();
  });

  // the hit lands on the loudest word, not on frame one
  const hit = span(local, 1.5, 1.9);
  if (hit > 0) {
    slash(ctx, { x: W / 2, y: H / 2 + 40, length: W * 0.95, angle: -0.06, progress: span(local, 1.5, 2.3), width: 30, colour: UI.red });
    shards(ctx, { x: W / 2, y: H / 2, progress: span(local, 1.5, 2.4), count: 14, radius: 900, colour: UI.gold });
  }
  if (local < 0.16) {
    ctx.fillStyle = `rgba(255,255,255,${(1 - local / 0.16) * 0.9})`;
    ctx.fillRect(0, 0, W, H);
  }
  text(ctx, scene.note, W / 2, H - 300, {
    size: 52, weight: 500, color: 'rgba(242,242,242,0.6)', align: 'center',
    alpha: clamp(span(local, 2.2, 3.0)),
  });
}

/** Big type on the pale stage: the idea scenes. */
function drawStatement(ctx, scene, t, local) {
  stageField(ctx, t);
  const idx = lineIndexAt(scene, t);
  const lines = scene.title.split('\n');
  lines.forEach((line, i) => {
    const p = span(local, 0.2 + i * 0.5, 1.6 + i * 0.5);
    text(ctx, line, 260, 620 + i * 200, {
      size: 168, weight: 700, family: 'Space Grotesk', color: i === 1 ? UI.red : UI.ink,
      alpha: clamp(p * 1.5),
    });
  });
  rule(ctx, 264, 880, 900, { progress: ease.outCubic(span(local, 0.6, 1.6)), colour: UI.ink, thickness: 8 });

  // the three rules tick in with the narration
  (scene.rules || []).forEach((value, i) => {
    const p = span(local, 3.0 + i * 1.1, 3.7 + i * 1.1);
    if (p <= 0) return;
    const y = 1120 + i * 150;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.4);
    ctx.translate((1 - ease.outExpo(p)) * -80, 0);
    ctx.beginPath();
    ctx.arc(300, y - 18, 30, 0, Math.PI * 2);
    ctx.fillStyle = UI.ink;
    ctx.fill();
    text(ctx, String(i + 1), 300, y - 6, { size: 34, weight: 700, color: UI.gold, align: 'center' });
    text(ctx, value, 370, y, { size: 76, weight: 700, family: 'Space Grotesk', color: UI.ink });
    ctx.restore();
  });

  // A slash marks a moment, not a paragraph: it lands once, on the third rule,
  // and is gone. A permanent one floated beside the type like a stray mark.
  const idx3 = scene.lines[2];
  if (idx3 && t >= idx3.start && t <= idx3.start + 0.8) {
    slash(ctx, {
      x: W * 0.76, y: 1160, length: 720, angle: -0.18,
      progress: span(t, idx3.start, idx3.start + 0.8), width: 22, colour: UI.red,
    });
  }
  void idx;
}

/** The loop: six nodes, one pulse travelling through them. */
function drawPipeline(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 360, {
    size: 132, weight: 700, family: 'Space Grotesk', color: UI.ink,
    alpha: clamp(span(local, 0.1, 0.7) * 2),
  });
  text(ctx, scene.note, 246, 440, { size: 46, weight: 500, color: 'rgba(23,23,26,0.6)', alpha: clamp(span(local, 1.0, 1.6)) });

  const steps = scene.steps;
  const y = 900;
  const x0 = 300;
  const gap = (W - 600) / (steps.length - 1);
  const active = Math.floor(span(local, 1.2, steps.length * 0.9 + 1.2) * steps.length);
  const travel = ((local * 0.42) % 1);

  // the rail
  ctx.save();
  rule(ctx, x0, y - 3, W - 600, { progress: ease.outCubic(span(local, 0.3, 1.4)), colour: 'rgba(11,11,12,0.25)', thickness: 6 });
  ctx.restore();

  steps.forEach((step, i) => {
    const p = span(local, 0.4 + i * 0.28, 1.1 + i * 0.28);
    if (p <= 0) return;
    const x = x0 + i * gap;
    const on = i <= active;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.6);
    const pop = ease.outBack(p);
    ctx.translate(x, y);
    ctx.scale(lerp(0.6, 1, pop), lerp(0.6, 1, pop));
    ctx.beginPath();
    ctx.arc(0, 0, 74, 0, Math.PI * 2);
    ctx.fillStyle = on ? UI.ink : UI.window;
    ctx.fill();
    ctx.lineWidth = 5;
    ctx.strokeStyle = UI.ink;
    ctx.stroke();
    text(ctx, String(i + 1), 0, 18, {
      size: 54, weight: 700, color: on ? UI.gold : UI.ink, align: 'center',
    });
    text(ctx, step, 0, 150, {
      size: 44, weight: 700, family: 'Inter', color: UI.ink, align: 'center', tracking: 2,
    });
    ctx.restore();
  });

  // a pulse travelling the rail, so the loop reads as a loop
  const px = x0 + travel * (W - 600);
  ctx.save();
  ctx.globalAlpha = 0.9 * clamp(span(local, 1.4, 2.0));
  ctx.beginPath();
  ctx.arc(px, y, 22, 0, Math.PI * 2);
  ctx.fillStyle = UI.red;
  ctx.fill();
  ctx.globalAlpha = 0.25;
  ctx.beginPath();
  ctx.arc(px, y, 54, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// ------------------------------------------------------------ github screen
function githubChrome(ctx, url, title, x, y, w, h, alpha = 1, scaleIn = 1) {
  return browser(ctx, { x, y, w, h, url, title, alpha, scaleIn });
}

/** The repository page: header, tabs, file table, about panel. */
function repoPage(ctx, box, { t, reveal = 1, files = ['README.md', 'books.json', 'index.html', 'style.css'], tab = 'Code' }) {
  const { x, y, w, h } = box;
  ctx.save();
  // header
  text(ctx, 'octocat-ana', x + 60, y + 122, { size: 40, weight: 600, color: UI.dim });
  text(ctx, '/', x + 300, y + 122, { size: 40, weight: 600, color: UI.faint });
  // Measure before placing, not after: every `text()` call restores the context,
  // so a `ctx.measureText` afterwards measures in the default 10 px font and
  // every measured layout collapses onto itself.
  const nameWidth = measure(ctx, 'book-list', { size: 46, weight: 700 });
  text(ctx, 'book-list', x + 340, y + 122, { size: 46, weight: 700, color: UI.text });
  chip(ctx, 'Public', { x: x + 366 + nameWidth, y: y + 90, colour: UI.dim, fill: UI.window2, size: 28 });

  let tx = x + 60;
  ['Code', 'Issues', 'Pull requests', 'Actions', 'Settings'].forEach((name) => {
    const on = name === tab;
    const width = measure(ctx, name, { size: 38, weight: on ? 700 : 500 });
    text(ctx, name, tx, y + 236, { size: 38, weight: on ? 700 : 500, color: on ? UI.text : UI.dim });
    if (on) {
      ctx.fillStyle = UI.red;
      ctx.fillRect(tx - 6, y + 250, width + 12, 6);
    }
    tx += width + 76;
  });
  ctx.fillStyle = UI.line;
  ctx.fillRect(x + 60, y + 262, w - 120, 3);

  // branch bar
  panel(ctx, { x: x + 60, y: y + 300, w: 420, h: 72, r: 14, fill: UI.window2, stroke: UI.line });
  text(ctx, 'main', x + 96, y + 348, { size: 34, weight: 600, color: UI.text });
  text(ctx, 'Branches', x + 380, y + 348, { size: 32, weight: 500, color: UI.dim });

  // file table
  const top = y + 420;
  panel(ctx, { x: x + 60, y: top, w: w * 0.62, h: 88, r: 14, fill: UI.window2, stroke: UI.line });
  text(ctx, 'octocat-ana', x + 100, top + 54, { size: 32, weight: 600, color: UI.text });
  text(ctx, 'initial commit', x + w * 0.40, top + 54, { size: 30, weight: 500, color: UI.dim });
  text(ctx, 'now', x + w * 0.60, top + 54, { size: 30, weight: 500, color: UI.dim, align: 'right' });

  files.forEach((name, i) => {
    const p = clamp(reveal * files.length - i);
    if (p <= 0) return;
    const fy = top + 100 + i * 92;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.fillStyle = i % 2 ? UI.white : UI.window;
    ctx.fillRect(x + 60, fy, w * 0.62, 88);
    ctx.fillStyle = UI.line;
    ctx.fillRect(x + 60, fy + 86, w * 0.62, 2);
    // a file glyph, drawn
    ctx.strokeStyle = UI.dim;
    ctx.lineWidth = 3;
    roundRect(ctx, x + 104, fy + 22, 32, 42, 5);
    ctx.stroke();
    text(ctx, name, x + 164, fy + 54, { size: 34, weight: name === 'README.md' ? 700 : 500, color: UI.text });
    text(ctx, 'a moment ago', x + w * 0.60, fy + 54, { size: 28, weight: 400, color: UI.faint, align: 'right' });
    ctx.restore();
  });

  // about panel
  const ax = x + w * 0.68;
  text(ctx, 'About', ax, top + 20, { size: 38, weight: 700, color: UI.text, alpha: reveal });
  text(ctx, 'A one page site that lists', ax, top + 84, { size: 32, weight: 400, color: UI.dim, alpha: reveal });
  text(ctx, 'books, built in a conversation.', ax, top + 126, { size: 32, weight: 400, color: UI.dim, alpha: reveal });
  ['HTML', 'CSS', 'JavaScript'].forEach((tag, i) => {
    chip(ctx, tag, {
      x: ax + i * 190, y: top + 176, colour: UI.dim, fill: UI.window2, size: 26, alpha: reveal,
    });
  });
  ctx.restore();
}

function drawGithub(ctx, scene, t, local) {
  stageField(ctx, t);
  const idx = lineIndexAt(scene, t);
  const headline = span(local, 0.15, 1.1);
  text(ctx, scene.title, 240, 330, {
    size: 108, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(headline * 1.6),
  });
  rule(ctx, 244, 372, 700, { progress: ease.outCubic(headline), colour: UI.red, thickness: 8 });

  // the first two lines are about signing up: show the empty front page
  const onRepo = local > 5.2;
  const box = { x: 240, y: 470, w: W - 480, h: 1440 };

  if (!onRepo) {
    const content = githubChrome(ctx, 'github.com', 'GitHub', box.x, box.y, box.w, box.h, clamp(span(local, 0.2, 0.9)));
    const { x, y, w } = content;
    panel(ctx, { x: x + 60, y: y + 60, w: w - 120, h: 1040, r: 20, fill: UI.window2, stroke: UI.line });
    text(ctx, 'Create a new repository', x + 120, y + 190, { size: 62, weight: 700, color: UI.text, alpha: clamp(span(local, 1.0, 1.6)) });
    text(ctx, 'Repository name', x + 120, y + 300, { size: 34, weight: 600, color: UI.dim, alpha: clamp(span(local, 1.6, 2.2)) });
    panel(ctx, { x: x + 120, y: y + 326, w: 900, h: 92, r: 12, fill: UI.white, stroke: UI.line });
    const typed = 'book-list'.slice(0, Math.max(0, Math.floor((local - 3.2) * 9)));
    text(ctx, typed, x + 156, y + 388, { size: 42, weight: 500, color: UI.text });
    if (local > 3.2 && typed.length < 9 && Math.floor(local * 3) % 2 === 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(x + 162 + ctx.measureText(typed).width, y + 350, 4, 46);
    }
    ['Public', 'Private'].forEach((opt, i) => {
      const on = i === 0;
      ctx.beginPath();
      ctx.arc(x + 140, y + 500 + i * 96, 18, 0, Math.PI * 2);
      ctx.lineWidth = 5;
      ctx.strokeStyle = on ? UI.ink : UI.faint;
      ctx.stroke();
      if (on) {
        ctx.beginPath();
        ctx.arc(x + 140, y + 500 + i * 96, 9, 0, Math.PI * 2);
        ctx.fillStyle = UI.ink;
        ctx.fill();
      }
      text(ctx, opt, x + 180, y + 512 + i * 96, { size: 38, weight: 600, color: UI.text, alpha: clamp(span(local, 2.2, 2.8)) });
    });
    // README checkbox
    const tick = clamp(span(local, 4.0, 4.4));
    roundRect(ctx, x + 120, y + 720, 34, 34, 6);
    ctx.strokeStyle = UI.dim;
    ctx.lineWidth = 4;
    ctx.stroke();
    if (tick > 0) {
      ctx.strokeStyle = UI.ink;
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(x + 128, y + 738);
      ctx.lineTo(x + 136, y + 748);
      ctx.lineTo(x + 152, y + 726);
      ctx.stroke();
    }
    text(ctx, 'Add a README file', x + 176, y + 750, { size: 36, weight: 500, color: UI.text, alpha: clamp(span(local, 3.8, 4.4)) });

    // create button
    const bp = clamp(span(local, 4.3, 4.9));
    panel(ctx, { x: x + 120, y: y + 830, w: 430, h: 96, r: 14, fill: bp > 0.5 ? UI.ink : '#8A8A94', stroke: null, alpha: bp });
    text(ctx, 'Create repository', x + 335, y + 890, { size: 36, weight: 700, color: UI.white, align: 'center', alpha: bp });

    // the pointer walks to Create and clicks
    const move = ease.inOutCubic(span(local, 4.5, 5.2));
    const cx = lerp(x + 1400, x + 400, move);
    const cy = lerp(y + 300, y + 878, move);
    cursor(ctx, cx, cy, { press: span(local, 5.15, 5.3), alpha: clamp(span(local, 3.6, 4.0)) });
    clickRing(ctx, x + 400, y + 878, span(local, 5.15, 5.6));
    return;
  }

  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list', 'book-list', box.x, box.y, box.w, box.h, clamp(span(local, 5.2, 5.7)));
  repoPage(ctx, content, {
    t, reveal: clamp(span(local, 5.5, 6.6)),
    files: ['README.md', 'books.json', 'index.html', 'style.css'],
  });

  // callouts for the four parts named in the narration
  const notes = [
    ['THE FILES', 6.4], ['THE COMMITS', 8.2], ['THE BRANCHES', 9.4], ['THE CHECKS', 10.6],
  ];
  notes.forEach(([label, at], i) => {
    const p = span(local, at, at + 0.5);
    if (p <= 0) return;
    // They land in the empty half of an empty repository, not on the tab row
    // where they were printing over "Code".
    const nx = content.x + 80 + i * 470;
    const ny = content.y + 1010;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.4);
    ctx.translate(0, (1 - ease.outCubic(p)) * 24);
    chip(ctx, label, { x: nx, y: ny, colour: UI.gold, fill: UI.ink, size: 26 });
    ctx.restore();
  });
  void idx;
}

// ------------------------------------------------------------------ connect
function drawConnect(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, W / 2, 330, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, align: 'center',
    alpha: clamp(span(local, 0.15, 1.0) * 1.6),
  });

  const left = { x: 300, y: 500, w: 1500, h: 1200 };
  const right = { x: 2040, y: 500, w: 1500, h: 1200 };

  // Arena panel
  const lp = clamp(span(local, 0.3, 1.1));
  panel(ctx, { ...left, r: 28, fill: '#141418', stroke: '#2A2A31', alpha: lp, shadow: 0.6 });
  ctx.save();
  ctx.globalAlpha = lp;
  text(ctx, 'ARENA', left.x + 60, left.y + 86, { size: 38, weight: 700, color: UI.gold, tracking: 8 });
  text(ctx, 'Connect GitHub', left.x + 60, left.y + 210, { size: 62, weight: 700, color: UI.white, family: 'Space Grotesk' });
  text(ctx, 'One authorisation, then the agent', left.x + 60, left.y + 282, { size: 34, weight: 400, color: '#9A9AA5' });
  text(ctx, 'works inside your repositories.', left.x + 60, left.y + 326, { size: 34, weight: 400, color: '#9A9AA5' });

  // authorise button
  const bp = clamp(span(local, 1.0, 1.6));
  panel(ctx, { x: left.x + 60, y: left.y + 400, w: 520, h: 100, r: 14, fill: bp > 0 ? UI.gold : '#3A3A42', stroke: null, alpha: bp });
  text(ctx, 'Authorise GitHub', left.x + 320, left.y + 464, {
    size: 36, weight: 700, color: UI.ink, align: 'center', alpha: bp,
  });
  cursor(ctx, lerp(left.x + 700, left.x + 380, ease.inOutCubic(span(local, 1.2, 1.9))), left.y + 450, {
    press: span(local, 1.9, 2.1), alpha: clamp(span(local, 0.8, 1.2)),
  });
  clickRing(ctx, left.x + 380, left.y + 450, span(local, 1.9, 2.4));

  // permission dialog
  const dp = clamp(span(local, 2.2, 2.8));
  if (dp > 0) {
    panel(ctx, { x: left.x + 60, y: left.y + 560, w: left.w - 120, h: 520, r: 20, fill: '#1E1E24', stroke: '#3A3A44', alpha: dp });
    text(ctx, 'Choose repositories', left.x + 120, left.y + 650, { size: 46, weight: 700, color: UI.white, alpha: dp });
    ['book-list', 'portfolio', 'scratch'].forEach((name, i) => {
      const on = i === 0;
      const rp = clamp(span(local, 2.6 + i * 0.2, 3.0 + i * 0.2)) * dp;
      roundRect(ctx, left.x + 120, left.y + 700 + i * 96, 40, 40, 8);
      ctx.strokeStyle = '#5A5A66';
      ctx.lineWidth = 4;
      ctx.stroke();
      if (on && rp > 0.4) {
        ctx.fillStyle = UI.gold;
        ctx.fill();
        ctx.strokeStyle = UI.ink;
        ctx.lineWidth = 7;
        ctx.beginPath();
        ctx.moveTo(left.x + 129, left.y + 722);
        ctx.lineTo(left.x + 137, left.y + 732);
        ctx.lineTo(left.x + 153, left.y + 710);
        ctx.stroke();
      }
      text(ctx, name, left.x + 190, left.y + 734 + i * 96, {
        size: 38, weight: 500, color: i === 0 ? UI.white : '#8A8A96', alpha: rp,
      });
    });
  }
  ctx.restore();

  // connector
  const cp = clamp(span(local, 3.0, 4.2));
  if (cp > 0) {
    ctx.save();
    ctx.strokeStyle = 'rgba(11,11,12,0.35)';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(left.x + left.w + 20, 1100);
    ctx.lineTo(right.x - 20, 1100);
    ctx.stroke();
    for (let i = 0; i < 5; i += 1) {
      const p = (local * 0.5 + i / 5) % 1;
      if (p > cp) continue;
      const px = lerp(left.x + left.w + 20, right.x - 20, p);
      ctx.beginPath();
      ctx.arc(px, 1100, 10, 0, Math.PI * 2);
      ctx.fillStyle = UI.red;
      ctx.globalAlpha = 0.9;
      ctx.fill();
    }
    ctx.restore();
  }

  // GitHub panel
  const rp2 = clamp(span(local, 3.2, 4.0));
  panel(ctx, { ...right, r: 28, fill: UI.window, stroke: UI.line, alpha: rp2, shadow: 0.5 });
  ctx.save();
  ctx.globalAlpha = rp2;
  text(ctx, 'GITHUB', right.x + 60, right.y + 86, { size: 38, weight: 700, color: UI.dim, tracking: 8 });
  text(ctx, 'octocat-ana / book-list', right.x + 60, right.y + 210, {
    size: 56, weight: 700, color: UI.text, family: 'Space Grotesk',
  });
  chip(ctx, 'CONNECTED', { x: right.x + 60, y: right.y + 260, colour: UI.ink, fill: '#DFF3E6', size: 28 });
  ['read the files', 'write a branch', 'open a pull request'].forEach((value, i) => {
    const p = clamp(span(local, 4.2 + i * 0.5, 4.8 + i * 0.5));
    if (p <= 0) return;
    ctx.save();
    ctx.globalAlpha = p * rp2;
    ctx.beginPath();
    ctx.arc(right.x + 84, right.y + 430 + i * 110, 20, 0, Math.PI * 2);
    ctx.fillStyle = UI.ink;
    ctx.fill();
    text(ctx, value, right.x + 130, right.y + 444 + i * 110, { size: 40, weight: 500, color: UI.text });
    ctx.restore();
  });
  ctx.restore();
}

// ------------------------------------------------------------------- prompt
const PROMPT_TEXT = [
  'Build a one page site that lists my favourite books.',
  'It should read books.json and draw one card per book.',
  'Plain HTML, CSS and JavaScript. No framework.',
  'Add a README that explains how to run it.',
  'Do not add a database yet.',
];

function promptTypedCount(local) {
  const total = PROMPT_TEXT.join('').length;
  const p = span(local, 1.2, 6.4);
  return Math.floor(total * (p < 1 ? ease.outCubic(p) : 1));
}

function drawPrompt(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 96, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  // the chat panel
  const box = { x: 240, y: 430, w: 2300, h: 1520 };
  const p = clamp(span(local, 0.25, 1.0));
  panel(ctx, { ...box, r: 26, fill: UI.window, stroke: UI.line, alpha: p, shadow: 0.6 });
  ctx.save();
  ctx.globalAlpha = p;
  text(ctx, 'ARENA  /  book-list', box.x + 60, box.y + 84, { size: 34, weight: 700, color: UI.dim, tracking: 5 });
  ctx.fillStyle = UI.line;
  ctx.fillRect(box.x + 60, box.y + 116, box.w - 120, 3);

  // the composer, holding the prompt
  const compY = box.y + 190;
  panel(ctx, { x: box.x + 60, y: compY, w: box.w - 120, h: 780, r: 20, fill: '#F7F7F9', stroke: UI.line2 });
  const count = promptTypedCount(local);
  let used = 0;
  PROMPT_TEXT.forEach((line, i) => {
    if (used > count) return;
    const slice = line.slice(0, Math.max(0, count - used));
    if (!slice) return;
    text(ctx, slice, box.x + 120, compY + 100 + i * 84, { size: 44, weight: 500, color: UI.text });
    if (i === 0 && local < 6.4) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(box.x + 120 + measure(ctx, slice, { size: 44, weight: 500 }), compY + 62, 4, 48);
    }
    used += line.length;
  });

  // annotations for the parts of the prompt
  const notes = [
    ['WHAT IT IS', 2.2], ['WHAT IT READS', 3.6], ['THE CONSTRAINT', 4.8], ['THE README', 6.0], ['THE SCOPE CUT', 7.0],
  ];
  notes.forEach(([label, at], i) => {
    const np = span(local, at, at + 0.5);
    if (np <= 0) return;
    // Same baseline as the line it points at: an annotation 20 px below its
    // subject reads as annotating the next line.
    const ny = compY + 100 + i * 84;
    ctx.save();
    ctx.globalAlpha = clamp(np * 1.5);
    ctx.strokeStyle = UI.red;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(box.x + 1560, ny - 12);
    ctx.lineTo(box.x + 1660, ny - 12);
    ctx.stroke();
    text(ctx, label, box.x + 1680, ny, {
      size: 32, weight: 700, color: UI.red, tracking: 3,
      alpha: clamp(np * 1.5),
    });
    ctx.restore();
  });

  // send button + pointer
  const sendP = clamp(span(local, 8.4, 9.0));
  panel(ctx, { x: box.x + box.w - 320, y: compY + 660, w: 200, h: 92, r: 16, fill: sendP > 0.4 ? UI.ink : '#9A9AA5', stroke: null });
  text(ctx, 'Send', box.x + box.w - 220, compY + 718, { size: 38, weight: 700, color: UI.white, align: 'center' });
  const mx = lerp(box.x + 1900, box.x + box.w - 230, ease.inOutCubic(span(local, 8.0, 8.6)));
  const my = lerp(compY + 900, compY + 706, ease.inOutCubic(span(local, 8.0, 8.6)));
  cursor(ctx, mx, my, { press: span(local, 8.6, 8.8), alpha: clamp(span(local, 7.6, 8.2)) });
  clickRing(ctx, box.x + box.w - 230, compY + 706, span(local, 8.6, 9.1));

  // the weak prompt, struck out, as a comparison card
  const wp = clamp(span(local, 1.6, 2.2));
  if (wp > 0 && local < 5) {
    panel(ctx, { x: W - 1180, y: 470, w: 940, h: 300, r: 20, fill: '#EFEFF3', stroke: UI.line2, alpha: wp });
    text(ctx, 'WEAK', W - 1130, 540, { size: 30, weight: 700, color: UI.dim, tracking: 5, alpha: wp });
    text(ctx, '“make me an app”', W - 1130, 640, { size: 52, weight: 600, family: 'Space Grotesk', color: '#6B6B75', alpha: wp });
    ctx.save();
    ctx.globalAlpha = wp;
    ctx.strokeStyle = UI.red;
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(W - 1130, 622);
    ctx.lineTo(W - 1130 + 620 * clamp(span(local, 2.3, 2.8)), 622);
    ctx.stroke();
    ctx.restore();
  }
  ctx.restore();
}

// -------------------------------------------------------------------- agent
const AGENT_STEPS = [
  ['Read README.md', 'pass'],
  ['Created branch feature/book-list', 'pass'],
  ['Wrote index.html', 'pass'],
  ['Wrote style.css', 'pass'],
  ['Added books.json', 'pass'],
  ['Opened pull request #1', 'pass'],
];

function drawAgent(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 100, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 430, w: W - 480, h: 1480 };
  panel(ctx, { ...box, r: 26, fill: '#141418', stroke: '#2A2A31', shadow: 0.7 });
  text(ctx, 'ARENA  /  book-list  /  feature/book-list', box.x + 60, box.y + 84, {
    size: 34, weight: 700, color: UI.gold, tracking: 4,
  });

  // the user's prompt, echoed as a bubble
  const up = clamp(span(local, 0.5, 1.2));
  panel(ctx, { x: box.x + 620, y: box.y + 150, w: 1800, h: 230, r: 22, fill: '#22222A', stroke: null, alpha: up });
  text(ctx, 'Build a one page site that lists my books.', box.x + 680, box.y + 236, {
    size: 38, weight: 500, color: UI.white, alpha: up,
  });
  text(ctx, 'Read books.json. No framework. No database yet.', box.x + 680, box.y + 300, {
    size: 34, weight: 500, color: '#B9B9C4', alpha: up,
  });

  // agent steps, one per beat
  AGENT_STEPS.forEach(([label, state], i) => {
    const p = clamp(span(local, 1.4 + i * 0.85, 1.9 + i * 0.85));
    if (p <= 0) return;
    const y = box.y + 470 + i * 100;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.beginPath();
    ctx.arc(box.x + 120, y - 12, 18, 0, Math.PI * 2);
    ctx.fillStyle = UI.green;
    ctx.fill();
    ctx.strokeStyle = UI.ink;
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(box.x + 111, y - 13);
    ctx.lineTo(box.x + 118, y - 5);
    ctx.lineTo(box.x + 130, y - 21);
    ctx.stroke();
    text(ctx, label, box.x + 168, y, { size: 40, weight: 500, color: '#E8E8EC' });
    text(ctx, 'done', box.x + 980, y, { size: 30, weight: 500, color: '#6F6F7A' });
    ctx.restore();
  });

  // the pull request card
  const pp = clamp(span(local, 5.2, 6.0));
  panel(ctx, { x: box.x + 1200, y: box.y + 470, w: 1180, h: 600, r: 22, fill: '#1E1E24', stroke: '#3A3A44', alpha: pp });
  ctx.save();
  ctx.globalAlpha = pp;
  text(ctx, 'PULL REQUEST', box.x + 1260, box.y + 546, { size: 28, weight: 700, color: UI.gold, tracking: 5 });
  text(ctx, '#1  Add book list page', box.x + 1260, box.y + 630, {
    size: 44, weight: 700, color: UI.white, family: 'Space Grotesk',
  });
  text(ctx, 'feature/book-list  →  main', box.x + 1260, box.y + 700, { size: 32, weight: 500, color: '#9A9AA5' });
  panel(ctx, { x: box.x + 1260, y: box.y + 740, w: 380, h: 76, r: 12, fill: '#2A2A32', stroke: null });
  text(ctx, '+128  −0', box.x + 1450, box.y + 790, { size: 32, weight: 600, color: '#8FE0A8', align: 'center' });
  text(ctx, 'Nothing is live yet.', box.x + 1260, box.y + 910, {
    size: 36, weight: 600, color: UI.gold,
  });
  text(ctx, 'The site only changes when you merge.', box.x + 1260, box.y + 962, {
    size: 32, weight: 400, color: '#B9B9C4',
  });
  ctx.restore();

  // branch chip on the left, so the word is learned before it is used
  const bp = clamp(span(local, 1.0, 1.6));
  if (bp > 0) {
    ctx.save();
    ctx.globalAlpha = bp;
    text(ctx, 'BRANCH', box.x + 60, box.y + 1180, { size: 28, weight: 700, color: '#6F6F7A', tracking: 5 });
    panel(ctx, { x: box.x + 60, y: box.y + 1200, w: 760, h: 84, r: 14, fill: '#22222A', stroke: '#3A3A44' });
    text(ctx, 'feature/book-list', box.x + 100, box.y + 1256, { size: 36, weight: 600, color: UI.white });
    ctx.restore();
  }
}

// --------------------------------------------------------------------- diff
const DIFF = [
  ['@@ index.html @@', 'ctx'],
  ['+ <main id="books"></main>', 'add'],
  ['- <div class="placeholder"></div>', 'del'],
  ['+ <script src="app.js"></script>', 'add'],
  ['@@ app.js (new file) @@', 'ctx'],
  ['+ const res = await fetch("books.json");', 'add'],
  ['+ const books = await res.json();', 'add'],
  ['+ books.forEach(book => render(book));', 'add'],
  ['@@ style.css @@', 'ctx'],
  ['+ .card { border-radius: 12px; padding: 24px; }', 'add'],
];

function drawDiff(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 100, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 420, w: W - 480, h: 1560 };
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list/pull/1/files', 'Files changed', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  text(ctx, 'Files changed', x + 60, y + 90, { size: 52, weight: 700, color: UI.text });
  chip(ctx, '3 files', { x: x + 440, y: y + 52, colour: UI.dim, fill: UI.window2, size: 26 });
  text(ctx, '+128', x + w - 260, y + 90, { size: 38, weight: 700, color: UI.green, align: 'right' });
  text(ctx, '−24', x + w - 120, y + 90, { size: 38, weight: 700, color: UI.red, align: 'right' });
  ctx.fillStyle = UI.line;
  ctx.fillRect(x + 60, y + 118, w - 120, 3);

  // file list
  ['index.html', 'app.js', 'style.css'].forEach((name, i) => {
    const p = clamp(span(local, 0.6 + i * 0.3, 1.1 + i * 0.3));
    if (p <= 0) return;
    ctx.save();
    ctx.globalAlpha = p;
    const fy = y + 150 + i * 62;
    panel(ctx, { x: x + 60, y: fy, w: 720, h: 50, r: 8, fill: UI.window2, stroke: null });
    text(ctx, name, x + 90, fy + 35, { size: 32, weight: 600, color: UI.text });
    text(ctx, i === 1 ? '+96' : '+16', x + 700, fy + 35, { size: 28, weight: 600, color: UI.green, align: 'right' });
    ctx.restore();
  });

  // the diff itself, revealing line by line with the narration
  const start = y + 380;
  const reveal = span(local, 1.2, 8.0) * DIFF.length;
  DIFF.forEach(([value, kind], i) => {
    if (i > reveal) return;
    const ly = start + i * 96;
    const alpha = clamp(reveal - i);
    ctx.save();
    ctx.globalAlpha = alpha;
    const bg = kind === 'add' ? 'rgba(46,158,91,0.12)' : kind === 'del' ? 'rgba(196,22,28,0.10)' : 'rgba(11,11,12,0.04)';
    ctx.fillStyle = bg;
    ctx.fillRect(x + 60, ly - 56, w - 120, 86);
    ctx.fillStyle = kind === 'add' ? UI.green : kind === 'del' ? UI.red : UI.faint;
    ctx.fillRect(x + 60, ly - 56, 6, 86);
    text(ctx, value, x + 110, ly, {
      size: 36, weight: 500, color: kind === 'ctx' ? UI.dim : UI.text, family: 'Inter',
    });
    ctx.restore();
  });

  // The three usual problems, each pinned to the line it describes. Stacking
  // them at one point printed three labels on top of each other.
  const notes = [
    ['A DEPENDENCY YOU DID NOT ASK FOR', 4.4, 4],
    ['A VALUE THAT SHOULD BE A SETTING', 5.6, 9],
    ['A TEST THAT TESTS NOTHING', 6.9, 6],
  ];
  notes.forEach(([label, at, lineAt], i) => {
    const p = span(local, at, at + 0.5);
    if (p <= 0) return;
    const ly = start + lineAt * 96;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.4);
    // a leader from the line to the label, so "which line?" is never a question
    const lx = x + w - 900;
    ctx.strokeStyle = UI.red;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(lx - 90, ly - 12);
    ctx.lineTo(lx - 30, ly - 12);
    ctx.stroke();
    chip(ctx, label, {
      x: lx, y: ly - 62, colour: UI.white, fill: UI.red, size: 26,
      alpha: clamp(p * 1.4),
    });
    ctx.restore();
    void i;
  });
}

// ------------------------------------------------------------------- checks
const CHECK_ROWS = [
  ['build', 'pass', '18s'],
  ['unit tests', 'pass', '42s'],
  ['link check', 'fail', '3s'],
  ['deploy preview', 'pending', ''],
];

function drawChecks(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 430, w: 2300, h: 1400 };
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list/pull/1/checks', 'Checks', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  text(ctx, 'All checks', x + 60, y + 110, { size: 54, weight: 700, color: UI.text });
  const titleWidth = measure(ctx, 'All checks', { size: 54, weight: 700 });
  const passed = local > 4.6;
  chip(ctx, passed ? '3 PASSED' : '1 FAILING', {
    x: x + 100 + titleWidth, y: y + 54, colour: passed ? '#1B7A44' : UI.white,
    fill: passed ? 'rgba(46,158,91,0.16)' : UI.red, size: 30,
  });

  CHECK_ROWS.forEach(([name, state, detail], i) => {
    const p = clamp(span(local, 0.7 + i * 0.5, 1.2 + i * 0.5));
    if (p <= 0) return;
    let s = state;
    if (name === 'link check' && local > 4.6) s = 'pass';
    if (name === 'deploy preview' && local > 6.0) s = 'pass';
    checkRow(ctx, {
      x: x + 60, y: y + 250 + i * 150, w: w - 120, name,
      state: s, progress: p, detail: s === 'pass' ? 'passed' : s === 'fail' ? 'failed' : 'running',
    });
    void detail;
  });

  // the failing log, opened
  const lp = clamp(span(local, 3.0, 3.6));
  if (lp > 0 && local < 5.2) {
    panel(ctx, { x: x + 60, y: y + 880, w: w - 120, h: 440, r: 16, fill: '#141418', stroke: '#2A2A31', alpha: lp });
    ctx.save();
    ctx.globalAlpha = lp;
    text(ctx, 'link check  /  log', x + 120, y + 946, { size: 30, weight: 700, color: UI.gold, tracking: 4 });
    codeBlock(ctx, [
      'Error: cannot resolve books.json',
      '  at build/links.js:42:11',
      '  hint: the file is in /data, not the root',
    ], { x: x + 120, y: y + 1020, size: 34, lineHeight: 66, progress: clamp(span(local, 3.2, 4.2)), colour: '#E8E8EC', dim: '#6F6F7A', gutter: false });
    ctx.restore();
  }

  // green sweep when it passes
  const gp = span(local, 6.0, 7.0);
  if (gp > 0) {
    ctx.save();
    ctx.globalAlpha = 0.10 * (1 - gp);
    ctx.fillStyle = UI.green;
    ctx.fillRect(x, y + 150, w, 600);
    ctx.restore();
  }
}

// -------------------------------------------------------------------- merge
function drawMerge(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const merged = local > 3.2;
  const box = { x: 240, y: 430, w: W - 480, h: 1520 };
  const content = githubChrome(ctx, merged ? 'github.com/octocat-ana/book-list' : 'github.com/octocat-ana/book-list/pull/1', 'book-list', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  if (!merged) {
    text(ctx, 'Add book list page', x + 60, y + 100, { size: 54, weight: 700, color: UI.text });
    chip(ctx, 'Open', { x: x + 700, y: y + 56, colour: UI.white, fill: UI.green, size: 26 });
    text(ctx, '3 commits · 3 files changed', x + 60, y + 160, { size: 32, weight: 400, color: UI.dim });

    // the green merge button
    const bp = clamp(span(local, 1.2, 1.9));
    const press = span(local, 2.3, 2.6);
    panel(ctx, {
      x: x + 60, y: y + 240, w: 520, h: 96, r: 14,
      fill: press > 0.4 ? '#248A4E' : UI.green, stroke: null, alpha: bp,
    });
    text(ctx, 'Merge pull request', x + 320, y + 300, { size: 38, weight: 700, color: UI.white, align: 'center', alpha: bp });
    cursor(ctx, lerp(x + 900, x + 300, ease.inOutCubic(span(local, 1.6, 2.3))), lerp(y + 500, y + 288, ease.inOutCubic(span(local, 1.6, 2.3))), {
      press, alpha: clamp(span(local, 1.2, 1.7)),
    });
    clickRing(ctx, x + 300, y + 288, span(local, 2.3, 2.8));

    // confirm dialog
    const dp = clamp(span(local, 2.6, 3.1));
    if (dp > 0) {
      panel(ctx, { x: x + w / 2 - 420, y: y + 520, w: 840, h: 360, r: 20, fill: UI.white, stroke: UI.line2, alpha: dp, shadow: 1 });
      text(ctx, 'Confirm merge', x + w / 2, y + 610, { size: 44, weight: 700, color: UI.text, align: 'center', alpha: dp });
      text(ctx, 'feature/book-list → main', x + w / 2, y + 672, { size: 32, weight: 500, color: UI.dim, align: 'center', alpha: dp });
      panel(ctx, { x: x + w / 2 - 180, y: y + 730, w: 360, h: 92, r: 14, fill: UI.green, stroke: null, alpha: dp });
      text(ctx, 'Confirm merge', x + w / 2, y + 788, { size: 34, weight: 700, color: UI.white, align: 'center', alpha: dp });
    }
    return;
  }

  // merged state, then the site itself
  const siteP = span(local, 4.6, 5.6);
  ctx.save();
  // The deployed site takes the frame. Leaving the repository at full strength
  // under it printed two interfaces on top of each other.
  ctx.globalAlpha = 1 - siteP * 0.92;
  repoPage(ctx, content, { t, reveal: 1, files: ['README.md', 'books.json', 'index.html', 'app.js', 'style.css'], tab: 'Code' });
  ctx.restore();
  chip(ctx, 'MERGED', { x: x + 60, y: y + 20, colour: UI.white, fill: UI.red, size: 26, alpha: clamp(span(local, 3.2, 3.6)) * (1 - siteP) });

  if (siteP > 0) {
    // a second window: the deployed site, with the URL typed into the bar
    // Below the repository's own header and tabs: starting any higher printed the
    // site's address bar across the repository title.
    const sw = Math.min(w * 0.78, 2400);
    const sh = 820;
    const sx = x + (w - sw) / 2;
    const inner = browser(ctx, {
      x: sx, y: y + 330, w: sw, h: sh, url: '', title: 'Book list', alpha: siteP,
      scaleIn: lerp(0.94, 1, ease.outCubic(siteP)),
    });
    const url = 'octocat-ana.github.io/book-list';
    const typed = url.slice(0, Math.floor(clamp(span(local, 4.9, 6.2)) * url.length));
    text(ctx, typed, sx + 250, y + 330 + 92 + 4, { size: 30, weight: 500, color: UI.text });
    if (local > 6.2) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(sx + 256 + measure(ctx, typed, { size: 30, weight: 500 }), y + 330 + 60, 3, 38);
    }
    // the page: a heading and three cards
    text(ctx, 'My books', inner.x + 60, inner.y + 110, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.text, alpha: clamp(span(local, 6.2, 6.8)) });
    for (let i = 0; i < 3; i += 1) {
      const cp = clamp(span(local, 6.4 + i * 0.22, 7.0 + i * 0.22));
      if (cp <= 0) continue;
      const cardW = (inner.w - 160) / 3 - 30;
      const cxp = inner.x + 60 + i * (cardW + 30);
      panel(ctx, { x: cxp, y: inner.y + 180, w: cardW, h: 470, r: 18, fill: UI.window2, stroke: UI.line, alpha: cp });
      ctx.save();
      ctx.globalAlpha = cp;
      ctx.fillStyle = UI.ink;
      ctx.fillRect(cxp + 30, inner.y + 220, cardW - 60, 240);
      text(ctx, ['Dune', 'Beloved', 'Piranesi'][i], cxp + 30, inner.y + 530, { size: 40, weight: 700, color: UI.text });
      text(ctx, ['Frank Herbert', 'Toni Morrison', 'Susanna Clarke'][i], cxp + 30, inner.y + 588, { size: 30, weight: 400, color: UI.dim });
      ctx.restore();
    }
  }
}

// ------------------------------------------------------------------ feature
function drawFeature(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  // the second feature, as a small, quick pass: prompt, diff, merge
  const box = { x: 240, y: 440, w: W - 480, h: 1420 };
  const stage = local < 4.4 ? 'prompt' : local < 8.0 ? 'diff' : 'merged';
  const content = githubChrome(ctx, stage === 'prompt' ? 'arena.ai/chat' : 'github.com/octocat-ana/book-list/pull/2', 'Pull request #2', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  if (stage === 'prompt') {
    panel(ctx, { x: x + 60, y: y + 60, w: w - 120, h: 560, r: 18, fill: '#141418', stroke: '#2A2A31' });
    text(ctx, 'ARENA', x + 120, y + 130, { size: 30, weight: 700, color: UI.gold, tracking: 5 });
    const lines = [
      'Add a search box above the list.',
      'It filters the cards as I type, ignores capitals,',
      'and shows a message when nothing matches.',
      'Do not change the card design. Do not add a library.',
    ];
    const p = span(local, 0.8, 3.2) * lines.length;
    lines.forEach((line, i) => {
      if (i > p) return;
      text(ctx, line, x + 120, y + 210 + i * 78, {
        size: 38, weight: 500, color: i === 3 ? UI.gold : UI.white, alpha: clamp(p - i),
      });
    });
    chip(ctx, 'ONE FILE  ·  ABOUT 40 LINES', { x: x + 120, y: y + 540, colour: UI.ink, fill: UI.gold, size: 26, alpha: clamp(span(local, 3.4, 3.9)) });
    return;
  }

  if (stage === 'diff') {
    text(ctx, 'Files changed', x + 60, y + 80, { size: 44, weight: 700, color: UI.text });
    chip(ctx, '1 file', { x: x + 400, y: y + 44, colour: UI.dim, fill: UI.window2, size: 26 });
    text(ctx, '+41', x + w - 240, y + 80, { size: 34, weight: 700, color: UI.green, align: 'right' });
    text(ctx, '−3', x + w - 120, y + 80, { size: 34, weight: 700, color: UI.red, align: 'right' });
    codeBlock(ctx, [
      '+ const search = document.createElement("input");',
      '+ search.placeholder = "Search books";',
      '+ search.addEventListener("input", filterCards);',
      '+ function filterCards() { ... }',
      '  function render(book) { ... }',
    ], { x: x + 120, y: y + 200, size: 38, lineHeight: 82, progress: clamp(span(local, 4.6, 7.0)), gutter: false });
    return;
  }

  // merged badge and the live page
  const p = clamp(span(local, 8.0, 8.8));
  panel(ctx, { x: x + w / 2 - 460, y: y + 260, w: 920, h: 520, r: 24, fill: UI.white, stroke: UI.line2, alpha: p, shadow: 1 });
  ctx.save();
  ctx.globalAlpha = p;
  ctx.beginPath();
  ctx.arc(x + w / 2, y + 400, 46, 0, Math.PI * 2);
  ctx.fillStyle = UI.green;
  ctx.fill();
  ctx.strokeStyle = UI.white;
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.moveTo(x + w / 2 - 20, y + 402);
  ctx.lineTo(x + w / 2 - 4, y + 418);
  ctx.lineTo(x + w / 2 + 24, y + 382);
  ctx.stroke();
  text(ctx, 'Merged and live', x + w / 2, y + 520, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.text, align: 'center' });
  text(ctx, 'Search box shipped in 4 minutes.', x + w / 2, y + 590, { size: 36, weight: 400, color: UI.dim, align: 'center' });
  text(ctx, 'Small, reviewed, reversible.', x + w / 2, y + 660, { size: 36, weight: 600, color: UI.ink, align: 'center' });
  ctx.restore();
}

// ------------------------------------------------------------------- revert
function drawRevert(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 430, w: W - 480, h: 1460 };
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list/pull/2', 'Pull request #2', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  text(ctx, 'Broken layout on small screens', x + 60, y + 100, { size: 50, weight: 700, color: UI.text });
  chip(ctx, 'MERGED', { x: x + 780, y: y + 52, colour: UI.white, fill: UI.red, size: 26 });

  // the revert button
  const bp = clamp(span(local, 1.2, 1.8));
  panel(ctx, { x: x + w - 520, y: y + 60, w: 400, h: 88, r: 14, fill: UI.window2, stroke: UI.line2, alpha: bp });
  text(ctx, 'Revert', x + w - 320, y + 116, { size: 36, weight: 700, color: UI.text, align: 'center', alpha: bp });
  cursor(ctx, lerp(x + w - 900, x + w - 320, ease.inOutCubic(span(local, 1.6, 2.4))), lerp(y + 260, y + 104, ease.inOutCubic(span(local, 1.6, 2.4))), {
    press: span(local, 2.4, 2.6), alpha: clamp(span(local, 1.2, 1.7)),
  });
  clickRing(ctx, x + w - 320, y + 104, span(local, 2.4, 2.9));

  // the commit history, with the revert arriving on top
  const hist = [
    ['Revert "Add search box"', 'now', true],
    ['Add search box', '2 minutes ago', false],
    ['Add book list page', 'yesterday', false],
    ['Initial commit', 'yesterday', false],
  ];
  hist.forEach(([label, when, fresh], i) => {
    const p = clamp(span(local, 2.8 + i * 0.4, 3.4 + i * 0.4));
    if (p <= 0) return;
    const cy = y + 300 + i * 150;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.strokeStyle = UI.line2;
    ctx.lineWidth = 4;
    if (i < hist.length - 1) {
      ctx.beginPath();
      ctx.moveTo(x + 96, cy + 30);
      ctx.lineTo(x + 96, cy + 150);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(x + 96, cy, 20, 0, Math.PI * 2);
    ctx.fillStyle = fresh ? UI.red : UI.line2;
    ctx.fill();
    text(ctx, label, x + 150, cy + 14, { size: 40, weight: fresh ? 700 : 500, color: UI.text });
    text(ctx, when, x + w - 120, cy + 14, { size: 30, weight: 400, color: UI.faint, align: 'right' });
    ctx.restore();
  });

  // the point of the lesson, in one line
  const lp = clamp(span(local, 5.4, 6.2));
  if (lp > 0) {
    panel(ctx, { x: x + 60, y: y + 950, w: w - 120, h: 220, r: 18, fill: UI.ink, stroke: null, alpha: lp });
    text(ctx, 'Nothing is lost. Every step can be undone.', x + 120, y + 1030, {
      size: 44, weight: 700, color: UI.white, family: 'Space Grotesk', alpha: lp,
    });
    text(ctx, 'That is why every change goes through Git.', x + 120, y + 1100, {
      size: 34, weight: 400, color: '#B9B9C4', alpha: lp,
    });
  }
}

// ----------------------------------------------------------------- patterns
const PATTERNS = [
  ['NAME THE OUTCOME', '“A search box above the list.”'],
  ['GIVE ONE EXAMPLE', '“Like the cards, but smaller.”'],
  ['STATE THE CONSTRAINT', '“No library. Under 50 lines.”'],
  ['PROTECT WHAT WORKS', '“Do not touch the header.”'],
  ['ASK FOR A PLAN', '“Plan first, then build.”'],
];

function drawPatterns(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 100, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  PATTERNS.forEach(([label, example], i) => {
    const p = clamp(span(local, 0.5 + i * 0.95, 1.1 + i * 0.95));
    if (p <= 0) return;
    const row = i;
    const yy = 520 + row * 290;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.translate((1 - ease.outExpo(p)) * -120, 0);
    panel(ctx, { x: 260, y: yy, w: W - 520, h: 240, r: 20, fill: i % 2 ? UI.window2 : UI.window, stroke: UI.line, shadow: 0.3 });
    ctx.fillStyle = i % 2 ? UI.red : UI.ink;
    ctx.fillRect(260, yy, 12, 240);
    text(ctx, String(i + 1).padStart(2, '0'), 320, yy + 78, { size: 34, weight: 700, color: UI.dim, tracking: 3 });
    text(ctx, label, 420, yy + 100, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.text });
    text(ctx, example, 420, yy + 180, { size: 40, weight: 400, color: UI.dim });
    ctx.restore();
  });
}

// ------------------------------------------------------------------- safety
function drawSafety(ctx, scene, t, local) {
  stageField(ctx, t);
  // a red field that arrives with the warning, then calms down
  const warn = span(local, 0.1, 0.5) * (1 - span(local, 3.4, 4.2));
  if (warn > 0) {
    ctx.save();
    ctx.globalAlpha = 0.10 * warn;
    ctx.fillStyle = UI.red;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
  slash(ctx, { x: W / 2, y: 300, length: W * 0.8, angle: -0.04, progress: span(local, 0.15, 0.9), width: 22, colour: UI.red });

  text(ctx, scene.title, W / 2, 420, {
    size: 118, weight: 700, family: 'Space Grotesk', color: UI.ink, align: 'center',
    alpha: clamp(span(local, 0.2, 0.9) * 1.6),
  });

  // a repository settings panel with a secret, masked
  const box = { x: 620, y: 620, w: W - 1240, h: 900 };
  panel(ctx, { ...box, r: 24, fill: UI.window, stroke: UI.line, shadow: 0.8 });
  text(ctx, 'Settings  /  Secrets', box.x + 60, box.y + 90, { size: 38, weight: 700, color: UI.text });
  ctx.fillStyle = UI.line;
  ctx.fillRect(box.x + 60, box.y + 130, box.w - 120, 3);

  const rows = [
    ['API_KEY', '••••••••••••••••', true],
    ['DATABASE_URL', '••••••••••••••••', true],
    ['password', 'hunter2', false],
  ];
  rows.forEach(([name, value, safe], i) => {
    const p = clamp(span(local, 1.0 + i * 0.7, 1.6 + i * 0.7));
    if (p <= 0) return;
    const yy = box.y + 220 + i * 180;
    ctx.save();
    ctx.globalAlpha = p;
    text(ctx, name, box.x + 60, yy, { size: 40, weight: 600, color: safe ? UI.text : UI.red });
    panel(ctx, {
      x: box.x + 60, y: yy + 30, w: box.w - 120, h: 84, r: 12,
      fill: safe ? '#F3F3F6' : 'rgba(196,22,28,0.10)', stroke: safe ? UI.line : UI.red,
    });
    text(ctx, value, box.x + 100, yy + 86, {
      size: 38, weight: 500, color: safe ? UI.dim : UI.red,
    });
    if (!safe) {
      // the strike-through is the lesson
      const sw = measure(ctx, value, { size: 38, weight: 500 });
      ctx.strokeStyle = UI.red;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(box.x + 96, yy + 70);
      ctx.lineTo(box.x + 104 + sw, yy + 70);
      ctx.stroke();
      chip(ctx, 'NEVER COMMIT THIS', { x: box.x + box.w - 480, y: yy + 48, colour: UI.white, fill: UI.red, size: 26 });
    }
    if (safe) {
      chip(ctx, 'IN SECRETS', { x: box.x + box.w - 400, y: yy + 48, colour: UI.green, fill: 'rgba(46,158,91,0.12)', size: 26 });
    }
    ctx.restore();
  });

  // a leaked key, revoked
  const rp = clamp(span(local, 4.4, 5.2));
  if (rp > 0) {
    panel(ctx, { x: box.x, y: box.y + 760, w: box.w, h: 120, r: 16, fill: UI.ink, stroke: null, alpha: rp });
    text(ctx, 'Revoke first. Clean history second.', box.x + 60, box.y + 832, {
      size: 42, weight: 700, color: UI.gold, alpha: rp,
    });
  }
}

// ------------------------------------------------------------------- habits
const HABITS = [
  ['Keep main working', 'Merge only what is green.'],
  ['One pull request, one idea', 'Small reviews actually happen.'],
  ['Write the README as you go', 'It is the context for the next prompt.'],
  ['Plain commit messages', 'Future you is a reader.'],
  ['Keep the next steps in the repo', 'Not in your head.'],
];

function drawHabits(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });
  HABITS.forEach(([label, detail], i) => {
    const p = clamp(span(local, 0.6 + i * 0.95, 1.2 + i * 0.95));
    if (p <= 0) return;
    const yy = 500 + i * 250;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.translate((1 - ease.outExpo(p)) * 100, 0);
    ctx.beginPath();
    ctx.arc(300, yy - 12, 34, 0, Math.PI * 2);
    ctx.fillStyle = UI.ink;
    ctx.fill();
    ctx.strokeStyle = UI.gold;
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(285, yy - 12);
    ctx.lineTo(297, yy);
    ctx.lineTo(316, yy - 26);
    ctx.stroke();
    text(ctx, label, 380, yy, { size: 66, weight: 700, family: 'Space Grotesk', color: UI.text });
    text(ctx, detail, 380, yy + 62, { size: 38, weight: 400, color: UI.dim });
    ctx.restore();
  });
}

// -------------------------------------------------------------------- recap
const RECAP = [
  'Create the repository',
  'Connect Arena, choose one repo',
  'Write a small prompt',
  'Let it work in a branch',
  'Read the diff, file by file',
  'Wait for green, then merge',
  'Watch the site update',
];

function drawRecap(ctx, scene, t, local) {
  stageField(ctx, t);
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });
  RECAP.forEach((label, i) => {
    const p = clamp(span(local, 0.42 + i * 0.72, 1.0 + i * 0.72));
    if (p <= 0) return;
    const col = i % 2;
    const row = Math.floor(i / 2);
    const xx = 260 + col * 1720;
    const yy = 520 + row * 300;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.translate((1 - ease.outExpo(p)) * -60, 0);
    panel(ctx, { x: xx, y: yy, w: 1620, h: 240, r: 20, fill: UI.window, stroke: UI.line, shadow: 0.4 });
    text(ctx, String(i + 1).padStart(2, '0'), xx + 60, yy + 150, { size: 76, weight: 700, family: 'Space Grotesk', color: UI.line2 });
    text(ctx, label, xx + 200, yy + 138, { size: 50, weight: 700, family: 'Space Grotesk', color: UI.text });
    ctx.restore();
  });
  // The closing card takes the empty half of the last row. Sitting it on row
  // four printed it straight over item seven.
  const last = 520 + 3 * 300;
  const p = clamp(span(local, 5.6, 6.4));
  if (p > 0) {
    ctx.save();
    ctx.globalAlpha = p;
    const xx = 260 + 1 * 1720;
    panel(ctx, { x: xx, y: last, w: 1620, h: 240, r: 20, fill: UI.ink, stroke: null });
    text(ctx, 'And repeat.', xx + 60, last + 108, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.gold });
    text(ctx, 'The loop is the product.', xx + 60, last + 176, { size: 36, weight: 400, color: '#B9B9C4' });
    ctx.restore();
  }
}

// -------------------------------------------------------------------- outro
function drawOutro(ctx, scene, t, local) {
  stageField(ctx, t, true);
  const lines = scene.title.split('\n');
  lines.forEach((line, i) => {
    const p = span(local, 0.15 + i * 0.35, 1.2 + i * 0.35);
    text(ctx, line, W / 2, 600 + i * 210, {
      size: 150, weight: 700, family: 'Space Grotesk', color: i === 1 ? UI.gold : UI.white,
      align: 'center', alpha: clamp(p * 1.5),
    });
  });
  rule(ctx, W / 2 - 460, 1330, 920, {
    progress: ease.outCubic(span(local, 1.4, 2.4)), colour: UI.red, thickness: 10,
  });
  text(ctx, 'No course. No framework. No permission.', W / 2, 1440, {
    size: 48, weight: 500, color: 'rgba(242,242,242,0.6)', align: 'center',
    alpha: clamp(span(local, 1.8, 2.6)),
  });
  // The streak and the flash together crossed the luminance change threshold
  // three times in a second. Both are calmer now, and the film still lands.
  rainbowStreak(ctx, { x: W / 2, y: 1740, w: W * 0.9, h: 90, progress: span(local, 2.6, 6.2) });
  if (local > 0.05 && local < 0.75) {
    ctx.fillStyle = `rgba(255,255,255,${(1 - (local - 0.05) / 0.7) * 0.55})`;
    ctx.fillRect(0, 0, W, H);
  }
}

// ------------------------------------------------------------------ dispatch
const RENDERERS = {
  title: drawTitle,
  statement: drawStatement,
  pipeline: drawPipeline,
  github: drawGithub,
  connect: drawConnect,
  prompt: drawPrompt,
  agent: drawAgent,
  diff: drawDiff,
  checks: drawChecks,
  merge: drawMerge,
  feature: drawFeature,
  revert: drawRevert,
  patterns: drawPatterns,
  safety: drawSafety,
  habits: drawHabits,
  recap: drawRecap,
  outro: drawOutro,
};

/** A scene change is a movement, never a cut: 12 frames of whip and flash. */
function transition(ctx, scene, local) {
  const p = span(local, 0, 0.34);
  if (p >= 1) return;
  const e = ease.outExpo(p);
  ctx.save();
  ctx.fillStyle = `rgba(255,255,255,${(1 - e) * 0.55})`;
  ctx.fillRect(0, 0, W, H);
  // speed lines run with the whip, so the frame has velocity even between shots
  speedLines(ctx, {
    x: W / 2, y: H / 2, w: W * 1.3, h: H, progress: 1 - e,
    count: 18, colour: UI.ink, alpha: 0.10,
  });
  ctx.restore();
  void scene;
}

/**
 * The scene camera: a slow push-in with a little drift, one per scene.
 *
 * Without it a card sits exactly still between two spoken lines, which is the
 * difference between a diagram and a shot. The move is small enough to never
 * read as a zoom and large enough that the frame is never identical for two
 * frames in a row.
 */
function camera(ctx, scene, local, t) {
  const length = Math.max(1, scene.end - scene.start);
  const p = clamp(local / length);
  const zoom = 1 + 0.035 * p;

  // A re-frame on every spoken line, the way an operator settles the shot on a
  // beat: the frame eases 26 units sideways and 7 down, then holds. It is the
  // difference between a diagram that is shown and a shot that is covered.
  // Beats land on every line *and* halfway through it. One per line left 3.7 s
  // of dead frame between moves, which reads as a held slide on a long film.
  const beats = [];
  for (let i = 0; i < scene.lines.length; i += 1) {
    const line = scene.lines[i];
    beats.push(Math.max(scene.start, line.start - 0.06));
    beats.push(line.start + (line.end - line.start) * 0.5);
  }
  const sign = (i) => (i % 2 === 0 ? 1 : -1);
  let idx = -1;
  for (let i = 0; i < beats.length; i += 1) {
    if (t >= beats[i]) idx = i;
  }
  let dx = 0;
  let dy = 0;
  if (idx >= 0) {
    const k = ease.outCubic(clamp((t - beats[idx]) / 0.42));
    dx = lerp(idx === 0 ? 0 : sign(idx - 1), sign(idx), k) * 58;
    dy = lerp(idx === 0 ? 0 : -1, 1, k) * 13;
  }
  dx += Math.sin(local * 0.31) * 1.6;
  dy += Math.cos(local * 0.27) * 1.2;

  ctx.translate(W / 2, H / 2);
  ctx.scale(zoom, zoom);
  ctx.translate(-W / 2 + dx, -H / 2 + dy);
}

/**
 * A light sheen crossing the whole frame, on a slow cycle.
 *
 * The stage is a flat field, and a flat field is what "static" looks like even
 * when the diagram on it is being read. A single soft band of light moving
 * across it keeps the entire frame in motion without asking the viewer to look
 * at anything new, and it costs one gradient per frame.
 */
function sheen(ctx, t, dark) {
  const period = 7.5;
  const p = (t % period) / period;
  const x = lerp(-W * 0.4, W * 1.4, p);
  const g = ctx.createLinearGradient(x - W * 0.35, 0, x + W * 0.35, 0);
  const alpha = dark ? 0.10 : 0.16;
  const colour = dark ? '255,240,200' : '255,255,255';
  g.addColorStop(0, `rgba(${colour},0)`);
  g.addColorStop(0.5, `rgba(${colour},${alpha})`);
  g.addColorStop(1, `rgba(${colour},0)`);
  ctx.save();
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

function render(t) {
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const scene = sceneAt(t);
  const local = t - scene.start;
  const draw = RENDERERS[scene.kind];
  if (!draw) throw new Error(`no renderer for scene ${scene.id} (${scene.kind})`);

  ctx.save();
  camera(ctx, scene, local, t);
  draw(ctx, scene, t, local);
  ctx.restore();
  transition(ctx, scene, local);

  if (scene.dark) {
    // the dark scenes carry the bands differently: the type is already framed
    bands(ctx, scene, t);
  } else {
    bands(ctx, scene, t);
  }
  if (local < 2.4 && ['github', 'connect', 'prompt', 'diff', 'checks', 'merge', 'feature', 'revert'].includes(scene.kind)) {
    chapterOverlay(ctx, scene, local);
  }
  sheen(ctx, t, !!scene.dark);
  grain(ctx, Math.round(t * FPS));
}

// -------------------------------------------------------------------- output
function srt(seconds) {
  const stamp = (s) => {
    const ms = Math.round(s * 1000);
    const hh = String(Math.floor(ms / 3600000)).padStart(2, '0');
    const mm = String(Math.floor(ms / 60000) % 60).padStart(2, '0');
    const ss = String(Math.floor(ms / 1000) % 60).padStart(2, '0');
    const mmm = String(ms % 1000).padStart(3, '0');
    return `${hh}:${mm}:${ss},${mmm}`;
  };
  return LINES.map((line, i) => (
    `${i + 1}\n${stamp(line.start)} --> ${stamp(Math.min(line.end, seconds))}\n${line.text}\n`
  )).join('\n');
}

function writeFilm(outDir) {
  const film = {
    title: 'Vibe Coding on Arena, through GitHub',
    duration_seconds: Math.round(TOTAL_SECONDS * 1000) / 1000,
    fps: FPS,
    canvas: { width: W, height: H },
    scenes: SHOTS.map((scene) => ({
      id: scene.id, kind: scene.kind, chapter: scene.chapter,
      start: Math.round(scene.start * 1000) / 1000,
      end: Math.round(scene.end * 1000) / 1000,
      narration_lines: scene.lines.length,
    })),
    // `shots` is what the audio designer reads for its scene cues, so the bed
    // changes on the chapter card rather than at an arbitrary second.
    shots: SHOTS.map((scene) => ({
      id: scene.id, label: scene.chapter,
      start: Math.round(scene.start * 1000) / 1000,
      end: Math.round(scene.end * 1000) / 1000,
      layers: ['stage', 'interface', 'callouts', 'captions'],
    })),
    score: [
      { kind: 'swell', at: 0.4, length: 1.9, gain: 0.10 },
      ...SHOTS.slice(1).map((scene) => ({
        kind: 'click', at: Math.round((scene.start + 0.1) * 100) / 100, length: 0.1, gain: 0.05,
      })),
      { kind: 'impact', at: Math.round((SHOTS[SHOTS.length - 1].start + 0.3) * 100) / 100, length: 1.4, gain: 0.12 },
    ],
    motion: {
      linear_interpolation: false,
      every_frame_drawn: true,
      transitions: ['whip + speed lines', 'slam', 'chapter card'],
      interface: 'vector mockups, no screenshots',
    },
    narration: {
      lines: LINES.length,
      source: VOICE.path ? path.basename(VOICE.path) : 'silent-fallback',
      duration_seconds: Math.round(LINES[LINES.length - 1].end * 1000) / 1000,
    },
    captions: 'captions.srt',
    // Declared by the film, measured on the delivered encode. The grain layer is
    // what carries most of the mean delta on this material: a held screen measures
    // 0.16-0.24 on structure alone. Both are checked, and both are reported.
    motion_gate: { min_mean: 0.8, max_static: 0.5 },
  };
  fs.writeFileSync(path.join(outDir, 'film.json'), JSON.stringify(film, null, 2));
  fs.writeFileSync(path.join(outDir, 'captions.srt'), srt(TOTAL_SECONDS), 'utf8');
  fs.writeFileSync(path.join(outDir, 'timeline.txt'), [
    'VIBE CODING ON ARENA, THROUGH GITHUB',
    '',
    ...SHOTS.map((scene) => `  ${scene.chapter.padEnd(24)} ${scene.id.padEnd(10)} `
      + `${scene.start.toFixed(1).padStart(7)}s - ${scene.end.toFixed(1).padStart(7)}s  ${scene.kind}`),
  ].join('\n'), 'utf8');
}

function main() {
  const outDir = path.resolve(OPTS.out);
  fs.mkdirSync(outDir, { recursive: true });
  const from = Math.max(0, Math.round(OPTS.from));
  const to = Math.min(TOTAL_FRAMES, OPTS.to === null ? TOTAL_FRAMES : Math.round(OPTS.to));
  const started = Date.now();

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
    fs.writeFileSync(path.join(outDir, `frame-${String(frame).padStart(6, '0')}.jpg`),
      canvas.toBuffer('image/jpeg', OPTS.quality));
    // The canvas is 3840x2160 and the grain and dot layers allocate native
    // buffers that the JS heap never sees, so V8 has no reason to collect them
    // and a long render climbs to several gigabytes and stalls. Ask for a
    // collection on a fixed cadence instead of waiting for the machine to swap.
    if (forceGC && (frame - from) % 12 === 0) forceGC();
    if (!OPTS.quiet && (frame - from) % 300 === 0) {
      const done = frame - from + 1;
      const rate = done / ((Date.now() - started) / 1000);
      console.log(`frame ${frame}/${to}  ${rate.toFixed(1)} fps  ${((to - frame) / rate).toFixed(0)}s left`);
    }
  }

  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({
    width: OPTS.width, height: OPTS.height, fps: FPS, frame_count: TOTAL_FRAMES,
    rendered_from: from, rendered_to: to, source: 'video_studio/films/vibe_coding.mjs',
    duration_seconds: Math.round(TOTAL_SECONDS * 1000) / 1000,
  }, null, 2));
  writeFilm(outDir);

  if (!OPTS.quiet) {
    console.log(`rendered ${to - from} frames at ${OPTS.width}x${OPTS.height} `
      + `in ${((Date.now() - started) / 1000).toFixed(1)}s`);
  }
}

main();
