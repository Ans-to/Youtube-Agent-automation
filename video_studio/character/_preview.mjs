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
import { characterFrame, walkPose, speechTimeline } from './animate.mjs';

const argv = process.argv.slice(2);
const outArg = argv.indexOf('--out');
const out = outArg >= 0 ? argv[outArg + 1] : '/tmp/char.png';

const W = 1050;
const H = 1500;
const canvas = createCanvas(W, H);
const ctx = canvas.getContext('2d');
ctx.fillStyle = '#0A0E14';
ctx.fillRect(0, 0, W, H);

const ground = 1380;
const scale = 0.52;
const place = (x) => ({ x, y: ground - 780 * scale, scale });

// neutral, speaking, waving
drawCharacter(ctx, solve(neutralPose(), place(170)), { viseme: VISEMES.AA });

const line = speechTimeline(['EVERY', 'FRAME', 'IS', 'CODE'], { start: 0.2, end: 2.0 });
const speaking = characterFrame(0.9, { scale, groundY: ground, hipX: 500, speech: { timeline: line } });
drawCharacter(ctx, speaking.solved, {
  viseme: speaking.viseme, blink: speaking.blink, browRaise: speaking.browRaise, breathe: speaking.breath,
});

const wavePose = neutralPose();
const waveBase = solve(wavePose, place(830));
const shoulder = waveBase.armL.origin;
Object.assign(wavePose, twoBoneIK(waveBase, 'armL', 'forearmL',
  [shoulder[0] + 300 * scale, shoulder[1] - 300 * scale], 1));
wavePose.forearmL += 0.9;
drawCharacter(ctx, solve(wavePose, place(830)), { viseme: VISEMES.O, browRaise: 0.7 });

// walk strip
const strip = createCanvas(W, 620);
const sctx = strip.getContext('2d');
sctx.fillStyle = '#0A0E14';
sctx.fillRect(0, 0, W, 620);
for (let i = 0; i < 4; i += 1) {
  const frame = characterFrame(i * 0.29, {
    mode: 'walk', scale: 0.30, groundY: 590, hipX: 130 + i * 250, stride: 1.16,
  });
  drawCharacter(sctx, frame.solved, { viseme: i % 2 ? VISEMES.E : VISEMES.REST });
}

const sheet = createCanvas(W, H + 620);
const s2 = sheet.getContext('2d');
s2.drawImage(canvas, 0, 0);
s2.drawImage(strip, 0, H);
fs.writeFileSync(out, sheet.toBuffer('image/png'));
console.log('wrote ' + out);
