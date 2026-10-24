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
import { beatState, pulse, spotlight, beatTicks } from '../motion/live.mjs';
import { secondUnit } from '../motion/second_unit.mjs';

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

// What "moving" means. These numbers are not this file's opinion: they are the
// same grid and the same threshold as `video_studio/repeat_frames.py`, which is
// what runs on the delivered file. A probe that is more forgiving than the
// delivery check is how a film passes its own audit and then freezes at 11:25
// on YouTube, which is exactly what happened once. tests/test_vibe_probe.py
// fails if the two ever disagree.
const PROBE = {
  blockDelta: 10.0,   // grey levels a 32x18 block must move to count
  stillShare: 0.02,   // share of blocks that must move; below this is a hold
  lagSeconds: 0.5,    // compare against half a second ago, not the last frame
  maxStillSeconds: 1.0,
};

// ------------------------------------------------------------------ options
function parseArgs(argv) {
  const opts = {
    out: 'frames', width: 1920, height: null, fps: 30, quality: 90,
    from: 0, to: null, still: null, quiet: false, plan: false,
    voiceLines: null, voiceScript: null, grain: true, probe: false,
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
    else if (flag === '--no-grain') opts.grain = false;
    else if (flag === '--probe') opts.probe = true;
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
  // The film starts at frame zero, not two and a half seconds later. A lead-in
  // of empty stage is dead air in the one place a viewer is most likely to
  // leave, and it measured as a two-second freeze on an otherwise clean cut.
  if (built.length) built[0].start = 0;
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
    const ox = CONTENT_ONLY ? 0 : (t * 18) % step;
    const oy = CONTENT_ONLY ? 0 : (t * 11) % step;
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
  const ox = CONTENT_ONLY ? 0 : (t * DOT_SPEED) % step;
  const oy = CONTENT_ONLY ? 0 : (t * DOT_SPEED * 0.55) % step;
  ctx.fillStyle = `rgba(20,20,26,${DOT_ALPHA})`;
  for (let gx = -step; gx < W + step; gx += step) {
    for (let gy = -step; gy < H + step; gy += step) {
      ctx.fillRect(gx + ox, gy + oy, DOT_SIZE, DOT_SIZE);
    }
  }

  // a slow pool of light that keeps the flat stage alive behind a still card
  const x = W * (CONTENT_ONLY ? 0.5 : 0.5 + Math.sin(t * 0.07) * 0.18);
  const glow = ctx.createRadialGradient(x, H * 0.45, 0, x, H * 0.45, H * 0.9);
  glow.addColorStop(0, 'rgba(255,255,255,0.30)');
  glow.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
}

// When set, the probe (and only the probe) strips the layers that move on their
// own — camera, drifting dots, the sheen — so the measurement reports what the
// content is doing rather than what the decoration is doing.
const CONTENT_ONLY = process.env.VC_PROBE_CONTENT === '1';
// Switchable so the probe can be validated against a frame we know is frozen:
// an instrument that never reports a fault is not an instrument.
const LIVE = process.env.VC_LIVE !== '0';

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
/**
 * Lay a line of words out centred, so each word can arrive on its own beat.
 *
 * One `text()` call per word, not one per line: a line that fades in as a block
 * is one event, and this card needs an event every second for twenty-five
 * seconds. Per-word arrivals also read as the narration speaking the title.
 */
function layoutWords(ctx, words, { size, weight = 700, family = 'Space Grotesk', gap = 46 }) {
  const widths = words.map((word) => measure(ctx, word, { size, weight, family }));
  const total = widths.reduce((sum, width) => sum + width, 0) + gap * (words.length - 1);
  let x = W / 2 - total / 2;
  return words.map((word, i) => {
    const entry = { text: word, x, w: widths[i] };
    x += widths[i] + gap;
    return entry;
  });
}

/**
 * A word arriving: it travels up into place and overshoots slightly.
 *
 * The travel and the fade are what move the picture. A word of this size
 * crossing the frame is a dozen blocks changing at once, which is the only
 * thing a freeze detector at delivery scale can actually see; a small word
 * fading in is invisible to it and reads as a slide to a viewer.
 */
function slamWord(ctx, entry, y, at, local, colour, {
  size, travel = 170, duration = 0.85, centre = false, alpha = 1,
} = {}) {
  const p = span(local, at, at + duration);
  if (p <= 0) return false;
  const e = ease.outExpo(p);
  ctx.save();
  ctx.globalAlpha = clamp(p * 3.2) * alpha;
  ctx.translate(0, (1 - e) * travel);
  text(ctx, entry.text, centre ? entry.x + entry.w / 2 : entry.x, y, {
    size, weight: 700, family: 'Space Grotesk', color: colour,
    align: centre ? 'center' : 'left',
  });
  ctx.restore();
  return true;
}

/**
 * The opening card: four spoken lines, four acts.
 *
 * The card used to land its type in the first two seconds and then hold for
 * twenty-three, and the freeze detector found seven dead spans in it. Each
 * spoken line now owns its own staging, and every stage is carried by big
 * moving parts: words crossing the frame, a ring of steps turning, slabs
 * stamping down. The narration is still the clock - every `at` below is
 * computed from the line's own start and end, so a slower read of the same
 * script spreads the same events out.
 */
function drawTitle(ctx, scene, t, local) {
  stageField(ctx, t, true);
  speedLines(ctx, { x: W / 2, y: H / 2, w: W * 1.4, h: H, progress: 1, count: 26, colour: '#FFFFFF', alpha: 0.05, angle: -0.2 });

  const beat = (line) => (line ? line.start - scene.start : 99);
  const over = (line) => (line ? line.end - scene.start : 99);
  const e0 = over(scene.lines[0]);
  const b1 = beat(scene.lines[1]);
  const b2 = beat(scene.lines[2]);
  const b3 = beat(scene.lines[3]);
  const e3 = over(scene.lines[3]);

  if (local < 0.16) {
    ctx.fillStyle = `rgba(255,255,255,${(1 - local / 0.16) * 0.9})`;
    ctx.fillRect(0, 0, W, H);
  }

  // ---------------------------------------------------------- act 1: title
  // The title arrives as two lines, not five words. Measured at delivery
  // scale a short word like "IT" moves four blocks of the picture and passes
  // as a slide; a whole line moves thirteen and registers. The slash then
  // holds the frame: it grows under the title and fades out of it, so the
  // first line of narration is a single staged moment instead of two type
  // entrances and eight quiet seconds.
  // Whole lines, so each arrival is one solid block of type.
  const lineEntries = [
    layoutWords(ctx, ['BUILD IT'], { size: 230, gap: 0 })[0],
    layoutWords(ctx, ['BY DESCRIBING IT'], { size: 230, gap: 0 })[0],
  ];

  // Fast slams, not slow ones. Measured on this material: a slam is visible
  // to the detector for about 0.8 seconds - a quick alpha ramp, a fast cross
  // of the frame, and half a second of comparison lag. Drift slower than that
  // and the picture is a slide. Every event below is spaced on that number,
  // and the slots are fractions of the spoken line so a slow read spreads
  // them and a fast read bunches them without ever freezing.
  const slam1 = 0.4;
  const slam2 = Math.min(Math.max(0.4 + (e0 - 0.4) * 0.12, 1.3), 1.7);
  const span1 = Math.max(0.8, b1 - slam2);
  const ev = (f) => slam2 + span1 * f;
  const slamDur = 0.7;
  const slamTravel = 240;
  const hitAt = ev(0.12);
  const compactAt = ev(0.28);
  const slashOffAt = ev(0.44);

  // From act 2 the title lifts and dims; from act 3 it is gone. Staging, not
  // a fade: the frame changes composition on every spoken line.
  const lift = ease.inOutCubic(clamp(span(local, b1 - 1.1, b1 + 0.2)));
  const gone = ease.inOutCubic(clamp(span(local, b2 - 0.2, b2 + 0.7)));
  // after the hit the title compacts upward, making room for the definition
  const compact = ease.outCubic(clamp(span(local, compactAt, compactAt + 0.7)));

  lineEntries.forEach((entry, i) => {
    const at = i === 0 ? slam1 : slam2;
    const p = span(local, at, at + slamDur);
    if (p <= 0) return;
    const e = ease.outExpo(p);
    ctx.save();
    // Fully out, not half-lit: at 50% the title printed behind the phrase
    // slabs that arrive next, so "BY DESCRIBING IT" was legible through
    // "PLAIN ENGLISH" for the whole of that beat.
    ctx.globalAlpha = clamp(p * 3.2) * (1 - lift) * (1 - gone);
    ctx.translate(0, (1 - e) * slamTravel - compact * 220 - lift * 200 - gone * 340);
    text(ctx, entry.text, entry.x, (i === 0 ? 960 : 1150), {
      size: 230, weight: 700, family: 'Space Grotesk',
      color: i === 0 ? UI.white : UI.gold,
    });
    ctx.restore();
  });

  const slashEnd = Math.min(b1 + 0.5, hitAt + 4.5);
  const slashOff = ease.inCubic(clamp(span(local, slashOffAt, slashOffAt + 0.7)));
  if (local > hitAt && slashOff < 1) {
    // a band of light falls through the frame as the slash lands
    const band = span(local, hitAt, hitAt + 0.45);
    if (band < 1) {
      const g = ctx.createLinearGradient(0, -200 + band * (H + 400), 0, 320 + band * (H + 400));
      g.addColorStop(0, 'rgba(255,240,190,0)');
      g.addColorStop(0.5, `rgba(255,240,190,${0.32 * (1 - band)})`);
      g.addColorStop(1, 'rgba(255,240,190,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }
    // An underline, not a slash. `slash()` draws a curved stroke across the
    // middle of the frame, and here the middle of the frame is the title: the
    // owner's first two notes on this cut were "text is overlapping" and "what is
    // that red arc in the first three seconds", and they were the same object - a
    // 46-unit red arc cutting through both lines of type.
    //
    // A rule that draws on beneath the second line does the same job (a hard
    // accent on the beat, in the film's red) without ever crossing a word, and it
    // still moves: it grows from 0 to full width in half a second, then swipes out
    // to the left, which is a block of mass travelling.
    {
      const entry = lineEntries[1];
      const yLine = 1150 - compact * 220 - lift * 200 - gone * 340;
      const grow = ease.outQuint(clamp(span(local, hitAt, hitAt + 0.5)));
      const width = entry.w * grow;
      const left = entry.x + (entry.w - width) / 2 - slashOff * 900;
      if (width > 2) {
        rule(ctx, left, yLine + 46 + slashOff * 420, width, {
          progress: 1, colour: UI.red, thickness: 26, alpha: 1 - slashOff,
        });
      }
    }
    // A burst of shards reads as debris over the type; the underline is the hit.
    void shards;
  }

  // The card's own closing line performs itself: three phrases swapping places
  // under the title. Each swap is two blocks of type crossing the frame in
  // opposite directions, which is what carries the tail of a slow read.
  const noteBits = ['A REAL APP.', 'A REAL REPOSITORY.', 'NO TYPING.'];
  const noteOut = ease.inOutCubic(clamp(span(local, b1 + 0.1, b1 + 0.6)));
  noteBits.forEach((bit, i) => {
    const inAt = ev(0.52 + i * 0.16);
    // The outgoing phrase clears first, then the new one arrives. They used to
    // travel at the same time and cross in the middle, and at 150 px of type that
    // is two readable words printed on top of each other for half a second: seen
    // on a still of 0:08, "A REAL REPOSITORY" and the phrase replacing it were
    // the same pixels. Staging, not a cross-fade.
    const swap = span(local, inAt + 0.2, inAt + 0.65);
    if (swap <= 0) return;
    const e = ease.outExpo(swap);
    const leave = i > 0 ? ease.inCubic(span(local, inAt, inAt + 0.2)) : 0;
    ctx.save();
    ctx.globalAlpha = clamp(swap * 2.4) * (1 - noteOut);
    if (i > 0 && leave < 1) {
      // the previous phrase crosses out to the left as this one comes in
      const prev = noteBits[i - 1];
      text(ctx, prev, W / 2 - leave * 700, 1860, {
        size: 150, weight: 700, family: 'Space Grotesk',
        color: 'rgba(242,242,242,0.5)', align: 'center',
        alpha: 1 - leave,
      });
    }
    text(ctx, bit, W / 2 + (1 - e) * 500, 1860, {
      size: 150, weight: 700, family: 'Space Grotesk',
      color: i === 1 ? UI.gold : 'rgba(242,242,242,0.85)', align: 'center',
    });
    ctx.restore();
  });

  // ------------------------------------------------- act 2: the definition
  // "You describe what you want in plain English. An agent writes it, on
  // GitHub, while you watch." The three phrases stamp in as slabs, each one
  // pushing the stack up. A phrase of type alone is a dozen blocks of picture;
  // a phrase on its slab is forty, and the push moves every slab already on
  // screen - so every beat of this line is impossible to read as a hold.
  const keyPhrases = [
    { text: 'PLAIN ENGLISH', colour: UI.white, size: 150 },
    { text: 'THE AGENT WRITES', colour: UI.gold, size: 150 },
    // the punchline is the biggest: "on GitHub" is what the film is about
    { text: 'ON GITHUB', colour: UI.white, size: 195 },
  ];
  const kStart = b1 + 0.3;
  const step2 = Math.min(Math.max((b2 - 2.1 - kStart) / 2, 0.8), 1.6);
  const keyW = 2600;
  const keyH = 260;
  // the phrases leave as the name stamps: the frame must never keep an old
  // composition and add a new one on top of it
  const keyOut = ease.inOutCubic(clamp(span(local, b2 - 0.15, b2 + 0.55)));
  // After the last slab the stack locks itself in: two settle stages, each one
  // moving all three slabs. Measured on this card, the slab arrivals cover
  // their own beats but the tail of the line went quiet for 0.7s between the
  // last arrival and the exit - and a quiet tail is a held frame. The two
  // settles are the answer, and they are what the eye reads as "done".
  const settleA = ease.outCubic(clamp(span(local, b2 - 2.1, b2 - 1.4)));
  const settleB = ease.outCubic(clamp(span(local, b2 - 1.0, b2 - 0.3)));
  keyPhrases.forEach((phrase, i) => {
    const at = kStart + i * step2;
    const p = span(local, at, at + 0.7);
    if (p <= 0) return;
    const e = ease.outBack(clamp(p * 1.2));
    // the stack scoots up as one when the next slab arrives, making room
    const scoot = i < keyPhrases.length - 1
      ? ease.outCubic(clamp(span(local, at + step2 - 0.7, at + step2))) * 120
      : 0;
    // Raised from 1220: at the old height the last slab ran into the caption
    // band, and "ON GITHUB" was printed underneath the subtitle.
    // The stack has to fit between three things: the title above it (which
    // is still on screen at 50% while the slabs land), the caption band below
    // it at 1900, and its own three slabs. 1180 + 2*220 + 260 = 1880.
    const y = 1180 + i * 220 + (1 - e) * 260 - scoot - settleA * 70 - settleB * 70;
    const x = W / 2 - keyW / 2;

    ctx.save();
    ctx.globalAlpha = clamp(p * 1.7) * (1 - keyOut);
    ctx.translate(0, -keyOut * 200);
    panel(ctx, {
      x, y, w: keyW, h: keyH, r: 28,
      fill: '#1A1A1E', stroke: i === 1 ? UI.gold : '#3A3A44',
    });
    ctx.fillStyle = i === 1 ? UI.gold : UI.red;
    ctx.fillRect(x, y, 22, keyH);
    text(ctx, phrase.text, W / 2, y + keyH / 2 + phrase.size * 0.35, {
      size: phrase.size, weight: 700, family: 'Space Grotesk',
      color: phrase.colour, align: 'center', tracking: 3,
    });
    ctx.restore();
  });

  // ------------------------------------------------------ act 3: the name
  // "This is called vibe coding" - the name stamps like a channel ident, and
  // the whole loop turns beside it: seven steps, one landing at a time, with a
  // hand sweeping to each. This is the film's table of contents, said once.
  const nameP = clamp(span(local, b2 + 0.25, b2 + 0.95));
  // It fades out as the promises arrive: the ident shares its corner with the
  // first slab, and two things in one place read as a mistake, not a stack.
  const nameOut = ease.inOutCubic(clamp(span(local, b3 + 0.2, b3 + 0.75)));
  if (nameP > 0 && nameOut < 1) {
    const e = ease.outExpo(nameP);
    ctx.save();
    ctx.globalAlpha = nameP * (1 - nameOut);
    ctx.translate(150, 1540 + (1 - e) * 40);
    text(ctx, 'VIBE CODING', 0, 0, { size: 46, weight: 700, color: UI.gold, tracking: 10 });
    ctx.fillStyle = UI.red;
    ctx.fillRect(0, 22, 520 * e, 6);
    ctx.restore();
  }

  const ringC = { x: W / 2, y: 1230 };
  const ringR = 440;
  const tile = 220;
  const steps = 7;
  const rStart = b2 + 0.55;
  const rEnd = Math.max(rStart + 2.4, b3 - 1.15);
  const step3 = (rEnd - rStart) / (steps - 1);
  const ringOut = ease.inOutCubic(clamp(span(local, b3 + 0.05, b3 + 0.55)));
  // The ring belongs to act 3 only. It used to be drawn from frame one, so the
  // opening title was staged on top of a half-built diagram.
  const ringIn = clamp(span(local, rStart - 0.45, rStart + 0.1));

  if (ringOut < 1 && ringIn > 0) {
    ctx.save();
    ctx.globalAlpha = (1 - ringOut) * ringIn;
    ctx.translate(ringC.x, ringC.y);
    ctx.scale(1 - ringOut * 0.16, 1 - ringOut * 0.16);
    ctx.translate(-ringC.x, -ringC.y);

    // the track the steps sit on
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 18;
    ctx.beginPath();
    ctx.arc(ringC.x, ringC.y, ringR, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    const startAngle = -Math.PI / 2;
    let handAngle = startAngle;
    for (let i = 0; i < steps; i += 1) {
      const at = rStart + i * step3;
      const landed = span(local, at, at + 0.45);
      if (landed <= 0) break;
      const angle = startAngle + (i * Math.PI * 2) / steps;
      handAngle = angle;
      const x = ringC.x + Math.cos(angle) * ringR;
      const y = ringC.y + Math.sin(angle) * ringR;
      const pop = ease.outBack(clamp(landed * 1.5));
      const colour = i === steps - 1 ? UI.red : UI.gold;

      // a beam fires outward as the step lands
      const beam = clamp(span(local, at, at + 0.55));
      if (beam < 1) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        const g = ctx.createLinearGradient(0, 0, 520, 0);
        g.addColorStop(0, i === steps - 1
          ? `rgba(196,22,28,${0.5 * (1 - beam)})`
          : `rgba(242,194,48,${0.5 * (1 - beam)})`);
        g.addColorStop(1, 'rgba(242,194,48,0)');
        ctx.fillStyle = g;
        ctx.fillRect(120, -110, 520, 220);
        ctx.restore();
      }

      ctx.save();
      ctx.fillStyle = colour;
      roundRect(ctx, x - (tile * pop) / 2, y - (tile * pop) / 2, tile * pop, tile * pop, 40);
      ctx.fill();
      if (pop > 0.5) {
        ctx.fillStyle = 'rgba(11,11,12,0.88)';
        roundRect(ctx, x - 74, y - 74, 148, 148, 28);
        ctx.fill();
        text(ctx, String(i + 1), x, y + 24, {
          size: 84, weight: 700, color: UI.white, align: 'center',
        });
      }
      ctx.restore();
    }

    // the hand: it sweeps to each step and keeps sweeping, so the ring is
    // never still between two landings
    const pulse = ease.outCubic(clamp(span(local, b3 - 1.05, b3 - 0.25)));
    const hubR = 90 + pulse * 40 * Math.sin(Math.PI * clamp(span(local, b3 - 1.05, b3 + 0.2)));
    ctx.save();
    ctx.translate(ringC.x, ringC.y);
    ctx.rotate(handAngle);
    const hg = ctx.createLinearGradient(0, 0, ringR, 0);
    hg.addColorStop(0, 'rgba(242,194,48,0.95)');
    hg.addColorStop(1, 'rgba(242,194,48,0.15)');
    ctx.fillStyle = hg;
    ctx.beginPath();
    ctx.moveTo(60, -16);
    ctx.lineTo(ringR - 120, -6);
    ctx.lineTo(ringR - 120, 6);
    ctx.lineTo(60, 16);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.fillStyle = UI.gold;
    ctx.beginPath();
    ctx.arc(ringC.x, ringC.y, hubR, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = UI.ink;
    ctx.beginPath();
    ctx.arc(ringC.x, ringC.y, hubR * 0.45, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.restore();
  }

  // ---------------------------------------------------- act 4: the promises
  // "By the end you will have a repository, a pull request, and a working
  // site." Three slabs stamp down; as each promise is spoken its slab turns
  // gold and takes a check. The card ends on three things kept, not on a
  // sentence about them.
  const promises = ['A REPOSITORY', 'A PULL REQUEST', 'A LIVE SITE'];
  const slabW = 880;
  const slabH = 230;
  const slabY = 1400;
  const slabX0 = W / 2 - (promises.length * (slabW + 80) - 80) / 2;
  const sIn = (i) => b3 + 0.45 + i * 0.9;
  const tickSpan = Math.max(0.6, e3 - 0.25 - (b3 + 3.0));
  const tickAt = (i) => b3 + 3.0 + (i * tickSpan) / 2;

  promises.forEach((label, i) => {
    const at = sIn(i);
    const p = span(local, at, at + 0.7);
    if (p <= 0) return;
    const e = ease.outBack(clamp(p * 1.2));
    const x = slabX0 + i * (slabW + 80);
    const y = slabY + (1 - e) * 220;

    // the tick: the slab fills gold, then a check plate stamps on top of it
    const tp = clamp(span(local, tickAt(i), tickAt(i) + 0.45));
    const fill = ease.inOutCubic(tp);
    const plate = ease.outBack(clamp(span(local, tickAt(i) + 0.25, tickAt(i) + 0.85) * 1.3));

    ctx.save();
    ctx.globalAlpha = clamp(p * 1.6);
    panel(ctx, {
      x, y, w: slabW, h: slabH, r: 28,
      fill: fill > 0
        ? `rgb(${Math.round(245 + (242 - 245) * fill)},${Math.round(245 + (194 - 245) * fill)},${Math.round(247 + (48 - 247) * fill)})`
        : '#F5F5F7',
      stroke: fill > 0 ? UI.gold : '#3A3A44',
    });
    ctx.fillStyle = UI.red;
    ctx.fillRect(x, y, 22, slabH);
    // Fit the label to the slab instead of trusting it to fit. The tick plate
    // takes the last 270 units, and "A PULL REQUEST" at 64 px ran underneath it:
    // seen on a still of 0:24, the plate sat on the final T.
    const room = slabW - 64 - 300;
    let labelSize = 64;
    while (labelSize > 34 && measure(ctx, label, { size: labelSize, weight: 700 }) > room) {
      labelSize -= 2;
    }
    text(ctx, label, x + 64, y + 148, {
      size: labelSize, weight: 700, color: UI.ink, tracking: 2,
    });

    if (plate > 0) {
      const px = x + slabW - 170;
      const py = y + slabH / 2;
      const s = plate;
      ctx.save();
      ctx.translate(0, (1 - ease.outExpo(clamp(plate))) * -120);
      ctx.fillStyle = UI.ink;
      roundRect(ctx, px - (78 * s), py - (78 * s), 156 * s, 156 * s, 30);
      ctx.fill();
      if (s > 0.45) {
        ctx.strokeStyle = UI.gold;
        ctx.lineWidth = 22;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        ctx.moveTo(px - 42, py - 2);
        ctx.lineTo(px - 12, py + 30);
        ctx.lineTo(px + 46, py - 34);
        ctx.stroke();
      }
      ctx.restore();
    }
    ctx.restore();
  });

  // scene.note's copy is performed by the phrase swaps in act 1; the card has
  // no small static caption row, because a row that sits still is a slide.
}

/** Big type on the pale stage: the idea scenes. */
function drawStatement(ctx, scene, t, local) {
  stageField(ctx, t);
  const beat = (line) => (line ? line.start - scene.start : 99);
  const over = (line) => (line ? line.end - scene.start : 99);
  const b = scene.lines.map(beat);
  const e = scene.lines.map(over);

  // The idea, stamped as two lines of big type over the first sentence, then
  // underlined by something with weight. A rule of eight pixels moves no
  // block of the picture; this bar is what carries the second between the
  // title and the first diagram.
  scene.title.split('\n').forEach((line, i) => {
    const at = i === 0 ? 0.35 : 1.5;
    const p = span(local, at, at + 0.7);
    if (p <= 0) return;
    const ex = ease.outExpo(p);
    ctx.save();
    ctx.globalAlpha = clamp(p * 3.2);
    ctx.translate(0, (1 - ex) * 150);
    text(ctx, line, 260, 620 + i * 200, {
      size: 168, weight: 700, family: 'Space Grotesk', color: i === 1 ? UI.red : UI.ink,
    });
    ctx.restore();
  });
  {
    const p = ease.outQuint(clamp(span(local, 2.9, 3.65)));
    if (p > 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(264, 860, 1200 * p, 150);
    }
  }

  // Every group below is one idea from the narration, on stage while its line
  // is spoken and gone before the next idea lands. The scene used to stack
  // everything it had in the first six seconds and hold for twenty-nine,
  // measured as four frozen spans.
  const leaving = (outAt) => ease.inOutCubic(clamp(span(local, outAt, outAt + 0.5)));

  // line 2 is a cycle - say it, look at it, change it - so it is drawn as one
  {
    const out = leaving(b[3] - 0.2);
    if (out < 1) {
      const values = ['SAY IT', 'SEE IT', 'CHANGE IT'];
      values.forEach((value, i) => {
        const at = b[1] - 0.2 + i * 1.4;
        const p = span(local, at, at + 0.55);
        if (p <= 0) return;
        const ex = ease.outBack(clamp(p * 1.2));
        const w = 1050;
        const x = 260 + i * (w + 100);
        ctx.save();
        ctx.globalAlpha = clamp(p * 1.8) * (1 - out);
        ctx.translate((1 - ex) * 90 - out * 160, 0);
        panel(ctx, { x, y: 1060, w, h: 240, r: 20, fill: UI.ink, stroke: UI.ink });
        ctx.fillStyle = UI.gold;
        ctx.fillRect(x, 1060, 22, 240);
        text(ctx, value, x + 56, 1225, {
          size: 64, weight: 700, family: 'Space Grotesk', color: UI.white,
        });
        ctx.restore();
      });
    }
  }

  // line 3: the work is recorded - commits landing on a rail, paced to the
  // line so the rail is still being written when the sentence ends
  {
    const railY = 1470;
    const railAt = b[2] - 0.3;
    const out = leaving(b[4] + 0.9);
    if (local > railAt && out < 1) {
      ctx.save();
      ctx.globalAlpha = 1 - out;
      ctx.translate(-out * 160, 0);
      ctx.strokeStyle = UI.ink;
      ctx.lineWidth = 10;
      ctx.beginPath();
      ctx.moveTo(300, railY);
      ctx.lineTo(300 + 1500 * ease.outCubic(clamp(span(local, railAt, railAt + 0.8))), railY);
      ctx.stroke();
      for (let i = 0; i < 4; i += 1) {
        const at = railAt + 0.4 + i * 1.2;
        const p = span(local, at, at + 0.5);
        if (p <= 0) break;
        const pop = ease.outBack(clamp(p * 1.5));
        const x = 300 + i * 380;
        // a beam as it lands: the tile alone is four blocks of picture, which
        // the detector shrugs at; tile plus beam is nearly twenty
        const beam = span(local, at, at + 0.55);
        if (beam < 1) {
          const g = ctx.createLinearGradient(0, railY - 90, 0, railY - 620);
          g.addColorStop(0, i === 3
            ? `rgba(196,22,28,${0.55 * (1 - beam)})`
            : `rgba(242,194,48,${0.55 * (1 - beam)})`);
          g.addColorStop(1, 'rgba(242,194,48,0)');
          ctx.fillStyle = g;
          ctx.fillRect(x - 110, railY - 620, 220, 530);
        }
        ctx.fillStyle = i === 3 ? UI.red : UI.gold;
        roundRect(ctx, x - 120 * pop, railY - 120 * pop, 240 * pop, 240 * pop, 44);
        ctx.fill();
      }
      ctx.restore();
    }
  }

  // line 4: "that does not mean you stop thinking"
  {
    const at = b[3] + 0.3;
    const p = span(local, at, at + 0.6);
    const out = leaving(b[4] + 1.6);
    if (p > 0 && out < 1) {
      const ex = ease.outBack(clamp(p * 1.15));
      const kick = span(local, b[4] - 0.5, b[4] - 0.05);
      ctx.save();
      ctx.globalAlpha = clamp(p * 1.8) * (1 - out);
      ctx.translate((1 - ex) * -110 - out * 200 + Math.sin(Math.PI * kick) * -26, 0);
      panel(ctx, { x: 260, y: 1760, w: 1500, h: 190, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(260, 1760, 18, 190);
      text(ctx, 'KEEP THINKING', 330, 1890, {
        size: 86, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // line 5: attention goes on the decision, not on the typing. Two opposed
  // slabs, the arrow that chooses, then the choice re-stated: DECISION
  // rises in weight while TYPING steps back - one more move before the rules.
  const pickAt = b[4] + 0.2;
  const emphasis = ease.outCubic(clamp(span(local, b[5] - 1.5, b[5] - 1.0)));
  const pickOut = leaving(b[6] - 0.3);
  if (pickOut < 1) {
    [
      { label: 'DECISION', x: 320, lift: emphasis * 26, alpha: 1 },
      { label: 'TYPING', x: 1420, lift: 0, alpha: 1 - emphasis * 0.5 },
    ].forEach((value, i) => {
      const p = span(local, pickAt + i * 1.2, pickAt + i * 1.2 + 0.55);
      if (p <= 0) return;
      const ex = ease.outBack(clamp(p * 1.2));
      ctx.save();
      ctx.globalAlpha = clamp(p * 1.8) * value.alpha * (1 - pickOut);
      ctx.translate((1 - ex) * 90 - pickOut * 200, -value.lift);
      panel(ctx, {
        x: value.x, y: 1600, w: 900, h: 230, r: 22,
        fill: UI.ink, stroke: UI.ink,
      });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(value.x, 1600, 22, 230);
      text(ctx, value.label, value.x + 56, 1755, {
        size: 64, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    });
    const ap = ease.outExpo(clamp(span(local, pickAt + 0.7, pickAt + 1.2)));
    if (ap > 0) {
      ctx.save();
      ctx.globalAlpha = ap * (1 - pickOut);
      text(ctx, '\u2190', 1275, 1755, { size: 130, weight: 700, color: UI.red });
      ctx.restore();
    }
  }

  // line 6 announces the rules; each rule then lands on the line that speaks
  // it - lines 7, 8 and 9 - as its own slab.
  {
    const at = b[5] - 0.7;
    const p = span(local, at, at + 0.6);
    if (p > 0) {
      const ex = ease.outBack(clamp(p * 1.2));
      ctx.save();
      ctx.globalAlpha = clamp(p * 1.8);
      ctx.translate(0, (1 - ex) * 100);
      text(ctx, '3 RULES', 2280, 1140, {
        size: 180, weight: 700, family: 'Space Grotesk', color: UI.red,
      });
      ctx.restore();
    }
  }

  // The three rule slabs, settling upward together at the end of the last
  // line so the scene closes on a move instead of on a freeze.
  const values = scene.rules || [];
  const settle = ease.outCubic(clamp(span(local, e[8] - 0.85, e[8] - 0.4)));
  values.forEach((value, i) => {
    const at = (b[6 + i] ?? 3) + 0.35;
    const p = span(local, at, at + 0.65);
    const tileAt = at + 1.5;
    const press = span(local, tileAt, tileAt + 0.45);
    if (p <= 0) return;
    const ex = ease.outBack(clamp(p * 1.15));
    const y = 1300 + i * 230 - settle * 70;
    const pressAlpha = 1 - Math.sin(Math.PI * press) * 0.35;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.8) * pressAlpha;
    ctx.translate((1 - ex) * -120, Math.sin(Math.PI * press) * 16);
    panel(ctx, { x: 260, y: y - 110, w: 3020, h: 190, r: 22, fill: UI.ink, stroke: UI.ink });
    ctx.fillStyle = i === 2 ? UI.red : UI.gold;
    roundRect(ctx, 300, y - 85, 150, 150, 34);
    ctx.fill();
    text(ctx, String(i + 1), 375, y + 14, { size: 70, weight: 700, color: UI.ink, align: 'center' });
    text(ctx, value, 540, y + 28, {
      size: 76, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    ctx.restore();
  });
}

/** The loop: six nodes, one pulse travelling through them. */
function drawPipeline(ctx, scene, t, local) {
  stageField(ctx, t);
  const b = scene.lines.map((line) => line.start - scene.start);
  text(ctx, scene.title, 240, 340, {
    size: 132, weight: 700, family: 'Space Grotesk', color: UI.ink,
    alpha: clamp(span(local, 0.1, 0.7) * 2),
  });
  text(ctx, scene.note, 246, 418, { size: 46, weight: 500, color: 'rgba(23,23,26,0.6)', alpha: clamp(span(local, 1.0, 1.6)) });

  const steps = scene.steps;
  const y = 800;
  const x0 = 300;
  const gap = (W - 600) / (steps.length - 1);

  // One beat per step named in the narration, then the loop turning over, then
  // the six read out together. The scene used to draw all six circles in the
  // first two seconds and leave a dot travelling the rail for thirty, which the
  // composition check scored as two arrangements in thirty-two seconds.
  const beats = [
    [b[1] + 0.2, 0, '01  A PROMPT', 'You say what you want, in plain words.'],
    [b[1] + 1.8, 1, '02  A PLAN', 'The agent says how it will do it, before it does.'],
    [b[1] + 3.6, 2, '03  A BRANCH', 'The work happens away from main, where it is safe.'],
    [b[2] + 0.3, 3, '04  A DIFF', 'Every changed line on one page.'],
    [b[2] + 2.0, 4, '05  THE CHECKS', 'The tests run without being asked.'],
    [b[3] + 0.4, 5, '06  A MERGE', 'Green, then into main. One small step.'],
  ].filter((beat) => Number.isFinite(beat[0]));
  let current = -1;
  beats.forEach((beat, i) => {
    if (local >= beat[0]) current = i;
  });
  const reached = current < 0 ? -1 : beats[current][1];

  rule(ctx, x0, y - 3, W - 600, { progress: ease.outCubic(span(local, 0.3, 1.4)), colour: 'rgba(11,11,12,0.25)', thickness: 6 });

  steps.forEach((step, i) => {
    const p = span(local, 0.4 + i * 0.28, 1.1 + i * 0.28);
    if (p <= 0) return;
    const x = x0 + i * gap;
    const on = i <= reached;
    const live = i === reached;
    ctx.save();
    ctx.globalAlpha = clamp(p * 1.6);
    const pop = ease.outBack(p) * (live ? 1.12 : 1);
    ctx.translate(x, y);
    ctx.scale(pop, pop);
    ctx.beginPath();
    ctx.arc(0, 0, 74, 0, Math.PI * 2);
    ctx.fillStyle = on ? UI.ink : UI.window;
    ctx.fill();
    ctx.lineWidth = live ? 9 : 5;
    ctx.strokeStyle = live ? UI.red : UI.ink;
    ctx.stroke();
    text(ctx, String(i + 1), 0, 18, {
      size: 54, weight: 700, color: on ? UI.gold : UI.ink, align: 'center',
    });
    text(ctx, step, 0, 150, {
      size: 44, weight: 700, family: 'Inter', color: UI.ink, align: 'center', tracking: 2,
    });
    ctx.restore();
  });

  // the pulse travelling the rail, so the loop reads as a loop
  const travel = ((local * 0.42) % 1);
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

  // The card for the step being described, in alternating slots: a large dark
  // block that moves across the frame is a new picture, the same block with new
  // words on it is not.
  if (current >= 0 && local < b[4] + 0.2) {
    const beat = beats[current];
    const cp = clamp(span(local, beat[0], beat[0] + 0.4));
    const slotX = current % 2 === 0 ? 240 : W - 2240;
    ctx.save();
    ctx.globalAlpha = cp;
    ctx.translate(0, (1 - ease.outCubic(cp)) * 90);
    panel(ctx, { x: slotX, y: 1160, w: 2000, h: 300, r: 22, fill: UI.ink, stroke: null });
    ctx.fillStyle = current === 5 ? UI.gold : UI.red;
    ctx.fillRect(slotX, 1160, 22, 300);
    text(ctx, beat[2], slotX + 80, 1290, {
      size: 64, weight: 700, family: 'Space Grotesk', color: UI.white, maxWidth: 1820,
    });
    text(ctx, beat[3], slotX + 80, 1382, { size: 34, weight: 400, color: '#B9B9C4', maxWidth: 1820 });
    ctx.restore();
  }

  // "then you go again": the loop turns over
  const again = clamp(span(local, b[4] + 0.3, b[4] + 0.8));
  if (again > 0) {
    ctx.save();
    ctx.globalAlpha = again;
    panel(ctx, { x: 240, y: 1160, w: W - 480, h: 300, r: 22, fill: UI.ink, stroke: null });
    ctx.fillStyle = UI.gold;
    ctx.fillRect(240, 1160, 22, 300);
    text(ctx, 'AND THEN AGAIN', 320, 1300, {
      size: 78, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    text(ctx, 'One small step further, every time.', 320, 1392, {
      size: 36, weight: 400, color: '#B9B9C4',
    });
    ctx.restore();
  }

  // "six parts. Prompt, plan, branch, diff, checks, merge." - the list, whole
  const all = clamp(span(local, b[5] + 0.3, b[5] + 0.8));
  if (all > 0) {
    ctx.save();
    ctx.globalAlpha = all;
    panel(ctx, { x: 240, y: 1160, w: W - 480, h: 300, r: 22, fill: UI.white, stroke: UI.ink });
    text(ctx, 'PROMPT · PLAN · BRANCH · DIFF · CHECKS · MERGE', 320, 1300, {
      size: 62, weight: 700, family: 'Space Grotesk', color: UI.ink,
    });
    ctx.fillStyle = UI.red;
    ctx.fillRect(320, 1360, 900 * ease.outCubic(all), 12);
    ctx.restore();
  }

  // "every step in this video is one turn of that loop"
  const close = clamp(span(local, b[6] + 0.3, b[6] + 0.8));
  if (close > 0) {
    ctx.save();
    ctx.globalAlpha = close;
    text(ctx, 'EVERY STEP IN THIS VIDEO', 240, 1300, {
      size: 96, weight: 700, family: 'Space Grotesk', color: UI.ink,
    });
    text(ctx, 'IS ONE TURN OF IT.', 240, 1410, {
      size: 96, weight: 700, family: 'Space Grotesk', color: UI.red,
    });
    ctx.restore();
  }
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

/**
 * Where in a spoken line a phrase is said, as a local time.
 *
 * The narration gives the scene its beats, and inside one sentence there are
 * four things named in order - the file list, the commit history, the branches,
 * the About panel. Timing those by hand means re-timing them every time the
 * voice changes, so the phrase position in the text is used instead: speech runs
 * at a roughly even rate, and the phrase is a good estimate of the moment.
 */
function phraseAt(scene, lineIndex, phrase, fallback) {
  const line = scene.lines[lineIndex];
  if (!line) return fallback;
  const spoken = String(line.spoken || '');
  const at = spoken.toLowerCase().indexOf(phrase.toLowerCase());
  const length = line.end - line.start;
  if (at < 0 || !length) return line.start - scene.start + fallback;
  return line.start - scene.start + (at / Math.max(1, spoken.length)) * length;
}

function drawGithub(ctx, scene, t, local) {
  stageField(ctx, t);
  // Every beat here is tied to the line that speaks it. It used to be tied to a
  // stopwatch, and the two disagreed badly: the narration spends thirty-six
  // seconds describing how to create a repository while the picture showed the
  // finished page after five, so half a minute of words pointed at nothing. The
  // composition check put a number on it - one arrangement held 46 seconds.
  //
  // The scene is now the three screens the words ask for, in their order: an
  // empty profile, the create form, the finished page. On the page the callout
  // travels to the part being named instead of printing one black panel in the
  // same corner. Measured, those panels score 0.94 to 0.99 against each other,
  // so nine of them were one picture with changing words.
  const b = scene.lines.map((line) => line.start - scene.start);
  const at = (i, offset = 0) => (b[i] ?? i * 5) + offset;

  const headline = span(local, 0.15, 1.1);
  text(ctx, scene.title, 240, 330, {
    size: 108, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(headline * 1.6),
  });
  rule(ctx, 244, 372, 700, { progress: ease.outCubic(headline), colour: UI.red, thickness: 8 });

  const box = { x: 240, y: 470, w: W - 480, h: 1440 };
  const formIn = at(2, 1.2);   // "press New repository, in the top right corner"
  const pageIn = at(7, 2.2);   // "press Create repository"

  // A pointer is a card and a line to the thing it names. The card is the part
  // that carries: measured on a 16x9 thumbnail, an outlined target moves too few
  // blocks to register as a new picture, while a filled card is a fifth of the
  // frame. So each beat puts a card in a different slot and draws a connector to
  // the row it is talking about - the position changes, which is what makes it a
  // new arrangement, and the line is what keeps it a pointer rather than a label.
  const point = (rect, label, start, slot, colour = UI.gold) => {
    const p = span(local, start, start + 0.36);
    if (p <= 0) return;
    const a = ease.outCubic(clamp(p));
    ctx.save();
    const grow = 22 * (1 - a);
    roundRect(ctx, rect.x - grow, rect.y - grow, rect.w + grow * 2, rect.h + grow * 2, 16);
    ctx.fillStyle = colour;
    ctx.globalAlpha = a * 0.16;
    ctx.fill();
    ctx.globalAlpha = a;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 8;
    ctx.stroke();
    // the connector, from the card's near edge to the middle of the target
    const cx = slot.x + (slot.x > rect.x ? 0 : 1120);
    const cy = slot.y + 120;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    const ty = rect.y + rect.h / 2;
    ctx.lineTo(rect.x + rect.w / 2, ty);
    ctx.strokeStyle = colour;
    ctx.lineWidth = 5;
    ctx.globalAlpha = a * 0.7;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(rect.x + rect.w / 2, ty, 12, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.globalAlpha = a;
    ctx.fill();
    ctx.globalAlpha = a;
    panel(ctx, { x: slot.x, y: slot.y, w: 1120, h: 240, r: 20, fill: UI.ink, stroke: null });
    ctx.fillStyle = colour;
    ctx.fillRect(slot.x, slot.y, 20, 240);
    text(ctx, label, slot.x + 70, slot.y + 150, {
      size: 50, weight: 700, family: 'Space Grotesk', color: UI.white, maxWidth: 1000,
    });
    ctx.restore();
  };

  if (local < formIn + 0.5) {
    // Screen one: an account with nothing in it, and one button.
    const a = clamp(span(local, 0.2, 1.0));
    const content = githubChrome(ctx, 'github.com', 'GitHub', box.x, box.y, box.w, box.h, a);
    const { x, y, w } = content;
    text(ctx, 'octocat-ana', x + 60, y + 120, {
      size: 52, weight: 700, color: UI.text, alpha: clamp(span(local, 0.8, 1.4)),
    });
    const btn = { x: x + w - 640, y: y + 56, w: 580, h: 96 };
    panel(ctx, { ...btn, r: 16, fill: UI.ink, stroke: null, alpha: clamp(span(local, 1.0, 1.6)) });
    text(ctx, 'New repository', btn.x + btn.w / 2, btn.y + 62, {
      size: 36, weight: 700, color: UI.white, align: 'center', alpha: clamp(span(local, 1.0, 1.6)),
    });
    const empty = { x: x + 60, y: y + 260, w: w - 120, h: 800 };
    panel(ctx, { ...empty, r: 20, fill: UI.window2, stroke: UI.line, alpha: clamp(span(local, 2.4, 3.2)) });
    text(ctx, 'No repositories yet', empty.x + empty.w / 2, empty.y + 360, {
      size: 56, weight: 700, color: UI.dim, align: 'center', alpha: clamp(span(local, 3.4, 4.2)),
    });
    text(ctx, 'The repository is the whole workspace.', empty.x + empty.w / 2, empty.y + 444, {
      size: 34, weight: 400, color: UI.faint, align: 'center', alpha: clamp(span(local, 5.6, 6.4)),
    });
    // The line about signing up and confirming the address had nothing to show.
    // A card that lands, then takes a tick, is the change that line needs.
    const cardAt = at(1, 0.9);
    const cp = clamp(span(local, cardAt, cardAt + 0.4));
    if (cp > 0) {
      const cw = 1160;
      const cx0 = x + w - cw - 80;
      const cy0 = y + 700 + (1 - ease.outCubic(cp)) * 90;
      ctx.save();
      ctx.globalAlpha = cp;
      panel(ctx, { x: cx0, y: cy0, w: cw, h: 340, r: 22, fill: UI.ink, stroke: null });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(cx0, cy0, 20, 340);
      text(ctx, 'CONFIRM YOUR EMAIL', cx0 + 66, cy0 + 120, {
        size: 52, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      text(ctx, 'One click. Then the account exists.', cx0 + 66, cy0 + 196, {
        size: 32, weight: 400, color: '#B9B9C4',
      });
      const ticked = clamp(span(local, cardAt + 2.6, cardAt + 3.0));
      ctx.beginPath();
      ctx.arc(cx0 + cw - 130, cy0 + 170, 62, 0, Math.PI * 2);
      ctx.strokeStyle = ticked > 0 ? UI.gold : '#4A4A54';
      ctx.lineWidth = 6;
      ctx.stroke();
      if (ticked > 0) {
        ctx.strokeStyle = UI.gold;
        ctx.lineWidth = 10;
        ctx.beginPath();
        ctx.moveTo(cx0 + cw - 158, cy0 + 170);
        ctx.lineTo(cx0 + cw - 136, cy0 + 194);
        ctx.lineTo(cx0 + cw - 100, cy0 + 146);
        ctx.stroke();
      }
      ctx.restore();
    }
    // The pointer is the beat for the line that says the button is in the top
    // right corner, and pressing it is what puts the form on screen.
    const move = ease.inOutCubic(span(local, at(2, -0.8), at(2, 0.4)));
    cursor(ctx, lerp(x + w * 0.5, btn.x + btn.w / 2, move), lerp(y + 700, btn.y + 50, move), {
      press: span(local, at(2, 0.45), at(2, 0.65)),
      alpha: clamp(span(local, at(2, -1.1), at(2, -0.5))),
    });
    clickRing(ctx, btn.x + btn.w / 2, btn.y + 50, span(local, at(2, 0.5), at(2, 1.1)));
    return;
  }

  if (local < pageIn + 0.4) {
    // Screen two: the form, filled in at the speed of the sentences that
    // describe filling it in.
    const a = clamp(span(local, formIn, formIn + 0.5));
    const content = githubChrome(ctx, 'github.com/new', 'New repository', box.x, box.y, box.w, box.h, a);
    const { x, y, w } = content;
    panel(ctx, { x: x + 60, y: y + 60, w: w - 120, h: 1240, r: 20, fill: UI.window2, stroke: UI.line });
    text(ctx, 'Create a new repository', x + 120, y + 200, { size: 62, weight: 700, color: UI.text });
    text(ctx, 'Repository name', x + 120, y + 322, { size: 34, weight: 600, color: UI.dim });

    const field = { x: x + 120, y: y + 352, w: 1300, h: 100 };
    panel(ctx, { ...field, r: 12, fill: UI.white, stroke: UI.line });
    const typed = 'book-list'.slice(0, Math.max(0, Math.floor((local - at(3, 0.25)) * 2.6)));
    text(ctx, typed, field.x + 36, field.y + 66, { size: 44, weight: 500, color: UI.text });
    if (local > at(3, 0.25) && typed.length < 9 && Math.floor(local * 3) % 2 === 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(field.x + 40 + measure(ctx, typed, { size: 44, weight: 500 }), field.y + 24, 5, 54);
    }

    [['Public', at(4, 0.4), 'Anyone can see it, and it gets free checks.'],
      ['Private', at(5, 0.4), 'Only people you invite can see it.']].forEach(([name, start, detail], i) => {
      const ry = y + 588 + i * 150;
      const on = local > start;
      ctx.beginPath();
      ctx.arc(x + 156, ry + 30, 21, 0, Math.PI * 2);
      ctx.lineWidth = on ? 6 : 4;
      ctx.strokeStyle = on ? UI.ink : UI.faint;
      ctx.stroke();
      if (on) {
        ctx.beginPath();
        ctx.arc(x + 156, ry + 30, 11, 0, Math.PI * 2);
        ctx.fillStyle = UI.ink;
        ctx.fill();
      }
      text(ctx, name, x + 210, ry + 42, { size: 42, weight: 600, color: UI.text });
      text(ctx, detail, x + 210, ry + 96, { size: 30, weight: 400, color: UI.dim });
    });

    const tick = clamp(span(local, at(6, 0.9), at(6, 1.3)));
    roundRect(ctx, x + 140, y + 908, 38, 38, 7);
    ctx.strokeStyle = UI.dim;
    ctx.lineWidth = 4;
    ctx.stroke();
    if (tick > 0) {
      ctx.save();
      ctx.globalAlpha = tick;
      ctx.strokeStyle = UI.ink;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(x + 149, y + 928);
      ctx.lineTo(x + 158, y + 939);
      ctx.lineTo(x + 177, y + 915);
      ctx.stroke();
      ctx.restore();
    }
    text(ctx, 'Add a README file', x + 206, y + 940, { size: 38, weight: 500, color: UI.text });

    const bp = clamp(span(local, at(6, 2.4), at(6, 3.0)));
    panel(ctx, { x: x + 140, y: y + 1030, w: 520, h: 100, r: 14, fill: bp > 0.5 ? UI.ink : '#8A8A94', stroke: null });
    text(ctx, 'Create repository', x + 400, y + 1094, {
      size: 36, weight: 700, color: UI.white, align: 'center',
    });

    // One pointer at a time, each on the row its sentence names.
    if (local >= at(7, 0.9)) {
      point({ x: x + 130, y: y + 1018, w: 540, h: 124 }, 'THEN PRESS THIS', at(7, 0.9),
        { x: x + 1500, y: y + 300 }, UI.red);
      cursor(ctx, x + 400, y + 1080, { press: span(local, at(7, 1.5), at(7, 1.75)), alpha: clamp(span(local, at(7, 0.4), at(7, 0.9))) });
      clickRing(ctx, x + 400, y + 1080, span(local, at(7, 1.6), at(7, 2.2)));
    } else if (local >= at(6, 0.9)) {
      point({ x: x + 128, y: y + 896, w: 700, h: 70 }, 'ONE TICK, ONE FILE',
        at(6, 0.9), { x: x + 1500, y: y + 940 });
    } else if (local >= at(5, 0.4)) {
      point({ x: x + 130, y: y + 716, w: 980, h: 130 }, 'PRIVATE: NOT READY YET',
        at(5, 0.4), { x: x + 1500, y: y + 620 });
    } else if (local >= at(4, 0.4)) {
      point({ x: x + 130, y: y + 566, w: 980, h: 130 }, 'PUBLIC: FREE CHECKS',
        at(4, 0.4), { x: x + 1500, y: y + 300 });
    } else if (local >= at(3, 0.3)) {
      point({ x: x + 120, y: y + 340, w: 1300, h: 124 }, 'LOWER CASE, WITH HYPHENS',
        at(3, 0.3), { x: x + 1500, y: y + 300 });
    }
    return;
  }

  // Screen three: the finished repository, and a pointer that walks to each
  // part as the narration names it.
  const a = clamp(span(local, pageIn, pageIn + 0.6));
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list', 'book-list', box.x, box.y, box.w, box.h, a);
  repoPage(ctx, content, {
    t, reveal: clamp(span(local, pageIn, pageIn + 1.0)),
    files: ['README.md', 'books.json', 'index.html', 'style.css'],
  });
  const { x, y, w } = content;
  const table = { x: x + 60, y: y + 420, w: w * 0.62, h: 470 };
  const commits = { x: x + 60, y: y + 420, w: w * 0.62, h: 90 };
  const branches = { x: x + 60, y: y + 300, w: 420, h: 72 };
  const about = { x: x + w * 0.66, y: y + 420, w: w * 0.32, h: 300 };
  const tabs = { x: x + 60, y: y + 196, w: 1200, h: 90 };

  // Line 8 promises four parts; line 9 names them in order, so the pointer
  // lands in the order the words do.
  const slotA = { x: x + 60, y: y + 1000 };
  const slotB = { x: x + w - 1180, y: y + 1000 };
  const slotC = { x: x + 60, y: y + 640 };
  const slotD = { x: x + w - 1180, y: y + 640 };
  if (local >= at(10, 0.25)) {
    point(tabs, 'THE ACTIONS TAB: THE CHECKS', at(10, 0.25), slotA, UI.red);
  } else if (local >= phraseAt(scene, 9, 'About', at(9, 4.0))) {
    point(about, 'AND THE ABOUT PANEL', phraseAt(scene, 9, 'About', at(9, 4.0)), slotC);
  } else if (local >= phraseAt(scene, 9, 'branches', at(9, 2.6))) {
    point(branches, 'THE BRANCHES', phraseAt(scene, 9, 'branches', at(9, 2.6)), slotB);
  } else if (local >= phraseAt(scene, 9, 'commit history', at(9, 1.2))) {
    point(commits, 'THE COMMIT HISTORY', phraseAt(scene, 9, 'commit history', at(9, 1.2)), slotA);
  } else if (local >= at(9, 0.1)) {
    point(table, 'THE FILE LIST', at(9, 0.1), slotD);
  } else if (local >= at(8, 0.3)) {
    point(table, 'FOUR PARTS, EVERY DAY', at(8, 0.3), slotC);
  }

  // The closing sentence gets the floor, not a corner.
  const end = span(local, at(11, 1.0), at(11, 1.5));
  if (end > 0) {
    const slide = ease.outCubic(clamp(end));
    ctx.save();
    ctx.globalAlpha = clamp(end * 2);
    panel(ctx, {
      x: 240, y: y + 1180 + (1 - slide) * 120, w: W - 480, h: 200, r: 20,
      fill: UI.ink, stroke: UI.ink,
    });
    ctx.fillStyle = UI.red;
    ctx.fillRect(240, y + 1180 + (1 - slide) * 120, 24, 200);
    text(ctx, 'THE REST IS CONVERSATION', 330, y + 1308 + (1 - slide) * 120, {
      size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    ctx.restore();
  }
}

// ------------------------------------------------------------------ connect
function drawConnect(ctx, scene, t, local) {
  stageField(ctx, t);
  const cb = scene.lines.map((line) => line.start - scene.start);
  const lat = (i, offset = 0) => (cb[i] ?? i * 5) + offset;
  text(ctx, scene.title, W / 2, 330, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, align: 'center',
    alpha: clamp(span(local, 0.15, 1.0) * 1.6),
  });

  // Two panels for the first six lines, one conversation for the last four, and
  // every beat on the sentence that asks for it. This scene used to draw its
  // whole picture in the first six seconds and hold for thirty-three, because
  // everything in it was timed from the top of the scene rather than from the
  // narration.
  const conversation = lat(6, 0.2);
  if (local < conversation) {
    const left = { x: 300, y: 500, w: 1500, h: 1200 };
    const right = { x: 2040, y: 500, w: 1500, h: 1200 };

    const lp = clamp(span(local, 0.3, 1.1));
    panel(ctx, { ...left, r: 28, fill: '#141418', stroke: '#2A2A31', alpha: lp, shadow: 0.6 });
    ctx.save();
    ctx.globalAlpha = lp;
    text(ctx, 'ARENA', left.x + 60, left.y + 86, { size: 38, weight: 700, color: UI.gold, tracking: 8 });
    text(ctx, 'Connect GitHub', left.x + 60, left.y + 210, { size: 62, weight: 700, color: UI.white, family: 'Space Grotesk' });
    text(ctx, 'One authorisation, then the agent', left.x + 60, left.y + 282, { size: 34, weight: 400, color: '#9A9AA5' });
    text(ctx, 'works inside your repositories.', left.x + 60, left.y + 326, { size: 34, weight: 400, color: '#9A9AA5' });

    // "open the GitHub connection, and approve the sign in"
    const bp = clamp(span(local, lat(1, 0.1), lat(1, 0.6)));
    panel(ctx, { x: left.x + 60, y: left.y + 400, w: 520, h: 100, r: 14, fill: bp > 0 ? UI.gold : '#3A3A42', stroke: null, alpha: bp });
    text(ctx, 'Authorise GitHub', left.x + 320, left.y + 464, {
      size: 36, weight: 700, color: UI.ink, align: 'center', alpha: bp,
    });
    cursor(ctx, lerp(left.x + 700, left.x + 380, ease.inOutCubic(span(local, lat(1, -0.5), lat(1, 0.2)))),
      left.y + 450, { press: span(local, lat(1, 0.2), lat(1, 0.4)), alpha: clamp(span(local, lat(1, -1.0), lat(1, -0.6))) });
    clickRing(ctx, left.x + 380, left.y + 450, span(local, lat(1, 0.25), lat(1, 0.75)));

    // "then choose which repositories the agent may touch"
    const dp = clamp(span(local, lat(2, -0.1), lat(2, 0.5)));
    if (dp > 0) {
      // A light modal on the dark panel, because the appearance of the screen is
      // the beat: dark-on-dark moved too little to read as a new picture, and
      // the scene held one arrangement for eleven seconds there.
      panel(ctx, { x: left.x + 60, y: left.y + 560, w: left.w - 120, h: 520, r: 20, fill: UI.white, stroke: UI.ink, alpha: dp });
      text(ctx, 'Choose repositories', left.x + 120, left.y + 650, { size: 46, weight: 700, color: UI.text, alpha: dp });
      ['book-list', 'portfolio', 'scratch'].forEach((name, i) => {
        const on = i === 0;
        // "start with one" - the other two are there and stay unticked
        const rp = clamp(span(local, lat(2, 0.3 + i * 0.2), lat(2, 0.7 + i * 0.2))) * dp;
        roundRect(ctx, left.x + 120, left.y + 700 + i * 96, 40, 40, 8);
        ctx.strokeStyle = UI.dim;
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
          size: 38, weight: 500, color: i === 0 ? UI.ink : UI.dim, alpha: rp,
        });
        // "start with one" lands as a pointer on the one ticked
        if (on && local > lat(3, 0.2)) {
          ctx.save();
          ctx.globalAlpha = clamp(span(local, lat(3, 0.2), lat(3, 0.5)));
          ctx.strokeStyle = UI.gold;
          ctx.lineWidth = 5;
          roundRect(ctx, left.x + 104, left.y + 684, left.w - 208, 76, 12);
          ctx.stroke();
          ctx.restore();
        }
      });
    }
    ctx.restore();

    const cp = clamp(span(local, lat(2, 1.0), lat(2, 2.0)));
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

    const rp2 = clamp(span(local, lat(1, 0.2), lat(1, 0.9)));
    panel(ctx, { ...right, r: 28, fill: UI.window, stroke: UI.line, alpha: rp2, shadow: 0.5 });
    ctx.save();
    ctx.globalAlpha = rp2;
    text(ctx, 'GITHUB', right.x + 60, right.y + 86, { size: 38, weight: 700, color: UI.dim, tracking: 8 });
    text(ctx, 'octocat-ana / book-list', right.x + 60, right.y + 210, {
      size: 56, weight: 700, color: UI.text, family: 'Space Grotesk',
    });
    chip(ctx, 'CONNECTED', { x: right.x + 60, y: right.y + 260, colour: UI.ink, fill: '#DFF3E6', size: 28 });
    // "read that permission screen properly": the three powers, one per beat
    ['read the files', 'write a branch', 'open a pull request'].forEach((value, i) => {
      const p = clamp(span(local, lat(4, 0.3 + i * 0.55), lat(4, 0.8 + i * 0.55)));
      if (p <= 0) return;
      ctx.save();
      ctx.globalAlpha = p * rp2;
      ctx.beginPath();
      ctx.arc(right.x + 84, right.y + 430 + i * 110, 20, 0, Math.PI * 2);
      ctx.fillStyle = i === 1 ? UI.red : UI.ink;
      ctx.fill();
      text(ctx, value, right.x + 130, right.y + 444 + i * 110, { size: 40, weight: 500, color: UI.text });
      ctx.restore();
    });
    ctx.restore();

    // "a useful helper and a very fast hazard" - the difference, as a band
    const bandAt = lat(5, 0.9);
    const p = span(local, bandAt, bandAt + 1.0);
    if (p > 0) {
      const ex = ease.outCubic(clamp(p * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, bandAt + 1.2, bandAt + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'USEFUL, NOT JUST FAST', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
    return;
  }

  // "now open your repository in Arena, and start a conversation": the two
  // panels become the one window the rest of the scene is about.
  const apart = ease.outCubic(clamp(span(local, conversation, conversation + 0.6)));
  const conv = { x: 300, y: 480, w: 3240, h: 1180 + (1 - apart) * 60 };
  panel(ctx, { ...conv, r: 28, fill: '#141418', stroke: '#2A2A31', shadow: 0.6 });
  ctx.save();
  ctx.globalAlpha = apart;
  text(ctx, 'ARENA', conv.x + 70, conv.y + 90, { size: 34, weight: 700, color: UI.gold, tracking: 8 });
  // "your repository name sits at the top of the conversation" - and it stays
  // there, highlighted on the line that tells you to check it every time.
  const nameBox = { x: conv.x + 70, y: conv.y + 130, w: 900, h: 120 };
  const checked = clamp(span(local, lat(8, 0.2), lat(8, 0.6)));
  const alarm = clamp(span(local, lat(9, 0.2), lat(9, 0.6)));
  panel(ctx, {
    x: nameBox.x, y: nameBox.y, w: nameBox.w, h: nameBox.h, r: 16,
    fill: alarm > 0.5 ? UI.red : UI.window2, stroke: UI.ink,
  });
  text(ctx, 'octocat-ana / book-list', nameBox.x + 40, nameBox.y + 78, {
    size: 46, weight: 700, family: 'Space Grotesk', color: alarm > 0.5 ? UI.white : UI.text,
  });
  if (checked > 0) {
    ctx.save();
    ctx.globalAlpha = checked;
    ctx.fillStyle = UI.gold;
    ctx.fillRect(nameBox.x, nameBox.y + nameBox.h + 14, nameBox.w * checked, 10);
    ctx.restore();
  }

  // the conversation itself, one message per capability the agent has
  const msgs = [
    ['You', 'Add a search box to the list.', lat(6, 0.6)],
    ['Agent', 'I can see the files, the history and the branch.', lat(7, 0.3)],
  ];
  msgs.forEach(([who, value, start], i) => {
    const mp = clamp(span(local, start, start + 0.5));
    if (mp <= 0) return;
    const my = conv.y + 340 + i * 260;
    ctx.save();
    ctx.globalAlpha = mp * apart;
    ctx.translate((1 - ease.outCubic(mp)) * 120, 0);
    panel(ctx, {
      x: conv.x + 70 + i * 180, y: my, w: 2100, h: 190, r: 18,
      fill: i === 0 ? UI.white : '#242430', stroke: i === 0 ? UI.line : '#33333D',
    });
    text(ctx, who.toUpperCase(), conv.x + 110 + i * 180, my + 60, {
      size: 26, weight: 700, color: i === 0 ? UI.faint : UI.gold, tracking: 4,
    });
    text(ctx, value, conv.x + 110 + i * 180, my + 128, {
      size: 38, weight: 500, color: i === 0 ? UI.text : '#E4E4EA', maxWidth: 1900,
    });
    ctx.restore();
  });

  // "the agent can see the files, the history, and the branch": three chips,
  // because the sentence lists three things
  ['THE FILES', 'THE HISTORY', 'THE BRANCH'].forEach((label, i) => {
    const cp2 = clamp(span(local, lat(7, 0.9 + i * 0.6), lat(7, 1.4 + i * 0.6)));
    if (cp2 <= 0) return;
    chip(ctx, label, {
      x: conv.x + 70 + i * 620, y: conv.y + 880,
      colour: UI.white, fill: i === 2 ? UI.red : UI.ink, size: 30, alpha: cp2 * apart,
    });
  });

  // "check it every single time. Wrong repository is the most expensive easy
  // mistake." - the mistake, named, while the name above turns red.
  const warnAt = lat(9, 0.5);
  const wp = clamp(span(local, warnAt, warnAt + 0.5));
  if (wp > 0) {
    ctx.save();
    ctx.globalAlpha = wp * apart;
    ctx.translate(0, (1 - ease.outCubic(wp)) * 200);
    panel(ctx, { x: conv.x + 70, y: conv.y + 980, w: conv.w - 140, h: 150, r: 18, fill: UI.red, stroke: null });
    text(ctx, 'WRONG REPOSITORY IS THE EXPENSIVE MISTAKE', conv.x + 130, conv.y + 1078, {
      size: 54, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    ctx.restore();
  }
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

/**
 * How much of the prompt is typed, per line of the prompt.
 *
 * The typing rides the lines that speak it - one prompt line per spoken line -
 * not a fixed five seconds at the top of the scene. A slow read types slowly.
 */
function promptTypedCount(local, scene) {
  const beat = (line) => (line ? line.start - scene.start : 99);
  const over = (line) => (line ? line.end - scene.start : 99);
  let used = 0;
  const counts = [];
  PROMPT_TEXT.forEach((line, i) => {
    const spoken = scene.lines[5 + i];
    const at = beat(spoken) + 0.2;
    const to = Math.max(at + 0.8, over(spoken) - 0.2);
    const p = span(local, at, to);
    counts.push(used + Math.floor(line.length * p));
    used += line.length;
  });
  return counts;
}

function drawPrompt(ctx, scene, t, local) {
  stageField(ctx, t);
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  text(ctx, scene.title, 240, 320, {
    size: 96, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });
  // The title takes a second beat on its own line: a bar of weight under it.
  {
    // Constant rate on purpose: this is a readout filling, not an entrance,
    // and an eased growth collapses into a sub-threshold crawl within a third
    // of a second. Constant, it moves twelve blocks of picture every half
    // second for as long as it grows.
    const p = clamp(span(local, (b[0] ?? 0) + 3.0, (b[0] ?? 0) + 4.3));
    if (p > 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(240, 340, 1500 * p, 220);
    }
  }

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
  const counts = promptTypedCount(local, scene);
  let used = 0;
  PROMPT_TEXT.forEach((line, i) => {
    const count = counts[i];
    const typed = count - used;
    used += line.length;
    if (typed <= 0) return;
    const slice = line.slice(0, typed);
    const full = measure(ctx, line, { size: 44, weight: 500 });
    // a bar of ink growing under the words as they are typed. Individual
    // characters move nothing measurable at delivery scale; the bar is what
    // carries the typing.
    ctx.fillStyle = 'rgba(242,194,48,0.55)';
    ctx.fillRect(box.x + 110, compY + 56 + i * 84, (full * typed) / line.length, 62);
    text(ctx, slice, box.x + 120, compY + 100 + i * 84, { size: 44, weight: 500, color: UI.text });
    if (typed < line.length) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(box.x + 120 + measure(ctx, slice, { size: 44, weight: 500 }), compY + 62, 4, 48);
    }
  });

  // Annotations for the parts of the prompt, each on the line that names it.
  // They swap places in one slot as slab-sized marks: a 26-pixel chip moves
  // two blocks of picture and reads as a freeze however briskly it fades.
  const notes = [
    ['WHAT IT IS', 2, 0.5], ['WHAT IT MAKES', 2, 2.0], ['WHAT DONE LOOKS LIKE', 2, 3.5],
    ['THE CONSTRAINT', 3, 0.5], ['THE NAMES', 3, 2.6], ['THE REASONS', 3, 4.7],
  ];
  notes.forEach(([label, lineAt, offset], i) => {
    const at = (b[lineAt] ?? 8) + offset;
    const np = span(local, at, at + 0.5);
    // The old slab clears out BEFORE the new one enters. They used to cross
    // in the same slot - two identical red slabs overlapping produce almost
    // no change in the picture, which measured as a 0.9 s freeze exactly at
    // the swap.
    // The last one has no successor to hand over to, so it used to stay on
    // screen for the remaining forty seconds - and the "here is one that works"
    // slab landed in the same place on top of it, which is why that stretch read
    // as one held picture. It leaves when the prompt itself arrives.
    const leaveAt = i < notes.length - 1
      ? (b[notes[i + 1][1]] ?? 12) + notes[i + 1][2] - 0.55
      : (b[4] ?? 20) - 0.1;
    const leave = ease.outCubic(clamp(span(local, leaveAt, leaveAt + 0.4)));
    if (np <= 0 || leave >= 1) return;
    const ex = ease.outCubic(clamp(np * 1.2));
    // Every note takes a punch a second after it lands. The swaps cover the
    // gaps between notes; the last note has no swap behind it, and its landing
    // alone is a block under the threshold - its punch is the second beat.
    const punch = Math.sin(Math.PI * clamp(span(local, at + 1.0, at + 1.5))) * 120;
    ctx.save();
    ctx.globalAlpha = clamp(np * 4) * (1 - leave);
    ctx.translate((1 - ex) * 600 - leave * 900, punch);
    panel(ctx, {
      x: box.x + box.w - 1400, y: compY + 500, w: 1500, h: 240, r: 18,
      fill: UI.red, stroke: UI.red,
    });
    text(ctx, label, box.x + box.w - 1300, compY + 655, {
      size: 54, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    ctx.restore();
  });

  // One card per sentence of the prompt, landing as that sentence is typed.
  // The composer alone was not enough: five sentences typed into one panel is a
  // slow fill, and measured it let a single arrangement sit for thirty-four
  // seconds. Each card is a block of picture that was not there before, and the
  // column reads as the anatomy of a good prompt by the end.
  {
    const parts = [
      ['01  IT NAMES THE THING', 'One page. Books. Yours.'],
      ['02  IT NAMES THE DATA', 'books.json, one card per book.'],
      ['03  IT NAMES THE CONSTRAINT', 'Plain HTML, CSS, JavaScript.'],
      ['04  IT ASKS FOR THE README', 'So the next session can start.'],
      ['05  IT SETS THE SCOPE CUT', 'No database. Not yet.'],
    ];
    parts.forEach(([label, detail], i) => {
      const start = (b[5 + i] ?? 24 + i * 5) + 0.35;
      const cp = clamp(span(local, start, start + 0.45));
      if (cp <= 0) return;
      const cy = 500 + i * 232;
      ctx.save();
      ctx.globalAlpha = cp;
      ctx.translate((1 - ease.outCubic(cp)) * 140, 0);
      panel(ctx, { x: 2580, y: cy, w: 1020, h: 205, r: 18, fill: UI.ink, stroke: null });
      ctx.fillStyle = i === 4 ? UI.gold : UI.red;
      ctx.fillRect(2580, cy, 18, 205);
      text(ctx, label, 2636, cy + 92, {
        size: 40, weight: 700, family: 'Space Grotesk', color: UI.white, maxWidth: 940,
      });
      text(ctx, detail, 2636, cy + 154, { size: 28, weight: 400, color: '#B9B9C4', maxWidth: 940 });
      ctx.restore();
    });
  }

  // cursor to send, and the press, on the line that says "send it"
  const sendAt = (b[11] ?? 48) + 0.25;
  const mx = lerp(box.x + 1900, box.x + box.w - 230, ease.inOutCubic(span(local, sendAt - 0.8, sendAt - 0.1)));
  const my = lerp(compY + 900, compY + 706, ease.inOutCubic(span(local, sendAt - 0.8, sendAt - 0.1)));
  cursor(ctx, mx, my, { press: span(local, sendAt - 0.1, sendAt + 0.1), alpha: clamp(span(local, sendAt - 1.2, sendAt - 0.6)) });
  clickRing(ctx, box.x + box.w - 230, compY + 706, span(local, sendAt - 0.1, sendAt + 0.4));

  // "here is a prompt that works" - the slab of the line, sliding in
  {
    const at = (b[4] ?? 20) - 0.2;
    const p2 = span(local, at, at + 1.0);
    if (p2 > 0) {
      const ex = ease.outCubic(p2);
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.65)));
      ctx.save();
      ctx.globalAlpha = clamp(p2 * 4);
      ctx.translate((1 - ex) * -600, punch * 80);
      panel(ctx, { x: box.x + 60, y: compY + 460, w: 1500, h: 200, r: 18, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(box.x + 60, compY + 460, 20, 200);
      text(ctx, 'HERE IS ONE THAT WORKS', box.x + 130, compY + 595, {
        size: 58, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // "that last sentence matters" - the scope-cut mark on the last line
  {
    const at = (b[10] ?? 44) + 0.3;
    const p2 = span(local, at, at + 0.55);
    if (p2 > 0) {
      const ex = ease.outCubic(clamp(p2 * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.0, at + 1.45)));
      ctx.save();
      ctx.globalAlpha = clamp(p2 * 4);
      ctx.translate((1 - ex) * -600, punch * 90);
      panel(ctx, { x: box.x + 60, y: compY + 620, w: 1700, h: 150, r: 14, fill: UI.red, stroke: UI.red });
      text(ctx, 'THE SCOPE CUT MATTERS', box.x + 130, compY + 722, {
        size: 54, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // "send it, then read the plan": the SENT stamp and the plan slab
  {
    const sentAt = (b[11] ?? 48) + 0.25;
    const sp = span(local, sentAt, sentAt + 0.5);
    if (sp > 0) {
      const ex = ease.outCubic(clamp(sp * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, sentAt + 1.0, sentAt + 1.4)));
      ctx.save();
      ctx.globalAlpha = clamp(sp * 4);
      ctx.translate((1 - ex) * -250, punch * 100);
      panel(ctx, { x: W / 2 - 800, y: 1480, w: 1600, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(W / 2 - 800, 1480, 22, 240);
      text(ctx, 'SENT', W / 2 - 720, 1645, {
        size: 110, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
    const planAt = (b[12] ?? 52) + 0.3;
    const pp = span(local, planAt, planAt + 0.6);
    if (pp > 0) {
      const ex = ease.outCubic(clamp(pp * 1.2));
      ctx.save();
      ctx.globalAlpha = clamp(pp * 4);
      ctx.translate(0, (1 - ex) * 600);
      panel(ctx, { x: W / 2 - 1300, y: 1500, w: 2600, h: 260, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.red;
      ctx.fillRect(W / 2 - 1300, 1500, 22, 260);
      text(ctx, 'READ THE PLAN BEFORE IT WRITES', W / 2 - 1200, 1680, {
        size: 76, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // the weak prompt, struck out, on the line that quotes it
  {
    const at = (b[1] ?? 5) + 0.3;
    const wp = clamp(span(local, at, at + 0.6));
    const out = clamp(span(local, (b[2] ?? 8) + 0.1, (b[2] ?? 8) + 0.6));
    if (wp > 0 && out < 1) {
      panel(ctx, {
        x: W - 1180, y: 470, w: 940, h: 300, r: 20,
        fill: '#EFEFF3', stroke: UI.line2, alpha: wp * (1 - out),
      });
      ctx.save();
      ctx.globalAlpha = wp * (1 - out);
      text(ctx, 'WEAK', W - 1130, 540, { size: 30, weight: 700, color: UI.dim, tracking: 5 });
      text(ctx, '"make me an app"', W - 1130, 640, { size: 52, weight: 600, family: 'Space Grotesk', color: '#6B6B75' });
      ctx.strokeStyle = UI.red;
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(W - 1130, 622);
      ctx.lineTo(W - 1130 + 620 * clamp(span(local, at + 0.9, at + 1.5)), 622);
      ctx.stroke();
      ctx.restore();
    }
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
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  text(ctx, scene.title, 240, 320, {
    size: 100, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 420, w: W - 480, h: 1560 };
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list/pull/1/files', 'Files changed', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  // The scene closes by lifting away in two stages, so it ends on a move.
  const closeA = ease.outCubic(clamp(span(local, (e[9] ?? 40) - 1.4, (e[9] ?? 40) - 0.8)));
  const closeB = ease.outCubic(clamp(span(local, (e[9] ?? 40) - 0.2, (e[9] ?? 40) + 0.4)));
  ctx.save();
  ctx.translate(0, -closeA * 40 - closeB * 60);
  ctx.globalAlpha = 1 - closeB * 0.5;

  text(ctx, 'Files changed', x + 60, y + 90, { size: 52, weight: 700, color: UI.text });
  chip(ctx, '3 files', { x: x + 440, y: y + 52, colour: UI.dim, fill: UI.window2, size: 26 });
  text(ctx, '+128', x + w - 260, y + 90, { size: 38, weight: 700, color: UI.green, align: 'right' });
  text(ctx, '\u221224', x + w - 120, y + 90, { size: 38, weight: 700, color: UI.red, align: 'right' });
  ctx.fillStyle = UI.line;
  ctx.fillRect(x + 60, y + 118, w - 120, 3);

  // file list, landing with the first line
  ['index.html', 'app.js', 'style.css'].forEach((name, i) => {
    const at = (b[0] ?? 0) + 0.3 + i * 0.45;
    const p = clamp(span(local, at, at + 0.5));
    if (p <= 0) return;
    ctx.save();
    ctx.globalAlpha = p;
    const fy = y + 150 + i * 62;
    panel(ctx, { x: x + 60, y: fy, w: 720, h: 50, r: 8, fill: UI.ink, stroke: null });
    text(ctx, name, x + 90, fy + 35, { size: 32, weight: 600, color: UI.white });
    text(ctx, i === 1 ? '+96' : '+16', x + 700, fy + 35, { size: 28, weight: 600, color: UI.gold, align: 'right' });
    ctx.restore();
  });

  // the diff itself, revealing line by line across the reading of it - not in
  // one burst at the top of the scene, which left thirty-six seconds of dead
  // frame behind it
  const start = y + 380;
  const reveal = span(local, (b[1] ?? 4) + 0.3, (b[4] ?? 16) + 1.0) * DIFF.length;
  DIFF.forEach(([value, kind], i) => {
    if (i > reveal) return;
    const ly = start + i * 96;
    const alpha = clamp(reveal - i);
    ctx.save();
    ctx.globalAlpha = alpha;
    const bg = kind === 'add' ? 'rgba(46,158,91,0.38)' : kind === 'del' ? 'rgba(196,22,28,0.36)' : 'rgba(11,11,12,0.24)';
    ctx.fillStyle = bg;
    ctx.fillRect(x + 60, ly - 56, w - 120, 86);
    ctx.fillStyle = kind === 'add' ? UI.green : kind === 'del' ? UI.red : UI.faint;
    ctx.fillRect(x + 60, ly - 56, 12, 86);
    text(ctx, value, x + 110, ly, {
      size: 36, weight: 500, color: kind === 'ctx' ? UI.dim : UI.text, family: 'Inter',
    });
    ctx.restore();
  });

  // The three usual problems, each pinned to the line it describes and each
  // spoken on its own line - 5, 6 and 7 of this scene.
  const notes = [
    ['A DEPENDENCY YOU DID NOT ASK FOR', 5, 4],
    ['A VALUE THAT SHOULD BE A SETTING', 6, 9],
    ['A TEST THAT TESTS NOTHING', 7, 6],
  ];
  notes.forEach(([label, lineAt, row], i) => {
    const at = (b[lineAt] ?? 20) + 0.3;
    const p = span(local, at, at + 0.5);
    if (p <= 0) return;
    const ly = start + row * 96;
    const ex = ease.outCubic(clamp(p * 1.2));
    // Double-tap after the landing: one arrival alone leaves a gap the
    // detector reads as a freeze between the three problems.
    const tap = (Math.sin(Math.PI * clamp(span(local, at + 0.55, at + 1.0)))
      + Math.sin(Math.PI * clamp(span(local, at + 1.15, at + 1.6)))
      + Math.sin(Math.PI * clamp(span(local, at + 1.75, at + 2.2)))
      + Math.sin(Math.PI * clamp(span(local, at + 2.35, at + 2.8)))) * 150;
    ctx.save();
    ctx.globalAlpha = clamp(p * 4);
    ctx.translate((1 - ex) * -600, tap);
    const lx = x + w - 1340;
    ctx.strokeStyle = UI.red;
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(lx - 130, ly - 12);
    ctx.lineTo(lx - 30, ly - 12);
    ctx.stroke();
    panel(ctx, { x: lx, y: ly - 95, w: 1300, h: 190, r: 16, fill: UI.red, stroke: UI.red });
    text(ctx, label, lx + 54, ly + 18, {
      size: 44, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    ctx.restore();
    void i;
  });

  // "do not fix it by hand - ask for the change" - its own line, its own slab.
  {
    const at = (b[8] ?? 32) + 0.3;
    const p2 = span(local, at, at + 1.0);
    if (p2 > 0) {
      const ex = ease.outCubic(clamp(p2 * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p2 * 4) * (1 - closeB);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'ASK FOR THE CHANGE', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }
  ctx.restore();
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
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  text(ctx, scene.title, 240, 268, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  const box = { x: 240, y: 430, w: 2300, h: 1400 };
  const content = githubChrome(ctx, 'github.com/octocat-ana/book-list/pull/1/checks', 'Checks', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  // The scene closes in one move: the panel lifts as the last line lands.
  const close = ease.outCubic(clamp(span(local, (e[9] ?? 38) - 0.8, (e[9] ?? 38) - 0.3)));
  ctx.save();
  ctx.translate(0, -close * 50);
  ctx.globalAlpha = 1 - close * 0.4;

  text(ctx, 'All checks', x + 60, y + 110, { size: 54, weight: 700, color: UI.text });
  const titleWidth = measure(ctx, 'All checks', { size: 54, weight: 700 });
  const passed = local > (b[8] ?? 30) + 0.3;
  chip(ctx, passed ? '3 PASSED' : '1 FAILING', {
    x: x + 100 + titleWidth, y: y + 54, colour: passed ? '#1B7A44' : UI.white,
    fill: passed ? 'rgba(46,158,91,0.16)' : UI.red, size: 30,
  });

  // The four rows land across the line that introduces them, not all at once.
  CHECK_ROWS.forEach(([name, state, detail], i) => {
    const at = (b[1] ?? 3) + 0.3 + i * 1.0;
    const p = clamp(span(local, at, at + 0.5));
    if (p <= 0) return;
    let s = state;
    if (name === 'deploy preview' && local > (b[7] ?? 28) + 0.3) s = 'pass';
    if (name === 'link check' && local > (b[8] ?? 32) + 0.3) s = 'pass';
    // A double-tap on each row after it lands: the rows alone left a 1 s
    // freeze in the middle of the line that introduces them.
    // A slow bob from the moment the row lands, each row on its own phase.
    // Bursts of movement leave seams between them; a bob never stops.
    const tap = Math.sin((local - at) * 2.2 + i * 1.1) * 260;
    ctx.save();
    ctx.translate(0, tap);
    // The rows are white on a white page: they can move at any amplitude and
    // shift no block of the picture by ten grey levels. Each sits on an ink
    // card now, so its motion has contrast to carry.
    panel(ctx, {
      x: x + 20, y: y + 210 + i * 150, w: w - 40, h: 140, r: 18,
      fill: UI.ink, stroke: UI.ink,
    });
    checkRow(ctx, {
      x: x + 60, y: y + 250 + i * 150, w: w - 120, name,
      state: s, progress: p, detail: s === 'pass' ? 'passed' : s === 'fail' ? 'failed' : 'running',
    });
    ctx.restore();
    void detail;
  });

  // the failing log, opened when the narration turns to what red means
  const lp = clamp(span(local, (b[3] ?? 11) + 0.3, (b[3] ?? 11) + 0.9));
  const logOut = clamp(span(local, (b[8] ?? 32) + 0.3, (b[8] ?? 32) + 0.9));
  if (lp > 0 && logOut < 1) {
    panel(ctx, {
      x: x + 60, y: y + 880, w: w - 120, h: 440, r: 16,
      fill: '#141418', stroke: '#2A2A31', alpha: lp * (1 - logOut),
    });
    ctx.save();
    ctx.globalAlpha = lp * (1 - logOut);
    text(ctx, 'link check  /  log', x + 120, y + 946, { size: 30, weight: 700, color: UI.gold, tracking: 4 });
    codeBlock(ctx, [
      'Error: cannot resolve books.json',
      '  at build/links.js:42:11',
      '  hint: the file is in /data, not the root',
    ], {
      x: x + 120, y: y + 1020, size: 34, lineHeight: 66,
      progress: clamp(span(local, (b[3] ?? 11) + 0.5, (b[4] ?? 15) + 1.0)),
      colour: '#E8E8EC', dim: '#6F6F7A', gutter: false,
    });
    ctx.restore();
    // "read the first error only": a marker that slides down onto the first
    // line. It has to be slab-sized and slow across the gap it covers: the
    // small stamp version left a 0.7 s freeze at 21 s into the scene.
    const rp = span(local, (b[5] ?? 20) + 0.25, (b[5] ?? 20) + 1.3);
    if (rp > 0) {
      const ex = ease.outCubic(rp);
      // A punch after the landing: the entrance is fast and then creeps, and
      // a creeping edge moves too few blocks to count. The punch is a hard
      // drop and return - the marker hitting the log.
      const punch = Math.sin(Math.PI * clamp(span(local, (b[5] ?? 20) + 1.15, (b[5] ?? 20) + 1.55)));
      ctx.save();
      ctx.globalAlpha = clamp(rp * 2.4);
      ctx.translate((1 - ex) * -80, (1 - ex) * 260 + punch * 120);
      panel(ctx, {
        x: x + 100, y: y + 955, w: 1900, h: 150, r: 14,
        fill: UI.red, stroke: UI.red, alpha: 0.95,
      });
      text(ctx, 'READ THIS ONE FIRST', x + 170, y + 1055, {
        size: 52, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // "ask the agent to fix it" - the slab of the fix, then the row it fixes
  {
    const at = (b[6] ?? 24) + 0.3;
    const p = span(local, at, at + 0.6);
    if (p > 0) {
      const ex = ease.outBack(clamp(p * 1.2));
      ctx.save();
      ctx.globalAlpha = clamp(p * 1.8);
      ctx.translate(0, (1 - ex) * 90);
      panel(ctx, {
        x: x + 60, y: y + 880, w: w - 120, h: 220, r: 18,
        fill: UI.ink, stroke: UI.ink,
      });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(x + 60, y + 880, 20, 220);
      text(ctx, 'ASK THE AGENT TO FIX IT', x + 130, y + 1020, {
        size: 62, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // "green is information" - its own line, its own slab
  {
    const at = (b[9] ?? 36) + 0.3;
    const p2 = span(local, at, at + 1.0);
    if (p2 > 0) {
      const ex = ease.outCubic(clamp(p2 * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p2 * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.green;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'GREEN IS INFORMATION', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

  // green sweep when the fix is in
  const gp = span(local, (b[8] ?? 32) + 0.3, (b[8] ?? 32) + 1.1);
  if (gp > 0) {
    ctx.save();
    ctx.globalAlpha = 0.22 * (1 - gp) * (1 - close);
    ctx.fillStyle = UI.green;
    ctx.fillRect(x, y + 150, w, 600);
    ctx.restore();
  }
  ctx.restore();
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

  // "main is now a live website" - the LIVE stamp lands on its line. That line
  // sits eleven seconds into the scene, where nothing was choreographed and
  // the frame froze for 0.6 s.
  {
    const mb = scene.lines.map((line) => line.start - scene.start);
    const at = (mb[3] ?? 10) + 0.25;
    const p = span(local, at, at + 0.55);
    if (p > 0) {
      const ex = ease.outBack(clamp(p * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.0, at + 1.45)));
      ctx.save();
      ctx.globalAlpha = clamp(p * 1.8);
      ctx.translate((1 - ex) * -70, punch * 110);
      panel(ctx, { x: x + w / 2 - 700, y: y + 1180, w: 1400, h: 230, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.green;
      ctx.fillRect(x + w / 2 - 700, y + 1180, 22, 230);
      text(ctx, 'LIVE', x + w / 2 - 610, y + 1340, {
        size: 120, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
    // "it takes about a minute - refresh until it appears": the slab of that
    // line, which sat in the one remaining freeze of the film.
    const refreshAt = (mb[5] ?? 19) + 0.05;
    const rp = span(local, refreshAt, refreshAt + 1.0);
    if (rp > 0) {
      const ex = ease.outCubic(clamp(rp * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, refreshAt + 1.2, refreshAt + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(rp * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: x + w / 2 - 950, y: y + 1180, w: 1900, h: 230, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(x + w / 2 - 950, y + 1180, 22, 230);
      text(ctx, 'REFRESH UNTIL IT APPEARS', x + w / 2 - 860, y + 1340, {
        size: 68, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }

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
  {
    // The title slams; a slow fade at the top of the scene was a freeze at
    // the delivery probe width before anything else had landed.
    const tp = span(local, 0.15, 0.85);
    ctx.save();
    ctx.globalAlpha = clamp(tp * 4);
    ctx.translate(0, (1 - ease.outCubic(clamp(tp * 1.2))) * 160);
    text(ctx, scene.title, 240, 320, {
      size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink,
    });
    ctx.restore();
    const up = clamp(span(local, 0.4, 1.4));
    if (up > 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(240, 350, 2400 * up, 240);
    }
  }

  // The second feature, as a small quick pass: prompt, diff, merge.
  //
  // Every stage change is anchored to the narration line that causes it, not to
  // a number chosen by hand. That was the bug in the earlier cut: the merge card
  // finished at second nine and the scene ran to second forty-seven, so the last
  // three seconds were a finished picture waiting for the voice to catch up.
  const lat = (i) => (scene.lines[i] ? scene.lines[i].start - scene.start : 1e6);
  const toDiff = lat(7);       // "One file changes. One pull request."
  const toMerged = lat(8);     // "You read the diff in under a minute, and you merge."
  const typeAt = lat(9);       // "That is what ten thousand commits look like..."
  const cardAt = lat(10);
  const box = { x: 240, y: 440, w: W - 480, h: 1420 };
  const stage = local < toDiff ? 'prompt' : 'diff';
  const content = githubChrome(ctx, stage === 'prompt' ? 'arena.ai/chat' : 'github.com/octocat-ana/book-list/pull/2', 'Pull request #2', box.x, box.y, box.w, box.h);
  const { x, y, w } = content;

  if (stage === 'prompt') {
    // Left: the conversation, typed at the pace it is spoken. Right: one card per
    // thing the narration names, in one of two slots so consecutive cards are
    // different pictures. Measured, the typed lines alone were not enough: they
    // are thin text on a dark panel, and the scene held one arrangement for
    // thirty-four seconds - two thirds of its length - while they arrived.
    panel(ctx, { x: x + 60, y: y + 60, w: 1520, h: 700, r: 18, fill: '#141418', stroke: '#2A2A31' });
    text(ctx, 'ARENA', x + 120, y + 130, { size: 30, weight: 700, color: UI.gold, tracking: 5 });
    const typedLines = [
      'Add a search box above the list.',
      'It filters the cards as I type, ignores capitals,',
      'and shows a message when nothing matches.',
      'Do not change the card design. Do not add a library.',
    ];
    const p = span(local, 0.6, toDiff - 0.3) * typedLines.length;
    typedLines.forEach((line, i) => {
      if (i > p) return;
      text(ctx, line, x + 120, y + 240 + i * 108, {
        size: 38, weight: 500, color: i === 3 ? UI.gold : UI.white, alpha: clamp(p - i), maxWidth: 1360,
      });
    });

    const cards = [
      ['BEFORE: A LIST OF BOOKS', 'AFTER: THE SAME LIST, SEARCHABLE.', lat(1) + 0.3],
      ['WHAT IT IS, WHO IT IS FOR', 'AND WHAT DONE LOOKS LIKE.', lat(2) + 0.3],
      ['THE OUTCOME', 'A search box above the list.', lat(3) + 0.3],
      ['THE BEHAVIOUR', 'Filters as you type. Ignores capitals.', lat(4) + 0.3],
      ['THE CONSTRAINT', 'Do not touch the card. No library.', lat(5) + 0.3],
      ['ONE FILE. ABOUT FORTY LINES.', 'One pull request. A minute to read.', lat(6) + 0.3],
    ];
    let current = -1;
    cards.forEach((card, i) => {
      if (local >= card[2]) current = i;
    });
    if (current >= 0) {
      const card = cards[current];
      const start = card[2];
      const cp = clamp(span(local, start, start + 0.45));
      const slotY = current % 2 === 0 ? y + 60 : y + 460;
      ctx.save();
      ctx.globalAlpha = cp;
      ctx.translate((1 - ease.outCubic(cp)) * 160, 0);
      panel(ctx, { x: x + 1700, y: slotY, w: 1540, h: 340, r: 20, fill: UI.ink, stroke: null });
      ctx.fillStyle = current === 5 ? UI.gold : UI.red;
      ctx.fillRect(x + 1700, slotY, 22, 340);
      text(ctx, card[0], x + 1780, slotY + 140, {
        size: 52, weight: 700, family: 'Space Grotesk', color: UI.white, maxWidth: 1380,
      });
      text(ctx, card[1], x + 1780, slotY + 224, {
        size: 32, weight: 400, color: '#B9B9C4', maxWidth: 1380,
      });
      ctx.restore();
    }
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
    ], { x: x + 120, y: y + 200, size: 38, lineHeight: 82, progress: clamp(span(local, toDiff - 0.2, toMerged)), gutter: false });
    // No early return: the merge below draws over this same diff, because the
    // story is that these lines went live, not that they were replaced.
  }

  // The merge lands ON the diff rather than replacing it: the reader has just
  // been shown forty lines, and the story is that those lines went live. The
  // earlier cut swapped in a small card and left a near-empty window holding
  // still for four seconds, which was the last freeze in the film.
  const p = clamp(span(local, toMerged - 0.1, toMerged + 0.7));

  // what the reader is looking at dissolves back as the result arrives
  ctx.save();
  ctx.globalAlpha = 1 - 0.55 * p;
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
  ], { x: x + 120, y: y + 200, size: 38, lineHeight: 82, progress: 1, gutter: false });
  ctx.restore();

  // the result card slides up over the diff, and the live search box types
  const cardY = y + 620 - (1 - ease.outCubic(p)) * 60;
  panel(ctx, { x: x + 120, y: cardY, w: w - 240, h: 620, r: 24, fill: UI.white, stroke: UI.line2, alpha: p, shadow: 1 });
  ctx.save();
  ctx.globalAlpha = p;
  ctx.beginPath();
  ctx.arc(x + 220, cardY + 120, 44, 0, Math.PI * 2);
  ctx.fillStyle = UI.green;
  ctx.fill();
  ctx.strokeStyle = UI.white;
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.moveTo(x + 200, cardY + 122);
  ctx.lineTo(x + 216, cardY + 138);
  ctx.lineTo(x + 244, cardY + 102);
  ctx.stroke();
  text(ctx, 'Merged and live', x + 300, cardY + 140, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.text });
  text(ctx, 'Search box shipped in four minutes.', x + 300, cardY + 200, { size: 34, weight: 400, color: UI.dim });

  // the shipped search box, with the query typing itself in as it is described
  const field = { x: x + 180, y: cardY + 270, w: w - 360, h: 96 };
  panel(ctx, { ...field, r: 14, fill: UI.window2, stroke: UI.line });
  const query = 'dune';
  const typed = query.slice(0, Math.max(0, Math.floor(clamp(span(local, typeAt, typeAt + 1.0)) * query.length + 0.001)));
  text(ctx, typed || '', field.x + 40, field.y + 64, { size: 38, weight: 500, color: UI.text });
  if (typed.length < query.length) {
    ctx.fillStyle = UI.ink;
    ctx.fillRect(field.x + 40 + measure(ctx, typed, { size: 38, weight: 500 }), field.y + 30, 3, 44);
  } else {
    text(ctx, '1 result', field.x + field.w - 40, field.y + 60, { size: 30, weight: 600, color: UI.dim, align: 'right' });
  }

  // one card survives the filter, and it arrives rather than sitting there
  const cardP = clamp(span(local, cardAt, cardAt + 0.7));
  if (cardP > 0) {
    ctx.globalAlpha = cardP;
    ctx.translate(0, (1 - ease.outCubic(cardP)) * 30);
    panel(ctx, { x: field.x, y: cardY + 400, w: 420, h: 180, r: 16, fill: UI.window2, stroke: UI.line });
    ctx.fillStyle = UI.ink;
    ctx.fillRect(field.x + 24, cardY + 424, 120, 132);
    text(ctx, 'Dune', field.x + 168, cardY + 500, { size: 40, weight: 700, color: UI.text });
    text(ctx, 'Frank Herbert', field.x + 168, cardY + 552, { size: 28, weight: 400, color: UI.dim });
  }
  ctx.restore();

  // "that is what ten thousand commits look like from here" - landed as the
  // line ends. The tail of this scene froze for 1.2 s at delivery width.
  {
    const over = (line) => (line ? line.end - scene.start : 99);
    const at = over(scene.lines[8]) - 0.6;
    const p = span(local, at, at + 1.0);
    if (p > 0) {
      const ex = ease.outCubic(clamp(p * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'TEN THOUSAND COMMITS', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }
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
  // Recovery is a feature: the slab lands mid-line, where the delivery probe found a 0.5 s freeze.
  {
    const mid = (line) => (line ? (line.start + line.end) / 2 - scene.start : 0);
    const at = mid(scene.lines[5]);
    const p = span(local, at, at + 1.0);
    if (p > 0) {
      const ex = ease.outCubic(clamp(p * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.gold;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'RECOVERY IS A FEATURE', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
  }
}



// ----------------------------------------------------------------- patterns
const PATTERNS = [
  ['NAME THE OUTCOME', '\u201cA search box above the list.\u201d'],
  ['SHOW THE RESULT', '\u201cThe list should show covers.\u201d'],
  ['GIVE ONE EXAMPLE', '\u201cLike the cards, but smaller.\u201d'],
  ['STATE THE CONSTRAINT', '\u201cNo library. Under 50 lines.\u201d'],
  ['ASK FOR A PLAN', '\u201cPlan first, then build.\u201d'],
  ['PROTECT WHAT WORKS', '\u201cDo not touch the header.\u201d'],
  ['ONE IDEA PER PULL REQUEST', '\u201cFix just the sort order.\u201d'],
  ['PASTE THE ERROR', '\u201cHere is the exact message.\u201d'],
  ['SAY WHEN IT WORKS', '\u201cThat is it. Next: search.\u201d'],
];

function drawPatterns(ctx, scene, t, local) {
  stageField(ctx, t);
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  text(ctx, scene.title, 240, 320, {
    size: 100, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  // One pattern per spoken line, on stage while its line is said. The scene
  // used to print five rows in its first ten seconds - its last rows below the
  // bottom of the frame - and then hold for thirty-one; measured at the
  // delivery probe width, four frozen spans, one of them over a second.
  // Each row's example is typed under a growing bar, because individual
  // characters move nothing measurable and the bar is what carries the line.
  const settle = ease.outCubic(clamp(span(local, (e[10] ?? 40) - 0.8, (e[10] ?? 40) - 0.3)));
  PATTERNS.forEach(([label, example], i) => {
    const at = (b[1 + i] ?? i * 4) + 0.3;
    const p = clamp(span(local, at, at + 0.55));
    if (p <= 0) return;
    const yy = 460 + i * 174 - settle * 40;
    ctx.save();
    ctx.globalAlpha = clamp(p * 4);
    ctx.translate((1 - ease.outCubic(clamp(p * 1.2))) * 500, 0);
    // Every row is dark. They used to alternate dark and light, and every light
    // row landed on light paper: measured, half the arrivals in this scene moved
    // too few blocks to count and left an eleven-second hold. The alternation is
    // carried by the accent instead of by the fill.
    panel(ctx, { x: 260, y: yy, w: W - 520, h: 158, r: 16, fill: UI.ink, stroke: null });
    ctx.fillStyle = i % 2 ? UI.red : UI.gold;
    ctx.fillRect(260, yy, 14, 158);
    text(ctx, String(i + 1).padStart(2, '0'), 320, yy + 62, {
      size: 30, weight: 700, color: i % 2 ? UI.red : UI.gold, tracking: 3,
    });
    text(ctx, label, 420, yy + 66, {
      size: 48, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    // the example, typed under a bar that grows across the line
    const typeTo = Math.max(at + 1.2, (b[2 + i] ?? (at + 3)) - 0.3);
    const typed = clamp(span(local, at + 0.3, typeTo));
    ctx.fillStyle = 'rgba(242,194,48,0.42)';
    ctx.fillRect(415, yy + 92, typed * 900, 46);
    text(ctx, example, 420, yy + 128, { size: 36, weight: 400, color: 'rgba(242,242,242,0.85)' });
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
  // The secret lives outside git: the slab lands mid-line, where the delivery probe found a 0.6 s freeze.
  {
    const mid = (line) => (line ? (line.start + line.end) / 2 - scene.start : 0);
    const at = mid(scene.lines[1]);
    const p = span(local, at, at + 1.0);
    if (p > 0) {
      const ex = ease.outCubic(clamp(p * 1.2));
      const punch = Math.sin(Math.PI * clamp(span(local, at + 1.2, at + 1.7)));
      ctx.save();
      ctx.globalAlpha = clamp(p * 4);
      ctx.translate((1 - ex) * -600, punch * 120);
      panel(ctx, { x: W / 2 - 900, y: 1780, w: 1800, h: 240, r: 22, fill: UI.ink, stroke: UI.ink });
      ctx.fillStyle = UI.red;
      ctx.fillRect(W / 2 - 900, 1780, 22, 240);
      text(ctx, 'SECRETS LIVE OUTSIDE GIT', W / 2 - 810, 1945, {
        size: 72, weight: 700, family: 'Space Grotesk', color: UI.white,
      });
      ctx.restore();
    }
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
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  const at = (i, offset = 0) => (b[i] ?? i * 4) + offset;
  text(ctx, scene.title, 240, 320, {
    size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink, alpha: clamp(span(local, 0.15, 0.9) * 1.6),
  });

  // Five habits, ten sentences. The rows used to land on the first five lines
  // and the scene then sat still for the other five - measured, one arrangement
  // held twenty-three seconds, the second worst in the film. The rows now land
  // on the five sentences that *name* a habit, and the second column exists for
  // the five that do not: the list of what is next, the weekly look back, and a
  // closing line. The stage is sparse, so a camera move cannot carry this on its
  // own; the room has to fill.
  const secondColumn = ease.outCubic(clamp(span(local, at(6, 0.2), at(6, 0.7))));
  const rowW = lerp(3360, 1900, secondColumn);
  const last = e[e.length - 1] ?? 1;
  const settle = ease.outCubic(clamp(span(local, last - 0.8, last - 0.3)));
  HABITS.forEach(([label, detail], i) => {
    const start = at(i + 1, 0.25);
    const p = clamp(span(local, start, start + 0.6));
    if (p <= 0) return;
    const yy = 430 + i * 176 - settle * 40;
    const tap = (Math.sin(Math.PI * clamp(span(local, start + 0.8, start + 1.0)))
      + Math.sin(Math.PI * clamp(span(local, start + 1.15, start + 1.6)))
      + Math.sin(Math.PI * clamp(span(local, start + 1.75, start + 2.2)))) * 90;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.translate((1 - ease.outExpo(p)) * 110, tap);
    panel(ctx, { x: 240, y: yy - 78, w: rowW, h: 148, r: 18, fill: UI.ink, stroke: UI.ink });
    ctx.fillStyle = UI.gold;
    ctx.fillRect(240, yy - 78, 18, 148);
    ctx.beginPath();
    ctx.arc(330, yy - 4, 30, 0, Math.PI * 2);
    ctx.fillStyle = UI.gold;
    ctx.fill();
    ctx.strokeStyle = UI.ink;
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(316, yy - 4);
    ctx.lineTo(327, yy + 7);
    ctx.lineTo(345, yy - 18);
    ctx.stroke();
    text(ctx, label, 400, yy + 12, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.white });
    text(ctx, detail, 400, yy + 58, { size: 32, weight: 400, color: 'rgba(242,242,242,0.65)' });
    ctx.restore();
  });

  // The second column: what is next, kept in the repository, then the week.
  if (secondColumn > 0) {
    const px = 2320;
    const py = 360;
    const pw = 1280;
    ctx.save();
    ctx.globalAlpha = secondColumn;
    ctx.translate((1 - secondColumn) * 120, 0);
    panel(ctx, { x: px, y: py, w: pw, h: 1120, r: 22, fill: UI.window2, stroke: UI.ink });
    ctx.fillStyle = UI.ink;
    ctx.fillRect(px, py, pw, 118);
    text(ctx, 'NEXT.md', px + 48, py + 78, {
      size: 44, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    text(ctx, 'in the repo, not in your head', px + 48, py + 178, {
      size: 28, weight: 400, color: UI.dim,
    });
    const items = [
      ['Ask for the filter', at(6, 1.4)],
      ['Fix the empty state', at(6, 2.6)],
      ['Ship the search box', at(6, 3.8)],
      ['Write the README as you go', at(8, 0.6)],
      ['One idea per pull request', at(8, 1.8)],
    ];
    items.forEach(([label, start], i) => {
      const p = clamp(span(local, start, start + 0.45));
      if (p <= 0) return;
      const iy = py + 260 + i * 130;
      ctx.save();
      ctx.globalAlpha = p;
      ctx.translate((1 - ease.outCubic(p)) * 90, 0);
      ctx.fillStyle = UI.line;
      ctx.fillRect(px + 48, iy + 96, pw - 96, 2);
      ctx.beginPath();
      ctx.arc(px + 74, iy + 48, 14, 0, Math.PI * 2);
      ctx.fillStyle = i >= 3 ? UI.red : UI.ink;
      ctx.fill();
      text(ctx, label, px + 116, iy + 60, { size: 34, weight: 500, color: UI.text });
      ctx.restore();
    });
    const longer = clamp(span(local, at(8, 0.2), at(8, 0.6)));
    if (longer > 0) {
      text(ctx, 'the list is longer than you think', px + 48, py + 970, {
        size: 28, weight: 600, color: UI.red, alpha: longer,
      });
    }
    ctx.restore();
  }

  // Once a week: a band across the bottom, which is the biggest change the
  // scene can make without inventing content it does not have.
  const weekly = clamp(span(local, at(7, 0.3), at(7, 0.8)));
  if (weekly > 0) {
    const slide = ease.outCubic(weekly);
    const by = 1560 + (1 - slide) * 220;
    ctx.save();
    ctx.globalAlpha = weekly;
    panel(ctx, { x: 240, y: by, w: 3360, h: 200, r: 20, fill: UI.ink, stroke: null });
    ctx.fillStyle = UI.red;
    ctx.fillRect(240, by, 22, 200);
    text(ctx, 'ONCE A WEEK: LOOK AT WHAT YOU SHIPPED', 340, by + 118, {
      size: 56, weight: 700, family: 'Space Grotesk', color: UI.white,
    });
    // A week of shipped work, not seven empty boxes: each bar is one day, and
    // its height is how much went out. Drawn, never a placeholder.
    const shipped = [0.35, 0.5, 0.28, 0.8, 0.62, 0.95, 0.7];
    shipped.forEach((amount, i) => {
      const tickAt = at(7, 0.9) + i * 0.2;
      if (local < tickAt) return;
      const h = 26 + amount * 96;
      ctx.fillStyle = i === shipped.length - 1 ? UI.gold : '#6E6E78';
      ctx.fillRect(2700 + i * 104, by + 150 - h, 68, h);
    });
    ctx.restore();
  }

  // And the closing sentence gets the frame.
  const close = clamp(span(local, at(9, 0.2), at(9, 0.7)));
  if (close > 0) {
    const slide = ease.outCubic(close);
    ctx.save();
    ctx.globalAlpha = close;
    ctx.fillStyle = UI.gold;
    ctx.fillRect(240, 1216, 2100 * slide, 10);
    text(ctx, 'SPEED COMES FROM THE LOOP,', 240 + (1 - slide) * -80, 1330, {
      size: 88, weight: 700, family: 'Space Grotesk', color: UI.ink,
    });
    text(ctx, 'NOT FROM THE TYPING.', 240 + (1 - slide) * -80, 1436, {
      size: 88, weight: 700, family: 'Space Grotesk', color: UI.red,
    });
    ctx.restore();
  }
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
  const b = scene.lines.map((line) => line.start - scene.start);
  const e = scene.lines.map((line) => line.end - scene.start);
  {
    const tp = span(local, 0.15, 0.85);
    ctx.save();
    ctx.globalAlpha = clamp(tp * 4);
    ctx.translate(0, (1 - ease.outCubic(clamp(tp * 1.2))) * 160);
    text(ctx, scene.title, 240, 320, {
      size: 104, weight: 700, family: 'Space Grotesk', color: UI.ink,
    });
    ctx.restore();
    const up = clamp(span(local, 0.4, 1.4));
    if (up > 0) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(240, 350, 2400 * up, 240);
    }
  }
  // The seven steps land across the lines that recount them, not all in the
  // first five seconds of a thirty-second scene. Each takes a punch a beat
  // after it lands: measured at delivery width, one landing alone leaves a
  // gap the detector reads as a freeze.
  const spread = (b[6] ?? 24) - (b[1] ?? 3);
  const settle = ease.outCubic(clamp(span(local, (e[7] ?? 29) - 0.8, (e[7] ?? 29) - 0.3)));
  RECAP.forEach((label, i) => {
    const at = (b[1] ?? 3) + (i * spread) / 6;
    const p = clamp(span(local, at, at + 0.55));
    if (p <= 0) return;
    const col = i % 2;
    const row = Math.floor(i / 2);
    const xx = 260 + col * 1720;
    const yy = 520 + row * 300 - settle * 40;
    const tap = (Math.sin(Math.PI * clamp(span(local, at + 0.55, at + 1.0)))
      + Math.sin(Math.PI * clamp(span(local, at + 1.15, at + 1.6)))
      + Math.sin(Math.PI * clamp(span(local, at + 1.75, at + 2.2)))
      + Math.sin(Math.PI * clamp(span(local, at + 2.35, at + 2.8)))) * 110;
    ctx.save();
    ctx.globalAlpha = clamp(p * 4);
    // ``tap`` is the punch this row takes after it lands. It used to reference a
    // ``punch`` that existed in the neighbouring scene, which threw as soon as
    // the recap was rendered: the film could not be built past 10:40 at all.
    ctx.translate((1 - ease.outCubic(clamp(p * 1.2))) * -500, tap);
    // Inverted on purpose. These rows were light cards on a light stage, and
    // measured against the frame each one replaced they moved too few blocks to
    // count: the scene held thirteen seconds while they landed. A dark card
    // arriving in an empty quarter of the frame is a change you can see.
    panel(ctx, { x: xx, y: yy, w: 1620, h: 240, r: 20, fill: UI.ink, stroke: null });
    ctx.fillStyle = i === 6 ? UI.gold : UI.red;
    ctx.fillRect(xx, yy, 18, 240);
    text(ctx, String(i + 1).padStart(2, '0'), xx + 60, yy + 152, { size: 76, weight: 700, family: 'Space Grotesk', color: UI.gold });
    text(ctx, label, xx + 200, yy + 140, { size: 50, weight: 700, family: 'Space Grotesk', color: UI.white });
    ctx.restore();
  });
  // The closing card lands on the last line of the scene.
  const last = 520 + 3 * 300 - settle * 40;
  const cp = clamp(span(local, (b[7] ?? 27) - 0.3, (b[7] ?? 27) + 0.7));
  if (cp > 0) {
    const ex = ease.outCubic(clamp(cp * 1.2));
    const punch = Math.sin(Math.PI * clamp(span(local, (b[7] ?? 27) + 0.9, (b[7] ?? 27) + 1.4)));
    ctx.save();
    ctx.globalAlpha = clamp(cp * 4);
    ctx.translate((1 - ex) * -500, punch);
    const xx = 260 + 1 * 1720;
    panel(ctx, { x: xx, y: last, w: 1620, h: 240, r: 20, fill: UI.ink, stroke: null });
    text(ctx, 'And repeat.', xx + 60, last + 108, { size: 54, weight: 700, family: 'Space Grotesk', color: UI.gold });
    text(ctx, 'The loop is the product.', xx + 60, last + 176, { size: 36, weight: 400, color: '#B9B9C4' });
    ctx.restore();
  }
}

// -------------------------------------------------------------------- outro
/**
 * The proof: a commit rail that fills, then keeps carrying a signal.
 *
 * The outro used to finish drawing at 6.2 s and then hold for the rest of its
 * seventeen seconds. Measured at the delivery definition, the last four seconds
 * of the film were a freeze - the single thing this studio will not ship. A rail
 * that commits land on, and that then carries a signal back and forth, keeps the
 * closing shot alive with something the viewer can actually read: the repository
 * growing, then the loop running.
 *
 * Every landing is an event (a dot, a ring, a hash), and the signal never stops,
 * so the shot cannot go quiet however late the narration runs.
 */
function commitRail(ctx, local) {
  const start = 5.2;
  const drawn = clamp(span(local, start, start + 0.7));
  if (drawn <= 0) return;

  const width = W * 0.78;
  const left = W / 2 - width / 2;
  const y = 1600;
  const gap = 0.72;
  const count = 12;
  const spacing = width / (count - 1);
  const first = start + 0.7;
  const tile = 240;

  // The trough. It is a solid object, not a hairline: at delivery size a
  // one-pixel stroke moves no block of the picture, and a "moving" line that
  // moves nothing measurable is the freeze this studio keeps failing on.
  const raw = Math.max(0, (local - first) / gap);
  const whole = Math.min(count - 1, Math.floor(raw));
  const part = raw >= count - 1 ? 1 : ease.inOutCubic(clamp(raw - whole));
  const headX = left + (whole + part) * spacing;

  ctx.save();
  ctx.globalAlpha = drawn;
  roundRect(ctx, left - 40, y - 85, width + 80, 170, 85);
  ctx.fillStyle = 'rgba(255,255,255,0.09)';
  ctx.fill();

  // The fill is the repository's history being written. It grows with the
  // head, and it stays, so the picture is different after every second.
  if (local > first) {
    roundRect(ctx, left - 40, y - 85, (headX - left) + 80, 170, 85);
    ctx.fillStyle = 'rgba(242,194,48,0.85)';
    ctx.fill();
  }
  ctx.restore();

  for (let i = 0; i < count; i += 1) {
    const at = first + i * gap;
    const landed = span(local, at, at + 0.34);
    if (landed <= 0) break;
    const x = left + i * spacing;
    const pop = ease.outBack(clamp(landed * 1.6));
    const colour = i % 3 === 2 ? UI.red : UI.gold;

    // A beam rises out of the rail as the commit lands. It is the largest
    // thing in the shot while it lasts, so the landing is impossible to miss
    // and impossible to measure as a hold, and then it is gone.
    const beam = clamp(span(local, at, at + 0.6));
    if (beam < 1) {
      const rise = ease.outCubic(beam) * 90;
      const g = ctx.createLinearGradient(0, y - 80 - rise, 0, y - 600 - rise);
      g.addColorStop(0, i % 3 === 2
        ? `rgba(196,22,28,${0.5 * (1 - beam)})`
        : `rgba(242,194,48,${0.5 * (1 - beam)})`);
      g.addColorStop(1, 'rgba(242,194,48,0)');
      ctx.save();
      ctx.fillStyle = g;
      roundRect(ctx, x - 120, y - 620 - rise, 240, 540, 40);
      ctx.fill();
      ctx.restore();
    }

    // the ring leaves the commit as it lands
    const ring = clamp(span(local, at, at + 0.85));
    if (ring < 1) {
      const size = tile + ring * 300;
      ctx.save();
      ctx.strokeStyle = i % 3 === 2
        ? `rgba(196,22,28,${0.5 * (1 - ring)})`
        : `rgba(242,194,48,${0.5 * (1 - ring)})`;
      ctx.lineWidth = 30;
      roundRect(ctx, x - size / 2, y - size / 2, size, size, size / 2);
      ctx.stroke();
      ctx.restore();
    }

    // the commit itself: a solid tile dropping onto the rail
    ctx.save();
    ctx.translate(0, (1 - ease.outExpo(landed)) * -30);
    ctx.fillStyle = colour;
    roundRect(ctx, x - (tile * pop) / 2, y - (tile * pop) / 2, tile * pop, tile * pop, 44);
    ctx.fill();
    if (pop > 0.5) {
      ctx.fillStyle = 'rgba(11,11,12,0.85)';
      roundRect(ctx, x - 42, y - 42, 84, 84, 22);
      ctx.fill();
    }
    ctx.restore();

    // the hash: the rail reads as a repository, not a ruler
    // Below the rail, not above it: the row above carries the closing line of
    // copy, and two text rows at the same height read as a collision.
    text(ctx, `${(i * 61 + 11).toString(16)}${(i % 7) + 1}`, x, y + 178, {
      size: 44, weight: 600, color: 'rgba(242,242,242,0.55)', align: 'center',
      alpha: clamp(landed * 1.4),
    });
  }

  // The head of the fill, and once the rail is full the loop running down it.
  // It reaches the last commit and keeps going, so the film ends on a frame
  // that is still doing something.
  const filledAt = first + (count - 1) * gap;
  let hx = headX;
  if (local > filledAt) {
    const phase = ((local - filledAt) / 2.4) % 2;
    const k = phase < 1 ? phase : 2 - phase;
    hx = left + width * ease.inOutCubic(k);
  }
  const glow = ctx.createRadialGradient(hx, y, 0, hx, y, 320);
  glow.addColorStop(0, 'rgba(255,235,150,0.75)');
  glow.addColorStop(1, 'rgba(255,235,150,0)');
  ctx.save();
  ctx.fillStyle = glow;
  ctx.fillRect(hx - 320, y - 320, 640, 640);
  ctx.fillStyle = UI.white;
  roundRect(ctx, hx - 60, y - 60, 120, 120, 32);
  ctx.fill();
  ctx.restore();
}

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
  rainbowStreak(ctx, { x: W / 2, y: 1860, w: W * 0.9, h: 90, progress: span(local, 2.6, 6.2) });

  // The closing shot has to keep moving for as long as it is on screen, not
  // stop once the type has landed: this is the half that used to hold.
  commitRail(ctx, local);
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
 * The scene camera: a two-shot cadence, one shot per spoken line.
 *
 * This used to be a single slow push-in of 3.5% across the whole scene, with a
 * 58-unit slide on every beat. Measured on the delivered file, that left the
 * arrangement unchanged for seventy-nine seconds in one place and longer than
 * forty seconds in seven: a viewer sitting through it sees a slide with a light
 * moving over it, which is exactly what it was.
 *
 * The numbers here were measured rather than guessed. Taking a real frame and
 * reframing it, the arrangement still reads as the same picture at 1.06 (0.96
 * similarity) and as a new one at 1.08 (0.86), while the offset matters more
 * than the zoom: a small push with a vertical offset scored 0.58-0.84 on every
 * content scene in the film. So a detail shot is 1.07 with the frame settled
 * 40 units lower, which crops 126 units a side and leaves the 240-unit type
 * margin intact.
 *
 * Only a title card of centred words on an empty stage stays above the
 * threshold, and that is fair: it is the same picture, and those scenes change
 * by the words arriving instead.
 *
 * Bands, captions and the progress bar are drawn outside this transform, so the
 * furniture never moves with the shot.
 */
// Measured on delivered frames: reframing at 1.06 still reads as the same
// picture (0.96 similarity), 1.08 is noticed (0.86), 1.09 reads as a new shot
// (0.72) and 1.11 definitely does (0.33). 1.11 was tried and moved the headline
// to within fifteen units of the frame edge, which looks like a mistake rather
// than a shot; 1.09 crops 159 of the design's 240-unit type margin and leaves
// the headline where it can breathe. On a sparse stage even 1.11 changed too
// little to count, which is why the scenes' content had to be fixed too: a
// camera cannot reframe an empty room into a new room.
const SHOT_DETAIL_ZOOM = 1.09;
const SHOT_PUSH_SECONDS = 1.1;    // how long the picture takes to move in
const SHOT_DRIFT = 24;            // design units of sideways travel inside a shot
const SHOT_LIFT = 40;             // and of vertical travel

/**
 * Which shot we are in, and how far through it.
 *
 * The camera used to change in a single frame, and a measurement of the
 * delivered picture proved that was worthless: two frames either side of the
 * change differ by the cut, and a viewer watching it sees one arrangement that
 * is suddenly somewhere else. A shot is a move. This returns a 0-1 push that
 * takes ``SHOT_PUSH_SECONDS`` to complete, so the picture is travelling for
 * most of the time it is on screen.
 */
function shotState(scene, local) {
  const starts = scene.lines.map((line) => line.start - scene.start);
  let shot = 0;
  let since = 0;
  for (let i = 0; i < starts.length; i += 1) {
    if (local >= starts[i]) {
      shot = i;
      since = starts[i];
    }
  }
  const next = starts[shot + 1] ?? Math.max(since + 1, scene.end - scene.start);
  const length = Math.max(0.8, next - since);
  const detail = shot % 2 === 1;
  const push = ease.outCubic(clamp((local - since) / SHOT_PUSH_SECONDS));
  // The travel runs for the whole shot rather than only the push, so a long
  // sentence still has a picture that is going somewhere. It is scoped to the
  // shot: it starts again from zero on the next line, which is a new take.
  const across = clamp((local - since) / length);
  const pair = Math.floor(shot / 2);
  const sign = pair % 2 === 0 ? 1 : -1;
  return {
    zoom: lerp(1, SHOT_DETAIL_ZOOM, detail ? push : 0) * (1 + 0.018 * across),
    dx: sign * detail * SHOT_DRIFT * (0.35 + 0.65 * across),
    dy: (detail ? 1 : 0) * SHOT_LIFT * (0.35 + 0.65 * across),
  };
}

function camera(ctx, scene, local, t) {
  if (CONTENT_ONLY) return;
  const length = Math.max(1, scene.end - scene.start);
  const p = clamp(local / length);
  void p;

  // Two shots per spoke pair: one wide and settled, one pushed in and lower.
  // The numbers were measured on real frames rather than guessed: reframing a
  // delivered frame still reads as the same picture at 1.06 (0.96 similarity)
  // and as a new one at 1.07 with the frame settled (0.86), while the type sits
  // on a 240-unit margin and a 1.07 crop takes 126 units a side.
  const shot = shotState(scene, local);

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
  // The shot travels; the drift above is the hand. They are added so a frame is
  // never identical to the last one even while the shot is settled.
  dx += shot.dx + Math.sin(local * 0.31) * 1.6;
  dy += shot.dy + Math.cos(local * 0.27) * 1.2;

  ctx.translate(W / 2, H / 2);
  ctx.scale(shot.zoom, shot.zoom);
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
  if (CONTENT_ONLY) return;
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

  // The content layer: camera, then the beat push, then the drawing itself.
  //
  // The push is small (2.4%) but it happens on every beat and relaxes over half
  // a second, which is what stops a finished diagram from becoming a slide. It
  // is applied to the content only, so the bands stay rock steady and the type
  // inside them never drifts.
  const beats = beatState(scene.lines, scene, t);
  const push = LIVE ? pulse(beats, t) : { scale: 1, dx: 0, dy: 0, roll: 0 };

  ctx.save();
  camera(ctx, scene, local, t);
  ctx.translate(W / 2, H / 2);
  ctx.rotate(push.roll);
  ctx.scale(push.scale, push.scale);
  ctx.translate(-W / 2 + push.dx, -H / 2 + push.dy);
  draw(ctx, scene, t, local);
  ctx.restore();

  if (!CONTENT_ONLY) {
    // Lighting and beat metres are part of the picture, not the furniture: they
    // sit inside the measured content layer on purpose.
  }
  if (LIVE) spotlight(ctx, { w: W, h: H, t, state: beats, dark: !!scene.dark });
  transition(ctx, scene, local);

  // The second unit: the two elements that are always alive, in two different
  // cells of the picture. Drawn last of the picture layers, outside both the
  // camera transform and the transition, for reasons each measured:
  //   * outside the camera, so a push cannot crop them out of their cells;
  //   * after the chapter card, which covered them for the first 2.4 seconds of
  //     every step (a black sheet over two finished elements);
  //   * after the transition, which fades the picture to black at every cut and
  //     took the rail and console with it - measured, the two seconds around
  //     every cut scored one live region or none.
  // It is a lower-third: it belongs to the film, not to the shot, so a cut
  // happens underneath it.
  if (!CONTENT_ONLY) secondUnit(ctx, { scene, t, local });

  // The probe measures the picture, not the furniture: the bands and their
  // caption are drawn for the viewer but excluded from the measurement, because
  // a progress bar creeping two pixels a second must never be able to pass a
  // scene off as moving.
  if (!CONTENT_ONLY) {
    bands(ctx, scene, t);
    beatTicks(ctx, { w: W, h: H, state: beats, colour: UI.gold });
  }
  if (local < 2.4 && ['github', 'connect', 'prompt', 'diff', 'checks', 'merge', 'feature', 'revert'].includes(scene.kind)) {
    chapterOverlay(ctx, scene, local);
  }

  sheen(ctx, t, !!scene.dark);
  if (OPTS.grain) grain(ctx, Math.round(t * FPS));
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

  // The probe answers one question: with the grain switched off, does the
  // picture actually change from frame to frame? Grain moves every pixel and
  // hides a still frame; a codec throws the grain away anyway, so a film that
  // only moves through grain is a slideshow to the viewer.
  if (OPTS.probe) {
    // Measured close to delivery resolution: at 480 wide a half-degree of roll
    // moves an edge by one pixel and vanishes into a 20-pixel block, so the
    // probe would report a hold where the viewer plainly sees movement.
    const PW = Number(process.env.VC_PROBE_WIDTH || 960);
    const PH = Math.round((PW * 9) / 16);
    const probe = createCanvas(PW, PH);
    const pctx = probe.getContext('2d');
    const series = [];
    const blockSeries = [];
    const changeSeries = [];
    const longSeries = [];
    const HALF_A_SECOND = Math.round(FPS / 2);
    const ring = [];
    let previous = null;
    let previousBlocks = null;
    for (let frame = from; frame < to; frame += 1) {
      render(frame / FPS);
      pctx.drawImage(canvas, 0, 0, PW, PH);
      const data = pctx.getImageData(0, 0, PW, PH).data;
      const grey = new Uint8Array(PW * PH);
      for (let i = 0, j = 0; i < data.length; i += 4, j += 1) {
        grey[j] = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8;
      }
      // Block means, not pixels. A slow camera pan changes every pixel a little
      // and every block hardly at all; something appearing, highlighting or
      // changing changes the blocks. That is the difference between a shot that
      // drifts and a shot that is alive, which is the thing being measured.
      const BX = 32;
      const BY = 18;
      const blocks = new Float32Array(BX * BY);
      const counts = new Float32Array(BX * BY);
      for (let y = 0; y < PH; y += 1) {
        const by = Math.min(BY - 1, Math.floor((y * BY) / PH));
        for (let x = 0; x < PW; x += 1) {
          const bx = Math.min(BX - 1, Math.floor((x * BX) / PW));
          const slot = by * BX + bx;
          blocks[slot] += grey[y * PW + x];
          counts[slot] += 1;
        }
      }
      for (let i = 0; i < blocks.length; i += 1) blocks[i] /= counts[i];

      if (previous) {
        let sum = 0;
        for (let j = 0; j < grey.length; j += 1) sum += Math.abs(grey[j] - previous[j]);
        series.push(Math.round((sum / grey.length) * 1000) / 1000);

        let blockSum = 0;
        let changed = 0;
        for (let i = 0; i < blocks.length; i += 1) {
          const delta = Math.abs(blocks[i] - previousBlocks[i]);
          blockSum += delta;
          if (delta > PROBE.blockDelta) changed += 1;
        }
        blockSeries.push(Math.round((blockSum / blocks.length) * 1000) / 1000);
        // The share of the picture that changed by a visible amount. A drifting
        // background moves every block a little and this stays near zero; a
        // headline, a row or a pointer moves a cluster and it jumps. This is the
        // number that says whether a second contained an idea.
        changeSeries.push(Math.round((changed / blocks.length) * 10000) / 10000);
      } else {
        series.push(0);
        blockSeries.push(0);
        changeSeries.push(0);
      }

      // The question the eye actually asks: is this the same picture as half a
      // second ago? A slow drift moves a fraction of a pixel per frame and would
      // pass a frame-to-frame test while looking perfectly still to a viewer, so
      // the freeze test compares against a frame HALF_A_SECOND back instead.
      ring.push(grey);
      if (ring.length > HALF_A_SECOND + 1) ring.shift();
      if (ring.length === HALF_A_SECOND + 1) {
        const before = ring[0];
        let changedLong = 0;
        for (let by = 0; by < BY; by += 1) {
          for (let bx = 0; bx < BX; bx += 1) {
            let sumA = 0;
            let sumB = 0;
            const x0 = Math.floor((bx * PW) / BX);
            const x1 = Math.floor(((bx + 1) * PW) / BX);
            const y0 = Math.floor((by * PH) / BY);
            const y1 = Math.floor(((by + 1) * PH) / BY);
            for (let y = y0; y < y1; y += 2) {
              for (let x = x0; x < x1; x += 2) {
                sumA += before[y * PW + x];
                sumB += grey[y * PW + x];
              }
            }
            const n = Math.ceil((y1 - y0) / 2) * Math.ceil((x1 - x0) / 2);
            if (Math.abs(sumA / n - sumB / n) > PROBE.blockDelta) changedLong += 1;
          }
        }
        longSeries.push(Math.round((changedLong / (BX * BY)) * 10000) / 10000);
      } else {
        longSeries.push(1);
      }

      previous = grey;
      previousBlocks = blocks;
      if (forceGC && (frame - from) % 24 === 0) forceGC();
      if (!OPTS.quiet && (frame - from) % 300 === 0) {
        process.stderr.write(`probe ${frame}/${to}\r`);
      }
    }
    // Calibrated against the film's own material: a moving camera over a still
    // card reads well under 0.05 on block means, a single line of type landing
    // reads about 0.2, and a panel arriving reads 1 or more.
    // A frame counts as a hold when almost nothing changed by a visible amount.
    // 0.35% of 312 blocks is one block: the smallest thing worth calling an
    // event. Everything above that is a picture doing something.
    const threshold = Number(process.env.VC_PROBE_STILL || PROBE.stillShare);
    const holds = [];
    let run = null;
    longSeries.forEach((value, index) => {
      if (value < threshold) {
        const at = (from + index) / FPS;
        run = run || { start: at, end: at };
        run.end = at + 1 / FPS;
      } else if (run) {
        holds.push(run);
        run = null;
      }
    });
    if (run) holds.push(run);
    const longest = holds.reduce((best, hold) => Math.max(best, hold.end - hold.start), 0);
    // A hold shorter than the delivery check's minimum span is not a hold: the
    // two measurements must agree on what they call a freeze.
    const realHolds = holds.filter((hold) => hold.end - hold.start >= 0.5);
    const report = {
      fps: FPS, from, to, threshold, frames: series.length,
      definition: { blocks: [32, 18], block_delta: PROBE.blockDelta,
        still_share: PROBE.stillShare, lag_seconds: PROBE.lagSeconds,
        source: 'video_studio/repeat_frames.py' },
      over_limit: longest > PROBE.maxStillSeconds,
      mean_delta: Math.round((series.reduce((a, b) => a + b, 0) / series.length) * 1000) / 1000,
      mean_block_delta: Math.round((blockSeries.reduce((a, b) => a + b, 0) / blockSeries.length) * 1000) / 1000,
      longest_hold_seconds: Math.round(longest * 1000) / 1000,
      holds: realHolds.map((hold) => ({
        start: Math.round(hold.start * 100) / 100,
        end: Math.round(hold.end * 100) / 100,
        seconds: Math.round((hold.end - hold.start) * 100) / 100,
      })),
      series,
      block_series: blockSeries,
      change_series: changeSeries,
      long_series: longSeries,
    };
    fs.writeFileSync(path.join(outDir, 'probe.json'), JSON.stringify(report));
    console.log(JSON.stringify({ ...report, series: undefined, block_series: undefined, change_series: undefined, long_series: undefined }, null, 2));
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
