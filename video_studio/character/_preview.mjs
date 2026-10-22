#!/usr/bin/env node
/**
 * Developer preview for the character rig: pose sheet + walk strip.
 *   node character/_preview.mjs [--out /tmp/char.png]
 */
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire(import.meta.url);
const { createCanvas } = require('@napi-rs/canvas');

import { solve, neutralPose, twoBoneIK, VISEMES } from './rig.mjs';
import { drawCharacter } from './body.mjs';
import { drawStick, resolveInk } from './stick.mjs';
import { EXPRESSIONS } from './expression.mjs';
import { characterFrame, walkPose, speechTimeline } from './animate.mjs';

const argv = process.argv.slice(2);
const outArg = argv.indexOf('--out');
const out = outArg >= 0 ? argv[outArg + 1] : '/tmp/char.png';
const styleArg = argv.indexOf('--style');
const style = styleArg >= 0 ? argv[styleArg + 1] : 'design';
const boilArg = argv.indexOf('--boil');
const boil = boilArg >= 0 ? Number(argv[boilArg + 1]) : 0;
if (!['design', 'stick'].includes(style)) {
  console.error('unknown --style ' + style + ' (expected design or stick)');
  process.exit(2);
}
const draw = style === 'stick' ? drawStick : drawCharacter;
// The stick figure needs its own paper, and the pose sheet is a drawing, not a
// frame, so the boil sample is fixed per figure rather than animated.
const paper = style === 'stick' ? resolveInk({}).paper : '#0A0E14';
const sheetOpts = (extra = {}) => (style === 'stick'
  ? { boil, frame: 0, cape: true, expression: EXPRESSIONS.talk, ...extra }
  : extra);

const W = 1050;
const H = 1500;
const canvas = createCanvas(W, H);
const ctx = canvas.getContext('2d');
ctx.fillStyle = paper;
ctx.fillRect(0, 0, W, H);

const ground = 1380;
const scale = 0.52;
const place = (x) => ({ x, y: ground - 780 * scale, scale });

// neutral, speaking, waving
draw(ctx, solve(neutralPose(), place(170)), sheetOpts({ viseme: VISEMES.AA }));

const line = speechTimeline(['EVERY', 'FRAME', 'IS', 'CODE'], { start: 0.2, end: 2.0 });
const speaking = characterFrame(0.9, { scale, groundY: ground, hipX: 500, speech: { timeline: line } });
draw(ctx, speaking.solved, sheetOpts({
  viseme: speaking.viseme, blink: speaking.blink, browRaise: speaking.browRaise, breathe: speaking.breath,
}));

const wavePose = neutralPose();
const waveBase = solve(wavePose, place(830));
const shoulder = waveBase.armL.origin;
Object.assign(wavePose, twoBoneIK(waveBase, 'armL', 'forearmL',
  [shoulder[0] + 300 * scale, shoulder[1] - 300 * scale], 1));
wavePose.forearmL += 0.9;
draw(ctx, solve(wavePose, place(830)), sheetOpts({ viseme: VISEMES.O, browRaise: 0.7 }));

// walk strip
const strip = createCanvas(W, 620);
const sctx = strip.getContext('2d');
sctx.fillStyle = paper;
sctx.fillRect(0, 0, W, 620);
for (let i = 0; i < 4; i += 1) {
  const frame = characterFrame(i * 0.29, {
    mode: 'walk', scale: 0.30, groundY: 590, hipX: 130 + i * 250, stride: 1.16,
  });
  draw(sctx, frame.solved, sheetOpts({ viseme: i % 2 ? VISEMES.E : VISEMES.REST, frame: i * 3 }));
}

const sheet = createCanvas(W, H + 620);
const s2 = sheet.getContext('2d');
s2.drawImage(canvas, 0, 0);
s2.drawImage(strip, 0, H);
fs.writeFileSync(out, sheet.toBuffer('image/png'));
console.log('wrote ' + out + ' (' + style + ' style' + (boil ? ', boil ' + boil : '') + ')');
