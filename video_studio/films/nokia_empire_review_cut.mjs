/**
 * A proposed ~15-minute editorial cut of the Nokia empire film.
 *
 * Nothing here mutates the original film or asserts editorial approval. The
 * manifest selects whole existing shots and retains their narration verbatim.
 * With --timing, every shot is retimed to the actual recorded line; --estimate
 * explicitly uses the original voice lengths and is not release evidence.
 *
 *   node video_studio/films/nokia_empire_review_cut.mjs --lines /tmp/lines.json
 *   node video_studio/films/nokia_empire_review_cut.mjs --estimate --script /tmp/script.md
 *   node video_studio/films/nokia_empire_review_cut.mjs --timing /tmp/voice/timing.json --starts /tmp/shots.json
 *   node video_studio/films/nokia_empire_review_cut.mjs --timing /tmp/voice/timing.json --stills /tmp/stills --scale .75
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { optics, frameBuffer, opticsFor } from '../motion/kit/optics.mjs';
import { W, H } from './nokia_full.mjs';
import { FILM, shotAt, shotStarts, totalSeconds } from './nokia_empire.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MANIFEST = path.join(HERE, 'nokia_empire_review_cut.json');
const ORIGINAL = path.join(HERE, 'empire_narration.json');
const LEAD = 0.25;
const FIRST_LEAD = 0.30;
const PAD = 0.95;

export function selectShots(manifest, film = FILM) {
  if (!manifest || manifest.schema_version !== 1 || !Array.isArray(manifest.shots) || !manifest.shots.length) {
    throw new Error('review cut manifest must contain a non-empty shot list');
  }
  const byId = new Map(film.map((shot, i) => [shot.id, { shot, i }]));
  let previous = -1;
  const selected = manifest.shots.map((id) => {
    const item = byId.get(id);
    if (!item || item.i <= previous) {
      throw new Error(`unknown, duplicate, or out-of-order shot: ${id}`);
    }
    previous = item.i;
    return item.shot;
  });
  const scenes = [...new Set(selected.map((shot) => shot.scene))];
  if (JSON.stringify(scenes) !== JSON.stringify(Array.from({ length: 13 }, (_, i) => i + 1))) {
    throw new Error('review cut must retain all thirteen scenes in order');
  }
  return selected;
}

export function retimeShots(shots, timing) {
  if (!Array.isArray(timing) || timing.length !== shots.length) {
    throw new Error('voice timing must contain exactly one row per selected shot');
  }
  return shots.map((shot, i) => {
    const row = timing[i];
    if (!row || row.shot !== shot.id || row.text !== shot.text ||
        typeof row.vo !== 'number' || !Number.isFinite(row.vo) || row.vo <= 0) {
      throw new Error(`${shot.id}: recorded timing is missing, out of order, or differs from the proposed script`);
    }
    // Round to milliseconds; never reduce the voice to fit a picture.
    const dur = Math.ceil(((i === 0 ? FIRST_LEAD : LEAD) + row.vo + PAD) * 1000) / 1000;
    return { ...shot, dur };
  });
}

export function reviewScript(shots, manifest, original) {
  const names = new Map(original.scenes.map((scene) => [scene.n, scene.name]));
  const words = shots.reduce((sum, shot) => sum + shot.text.trim().split(/\s+/).length, 0);
  let out = `# ${manifest.title}\n\n`;
  out += '**Proposed editorial cut — not approved for release.**\n\n';
  out += `This draft selects ${shots.length} complete shots (${words.toLocaleString('en-US')} words) from the author's existing narration. `;
  out += 'The selected words remain verbatim and in order; omitted material is a proposed editorial cut. ';
  out += 'The replacement title is also proposed: the original $300 billion figure remains unverified.\n\n';
  out += 'The final runtime depends on the actual narration and shot clock. Historical claims, picture, sound and captions still require review.\n';
  let scene = null;
  for (const shot of shots) {
    if (scene !== shot.scene) {
      scene = shot.scene;
      out += `\n## Scene ${scene}: ${names.get(scene) || ''}\n\n`;
    }
    out += `**${shot.id}** ${shot.text}\n\n`;
  }
  return `${out.trimEnd()}\n`;
}

function writeJson(dest, data) {
  fs.mkdirSync(path.dirname(path.resolve(dest)), { recursive: true });
  fs.writeFileSync(path.resolve(dest), JSON.stringify(data, null, 2) + '\n');
}

async function main() {
  const args = process.argv.slice(2);
  const value = (flag) => {
    const i = args.indexOf(flag);
    if (i < 0) return null;
    if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`${flag} needs a value`);
    return args[i + 1];
  };
  const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
  const selected = selectShots(manifest);
  const lines = value('--lines');
  const script = value('--script');
  const timingPath = value('--timing');
  const startsPath = value('--starts');
  const stills = value('--stills');
  const pipe = args.includes('--pipe');
  const estimate = args.includes('--estimate');
  if (timingPath && estimate) throw new Error('use --timing or --estimate, not both');
  const timed = timingPath ? retimeShots(selected, JSON.parse(fs.readFileSync(path.resolve(timingPath), 'utf8'))) : selected;
  if ((startsPath || stills || pipe) && !timingPath && !estimate) {
    throw new Error('a clock or picture requires --timing, or explicit --estimate for a non-release draft');
  }
  if (lines) writeJson(lines, selected.map((shot) => ({ shot: shot.id, text: shot.text })));
  if (script) {
    fs.mkdirSync(path.dirname(path.resolve(script)), { recursive: true });
    fs.writeFileSync(path.resolve(script), reviewScript(selected, manifest, JSON.parse(fs.readFileSync(ORIGINAL, 'utf8'))));
  }
  if (startsPath) writeJson(startsPath, shotStarts(timed));
  if (!stills && !pipe) {
    console.log(`${selected.length} selected shots; ${totalSeconds(timed).toFixed(2)}s ${timingPath ? 'from recorded narration' : '(original-voice estimate)'}; not approved`);
    return;
  }
  const fps = Number(value('--fps') || 24);
  const scale = Number(value('--scale') || 1);
  if (!Number.isFinite(fps) || fps <= 0 || !Number.isFinite(scale) || scale <= 0 || scale > 3) {
    throw new Error('fps and scale must be positive finite numbers');
  }
  loadFonts();
  const dw = Math.round(W * scale);
  const dh = Math.round(H * scale);
  const canvas = createCanvas(dw, dh);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(timed, W, H, { join: 0.45, background: timed[0].background, scale });
  const fb = frameBuffer(dw, dh);
  function paint(t) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, dw, dh);
    renderer.render(ctx, t);
    fb.ctx.setTransform(1, 0, 0, 1, 0, 0);
    fb.ctx.clearRect(0, 0, dw, dh);
    fb.ctx.drawImage(canvas, 0, 0);
    optics(ctx, { source: fb.canvas, w: dw, h: dh, frame: Math.round(t * fps), ...opticsFor(shotAt(t, timed)) });
  }
  if (stills) {
    fs.mkdirSync(stills, { recursive: true });
    shotStarts(timed).forEach((row, i) => {
      paint(row.start + (row.end - row.start) * 0.78);
      fs.writeFileSync(path.join(stills, `${String(i).padStart(3, '0')}-${row.id}.png`), canvas.toBuffer('image/png'));
    });
    console.log(`wrote ${timed.length} stills to ${stills}`);
  }
  if (pipe) {
    const total = Math.round(renderer.duration * fps);
    const from = Number(value('--from') || 0);
    const to = Math.min(total, Number(value('--to') || total));
    if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to <= from) {
      throw new Error('invalid frame range');
    }
    for (let i = from; i < to; i += 1) {
      paint(i / fps);
      const data = canvas.data();
      if (!process.stdout.write(data)) await new Promise((resolve) => process.stdout.once('drain', resolve));
    }
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => { console.error(`Nokia review cut: ${error.message}`); process.exitCode = 2; });
}
