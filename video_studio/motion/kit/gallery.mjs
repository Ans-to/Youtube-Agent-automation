#!/usr/bin/env node
/**
 * Draw every shape, every type move and every transition, so they can be looked at.
 *
 *     node motion/kit/gallery.mjs --out /tmp/kit
 *
 * A library nobody has seen is a library nobody can trust. This renders one
 * contact sheet per family with each item labelled and drawn at three progress
 * values, so a defect - a shape that collapses, a move that never completes - is
 * visible in a single image instead of a full render.
 */
import { createCanvas, GlobalFonts } from '@napi-rs/canvas';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { UI, text } from '../ui.mjs';
import { SHAPES, drawShape } from './shapes.mjs';
import { TYPE_MOVES, drawType } from './type.mjs';
import { ENTRANCES, BEHAVIOURS, EXITS, applyEntrance, applyBehaviour, applyExit } from './motion.mjs';
import { TRANSITIONS, TRANSITION_IDS } from './transitions.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const FONT_DIR = path.join(ROOT, 'assets', 'fonts');

// The studio's own faces, if the asset folder is present; otherwise the system's.
if (fs.existsSync(FONT_DIR)) {
  for (const file of fs.readdirSync(FONT_DIR)) {
    if (/\.(ttf|otf|woff2?)$/i.test(file)) GlobalFonts.registerFromPath(path.join(FONT_DIR, file));
  }
}

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, arg, i, all) => {
  if (arg.startsWith('--')) pairs.push([arg.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]);
  return pairs;
}, []));
const OUT = path.resolve(args.out || '/tmp/kit');
fs.mkdirSync(OUT, { recursive: true });

const W = 1600;
const H = 1000;
const PALETTE = { text: '#12233F', caption: '#B4762A', dim: '#7A828F' };

function sheet(title, entries, columns, cell, painter) {
  const rows = Math.ceil(entries.length / columns);
  const canvas = createCanvas(W, H + rows * cell.h + 90);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#F7F8FA';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  text(ctx, title, 40, 54, { size: 30, weight: 700, family: 'Inter', color: UI.text });
  text(ctx, `${entries.length} items`, 40, 82, { size: 18, weight: 500, family: 'Inter', color: UI.dim });
  entries.forEach((entry, i) => {
    const col = i % columns;
    const row = Math.floor(i / columns);
    const x = 40 + col * (cell.w + 12);
    const y = 110 + row * (cell.h + 12);
    ctx.save();
    ctx.fillStyle = '#FFFFFF';
    ctx.strokeStyle = '#DCDCE2';
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, cell.w, cell.h);
    // Each cell is a frame: artwork that overflows is a defect in the artwork, and
    // without a clip the gallery hides it by painting over the neighbour, which is
    // how two overlapping type moves looked like one broken one.
    ctx.save();
    ctx.beginPath();
    ctx.rect(x + 1, y + 1, cell.w - 2, cell.h - 2);
    ctx.clip();
    painter(ctx, entry, x, y, cell);
    ctx.restore();
    ctx.strokeRect(x, y, cell.w, cell.h);
    ctx.fillStyle = UI.text;
    text(ctx, entry.id, x + 8, y + cell.h - 8, { size: 13, weight: 600, family: 'Inter', color: '#4A5260' });
    ctx.restore();
  });
  return canvas;
}

// ---------------------------------------------------------------- shape sheet
const shapeEntries = Object.values(SHAPES);
const byFamily = {
  geometry: shapeEntries.filter((s) => s.family === 'geometry'),
  object: shapeEntries.filter((s) => s.family === 'object'),
  data: shapeEntries.filter((s) => s.family === 'data'),
  diagram: shapeEntries.filter((s) => s.family === 'diagram'),
};

for (const [family, entries] of Object.entries(byFamily)) {
  const columns = 6;
  const cell = { w: 250, h: 150 };
  const canvas = sheet(`Shapes: ${family}`, entries, columns, cell, (ctx, entry, x, y, c) => {
    const pad = 18;
    drawShape(ctx, entry.id, {
      x: x + pad, y: y + pad, w: c.w - pad * 2, h: c.h - pad * 2 - 14,
      p: 1, palette: PALETTE, params: {},
    });
  });
  const file = path.join(OUT, `shapes-${family}.png`);
  fs.writeFileSync(file, canvas.toBuffer('image/png'));
  console.log(`wrote ${file}`);
}

// ----------------------------------------------------------------- type sheet
const typeEntries = Object.keys(TYPE_MOVES).map((id) => ({ id }));
{
  const columns = 3;
  const cell = { w: 500, h: 200 };
  const canvas = sheet('Kinetic type, at half progress', typeEntries, columns, cell, (ctx, entry, x, y, c) => {
    ctx.save();
    // Centred, because one of the moves (path-text) lays its characters out about
    // a centre point rather than from a left edge - drawn from x=0 it hung off the
    // side of the cell and the clip cut it in half.
    ctx.translate(x + c.w / 2, y + 30);
    drawType(ctx, entry.id, {
      value: 'Nokia lost its empire',
      x: 0, y: c.h * 0.48, p: 0.55, size: 34, weight: 700, family: 'Inter',
      colour: '#12233F', accent: '#B4762A', align: 'center', span: c.w - 40, emphasis: 'empire',
    });
    ctx.restore();
  });
  const file = path.join(OUT, 'type-moves.png');
  fs.writeFileSync(file, canvas.toBuffer('image/png'));
  console.log(`wrote ${file}`);
}

// -------------------------------------------------------------- motion sheets
function artwork(ctx, box) {
  // A neutral piece of art: three bars and a disc. Every move applies to it.
  ctx.fillStyle = '#12233F';
  for (let i = 0; i < 3; i += 1) {
    roundBar(ctx, box.x + box.w * 0.08, box.y + box.h * (0.2 + i * 0.24), box.w * 0.84 * (1 - i * 0.18), box.h * 0.12);
  }
  ctx.fillStyle = '#B4762A';
  ctx.beginPath();
  ctx.arc(box.x + box.w * 0.82, box.y + box.h * 0.82, Math.min(box.w, box.h) * 0.10, 0, Math.PI * 2);
  ctx.fill();
}

function roundBar(ctx, x, y, w, h) {
  const r = Math.min(h / 2, 8);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  ctx.fill();
}

function motionSheet(title, ids, file, applicator) {
  const columns = 5;
  const cell = { w: 290, h: 190 };
  const entries = ids.map((id) => ({ id }));
  const canvas = sheet(title, entries, columns, cell, (ctx, entry, x, y, c) => {
    const box = { x: x + 22, y: y + 20, w: c.w - 44, h: c.h - 56 };
    applicator(ctx, entry.id, box);
  });
  fs.writeFileSync(path.join(OUT, file), canvas.toBuffer('image/png'));
  console.log(`wrote ${path.join(OUT, file)}`);
}

motionSheet('Entrances, at 35%', Object.keys(ENTRANCES), 'motion-entrances.png', (ctx, id, box) => {
  applyEntrance(ctx, id, { p: 0.35, box, accent: '#B4762A', ink: '#12233F' }, () => artwork(ctx, box));
});

motionSheet('Behaviours, at half the shot', Object.keys(BEHAVIOURS), 'motion-behaviours.png', (ctx, id, box) => {
  applyBehaviour(ctx, id, { t: 1.5, seconds: 3, box }, () => artwork(ctx, box));
});

motionSheet('Exits, at 55%', Object.keys(EXITS), 'motion-exits.png', (ctx, id, box) => {
  applyExit(ctx, id, { p: 0.55, box }, () => artwork(ctx, box));
});

// ---------------------------------------------------------- transition sheets
for (const at of [0.25, 0.5, 0.75]) {
  const columns = 4;
  const cell = { w: 380, h: 230 };
  const entries = TRANSITION_IDS.map((id) => ({ id }));
  const canvas = sheet(`Transitions at ${Math.round(at * 100)}%`, entries, columns, cell, (ctx, entry, x, y, c) => {
    const w = c.w - 20;
    const h = c.h - 40;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x + 10, y + 10, w, h);
    ctx.clip();
    ctx.translate(x + 10, y + 10);
    const a = () => {
      ctx.fillStyle = '#E7EAF0';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#12233F';
      roundBar(ctx, w * 0.12, h * 0.3, w * 0.6, h * 0.08);
      roundBar(ctx, w * 0.12, h * 0.48, w * 0.4, h * 0.08);
    };
    const b = () => {
      ctx.fillStyle = '#F3E7D6';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#B4762A';
      roundBar(ctx, w * 0.12, h * 0.34, w * 0.7, h * 0.10);
      ctx.beginPath();
      ctx.arc(w * 0.78, h * 0.68, h * 0.14, 0, Math.PI * 2);
      ctx.fill();
    };
    const fn = TRANSITIONS[entry.id];
    fn(ctx, {
      a, b, p: at, w, h, direction: 'left', accent: '#B4762A',
      word: (c2, { p }) => {
        c2.save();
        c2.globalAlpha *= 0.9;
        text(c2, 'ECOSYSTEM', w / 2, h / 2, {
          size: 30 + p * 20, weight: 800, family: 'Inter', color: '#12233F', align: 'center',
        });
        c2.restore();
      },
    });
    ctx.restore();
  });
  const file = path.join(OUT, `transitions-${Math.round(at * 100)}.png`);
  fs.writeFileSync(file, canvas.toBuffer('image/png'));
  console.log(`wrote ${file}`);
}

console.log(`\nshapes: ${Object.keys(SHAPES).length}`
  + `  type moves: ${Object.keys(TYPE_MOVES).length}`
  + `  entrances: ${Object.keys(ENTRANCES).length}`
  + `  behaviours: ${Object.keys(BEHAVIOURS).length}`
  + `  exits: ${Object.keys(EXITS).length}`
  + `  transitions: ${TRANSITION_IDS.length}`);
