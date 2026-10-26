import fs from 'fs'; import path from 'path';
import { createCanvas, GlobalFonts } from '@napi-rs/canvas';
import { drawRoom } from './films/studio_hero.mjs';
for (const f of fs.readdirSync('./assets/fonts')) GlobalFonts.registerFromPath(path.join('./assets/fonts', f));
const W = 1280, H = 720, canvas = createCanvas(W, H), ctx = canvas.getContext('2d');
[3.6, 11.0, 17.4].forEach((t, i) => {
  ctx.clearRect(0,0,W,H); drawRoom(ctx, t);
  fs.writeFileSync(`/tmp/room-${i}.png`, canvas.toBuffer('image/png'));
});
console.log('ok');
