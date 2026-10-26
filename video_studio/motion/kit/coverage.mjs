/**
 * How much of the frame is actually doing something.
 *
 * The films passed every gate and still had shots that sat empty for seconds.
 * No audit caught it, because every audit looked at layers, labels and timing -
 * never at the pixels the viewer sees. This one reads the rendered frames and
 * reports, per sample, the share of the frame that differs from its own
 * background.
 *
 * Coverage is not a quality score: a good shot can be 8 % ink and a bad one can
 * be 40 %. It is a floor. A frame under a few percent is a blank screen with a
 * caption on it.
 */
import { loadImage, createCanvas } from '@napi-rs/canvas';
import fs from 'fs';
import path from 'path';

const SAMPLE_W = 320;

/** Load a frame, shrink it, and return luma as a flat array. */
async function luma(file) {
  const img = await loadImage(file);
  const h = Math.round((SAMPLE_W * img.height) / img.width);
  const canvas = createCanvas(SAMPLE_W, h);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0, SAMPLE_W, h);
  const { data } = ctx.getImageData(0, 0, SAMPLE_W, h);
  const out = new Float32Array(SAMPLE_W * h);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = 0.2126 * data[i * 4] + 0.7152 * data[i * 4 + 1] + 0.0722 * data[i * 4 + 2];
  }
  return out;
}

/**
 * The background of a frame is its median luma: whatever most of the screen is.
 * Ink is anything that leaves it by more than `threshold`.
 */
function inkShare(pixels, threshold) {
  const sorted = Float32Array.from(pixels).sort();
  const median = sorted[Math.floor(sorted.length / 2)];
  let ink = 0;
  let darkest = 255;
  let brightest = 0;
  let sum = 0;
  let sumSq = 0;
  for (let i = 0; i < pixels.length; i += 1) {
    if (Math.abs(pixels[i] - median) > threshold) ink += 1;
    if (pixels[i] < darkest) darkest = pixels[i];
    if (pixels[i] > brightest) brightest = pixels[i];
    sum += pixels[i];
    sumSq += pixels[i] * pixels[i];
  }
  const mean = sum / pixels.length;
  const std = Math.sqrt(Math.max(0, sumSq / pixels.length - mean * mean));
  return {
    ink: ink / pixels.length,
    range: (brightest - darkest) / 255,
    // Spread and contrast are palette-independent; "ink" is not. On a dark shot
    // most of the frame sits near the median and only the drawn lines leave it,
    // so ink alone called a full chart an empty screen.
    std: std / 255,
    median: median / 255,
  };
}

/**
 * Walk a frame directory and report every sample.
 *
 * @param {string} dir      directory of numbered PNGs
 * @param {object} options  { step, threshold, fps }
 */
export async function auditCoverage(dir, { step = 15, threshold = 10, fps = 30 } = {}) {
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.png')).sort();
  const samples = [];
  for (let i = 0; i < files.length; i += step) {
    const pixels = await luma(path.join(dir, files[i]));
    const result = inkShare(pixels, threshold);
    samples.push({ frame: i, t: i / fps, ...result });
  }
  const inks = samples.map((s) => s.ink).sort((a, b) => a - b);
  const empty = samples.filter((s) => s.ink < 0.04 && s.range < 0.12 && s.std < 0.02);
  return {
    samples,
    frames: files.length,
    medianInk: inks[Math.floor(inks.length / 2)] || 0,
    minInk: inks[0] || 0,
    empty: empty.map((s) => +s.t.toFixed(2)),
    // A shot that keeps one still frame on screen is not motion. This is the
    // cheapest possible check for "nothing is happening".
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('usage: node motion/kit/coverage.mjs <frames-dir> [--step n]');
    process.exit(1);
  }
  const stepArg = process.argv.indexOf('--step');
  const step = stepArg > -1 ? Number(process.argv[stepArg + 1]) : 15;
  const report = await auditCoverage(dir, { step });
  for (const s of report.samples) {
    const bar = '#'.repeat(Math.round(s.ink * 60));
    console.log(`${s.t.toFixed(2).padStart(6)}s  ink ${(s.ink * 100).toFixed(1).padStart(5)}%  contrast ${(s.std * 100).toFixed(0).padStart(3)}%  range ${(s.range * 100).toFixed(0).padStart(3)}%  ${bar}`);
  }
  console.log(`\nframes ${report.frames}  median ink ${(report.medianInk * 100).toFixed(1)}%  min ${(report.minInk * 100).toFixed(1)}%`);
  console.log(`effectively empty (flat and low contrast): ${report.empty.length}${report.empty.length ? ' at ' + report.empty.join('s, ') + 's' : ''}`);
}
