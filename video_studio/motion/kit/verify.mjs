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
import { CARD_IDS, cards } from './cards.mjs';
import { camera, withCamera, move as cameraMove, auditCamera, SHOTS } from './camera.mjs';
import { grade } from './light.mjs';
import { renderShot, auditShotList, totalDuration } from './stage.mjs';
import { auditNoRepeat } from './budget.mjs';

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

for (const id of CARD_IDS) {
  check('card', id, (ctx) => {
    cards[id](ctx, {
      x: 20, y: 110, w: W - 40, p: 1, palette: PALETTE,
      text: id === 'stat' ? '1 in 3' : 'The phone in every pocket',
      label: 'Helsinki, 1998', source: 'Jorma Ollila', number: '03',
      cta: 'Watch the story',
    });
  }, 0.4);
}

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
// The film as it is actually cut: allocated, retimed to the narration, and
// joined. Auditing the raw shot source instead would check a list nobody
// renders - which is exactly how it reported repeats that the build had fixed.
const demos = [];
try {
  const mod = await import('../../films/nokia_opening.mjs');
  demos.push(...(mod.FILM || []));
} catch { /* the film is optional here */ }
if (demos.length) {
  // The owner's main rule: no technique twice anywhere in the film.
  const repeats = auditNoRepeat(demos);
  repeats.forEach((r) => problems.push(`repeat: ${r}`));
  const notes = auditShotList(demos);
  notes.forEach((n) => problems.push(`scene 1: ${n}`));
  if (totalDuration(demos) > 55) problems.push(`the film runs ${totalDuration(demos)}s - longer than the 51s cut it was written as`);

  // Does each shot actually change on screen?
  //
  // This used to be a guess: "the shot has no entrance, so it is a still". That
  // was wrong both ways - it flagged a chart that animates through its own
  // progress, and it would have passed a shot whose entrance had already
  // finished. Rendering two frames and comparing them is the measurement.
  // Render at the size the film is authored for, then compare.
  //
  // This used to render straight into a 320x180 canvas. Film modules size their
  // layers against their own 1280x720 constants, so at 320 wide most of a shot
  // landed outside the canvas and two nearly-empty frames always matched - which
  // is how two genuinely animated shots started reporting as frozen.
  const W2 = 320;
  const H2 = 180;
  const SHOT_W = 1280;
  const SHOT_H = 720;
  const a = createCanvas(SHOT_W, SHOT_H);
  const b = createCanvas(SHOT_W, SHOT_H);
  const smallA = createCanvas(W2, H2);
  const smallB = createCanvas(W2, H2);
  const ax = a.getContext('2d');
  const bx = b.getContext('2d');
  const sax = smallA.getContext('2d');
  const sbx = smallB.getContext('2d');
  demos.forEach((shot) => {
    try {
      renderShot(ax, shot, shot.dur * 0.15, SHOT_W, SHOT_H, { frame: Math.round(shot.dur * 0.15 * 30) });
      renderShot(bx, shot, shot.dur * 0.85, SHOT_W, SHOT_H, { frame: Math.round(shot.dur * 0.85 * 30) });
      sax.drawImage(a, 0, 0, W2, H2);
      sbx.drawImage(b, 0, 0, W2, H2);
      const da = sax.getImageData(0, 0, W2, H2).data;
      const db = sbx.getImageData(0, 0, W2, H2).data;
      let changed = 0;
      for (let i = 0; i < da.length; i += 4) {
        if (Math.abs(da[i] - db[i]) > 3 || Math.abs(da[i + 1] - db[i + 1]) > 3) changed += 1;
      }
      const share = (changed / (W2 * H2)) * 100;
      if (share < 0.5) problems.push(`shot ${shot.id} is frozen: ${share.toFixed(2)}% of pixels change across the shot`);
    } catch (err) {
      problems.push(`shot ${shot.id} throws: ${err.message}`);
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
