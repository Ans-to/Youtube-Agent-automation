/**
 * A pacing pass on the opening-only Nokia semantic pilot.
 *
 * It keeps the original Nokia house shot scaffolds, palettes, type and drawn
 * product kit. The changes are on the subjects: connections, phones, data and
 * the old/new interactions develop through the spoken ideas. No photographic
 * source or still-image animation is used. Cue times are approximate model
 * alignment, not a listening attestation. This is not the 15-minute film.
 *
 *   node video_studio/films/nokia_pacing_pilot.mjs --validate
 *   node video_studio/films/nokia_pacing_pilot.mjs --sample 24 --out preview.png
 *   node video_studio/films/nokia_pacing_pilot.mjs --pipe --from 0 --to 150
 *   node video_studio/films/nokia_pacing_pilot.mjs --pipe --preview-scale .5 --step 3
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
import { measure, roundRect, text } from '../motion/ui.mjs';
import { W, H } from './nokia_full.mjs';
import { makeShots, validatePlan } from './nokia_semantic_pilot.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const PLAN = path.join(HERE, 'nokia_semantic_pilot_plan.json');
const CUES = path.join(HERE, 'nokia_pacing_pilot_cues.json');
const VOICE = path.join(ROOT, 'docs/media/nokia/audio-repair-draft/voice-timing.json');
const SHOTS = path.join(ROOT, 'docs/media/nokia/audio-repair-draft/shots.json');
const FPS = 30;
const clamp = (v) => Math.max(0, Math.min(1, v));
const ease = (v) => { const x = clamp(v); return x * x * (3 - 2 * x); };
const at = (t, a, b) => clamp((t - a) / (b - a));
const GOLD = '#E2B94F';
const INK = '#F3EEE2';
const SOFT = 'rgba(243,238,226,0.68)';

// Gartner worldwide all-mobile-phone sales, not smartphone OS share.
export const LEADERSHIP_SHARES = [
  ['Nokia', 38.6, true], ['Samsung', 16.3, false], ['Motorola', 8.7, false],
  ['LG', 8.4, false], ['Sony Ericsson', 7.6, false], ['Others', 20.3, false],
];
export const NOKIA_SHARE_BY_YEAR = [[2008, 38.6], [2009, 36.4], [2011, 23.8], [2012, 19.1], [2013, 13.9]];
// An elapsed-year axis: 2009→2011 is twice the 2008→2009 distance.
export const declineYearPosition = (year) => (year - 2008) / 5;

/** Cue membership and order are structural evidence, not audible alignment. */
export function validateCues(cues, plan, voice) {
  if (cues?.schema_version !== 1 || cues.fps !== plan.fps || !Array.isArray(cues.moments) || !cues.moments.length) {
    throw new Error('missing pacing cues');
  }
  const lines = new Map(voice.map((x) => [x.shot, x]));
  let last = -1;
  for (const cue of cues.moments) {
    const row = plan.rows.find((x) => x.shot === cue.shot && cue.frame >= x.start_frame && cue.frame < x.end_frame);
    const line = lines.get(cue.shot);
    if (!row || !line || !Number.isInteger(cue.frame) || cue.frame <= last ||
        typeof cue.words !== 'string' || !cue.words || !line.text.includes(cue.words) ||
        !row.spoken_span.includes(cue.words) ||
        typeof cue.visual_action !== 'string' || !cue.visual_action.trim()) {
      throw new Error(`invalid pacing cue at frame ${cue.frame}`);
    }
    last = cue.frame;
  }
  if (plan.rows.some((row) => !cues.moments.some((cue) => cue.shot === row.shot && cue.frame >= row.start_frame && cue.frame < row.end_frame))) {
    throw new Error('every pilot beat needs a pacing cue');
  }
  return { moments: cues.moments.length,
    timing: 'approximate word alignments; watching and listening still required' };
}

function replaceLayer(shot, id, draw) {
  const layer = shot.layers.find((item) => item.id === id);
  if (!layer) throw new Error(`missing house layer ${id}`);
  layer.draw = draw;
}

function insertBeforeWords(shot, layer) {
  const i = shot.layers.findIndex((item) => item.id === 'words');
  if (i < 0) throw new Error('missing house words layer');
  shot.layers.splice(i, 0, { depth: 1, ...layer });
}

/** Global reach: the connections visibly draw to distinct destinations. */
function worldMap(ctx, { t, dur }) {
  const destinations = ['london', 'lagos', 'delhi', 'beijing', 'newyork', 'sydney'];
  const arcs = destinations.map((to, i) => ({ from: 'helsinki', to,
    t: ease(at(t, 0.30 + i * 0.42, 2.25 + i * 0.42)),
    colour: 'rgba(230,190,82,0.82)', width: 2.5, head: true }));
  const pins = destinations.map((name, i) => ({ at: name,
    t: at(t, 1.0 + i * 0.42, 2.1 + i * 0.42), colour: GOLD }));
  drawMap(ctx, { x: W * 0.085, y: H * 0.23, w: W * 0.83, h: H * 0.47,
    p: 0.35 + 0.57 * clamp(t / dur), projection: 'winkel', land: '#17635f',
    landEdge: 'rgba(220,244,236,0.55)', graticule: true,
    graticuleColour: 'rgba(150,220,210,0.05)',
    palette: { land: '#17635f', landEdge: 'rgba(220,244,236,0.55)',
      text: '#E9F0E6', caption: '#D8B24A' }, arcs, pins });
}

/** A symbolic group of people with phones, not a count or population statistic. */
function globalPeople(ctx, { t }) {
  for (let i = 0; i < 5; i += 1) {
    const arrive = ease(at(t, 3.05 + i * 0.40, 3.90 + i * 0.40));
    if (!arrive) continue;
    const x = W * (0.65 + i * 0.061) + (1 - arrive) * 24;
    const y = H * 0.76 + (1 - arrive) * 22;
    ctx.save(); ctx.globalAlpha *= arrive * 0.76;
    ctx.fillStyle = '#DAE5DD';
    ctx.beginPath(); ctx.arc(x, y - 25, 11, 0, Math.PI * 2); ctx.fill();
    roundRect(ctx, x - 16, y - 10, 32, 37, 12); ctx.fill();
    // A small handset in the person's hand ties the group to the narration's
    // products; the exact number of icons is deliberately not a claim.
    ctx.strokeStyle = '#DAE5DD'; ctx.lineWidth = 4; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(x + 12, y + 5); ctx.lineTo(x + 26, y - 3); ctx.stroke();
    ctx.fillStyle = GOLD; roundRect(ctx, x + 22, y - 17, 12, 19, 3); ctx.fill();
    ctx.restore();
  }
}

function worldWords(ctx, { t }) {
  text(ctx, 'A COMPANY IN THE WORLD', W * 0.075, H * 0.155, { size: 12,
    family: 'Inter', weight: 600, color: '#D8B24A', tracking: 7,
    alpha: 0.65 + 0.35 * ease(at(t, 0, 0.55)) });
  const firstOut = ease(at(t, 1.35, 1.85));
  text(ctx, 'Imagine a company...', W * 0.075, H * 0.78 + 8 * firstOut, {
    size: 52, family: 'Instrument Serif', weight: 400, color: INK, alpha: 1 - firstOut });
  const reachIn = ease(at(t, 1.75, 2.25));
  const reachOut = ease(at(t, 2.85, 3.20));
  text(ctx, 'that reaches across the world.', W * 0.075, H * 0.78 + (1 - reachIn) * 10 + reachOut * 8, {
    size: 52, family: 'Instrument Serif', weight: 400, color: INK, alpha: reachIn * (1 - reachOut) });
  const people = ease(at(t, 3.20, 3.85));
  const lead = 'Billions of people';
  const x = W * 0.075;
  text(ctx, lead, x, H * 0.78 + (1 - people) * 14, {
    size: 52, family: 'Instrument Serif', weight: 400, color: INK, alpha: people });
  const worldwide = ease(at(t, 4.25, 4.95));
  const leadWidth = measure(ctx, lead, { size: 52, family: 'Instrument Serif', weight: 400 });
  text(ctx, ', worldwide.', x + leadWidth, H * 0.78 + (1 - worldwide) * 10, {
    size: 52, family: 'Instrument Serif', weight: 400, color: INK, alpha: worldwide });
}

/** One specific action: a handset is put inside a garment pocket. */
function pocketSubject(ctx, { t, dur }) {
  const drop = 0.15 + 0.85 * ease(at(t, 0.02, Math.max(0.1, dur - 0.16)));
  const phoneW = W * 0.145, phoneH = H * 0.49;
  const x = W * 0.4275, y = H * (0.12 + 0.25 * drop);
  const px = W * 0.345, py = H * 0.49, pw = W * 0.31, ph = H * 0.33;
  // Hide the back of the handset inside the cloth: it must not protrude
  // through the bottom edge as it moves into the pocket.
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, py + ph * 0.76); ctx.clip();
  drawHandset(ctx, { x, y, w: phoneW, h: phoneH, facing: 0.08,
    screen: 'menu', glow: 0.8, antenna: false });
  ctx.restore();
  ctx.save();
  const fabric = ctx.createLinearGradient(px, py, px + pw, py + ph);
  fabric.addColorStop(0, '#3B4146'); fabric.addColorStop(0.55, '#282D33');
  fabric.addColorStop(1, '#15191E');
  ctx.fillStyle = fabric; ctx.strokeStyle = 'rgba(228,228,218,0.38)'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + pw, py);
  ctx.lineTo(px + pw * 0.91, py + ph * 0.82);
  ctx.quadraticCurveTo(px + pw * 0.5, py + ph * 1.08, px + pw * 0.09, py + ph * 0.82);
  ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.setLineDash([5, 5]); ctx.strokeStyle = 'rgba(235,229,207,0.36)';
  ctx.beginPath(); ctx.moveTo(px + pw * 0.04, py + H * 0.022);
  ctx.lineTo(px + pw * 0.96, py + H * 0.022); ctx.stroke();
  ctx.restore();
}

/** A chorus of drawn phones, resolving to one handset as Nokia is named. */
function manyPhones(ctx, { t }) {
  const settle = ease(at(t, 2.4, 3.8));
  const fadeGrid = ease(at(t, 2.8, 3.65));
  const mainPhone = ease(at(t, 3.45, 4.45));
  const cols = 5, rows = 3;
  const centreX = W * 0.755, centreY = H * 0.48;
  for (let i = 0; i < cols * rows; i += 1) {
    const built = ease(at(t, i * 0.105, i * 0.105 + 0.7));
    // A few faint phones are present at the cut; the rest still assemble in
    // sequence. This avoids a nearly empty incoming frame before the voice.
    const appear = i < 3 ? 0.38 + 0.62 * built : built;
    if (!appear) continue;
    const x0 = W * (0.57 + (i % cols) * 0.082);
    const y0 = H * (0.25 + Math.floor(i / cols) * 0.18);
    const x = x0 + (centreX - x0) * 0.34 * settle;
    const y = y0 + (centreY - y0) * 0.34 * settle + (1 - appear) * 28;
    const w = W * 0.038, h = H * 0.11;
    ctx.save(); ctx.globalAlpha *= appear * (1 - fadeGrid);
    ctx.fillStyle = '#393D42'; ctx.strokeStyle = 'rgba(243,238,226,0.46)'; ctx.lineWidth = 1.1;
    roundRect(ctx, x, y, w, h, w * 0.16); ctx.fill(); ctx.stroke();
    ctx.fillStyle = 'rgba(172,197,164,0.8)'; roundRect(ctx, x + w * 0.13, y + h * 0.18, w * 0.74, h * 0.27, w * 0.035); ctx.fill();
    ctx.fillStyle = 'rgba(241,226,179,0.50)';
    for (let k = 0; k < 6; k += 1) ctx.fillRect(x + w * (0.18 + (k % 3) * 0.22), y + h * (0.58 + Math.floor(k / 3) * 0.11), w * 0.12, h * 0.045);
    ctx.restore();
  }
  if (mainPhone > 0) {
    ctx.save(); ctx.globalAlpha *= mainPhone;
    drawHandset(ctx, { x: W * 0.70, y: H * 0.23, w: W * 0.12, h: H * 0.51,
      facing: 0.06, screen: 'menu', glow: 0.75, antenna: false });
    ctx.restore();
  }
}

function nameWords(ctx, { t }) {
  text(ctx, 'For millions of people,', W * 0.075, H * 0.35, { size: 45, family: 'Instrument Serif', weight: 400, color: SOFT, alpha: 0.80 + 0.20 * ease(at(t, 0, 0.50)) });
  text(ctx, 'that company was', W * 0.075, H * 0.47, { size: 54, family: 'Instrument Serif', weight: 400, color: INK, alpha: ease(at(t, 1.95, 2.65)) });
  // Arrive slightly ahead of the estimated spoken name rather than masking it
  // until after the narrator has said it.
  const brand = ease(at(t, 2.85, 3.60));
  text(ctx, 'Nokia.', W * 0.075, H * 0.62 + (1 - brand) * 20, { size: 82, family: 'Instrument Serif', weight: 400, color: GOLD, alpha: brand });
}

/** Wider, synchronously growing bars preserve relative market-share ordering. */
function leadershipBars(ctx, { t }) {
  const data = LEADERSHIP_SHARES;
  const x0 = W * 0.105, step = W * 0.143, barW = W * 0.059;
  const base = H * 0.78, h = H * 0.27;
  // The growth is the chart itself, not an animated overlay on a finished still.
  // Every bar uses the same factor, so a rival's share never exceeds its true
  // relationship to another bar during the reveal.
  const growth = 0.16 + 0.84 * ease(at(t, 0.05, 2.10));
  // The comparison resolves into the two largest individual vendors. Both
  // keep equal widths and the same vertical scale during the transition.
  const fadeOthers = ease(at(t, 2.35, 2.90));
  const focus = ease(at(t, 2.90, 4.75));
  ctx.save();
  ctx.fillStyle = 'rgba(243,238,226,0.25)'; ctx.fillRect(x0 - 14, base, step * 5 + barW + 28, 1);
  data.forEach(([label, value, leader], i) => {
    const initialCenter = x0 + i * step + barW / 2;
    const targetCenter = i === 0 ? W * 0.31 : i === 1 ? W * 0.59 : initialCenter;
    const center = initialCenter + (targetCenter - initialCenter) * focus;
    const width = barW + (i < 2 ? W * 0.035 * focus : 0);
    const x = center - width / 2, height = value / 40 * h * growth;
    ctx.save(); ctx.globalAlpha *= i < 2 ? 1 : 1 - fadeOthers;
    const fill = ctx.createLinearGradient(0, base - height, 0, base);
    if (leader) { fill.addColorStop(0, '#EDCD7A'); fill.addColorStop(1, '#9D6D29'); }
    else { fill.addColorStop(0, 'rgba(207,214,211,0.72)'); fill.addColorStop(1, 'rgba(140,148,151,0.48)'); }
    ctx.fillStyle = fill; ctx.fillRect(x, base - height, width, height);
    ctx.fillStyle = leader ? 'rgba(255,239,199,0.84)' : 'rgba(242,242,235,0.55)'; ctx.fillRect(x, base - height, width, 2);
    text(ctx, label, center, base + H * 0.05, { size: label.length > 11 ? 14 : 17, family: 'Inter', weight: 500, align: 'center', color: leader ? 'rgba(243,238,226,0.86)' : 'rgba(243,238,226,0.58)' });
    if (i < 2 && focus > 0.25) text(ctx, `${value}%`, center, base - height - H * 0.02, {
      size: 18, family: 'Inter', weight: 600, align: 'center', color: INK, alpha: at(focus, 0.25, 1) });
    ctx.restore();
  });
  ctx.restore();
}

function leadershipCallout(ctx, { t }) {
  const figure = ease(at(t, 1.65, 2.40));
  text(ctx, '38.6%', W * 0.72, H * 0.31 + (1 - figure) * 14, {
    size: 67, family: 'Instrument Serif', weight: 400, color: GOLD, alpha: figure });
  const label = ease(at(t, 2.45, 3.20));
  text(ctx, 'OF ALL PHONES SOLD', W * 0.72, H * 0.36 + (1 - label) * 8, {
    size: 13, family: 'Inter', weight: 600, color: SOFT, alpha: label });
}

/** A chronological, labeled all-phone share chart, not total company value. */
function declineBars(ctx, { t, dur }) {
  const data = NOKIA_SHARE_BY_YEAR;
  const x0 = W * 0.105, x1 = W * 0.88, base = H * 0.79, h = H * 0.28;
  const barW = W * 0.085;
  // Reveal a different year as the narration moves from the former lead to the
  // struggle. All heights are the actual shares on a 0–40% common scale.
  const start = [0, 0.75, 1.9, 3.1, 4.3];
  const points = [];
  // After the full time-proportional series, resolve to a labeled endpoint
  // comparison. Intermediate years and the continuous line fade out as the
  // endpoints move, so their new positions cannot masquerade as an axis.
  const endpointFade = ease(at(t, 5.85, 6.15));
  const endpointFocus = ease(at(t, 6.15, dur - 0.10));
  ctx.save();
  ctx.fillStyle = 'rgba(243,238,226,0.25)'; ctx.fillRect(x0 - barW * 0.5, base, x1 - x0 + barW, 1);
  data.forEach(([year, value], i) => {
    const yearX = x0 + declineYearPosition(year) * (x1 - x0);
    const targetX = i === 0 ? W * 0.31 : i === data.length - 1 ? W * 0.65 : yearX;
    const x = yearX + (targetX - yearX) * endpointFocus;
    const built = ease(at(t, start[i], Math.min(dur - 0.15, start[i] + 1.25)));
    const reveal = i === 0 ? 0.22 + 0.78 * built : built;
    const height = value / 40 * h * reveal;
    if (reveal > 0) {
      ctx.save(); ctx.globalAlpha *= (i === 0 || i === data.length - 1) ? 1 : 1 - endpointFade;
      const fill = ctx.createLinearGradient(0, base - height, 0, base);
      if (i === 0) { fill.addColorStop(0, '#D7B369'); fill.addColorStop(1, '#8E6835'); }
      else { fill.addColorStop(0, 'rgba(185,201,209,0.70)'); fill.addColorStop(1, 'rgba(115,130,143,0.48)'); }
      ctx.fillStyle = fill; ctx.fillRect(x - barW / 2, base - height, barW, height);
      ctx.fillStyle = i === 0 ? 'rgba(255,235,191,0.8)' : 'rgba(218,229,235,0.65)';
      ctx.fillRect(x - barW / 2, base - height, barW, 2);
      text(ctx, String(year), x, base + H * 0.047, { size: 17, family: 'Inter', weight: 500, align: 'center', color: 'rgba(230,234,234,0.76)', alpha: at(reveal, 0, 0.18) });
      if (reveal > 0.8) text(ctx, `${value}%`, x, base - height - H * 0.022, { size: 18, family: 'Inter', weight: 600, align: 'center', color: 'rgba(230,234,234,0.76)', alpha: at(reveal, 0.8, 1) });
      ctx.restore();
    }
    points.push([yearX, base - value / 40 * h]);
  });
  // The path is time-proportional: the gap from 2009 to 2011 is two years.
  // It begins only once the narrated line reaches the loss of leadership.
  const tracing = at(t, 4.0, 6.15);
  if (tracing > 0) {
    ctx.save(); ctx.globalAlpha *= 1 - endpointFade;
    ctx.beginPath(); ctx.rect(x0 - 20, H * 0.42, (x1 - x0 + 40) * tracing, H * 0.38); ctx.clip();
    ctx.strokeStyle = 'rgba(226,185,79,0.85)'; ctx.lineWidth = 3; ctx.lineJoin = 'round';
    ctx.beginPath(); points.forEach(([x, y], i) => { if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); }); ctx.stroke();
    ctx.restore();
  }
  ctx.restore();
}

function declineFocus(ctx, { t, dur }) {
  const data = NOKIA_SHARE_BY_YEAR;
  const edges = [0.10, 1.55, 2.90, 4.15, 5.30, dur + 0.35];
  data.forEach(([year, value], i) => {
    const inPhase = ease(at(t, edges[i], edges[i] + 0.32));
    const outPhase = 1 - ease(at(t, edges[i + 1] - 0.28, edges[i + 1]));
    const alpha = inPhase * outPhase;
    if (alpha <= 0) return;
    const y = H * 0.31 + (1 - inPhase) * 11;
    text(ctx, `${year}  ·  ${value}%`, W * 0.69, y, { size: 49,
      family: 'Instrument Serif', weight: 400, color: i === 0 ? GOLD : INK, alpha });
  });
}

/** Three distinct drawn phones arrive; their screen content builds over time. */
function smartphoneSubject(ctx, { t, dur }) {
  const arrive = ease(at(t, 0, Math.max(0.2, dur - 0.35)));
  const spread = 0.20 + 0.80 * arrive;
  contact(ctx, W * 0.5, H * 0.845, W * 0.26, H * 0.02, 0.48);
  const sidePhones = [
    { x: 0.5 - 0.17 * spread, angle: -0.035, glow: 0.45 },
    { x: 0.5 + 0.17 * spread, angle: 0.035, glow: 0.45 },
  ];
  sidePhones.forEach((phone, i) => {
    const visible = ease(at(t, 0.1 + 0.35 * i, 1.0 + 0.35 * i));
    ctx.save(); ctx.globalAlpha *= visible * 0.68;
    drawSmartphone(ctx, { x: W * (phone.x - 0.052), y: H * (0.26 + 0.04 * (1 - visible)),
      w: W * 0.104, h: H * 0.46, rotate: phone.angle, glow: phone.glow,
      apps: Math.max(0, Math.min(12, Math.round((t - 0.4 - 0.28 * i) * 3.4))) });
    ctx.restore();
  });
  drawSmartphone(ctx, { x: W * 0.44, y: H * (0.21 + 0.09 * (1 - arrive)),
    w: W * 0.12, h: H * 0.54, glow: 0.8,
    apps: Math.max(0, Math.min(12, Math.round((t + 0.15) * 3.2))) });
}

/** Explain the change in interaction: a key press gives way to a screen touch. */
function keyPress(ctx, { t }) {
  const down = ease(at(t, 0.15, 0.55));
  const fade = 1 - ease(at(t, 1.0, 1.45));
  if (down * fade <= 0) return;
  const cx = W * 0.228, cy = H * 0.525;
  ctx.save(); ctx.globalAlpha *= down * fade * 0.9; ctx.strokeStyle = GOLD; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(cx, cy, 11 - 3 * down, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = 'rgba(243,238,226,0.9)'; ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
function interactionArrow(ctx, { t }) {
  const k = ease(at(t, 0.85, 2.15));
  if (k > 0) {
    const x = W * 0.405, end = x + W * 0.19 * k, y = H * 0.48;
    ctx.save(); ctx.strokeStyle = `rgba(226,185,79,${0.78 * k})`; ctx.fillStyle = `rgba(226,185,79,${0.78 * k})`;
    ctx.lineWidth = 3; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(end, y); ctx.stroke();
    if (k > 0.85) { ctx.beginPath(); ctx.moveTo(end, y); ctx.lineTo(end - 13, y - 8); ctx.lineTo(end - 13, y + 8); ctx.closePath(); ctx.fill(); }
    ctx.restore();
  }
}
function screenTouch(ctx, { t }) {
  const touch = ease(at(t, 0.72, 1.48));
  if (touch <= 0) return;
  const cx = W * 0.70, cy = H * (0.59 - 0.245 * touch);
  ctx.save(); ctx.globalAlpha *= Math.min(1, touch * 2) * 0.85;
  ctx.strokeStyle = '#E7D398'; ctx.lineWidth = 2.6; ctx.beginPath();
  ctx.arc(cx, cy, 13 - 5 * touch, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = 'rgba(243,238,226,0.9)'; ctx.beginPath(); ctx.arc(cx, cy, 3.5, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
  // A small interface opens below the tapped icon; the mark is an action with
  // a visible consequence, not a decorative pulse on an unchanged phone.
  const opened = ease(at(t, 1.40, 2.45));
  if (opened > 0) {
    const x = W * 0.670, y = H * 0.435, w = W * 0.080, h = H * 0.25 * opened;
    ctx.save(); ctx.globalAlpha *= opened * 0.92;
    ctx.fillStyle = '#B2CDD0'; roundRect(ctx, x, y, w, h, 6); ctx.fill();
    if (opened > 0.4) {
      ctx.fillStyle = 'rgba(232,243,238,0.76)';
      ctx.fillRect(x + w * 0.14, y + h * 0.20, w * 0.70, 3);
      ctx.fillRect(x + w * 0.14, y + h * 0.38, w * 0.55, 3);
      ctx.fillRect(x + w * 0.14, y + h * 0.56, w * 0.64, 3);
    }
    ctx.restore();
  }
}

export function makePacedShots(plan) {
  const shots = makeShots(plan);
  for (let i = 0; i < shots.length; i += 1) {
    const shot = shots[i];
    switch (plan.rows[i].visual) {
      case 'world':
        replaceLayer(shot, 'map', worldMap);
        insertBeforeWords(shot, { id: 'global-people', draw: globalPeople });
        replaceLayer(shot, 'words', worldWords);
        break;
      case 'pocket': replaceLayer(shot, 'subject', pocketSubject); break;
      case 'name':
        replaceLayer(shot, 'words', nameWords);
        insertBeforeWords(shot, { id: 'people-products', draw: manyPhones });
        break;
      case 'leadership':
        replaceLayer(shot, 'bars', leadershipBars);
        insertBeforeWords(shot, { id: 'market-share-callout', draw: leadershipCallout });
        break;
      case 'decline':
        replaceLayer(shot, 'bars', declineBars);
        insertBeforeWords(shot, { id: 'year-focus', draw: declineFocus });
        break;
      case 'smartphone': replaceLayer(shot, 'subject', smartphoneSubject); break;
      case 'comparison':
        insertBeforeWords(shot, { id: 'key-press', draw: keyPress });
        insertBeforeWords(shot, { id: 'interaction-arrow', draw: interactionArrow });
        insertBeforeWords(shot, { id: 'screen-touch', draw: screenTouch });
        break;
      default: throw new Error('unknown paced composition');
    }
  }
  return shots;
}

async function main() {
  const args = process.argv.slice(2);
  const get = (flag, fallback = null) => { const i = args.indexOf(flag); return i < 0 ? fallback : args[i + 1]; };
  const plan = JSON.parse(fs.readFileSync(PLAN, 'utf8'));
  const cues = JSON.parse(fs.readFileSync(CUES, 'utf8'));
  const voice = JSON.parse(fs.readFileSync(VOICE, 'utf8'));
  const clock = JSON.parse(fs.readFileSync(SHOTS, 'utf8'));
  const result = validatePlan(plan, voice, clock);
  const timing = validateCues(cues, plan, voice);
  if (args.includes('--validate')) { console.log(JSON.stringify({ ...result, ...timing }, null, 2)); return; }
  const scale = Number(get('--preview-scale', 1.5));
  if (!Number.isFinite(scale) || scale < 0.25 || scale > 1.5) throw new Error('preview scale must be 0.25–1.5');
  loadFonts();
  const pictures = makePacedShots(plan);
  const width = Math.round(W * scale), height = Math.round(H * scale);
  const canvas = createCanvas(width, height), ctx = canvas.getContext('2d');
  const renderer = createRenderer(pictures, W, H, { join: 0, background: pictures[0].background, scale });
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
    const from = Number(get('--from', 0)), to = Number(get('--to', result.frames)), step = Number(get('--step', 1));
    if (!Number.isInteger(from) || !Number.isInteger(to) || !Number.isInteger(step) || from < 0 || to > result.frames || to <= from || step < 1 || step > 30) throw new Error('invalid frame range');
    for (let i = from; i < to; i += step) {
      paint(i);
      if (!process.stdout.write(canvas.data())) await new Promise((resolve) => process.stdout.once('drain', resolve));
    }
    return;
  }
  throw new Error('specify --validate, --sample, or --pipe');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => { console.error(`Nokia pacing pilot: ${error.message}`); process.exitCode = 2; });
}
