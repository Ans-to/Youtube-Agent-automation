#!/usr/bin/env node
/**
 * Does every block actually put ink on the canvas?
 *
 * The worst fault in this kit was not a shape drawn badly - it was eleven
 * geometry primitives that drew *nothing*, because each was waiting for a fill
 * the caller never passed. A gallery sheet showed it, but only because someone
 * looked. This renders every block alone on a white field and counts the pixels
 * that changed, so "it draws nothing" fails the build instead of the eye.
 *
 *     node motion/kit/verify.mjs            # exit 1 if anything is blank
 *     node motion/kit/verify.mjs --verbose
 */

import { createCanvas, GlobalFonts } from '@napi-rs/canvas';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { SHAPES, drawShape } from './shapes.mjs';
import { TYPE_MOVES, drawType } from './type.mjs';
import { ENTRANCES, BEHAVIOURS, EXITS, applyEntrance, applyBehaviour, applyExit } from './motion.mjs';
import { TRANSITIONS, TRANSITION_IDS } from './transitions.mjs';
import { drawMap, CITIES, REGIONS, project } from './world.mjs';
import { camera, withCamera, move as cameraMove, auditCamera, SHOTS } from './camera.mjs';
import { grade } from './light.mjs';
import { renderShot, auditShotList, totalDuration } from './stage.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FONT_DIR = path.resolve(HERE, '..', '..', 'assets', 'fonts');
if (fs.existsSync(FONT_DIR)) {
  for (const f of fs.readdirSync(FONT_DIR)) if (/\.(ttf|otf|woff2?)$/i.test(f)) GlobalFonts.registerFromPath(path.join(FONT_DIR, f));
}

const W = 320;
const H = 200;
const PALETTE = { text: '#12233F', caption: '#B4762A', dim: '#6E7683' };

/**
 * Percentage of pixels that differ from the background. A block below 0.2% is
 * drawing nothing anyone could see.
 */
function inkCoverage(paint) {
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, W, H);
  paint(ctx, canvas);
  const data = ctx.getImageData(0, 0, W, H).data;
  let changed = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i] < 250 || data[i + 1] < 250 || data[i + 2] < 250) changed += 1;
  }
  return (changed / (W * H)) * 100;
}

const results = [];
function check(group, id, paint, minimum = 0.2) {
  let coverage;
  let error = null;
  try {
    coverage = inkCoverage(paint);
  } catch (err) {
    error = err.message;
    coverage = 0;
  }
  results.push({ group, id, coverage, error, minimum });
}

for (const id of Object.keys(SHAPES)) {
  for (const p of [0.4, 1]) {
    check('shape', `${id}@${p}`, (ctx) => {
      drawShape(ctx, id, { x: W * 0.18, y: H * 0.14, w: W * 0.64, h: H * 0.72, p, palette: PALETTE });
    });
  }
}

for (const id of Object.keys(TYPE_MOVES)) {
  for (const p of [0.55, 1]) {
    check('type', `${id}@${p}`, (ctx) => {
      drawType(ctx, id, {
        value: 'Nokia lost its empire', x: W * 0.06, y: H * 0.58, p,
        size: 17, weight: 700, family: 'Inter', colour: PALETTE.text,
        accent: PALETTE.caption, align: 'left', span: W * 0.88, emphasis: 'empire',
      });
    });
  }
}

const box = { x: W * 0.1, y: H * 0.2, w: W * 0.8, h: H * 0.6 };
const artwork = (ctx) => {
  ctx.fillStyle = PALETTE.caption;
  ctx.fillRect(box.x, box.y, box.w, box.h);
};
for (const id of Object.keys(ENTRANCES)) {
  check('entrance', id, (ctx) => applyEntrance(ctx, id, { p: 0.5, t: 1, box, accent: PALETTE.caption }, () => artwork(ctx)));
}
for (const id of Object.keys(BEHAVIOURS)) {
  check('behaviour', id, (ctx) => applyBehaviour(ctx, id, { p: 0.5, t: 1, box, accent: PALETTE.caption }, () => artwork(ctx)));
}
for (const id of Object.keys(EXITS)) {
  check('exit', id, (ctx) => applyExit(ctx, id, { p: 0.4, box, accent: PALETTE.caption, draw: () => artwork(ctx) }, () => artwork(ctx)));
}

/**
 * Transitions are sampled at 20% and 80%, not at the midpoint.
 *
 * `fade` dips through white on purpose and `flash` peaks white - both are
 * legitimately blank at 0.5, and the midpoint of a `push` is the moment both
 * shots are half off-frame. A shot is a full-frame picture, though, so the test
 * frames have to be full-frame too, or a working push looks broken.
 */
for (const id of TRANSITION_IDS) {
  const frames = [0.2, 0.8].map((p) => (ctx) => {
    const a = (c = ctx) => { c.fillStyle = PALETTE.text; c.fillRect(0, 0, W, H); };
    const b = (c = ctx) => { c.fillStyle = PALETTE.caption; c.fillRect(0, 0, W, H); };
    TRANSITIONS[id](ctx, { a, b, p, w: W, h: H, palette: PALETTE });
  });
  // Best of the two, so a dip-through-white does not read as a failure.
  check('transition', id, (ctx) => {
    frames[0](ctx);
    const first = ctx.getImageData(0, 0, W, H);
    frames[1](ctx);
    void first;
  });
}

check('map', 'world', (ctx) => drawMap(ctx, { x: 8, y: 8, w: W - 16, h: H - 16, p: 1, palette: PALETTE }));
check('map', 'world-pins', (ctx) => drawMap(ctx, {
  x: 8, y: 8, w: W - 16, h: H - 16, p: 1, palette: PALETTE,
  pins: REGIONS.world.map((at) => ({ at, t: 1 })),
}));
check('map', 'world-arcs', (ctx) => drawMap(ctx, {
  x: 8, y: 8, w: W - 16, h: H - 16, p: 1, palette: PALETTE,
  arcs: [{ from: 'helsinki', to: 'tokyo', t: 1 }, { from: 'helsinki', to: 'newyork', t: 1 }],
}));

check('light', 'grade', (ctx) => {
  ctx.fillStyle = '#FAF8F3';
  ctx.fillRect(0, 0, W, H);
  grade(ctx, W, H, { frame: 2, bloomAt: [0.5, 0.5] });
});

/* -------------------------------------------------------------------------
 * Structural checks
 * ---------------------------------------------------------------------- */

const problems = [];

// Every city must project inside the frame, or a pin lands off-screen.
for (const [id, city] of Object.entries(CITIES)) {
  const q = project(city.lon, city.lat, 'equirect');
  if (q.x < 0.02 || q.x > 0.98 || q.y < 0.02 || q.y > 0.98) {
    problems.push(`city ${id} projects outside the frame at ${q.x.toFixed(2)}, ${q.y.toFixed(2)}`);
  }
}

// A camera framing is legal on its own; a camera *move* is what has a speed.
for (const shot of Object.keys(SHOTS)) {
  const notes = auditCamera(camera({ shot }), 3, { moving: false });
  if (notes.length) problems.push(`camera ${shot}: ${notes.join('; ')}`);
}
// And the rule has to actually fire, or it is decoration: a wide-to-macro in
// one second is a lurch and must be caught.
if (auditCamera(cameraMove('wide', 'macro', 1), 1, { moving: true }).length === 0) {
  problems.push('auditCamera let a 1-second wide-to-macro move through');
}
if (auditCamera(cameraMove('wide', 'medium', 4), 4, { moving: true }).length > 0) {
  problems.push('auditCamera rejected a 4-second wide-to-medium move, which is fine');
}

// And a shot list must obey the pacing rules.
const demos = [];
try {
  const mod = await import('../../films/nokia_scene1.mjs');
  demos.push(...(mod.SCENE1 || []));
} catch { /* the film is optional here */ }
if (demos.length) {
  const notes = auditShotList(demos);
  notes.forEach((n) => problems.push(`scene 1: ${n}`));
  if (totalDuration(demos) > 40) problems.push(`scene 1 runs ${totalDuration(demos)}s - the hook was written as 35`);
  // Render each shot once: a shot that throws is worse than a blank shape.
  const c = createCanvas(160, 90);
  const cx = c.getContext('2d');
  demos.forEach((shot) => {
    try {
      renderShot(cx, shot, shot.dur * 0.5, 160, 90, { frame: 0 });
    } catch (err) {
      problems.push(`shot ${shot.id} throws at half way: ${err.message}`);
    }
  });
}

/* -------------------------------------------------------------------------
 * Report
 * ---------------------------------------------------------------------- */

const blanks = results.filter((r) => r.error || r.coverage < r.minimum);
const groups = [...new Set(results.map((r) => r.group))];
const verbose = process.argv.includes('--verbose');

groups.forEach((g) => {
  const rows = results.filter((r) => r.group === g);
  const worst = rows.reduce((a, b) => (a.coverage <= b.coverage ? a : b));
  const bad = rows.filter((r) => r.error || r.coverage < r.minimum);
  const status = bad.length ? 'FAIL' : 'ok  ';
  console.log(`${status} ${g.padEnd(11)} ${String(rows.length).padStart(3)} checks, worst ${worst.coverage.toFixed(2)}% (${worst.id})`);
  if (verbose) rows.forEach((r) => console.log(`       ${r.id.padEnd(28)} ${r.coverage.toFixed(2)}%${r.error ? `  ${r.error}` : ''}`));
});

if (blanks.length) {
  console.log('\nBLANK OR BROKEN:');
  blanks.forEach((r) => console.log(`  ${r.group}/${r.id}: ${r.error || `${r.coverage.toFixed(3)}% of pixels changed`}`));
}
if (problems.length) {
  console.log('\nSTRUCTURE:');
  problems.forEach((p) => `  ${p}`.trim() && console.log(`  ${p}`));
}

const failed = blanks.length + problems.length;
console.log(`\n${results.length} visual checks, ${problems.length} structure notes, ${failed} failing`);
process.exit(failed ? 1 : 0);
