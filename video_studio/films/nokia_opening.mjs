/**
 * Nokia: the opening fifty seconds.
 *
 * Scene 1 (the hook, 0:00-0:35) comes from nokia_scene1.mjs. This file adds the
 * first three shots of Scene 2, so the piece is a film with a turn in it rather
 * than a demonstration reel: the hook ends on the phone alone, and the story
 * starts again in 1865 with a paper mill.
 *
 *     node films/nokia_opening.mjs --stills /tmp/nokia     contact sheet
 *     node films/nokia_opening.mjs --frames /tmp/frames     PNG sequence
 */

import { drawShape } from '../motion/kit/shapes.mjs';
import { drawType } from '../motion/kit/type.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { cards } from '../motion/kit/cards.mjs';
import { camera } from '../motion/kit/camera.mjs';
import { text } from '../motion/ui.mjs';
import { SCENE1 } from './nokia_scene1.mjs';

const W = 1280;
const H = 720;

export const PALETTE = {
  text: '#12233F',
  caption: '#B4762A',
  dim: '#6E7683',
  land: '#E2E6EC',
  landEdge: '#C6CDD7',
  paper: '#FAF8F3',
};

function say(ctx, value, x, y, options = {}) {
  const {
    size = 40, weight = 600, colour = PALETTE.text, align = 'left',
    family = 'Inter', opacity = 1, tracking = 0,
  } = options;
  ctx.save();
  ctx.globalAlpha *= opacity;
  if (tracking) {
    ctx.font = `${weight} ${size}px ${family}`;
    let cursor = align === 'center' ? x - ctx.measureText(value).width / 2 : x;
    for (const ch of value) {
      ctx.fillStyle = colour;
      ctx.fillText(ch, cursor, y);
      cursor += ctx.measureText(ch).width + tracking;
    }
  } else {
    text(ctx, value, x, y, { size, weight, family, color: colour, align });
  }
  ctx.restore();
}

/* -------------------------------------------------------------------------
 * Shot 6 - 0:35 to 0:41. 1865. A paper mill in a Finnish town.
 * ---------------------------------------------------------------------- */

const shot6 = {
  id: 'history-01-mill',
  dur: 6,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'wide', at: [0.46, 0.52], zoom: 0.2 + t * 0.55 }),
  grade: { vignetteStrength: 0.40, bloomAt: [0.28, 0.34], bloomStrength: 0.10 },
  transitionIn: 'luma',
  layers: [
    {
      // Ground and a river line: Tammerkoski ran the mill, so the water is the
      // reason the mill is there and belongs in the first frame of the scene.
      id: 'ground', depth: 0.65, from: 0.0,
      draw: (ctx, { p }) => {
        const k = Math.min(1, p * 2.2);
        ctx.strokeStyle = '#C9C5BA';
        ctx.lineWidth = 2;
        ctx.globalAlpha = k;
        ctx.beginPath();
        ctx.moveTo(0, H * 0.78);
        ctx.lineTo(W, H * 0.74);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(18,35,63,0.16)';
        ctx.lineWidth = 1.2;
        for (let i = 0; i < 4; i += 1) {
          ctx.beginPath();
          ctx.moveTo(W * (0.04 + i * 0.02), H * (0.84 + i * 0.035));
          ctx.quadraticCurveTo(W * 0.5, H * (0.82 + i * 0.035), W * (0.96 - i * 0.02), H * (0.85 + i * 0.035));
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      },
    },
    {
      id: 'mill', depth: 0.9, from: 0.06, entrance: 'draw-on',
      box: { x: W * 0.18, y: H * 0.26, w: W * 0.46, h: H * 0.46 },
      draw: (ctx, { p }) => {
        drawShape(ctx, 'factory', {
          x: W * 0.18, y: H * 0.26, w: W * 0.46, h: H * 0.46, p, palette: PALETTE,
        });
      },
    },
    {
      // Smoke, drifting: the mill is working, not a drawing of a mill.
      id: 'smoke', depth: 0.85, from: 0.34,
      draw: (ctx, { t }) => {
        for (let i = 0; i < 5; i += 1) {
          const phase = ((t * 0.26 + i / 5) % 1);
          const r = 16 + phase * 54;
          ctx.save();
          ctx.globalAlpha = (1 - phase) * 0.14;
          ctx.fillStyle = '#A9A69E';
          ctx.beginPath();
          ctx.arc(W * 0.30 + phase * 92 - 20, H * 0.24 - phase * 130, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      },
    },
    {
      id: 'rolls', depth: 1.05, from: 0.40, entrance: 'rise',
      box: { x: W * 0.64, y: H * 0.40, w: W * 0.24, h: H * 0.30 },
      draw: (ctx, { p }) => {
        drawShape(ctx, 'paper-roll', {
          x: W * 0.63, y: H * 0.46, w: W * 0.26, h: H * 0.26, p, palette: PALETTE,
        });
      },
    },
    {
      id: 'year', screen: true, depth: 1.2, from: 0.20,
      draw: (ctx, { p }) => {
        cards.chapter(ctx, {
          x: W * 0.07, y: H * 0.16, w: W * 0.5, number: '02', text: '1865', palette: PALETTE, p,
        });
      },
    },
    {
      id: 'claim', screen: true, depth: 1.2, from: 0.52,
      draw: (ctx, { p }) => {
        say(ctx, 'A paper mill in a Finnish town.', W * 0.07, H * 0.88, {
          size: 26, weight: 500, colour: '#2A3140', opacity: Math.min(1, p * 1.6),
        });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 7 - 0:41 to 0:46. Rubber, cable, electronics. One company, four trades.
 * ---------------------------------------------------------------------- */

const TRADES = [
  { id: 'paper-roll', label: 'PAPER' },
  { id: 'rubber-sheet', label: 'RUBBER' },
  { id: 'cable-coil', label: 'CABLE' },
  { id: 'chip', label: 'ELECTRONICS' },
];

const shot7 = {
  id: 'history-02-trades',
  dur: 5,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'wide', at: [0.5, 0.5], zoom: 0.1 + t * 0.3 }),
  grade: { vignetteStrength: 0.30, bloomAt: [0.5, 0.44], bloomStrength: 0.06 },
  transitionIn: 'push',
  layers: [
    {
      id: 'rule', depth: 0.8, from: 0.0,
      draw: (ctx, { p }) => {
        ctx.strokeStyle = 'rgba(18,35,63,0.18)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(W * 0.08, H * 0.34);
        ctx.lineTo(W * 0.08 + W * 0.84 * Math.min(1, p * 1.4), H * 0.34);
        ctx.stroke();
      },
    },
    ...TRADES.map((trade, i) => ({
      id: `trade-${i}`, depth: 1.0, from: 0.14 + i * 0.12, entrance: 'rise',
      box: { x: W * (0.08 + i * 0.21), y: H * 0.30, w: W * 0.18, h: H * 0.30 },
      draw: (ctx, { p }) => {
        const x = W * (0.08 + i * 0.21);
        drawShape(ctx, trade.id, { x, y: H * 0.28, w: W * 0.18, h: H * 0.34, p: 1, palette: PALETTE });
        say(ctx, trade.label, x + W * 0.09, H * 0.72, {
          size: 13, weight: 700, colour: PALETTE.text, align: 'center', tracking: 2.4,
          opacity: Math.min(1, Math.max(0, (p - 0.3) * 3)),
        });
      },
    })),
    {
      id: 'line', screen: true, depth: 1.1, from: 0.56,
      draw: (ctx, { p }) => {
        drawType(ctx, 'weight-ramp', {
          value: 'Four industries. One company.', x: W * 0.5, y: H * 0.86, p,
          size: 32, weight: 700, family: 'Inter', colour: PALETTE.text,
          accent: PALETTE.caption, align: 'center', span: W - 160,
        });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 8 - 0:46 to 0:50. The rise: by 2007, one in three phones on earth.
 * ---------------------------------------------------------------------- */

const shot8 = {
  id: 'history-03-rise',
  dur: 4,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'medium', at: [0.42, 0.44], zoom: 0.25 + t * 0.6 }),
  grade: { vignetteStrength: 0.34, bloomAt: [0.4, 0.40], bloomStrength: 0.09 },
  transitionIn: 'iris',
  layers: [
    {
      id: 'chart', depth: 0.9, from: 0.02,
      draw: (ctx, { p }) => {
        drawShape(ctx, 'area', {
          x: W * 0.08, y: H * 0.22, w: W * 0.44, h: H * 0.48, p, palette: PALETTE,
        });
        // Two dates only: the chart is the sentence, so it needs its start and
        // its end and nothing else.
        say(ctx, '1992', W * 0.09, H * 0.78, { size: 13, weight: 700, colour: PALETTE.dim });
        say(ctx, '2007', W * 0.52, H * 0.78, { size: 13, weight: 700, colour: PALETTE.caption, align: 'right' });
      },
    },
    {
      id: 'stat', screen: true, depth: 1.1, from: 0.26,
      draw: (ctx, { p }) => {
        cards.stat(ctx, {
          x: W * 0.68, y: H * 0.42, w: W * 0.26,
          text: '1 in 3', label: 'phones sold worldwide, 2007',
          palette: PALETTE, p,
        });
      },
    },
    {
      id: 'note', screen: true, depth: 1.1, from: 0.55,
      draw: (ctx, { p }) => {
        say(ctx, 'and then the ground moved.', W * 0.08, H * 0.92, {
          size: 21, weight: 500, colour: '#3A4150', opacity: Math.min(1, p * 1.6),
        });
      },
    },
  ],
};

export const SCENE2 = [shot6, shot7, shot8];
export const FILM = [...SCENE1, ...SCENE2];

/** The clock in seconds at which each shot starts, for the score's cues. */
export function shotStarts(shots = FILM) {
  let at = 0;
  return shots.map((s) => {
    const row = { id: s.id, start: at, end: at + s.dur };
    at += s.dur;
    return row;
  });
}

export function totalSeconds(shots = FILM) {
  return shots.reduce((sum, s) => sum + s.dur, 0);
}

/* -------------------------------------------------------------------------
 * Command line
 * ---------------------------------------------------------------------- */

const main = async () => {
  const { createCanvas, GlobalFonts } = await import('@napi-rs/canvas');
  const fs = await import('fs');
  const path = await import('path');
  const { fileURLToPath } = await import('url');
  const { renderShot } = await import('../motion/kit/stage.mjs');

  const HERE = path.dirname(fileURLToPath(import.meta.url));
  const FONT_DIR = path.resolve(HERE, '..', 'assets', 'fonts');
  if (fs.existsSync(FONT_DIR)) {
    for (const f of fs.readdirSync(FONT_DIR)) if (/\.(ttf|otf|woff2?)$/i.test(f)) GlobalFonts.registerFromPath(path.join(FONT_DIR, f));
  }

  const args = process.argv.slice(2);
  const flag = (name) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : null;
  };
  const stills = flag('--stills');
  const frames = flag('--frames');
  const fps = Number(flag('--fps') || 30);

  if (stills) {
    const out = path.resolve(stills);
    fs.mkdirSync(out, { recursive: true });
    const FRACS = [0.15, 0.45, 0.75, 0.95];
    const TW = 420;
    const TH = 236;
    const canvas = createCanvas(FRACS.length * TW + 40, FILM.length * TH + 90);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#F2F2F5';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    text(ctx, 'Nokia: the opening fifty seconds', 20, 32, { size: 22, weight: 700, family: 'Inter', color: '#17171A' });
    text(ctx, `${FILM.length} shots, ${totalSeconds().toFixed(0)} seconds`, 20, 56, { size: 13, weight: 500, family: 'Inter', color: '#6B6B75' });
    const frame = createCanvas(W, H);
    const fctx = frame.getContext('2d');
    FILM.forEach((shot, r) => {
      FRACS.forEach((frac, c) => {
        fctx.clearRect(0, 0, W, H);
        renderShot(fctx, shot, shot.dur * frac, W, H, { frame: Math.round(shot.dur * frac * fps) });
        ctx.drawImage(frame, 20 + c * TW, 70 + r * TH, TW, TH);
        ctx.strokeStyle = '#C9C9D2';
        ctx.lineWidth = 1;
        ctx.strokeRect(20 + c * TW + 0.5, 70 + r * TH + 0.5, TW - 1, TH - 1);
      });
    });
    fs.writeFileSync(path.join(out, 'opening-sheet.png'), canvas.toBuffer('image/png'));
    console.log(`wrote ${out}/opening-sheet.png`);
    return;
  }

  if (frames) {
    const out = path.resolve(frames);
    fs.mkdirSync(out, { recursive: true });
    const frame = createCanvas(W, H);
    const ctx = frame.getContext('2d');
    const total = Math.round(totalSeconds() * fps);
    let written = 0;
    for (const shot of FILM) {
      const count = Math.round(shot.dur * fps);
      for (let i = 0; i < count; i += 1) {
        const t = i / fps;
        ctx.clearRect(0, 0, W, H);
        renderShot(ctx, shot, t, W, H, { frame: written });
        fs.writeFileSync(path.join(out, `${String(written).padStart(5, '0')}.png`), frame.toBuffer('image/png'));
        written += 1;
      }
      console.log(`  ${shot.id} done (${written}/${total})`);
    }
    console.log(`wrote ${written} frames to ${out}`);
    return;
  }

  console.log(`shots: ${FILM.length}, ${totalSeconds()}s`);
  shotStarts().forEach((s) => console.log(`  ${s.start.toFixed(0)}s  ${s.id}`));
};

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => { console.error(err); process.exit(1); });
}
