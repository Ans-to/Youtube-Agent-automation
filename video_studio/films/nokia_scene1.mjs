/**
 * Nokia, Scene 1 - the hook, 0:00 to 0:35.
 *
 * This exists to answer one question: does the kit build a shot that looks like
 * a film, or does it still look like a slide deck? So it uses everything at
 * once - map, camera, layers, depth, grade, type - and nothing else. No
 * templates, no per-beat special cases.
 *
 *     node films/nokia_scene1.mjs --sheet /tmp/s1     stills, for looking at
 *
 * The five beats are the script's own:
 *   0:00  a phone ringing in a dark room
 *   0:05  people in different cities
 *   0:12  the world map lights up
 *   0:20  the classic phone becomes a smartphone
 *   0:28  the phone alone, a slow push in
 */

import { drawShape } from '../motion/kit/shapes.mjs';
import { drawType } from '../motion/kit/type.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { camera } from '../motion/kit/camera.mjs';
import { text } from '../motion/ui.mjs';

export const PALETTE = {
  text: '#12233F',
  caption: '#B4762A',
  dim: '#6E7683',
  land: '#E2E6EC',
  landEdge: '#C6CDD7',
  paper: '#FAF8F3',
};

const W = 1280;
const H = 720;

/** Small helper: a word, in the film's voice, positioned by its baseline. */
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
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(ch, cursor, y);
      cursor += ctx.measureText(ch).width + tracking;
    }
  } else {
    text(ctx, value, x, y, { size, weight, family, color: colour, align });
  }
  ctx.restore();
}

/* -------------------------------------------------------------------------
 * Shot 1 - 0:00 to 0:05. A phone ringing in a dark room.
 * ---------------------------------------------------------------------- */

const shot1 = {
  id: 'hook-01-ringing',
  dur: 5,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'medium', at: [0.5, 0.52], zoom: 0.35 + t * 0.65 }),
  grade: { vignetteStrength: 0.42, bloomAt: [0.5, 0.5], bloomStrength: 0.1 },
  layers: [
    {
      // The room, reduced to the two things that say "indoors at night": a
      // table edge and a pool of lamp light on the wall behind. Earlier this
      // was a floor line and a wall seam, which the 1.4x push turned into two
      // enormous diagonals crossing the frame.
      id: 'room', depth: 0.75, from: 0.0,
      draw: (ctx, { p }) => {
        const pool = ctx.createRadialGradient(W * 0.5, H * 0.30, 20, W * 0.5, H * 0.34, W * 0.34);
        pool.addColorStop(0, `rgba(255,250,236,${0.5 * Math.min(1, p * 2)})`);
        pool.addColorStop(1, 'rgba(255,250,236,0)');
        ctx.save();
        ctx.fillStyle = pool;
        ctx.fillRect(0, 0, W, H * 0.8);
        ctx.strokeStyle = '#C6C1B4';
        ctx.lineWidth = 2;
        ctx.globalAlpha = Math.min(1, p * 1.6);
        ctx.beginPath();
        ctx.moveTo(W * 0.24, H * 0.665);
        ctx.lineTo(W * 0.76, H * 0.665);
        ctx.stroke();
        ctx.restore();
      },
    },
    {
      // The ring: waves radiating out of the handset, alive the whole shot.
      id: 'ring', depth: 1.0, from: 0.04, entrance: 'iris',
      box: { x: W * 0.2, y: H * 0.18, w: W * 0.6, h: H * 0.68 },
      behaviour: 'breathe', behaviourOptions: { amount: 0.06 },
      draw: (ctx, { t }) => {
        const cx = W * 0.5;
        const cy = H * 0.52;
        for (let i = 0; i < 3; i += 1) {
          const phase = ((t * 0.9 + i / 3) % 1);
          const r = 90 + phase * 190;
          ctx.save();
          ctx.strokeStyle = PALETTE.caption;
          ctx.globalAlpha = (1 - phase) * 0.5;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(cx, cy, r, -0.9, 0.9);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(cx, cy, r, Math.PI - 0.9, Math.PI + 0.9);
          ctx.stroke();
          ctx.restore();
        }
      },
    },
    {
      id: 'phone', depth: 1.0, from: 0.07, entrance: 'squash',
      box: { x: W * 0.5 - 62, y: H * 0.34, w: 124, h: 250 },
      draw: (ctx, { t }) => {
        // The ring makes the phone move: a 2px vibration, not camera shake.
        const buzz = Math.sin(t * 42) * 1.8;
        drawShape(ctx, 'phone-classic', {
          x: W * 0.5 - 62 + buzz, y: H * 0.34, w: 124, h: 250, p: 1, palette: PALETTE,
        });
      },
    },
    {
      // A caption rises from its own line. Wiping from the top of the frame
      // meant a bottom caption stayed hidden until 91% of the wipe and dragged
      // a full-width rule across the picture on the way down.
      id: 'caption', screen: true, depth: 1.1, from: 0.28, entrance: 'rise',
      box: { x: W * 0.22, y: H * 0.80, w: W * 0.56, h: 54 },
      draw: (ctx, { p }) => {
        say(ctx, 'A COMPANY NOBODY COULD CATCH', W * 0.5, H * 0.86, {
          size: 17, weight: 700, colour: PALETTE.caption, align: 'center', tracking: 3.4, opacity: p,
        });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 2 - 0:05 to 0:12. People in different cities.
 * ---------------------------------------------------------------------- */

const CITIES_2 = ['newyork', 'saopaulo', 'lagos', 'cairo', 'mumbai', 'shanghai', 'tokyo', 'sydney'];

const shot2 = {
  id: 'hook-02-cities',
  dur: 7,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'wide', at: [0.5, 0.48], zoom: 0.15 + t * 0.2 }),
  grade: { vignetteStrength: 0.30, bloomAt: [0.5, 0.45], bloomStrength: 0.07 },
  layers: [
    {
      id: 'map', depth: 0.55, from: 0.0,
      // A held map with nothing moving is a poster; a slow drift is the
      // difference between a still and a shot.
      behaviour: 'drift', behaviourOptions: { amount: 0.012 },
      draw: (ctx, { p }) => {
        drawMap(ctx, {
          x: 40, y: 60, w: W - 80, h: H - 130, p, palette: PALETTE,
          land: PALETTE.land, landEdge: PALETTE.landEdge,
        });
      },
    },
    {
      // Pins cascade left to right, so the eye travels the world rather than
      // being shown eight dots at once.
      id: 'pins', depth: 0.55, from: 0.30,
      draw: (ctx, { p }) => {
        drawMap(ctx, {
          x: 40, y: 60, w: W - 80, h: H - 130, p: 1, palette: PALETTE,
          land: 'rgba(0,0,0,0)', landEdge: 'rgba(0,0,0,0)', graticule: false,
          pins: CITIES_2.map((at, i) => ({ at, t: Math.max(0, Math.min(1, (p - i * 0.085) / 0.3)) })),
        });
      },
    },
    {
      id: 'line', screen: true, depth: 1.1, from: 0.40,
      draw: (ctx, { p }) => {
        const value = 'MILLIONS OF POCKETS';
        drawType(ctx, 'weight-ramp', {
          value, x: W * 0.5, y: H * 0.90, p, size: 34, weight: 700, family: 'Inter',
          colour: PALETTE.text, accent: PALETTE.caption, align: 'center', span: W - 120,
        });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 3 - 0:12 to 0:20. The map lights up; the product reaches everywhere.
 * ---------------------------------------------------------------------- */

const shot3 = {
  id: 'hook-03-world',
  dur: 8,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'wide', at: [0.55, 0.45], zoom: 0.5 + t * 0.4 }),
  grade: { vignetteStrength: 0.36, bloomAt: [0.55, 0.42], bloomStrength: 0.13 },
  layers: [
    {
      id: 'glow', depth: 0.4, from: 0.0,
      draw: (ctx, { p }) => {
        drawMap(ctx, {
          x: 40, y: 50, w: W - 80, h: H - 120, p: 1, palette: PALETTE,
          graticule: true,
          land: 'rgba(0,0,0,0)', landEdge: 'rgba(0,0,0,0)',
          glow: { lon: 24.9, lat: 60.2, radius: 0.30, t: Math.min(1, p * 1.6), strength: 0.30 },
        });
      },
    },
    {
      id: 'land', depth: 0.6, from: 0.04,
      draw: (ctx, { p }) => {
        drawMap(ctx, {
          x: 40, y: 50, w: W - 80, h: H - 120,
          p: Math.min(1, p * 1.25), palette: PALETTE,
          land: PALETTE.land, landEdge: PALETTE.landEdge, graticule: false,
        });
      },
    },
    {
      // Arcs leave Helsinki for every region: the empire, drawn as routes.
      id: 'routes', depth: 0.62, from: 0.30,
      draw: (ctx, { p }) => {
        const targets = ['london', 'newyork', 'saopaulo', 'lagos', 'cairo', 'delhi', 'beijing', 'tokyo', 'sydney'];
        drawMap(ctx, {
          x: 40, y: 50, w: W - 80, h: H - 120, p: 1, palette: PALETTE,
          graticule: false, land: 'rgba(0,0,0,0)', landEdge: 'rgba(0,0,0,0)',
          arcs: targets.map((to, i) => ({
            from: 'helsinki', to,
            t: Math.max(0, Math.min(1, (p - i * 0.075) / 0.32)),
          })),
          pins: [{ at: 'helsinki', t: 1, colour: PALETTE.text }],
        });
      },
    },
    {
      id: 'title', screen: true, depth: 1.05, from: 0.42, entrance: 'rise',
      box: { x: 60, y: H * 0.80, w: W - 120, h: 70 },
      draw: (ctx, { p, t }) => {
        drawType(ctx, 'karaoke', {
          value: 'One in three phones on earth.',
          x: 78, y: H * 0.86, p: Math.min(1, 0.25 + t / 3.2),
          size: 40, weight: 700, family: 'Inter',
          colour: PALETTE.text, accent: PALETTE.caption, align: 'left', span: W - 200,
        });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 4 - 0:20 to 0:28. The classic phone becomes a smartphone.
 * ---------------------------------------------------------------------- */

const shot4 = {
  id: 'hook-04-turn',
  dur: 8,
  background: PALETTE.paper,
  camera: (t) => camera({ shot: 'medium', at: [0.5, 0.5], zoom: 0.35 + t * 0.5 }),
  grade: { vignetteStrength: 0.34, bloomAt: [0.5, 0.45], bloomStrength: 0.09 },
  layers: [
    {
      id: 'axis', depth: 0.7, from: 0.03,
      draw: (ctx, { p }) => {
        ctx.save();
        ctx.strokeStyle = '#CFCBC0';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(W * 0.22, H * 0.16);
        ctx.lineTo(W * 0.22 + (W * 0.56) * p, H * 0.16);
        ctx.stroke();
        ctx.restore();
      },
    },
    {
      id: 'old', depth: 1.0, from: 0.07, entrance: 'stamp',
      box: { x: W * 0.30, y: H * 0.26, w: 132, h: 266 },
      exit: 'fade',
      draw: (ctx, { t }) => {
        // The old phone is pushed back and dimmed as the new one takes the
        // frame - the whole point of the shot is what replaces what.
        const kept = 1 - Math.min(1, Math.max(0, (t - 3.4) / 2.2));
        ctx.save();
        ctx.globalAlpha *= 0.35 + kept * 0.65;
        drawShape(ctx, 'phone-classic', { x: W * 0.30, y: H * 0.26, w: 132, h: 266, p: 1, palette: PALETTE });
        ctx.restore();
      },
    },
    {
      // A box, not the whole frame: `assembly` draws a seam at its box centre,
      // and with no box that seam was a full-height rule across the picture.
      id: 'new', depth: 1.0, from: 0.34, entrance: 'assembly',
      box: { x: W * 0.56, y: H * 0.22, w: 150, h: 300 },
      draw: (ctx) => {
        drawShape(ctx, 'phone-smart', { x: W * 0.56, y: H * 0.22, w: 150, h: 300, p: 1, palette: PALETTE });
      },
    },
    {
      id: 'y1', screen: true, depth: 1.1, from: 0.2,
      draw: (ctx, { p }) => {
        say(ctx, '1982', W * 0.30 + 66, H * 0.16 - 14, { size: 20, weight: 700, colour: PALETTE.dim, align: 'center', opacity: p });
        say(ctx, 'the phone', W * 0.30 + 66, H * 0.72, { size: 24, weight: 600, colour: PALETTE.text, align: 'center', opacity: p });
      },
    },
    {
      id: 'y2', screen: true, depth: 1.1, from: 0.62,
      draw: (ctx, { p }) => {
        say(ctx, '2007', W * 0.56 + 75, H * 0.16 - 14, { size: 20, weight: 700, colour: PALETTE.caption, align: 'center', opacity: p });
        say(ctx, 'a computer', W * 0.56 + 75, H * 0.75, { size: 24, weight: 600, colour: PALETTE.text, align: 'center', opacity: p });
      },
    },
  ],
};

/* -------------------------------------------------------------------------
 * Shot 5 - 0:28 to 0:35. The phone alone; a slow push.
 * ---------------------------------------------------------------------- */

const shot5 = {
  id: 'hook-05-alone',
  dur: 7,
  background: '#F6F3EA',
  camera: (t) => camera({ shot: 'close', at: [0.5, 0.48], zoom: 0.12 + t * 0.28 }),
  grade: { vignetteStrength: 0.46, bloomAt: [0.5, 0.44], bloomStrength: 0.11 },
  layers: [
    {
      // A single table line: the room, reduced to one mark.
      id: 'table', depth: 0.6, from: 0.0,
      draw: (ctx, { p }) => {
        ctx.save();
        ctx.strokeStyle = '#C8C3B6';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(W * 0.5 - (W * 0.18) * p, H * 0.70);
        ctx.lineTo(W * 0.5 + (W * 0.18) * p, H * 0.70);
        ctx.stroke();
        ctx.restore();
      },
    },
    {
      id: 'shadow', depth: 0.95, from: 0.06,
      draw: (ctx, { p }) => {
        const g = ctx.createRadialGradient(W * 0.5, H * 0.70, 4, W * 0.5, H * 0.70, 200);
        g.addColorStop(0, `rgba(18,35,63,${0.16 * p})`);
        g.addColorStop(1, 'rgba(18,35,63,0)');
        ctx.save();
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.ellipse(W * 0.5, H * 0.705, 104, 18, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      },
    },
    {
      id: 'phone', depth: 1.0, from: 0.04, entrance: 'rise',
      box: { x: W * 0.5 - 72, y: H * 0.20, w: 144, h: 356 },
      behaviour: 'breathe', behaviourOptions: { amount: 0.012 },
      draw: (ctx) => {
        drawShape(ctx, 'phone-smart', { x: W * 0.5 - 72, y: H * 0.20, w: 144, h: 356, p: 1, palette: PALETTE });
      },
    },
    {
      id: 'last', screen: true, depth: 1.15, from: 0.50, entrance: 'squash',
      box: { x: W * 0.25, y: H * 0.755, w: W * 0.5, h: 50 },
      draw: (ctx, { p }) => {
        say(ctx, 'and then it stopped', W * 0.5, H * 0.80, {
          size: 30, weight: 500, colour: '#3A4150', align: 'center', opacity: p,
        });
      },
    },
  ],
};

export const SCENE1 = [shot1, shot2, shot3, shot4, shot5];

/* -------------------------------------------------------------------------
 * Stills
 * ---------------------------------------------------------------------- */

const sheetMain = async () => {
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

  const argList = process.argv.slice(2);
  const outIdx = argList.indexOf('--sheet');
  const out = path.resolve(outIdx >= 0 ? argList[outIdx + 1] : '/tmp/s1');
  fs.mkdirSync(out, { recursive: true });

  const FRACS = [0.12, 0.38, 0.66, 0.94];
  const TW = 480;
  const TH = 270;
  const cols = FRACS.length;
  const canvas = createCanvas(cols * TW + 40, SCENE1.length * TH + 90);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#F2F2F5';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  text(ctx, 'Nokia, Scene 1 - built from the kit', 20, 30, { size: 20, weight: 700, family: 'Inter', color: '#17171A' });
  text(ctx, `${SCENE1.length} shots, 35 seconds, four frames each`, 20, 52, { size: 13, weight: 500, family: 'Inter', color: '#6B6B75' });

  const frame = createCanvas(W, H);
  const fctx = frame.getContext('2d');

  SCENE1.forEach((shot, r) => {
    FRACS.forEach((frac, c) => {
      fctx.clearRect(0, 0, W, H);
      renderShot(fctx, shot, shot.dur * frac, W, H, { frame: Math.round(shot.dur * frac * 30) });
      const x = 20 + c * TW;
      const y = 70 + r * TH;
      ctx.drawImage(frame, x, y, TW, TH);
      ctx.strokeStyle = '#C9C9D2';
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, TW - 1, TH - 1);
      text(ctx, `${shot.id}  ${(shot.dur * frac).toFixed(1)}s`, x + 6, y + TH - 7, {
        size: 10, weight: 600, family: 'Inter', color: '#FFFFFF',
      });
    });
  });

  fs.writeFileSync(path.join(out, 'scene1-sheet.png'), canvas.toBuffer('image/png'));

  // Full-size stills of the strongest frame in each shot, for judging detail.
  SCENE1.forEach((shot) => {
    fctx.clearRect(0, 0, W, H);
    renderShot(fctx, shot, shot.dur * 0.7, W, H, { frame: Math.round(shot.dur * 0.7 * 30) });
    fs.writeFileSync(path.join(out, `${shot.id}.png`), frame.toBuffer('image/png'));
  });

  console.log(`wrote ${out}/scene1-sheet.png and ${SCENE1.length} stills`);
};

if (import.meta.url === `file://${process.argv[1]}`) {
  sheetMain().catch((err) => { console.error(err); process.exit(1); });
}
