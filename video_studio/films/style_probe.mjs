/**
 * Three art directions, the same six seconds.
 *
 * The film was rejected for its look, and the look had never been a decision - it
 * was one palette and one house style applied to everything. These are three
 * different genres, not three tints of one, so the direction can be chosen by
 * eye rather than argued about:
 *
 *   SIGNAL    a two-colour poster: near-black, cream, signal orange. Anton, big,
 *             hard edges, no texture. Motion is masks and hard cuts.
 *   MONOLITH  dark and expensive: true black, old gold, hairline rules, an elegant
 *             serif. Small subjects, vast space, slow moves.
 *   STANZA    kinetic type: light ground, black type, one red. The words are the
 *             picture; the phone and the map are secondary marks.
 *
 * Same content in all three: a phone, a world, a number. Render one with
 *   node films/style_probe.mjs --style signal --frames /tmp/sig --fps 30
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { drawShape } from '../motion/kit/shapes.mjs';
import { drawMap } from '../motion/kit/world.mjs';
import { drawType } from '../motion/kit/type.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { text, clamp, ease } from '../motion/ui.mjs';

const W = 1280;
const H = 720;
const HERE = path.dirname(fileURLToPath(import.meta.url));

/* ---------------------------------------------------------------- type ---- */

const FONT = {
  poster: 'Anton',
  serif: 'Instrument Serif',
  sans: 'Inter',
};

function type(ctx, value, x, y, opts = {}) {
  const {
    size = 80, weight = 700, family = FONT.sans, colour = '#000',
    align = 'left', tracking = 0, alpha = 1, baseline = 'alphabetic',
  } = opts;
  ctx.save();
  ctx.globalAlpha *= alpha;
  ctx.font = `${weight} ${size}px "${family}"`;
  ctx.fillStyle = colour;
  ctx.textAlign = align;
  ctx.textBaseline = baseline;
  if (tracking) {
    // Canvas letterSpacing is not everywhere, so space by hand when asked.
    const chars = [...value];
    const widths = chars.map((c) => ctx.measureText(c).width + tracking);
    const total = widths.reduce((a, b) => a + b, 0) - tracking;
    let cx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
    ctx.textAlign = 'left';
    chars.forEach((c, i) => { ctx.fillText(c, cx, y); cx += widths[i]; });
  } else {
    ctx.fillText(value, x, y);
  }
  ctx.restore();
}

/** A word that rises out of its own baseline, masked by the line above it. */
function rise(ctx, value, x, y, opts = {}) {
  const { p = 1, size = 80, weight = 700, family = FONT.sans, colour = '#000', align = 'left', clip = true } = opts;
  const k = ease.outCubic(clamp(p));
  ctx.save();
  if (clip) {
    ctx.beginPath();
    ctx.rect(x - size * 3, y - size * 1.02, size * 22, size * 1.12);
    ctx.clip();
  }
  ctx.globalAlpha *= clamp(p * 1.6);
  ctx.translate(0, (1 - k) * size * 1.05);
  type(ctx, value, x, y, { size, weight, family, colour, align });
  ctx.restore();
}

const stillCam = () => ({ zoom: 1, at: [0.5, 0.5], rotate: 0 });

/* --------------------------------------------------------------- SIGNAL ---- */

const SIGNAL = {
  ground: '#0A0A0B',
  ink: '#F6F2E7',
  hot: '#FF4B12',
  dim: '#6E6A62',
};

function signalPhone(ctx, { x, y, w, h, p }) {
  const ring = (r, a, width) => {
    ctx.save();
    ctx.strokeStyle = SIGNAL.hot;
    ctx.globalAlpha *= a;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.arc(x + w / 2, y + h / 2, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  };
  const t = clamp(p);
  ring(w * (0.58 + t * 0.22), 0.85 * (1 - t), 5);
  ring(w * (0.46 + t * 0.18), 0.55 * (1 - t), 3);
  drawShape(ctx, 'phone-classic', {
    x, y, w, h, p: 1,
    palette: { text: SIGNAL.ink, caption: SIGNAL.hot },
    params: { fill: SIGNAL.ink, keyInk: SIGNAL.ground, stroke: SIGNAL.ink },
  });
}

const signalShots = [
  {
    id: 'signal-1',
    dur: 2.3,
    background: SIGNAL.ground,
    camera: stillCam,
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0 },
    layers: [
      {
        id: 'phone', depth: 1,
        draw: (ctx) => signalPhone(ctx, { x: W * 0.765, y: H * 0.19, w: W * 0.165, h: H * 0.62, p: 0.9 }),
      },
      {
        id: 'word', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          // The type is the composition: two words, one cropped by the frame edge.
          ctx.save();
          ctx.globalAlpha *= clamp(p * 1.4);
          // 190, not 250: two lines of Anton at 250 ran into the handset, and a
          // collision is not a composition.
          type(ctx, 'ONE', W * 0.055, H * 0.50, { size: 190, family: FONT.poster, colour: SIGNAL.ink });
          type(ctx, 'PHONE', W * 0.055, H * 0.76, { size: 190, family: FONT.poster, colour: SIGNAL.hot });
          ctx.restore();
        },
      },
      {
        id: 'rule', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.fillStyle = SIGNAL.hot;
          ctx.globalAlpha *= clamp(p * 2);
          ctx.fillRect(W * 0.055, H * 0.075, W * 0.34 * ease.outCubic(clamp(p * 1.2)), 8);
          ctx.restore();
          type(ctx, 'NOKIA · 1994', W * 0.055, H * 0.92, {
            size: 20, weight: 700, family: FONT.sans, colour: SIGNAL.dim, tracking: 5, alpha: clamp(p * 2),
          });
        },
      },
    ],
  },
  {
    id: 'signal-2',
    dur: 2.3,
    background: SIGNAL.ground,
    camera: stillCam,
    transition: { kind: 'cut', label: 'cut', options: {} },
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0 },
    layers: [
      {
        id: 'map', depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.globalAlpha *= clamp(p * 2.2);
          drawMap(ctx, {
            x: -W * 0.04, y: H * 0.02, w: W * 1.08, h: H * 0.70, p: 1,
            projection: 'winkel', graticule: false,
            land: SIGNAL.hot, landEdge: SIGNAL.hot,
            palette: { text: SIGNAL.ink, caption: SIGNAL.hot },
          });
          ctx.restore();
        },
      },
      {
        id: 'word', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          // Inverted type over the silhouette: the map is the ground, the words
          // are knocked out of it.
          // Both words in cream, in the empty band under the map. The knockout
          // version put near-black type on red and it simply disappeared.
          rise(ctx, 'EVERY', W * 0.045, H * 0.755, {
            p, size: 118, family: FONT.poster, colour: SIGNAL.ink,
          });
          rise(ctx, 'POCKET', W * 0.045, H * 0.925, {
            p: clamp((p - 0.18) / 0.8), size: 118, family: FONT.poster, colour: SIGNAL.hot,
          });
        },
      },
    ],
  },
  {
    id: 'signal-3',
    dur: 1.8,
    background: SIGNAL.ground,
    camera: stillCam,
    transition: { kind: 'cut', label: 'cut', options: {} },
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0 },
    layers: [
      {
        id: 'block', depth: 1,
        draw: (ctx, { p }) => {
          const k = ease.outCubic(clamp(p * 1.5));
          ctx.save();
          ctx.fillStyle = SIGNAL.hot;
          ctx.fillRect(0, H * 0.30, W * k, H * 0.44);
          ctx.restore();
        },
      },
      {
        id: 'stat', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.globalAlpha *= clamp((p - 0.25) * 3);
          type(ctx, '1 IN 3', W * 0.5, H * 0.62, {
            size: 190, family: FONT.poster, colour: SIGNAL.ground, align: 'center',
          });
          ctx.restore();
          type(ctx, 'OF EVERY PHONE SOLD ON EARTH · 2007', W * 0.5, H * 0.86, {
            size: 22, weight: 700, colour: SIGNAL.ink, align: 'center', tracking: 6,
            alpha: clamp((p - 0.45) * 3),
          });
        },
      },
    ],
  },
];

/* ------------------------------------------------------------- MONOLITH ---- */

const MONO = {
  ground: '#04060A',
  ink: '#DED9CE',
  gold: '#C9A227',
  dim: '#6B6F78',
};

const monoShots = [
  {
    id: 'mono-1',
    dur: 2.3,
    background: MONO.ground,
    camera: (t) => ({ zoom: 1 + t * 0.06, at: [0.5, 0.5], rotate: 0 }),
    grade: {
      vignetteStrength: 0.42, grainAmount: 0.30, paper: false, riso: 0, tooth: 0.04,
      bloomAt: [0.5, 0.44], bloomStrength: 0.20,
    },
    layers: [
      {
        id: 'ring', depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.strokeStyle = MONO.gold;
          ctx.globalAlpha *= 0.5 * clamp(p * 1.5);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(W * 0.5, H * 0.42, H * 0.28, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();
        },
      },
      {
        id: 'phone', depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.globalAlpha *= clamp((p - 0.1) * 2);
          drawShape(ctx, 'phone-classic', {
            x: W * 0.5 - 60, y: H * 0.20, w: 120, h: 264, p: 1,
            palette: { text: MONO.ink, caption: MONO.gold },
            params: { fill: 'rgba(0,0,0,0)', keyInk: MONO.ink, stroke: MONO.ink },
          });
          ctx.restore();
        },
      },
      {
        id: 'title', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          ctx.save();
          ctx.globalAlpha *= clamp((p - 0.2) * 1.8);
          type(ctx, 'It starts with a phone', W * 0.5, H * 0.80, {
            size: 54, weight: 400, family: FONT.serif, colour: MONO.ink, align: 'center',
          });
          ctx.restore();
          const k = clamp((p - 0.45) * 2);
          ctx.save();
          ctx.fillStyle = MONO.gold;
          ctx.globalAlpha *= k;
          ctx.fillRect(W * 0.5 - 120 * k, H * 0.855, 240 * k, 1);
          ctx.restore();
          type(ctx, 'N O K I A   ·   T H E   O P E N I N G', W * 0.5, H * 0.90, {
            size: 15, weight: 400, colour: MONO.dim, align: 'center', alpha: clamp((p - 0.55) * 2),
          });
        },
      },
    ],
  },
  {
    id: 'mono-2',
    dur: 2.3,
    background: MONO.ground,
    camera: (t) => ({ zoom: 1 + t * 0.10, at: [0.5, 0.46], rotate: 0 }),
    transition: { kind: 'dissolve', label: 'dissolve', options: {} },
    grade: {
      vignetteStrength: 0.42, grainAmount: 0.30, paper: false, riso: 0, tooth: 0.04,
      bloomAt: [0.5, 0.4], bloomStrength: 0.16,
    },
    layers: [
      {
        id: 'map', depth: 1,
        draw: (ctx, { p }) => {
          // Outline only: the land is a hairline, not a fill. It reads as a
          // drawing of the world rather than a graphic of it.
          ctx.save();
          ctx.globalAlpha *= clamp((p - 0.1) * 2);
          drawMap(ctx, {
            x: W * 0.08, y: H * 0.13, w: W * 0.84, h: H * 0.64, p: 1,
            projection: 'winkel', graticule: false,
            land: 'rgba(201,162,39,0.13)', landEdge: 'rgba(222,217,206,0.55)',
            palette: { text: MONO.ink, caption: MONO.gold },
          });
          ctx.restore();
        },
      },
      {
        id: 'caption', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          type(ctx, 'in every pocket on earth', W * 0.5, H * 0.885, {
            size: 44, weight: 400, family: FONT.serif, colour: MONO.ink, align: 'center',
            alpha: clamp((p - 0.35) * 2),
          });
        },
      },
    ],
  },
  {
    id: 'mono-3',
    dur: 1.8,
    background: MONO.ground,
    camera: stillCam,
    transition: { kind: 'dissolve', label: 'dissolve', options: {} },
    grade: {
      vignetteStrength: 0.46, grainAmount: 0.30, paper: false, riso: 0, tooth: 0.04,
      bloomAt: [0.5, 0.44], bloomStrength: 0.16,
    },
    layers: [
      {
        id: 'stat', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          const k = ease.outCubic(clamp(p * 1.4));
          type(ctx, 'one in three', W * 0.5, H * 0.47, {
            size: 128, weight: 400, family: FONT.serif, colour: MONO.ink, align: 'center',
            alpha: clamp(p * 2),
          });
          ctx.save();
          ctx.fillStyle = MONO.gold;
          ctx.globalAlpha *= clamp((p - 0.3) * 2.5);
          ctx.fillRect(W * 0.5 - 180 * k, H * 0.53, 360 * k, 1);
          ctx.restore();
          type(ctx, 'O F   E V E R Y   P H O N E   S O L D   ·   2 0 0 7', W * 0.5, H * 0.60, {
            size: 14, weight: 400, colour: MONO.dim, align: 'center', alpha: clamp((p - 0.45) * 2.5),
          });
        },
      },
    ],
  },
];

/* --------------------------------------------------------------- STANZA ---- */

const STANZA = {
  ground: '#F1EDE4',
  ink: '#111111',
  red: '#E4002B',
};

const stanzaShots = [
  {
    id: 'stanza-1',
    dur: 2.3,
    background: STANZA.ground,
    camera: (t) => ({ zoom: 1 + t * 0.05, at: [0.5, 0.5], rotate: 0 }),
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0.05 },
    layers: [
      {
        id: 'stamp', depth: 1,
        draw: (ctx, { p }) => {
          // The object is a mark behind the words, not a picture beside them.
          ctx.save();
          ctx.globalAlpha *= 0.14 * clamp(p * 2);
          ctx.translate(W * 0.70, H * 0.44);
          ctx.rotate(-0.06);
          ctx.translate(-W * 0.70, -H * 0.44);
          drawShape(ctx, 'phone-classic', {
            x: W * 0.70 - 90, y: H * 0.16, w: 180, h: 380, p: 1,
            palette: { text: STANZA.ink, caption: STANZA.red },
            params: { fill: STANZA.ink, keyInk: STANZA.ground },
          });
          ctx.restore();
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          rise(ctx, 'IT STARTS', W * 0.04, H * 0.40, {
            p, size: 132, weight: 900, colour: STANZA.ink,
          });
          rise(ctx, 'WITH A', W * 0.04, H * 0.56, {
            p: clamp((p - 0.14) / 0.86), size: 132, weight: 900, colour: STANZA.ink,
          });
          rise(ctx, 'PHONE', W * 0.04, H * 0.72, {
            p: clamp((p - 0.28) / 0.72), size: 132, weight: 900, colour: STANZA.red,
          });
        },
      },
      {
        id: 'edge', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          // A red block that slides in from the frame edge and stops as a margin.
          const k = ease.outCubic(clamp((p - 0.1) * 1.6));
          ctx.save();
          ctx.fillStyle = STANZA.red;
          ctx.fillRect(W - (1 - k) * W * 0.10 - W * 0.012, 0, W * 0.012, H);
          ctx.restore();
        },
      },
    ],
  },
  {
    id: 'stanza-2',
    dur: 2.3,
    background: STANZA.ground,
    camera: stillCam,
    transition: { kind: 'cut', label: 'cut', options: {} },
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0.05 },
    layers: [
      {
        id: 'map', depth: 1,
        draw: (ctx, { p }) => {
          // The map slides while the words are still arriving: type and picture
          // move on different clocks, which is what makes it feel designed.
          const drift = -W * 0.10 * (1 - ease.outCubic(clamp(p * 0.8)));
          ctx.save();
          ctx.globalAlpha *= clamp(p * 2.4) * 0.9;
          drawMap(ctx, {
            x: W * 0.46 + drift, y: H * 0.30, w: W * 0.60, h: H * 0.54, p: 1,
            projection: 'winkel', graticule: false,
            land: STANZA.red, landEdge: STANZA.red,
            palette: { text: STANZA.ink, caption: STANZA.red },
          });
          ctx.restore();
        },
      },
      {
        id: 'words', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          rise(ctx, 'EVERY', W * 0.04, H * 0.36, {
            p, size: 120, weight: 900, colour: STANZA.ink,
          });
          rise(ctx, 'POCKET', W * 0.04, H * 0.50, {
            p: clamp((p - 0.12) / 0.88), size: 120, weight: 900, colour: STANZA.ink,
          });
          type(ctx, 'ON EARTH', W * 0.04, H * 0.63, {
            size: 30, weight: 700, colour: STANZA.red, tracking: 8,
            alpha: clamp((p - 0.4) * 3),
          });
        },
      },
    ],
  },
  {
    id: 'stanza-3',
    dur: 1.8,
    background: STANZA.ink,
    camera: stillCam,
    transition: { kind: 'cut', label: 'cut', options: {} },
    grade: { vignetteStrength: 0, grainAmount: 0, paper: false, riso: 0, tooth: 0.05 },
    layers: [
      {
        id: 'stat', screen: true, depth: 1,
        draw: (ctx, { p }) => {
          // One number, enormous, with the frame cropping it.
          const k = ease.outCubic(clamp(p * 1.5));
          type(ctx, '1', W * 0.06, H * 0.74, {
            size: 460 * (0.9 + k * 0.1), weight: 900, family: FONT.serif,
            colour: STANZA.ground, alpha: clamp(p * 2),
          });
          ctx.save();
          ctx.fillStyle = STANZA.red;
          ctx.globalAlpha *= clamp((p - 0.2) * 3);
          ctx.fillRect(W * 0.30, H * 0.22, W * 0.012, H * 0.56 * k);
          ctx.restore();
          type(ctx, 'IN', W * 0.315, H * 0.40, {
            size: 46, weight: 900, colour: STANZA.ground, alpha: clamp((p - 0.25) * 3),
          });
          type(ctx, '3', W * 0.305, H * 0.75, {
            size: 210, weight: 900, colour: STANZA.ground, alpha: clamp((p - 0.35) * 3),
          });
          type(ctx, 'PHONES SOLD WORLDWIDE', W * 0.52, H * 0.745, {
            size: 22, weight: 700, colour: STANZA.ground, tracking: 4, alpha: clamp((p - 0.5) * 3),
          });
        },
      },
    ],
  },
];

/* ------------------------------------------------------------------ cli ---- */

export const STYLES = { signal: signalShots, monolith: monoShots, stanza: stanzaShots };

const main = async () => {
  const args = process.argv.slice(2);
  const flag = (name) => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : null;
  };
  const styleName = flag('--style') || 'signal';
  const shots = STYLES[styleName];
  if (!shots) throw new Error(`unknown style ${styleName}; have ${Object.keys(STYLES).join(', ')}`);
  const fonts = loadFonts();
  const fps = Number(flag('--fps') || 30);
  const out = flag('--frames');
  const seconds = shots.reduce((a, s) => a + s.dur, 0);
  console.log(`${styleName}: ${seconds.toFixed(1)}s, ${fonts} fonts`);
  if (!out) return;

  fs.mkdirSync(out, { recursive: true });
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(shots, W, H, { join: 0.4, background: shots[0].background });
  const total = Math.round(renderer.duration * fps);
  for (let i = 0; i < total; i += 1) {
    ctx.clearRect(0, 0, W, H);
    renderer.render(ctx, i / fps);
    fs.writeFileSync(path.join(out, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
  }
  console.log(`wrote ${total} frames to ${out}`);
};

if (import.meta.url === `file://${process.argv[1]}`) main();
