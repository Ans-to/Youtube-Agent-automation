/**
 * Nokia semantic/style correction: opening-only review pilot.
 *
 * Drawn with the original Nokia film's shot builders, type, palettes, optics
 * and product kit. This is not a replacement for the complete 15-minute film.
 * The plan quotes every spoken character in the covered lines and identifies
 * what each visual means; those structural checks do not judge meaning or
 * establish word-level synchronization. A human review is still required.
 *
 *   node video_studio/films/nokia_semantic_pilot.mjs --validate
 *   node video_studio/films/nokia_semantic_pilot.mjs --sample 6 --out /tmp/frame.png
 *   node video_studio/films/nokia_semantic_pilot.mjs --pipe --from 0 --to 150
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { optics, frameBuffer, opticsFor } from '../motion/kit/optics.mjs';
import { drawHandset } from '../motion/kit/product.mjs';
import { drawSmartphone, contact } from '../motion/kit/objects.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { W, H, typeShot, objectShot, chartShot, mapShot, compareShot } from './nokia_full.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const PLAN = path.join(HERE, 'nokia_semantic_pilot_plan.json');
const VOICE = path.join(ROOT, 'docs/media/nokia/nokia-15-minute-review-voice-timing.json');
const SHOTS = path.join(ROOT, 'docs/media/nokia/nokia-15-minute-review-shots.json');
const FPS = 30;
const SCALE = 1.5;
const clip = (x) => Math.max(0, Math.min(1, x));
const smooth = (x) => { const p = clip(x); return p * p * (3 - 2 * p); };
const VISUALS = new Set(['world', 'pocket', 'name', 'leadership', 'decline', 'smartphone', 'comparison']);

/** Structural traceability, not an automated determination of semantic truth. */
export function validatePlan(plan, voice, shots) {
  if (plan?.schema_version !== 1 || plan.fps !== FPS || !Array.isArray(plan.rows) || !plan.rows.length) {
    throw new Error('invalid pilot plan');
  }
  if (!Array.isArray(voice) || !Array.isArray(shots)) throw new Error('voice/shot clock missing');
  const lines = new Map(voice.map((x) => [x.shot, x]));
  const clock = new Map(shots.map((x) => [x.id, x]));
  const covered = [];
  let frame = plan.start_frame;
  let current = null;
  let char = 0;
  for (const row of plan.rows) {
    const line = lines.get(row.shot);
    const shot = clock.get(row.shot);
    if (!line || !shot || !VISUALS.has(row.visual) || !row.intent?.trim()) throw new Error('missing voice, shot, visual or intent');
    if (!Number.isInteger(row.start_frame) || !Number.isInteger(row.end_frame) ||
        row.start_frame !== frame || row.end_frame <= frame) throw new Error(`non-contiguous picture at ${row.shot}`);
    if (current !== row.shot) {
      if (current && char !== lines.get(current).text.length) throw new Error(`uncovered narration at ${current}`);
      if (covered.includes(row.shot)) throw new Error(`shot repeated out of order: ${row.shot}`);
      if (Math.abs(row.start_frame / FPS - shot.start) > 0.034) throw new Error(`wrong shot start: ${row.shot}`);
      current = row.shot; covered.push(row.shot); char = 0;
    } else if (row.start_frame / FPS < line.start || row.start_frame / FPS > line.end) {
      throw new Error(`interior cue outside narration: ${row.shot}`);
    }
    if (!Number.isInteger(row.char_start) || !Number.isInteger(row.char_end) || row.char_start !== char ||
        row.char_end <= char || line.text.slice(row.char_start, row.char_end) !== row.spoken_span) {
      throw new Error(`narration span differs or leaves a gap: ${row.shot}`);
    }
    char = row.char_end;
    frame = row.end_frame;
  }
  if (char !== lines.get(current).text.length || frame !== plan.end_frame ||
      Math.abs(frame / FPS - clock.get(current).end) > 0.034) throw new Error('pilot does not end on its covered shot');
  if (JSON.stringify(covered) !== JSON.stringify(shots.slice(0, covered.length).map((x) => x.id))) {
    throw new Error('pilot must cover the opening shots in order');
  }
  return { shots: covered.length, beats: plan.rows.length, frames: frame - plan.start_frame,
    duration: (frame - plan.start_frame) / FPS, timing: 'model-derived cue estimate; human listening required',
    semantic_review: 'unverified' };
}

function mapComposition() {
  const shot = mapShot('teal', { kicker: 'A COMPANY IN THE WORLD',
    caption: 'A company reaches around the world.', box: [0.085, 0.23, 0.83, 0.47],
    land: '#17635f', landEdge: 'rgba(220,244,236,0.55)' });
  const layer = shot.layers.find((x) => x.id === 'map');
  const destinations = ['london', 'lagos', 'delhi', 'beijing', 'newyork', 'sydney'];
  layer.draw = (ctx, { p }) => {
    const arcs = destinations.map((to, i) => ({ from: 'helsinki', to,
      t: smooth((p - 0.22 - i * 0.075) / 0.29), colour: 'rgba(226,185,79,0.70)',
      width: 1.7, head: false }));
    drawMap(ctx, { x: W * 0.085, y: H * 0.23, w: W * 0.83, h: H * 0.47,
      p: clip(p * 0.86), projection: 'winkel', land: '#17635f',
      landEdge: 'rgba(220,244,236,0.55)', graticule: true,
      graticuleColour: 'rgba(150,220,210,0.05)',
      palette: { land: '#17635f', landEdge: 'rgba(220,244,236,0.55)',
        text: '#E9F0E6', caption: '#D8B24A' }, arcs });
  };
  return shot;
}

function pocketComposition() {
  return objectShot('graphite', {
    kicker: 'CARRIED EVERYWHERE', caption: 'In their pockets.',
    draw: (ctx, { p }) => {
      // The product physically enters a drawn pocket: the motion itself carries
      // the narrated action. No photographic or pre-rendered image is used.
      const drop = smooth((p - 0.04) / 0.82);
      const x = W * 0.442, y = H * (0.16 + 0.19 * drop);
      drawHandset(ctx, { x, y, w: W * 0.116, h: H * 0.45,
        facing: 0.08, screen: 'menu', glow: 0.8, antenna: false });
      const px = W * 0.365, py = H * 0.50, pw = W * 0.27, ph = H * 0.30;
      ctx.save();
      const fabric = ctx.createLinearGradient(px, py, px + pw, py + ph);
      fabric.addColorStop(0, '#343940'); fabric.addColorStop(0.55, '#252a30');
      fabric.addColorStop(1, '#15191e');
      ctx.fillStyle = fabric; ctx.strokeStyle = 'rgba(218,220,218,0.28)'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + pw, py);
      ctx.lineTo(px + pw * 0.91, py + ph * 0.82); ctx.quadraticCurveTo(px + pw * 0.5, py + ph * 1.08, px + pw * 0.09, py + ph * 0.82);
      ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.setLineDash([5, 5]); ctx.strokeStyle = 'rgba(225,222,207,0.26)';
      ctx.beginPath(); ctx.moveTo(px + pw * 0.04, py + H * 0.022); ctx.lineTo(px + pw * 0.96, py + H * 0.022); ctx.stroke();
      ctx.restore();
    },
  });
}

function chart(world, opts) {
  const shot = chartShot(world, opts);
  // Extend the meaningful growth of the actual bars across the spoken beat,
  // rather than moving a completed still chart or adding decorative jitter.
  const bars = shot.layers.find((x) => x.id === 'bars');
  const draw = bars.draw;
  bars.draw = (ctx, local) => draw(ctx, { ...local, p: local.p * 0.59 });
  return shot;
}

function composition(kind) {
  if (kind === 'world') return mapComposition();
  if (kind === 'pocket') return pocketComposition();
  if (kind === 'name') return typeShot('gold', {
    lines: [
      { text: 'For millions of people,', size: 45, at: 0.04, colour: 'rgba(243,238,226,0.66)', gap: 0.12 },
      { text: 'that company was', size: 54, at: 0.55, colour: 'rgba(243,238,226,0.82)', gap: 0.13 },
      { text: 'Nokia.', size: 82, at: 0.73, colour: '#E2B94F' },
    ], top: 0.35,
  });
  if (kind === 'leadership') return chart('gold', {
    kicker: 'ALL PHONES SOLD · GARTNER · 2008', caption: 'Nokia led the market.',
    note: '38.6% of worldwide mobile-phone sales', base: 0.79, height: 0.27,
    bars: [{ label: 'Nokia', value: 38.6, hot: true }, { label: 'Samsung', value: 16.3, hot: false },
      { label: 'Motorola', value: 8.7, hot: false }, { label: 'LG', value: 8.4, hot: false },
      { label: 'Sony Ericsson', value: 7.6, hot: false }, { label: 'Others', value: 20.3, hot: false }], scaleMax: 40,
  });
  if (kind === 'decline') return chart('cold', {
    kicker: 'NOKIA · ALL PHONES SOLD · GARTNER', caption: 'A leader under pressure.',
    note: 'Worldwide market share, 2008–2013', base: 0.79, height: 0.27,
    bars: [{ label: '2008', value: 38.6, hot: true }, { label: '2009', value: 36.4, hot: false },
      { label: '2011', value: 23.8, hot: false }, { label: '2012', value: 19.1, hot: false },
      { label: '2013', value: 13.9, hot: false }], scaleMax: 40,
  });
  if (kind === 'smartphone') return objectShot('cobalt', {
    kicker: 'A NEW GENERATION', caption: 'The smartphone arrives.',
    draw: (ctx, { p }) => {
      const reveal = smooth(p / 0.85);
      contact(ctx, W * 0.5, H * 0.845, W * 0.14, H * 0.018, 0.48);
      drawSmartphone(ctx, { x: W * 0.44, y: H * 0.23, w: W * 0.12, h: H * 0.54,
        glow: 0.7, apps: Math.round(12 * reveal) });
    },
  });
  if (kind === 'comparison') return compareShot('graphite', {
    kicker: 'THE INTERACTION CHANGED', caption: 'Touchscreens replaced buttons.',
    leftLabel: 'KEYPAD', rightLabel: 'TOUCHSCREEN',
    left: (ctx) => drawHandset(ctx, { x: W * 0.20, y: H * 0.30, w: W * 0.11, h: H * 0.44,
      facing: 0.12, screen: 'menu', glow: 0.5, antenna: false }),
    right: (ctx, { p }) => drawSmartphone(ctx, { x: W * 0.66, y: H * 0.28, w: W * 0.10, h: H * 0.46,
      glow: 0.7, apps: Math.round(12 * smooth((p - 0.12) / 0.75)) }),
  });
  throw new Error(`no composition for ${kind}`);
}

export function makeShots(plan) {
  return plan.rows.map((row, i) => {
    const shot = composition(row.visual);
    // The house builders normally fade in from an empty field. On a spoken
    // cut that delayed the subject after the words began, creating a semantic
    // gap. Start their explanatory layers partway through their entrance so the
    // relevant object/graph is already visible; the remaining build still plays.
    shot.layers = shot.layers.map((layer) => {
      if (layer.id === 'field' || layer.id === 'air') return layer;
      const draw = layer.draw;
      return { ...layer, draw: (ctx, local) => draw(ctx, { ...local, p: 0.28 + local.p * 0.72 }) };
    });
    return { ...shot, id: `${row.shot}-${i + 1}`, dur: (row.end_frame - row.start_frame) / FPS,
      transition: { kind: 'cut', label: 'cut', options: {} },
      // The semantic motion above is the animation. Do not rely on a camera pan
      // or on grain to make an otherwise unrelated still seem animated.
      drift: false, camera: () => ({ zoom: 1, at: [0.5, 0.5], rotate: 0 }) };
  });
}

async function main() {
  const args = process.argv.slice(2);
  const get = (flag, fallback = null) => { const i = args.indexOf(flag); return i < 0 ? fallback : args[i + 1]; };
  const plan = JSON.parse(fs.readFileSync(PLAN, 'utf8'));
  const voice = JSON.parse(fs.readFileSync(VOICE, 'utf8'));
  const shots = JSON.parse(fs.readFileSync(SHOTS, 'utf8'));
  const result = validatePlan(plan, voice, shots);
  if (args.includes('--validate')) { console.log(JSON.stringify(result, null, 2)); return; }
  loadFonts();
  const pictures = makeShots(plan);
  const width = Math.round(W * SCALE), height = Math.round(H * SCALE);
  const canvas = createCanvas(width, height), ctx = canvas.getContext('2d');
  const renderer = createRenderer(pictures, W, H, { join: 0, background: pictures[0].background, scale: SCALE });
  const fb = frameBuffer(width, height);
  const paint = (frame) => {
    const t = frame / FPS;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, width, height);
    renderer.render(ctx, t);
    fb.ctx.setTransform(1, 0, 0, 1, 0, 0); fb.ctx.clearRect(0, 0, width, height); fb.ctx.drawImage(canvas, 0, 0);
    let elapsed = 0;
    const shot = pictures.find((s) => { elapsed += s.dur; return t < elapsed; }) || pictures[pictures.length - 1];
    optics(ctx, { source: fb.canvas, w: width, h: height, frame, ...opticsFor(shot) });
  };
  if (get('--sample') !== null) {
    const seconds = Number(get('--sample')); const output = get('--out');
    if (!Number.isFinite(seconds) || seconds < 0 || seconds >= result.duration || !output) throw new Error('invalid sample time/output');
    paint(Math.round(seconds * FPS));
    fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
    fs.writeFileSync(path.resolve(output), canvas.toBuffer('image/png'));
    return;
  }
  if (args.includes('--pipe')) {
    const from = Number(get('--from', 0)), to = Number(get('--to', result.frames));
    if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to > result.frames || to <= from) throw new Error('invalid frame range');
    for (let i = from; i < to; i += 1) {
      paint(i);
      if (!process.stdout.write(canvas.data())) await new Promise((resolve) => process.stdout.once('drain', resolve));
    }
    return;
  }
  throw new Error('specify --validate, --sample, or --pipe');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => { console.error(`Nokia semantic pilot: ${error.message}`); process.exitCode = 2; });
}
