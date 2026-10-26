/**
 * Render a film straight into an encoder.
 *
 * Writing 1080p PNGs to disk and letting ffmpeg read them back cost more than
 * drawing the film: 1716 frames of PNG is four gigabytes of encoding, and the
 * render spent about three quarters of its time compressing still images that
 * were about to be thrown away. Piping raw frames to ffmpeg removes the round
 * trip and the disk.
 *
 *   node render_to_video.mjs --film ./films/nokia_atlas.mjs \
 *        --out /tmp/film.mp4 --scale 1.5 --fps 30
 *   node render_to_video.mjs --film ... --out /tmp/film.mp4 --frames /tmp/png  # both
 */
import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { createCanvas } from '@napi-rs/canvas';
import { createRenderer } from './motion/kit/timeline.mjs';
import { loadFonts } from './motion/kit/fonts.mjs';
import { optics, frameBuffer, opticsFor } from './motion/kit/optics.mjs';

const args = process.argv.slice(2);
const flag = (k, d = null) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };

const filmPath = path.resolve(flag('--film', './films/nokia_atlas.mjs'));
const out = flag('--out');
const pngDir = flag('--frames');
const fps = Number(flag('--fps', '30'));
const scale = Number(flag('--scale', '1'));
const crf = flag('--crf', '19');
const preset = flag('--preset', 'medium');
const ffmpeg = process.env.FFMPEG || 'ffmpeg';

if (!out && !pngDir) {
  console.error('usage: node render_to_video.mjs --film <file> (--out <mp4> | --frames <dir>)');
  process.exit(2);
}

loadFonts();
const mod = await import(filmPath);
const { FILM } = mod;
const W = mod.SIZE.W;
const H = mod.SIZE.H;
const shotAt = mod.shotAt || (() => FILM[0]);
const dw = Math.round(W * scale);
const dh = Math.round(H * scale);

const canvas = createCanvas(dw, dh);
const ctx = canvas.getContext('2d');
const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background, scale });
const fb = frameBuffer(dw, dh);

const paint = (t, frame) => {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, dw, dh);
  renderer.render(ctx, t);
  fb.ctx.setTransform(1, 0, 0, 1, 0, 0);
  fb.ctx.clearRect(0, 0, dw, dh);
  fb.ctx.drawImage(canvas, 0, 0);
  optics(ctx, { source: fb.canvas, w: dw, h: dh, frame, ...opticsFor(shotAt(t)) });
};

const total = Math.round(renderer.duration * fps);
console.log(`${path.basename(filmPath)}: ${renderer.duration.toFixed(1)}s, ${total} frames at ${dw}x${dh}`);

if (pngDir) fs.mkdirSync(pngDir, { recursive: true });

const encoder = out
  ? spawn(ffmpeg, [
    '-y', '-loglevel', 'error',
    '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${dw}x${dh}`, '-r', String(fps), '-i', '-',
    '-c:v', 'libx264', '-preset', preset, '-crf', crf,
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] })
  : null;

const write = (buf) => new Promise((resolve) => {
  if (!encoder) return resolve();
  if (encoder.stdin.write(buf)) return resolve();
  encoder.stdin.once('drain', resolve);
});

const started = Date.now();
for (let i = 0; i < total; i += 1) {
  const t = i / fps;
  paint(t, i);
  if (pngDir) {
    fs.writeFileSync(path.join(pngDir, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
  }
  if (encoder) {
    const img = ctx.getImageData(0, 0, dw, dh);
    await write(Buffer.from(img.data.buffer, img.data.byteOffset, img.data.byteLength));
  }
  if (i % 120 === 0 || i === total - 1) {
    const rate = (i + 1) / ((Date.now() - started) / 1000);
    process.stdout.write(`\r  ${i + 1}/${total} frames  ${rate.toFixed(1)} fps  `);
  }
}
process.stdout.write('\n');

if (encoder) {
  encoder.stdin.end();
  await new Promise((resolve, reject) => {
    encoder.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`ffmpeg exited ${code}`))));
  });
  console.log(`wrote ${out}`);
}
