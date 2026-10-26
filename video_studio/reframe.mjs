/**
 * Re-render part of a cut, and leave the rest alone.
 *
 * Fixing one shot should not cost a full render. This renders a time range of a
 * film back into an existing frame directory, so a shot can be improved after the
 * film has been approved and conformed without touching a frame of the others.
 *
 *   node reframe.mjs --film films/nokia_atlas.mjs --frames /tmp/atlas-frames \
 *                    --from 26.4 --to 32.4
 */
import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';
import { createRenderer } from './motion/kit/timeline.mjs';
import { loadFonts } from './motion/kit/fonts.mjs';

const args = process.argv.slice(2);
const flag = (k, d = null) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };

const filmPath = path.resolve(flag('--film', './films/nokia_atlas.mjs'));
const framesDir = flag('--frames');
const fps = Number(flag('--fps', '30'));
if (!framesDir) {
  console.error('usage: node reframe.mjs --film <file> --frames <dir> [--from s] [--to s]');
  process.exit(2);
}

loadFonts();
const mod = await import(filmPath);
const { FILM } = mod;
const W = mod.SIZE?.W ?? 1280;
const H = mod.SIZE?.H ?? 720;

const canvas = createCanvas(W, H);
const ctx = canvas.getContext('2d');
const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background });

const from = Number(flag('--from', '0'));
const to = Number(flag('--to', String(renderer.duration)));
const first = Math.max(0, Math.round(from * fps));
const last = Math.min(Math.round(renderer.duration * fps) - 1, Math.round(to * fps));

let n = 0;
for (let i = first; i <= last; i += 1) {
  ctx.clearRect(0, 0, W, H);
  renderer.render(ctx, i / fps);
  fs.writeFileSync(path.join(framesDir, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
  n += 1;
}
console.log(`reframed ${n} frames (${(first / fps).toFixed(2)}s - ${(last / fps).toFixed(2)}s) into ${framesDir}`);
