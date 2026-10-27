/**
 * NOKIA: THE RISE AND FALL OF A $300 BILLION EMPIRE
 *
 * The second film written against the motion kit, and the first written from
 * somebody else's script. The narration in `empire_narration.json` is the
 * author's, word for word; this file splits it at sentence boundaries and gives
 * every beat a picture. Nothing is re-written, because a film that quietly
 * edits its own script is a film nobody can check.
 *
 * House style is imported, not re-implemented: the seven shot builders, the
 * twelve worlds, the type helpers and the join grammar all come from
 * `nokia_full.mjs`. A second film that draws its own charts is a second film
 * that drifts.
 *
 *   node films/nokia_empire.mjs                        # the shot list
 *   node films/nokia_empire.mjs --lines /tmp/l.json    # narration lines
 *   node films/nokia_empire.mjs --starts /tmp/s.json   # the clock
 *   node films/nokia_empire.mjs --stills /tmp/st --scale 0.5
 *   node films/nokia_empire.mjs --pipe --scale 1.5 --fps 24 --from 0 --to 200
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';
import { createRenderer } from '../motion/kit/timeline.mjs';
import { drawHandset } from '../motion/kit/product.mjs';
import {
  drawSmartphone, drawMill, drawPaperReam, drawRubberSheet, drawCableDrum,
  drawChip, drawPlinth, contact, drawCityscape, drawRooftop, drawPine,
} from '../motion/kit/objects.mjs';
import { optics, frameBuffer, opticsFor } from '../motion/kit/optics.mjs';
import { span, clamp, ease } from '../motion/ui.mjs';
import {
  W, H, text, caps, rise, rule,
  typeShot, objectShot, chartShot, mapShot, bandsShot, compareShot, endShot, T,
} from './nokia_full.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/* ------------------------------------------------------------- helpers ---- */

/** A handset standing on the floor of a room, with its own contact shadow. */
function handset({
  x = 0.42, y = 0.26, w = 0.16, h = 0.56, facing = 0.16, glow = 0.8,
  body = ['#5E5A52', '#211E1A', '#413D36'], screen = 'menu', floor = 0.845, antenna = true,
} = {}) {
  return (ctx, { glow: g = 1 } = {}) => {
    contact(ctx, W * (x + w / 2), H * floor, W * (w * 0.95), H * 0.022, 0.55);
    drawHandset(ctx, {
      x: W * x, y: H * y, w: W * w, h: H * h, facing,
      screen, glow: glow * g, body, antenna, bezel: '#0D0E0C',
    });
  };
}

/** Stylized 1980s/early-GSM handset silhouette with an external antenna. */
function earlyHandset({ x = 0.42, y = 0.29, w = 0.16, h = 0.51, glow = 0.6 } = {}) {
  return (ctx) => {
    contact(ctx, W * (x + w / 2), H * 0.845, W * (w * 1.1), H * 0.022, 0.55);
    ctx.save();
    ctx.fillStyle = '#25282B';
    ctx.fillRect(W * (x + w * 0.16), H * (y - 0.14), W * w * 0.07, H * 0.15);
    ctx.fillStyle = '#16191C';
    ctx.fillRect(W * x, H * y, W * w, H * h);
    ctx.fillStyle = '#555B5C';
    ctx.fillRect(W * (x + w * 0.08), H * (y + h * 0.05), W * w * 0.84, H * h * 0.9);
    ctx.fillStyle = `rgba(173,204,150,${0.5 + glow * 0.3})`;
    ctx.fillRect(W * (x + w * 0.19), H * (y + h * 0.18), W * w * 0.62, H * h * 0.16);
    ctx.fillStyle = '#252A2A';
    for (let row = 0; row < 4; row += 1) {
      for (let col = 0; col < 3; col += 1) {
        ctx.fillRect(W * (x + w * (0.19 + col * 0.22)), H * (y + h * (0.46 + row * 0.10)), W * w * 0.16, H * h * 0.07);
      }
    }
    ctx.restore();
  };
}

/** Three handsets at three sizes: a decade in one frame. */
function handsetRow(specs, floor = 0.845) {
  return (ctx, { glow = 1 } = {}) => {
    for (const s of specs) {
      contact(ctx, W * (s.x + s.w / 2), H * floor, W * (s.w * 0.9), H * 0.018, 0.45);
      drawHandset(ctx, {
        x: W * s.x, y: H * s.y, w: W * s.w, h: H * s.h, facing: s.facing ?? 0.12,
        screen: s.screen || 'menu', glow: (s.glow ?? 0.7) * glow,
        body: s.body || ['#5E5A52', '#211E1A', '#413D36'], bezel: '#0D0E0C',
      });
    }
  };
}

const plinth = (colour = 'rgba(255,255,255,0.035)') => (ctx) => {
  drawPlinth(ctx, { x: 0, y: H * 0.86, w: W, h: H * 0.15, colour });
};

const S = (k, w, t, o = {}) => ({ k, w, t, o });

/* --------------------------------------------------------------- script ---- */

const SCENES = [
  {
    n: 1,
    name: 'THE EMPIRE THAT LOST THE FUTURE',
    world: 'graphite',
    shots: [
      S('object', 'graphite', 'Imagine building a company so powerful that billions of people around the world carry its products in their pockets.', {
        kicker: 'ESPOO · FINLAND',
        draw: handset({ x: 0.43, y: 0.24, w: 0.15, h: 0.60, glow: 0.35 }),
      }),
      S('type', 'gold', 'A company whose name becomes almost synonymous with mobile phones.', {
        kicker: 'THE NAME',
        lines: [{ text: 'Nokia.', size: 150, at: 0.08, colour: '#E2B94F' }],
        top: 0.50,
      }),
      S('object', 'amber', 'A company whose devices survive drops, outlast batteries, and become legendary for their durability.', {
        kicker: 'DURABILITY',
        caption: 'Drop it. It still works.',
        draw: handsetRow([
          { x: 0.30, y: 0.34, w: 0.10, h: 0.42, glow: 0.5 },
          { x: 0.45, y: 0.28, w: 0.12, h: 0.50, glow: 0.8 },
          { x: 0.60, y: 0.36, w: 0.09, h: 0.38, glow: 0.4 },
        ]),
      }),
      S('type', 'ash', 'For millions of people, that company was Nokia.', {
        lines: [
          { text: 'For millions of people,', size: 40, at: 0.06, colour: 'rgba(233,231,226,0.62)', gap: 0.11 },
          { text: 'that company was Nokia.', size: 72, at: 0.16, gap: 0.16 },
        ],
        top: 0.40,
      }),
      S('chart', 'gold', 'At its peak, Nokia dominated the mobile phone industry.', {
        // Gartner's full-year end-user sales, not Nokia's separate Q4 estimate.
        kicker: 'ALL PHONES SOLD · GARTNER · 2007',
        caption: 'Nearly forty percent.',
        bars: [
          { label: 'Nokia', value: 37.8, hot: true },
          { label: 'Samsung', value: 13.4 },
          { label: 'Motorola', value: 14.3 },
          { label: 'Sony Ericsson', value: 8.8 },
          { label: 'Others', value: 25.7 },
        ],
        lit: 0.0,
      }),
      S('map', 'gold', 'Its devices were everywhere, from crowded streets in Asia to offices in Europe and homes across Africa.', {
        kicker: 'EVERYWHERE',
        caption: 'Every market at once.',
        arcs: [
          { from: 'helsinki', to: 'london', t: 0.42, colour: 'rgba(226,185,79,0.50)', width: 1.4, head: false },
          { from: 'helsinki', to: 'delhi', t: 0.50, colour: 'rgba(226,185,79,0.48)', width: 1.4, head: false },
          { from: 'helsinki', to: 'lagos', t: 0.58, colour: 'rgba(226,185,79,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'beijing', t: 0.66, colour: 'rgba(226,185,79,0.42)', width: 1.3, head: false },
          { from: 'helsinki', to: 'newyork', t: 0.74, colour: 'rgba(226,185,79,0.38)', width: 1.3, head: false },
        ],
      }),
      S('type', 'ash', 'But then, something extraordinary happened.', {
        lines: [{ text: 'And then', size: 66, at: 0.08, colour: 'rgba(233,231,226,0.66)', gap: 0.13 },
          { text: 'it turned.', size: 96, at: 0.20 }],
        top: 0.40,
        transition: T('iris'),
      }),
      S('chart', 'cold', 'In just a few years, the company that once ruled the mobile world found itself struggling to survive.', {
        // Keep the denominator and full-year period consistent throughout.
        // The previous 3% was a smartphone estimate, not all phones sold.
        kicker: 'ALL PHONES SOLD · GARTNER · PERCENT',
        caption: 'Six years.',
        bars: [
          { label: '2007', value: 37.8, hot: true },
          { label: '2009', value: 36.4 },
          { label: '2011', value: 23.8 },
          { label: '2012', value: 19.1 },
          { label: '2013', value: 13.9 },
        ],
        lit: 0.0,
      }),
      S('compare', 'graphite', 'A new generation of smartphones arrived.', {
        kicker: 'TWO IDEAS OF A PHONE',
        leftLabel: '2006 · KEYPAD',
        rightLabel: '2007 · TOUCHSCREEN',
        caption: 'The industry changed shape.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.20, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.14, screen: 'menu', glow: 0.5 }),
        right: (ctx, { glow }) => drawSmartphone(ctx, { x: W * 0.66, y: H * 0.28, w: W * 0.10, h: H * 0.46, glow }),
      }),
      S('type', 'graphite', 'Touchscreens replaced buttons.', {
        kicker: 'WHAT PEOPLE STARTED ASKING FOR',
        lines: [
          { text: 'Glass.', size: 74, at: 0.06, gap: 0.12 },
          { text: 'And software.', size: 74, at: 0.18, colour: 'rgba(237,234,226,0.70)' },
        ],
        top: 0.40,
      }),
      S('chart', 'graphite', 'Apps became more important than hardware.', {
        kicker: 'APPLICATIONS AVAILABLE · 2011, THOUSANDS',
        caption: 'Half a million, against fifty.',
        bars: [
          { label: 'App Store', value: 500, hot: true },
          { label: 'Android', value: 300 },
          { label: 'Ovi', value: 50 },
        ],
        lit: 0.0,
      }),
      S('type', 'ash', 'And the company that had helped connect the world suddenly seemed unable to understand where the world was going.', {
        lines: [
          { text: 'It had connected', size: 52, at: 0.06, colour: 'rgba(233,231,226,0.70)', gap: 0.12 },
          { text: 'the world.', size: 52, at: 0.15, colour: 'rgba(233,231,226,0.70)', gap: 0.16 },
          { text: 'Then lost it.', size: 86, at: 0.28 },
        ],
        top: 0.34,
      }),
      S('type', 'gold', 'This is the story of Nokia.', {
        kicker: 'FROM 1865 TO TODAY',
        lines: [{ text: 'This is the story', size: 74, at: 0.08, gap: 0.14 },
          { text: 'of a company', size: 74, at: 0.20, colour: 'rgba(243,238,226,0.72)', gap: 0.16 },
          { text: 'that had it all.', size: 74, at: 0.34, colour: '#E2B94F' }],
        top: 0.34,
        transition: T('fade', { dip: 'paper' }),
      }),
      S('bands', 'sepia', 'A company that rose from humble beginnings to become a global technology giant,', {
        kicker: 'ONE COMPANY, FIVE INDUSTRIES',
        bands: [
          { label: 'Paper', sub: '1865', colour: 'rgba(226,185,79,0.66)' },
          { label: 'Rubber', sub: '1898', colour: 'rgba(196,105,46,0.56)' },
          { label: 'Cable', sub: '1912', colour: 'rgba(150,150,160,0.50)' },
          { label: 'Phones', sub: '1981', colour: 'rgba(120,160,210,0.46)' },
          { label: 'Networks', sub: '2016', colour: 'rgba(80,190,175,0.46)' },
        ],
        caption: 'Started with paper.',
      }),
      S('type', 'ash', 'dominated an entire industry, ignored crucial warning signs, and lost its leadership in the smartphone revolution.', {
        lines: [
          { text: 'Dominated.', size: 58, at: 0.05, gap: 0.10 },
          { text: 'Ignored the signs.', size: 58, at: 0.15, colour: 'rgba(233,231,226,0.74)', gap: 0.10 },
          { text: 'Lost the lead.', size: 58, at: 0.25, colour: 'rgba(233,231,226,0.50)' },
        ],
        top: 0.40,
      }),
      S('type', 'ash', 'And the most shocking part?', {
        lines: [{ text: 'And the most', size: 46, at: 0.10, colour: 'rgba(233,231,226,0.55)', gap: 0.11 },
          { text: 'shocking part?', size: 92, at: 0.24 }],
        top: 0.42,
        transition: T('cut'),
      }),
      S('type', 'gold', 'Nokia didn\'t simply lose because it couldn\'t build a phone. It lost because the rules of the entire industry changed.', {
        kicker: 'THE ARGUMENT',
        lines: [
          { text: 'It did not lose', size: 46, at: 0.05, colour: 'rgba(243,238,226,0.62)', gap: 0.11 },
          { text: 'the phone.', size: 46, at: 0.14, colour: 'rgba(243,238,226,0.62)', gap: 0.18 },
          { text: 'The rules changed.', size: 84, at: 0.30, colour: '#E2B94F' },
        ],
        top: 0.36,
      }),
    ],
  },
  {
    n: 2,
    name: 'FROM A PAPER MILL TO A GLOBAL COMPANY',
    world: 'sepia',
    shots: [
      S('type', 'sepia', 'The Nokia story began long before smartphones, mobile networks, or even the modern electronics industry existed.', {
        kicker: 'ACT II · 1865',
        lines: [
          { text: 'Before the phone,', size: 56, at: 0.06, gap: 0.12 },
          { text: 'there was paper.', size: 56, at: 0.18, colour: 'rgba(242,230,204,0.72)' },
        ],
        top: 0.40,
        transition: T('wipe', { direction: 'left' }),
      }),
      S('object', 'sepia', 'In 1865, Finnish engineer Fredrik Idestam established a wood-pulp mill near the town of Tampere.', {
        kicker: '1865 · TAMPERE',
        caption: 'A wood-pulp mill, and a river.',
        draw: (ctx, { p }) => {
          drawPine(ctx, { x: W * 0.10, y: H * 0.52, h: H * 0.34, colour: 'rgba(24,18,12,0.85)' });
          drawPine(ctx, { x: W * 0.86, y: H * 0.56, h: H * 0.28, colour: 'rgba(24,18,12,0.8)' });
          drawMill(ctx, { x: W * 0.28, y: H * 0.34, w: W * 0.44, h: H * 0.50 });
        },
      }),
      S('object', 'sepia', 'His business focused on producing paper, a valuable industrial product during a period of growing demand.', {
        kicker: 'THE FIRST PRODUCT',
        caption: 'Paper.',
        draw: (ctx) => {
          contact(ctx, W * 0.5, H * 0.845, W * 0.17, H * 0.022, 0.45);
          drawPaperReam(ctx, { x: W * 0.35, y: H * 0.40, w: W * 0.30, h: H * 0.44, colour: '#F2ECDD', edge: '#CFC7B4' });
        },
      }),
      S('type', 'sepia', 'A few years later, he established another mill near the Nokianvirta River.', {
        // A world map cannot accurately identify this river at this scale.
        kicker: 'THE NOKIANVIRTA',
        lines: [
          { text: 'A second mill.', size: 58, at: 0.06, gap: 0.12 },
          { text: 'A river, and a name.', size: 58, at: 0.18, colour: 'rgba(242,230,204,0.72)' },
        ],
        top: 0.40,
      }),
      S('type', 'sepia', 'The name Nokia eventually became associated with the company.', {
        kicker: 'THE NAME',
        lines: [{ text: 'Nokia.', size: 128, at: 0.08 }],
        top: 0.48,
        note: 'A town on a river, sixty-one degrees north.',
      }),
      S('type', 'sepia', 'But the business that would one day dominate mobile phones did not begin by making phones at all.', {
        kicker: '1865',
        lines: [
          { text: 'Not for', size: 46, at: 0.05, colour: 'rgba(242,230,204,0.60)', gap: 0.11 },
          { text: 'another century.', size: 80, at: 0.17 },
        ],
        top: 0.42,
        note: 'The first mobile phone came in 1982.',
      }),
      S('bands', 'sepia', 'Over the following decades, the Nokia name became connected with different industrial operations.', {
        kicker: '1871 — 1912',
        bands: [
          { label: 'Paper', sub: '1865', colour: 'rgba(226,185,79,0.62)' },
          { label: 'Rubber', sub: '1898', colour: 'rgba(196,105,46,0.54)' },
          { label: 'Cable', sub: '1912', colour: 'rgba(150,150,160,0.46)' },
        ],
        caption: 'Three trades, one town.',
      }),
      S('object', 'copper', 'The company expanded beyond paper production, while other Finnish businesses developed rubber products and electrical equipment.', {
        kicker: '1898 · RUBBER',
        caption: 'Boots, tyres, groundsheets.',
        draw: (ctx) => {
          contact(ctx, W * 0.5, H * 0.845, W * 0.19, H * 0.022, 0.5);
          drawRubberSheet(ctx, { x: W * 0.31, y: H * 0.46, w: W * 0.38, h: H * 0.36 });
        },
      }),
      S('object', 'steel', 'Eventually, these separate industrial histories converged.', {
        kicker: '1912 · CABLE',
        caption: 'Copper wire, and the networks a town needs.',
        draw: (ctx) => {
          contact(ctx, W * 0.5, H * 0.85, W * 0.19, H * 0.022, 0.55);
          drawCableDrum(ctx, { x: W * 0.345, y: H * 0.44, w: W * 0.31, h: H * 0.40 });
        },
      }),
      S('bands', 'sepia', 'In 1967, Nokia Corporation was formed through the merger of Nokia Ab, Finnish Rubber Works, and Finnish Cable Works.', {
        kicker: '1967 · THE MERGER',
        bands: [
          { label: 'Nokia Ab', sub: 'PAPER', colour: 'rgba(226,185,79,0.62)' },
          { label: 'Finnish Rubber Works', sub: 'RUBBER', colour: 'rgba(196,105,46,0.54)' },
          { label: 'Finnish Cable Works', sub: 'CABLE', colour: 'rgba(150,150,160,0.46)' },
        ],
        caption: 'Three companies become one.',
        transition: T('fade', { dip: 'paper' }),
      }),
      S('bands', 'sepia', 'The result was a diversified company with interests spanning several industries. It manufactured everything from cables and rubber products to electronics.', {
        kicker: 'A CONGLOMERATE',
        bands: [
          { label: 'Paper', sub: 'INDUSTRIAL', colour: 'rgba(226,185,79,0.55)' },
          { label: 'Rubber', sub: 'INDUSTRIAL', colour: 'rgba(196,105,46,0.50)' },
          { label: 'Cable', sub: 'INDUSTRIAL', colour: 'rgba(150,150,160,0.44)' },
          { label: 'Electronics', sub: 'THE NEW ONE', colour: 'rgba(120,160,210,0.50)' },
        ],
        caption: 'Four industries, one balance sheet.',
      }),
      S('type', 'sepia', 'This diversity would give Nokia a foundation for future expansion. But its most important opportunity was still ahead.', {
        lines: [
          { text: 'A foundation,', size: 54, at: 0.06, gap: 0.12 },
          { text: 'not a future.', size: 54, at: 0.18, colour: 'rgba(242,230,204,0.70)' },
        ],
        top: 0.40,
        note: 'The opportunity arrived with a radio.',
      }),
      S('type', 'cobalt', 'As telecommunications technology developed, Nokia began investing in an industry that would eventually transform the way humanity communicated.', {
        kicker: 'ACT III · 1981',
        lines: [
          { text: 'Then it bet', size: 52, at: 0.06, colour: 'rgba(228,238,248,0.70)', gap: 0.11 },
          { text: 'on a radio.', size: 92, at: 0.18 },
        ],
        top: 0.40,
      }),
      S('map', 'cobalt', 'And the company was about to discover a market far bigger than anyone could have imagined.', {
        kicker: 'A MARKET NOBODY HAD MEASURED',
        caption: 'Bigger than anyone imagined.',
        land: 'rgba(34,72,132,0.85)',
        landEdge: 'rgba(150,196,240,0.55)',
        arcs: [
          { from: 'helsinki', to: 'stockholm', t: 0.40, colour: 'rgba(201,162,39,0.55)', width: 1.4, head: false },
          { from: 'helsinki', to: 'london', t: 0.48, colour: 'rgba(201,162,39,0.50)', width: 1.4, head: false },
          { from: 'helsinki', to: 'moscow', t: 0.56, colour: 'rgba(201,162,39,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'newyork', t: 0.64, colour: 'rgba(201,162,39,0.40)', width: 1.3, head: false },
        ],
        transition: T('push', { direction: 'left' }),
      }),
    ],
  },

  {
    n: 3,
    name: 'THE BIRTH OF THE MOBILE REVOLUTION',
    world: 'cobalt',
    shots: [
      S('object', 'cobalt', 'During the 1980s, mobile communication was still expensive, complicated, and far from accessible to ordinary people. Early mobile phones were bulky. Networks were limited. And owning a mobile telephone was often a luxury reserved for businesses and wealthy customers.', {
        kicker: '1980s · THE MOBILE AGE BEGINS',
        caption: 'Mobile phones were bulky.',
        draw: earlyHandset({ x: 0.415, y: 0.29, w: 0.17, h: 0.51, glow: 0.45 }),
      }),
      S('compare', 'cobalt', 'But Nokia recognized that the future of telecommunications would depend on something powerful: mobility. People didn\'t want to remain connected only when sitting beside a telephone. They wanted to communicate while traveling, working, and living their everyday lives.', {
        kicker: 'THE IDEA',
        leftLabel: 'THE DESK',
        rightLabel: 'THE ROAD',
        caption: 'Connected, while moving.',
        left: (ctx, { p }) => {
          ctx.save();
          ctx.globalAlpha *= 0.55;
          ctx.fillStyle = 'rgba(150,190,235,0.20)';
          ctx.fillRect(W * 0.17, H * 0.46, W * 0.16, H * 0.12);
          ctx.fillStyle = 'rgba(150,190,235,0.10)';
          ctx.fillRect(W * 0.20, H * 0.42, W * 0.10, H * 0.05);
          ctx.restore();
        },
        right: (ctx) => drawHandset(ctx, { x: W * 0.66, y: H * 0.30, w: W * 0.10, h: H * 0.44, facing: 0.2, screen: 'menu', glow: 0.7 }),
      }),
      S('object', 'cobalt', 'Nokia invested heavily in telecommunications equipment and mobile technology. In 1987, the company introduced the Mobira Cityman, a portable mobile phone designed for the emerging mobile market.', {
        kicker: '1987 · MOBIRA CITYMAN',
        caption: 'A phone you could carry.',
        draw: earlyHandset({ x: 0.415, y: 0.28, w: 0.17, h: 0.52, glow: 0.55 }),
      }),
      S('compare', 'cobalt', 'It was still expensive and relatively large compared with the phones that would follow. But it represented something important. Communication was becoming portable.', {
        kicker: 'THIRTEEN YEARS',
        leftLabel: '1987 · 800 GRAMS',
        rightLabel: '2000 · 133 GRAMS',
        caption: 'The same idea, smaller.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.22, y: H * 0.26, w: W * 0.13, h: H * 0.50, facing: 0.1, screen: 'menu', glow: 0.5 }),
        right: (ctx) => drawHandset(ctx, { x: W * 0.68, y: H * 0.36, w: W * 0.07, h: H * 0.30, facing: 0.1, screen: 'menu', glow: 0.8 }),
      }),
      S('type', 'cobalt', 'Then, in 1991, a GSM call was made using a Nokia phone over a commercial GSM network in Finland.', {
        kicker: '1 JULY 1991 · HELSINKI',
        lines: [
          { text: 'The first GSM call.', size: 68, at: 0.06, gap: 0.13 },
          { text: 'Made on a Nokia.', size: 68, at: 0.18, colour: 'rgba(228,238,248,0.70)' },
        ],
        top: 0.42,
      }),
      S('bands', 'cobalt', 'The technology behind GSM would become one of the foundations of modern mobile communication.', {
        kicker: 'FOUR GENERATIONS',
        bands: [
          { label: 'NMT', sub: '1981 · ANALOGUE', colour: 'rgba(120,160,210,0.55)' },
          { label: 'GSM', sub: '1991 · DIGITAL', colour: 'rgba(150,180,220,0.52)' },
          { label: '3G', sub: '2001 · DATA', colour: 'rgba(190,180,120,0.50)' },
          { label: '4G', sub: '2009 · EVERYTHING', colour: 'rgba(210,160,90,0.52)' },
        ],
        caption: 'A standard every decade.',
      }),
      S('chart', 'cobalt', 'Nokia was now positioned in a rapidly expanding market. The company had industrial experience, telecommunications expertise, and a growing understanding of what consumers wanted.', {
        kicker: 'MOBILE SUBSCRIPTIONS WORLDWIDE, MILLIONS',
        caption: 'The market underneath it.',
        bars: [
          { label: '1990', value: 11 },
          { label: '1993', value: 34 },
          { label: '1996', value: 145 },
          { label: '1999', value: 480, hot: true },
        ],
        lit: 0.0,
        scaleMax: 540,
      }),
      S('object', 'cobalt', 'But the greatest opportunity came when mobile phones began moving beyond wealthy early adopters. The next challenge was to make them smaller, more affordable, more reliable, and easier to use.', {
        kicker: 'SMALLER. CHEAPER. EVERYWHERE.',
        caption: 'The phone leaves the car.',
        draw: handsetRow([
          { x: 0.26, y: 0.40, w: 0.09, h: 0.36, glow: 0.5 },
          { x: 0.38, y: 0.34, w: 0.11, h: 0.44, glow: 0.8 },
          { x: 0.51, y: 0.28, w: 0.13, h: 0.52, glow: 1.0 },
        ]),
      }),
      S('type', 'cobalt', 'Nokia was ready to take that challenge. And over the following decade, it would become one of the most recognizable brands on Earth.', {
        kicker: '1992 — 2000',
        lines: [
          { text: 'Then it went', size: 52, at: 0.06, colour: 'rgba(228,238,248,0.66)', gap: 0.12 },
          { text: 'everywhere.', size: 96, at: 0.18 },
        ],
        top: 0.42,
        transition: T('fade', { dip: 'paper' }),
      }),
    ],
  },
  {
    n: 4,
    name: 'HOW NOKIA CONQUERED THE WORLD',
    world: 'amber',
    shots: [
      S('object', 'amber', 'The 1990s became a turning point for Nokia. In 1992, the company introduced the Nokia 1011, one of its early mass-produced GSM mobile phones.', {
        kicker: '1992 · NOKIA 1011',
        caption: 'An early mass-produced GSM phone.',
        draw: earlyHandset({ x: 0.42, y: 0.28, w: 0.16, h: 0.52, glow: 0.7 }),
      }),
      S('bands', 'amber', 'That same year, Nokia made a major strategic decision. It began focusing its business more heavily on telecommunications. Instead of spreading its attention across multiple industries, the company increasingly concentrated on the technology that would define its future.', {
        kicker: '1992 · THE DECISION',
        bands: [
          { label: 'Telecom', sub: 'STRATEGIC FOCUS', colour: 'rgba(226,185,79,0.66)' },
          { label: 'Rubber', sub: 'EARLIER BUSINESS', colour: 'rgba(196,105,46,0.34)' },
          { label: 'Cable', sub: 'EARLIER BUSINESS', colour: 'rgba(150,150,160,0.30)' },
          { label: 'Paper', sub: 'EARLIER BUSINESS', colour: 'rgba(226,185,79,0.26)' },
        ],
        // Divestitures occurred over several years, not all in 1992.
        caption: 'A new strategic focus.',
      }),
      S('chart', 'amber', 'The decision helped Nokia become more focused as mobile communications expanded around the world. Its phones offered a combination that customers valued: dependable performance, practical design, and increasingly accessible technology.', {
        // Nokia annual reports; company sales, not estimates of the whole market.
        kicker: 'NOKIA PHONE SALES · MILLIONS',
        caption: '40.8m to 128.4m.',
        bars: [
          { label: '1998', value: 40.8 },
          { label: '1999', value: 78.5 },
          { label: '2000', value: 128.4, hot: true },
        ],
        lit: 0.9,
      }),
      S('type', 'amber', 'Nokia also understood something that competitors sometimes overlooked. A mobile phone wasn\'t just a technical device. It was a personal product.', {
        lines: [
          { text: 'Not a device.', size: 50, at: 0.06, colour: 'rgba(243,238,226,0.62)', gap: 0.13 },
          { text: 'A personal object.', size: 76, at: 0.20 },
        ],
        top: 0.40,
      }),
      S('bands', 'amber', 'People wanted something that felt comfortable in their hands, looked attractive, and worked reliably throughout the day. Nokia responded with a growing range of devices for different customers.', {
        kicker: 'ONE RANGE, MANY CUSTOMERS',
        bands: [
          { label: 'Business', sub: 'COMMUNICATOR', colour: 'rgba(160,170,190,0.42)' },
          { label: 'Youth', sub: '3210', colour: 'rgba(226,185,79,0.50)' },
          { label: 'Camera', sub: '7650', colour: 'rgba(196,105,46,0.44)' },
          { label: 'Music', sub: 'N91', colour: 'rgba(150,190,170,0.40)' },
        ],
        caption: 'A phone for each pocket.',
      }),
      S('compare', 'amber', 'Then came phones that became cultural icons. The Nokia 3210 helped popularize mobile phones with younger consumers. Its internal antenna and customizable covers made it distinctive.', {
        kicker: '1999 · THE 3210',
        leftLabel: 'BEFORE · ANTENNA',
        rightLabel: '3210 · INTERNAL ANTENNA',
        caption: 'The bump disappeared.',
        left: (ctx) => {
          drawHandset(ctx, { x: W * 0.20, y: H * 0.32, w: W * 0.10, h: H * 0.42, facing: 0.12, screen: 'menu', glow: 0.4 });
          ctx.fillStyle = 'rgba(243,238,226,0.5)';
          ctx.fillRect(W * 0.242, H * 0.27, W * 0.006, H * 0.055);
        },
        right: (ctx) => drawHandset(ctx, { x: W * 0.68, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.12, screen: 'menu', glow: 0.9, antenna: false }),
      }),
      S('object', 'gold', 'The Nokia 3310, introduced in 2000, became famous for its sturdy construction, long battery life, and simple games. Snake became a familiar source of entertainment for millions of people.', {
        kicker: '2000 · THE 3310',
        caption: 'Snake.',
        draw: handset({ x: 0.42, y: 0.26, w: 0.16, h: 0.55, facing: 0.14, glow: 0.95, antenna: false }),
        transition: T('rack'),
      }),
      S('type', 'amber', 'These phones didn\'t need enormous screens or thousands of applications to be useful. They needed to do a few important things exceptionally well. Make calls. Send messages. Last through the day. Survive everyday use.', {
        kicker: 'THE BRIEF',
        lines: [
          { text: 'Calls.', size: 46, at: 0.04, colour: 'rgba(243,238,226,0.80)', gap: 0.075 },
          { text: 'Messages.', size: 46, at: 0.11, colour: 'rgba(243,238,226,0.72)', gap: 0.075 },
          { text: 'A week on a charge.', size: 46, at: 0.18, colour: 'rgba(243,238,226,0.64)', gap: 0.075 },
          { text: 'Survive the floor.', size: 46, at: 0.25, colour: 'rgba(243,238,226,0.56)' },
        ],
        top: 0.38,
      }),
      S('map', 'amber', 'And Nokia delivered. Its products spread across countries and income groups, helping make mobile communication part of everyday life. The company\'s influence extended beyond hardware. Its brand became a symbol of reliability.', {
        kicker: 'RELIABILITY, EXPORTED',
        caption: 'Every market at once.',
        land: 'rgba(150,110,50,0.55)',
        landEdge: 'rgba(226,185,79,0.42)',
        arcs: [
          { from: 'helsinki', to: 'london', t: 0.38, colour: 'rgba(226,185,79,0.46)', width: 1.3, head: false },
          { from: 'helsinki', to: 'lagos', t: 0.46, colour: 'rgba(226,185,79,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'mumbai', t: 0.54, colour: 'rgba(226,185,79,0.42)', width: 1.3, head: false },
          { from: 'helsinki', to: 'beijing', t: 0.62, colour: 'rgba(226,185,79,0.40)', width: 1.2, head: false },
          { from: 'helsinki', to: 'saopaulo', t: 0.70, colour: 'rgba(226,185,79,0.36)', width: 1.2, head: false },
        ],
      }),
      S('chart', 'amber', 'For many customers, buying a Nokia phone wasn\'t a difficult decision. It was the obvious choice.', {
        kicker: 'ALL PHONES SOLD · GARTNER · PERCENT',
        caption: 'The obvious choice.',
        bars: [
          { label: '1998', value: 22.9 },
          { label: '2000', value: 30.6 },
          { label: '2003', value: 34.8 },
          { label: '2006', value: 34.8 },
          { label: '2007', value: 37.8, hot: true },
        ],
        lit: 0.9,
      }),
      S('type', 'amber', 'But Nokia\'s growing dominance created a new danger. The company had become exceptionally good at building the phones people wanted. The question was whether it could recognize the moment when people began wanting something entirely different.', {
        kicker: 'THE DANGER',
        lines: [
          { text: 'It got very good', size: 46, at: 0.05, colour: 'rgba(243,238,226,0.66)', gap: 0.115 },
          { text: 'at the old question.', size: 46, at: 0.16, colour: 'rgba(243,238,226,0.66)', gap: 0.18 },
          { text: 'The new one arrived', size: 50, at: 0.30, gap: 0.11 },
          { text: 'in January 2007.', size: 50, at: 0.41, colour: '#E2B94F' },
        ],
        top: 0.34,
        transition: T('fade', { dip: 'paper' }),
      }),
    ],
  },
  {
    n: 5,
    name: 'THE PEAK OF THE EMPIRE',
    world: 'gold',
    shots: [
      S('type', 'gold', 'By the early 2000s, Nokia had become the undisputed leader of the mobile phone industry. Its products reached customers across continents, and its business benefited from the rapid expansion of mobile networks.', {
        kicker: 'ACT IV · 2000 — 2007',
        lines: [
          { text: 'The undisputed', size: 54, at: 0.06, gap: 0.12 },
          { text: 'leader.', size: 96, at: 0.18, colour: '#E2B94F' },
        ],
        top: 0.40,
        transition: T('wipe', { direction: 'left' }),
      }),
      S('chart', 'gold', 'In 2000, the company introduced the Nokia 3310, a phone that would become one of the most recognizable mobile devices in history.', {
        kicker: 'UNITS SOLD, MILLIONS',
        caption: 'One model, one hundred and twenty-six million.',
        bars: [
          { label: '3210', value: 160 },
          { label: '3310', value: 126, hot: true },
          { label: '1100', value: 250 },
          { label: 'iPhone', value: 220 },
        ],
        lit: 0.5,
        scaleMax: 270,
      }),
      S('bands', 'gold', 'Other models followed, including camera phones, multimedia devices, and increasingly sophisticated smartphones.', {
        kicker: '2002 — 2007',
        bands: [
          { label: '7650', sub: '2002 · CAMERA', colour: 'rgba(196,105,46,0.46)' },
          { label: 'N-Gage', sub: '2003 · GAMES', colour: 'rgba(150,190,170,0.40)' },
          { label: 'N95', sub: '2007 · EVERYTHING', colour: 'rgba(226,185,79,0.55)' },
          { label: 'Eseries', sub: '2006 · BUSINESS', colour: 'rgba(160,170,190,0.42)' },
        ],
        caption: 'The range kept widening.',
      }),
      S('type', 'gold', 'Nokia wasn\'t simply selling basic communication tools anymore. It was exploring how mobile devices could support photography, music, internet access, and productivity.', {
        lines: [
          { text: 'Photography.', size: 40, at: 0.04, colour: 'rgba(243,238,226,0.78)', gap: 0.085 },
          { text: 'Music.', size: 40, at: 0.12, colour: 'rgba(243,238,226,0.70)', gap: 0.085 },
          { text: 'The internet.', size: 40, at: 0.20, colour: 'rgba(243,238,226,0.62)', gap: 0.085 },
          { text: 'Work.', size: 40, at: 0.28, colour: 'rgba(243,238,226,0.54)' },
        ],
        top: 0.38,
      }),
      S('map', 'gold', 'The company possessed enormous manufacturing capabilities and deep relationships with telecommunications operators. Its global distribution network helped it reach markets that many competitors struggled to serve.', {
        kicker: 'GLOBAL MANUFACTURING AND DISTRIBUTION',
        caption: 'A supply chain, not a product line.',
        arcs: [
          { from: 'helsinki', to: 'newyork', t: 0.36, colour: 'rgba(226,185,79,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'mumbai', t: 0.44, colour: 'rgba(226,185,79,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'shanghai', t: 0.52, colour: 'rgba(226,185,79,0.42)', width: 1.3, head: false },
          { from: 'helsinki', to: 'cairo', t: 0.60, colour: 'rgba(226,185,79,0.40)', width: 1.2, head: false },
          { from: 'helsinki', to: 'sydney', t: 0.68, colour: 'rgba(226,185,79,0.36)', width: 1.2, head: false },
          { from: 'helsinki', to: 'saopaulo', t: 0.76, colour: 'rgba(226,185,79,0.34)', width: 1.2, head: false },
        ],
      }),
      S('chart', 'gold', 'At the same time, its scale gave it significant advantages in manufacturing, purchasing components, and launching new products.', {
        kicker: 'NET SALES, BILLIONS OF EUROS',
        caption: 'Four times the size in ten years.',
        bars: [
          { label: '1998', value: 13 },
          { label: '2000', value: 30 },
          { label: '2003', value: 29 },
          { label: '2005', value: 34 },
          { label: '2007', value: 51, hot: true },
        ],
        lit: 0.9,
      }),
      S('chart', 'gold', 'By 2007, Nokia held roughly 40 percent of the global mobile phone market, depending on the market definition and measurement used.', {
        kicker: 'ALL PHONES SOLD · GARTNER · 2007',
        caption: 'Nearly forty percent.',
        bars: [
          { label: 'Nokia', value: 37.8, hot: true },
          { label: 'Samsung', value: 13.4 },
          { label: 'Motorola', value: 14.3 },
          { label: 'Sony Ericsson', value: 8.8 },
          { label: 'LG', value: 6.8 },
        ],
        lit: 0.0,
      }),
      S('bands', 'gold', 'Its influence was extraordinary. For years, Nokia had helped define what a mobile phone should be. Its engineers understood antennas, batteries, radio technology, physical controls, and manufacturing on a massive scale.', {
        kicker: 'WHAT THE ENGINEERS KNEW',
        bands: [
          { label: 'Antennas', sub: 'RADIO', colour: 'rgba(226,185,79,0.50)' },
          { label: 'Batteries', sub: 'POWER', colour: 'rgba(196,105,46,0.44)' },
          { label: 'Keypads', sub: 'TOUCH', colour: 'rgba(160,170,190,0.40)' },
          { label: 'Tooling', sub: 'SCALE', colour: 'rgba(150,190,170,0.38)' },
        ],
        caption: 'Ten thousand engineers, one craft.',
      }),
      S('type', 'gold', 'Its products were trusted by consumers. Its business was global. Its future appeared secure.', {
        lines: [
          { text: 'Trusted.', size: 44, at: 0.05, colour: 'rgba(243,238,226,0.70)', gap: 0.10 },
          { text: 'Global.', size: 44, at: 0.14, colour: 'rgba(243,238,226,0.62)', gap: 0.14 },
          { text: 'Secure.', size: 92, at: 0.28, colour: '#E2B94F' },
        ],
        top: 0.38,
      }),
      S('type', 'ash', 'But a dangerous assumption was beginning to take hold. Nokia had become so successful at winning the existing mobile phone market that it risked underestimating how radically that market could change.', {
        kicker: 'THE ASSUMPTION',
        lines: [
          { text: 'That tomorrow', size: 48, at: 0.05, colour: 'rgba(233,231,226,0.66)', gap: 0.115 },
          { text: 'would look like today.', size: 48, at: 0.16, colour: 'rgba(233,231,226,0.66)' },
        ],
        top: 0.42,
        transition: T('fade', { dip: 'paper' }),
      }),
      S('type', 'graphite', 'And in January 2007, the industry received a warning that would soon become impossible to ignore.', {
        kicker: 'ACT V · 2007',
        lines: [{ text: 'January 2007.', size: 84, at: 0.10 }],
        top: 0.46,
        transition: T('iris'),
      }),
    ],
  },
  {
    n: 6,
    name: 'THE MOMENT EVERYTHING CHANGED',
    world: 'graphite',
    shots: [
      S('type', 'graphite', 'On January 9, 2007, Steve Jobs walked onto a stage in San Francisco and introduced the original iPhone.', {
        kicker: '9 JANUARY 2007 · SAN FRANCISCO',
        lines: [
          { text: 'A stage,', size: 50, at: 0.05, colour: 'rgba(237,234,226,0.62)', gap: 0.115 },
          { text: 'a screen,', size: 50, at: 0.16, colour: 'rgba(237,234,226,0.62)', gap: 0.115 },
          { text: 'a phone built around touch.', size: 58, at: 0.28 },
        ],
        top: 0.38,
      }),
      S('type', 'graphite', 'It was not the first smartphone. Nokia had already produced advanced mobile devices, including smartphones with internet connectivity and software applications.', {
        // Do not portray a generic candy-bar handset as the clamshell Communicator.
        kicker: '1996 · THE COMMUNICATOR',
        lines: [
          { text: 'Nokia had made', size: 52, at: 0.06, gap: 0.12 },
          { text: 'smartphones before.', size: 62, at: 0.18, colour: 'rgba(237,234,226,0.72)' },
        ],
        top: 0.40,
      }),
      S('compare', 'graphite', 'But the iPhone presented a different vision of what a phone could become. Instead of relying primarily on physical buttons, it placed a large touchscreen at the center of the experience.', {
        kicker: 'TWO VISIONS',
        leftLabel: 'KEYS FIRST',
        rightLabel: 'SCREEN FIRST',
        caption: 'The interface moved to the glass.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.20, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.14, screen: 'menu', glow: 0.5 }),
        right: (ctx, { glow }) => drawSmartphone(ctx, { x: W * 0.65, y: H * 0.26, w: W * 0.11, h: H * 0.50, glow }),
      }),
      S('object', 'graphite', 'It made browsing the internet feel more natural. It introduced a new way to interact with software. And it suggested that a phone could become a flexible computing platform rather than simply a communication device with additional features.', {
        kicker: 'A COMPUTER THAT FITS A HAND',
        caption: 'Software, in the palm.',
        draw: (ctx, { p, glow }) => {
          contact(ctx, W * 0.5, H * 0.855, W * 0.13, H * 0.02, 0.5);
          drawSmartphone(ctx, { x: W * 0.425, y: H * 0.20, w: W * 0.15, h: H * 0.63, glow });
        },
      }),
      S('type', 'graphite', 'The significance of the iPhone went far beyond its appearance. Apple was changing the relationship between hardware and software. The user experience became central to the product.', {
        kicker: 'THE REAL CHANGE',
        lines: [
          { text: 'The software', size: 52, at: 0.06, colour: 'rgba(237,234,226,0.66)', gap: 0.12 },
          { text: 'became the product.', size: 62, at: 0.18 },
        ],
        top: 0.40,
      }),
      S('chart', 'graphite', 'Applications, internet services, and the interface worked together to create an experience that felt different from traditional mobile phones.', {
        kicker: 'APPLICATIONS BY 2011, THOUSANDS',
        caption: 'Half a million, four years later.',
        bars: [
          { label: 'App Store', value: 500, hot: true },
          { label: 'Android', value: 300 },
          { label: 'Ovi', value: 50 },
        ],
        lit: 0.0,
      }),
      S('bands', 'graphite', 'Nokia had talented engineers and sophisticated devices of its own. But much of its business was built around a different model. It offered many products, multiple interfaces, and a range of software platforms.', {
        kicker: 'MANY PHONES, MANY SYSTEMS',
        bands: [
          { label: 'Series 40', sub: 'FEATURE PHONES', colour: 'rgba(160,170,190,0.34)' },
          { label: 'S60', sub: 'SMARTPHONES', colour: 'rgba(190,180,120,0.34)' },
          { label: 'S80 / S90', sub: 'COMMUNICATOR', colour: 'rgba(150,150,160,0.30)' },
          { label: 'Maemo', sub: 'TABLET', colour: 'rgba(120,160,210,0.30)' },
        ],
        caption: 'Four platforms, one company.',
      }),
      S('type', 'cold', 'That approach had helped it serve customers with different needs. However, it also made it harder to create one consistent, rapidly evolving software experience across its entire portfolio.', {
        kicker: 'PLATFORM FRAGMENTATION',
        lines: [
          { text: 'Many devices.', size: 50, at: 0.07, gap: 0.13 },
          { text: 'Many software paths.', size: 60, at: 0.19 },
        ],
        top: 0.42,
      }),
      S('type', 'graphite', 'The iPhone didn\'t destroy Nokia overnight. But it changed the direction of competition. The question was no longer simply who could build the best mobile phone. It was who could build the best mobile computing platform.', {
        kicker: 'THE NEW QUESTION',
        lines: [
          { text: 'Not who builds', size: 46, at: 0.05, colour: 'rgba(237,234,226,0.60)', gap: 0.11 },
          { text: 'the best phone.', size: 46, at: 0.16, colour: 'rgba(237,234,226,0.60)', gap: 0.17 },
          { text: 'Who builds the platform.', size: 56, at: 0.30 },
        ],
        top: 0.36,
      }),
      S('type', 'steel', 'And another competitor was already preparing to take advantage of that change.', {
        kicker: 'ACT VI · 2007',
        lines: [{ text: 'Then a second one arrived.', size: 56, at: 0.10 }],
        top: 0.46,
        transition: T('push', { direction: 'left' }),
      }),
    ],
  },

  {
    n: 7,
    name: 'THE ENEMY NOKIA UNDERESTIMATED',
    world: 'steel',
    shots: [
      S('type', 'steel', 'While Apple was redefining the premium smartphone experience, Google was helping create another major force in the industry. Google acquired Android in 2005. In 2007, it announced the Android platform alongside other members of the Open Handset Alliance.', {
        kicker: '2005 — 2007 · ANDROID',
        lines: [
          { text: 'A new platform:', size: 46, at: 0.05, colour: 'rgba(232,237,242,0.62)', gap: 0.11 },
          { text: 'Android.', size: 88, at: 0.16 },
        ],
        top: 0.42,
      }),
      S('type', 'steel', 'The first commercially available Android phone arrived in 2008.', {
        // The first G1 had a slide-out keyboard, not the generic glass slab.
        kicker: '2008 · THE FIRST ANDROID PHONE',
        lines: [
          { text: 'Android', size: 72, at: 0.06, gap: 0.13 },
          { text: 'reaches a phone.', size: 58, at: 0.18, colour: 'rgba(232,237,242,0.72)' },
        ],
        top: 0.40,
      }),
      S('bands', 'steel', 'Android offered a different path from Apple\'s tightly controlled ecosystem. It could be adopted by multiple manufacturers, allowing companies to build smartphones using a common software foundation.', {
        kicker: 'ONE SYSTEM, MANY MAKERS',
        bands: [
          { label: 'Samsung', sub: 'ANDROID', colour: 'rgba(120,160,210,0.42)' },
          { label: 'HTC', sub: 'ANDROID', colour: 'rgba(150,180,220,0.40)' },
          { label: 'LG', sub: 'ANDROID', colour: 'rgba(160,170,190,0.38)' },
          { label: 'Motorola', sub: 'ANDROID', colour: 'rgba(190,180,120,0.38)' },
        ],
        caption: 'A common foundation.',
      }),
      S('bands', 'steel', 'That distinction would become enormously important. Samsung, HTC, and other manufacturers could compete across different price ranges while using Android as their operating system.', {
        kicker: 'THE PRICE LADDER',
        bands: [
          { label: 'Flagship', sub: '600 EUROS', colour: 'rgba(226,185,79,0.44)' },
          { label: 'Mid-range', sub: '300 EUROS', colour: 'rgba(150,180,220,0.36)' },
          { label: 'Entry', sub: '80 EUROS', colour: 'rgba(160,170,190,0.30)' },
        ],
        caption: 'Every shelf, every customer.',
      }),
      S('chart', 'steel', 'As more devices entered the market, more customers gained access to modern smartphone features. Developers could create applications for a growing audience. Consumers gained more choices. And the platform became increasingly attractive as its ecosystem expanded.', {
        kicker: 'ANDROID SMARTPHONE SALES · GARTNER · PERCENT',
        caption: 'Four percent to seventy-eight.',
        bars: [
          { label: '2009', value: 3.9 },
          { label: '2010', value: 22.7 },
          { label: '2011', value: 46 }, // rounded: 219m of 472m
          { label: '2012', value: 66.4 },
          { label: '2013', value: 78.4, hot: true },
        ],
        lit: 0.9,
      }),
      S('bands', 'steel', 'Nokia faced a difficult competitive landscape. Apple controlled the iPhone experience. Android was building a broad network of manufacturers and developers. Both platforms were benefiting from a shift toward software, services, and applications.', {
        kicker: 'THREE PLATFORMS · 2011',
        bands: [
          { label: 'iOS', sub: 'APPLE · CLOSED', colour: 'rgba(200,205,215,0.40)' },
          { label: 'Android', sub: 'GOOGLE · OPEN', colour: 'rgba(150,190,170,0.40)' },
          { label: 'Symbian', sub: 'NOKIA · LEGACY', colour: 'rgba(190,180,120,0.32)' },
        ],
        caption: 'Two of them were growing.',
      }),
      S('type', 'steel', 'Nokia, meanwhile, was still managing a complex collection of devices and software systems.', {
        lines: [
          { text: 'One company,', size: 46, at: 0.06, colour: 'rgba(232,237,242,0.62)', gap: 0.12 },
          { text: 'many systems.', size: 62, at: 0.18 },
        ],
        top: 0.40,
      }),
      S('chart', 'steel', 'The company had the resources to compete. It had an established smartphone business, a globally recognized brand, and years of engineering experience.', {
        // Nokia's consolidated R&D expenses; 2007 is the restated figure
        // shown alongside 2008 in Nokia's 2008 annual report.
        kicker: 'NOKIA GROUP R&D · BILLIONS OF EUROS',
        caption: 'It was not a company without resources.',
        bars: [
          { label: '2007', value: 5.636 },
          { label: '2008', value: 5.968, hot: true },
          { label: '2009', value: 5.909 },
          { label: '2010', value: 5.863, hot: false },
        ],
        lit: 0.9,
        scaleMax: 6.5,
      }),
      S('type', 'steel', 'But those advantages could not automatically guarantee success in a market where the rules were changing. The battle was moving away from the phone alone. It was becoming a battle over operating systems, developer support, and the everyday experience of using a device.', {
        kicker: 'THE BATTLE',
        lines: [
          { text: 'The contest moved', size: 44, at: 0.05, colour: 'rgba(232,237,242,0.60)', gap: 0.11 },
          { text: 'off the phone.', size: 44, at: 0.16, colour: 'rgba(232,237,242,0.60)' },
        ],
        top: 0.42,
      }),
      S('type', 'cold', 'And Nokia\'s position was about to become even more difficult.', {
        kicker: 'ACT VII · 2010',
        lines: [{ text: 'It got harder.', size: 64, at: 0.10 }],
        top: 0.46,
        transition: T('push', { direction: 'left' }),
      }),
    ],
  },
  {
    n: 8,
    name: 'THE SOFTWARE PROBLEM',
    world: 'cold',
    shots: [
      S('type', 'cold', 'One of Nokia\'s biggest challenges was not a lack of hardware expertise. It was software.', {
        kicker: 'THE PROBLEM',
        lines: [
          { text: 'Not the hardware.', size: 48, at: 0.06, colour: 'rgba(233,237,242,0.62)', gap: 0.13 },
          { text: 'The software.', size: 88, at: 0.20 },
        ],
        top: 0.40,
      }),
      S('chart', 'cold', 'For years, Nokia had relied heavily on Symbian, an operating system used in many of its smartphones. Symbian had helped the company deliver advanced mobile capabilities long before the iPhone arrived. It was not an insignificant achievement.', {
        kicker: 'SMARTPHONE OS · GARTNER · 2007',
        caption: 'Almost two thirds.',
        bars: [
          { label: 'Symbian', value: 63.5, hot: true },
          { label: 'RIM', value: 9.6 },
          { label: 'Windows', value: 12.0 },
          { label: 'iPhone', value: 2.7 },
          { label: 'Other', value: 12.1 },
        ],
        lit: 0.0,
      }),
      S('bands', 'cold', 'But the demands of the smartphone market were changing rapidly. Modern smartphones needed intuitive interfaces, smooth touch interactions, frequent software improvements, and strong application ecosystems.', {
        kicker: 'WHAT A NEW PHONE NEEDED',
        bands: [
          { label: 'Touch', sub: 'INTERFACE', colour: 'rgba(150,190,210,0.40)' },
          { label: 'Updates', sub: 'CADENCE', colour: 'rgba(160,170,190,0.36)' },
          { label: 'Apps', sub: 'ECOSYSTEM', colour: 'rgba(190,180,120,0.36)' },
          { label: 'Services', sub: 'ACCOUNTS', colour: 'rgba(150,190,170,0.32)' },
        ],
        caption: 'None of it was in the box.',
      }),
      S('type', 'cold', 'Nokia\'s software environment became increasingly difficult to manage. Different devices and versions of its operating systems created complexity.', {
        kicker: 'SOFTWARE COMPLEXITY',
        lines: [
          { text: 'Different devices.', size: 50, at: 0.07, gap: 0.13 },
          { text: 'Different versions.', size: 60, at: 0.19 },
        ],
        top: 0.42,
      }),
      S('bands', 'cold', 'The company also struggled to move quickly enough as consumer expectations evolved. Developers were increasingly drawn to platforms where they could reach large audiences and build applications using consistent tools.', {
        kicker: 'WHERE THE DEVELOPERS WENT',
        bands: [
          { label: 'iOS', sub: 'ONE STORE, ONE TOOLCHAIN', colour: 'rgba(200,205,215,0.40)' },
          { label: 'Android', sub: 'ONE SDK, MANY MAKERS', colour: 'rgba(150,190,170,0.40)' },
          { label: 'Symbian', sub: 'MANY SIGNINGS', colour: 'rgba(190,180,120,0.30)' },
        ],
        caption: 'The developers left first.',
      }),
      S('type', 'cold', 'Apple and Android were gaining momentum. Nokia needed to respond with a competitive, unified software strategy. Instead, the company spent years navigating difficult platform decisions.', {
        lines: [
          { text: 'Two platforms grew.', size: 44, at: 0.05, colour: 'rgba(233,237,242,0.60)', gap: 0.11 },
          { text: 'One kept deciding.', size: 56, at: 0.16 },
        ],
        top: 0.42,
      }),
      S('type', 'ember', 'In 2010, Nokia appointed Stephen Elop as its new chief executive. The company needed a clear plan to regain momentum.', {
        kicker: '2010 · A NEW CHIEF EXECUTIVE',
        lines: [{ text: 'A new chief executive.', size: 56, at: 0.10 }],
        top: 0.46,
        transition: T('fade', { dip: 'paper' }),
      }),
      S('type', 'ember', 'In February 2011, Elop announced that Nokia would adopt Microsoft\'s Windows Phone platform as its primary smartphone strategy. The decision was intended to help Nokia differentiate itself and compete against Apple and Android. It also meant moving away from Symbian as the foundation of its future smartphone business.', {
        kicker: 'FEBRUARY 2011 · THE PLATFORM CHANGES',
        lines: [
          { text: 'Symbian out.', size: 62, at: 0.05, gap: 0.13 },
          { text: 'Windows Phone in.', size: 62, at: 0.17, colour: 'rgba(246,230,214,0.72)' },
        ],
        top: 0.42,
      }),
      S('type', 'ember', 'But the transition carried enormous risks. Nokia needed to persuade consumers to buy into a new ecosystem. It needed developers to support that ecosystem. And it needed to do both while competitors were rapidly expanding their own platforms.', {
        kicker: 'THREE THINGS AT ONCE',
        lines: [
          { text: 'Win the buyer.', size: 40, at: 0.04, colour: 'rgba(246,230,214,0.74)', gap: 0.09 },
          { text: 'Win the developer.', size: 40, at: 0.12, colour: 'rgba(246,230,214,0.68)', gap: 0.09 },
          { text: 'Do it while losing.', size: 40, at: 0.20, colour: 'rgba(246,230,214,0.62)' },
        ],
        top: 0.40,
      }),
      S('type', 'ember', 'Time was running out. The company was making a decisive move. But the question remained: would that move be enough?', {
        lines: [{ text: 'Was it enough?', size: 84, at: 0.10 }],
        top: 0.46,
        transition: T('iris'),
      }),
    ],
  },
  {
    n: 9,
    name: 'THE BURNING PLATFORM',
    world: 'ember',
    shots: [
      S('type', 'ember', 'In February 2011, Stephen Elop circulated a memo that became famous throughout the technology industry. It compared Nokia\'s situation to a person standing on a burning platform, forced to jump into cold water to escape a greater danger.', {
        kicker: 'FEBRUARY 2011 · THE MEMO',
        lines: [
          { text: 'A burning', size: 66, at: 0.06, gap: 0.13 },
          { text: 'platform.', size: 66, at: 0.18, colour: '#F0C26A' },
        ],
        top: 0.42,
      }),
      S('type', 'ember', 'The message was clear. Nokia could not continue operating as if its existing strategy would be enough. The company needed fundamental change.', {
        kicker: 'THE MESSAGE',
        lines: [
          { text: 'Change,', size: 58, at: 0.06, gap: 0.12 },
          { text: 'or fall behind.', size: 58, at: 0.18, colour: 'rgba(246,230,214,0.72)' },
        ],
        top: 0.42,
      }),
      S('chart', 'ember', 'But change comes with a cost. Nokia\'s decision to move toward Windows Phone created uncertainty around its existing products and future direction.', {
        kicker: 'ALL PHONES SOLD · GARTNER · PERCENT',
        caption: 'Nokia’s share declined.',
        bars: [
          { label: '2011', value: 23.8, hot: true },
          { label: '2012', value: 19.1 },
          { label: '2013', value: 13.9 },
        ],
        lit: 0.0,
        scaleMax: 26,
      }),
      S('bands', 'ember', 'Consumers wondered whether they should continue buying Symbian devices. Developers had to decide where to invest their time. Employees faced a major organizational transition.', {
        kicker: 'THREE GROUPS WAITED',
        bands: [
          { label: 'Consumers', sub: 'BUY NOW OR WAIT?', colour: 'rgba(246,230,214,0.30)' },
          { label: 'Developers', sub: 'WHICH PLATFORM?', colour: 'rgba(240,194,106,0.28)' },
          { label: 'Employees', sub: 'WHICH OFFICE?', colour: 'rgba(196,105,46,0.26)' },
        ],
        caption: 'Everyone paused at once.',
      }),
      S('chart', 'cold', 'Meanwhile, Apple\'s iPhone and Android devices continued attracting customers.', {
        kicker: 'SMARTPHONE OS · GARTNER · 2013',
        caption: 'The others did not pause.',
        bars: [
          { label: 'Android', value: 78.4, hot: true },
          { label: 'iOS', value: 15.6 },
          { label: 'Windows Phone', value: 3.2 },
          { label: 'Other', value: 2.8 },
        ],
        lit: 0.0,
        transition: T('fade', { dip: 'paper' }),
      }),
      S('object', 'ember', 'Nokia and Microsoft introduced the Lumia smartphone line, hoping to combine Nokia\'s hardware strengths with Microsoft\'s software platform. Some Lumia devices received praise for their design, cameras, and distinctive appearance.', {
        kicker: '2011 · LUMIA',
        caption: 'Good hardware, new system.',
        draw: (ctx, { glow }) => {
          contact(ctx, W * 0.5, H * 0.855, W * 0.13, H * 0.02, 0.5);
          drawSmartphone(ctx, { x: W * 0.425, y: H * 0.20, w: W * 0.15, h: H * 0.63, glow, bodyColour: '#123A4A', screenFrom: '#0E5C74', screenTo: '#08202B' });
        },
        transition: T('cut'),
      }),
      S('bands', 'ember', 'But the wider challenge was much larger than individual phone reviews. A smartphone platform needs more than attractive hardware. It needs applications, developer confidence, services, and a large enough user base to sustain growth.', {
        kicker: 'WHAT A PLATFORM NEEDS',
        bands: [
          { label: 'Applications', sub: 'CHOICE', colour: 'rgba(240,194,106,0.34)' },
          { label: 'Developers', sub: 'CONFIDENCE', colour: 'rgba(246,230,214,0.28)' },
          { label: 'Services', sub: 'ACCOUNTS', colour: 'rgba(150,190,170,0.26)' },
          { label: 'Users', sub: 'SCALE', colour: 'rgba(160,170,190,0.26)' },
        ],
        caption: 'Hardware was the easy part.',
      }),
      S('type', 'cold', 'Windows Phone struggled to match the scale of the iOS and Android ecosystems. That made it harder to attract users. And fewer users made it harder to attract developers. It was a difficult cycle to break.', {
        // Avoid an unsupported snapshot of app-store counts and dates.
        kicker: 'THE ECOSYSTEM CHALLENGE',
        lines: [
          { text: 'Users.', size: 56, at: 0.06, gap: 0.12 },
          { text: 'Developers.', size: 56, at: 0.18, gap: 0.12 },
          { text: 'Applications.', size: 56, at: 0.30 },
        ],
        top: 0.36,
      }),
      S('type', 'ash', 'Nokia was trying to rebuild its position while the industry was moving forward at extraordinary speed. The company had made a bold strategic decision. But it had entered a race in which its competitors had already built substantial momentum.', {
        kicker: 'THE RACE',
        lines: [
          { text: 'A bold decision,', size: 44, at: 0.05, colour: 'rgba(233,231,226,0.62)', gap: 0.11 },
          { text: 'entered late.', size: 44, at: 0.16, colour: 'rgba(233,231,226,0.62)' },
        ],
        top: 0.42,
        transition: T('fade', { dip: 'paper' }),
      }),
      S('type', 'ash', 'And Nokia\'s time as the dominant force in mobile phones was drawing to a close.', {
        lines: [{ text: 'The end of the lead.', size: 56, at: 0.10 }],
        top: 0.46,
      }),
    ],
  },
  {
    n: 10,
    name: 'THE $7.2 BILLION DECISION',
    world: 'ash',
    shots: [
      S('chart', 'ash', 'By 2013, Nokia\'s position in the smartphone market had weakened dramatically. The company remained an important mobile phone manufacturer, but it was no longer setting the direction of the industry.', {
        kicker: 'SHARE OF PHONES SOLD · 2013',
        caption: 'No longer the direction.',
        bars: [
          { label: 'Samsung', value: 25 },
          { label: 'Nokia', value: 14, hot: true },
          { label: 'Apple', value: 9 },
          { label: 'Others', value: 52 },
        ],
        lit: 0.0,
      }),
      S('type', 'ash', 'In September 2013, Microsoft announced an agreement to acquire substantially all of Nokia\'s Devices and Services business.', {
        kicker: '3 SEPTEMBER 2013',
        lines: [{ text: 'A sale is announced.', size: 54, at: 0.10 }],
        top: 0.46,
      }),
      S('type', 'ash', 'The transaction was valued at approximately 5.44 billion euros, equivalent to roughly 7.2 billion US dollars at the time.', {
        kicker: 'AGREED PRICE · BUSINESS AND PATENT LICENSE',
        lines: [
          { text: '€5.44 billion.', size: 64, at: 0.06, gap: 0.16 },
          { text: '$7.2 billion.', size: 64, at: 0.22, colour: 'rgba(233,231,226,0.62)' },
        ],
        top: 0.38,
      }),
      S('bands', 'ash', 'It included Nokia\'s mobile phone business and related assets, alongside licensing arrangements. The deal was completed in April 2014.', {
        kicker: 'WHAT MOVED',
        bands: [
          { label: 'Devices', sub: 'SOLD', colour: 'rgba(200,205,210,0.26)' },
          { label: 'Services', sub: 'SOLD', colour: 'rgba(200,205,210,0.22)' },
          { label: 'Patents', sub: 'LICENSED, KEPT', colour: 'rgba(226,185,79,0.34)' },
        ],
        caption: 'Completed April 2014.',
      }),
      S('object', 'ash', 'For Nokia, this was a defining moment. A company that had once dominated mobile phones was transferring the core of its device business to another technology giant.', {
        kicker: '2014',
        caption: 'A phone, in a box.',
        draw: (ctx, { p }) => {
          const k = clamp(p * 2.4);
          ctx.save();
          ctx.globalAlpha *= k;
          ctx.fillStyle = 'rgba(0,0,0,0.45)';
          ctx.beginPath();
          ctx.ellipse(W * 0.5, H * 0.83, W * 0.22, H * 0.03, 0, 0, Math.PI * 2);
          ctx.fill();
          const w = W * 0.30;
          const h = H * 0.20;
          const x = W * 0.5 - w / 2;
          const y = H * 0.62;
          ctx.fillStyle = '#2A2C30';
          ctx.fillRect(x, y, w, h);
          ctx.fillStyle = 'rgba(255,255,255,0.06)';
          ctx.fillRect(x, y, w, h * 0.22);
          ctx.strokeStyle = 'rgba(233,231,226,0.18)';
          ctx.lineWidth = 1;
          ctx.strokeRect(x, y, w, h);
          ctx.restore();
        },
      }),
      S('bands', 'ash', 'Microsoft hoped the acquisition would strengthen its position in smartphones. Nokia, meanwhile, would concentrate on other businesses, including telecommunications network equipment, mapping and location services, and technology licensing.', {
        kicker: 'WHAT NOKIA KEPT IN 2014',
        bands: [
          { label: 'Networks', sub: 'EQUIPMENT', colour: 'rgba(80,190,175,0.38)' },
          { label: 'Here', sub: 'MAPPING', colour: 'rgba(120,160,210,0.34)' },
          { label: 'Licensing', sub: 'PATENTS', colour: 'rgba(226,185,79,0.36)' },
        ],
        caption: 'Three businesses left.',
      }),
      S('type', 'ash', 'The company had not disappeared. Its name still carried enormous recognition. Its engineering capabilities and intellectual property remained valuable.', {
        lines: [
          { text: 'Not gone.', size: 68, at: 0.08, gap: 0.14 },
          { text: 'Different.', size: 68, at: 0.20, colour: 'rgba(233,231,226,0.66)' },
        ],
        top: 0.40,
      }),
      S('compare', 'ash', 'But the Nokia that millions of people remembered as the king of mobile phones was no longer operating that business in the same way.', {
        kicker: 'THE SAME NAME',
        leftLabel: '2007',
        rightLabel: '2014',
        caption: 'One of these is still a phone company.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.22, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.12, screen: 'menu', glow: 0.5 }),
        right: (ctx) => {
          ctx.save();
          ctx.globalAlpha *= 0.6;
          ctx.strokeStyle = 'rgba(233,231,226,0.28)';
          ctx.setLineDash([6, 8]);
          ctx.strokeRect(W * 0.66, H * 0.36, W * 0.10, H * 0.38);
          ctx.restore();
        },
      }),
      S('chart', 'ash', 'The fall was remarkable. Within a relatively short period, the company had moved from industry leadership to a position where its phone business was being sold.', {
        kicker: 'SHARE PRICE, INDEXED TO THE PEAK',
        caption: 'Ninety percent, gone.',
        bars: [
          { label: '2000', value: 100, hot: true },
          { label: '2007', value: 46 },
          { label: '2011', value: 12 },
          { label: '2013', value: 8 },
        ],
        lit: 0.0,
        scaleMax: 110,
      }),
      S('type', 'ash', 'For consumers, it marked the end of an era. For businesses around the world, it became a powerful lesson about technological disruption. Success in one generation of technology does not guarantee success in the next. And the reasons behind Nokia\'s decline were more complicated than a single bad product or one executive\'s decision.', {
        kicker: 'THE LESSON',
        lines: [
          { text: 'Not one product.', size: 40, at: 0.04, colour: 'rgba(233,231,226,0.62)', gap: 0.09 },
          { text: 'Not one decision.', size: 40, at: 0.12, colour: 'rgba(233,231,226,0.62)' },
        ],
        top: 0.42,
        transition: T('fade', { dip: 'paper' }),
      }),
    ],
  },

  {
    n: 11,
    name: "WHAT REALLY DESTROYED NOKIA'S DOMINANCE?",
    world: 'steel',
    shots: [
      S('type', 'steel', 'So what really caused Nokia\'s decline? The answer is not as simple as saying the company failed to make a touchscreen phone.', {
        kicker: 'ACT VIII · THE QUESTION',
        lines: [
          { text: 'So what', size: 52, at: 0.06, colour: 'rgba(232,237,242,0.62)', gap: 0.12 },
          { text: 'happened?', size: 92, at: 0.18 },
        ],
        top: 0.40,
        transition: T('wipe', { direction: 'left' }),
      }),
      S('compare', 'steel', 'Nokia produced touchscreen devices. It had smartphone technology. It employed talented engineers. And it possessed a globally recognized brand.', {
        kicker: '2008 · THE 5800',
        leftLabel: '2007 · KEYPAD',
        rightLabel: '2008 · TOUCH',
        caption: 'It made touchscreens too.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.22, y: H * 0.30, w: W * 0.11, h: H * 0.44, facing: 0.12, screen: 'menu', glow: 0.5 }),
        right: (ctx, { glow }) => drawSmartphone(ctx, { x: W * 0.66, y: H * 0.26, w: W * 0.11, h: H * 0.50, glow, bodyColour: '#24262B', screenFrom: '#2A4A5E', screenTo: '#101B24' }),
      }),
      S('type', 'steel', 'Its deeper problem was that the center of competition had shifted. First, software became more important. The smartphone experience increasingly depended on how naturally hardware, operating systems, applications, and online services worked together.', {
        kicker: 'REASON ONE',
        lines: [
          { text: '01', size: 44, at: 0.04, colour: 'rgba(226,185,79,0.75)', gap: 0.09 },
          { text: 'Software', size: 88, at: 0.13, gap: 0.15 },
          { text: 'became the product.', size: 34, at: 0.24, colour: 'rgba(232,237,242,0.62)' },
        ],
        top: 0.36,
      }),
      S('type', 'steel', 'Second, ecosystems became powerful competitive advantages. Apple and Android benefited from expanding communities of developers, application creators, manufacturers, and users.', {
        kicker: 'REASON TWO',
        lines: [
          { text: '02', size: 44, at: 0.04, colour: 'rgba(226,185,79,0.75)', gap: 0.09 },
          { text: 'Ecosystems', size: 84, at: 0.13, gap: 0.15 },
          { text: 'became the moat.', size: 34, at: 0.24, colour: 'rgba(232,237,242,0.62)' },
        ],
        top: 0.36,
      }),
      S('type', 'steel', 'Third, Nokia struggled to transform its software strategy quickly enough. Its legacy platforms and organizational complexity made it difficult to respond at the pace the new market demanded.', {
        kicker: 'REASON THREE',
        lines: [
          { text: '03', size: 44, at: 0.04, colour: 'rgba(226,185,79,0.75)', gap: 0.09 },
          { text: 'Slow', size: 92, at: 0.13, gap: 0.10 },
          { text: 'transformation.', size: 62, at: 0.20, gap: 0.15 },
          { text: 'The market moved faster.', size: 30, at: 0.29, colour: 'rgba(232,237,242,0.60)' },
        ],
        top: 0.34,
      }),
      S('type', 'steel', 'Fourth, the Windows Phone strategy introduced a major transition risk. It offered Nokia a fresh direction, but the platform never achieved the market scale needed to challenge its leading competitors.', {
        kicker: 'REASON FOUR',
        lines: [
          { text: '04', size: 44, at: 0.04, colour: 'rgba(226,185,79,0.75)', gap: 0.09 },
          { text: 'Strategic', size: 66, at: 0.12, gap: 0.11 },
          { text: 'risk.', size: 66, at: 0.22, gap: 0.15 },
          { text: 'A new platform, a smaller base.', size: 30, at: 0.31, colour: 'rgba(232,237,242,0.60)' },
        ],
        top: 0.34,
      }),
      S('type', 'steel', 'Finally, consumer expectations changed. People increasingly wanted their phones to function as cameras, entertainment centers, navigation tools, internet browsers, and personal computers.', {
        kicker: 'REASON FIVE',
        lines: [
          { text: '05', size: 44, at: 0.04, colour: 'rgba(226,185,79,0.75)', gap: 0.09 },
          { text: 'Expectations', size: 78, at: 0.12, gap: 0.10 },
          { text: 'changed.', size: 78, at: 0.22, gap: 0.15 },
          { text: 'A phone became a computer.', size: 30, at: 0.31, colour: 'rgba(232,237,242,0.60)' },
        ],
        top: 0.34,
      }),
      S('type', 'steel', 'A phone could no longer compete on durability and battery life alone. It needed to deliver an entire digital experience.', {
        lines: [
          { text: 'Durability was', size: 46, at: 0.05, colour: 'rgba(232,237,242,0.62)', gap: 0.11 },
          { text: 'no longer enough.', size: 46, at: 0.16, colour: 'rgba(232,237,242,0.62)' },
        ],
        top: 0.42,
      }),
      S('bands', 'steel', 'Nokia\'s traditional strengths had not suddenly become worthless. Manufacturing quality, engineering, distribution, and brand recognition still mattered. But those strengths were no longer sufficient to guarantee leadership.', {
        kicker: 'WHAT IT STILL HAD',
        bands: [
          { label: 'Manufacturing', sub: 'STILL BEST IN CLASS', colour: 'rgba(160,170,190,0.30)' },
          { label: 'Engineering', sub: 'STILL DEEP', colour: 'rgba(150,180,220,0.28)' },
          { label: 'Distribution', sub: 'STILL GLOBAL', colour: 'rgba(150,190,170,0.26)' },
          { label: 'Brand', sub: 'STILL KNOWN', colour: 'rgba(226,185,79,0.28)' },
        ],
        caption: 'None of it was the question.',
      }),
      S('type', 'steel', 'The company was competing in a different game. And while Nokia was trying to adapt, its competitors were defining the rules.', {
        lines: [
          { text: 'A different game,', size: 44, at: 0.05, colour: 'rgba(232,237,242,0.60)', gap: 0.11 },
          { text: 'with new rules.', size: 44, at: 0.16, colour: 'rgba(232,237,242,0.60)' },
        ],
        top: 0.42,
      }),
      S('type', 'gold', 'The lesson is uncomfortable but important. Sometimes, a company doesn\'t fall because it stops being good at what it does. It falls because what it does well is no longer enough.', {
        kicker: 'THE LESSON',
        lines: [
          { text: 'It did not stop', size: 46, at: 0.05, colour: 'rgba(243,238,226,0.64)', gap: 0.115 },
          { text: 'being good.', size: 46, at: 0.16, colour: 'rgba(243,238,226,0.64)', gap: 0.18 },
          { text: 'Good stopped being enough.', size: 54, at: 0.30, colour: '#E2B94F' },
        ],
        top: 0.34,
        transition: T('fade', { dip: 'paper' }),
      }),
    ],
  },
  {
    n: 12,
    name: 'THE COMEBACK NOBODY EXPECTED',
    world: 'teal',
    shots: [
      S('type', 'teal', 'But the story of Nokia did not end with the sale of its phone business. The company continued operating, transforming itself into a business focused heavily on telecommunications network equipment and related technology.', {
        kicker: 'ACT IX · BEYOND THE PHONE',
        lines: [
          { text: 'The story did not end', size: 40, at: 0.05, colour: 'rgba(233,240,230,0.64)', gap: 0.10 },
          { text: 'with the phone.', size: 40, at: 0.15, colour: 'rgba(233,240,230,0.64)', gap: 0.16 },
          { text: 'It changed jobs.', size: 62, at: 0.28 },
        ],
        top: 0.36,
        transition: T('wipe', { direction: 'left' }),
      }),
      S('type', 'teal', 'In 2016, Nokia completed its acquisition of Alcatel-Lucent, expanding its capabilities in networking and communications infrastructure.', {
        // An undated market-share snapshot did not support the acquisition.
        kicker: '2016 · NETWORKING',
        lines: [
          { text: 'Nokia', size: 62, at: 0.06, gap: 0.12 },
          { text: '+ Alcatel-Lucent', size: 62, at: 0.18, colour: 'rgba(233,240,230,0.72)' },
        ],
        top: 0.40,
      }),
      S('map', 'teal', 'The company became increasingly focused on the technology that allows mobile networks and digital communications to function.', {
        kicker: 'THE NETWORKS',
        caption: 'The radio, not the handset.',
        land: 'rgba(28,96,92,0.85)',
        landEdge: 'rgba(150,224,208,0.50)',
        arcs: [
          { from: 'helsinki', to: 'london', t: 0.40, colour: 'rgba(216,178,74,0.48)', width: 1.4, head: false },
          { from: 'helsinki', to: 'newyork', t: 0.48, colour: 'rgba(216,178,74,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'delhi', t: 0.56, colour: 'rgba(216,178,74,0.42)', width: 1.3, head: false },
          { from: 'helsinki', to: 'tokyo', t: 0.64, colour: 'rgba(216,178,74,0.38)', width: 1.3, head: false },
          { from: 'helsinki', to: 'saopaulo', t: 0.72, colour: 'rgba(216,178,74,0.34)', width: 1.2, head: false },
        ],
      }),
      S('type', 'teal', 'Instead of dominating the phones in people\'s hands, Nokia was concentrating on equipment and systems that help connect those phones to the wider world.', {
        lines: [
          { text: 'The road,', size: 54, at: 0.06, colour: 'rgba(233,240,230,0.70)', gap: 0.12 },
          { text: 'not the car.', size: 88, at: 0.18 },
        ],
        top: 0.40,
      }),
      S('bands', 'teal', 'Its business became less visible to ordinary consumers, but remained important to the telecommunications industry. The Nokia name survived. Its role changed. And that distinction matters.', {
        kicker: 'LESS VISIBLE, STILL THERE',
        bands: [
          { label: 'Radio', sub: 'BASE STATIONS', colour: 'rgba(80,190,175,0.34)' },
          { label: 'Optical', sub: 'FIBRE', colour: 'rgba(150,190,170,0.28)' },
          { label: 'Licensing', sub: 'PATENTS', colour: 'rgba(226,185,79,0.30)' },
        ],
        caption: 'Seventy-seven thousand people.',
      }),
      S('type', 'teal', 'The company that once defined mobile phones found a different place in the technology landscape. It did not recreate its former consumer-phone dominance. Instead, it rebuilt its identity around another part of the communications industry.', {
        kicker: 'A DIFFERENT NOKIA',
        lines: [
          { text: 'It did not', size: 44, at: 0.05, colour: 'rgba(233,240,230,0.60)', gap: 0.11 },
          { text: 'get the old job back.', size: 44, at: 0.16, colour: 'rgba(233,240,230,0.60)' },
        ],
        top: 0.42,
      }),
      S('type', 'gold', 'For Nokia, survival required accepting that its future would not necessarily look like its past.', {
        kicker: 'A DIFFERENT FUTURE',
        lines: [
          { text: 'The future', size: 48, at: 0.06, colour: 'rgba(243,238,226,0.64)', gap: 0.12 },
          { text: 'did not look', size: 48, at: 0.18, colour: 'rgba(243,238,226,0.64)', gap: 0.12 },
          { text: 'like the past.', size: 84, at: 0.32, colour: '#E2B94F' },
        ],
        top: 0.34,
        transition: T('fade', { dip: 'paper' }),
      }),
    ],
  },
  {
    n: 13,
    name: 'THE FINAL LESSON',
    world: 'gold',
    shots: [
      S('compare', 'gold', 'Nokia\'s story is more than the rise and fall of a mobile phone empire. It is a warning about the danger of becoming too comfortable with success.', {
        kicker: 'THE FINAL SCENE',
        leftLabel: '2000',
        rightLabel: '2007',
        caption: 'The same table, seven years apart.',
        left: (ctx) => drawHandset(ctx, { x: W * 0.24, y: H * 0.34, w: W * 0.09, h: H * 0.36, facing: 0.12, screen: 'menu', glow: 0.6 }),
        right: (ctx, { glow }) => drawSmartphone(ctx, { x: W * 0.66, y: H * 0.30, w: W * 0.09, h: H * 0.44, glow }),
        transition: T('wipe', { direction: 'left' }),
      }),
      S('map', 'gold', 'Nokia helped bring mobile communication to billions of people. It built products that became cultural icons.', {
        kicker: 'ONE COMPANY, FOUR BILLION PEOPLE',
        caption: 'The call, and the road.',
        land: 'rgba(120,100,52,0.55)',
        landEdge: 'rgba(226,185,79,0.40)',
        arcs: [
          { from: 'helsinki', to: 'london', t: 0.40, colour: 'rgba(226,185,79,0.46)', width: 1.4, head: false },
          { from: 'helsinki', to: 'lagos', t: 0.48, colour: 'rgba(226,185,79,0.44)', width: 1.3, head: false },
          { from: 'helsinki', to: 'mumbai', t: 0.56, colour: 'rgba(226,185,79,0.42)', width: 1.3, head: false },
          { from: 'helsinki', to: 'beijing', t: 0.64, colour: 'rgba(226,185,79,0.38)', width: 1.3, head: false },
          { from: 'helsinki', to: 'newyork', t: 0.72, colour: 'rgba(226,185,79,0.34)', width: 1.2, head: false },
        ],
      }),
      S('type', 'ash', 'But when the industry changed, its enormous strengths could not fully protect it from disruption.', {
        lines: [
          { text: 'Strength was', size: 46, at: 0.05, colour: 'rgba(233,231,226,0.62)', gap: 0.11 },
          { text: 'not protection.', size: 46, at: 0.16, colour: 'rgba(233,231,226,0.62)' },
        ],
        top: 0.42,
      }),
      S('bands', 'gold', 'The world moved from phones built around hardware to smartphones built around software, services, and ecosystems. And Nokia struggled to make that transition in time.', {
        kicker: 'THE TRANSITION',
        bands: [
          // These overlapped; none began on a single arbitrary date.
          { label: 'Hardware', sub: 'DEVICES', colour: 'rgba(160,170,190,0.34)' },
          { label: 'Software', sub: 'INTERFACES', colour: 'rgba(226,185,79,0.44)' },
          { label: 'Services', sub: 'ONLINE', colour: 'rgba(150,190,170,0.34)' },
          { label: 'Ecosystems', sub: 'DEVELOPERS', colour: 'rgba(120,160,210,0.34)' },
        ],
        caption: 'It was one transition too many.',
      }),
      S('object', 'gold', 'Today, the old Nokia phones remain symbols of a different technological era. They remind us that even the most powerful companies can lose their position when they fail to adapt.', {
        kicker: 'THE PHONE IN THE DRAWER',
        caption: 'It still turns on.',
        draw: (ctx, { glow }) => {
          contact(ctx, W * 0.5, H * 0.845, W * 0.13, H * 0.02, 0.5);
          drawHandset(ctx, { x: W * 0.435, y: H * 0.30, w: W * 0.13, h: H * 0.48, facing: 0.10, screen: 'menu', glow: 0.75 });
        },
      }),
      S('type', 'gold', 'Because in business, being the best at yesterday\'s technology does not guarantee that you will lead tomorrow.', {
        lines: [
          { text: 'Best at yesterday', size: 44, at: 0.05, colour: 'rgba(243,238,226,0.62)', gap: 0.11 },
          { text: 'is not a plan', size: 44, at: 0.16, colour: 'rgba(243,238,226,0.62)', gap: 0.11 },
          { text: 'for tomorrow.', size: 44, at: 0.27, colour: 'rgba(243,238,226,0.62)' },
        ],
        top: 0.42,
      }),
      S('end', 'gold', 'And sometimes, the hardest thing for an empire to do is recognize that the world has already moved on.', {
        lines: [
          { text: 'The biggest threat', size: 40, at: 0.05, colour: 'rgba(243,238,226,0.60)', gap: 0.085 },
          { text: 'to success', size: 40, at: 0.13, colour: 'rgba(243,238,226,0.60)', gap: 0.105 },
          { text: 'is believing it', size: 54, at: 0.23, gap: 0.10 },
          { text: 'will last forever.', size: 54, at: 0.32, colour: '#E2B94F' },
        ],
        small: 'NOKIA · REINVENTED',
        transition: T('push', { direction: 'left' }),
      }),
    ],
  },
];

/* --------------------------------------------------------------- assemble -- */

const BUILDER = {
  type: typeShot, object: objectShot, chart: chartShot, map: mapShot,
  bands: bandsShot, compare: compareShot, end: endShot,
};

const LEAD = 0.25;
const LEAD_FIRST = 0.30;
const PAD = 0.95;

function readTiming() {
  try {
    return JSON.parse(fs.readFileSync(new URL('./nokia_empire-timing.json', import.meta.url), 'utf8'));
  } catch {
    return null;
  }
}

const SPOKEN = Object.fromEntries((readTiming() || []).map((r) => [r.shot, r.vo]));

const ROWS = [];
for (const scene of SCENES) {
  scene.shots.forEach((s, i) => {
    const id = `s${String(scene.n).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`;
    const vo = SPOKEN[id];
    const dur = vo === undefined
      ? Math.round((LEAD + s.t.trim().split(/\s+/).length / 2.42 + PAD) * 100) / 100
      : Math.round((LEAD + vo + PAD) * 100) / 100;
    ROWS.push({ id, scene: scene.n, sceneName: scene.name, text: s.t, dur, ...s });
  });
}

export const FILM = ROWS.map((row, i, all) => {
  const shot = BUILDER[row.k](row.w, row.o);
  const token = row.o.transition || null;
  const ground = (i > 0 ? all[i - 1] : row).w;
  const from = i > 0 ? all[i - 1] : row;
  const paperGround = shot.background;
  void ground;
  let transition = { kind: 'cut', label: 'cut', options: {} };
  if (token) {
    transition = token.kind === 'fade'
      ? { ...token, options: { ...token.options, colour: prevGround(all, i) } }
      : token;
  }
  return { ...shot, id: row.id, text: row.text, dur: row.dur, transition, scene: row.scene };
});

function prevGround(all, i) {
  if (i === 0) return '#101010';
  const prev = all[i - 1];
  const shot = BUILDER[prev.k](prev.w, prev.o);
  return shot.background || '#101010';
}

export function totalSeconds(shots = FILM) {
  return shots.reduce((a, s) => a + s.dur, 0);
}

export function shotStarts(shots = FILM) {
  let at = 0;
  return shots.map((s, i) => {
    const row = {
      id: s.id,
      scene: s.scene,
      start: Math.round(at * 1000) / 1000,
      end: Math.round((at + s.dur) * 1000) / 1000,
      voStart: Math.round((at + (i === 0 ? LEAD_FIRST : LEAD)) * 1000) / 1000,
      transition: (s.transition && s.transition.label) || 'cut',
    };
    at += s.dur;
    return row;
  });
}

export function shotAt(t, shots = FILM) {
  let at = 0;
  for (const shot of shots) {
    if (t < at + shot.dur) return shot;
    at += shot.dur;
  }
  return shots[shots.length - 1];
}

/* ----------------------------------------------------------------- main ---- */

async function main() {
  const args = process.argv.slice(2);
  const flag = (k, d = null) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
  loadFonts();
  const fps = Number(flag('--fps') || 24);
  const scale = Number(flag('--scale') || 1);
  const stills = flag('--stills');
  const framesDir = flag('--frames');
  const startsPath = flag('--starts');
  const linesPath = flag('--lines');
  const dw = Math.round(W * scale);
  const dh = Math.round(H * scale);

  if (linesPath) {
    fs.writeFileSync(path.resolve(linesPath), JSON.stringify(
      FILM.map((s) => ({ shot: s.id, text: s.text })), null, 2,
    ));
    console.log(`wrote ${linesPath} (${FILM.length} lines)`);
    return;
  }

  if (startsPath) {
    fs.writeFileSync(path.resolve(startsPath), JSON.stringify(shotStarts(), null, 2));
    console.log(`wrote ${startsPath} (${totalSeconds().toFixed(1)}s)`);
  }

  const canvas = createCanvas(dw, dh);
  const ctx = canvas.getContext('2d');
  const renderer = createRenderer(FILM, W, H, { join: 0.45, background: FILM[0].background, scale });
  const fb = frameBuffer(dw, dh);
  const paint = (t) => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, dw, dh);
    renderer.render(ctx, t);
    fb.ctx.setTransform(1, 0, 0, 1, 0, 0);
    fb.ctx.clearRect(0, 0, dw, dh);
    fb.ctx.drawImage(canvas, 0, 0);
    optics(ctx, { source: fb.canvas, w: dw, h: dh, frame: Math.round(t * fps), ...opticsFor(shotAt(t)) });
  };

  if (stills) {
    fs.mkdirSync(stills, { recursive: true });
    shotStarts().forEach((row, i) => {
      const t = row.start + (row.end - row.start) * 0.78;
      paint(t);
      fs.writeFileSync(path.join(stills, `${String(i).padStart(3, '0')}-${FILM[i].id}.png`), canvas.toBuffer('image/png'));
    });
    console.log(`wrote ${FILM.length} stills to ${stills}`);
    return;
  }

  if (flag('--pipe')) {
    const total = Math.round(renderer.duration * fps);
    const from = Number(flag('--from', 0));
    const to = Math.min(total, Number(flag('--to', total)));
    for (let i = from; i < to; i += 1) {
      paint(i / fps);
      const data = canvas.data();
      let off = 0;
      while (off < data.length) {
        const chunk = data.subarray(off);
        off += chunk.length;
        if (!process.stdout.write(chunk)) {
          await new Promise((resolve) => process.stdout.once('drain', resolve));
        }
      }
    }
    return;
  }

  if (framesDir) {
    fs.mkdirSync(framesDir, { recursive: true });
    const total = Math.round(renderer.duration * fps);
    const from = Number(flag('--from', 0));
    const to = Math.min(total, Number(flag('--to', total)));
    for (let i = from; i < to; i += 1) {
      paint(i / fps);
      fs.writeFileSync(path.join(framesDir, `${String(i).padStart(5, '0')}.png`), canvas.toBuffer('image/png'));
    }
    console.log(`wrote frames ${from}-${to} of ${total}`);
    return;
  }

  console.log(`${FILM.length} shots, ${totalSeconds().toFixed(1)}s`);
  shotStarts().forEach((s) => console.log(
    `  ${s.start.toFixed(1)}s  ${s.id}  ${(s.end - s.start).toFixed(1)}s  [${s.transition}]`,
  ));
}

if (import.meta.url === `file://${process.argv[1]}`) main();
