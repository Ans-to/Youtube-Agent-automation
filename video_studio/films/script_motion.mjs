/**
 * Script-first, code-drawn motion graphics. Uses the same 1280x720 design
 * space, dark cinematic fields, gold/teal palette, house fonts and product kit
 * as the Nokia film. There are no photographs, downloaded pictures or AI
 * backplates. The visual primitive is chosen from meaning, never duration.
 *
 *   node video_studio/films/script_motion.mjs --plan render-plan.json --validate
 *   node video_studio/films/script_motion.mjs --plan render-plan.json --sample 2 --out frame.png
 *   node video_studio/films/script_motion.mjs --plan render-plan.json --pipe
 *
 * Measured line boundaries are not word alignment. A named person must watch
 * and listen to every beat of the encoded output before approval.
 */
import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { drawHandset } from '../motion/kit/product.mjs';
import { drawSmartphone } from '../motion/kit/objects.mjs';
import { roundRect } from '../motion/ui.mjs';
import { chartBarState } from '../motion/chart.mjs';

const W = 1280, H = 720, FPS = 30;
const GOLD = '#E2B94F', INK = '#F3EEE2', SOFT = '#C5D5CB', RED = '#E57868';
const clamp = (n) => Math.max(0, Math.min(1, n));
const smooth = (n) => { n = clamp(n); return n * n * (3 - 2 * n); };
const palettes = {
  calm: ['#071110', '#11302D'], warm: ['#160E08', '#3B2716'],
  moving: ['#071215', '#12333B'], tense: ['#0E0B0D', '#391917'],
  sparse: ['#0D0E12', '#252930'], history: ['#171006', '#443019'],
  build: ['#090D17', '#172E4B'], resolve: ['#0B0B0D', '#302819'],
};

export function validateRenderPlan(plan) {
  if (plan?.schema_version !== 1 || plan.fps !== FPS || !Array.isArray(plan.beats) || !plan.beats.length ||
      !Number.isInteger(plan.frames) || plan.frames < 1) throw new Error('invalid measured render plan');
  let cursor = 0;
  for (const beat of plan.beats) {
    if (!beat.id || !Number.isInteger(beat.start_frame) || !Number.isInteger(beat.end_frame) ||
        beat.start_frame !== cursor || beat.end_frame <= cursor ||
        !Number.isInteger(beat.voice_start_frame) || beat.voice_start_frame < beat.start_frame ||
        beat.voice_start_frame >= beat.end_frame || !Number.isFinite(beat.voice_end) ||
        beat.voice_end > beat.end_frame / FPS + 0.001 || beat.voice_end <= beat.voice_start_frame / FPS ||
        !beat.visual?.graphic || !beat.visual?.focus_quote || !palettes[beat.visual.mood]) {
      throw new Error(`invalid beat/clock: ${beat.id || '(missing id)'}`);
    }
    cursor = beat.end_frame;
  }
  if (cursor !== plan.frames) throw new Error('frame clock does not cover the whole film');
  return { frames: cursor, duration: cursor / FPS, beats: plan.beats.length,
    timing: 'clip boundaries measured; word/visual alignment unverified' };
}

function line(ctx, x1, y1, x2, y2) {
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
}
function trace(ctx, commands) {
  ctx.beginPath();
  for (const [cmd, ...args] of commands) ctx[cmd](...args);
}
function box(ctx, x, y, w, h, r, fill, stroke = null) {
  roundRect(ctx, x, y, w, h, r); ctx.fillStyle = fill; ctx.fill();
  if (stroke) { ctx.strokeStyle = stroke; ctx.stroke(); }
}
function surface(ctx, x, y, radius, colour = '#2F605B') {
  const g = ctx.createRadialGradient(x - radius * .25, y - radius * .35, 2, x, y, radius);
  g.addColorStop(0, colour); g.addColorStop(.72, '#172F30'); g.addColorStop(1, '#0B171A');
  return g;
}
function icon(ctx, kind, x, y, size, progress = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(size / 200, size / 200);
  ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  ctx.strokeStyle = '#E6ECE0'; ctx.fillStyle = surface(ctx, 0, 0, 110);
  const fillStroke = () => { ctx.fill(); ctx.stroke(); };
  switch (kind) {
    case 'phone':
      drawHandset(ctx, { x: -52, y: -95, w: 104, h: 190, screen: 'blank', antenna: false, glow: .3 });
      break;
    case 'screen':
      drawSmartphone(ctx, { x: -53, y: -96, w: 106, h: 192, apps: 0, glow: .55 });
      break;
    case 'person': case 'people': {
      const person = (xx, yy, s) => {
        ctx.save(); ctx.translate(xx, yy); ctx.scale(s, s);
        ctx.beginPath(); ctx.arc(0, -42, 25, 0, Math.PI * 2); fillStroke();
        box(ctx, -39, -10, 78, 75, 26, surface(ctx, 0, 15, 80), '#E6ECE0'); ctx.restore();
      };
      if (kind === 'person') person(0, 0, 1.15);
      else { person(-55, 13, .65); person(55, 13, .65); person(0, 0, .9); }
      break;
    }
    case 'pocket':
      trace(ctx, [['moveTo', -75, -70], ['lineTo', 75, -70], ['lineTo', 60, 48],
        ['quadraticCurveTo', 0, 100, -60, 48], ['closePath']]); fillStroke();
      line(ctx, -62, -48, 62, -48); break;
    case 'sun':
      ctx.fillStyle = '#E2B94F'; ctx.beginPath(); ctx.arc(0, 0, 45, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#E2B94F'; ctx.lineWidth = 7;
      for (let i = 0; i < 8; i += 1) { const a = i * Math.PI / 4; line(ctx, 61 * Math.cos(a), 61 * Math.sin(a), 84 * Math.cos(a), 84 * Math.sin(a)); }
      break;
    case 'light': {
      const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, 90);
      glow.addColorStop(0, 'rgba(255,244,183,.95)'); glow.addColorStop(.25, 'rgba(226,185,79,.8)');
      glow.addColorStop(1, 'rgba(226,185,79,0)');
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(0, 0, 90, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#F4DC83'; ctx.beginPath(); ctx.arc(0, 0, 28, 0, Math.PI * 2); ctx.fill(); break;
    }
    case 'leaf':
      trace(ctx, [['moveTo', -70, 50], ['bezierCurveTo', -85, -25, -5, -90, 75, -75],
        ['bezierCurveTo', 87, 0, 40, 83, -70, 50], ['closePath']]);
      ctx.fillStyle = '#32785D'; fillStroke(); line(ctx, -67, 54, 55, -58);
      line(ctx, -28, 18, -38, -18); line(ctx, 8, -14, 40, -8); break;
    case 'seed':
      ctx.beginPath(); ctx.ellipse(0, 0, 52, 75, .4, 0, Math.PI * 2); ctx.fillStyle = '#8B6841'; fillStroke();
      line(ctx, -30, 40, 30, -40); break;
    case 'plant':
      ctx.strokeStyle = '#BED8C3'; ctx.lineWidth = 7; line(ctx, 0, 70, 0, -55);
      trace(ctx, [['moveTo', 0, -8], ['bezierCurveTo', -10, -65, -72, -70, -70, -34],
        ['bezierCurveTo', -64, -6, -28, 0, 0, -8], ['closePath']]); ctx.fillStyle = '#32785D'; fillStroke();
      trace(ctx, [['moveTo', 0, 20], ['bezierCurveTo', 15, -35, 72, -40, 72, -10],
        ['bezierCurveTo', 68, 18, 36, 30, 0, 20], ['closePath']]); ctx.fillStyle = '#3F8969'; fillStroke();
      break;
    case 'server': {
      // A shaded equipment rack, not a stock screenshot or a random chart.
      box(ctx, -82, -91, 164, 182, 13, '#162329', '#94AEA8');
      for (let i = 0; i < 3; i += 1) {
        const yy = -77 + i * 53;
        box(ctx, -70, yy, 140, 44, 6, surface(ctx, 0, yy + 15, 120, '#3B6863'), '#95B1AB');
        ctx.fillStyle = GOLD; ctx.beginPath(); ctx.arc(-51, yy + 21, 4, 0, Math.PI * 2); ctx.fill();
        box(ctx, -28, yy + 9, 86, 25, 3, '#142A2D');
        ctx.strokeStyle = 'rgba(197,213,203,.65)'; ctx.lineWidth = 2;
        for (let j = 0; j < 6; j += 1) line(ctx, -17 + j * 11, yy + 15, -17 + j * 11, yy + 28);
      } break;
    }
    case 'laptop': {
      box(ctx, -82, -83, 164, 123, 9, '#141E23', '#B6CBC5');
      box(ctx, -73, -74, 146, 104, 4, surface(ctx, 0, -25, 125, '#3A7470'));
      ctx.strokeStyle = 'rgba(230,240,232,.20)'; ctx.lineWidth = 2; line(ctx, -68, 15, -4, -70);
      trace(ctx, [['moveTo', -95, 41], ['lineTo', 95, 41], ['lineTo', 79, 67], ['lineTo', -79, 67], ['closePath']]);
      ctx.fillStyle = '#A9B6B4'; ctx.fill();
      trace(ctx, [['moveTo', -64, 45], ['lineTo', 64, 45], ['lineTo', 58, 57], ['lineTo', -58, 57], ['closePath']]);
      ctx.fillStyle = '#506665'; ctx.fill(); break;
    }
    case 'message':
      box(ctx, -75, -48, 150, 96, 12, surface(ctx, 0, 0, 110), '#E6ECE0');
      trace(ctx, [['moveTo', -68, -40], ['lineTo', 0, 11], ['lineTo', 68, -40]]); ctx.stroke(); break;
    case 'package':
      trace(ctx, [['moveTo', -65, -43], ['lineTo', 0, -75], ['lineTo', 65, -43], ['lineTo', 65, 45],
        ['lineTo', 0, 79], ['lineTo', -65, 45], ['closePath']]); ctx.fillStyle = '#8A6C48'; fillStroke();
      line(ctx, -65, -43, 0, -10); line(ctx, 65, -43, 0, -10); line(ctx, 0, -10, 0, 79); break;
    case 'store': case 'building':
      box(ctx, -65, -52, 130, 122, 7, surface(ctx, 0, 0, 110), '#E6ECE0');
      if (kind === 'store') { trace(ctx, [['moveTo', -74, -52], ['lineTo', -58, -77], ['lineTo', 58, -77], ['lineTo', 74, -52], ['closePath']]); ctx.fillStyle = '#B38F4D'; fillStroke(); }
      box(ctx, -17, 18, 34, 52, 2, '#14252A', '#E6ECE0');
      for (const xx of [-42, 31]) for (const yy of [-25, 4]) box(ctx, xx, yy, 14, 12, 2, '#D5BF77');
      break;
    case 'car':
      trace(ctx, [['moveTo', -77, 12], ['lineTo', -58, -27], ['lineTo', -22, -48], ['lineTo', 43, -48],
        ['lineTo', 66, -18], ['lineTo', 79, -10], ['lineTo', 79, 28], ['lineTo', -77, 28], ['closePath']]); fillStroke();
      for (const xx of [-48, 48]) { ctx.fillStyle = '#111B1D'; ctx.beginPath(); ctx.arc(xx, 30, 17, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); } break;
    case 'battery':
      box(ctx, -63, -42, 126, 84, 10, surface(ctx, 0, 0, 100), '#E6ECE0');
      box(ctx, 63, -16, 13, 32, 3, '#E6ECE0'); ctx.strokeStyle = GOLD;
      line(ctx, -43, 0, -20, 0); line(ctx, 24, 0, 47, 0); line(ctx, 35, -12, 35, 12); break;
    case 'coin':
      ctx.beginPath(); ctx.ellipse(0, 0, 70, 70, 0, 0, Math.PI * 2); ctx.fillStyle = '#B29145'; fillStroke();
      ctx.beginPath(); ctx.ellipse(0, 0, 53, 53, 0, 0, Math.PI * 2); ctx.stroke(); break;
    case 'document':
      box(ctx, -55, -75, 110, 150, 7, '#C1CFC9', '#E6ECE0'); ctx.strokeStyle = '#34514D';
      for (const yy of [-40, -15, 10, 35]) line(ctx, -32, yy, 33, yy); break;
    case 'shield':
      trace(ctx, [['moveTo', 0, -80], ['lineTo', 68, -55], ['lineTo', 58, 25],
        ['quadraticCurveTo', 0, 95, -58, 25], ['lineTo', -68, -55], ['closePath']]); fillStroke();
      trace(ctx, [['moveTo', -27, 0], ['lineTo', -5, 23], ['lineTo', 34, -28]]); ctx.stroke(); break;
    case 'clock':
      ctx.beginPath(); ctx.arc(0, 0, 72, 0, Math.PI * 2); fillStroke();
      line(ctx, 0, 0, 0, -43); line(ctx, 0, 0, 31, 14); break;
    case 'gear':
      for (let i = 0; i < 8; i += 1) { ctx.save(); ctx.rotate(i * Math.PI / 4); box(ctx, -11, -80, 22, 32, 3, '#8CA29A'); ctx.restore(); }
      ctx.beginPath(); ctx.arc(0, 0, 59, 0, Math.PI * 2); fillStroke();
      ctx.beginPath(); ctx.arc(0, 0, 20, 0, Math.PI * 2); ctx.fillStyle = '#101E20'; ctx.fill(); break;
    case 'globe':
      ctx.beginPath(); ctx.arc(0, 0, 76, 0, Math.PI * 2); fillStroke();
      ctx.beginPath(); ctx.ellipse(0, 0, 35, 75, 0, 0, Math.PI * 2); ctx.stroke();
      line(ctx, -74, 0, 74, 0); line(ctx, -62, -37, 62, -37); line(ctx, -62, 37, 62, 37); break;
    case 'abstract':
      ctx.beginPath(); ctx.arc(0, 0, 68, 0, Math.PI * 2); fillStroke();
      ctx.beginPath(); ctx.arc(0, 0, 30, 0, Math.PI * 2); ctx.strokeStyle = GOLD; ctx.stroke(); break;
    default: throw new Error(`unsupported icon ${kind}`);
  }
  ctx.restore();
}

const hasArabic = (value) => /[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]/u.test(String(value));
function fitLines(ctx, value, maxWidth, size, family, maxLines = 2) {
  const words = String(value).split(/\s+/); let lines = [], row = '';
  ctx.direction = hasArabic(value) ? 'rtl' : 'ltr';
  ctx.font = `400 ${size}px "${family}"`;
  for (const word of words) {
    const candidate = row ? `${row} ${word}` : word;
    if (row && ctx.measureText(candidate).width > maxWidth) { lines.push(row); row = word; }
    else row = candidate;
  }
  if (row) lines.push(row);
  if (lines.length > maxLines || lines.some((s) => ctx.measureText(s).width > maxWidth)) {
    if (size <= 19) throw new Error(`text cannot fit safely: ${value}`);
    return fitLines(ctx, value, maxWidth, size - 2, family, maxLines);
  }
  return { lines, size };
}
function writeLines(ctx, value, x, y, maxWidth, size, family, color, align = 'center', maxLines = 2) {
  const rtl = hasArabic(value);
  const chosenFamily = rtl ? 'Noto Naskh Arabic' : family;
  ctx.save();
  const fitted = fitLines(ctx, value, maxWidth, size, chosenFamily, maxLines);
  ctx.font = `400 ${fitted.size}px "${chosenFamily}"`; ctx.fillStyle = color;
  ctx.direction = rtl ? 'rtl' : 'ltr';
  // The headline's left margin becomes the corresponding right margin in RTL.
  const actualAlign = rtl && align === 'left' ? 'right' : align;
  const actualX = rtl && align === 'left' ? W - x : x;
  ctx.textAlign = actualAlign;
  fitted.lines.forEach((s, i) => ctx.fillText(s, actualX, y + i * fitted.size * 1.18)); ctx.restore();
}
function node(ctx, data, x, y, size, p = 1) {
  ctx.save(); ctx.globalAlpha *= .55 + .45 * smooth(p);
  // The same lit-object staging as the house film: a quiet contact shadow and
  // a soft pool behind the drawn object, never an image or a source of motion.
  const halo = ctx.createRadialGradient(x, y, 0, x, y, size * .70);
  halo.addColorStop(0, 'rgba(111,182,151,.12)'); halo.addColorStop(1, 'rgba(111,182,151,0)');
  ctx.fillStyle = halo; ctx.fillRect(x - size, y - size, 2 * size, 2 * size);
  ctx.fillStyle = 'rgba(0,0,0,.28)'; ctx.beginPath();
  ctx.ellipse(x, y + size * .49, size * .44, size * .055, 0, 0, Math.PI * 2); ctx.fill();
  icon(ctx, data.icon, x, y + (1 - smooth(p)) * 12, size, p);
  writeLines(ctx, data.label, x, y + size * .68, size * 1.55, 25, 'Inter', SOFT, 'center', 2);
  ctx.restore();
}
function arrow(ctx, x1, y, x2, progress, blocked = false) {
  const end = x1 + (x2 - x1) * clamp(progress);
  ctx.save(); ctx.strokeStyle = blocked ? RED : GOLD; ctx.lineWidth = 4; ctx.lineCap = 'round';
  line(ctx, x1, y, end, y);
  if (!blocked && progress > .03) {
    trace(ctx, [['moveTo', end - 14, y - 10], ['lineTo', end, y], ['lineTo', end - 14, y + 10]]); ctx.stroke();
  }
  ctx.restore();
}

function picture(ctx, beat, local, duration) {
  const visual = beat.visual, graph = visual.graphic;
  // No guessed word timestamps: the action develops over its own measured clip.
  const voiceOffset = (beat.voice_start_frame - beat.start_frame) / FPS;
  const speechDuration = Math.max(.1, beat.voice_end - beat.voice_start_frame / FPS);
  const p = clamp((local - voiceOffset + .12) / Math.max(.3, speechDuration));
  const entrance = smooth((local + .35) / .85);
  const bg = palettes[visual.mood];
  ctx.fillStyle = bg[0]; ctx.fillRect(0, 0, W, H);
  const gradient = ctx.createRadialGradient(W * .49, H * .43, 10, W * .49, H * .43, W * .7);
  gradient.addColorStop(0, bg[1]); gradient.addColorStop(1, bg[0]); ctx.fillStyle = gradient; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(226,185,79,.36)'; ctx.lineWidth = 2; line(ctx, 78, 170, 78 + 180 * entrance, 170);
  ctx.save(); ctx.globalAlpha = .72 + .28 * entrance;
  writeLines(ctx, visual.focus_quote, 78, 110, 1100, 52, 'Instrument Serif', INK, 'left', 2);
  ctx.restore();
  if (graph.type === 'focus') {
    const scale = graph.effect === 'grow' ? .58 + .42 * smooth(p)
      : graph.effect === 'shrink' ? 1 - .40 * smooth(p) : .80 + .20 * smooth(p);
    node(ctx, graph.node, 640, 367, 250 * scale, entrance);
  } else if (graph.type === 'transfer') {
    node(ctx, graph.from, 265, 350, 225, entrance);
    node(ctx, graph.to, 1015, 350, 225, entrance);
    arrow(ctx, 405, 360, 875, p);
    const x = 405 + 470 * p;
    icon(ctx, graph.item.icon, x, 300, 110, p);
    writeLines(ctx, graph.item.label, x, 235, 210, 20, 'Inter', SOFT, 'center', 2);
    writeLines(ctx, graph.relation, 640, 435, 330, 25, 'Inter', GOLD, 'center', 2);
  } else if (graph.type === 'blocked') {
    // A negated action is NOT a travelling object that happens to stop. The
    // crossed-out item remains in place, so no attempted send is invented.
    node(ctx, graph.from, 265, 350, 225, entrance);
    // Stage the recipient into the diagram across the spoken phrase, while the
    // crossed-out item stays put. This is an entrance, not a sent packet.
    const reveal = .7 * p + .3 * smooth(p);
    const targetX = 1100 - 210 * reveal;
    node(ctx, graph.to, targetX, 350, 285, entrance);
    icon(ctx, graph.item.icon, 620, 342, 155, p);
    ctx.save(); ctx.strokeStyle = RED; ctx.lineWidth = 11;
    ctx.beginPath(); ctx.arc(620, 342, 87, 0, Math.PI * 2); ctx.stroke();
    line(ctx, 557, 405, 683, 279); ctx.restore();
    writeLines(ctx, graph.item.label, 620, 245, 230, 21, 'Inter', SOFT, 'center', 2);
    writeLines(ctx, graph.relation, 620, 482, 330, 25, 'Inter', RED, 'center', 2);
  } else if (graph.type === 'transform') {
    if (graph.from.icon === 'seed' && graph.to.icon === 'plant') {
      // A literal, drawn sprout develops from the seed, rather than an unrelated
      // decorative arrow. The seed stays present while the stem and leaves grow.
      const growth = smooth(p);
      ctx.strokeStyle = 'rgba(226,185,79,.40)'; ctx.lineWidth = 2; line(ctx, 460, 510, 820, 510);
      ctx.strokeStyle = '#A9D9B4'; ctx.lineWidth = 10;
      line(ctx, 640, 488, 640, 488 - growth * 225);
      if (growth > .25) {
        const leaf = smooth((growth - .25) / .75);
        ctx.save(); ctx.translate(640, 400 - 70 * growth); ctx.scale(leaf, leaf);
        trace(ctx, [['moveTo', 0, 0], ['bezierCurveTo', -24, -100, -150, -92, -130, -35],
          ['bezierCurveTo', -115, 5, -53, 12, 0, 0], ['closePath']]);
        ctx.fillStyle = '#3F8969'; ctx.fill(); ctx.strokeStyle = '#C5E1C8'; ctx.lineWidth = 5; ctx.stroke();
        trace(ctx, [['moveTo', 0, 32], ['bezierCurveTo', 30, -65, 150, -70, 130, -20],
          ['bezierCurveTo', 112, 22, 55, 42, 0, 32], ['closePath']]);
        ctx.fillStyle = '#32785D'; ctx.fill(); ctx.stroke(); ctx.restore();
      }
      icon(ctx, 'seed', 640, 497, 105, p);
      writeLines(ctx, graph.from.label, 480, 555, 260, 24, 'Inter', SOFT, 'center', 2);
      writeLines(ctx, graph.to.label, 800, 555, 260, 24, 'Inter', SOFT, 'center', 2);
    } else {
      ctx.save(); ctx.globalAlpha = 1 - .75 * smooth(p); node(ctx, graph.from, 530, 350, 260, entrance); ctx.restore();
      ctx.save(); ctx.globalAlpha = .2 + .8 * smooth(p); node(ctx, graph.to, 750, 350, 260, entrance); ctx.restore();
      writeLines(ctx, graph.relation, 640, 525, 300, 25, 'Inter', GOLD, 'center', 2);
    }
  } else if (graph.type === 'compare') {
    node(ctx, graph.left, 360, 350, 220, entrance);
    node(ctx, graph.right, 920, 350, 220, entrance);
    const x = 590 + 100 * smooth(p);
    ctx.strokeStyle = GOLD; ctx.lineWidth = 3; line(ctx, 550, 365, x, 365);
    writeLines(ctx, graph.relation, 640, 300, 270, 26, 'Inter', GOLD, 'center', 2);
  } else if (graph.type === 'sequence') {
    const n = graph.nodes.length, left = 170, right = 1110, gap = (right - left) / (n - 1);
    graph.nodes.forEach((item, i) => {
      const appear = .5 + .5 * smooth(p * n - i + .3);
      node(ctx, item, left + i * gap, 350, n === 4 ? 135 : 180, appear);
      if (i < n - 1) arrow(ctx, left + i * gap + 85, 350, left + (i + 1) * gap - 85, clamp(p * (n - 1) - i));
    });
  } else if (graph.type === 'chart') {
    const bars = graph.bars, vals = bars.map((b) => Number(b.value.replaceAll(',', '')));
    const max = Math.max(...vals), count = bars.length, width = 750 / count, left = 260;
    ctx.strokeStyle = 'rgba(243,238,226,.55)'; ctx.lineWidth = 2; line(ctx, 220, 525, 1060, 525);
    bars.forEach((bar, i) => {
      const x = left + i * width + width * .2, bw = width * .55;
      const progress = smooth(clamp(p * count - i));
      const state = chartBarState(vals[i], max, progress), height = 260 * state.relativeHeight;
      const grad = ctx.createLinearGradient(x, 525 - height, x, 525); grad.addColorStop(0, GOLD); grad.addColorStop(1, '#5B794E');
      box(ctx, x, 525 - height, bw, Math.max(.01, height), 6, grad);
      // The literal number is shown only when the bar actually reaches that
      // value. A final label over an unfinished bar would imply the wrong scale.
      if (state.labelVisible) writeLines(ctx, bar.value, x + bw / 2, 505 - height, bw + 30, 27, 'Inter', INK, 'center', 1);
      if (state.started) writeLines(ctx, bar.label, x + bw / 2, 560, width - 10, 23, 'Inter', SOFT, 'center', 2);
    });
  } else throw new Error(`unsupported graphic ${graph.type}`);
  // A hairline foot rule is a framing element, not evidence of semantic motion.
  ctx.strokeStyle = 'rgba(226,185,79,.25)'; ctx.lineWidth = 1; line(ctx, 78, 655, 1202, 655);
}

async function main() {
  const args = process.argv.slice(2), get = (flag, fallback = null) => {
    const i = args.indexOf(flag); return i < 0 ? fallback : args[i + 1];
  };
  const name = get('--plan'); if (!name) throw new Error('--plan is required');
  const plan = JSON.parse(fs.readFileSync(name, 'utf8')), result = validateRenderPlan(plan);
  if (args.includes('--validate')) { console.log(JSON.stringify(result, null, 2)); return; }
  const scale = Number(get('--scale', 1.5));
  if (!Number.isFinite(scale) || scale < .25 || scale > 1.5) throw new Error('scale must be between .25 and 1.5');
  loadFonts();
  const canvas = createCanvas(Math.round(W * scale), Math.round(H * scale)), ctx = canvas.getContext('2d');
  let index = 0;
  const paint = (frame) => {
    if (frame < plan.beats[index].start_frame) index = 0;
    while (index < plan.beats.length - 1 && frame >= plan.beats[index].end_frame) index += 1;
    const beat = plan.beats[index], t = (frame - beat.start_frame) / FPS;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    picture(ctx, beat, t, (beat.end_frame - beat.start_frame) / FPS);
  };
  if (get('--sample') !== null) {
    const seconds = Number(get('--sample')), output = get('--out');
    if (!Number.isFinite(seconds) || seconds < 0 || seconds >= result.duration || !output) throw new Error('invalid sample time or output');
    paint(Math.floor(seconds * FPS)); fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
    fs.writeFileSync(output, canvas.toBuffer('image/png')); return;
  }
  if (args.includes('--pipe')) {
    for (let frame = 0; frame < plan.frames; frame += 1) {
      paint(frame);
      if (!process.stdout.write(canvas.data())) await new Promise((resolve) => process.stdout.once('drain', resolve));
    }
    return;
  }
  throw new Error('choose --validate, --sample or --pipe');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => { console.error(`Script motion: ${error.message}`); process.exitCode = 2; });
}
