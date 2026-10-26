/**
 * The accessory library.
 *
 * The film was rejected for repeating the same stock: one phone glyph, one map,
 * carried through eight shots. Each shot in this story needs its own subject -
 * a mill in 1865, a rubber works, a cable drum, a chip - and an object that is
 * shared between shots is shared because it is the *same object*, not because
 * the kit only has one.
 *
 * Every drawing here is a modelled thing in the same idiom as product.mjs: a
 * base shape shaded across its form, a highlight on the lit side, a shadow on
 * the far side, and a contact shadow where it meets the ground. No flat fills.
 *
 * All of it is paths and gradients, deterministic in `t`, resolution free.
 */
import { roundRect, clamp, lerp, noise } from '../ui.mjs';

const shade = (ctx, x0, y0, x1, y1, stops) => {
  const g = ctx.createLinearGradient(x0, y0, x1, y1);
  stops.forEach(([at, col]) => g.addColorStop(at, col));
  return g;
};

/** Ground shadow under anything standing up. */
export function contact(ctx, cx, cy, rx, ry, alpha = 0.45) {
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rx);
  g.addColorStop(0, `rgba(0,0,0,${alpha})`);
  g.addColorStop(0.6, `rgba(0,0,0,${alpha * 0.35})`);
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
}

/* ----------------------------------------------------------- a skyline ---- */

/**
 * A city, in three depths. Towers are generated from a seed, so the skyline is
 * the same on every frame and can be re-rendered identically, but no two shots
 * of the film get the same skyline.
 */
export function drawSkyline(ctx, {
  x, y, w, h, seed = 1, layers = 3, p = 1, lit = 0.5,
  near = '#161412', far = '#3A322C', window = '#F2C867',
}) {
  for (let L = 0; L < layers; L += 1) {
    const depth = L / Math.max(1, layers - 1);
    const baseY = y + h;
    const height = h * lerp(0.95, 0.42, depth);
    const colour = lerp(0, 1, depth) > 0.5 ? far : near;
    const alpha = lerp(1, 0.55, depth);
    const rise = clamp(p * (1.25 - depth * 0.3));
    ctx.save();
    ctx.globalAlpha *= alpha;
    let cx = x;
    let i = 0;
    while (cx < x + w) {
      const n = noise(seed * 13.7 + L * 91.3 + i * 5.1);
      const n2 = noise(seed * 7.1 + L * 41.9 + i * 3.3);
      const bw = w * (0.045 + n * 0.055);
      const bh = height * (0.32 + n2 * 0.68) * rise;
      const top = baseY - bh;
      const g = shade(ctx, cx, top, cx + bw, baseY, [
        [0, colour],
        [0.55, colour],
        [1, 'rgba(0,0,0,0.55)'],
      ]);
      ctx.fillStyle = g;
      ctx.fillRect(cx, top, bw, bh);
      /* a rooftop mark on some towers */
      if (n2 > 0.62) {
        ctx.fillStyle = colour;
        ctx.fillRect(cx + bw * 0.42, top - bh * 0.09, bw * 0.16, bh * 0.09);
      }
      /* windows, only on the near layer, and only some of them lit */
      if (L === 0 && bh > h * 0.18) {
        const cols = Math.max(1, Math.round(bw / (w * 0.018)));
        const rows = Math.max(2, Math.round(bh / (h * 0.055)));
        for (let r = 0; r < rows; r += 1) {
          for (let c = 0; c < cols; c += 1) {
            const wl = noise(seed * 3.1 + i * 17 + r * 7 + c * 2.7);
            if (wl > 1 - lit) {
              ctx.fillStyle = `rgba(242,200,103,${0.25 + wl * 0.5})`;
              ctx.fillRect(
                cx + bw * (0.14 + c * 0.72 / cols),
                top + bh * (0.10 + r * 0.82 / rows),
                Math.max(1, bw * 0.26 / cols),
                Math.max(1, bh * 0.34 / rows),
              );
            }
          }
        }
      }
      cx += bw * 0.92;
      i += 1;
    }
    ctx.restore();
  }
}

/* ------------------------------------------------------- a smartphone ---- */

/** The other end of the story: a glass slab, lit, with a grid of apps. */
export function drawSmartphone(ctx, {
  x, y, w, h, glow = 1, rotate = 0, apps = 12,
  bodyColour = '#1B1D21', screenFrom = '#16324F', screenTo = '#0A1520',
}) {
  ctx.save();
  ctx.translate(x + w / 2, y + h / 2);
  if (rotate) ctx.rotate(rotate);
  ctx.translate(-w / 2, -h / 2);

  /* the slab */
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.6)';
  ctx.shadowBlur = w * 0.22;
  ctx.shadowOffsetY = h * 0.02;
  ctx.fillStyle = shade(ctx, 0, 0, w, 0, [
    [0, '#4A4E58'], [0.10, bodyColour], [0.80, '#0E1013'], [1, '#31343A'],
  ]);
  roundRect(ctx, 0, 0, w, h, w * 0.14);
  ctx.fill();
  ctx.restore();

  /* rim light */
  ctx.strokeStyle = 'rgba(255,255,255,0.16)';
  ctx.lineWidth = Math.max(1, w * 0.008);
  roundRect(ctx, w * 0.006, h * 0.004, w * 0.988, h * 0.992, w * 0.135);
  ctx.stroke();

  /* the glass */
  const inset = w * 0.045;
  const sx = inset;
  const sy = inset;
  const sw = w - inset * 2;
  const sh = h - inset * 2;
  const g = shade(ctx, 0, sy, 0, sy + sh, [[0, screenFrom], [1, screenTo]]);
  ctx.fillStyle = g;
  roundRect(ctx, sx, sy, sw, sh, w * 0.105);
  ctx.fill();

  /* apps: a grid of lit tiles, some deeper than others */
  ctx.save();
  roundRect(ctx, sx, sy, sw, sh, w * 0.105);
  ctx.clip();
  const cols = 4;
  const rows = Math.ceil(apps / cols);
  const cell = sw / (cols + 1.1);
  for (let i = 0; i < apps; i += 1) {
    const c = i % cols;
    const r = Math.floor(i / cols);
    const ax = sx + cell * 0.55 + c * cell;
    const ay = sy + sh * 0.10 + r * cell * 1.16;
    if (ay > sy + sh * 0.86) break;
    const hue = noise(i * 4.3);
    ctx.fillStyle = `hsl(${Math.round(190 + hue * 90)} ${Math.round(35 + hue * 30)}% ${Math.round(42 + hue * 22)}%)`;
    ctx.globalAlpha = 0.85;
    roundRect(ctx, ax, ay, cell * 0.72, cell * 0.72, cell * 0.20);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  /* the bloom of a lit screen */
  if (glow > 0) {
    const b = ctx.createLinearGradient(sx, sy, sx, sy + sh);
    b.addColorStop(0, `rgba(150,205,255,${0.16 * glow})`);
    b.addColorStop(0.5, `rgba(120,190,255,${0.05 * glow})`);
    b.addColorStop(1, `rgba(90,160,255,${0.10 * glow})`);
    ctx.fillStyle = b;
    ctx.fillRect(sx, sy, sw, sh);
  }
  /* glass reflection: a hard diagonal, as on the handset */
  ctx.fillStyle = 'rgba(255,255,255,0.07)';
  ctx.beginPath();
  ctx.moveTo(sx - sw * 0.2, sy + sh);
  ctx.lineTo(sx + sw * 0.55, sy - sh * 0.15);
  ctx.lineTo(sx + sw * 0.80, sy - sh * 0.15);
  ctx.lineTo(sx - sw * 0.2, sy + sh * 1.3);
  ctx.closePath();
  ctx.fill();
  ctx.restore();

  /* speaker slot */
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  roundRect(ctx, w * 0.42, h * 0.012, w * 0.16, h * 0.006, h * 0.004);
  ctx.fill();

  ctx.restore();
}

/* ------------------------------------------------ a 1865 paper mill ---- */

/** A pine, as three stacked skirts over a trunk. */
export function drawPine(ctx, { x, y, w, h, colour = '#1D3B32', rim = 'rgba(255,255,255,0.10)' }) {
  ctx.save();
  ctx.fillStyle = '#241C14';
  ctx.fillRect(x + w * 0.44, y + h * 0.72, w * 0.12, h * 0.28);
  const tiers = [
    [0.00, 0.62, 1.00],
    [0.22, 0.56, 0.74],
    [0.44, 0.44, 0.48],
  ];
  for (const [top, widthF, heightF] of tiers) {
    const tw = w * widthF;
    const th = h * heightF;
    const ty = y + h * top;
    const g = shade(ctx, x + w * 0.5 - tw / 2, ty, x + w * 0.5 + tw / 2, ty, [
      [0, colour], [0.6, colour], [1, 'rgba(0,0,0,0.55)'],
    ]);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(x + w * 0.5, ty);
    ctx.lineTo(x + w * 0.5 + tw / 2, ty + th);
    ctx.lineTo(x + w * 0.5 - tw / 2, ty + th);
    ctx.closePath();
    ctx.fill();
  }
  /* rim light down the left edge of the silhouette */
  ctx.strokeStyle = rim;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x + w * 0.5, y);
  ctx.lineTo(x + w * 0.5 - w * 0.31, y + h * 0.62);
  ctx.stroke();
  ctx.restore();
}

/**
 * The mill: a long shed with a pitched roof, a chimney that smokes, a water
 * wheel turning, and windows lit from inside. `t` drives the smoke and the wheel.
 */
export function drawMill(ctx, { x, y, w, h, t = 0, smoke = 1, wheel = 1 }) {
  const wall = '#3B3229';
  const roof = '#241E19';

  /* chimney, behind the shed */
  const chX = x + w * 0.70;
  const chW = w * 0.062;
  const chH = h * 0.92;
  ctx.save();
  ctx.fillStyle = shade(ctx, chX, 0, chX + chW, 0, [
    [0, '#4A4038'], [0.5, '#2E2721'], [1, '#1A1613'],
  ]);
  ctx.fillRect(chX, y + h - chH, chW, chH);
  /* banding */
  for (let i = 0; i < 4; i += 1) {
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(chX, y + h - chH + chH * (0.18 + i * 0.2), chW, h * 0.012);
  }
  ctx.fillStyle = '#15120F';
  ctx.fillRect(chX - chW * 0.12, y + h - chH - h * 0.018, chW * 1.24, h * 0.022);
  ctx.restore();

  /* smoke: puffs that rise, spread and die */
  if (smoke > 0) {
    ctx.save();
    for (let i = 0; i < 9; i += 1) {
      const age = ((t * 0.22 + i * 0.13) % 1);
      const px = chX + chW / 2 + Math.sin(age * 3 + i) * w * 0.06 + age * w * 0.10;
      const py = y + h - chH - h * 0.02 - age * h * 0.55;
      const r = w * (0.02 + age * 0.075);
      const a = (1 - age) * 0.30 * smoke;
      const g = ctx.createRadialGradient(px, py, 0, px, py, r * 2.2);
      g.addColorStop(0, `rgba(214,206,194,${a})`);
      g.addColorStop(1, 'rgba(214,206,194,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(px, py, r * 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  /* the shed */
  const bx = x + w * 0.06;
  const bw = w * 0.78;
  const by = y + h * 0.42;
  const bh = h * 0.58;
  ctx.save();
  ctx.fillStyle = shade(ctx, bx, 0, bx + bw, 0, [
    [0, '#4C4239'], [0.55, wall], [1, '#221C17'],
  ]);
  ctx.fillRect(bx, by, bw, bh);
  /* pitched roof with an overhang */
  ctx.fillStyle = roof;
  ctx.beginPath();
  ctx.moveTo(bx - w * 0.03, by);
  ctx.lineTo(bx + bw * 0.5, by - h * 0.17);
  ctx.lineTo(bx + bw + w * 0.03, by);
  ctx.closePath();
  ctx.fill();
  /* roof rim light */
  ctx.strokeStyle = 'rgba(255,226,180,0.18)';
  ctx.lineWidth = 1.4;
  ctx.stroke();
  /* windows */
  for (let i = 0; i < 7; i += 1) {
    const wx = bx + bw * (0.06 + i * 0.135);
    const wy = by + bh * 0.26;
    ctx.fillStyle = 'rgba(255,196,104,0.72)';
    ctx.fillRect(wx, wy, bw * 0.055, bh * 0.26);
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(wx, wy + bh * 0.12, bw * 0.055, bh * 0.012);
    const wg = ctx.createRadialGradient(wx + bw * 0.028, wy + bh * 0.13, 0, wx + bw * 0.028, wy + bh * 0.13, bw * 0.09);
    wg.addColorStop(0, 'rgba(255,196,104,0.22)');
    wg.addColorStop(1, 'rgba(255,196,104,0)');
    ctx.fillStyle = wg;
    ctx.fillRect(wx - bw * 0.04, wy - bh * 0.08, bw * 0.14, bh * 0.44);
  }
  /* plinth */
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(bx - w * 0.02, y + h * 0.985, bw + w * 0.04, h * 0.015);
  ctx.restore();

  /* water wheel */
  if (wheel > 0) {
    const wx = x + w * 0.045;
    const wy = y + h * 0.66;
    const wr = h * 0.17;
    ctx.save();
    ctx.translate(wx, wy);
    ctx.rotate(t * 0.55);
    ctx.strokeStyle = 'rgba(214,190,150,0.55)';
    ctx.lineWidth = Math.max(1.2, wr * 0.09);
    ctx.beginPath();
    ctx.arc(0, 0, wr, 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = Math.max(1, wr * 0.045);
    for (let i = 0; i < 8; i += 1) {
      const a = (i / 8) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * wr * 0.18, Math.sin(a) * wr * 0.18);
      ctx.lineTo(Math.cos(a) * wr, Math.sin(a) * wr);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * wr, Math.sin(a) * wr);
      ctx.lineTo(Math.cos(a + 0.3) * wr * 1.12, Math.sin(a + 0.3) * wr * 1.12);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(214,190,150,0.7)';
    ctx.beginPath();
    ctx.arc(0, 0, wr * 0.14, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

/* ------------------------------------------------- a company's four trades ---- */

/** Paper: a stack of sheets, seen from the corner. */
export function drawPaperReam(ctx, { x, y, w, h, colour = '#E8E2D2', edge = '#CFC7B4' }) {
  const d = w * 0.26;
  ctx.save();
  ctx.fillStyle = edge;
  ctx.beginPath();
  ctx.moveTo(x, y + h * 0.30);
  ctx.lineTo(x + d, y + h * 0.18);
  ctx.lineTo(x + w, y + h * 0.18);
  ctx.lineTo(x + w - d, y + h * 0.30);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = shade(ctx, 0, y, 0, y + h, [[0, colour], [1, '#B9B2A2']]);
  roundRect(ctx, x + d * 0.1, y + h * 0.30, w - d * 0.2, h * 0.52, 2);
  ctx.fill();
  /* individual sheets on the front face */
  ctx.strokeStyle = 'rgba(0,0,0,0.10)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 7; i += 1) {
    const yy = y + h * 0.30 + (h * 0.52 * i) / 7;
    ctx.beginPath();
    ctx.moveTo(x + d * 0.1, yy);
    ctx.lineTo(x + w - d * 0.1, yy);
    ctx.stroke();
  }
  /* banding */
  ctx.fillStyle = 'rgba(20,24,30,0.55)';
  ctx.fillRect(x + w * 0.30, y + h * 0.29, w * 0.10, h * 0.54);
  ctx.fillRect(x + w * 0.62, y + h * 0.29, w * 0.10, h * 0.54);
  ctx.restore();
}

/** Rubber: a dark sheet with a live edge and a wet sheen. */
export function drawRubberSheet(ctx, { x, y, w, h }) {
  ctx.save();
  const g = shade(ctx, 0, y, 0, y + h, [[0, '#3A3A3C'], [0.4, '#232326'], [1, '#101012']]);
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.moveTo(x, y + h * 0.22);
  ctx.bezierCurveTo(x + w * 0.25, y + h * 0.08, x + w * 0.6, y + h * 0.30, x + w, y + h * 0.16);
  ctx.lineTo(x + w, y + h * 0.86);
  ctx.bezierCurveTo(x + w * 0.6, y + h * 0.98, x + w * 0.25, y + h * 0.74, x, y + h * 0.88);
  ctx.closePath();
  ctx.fill();
  /* the sheen runs along the top edge */
  ctx.strokeStyle = 'rgba(200,210,225,0.55)';
  ctx.lineWidth = Math.max(1.2, h * 0.022);
  ctx.beginPath();
  ctx.moveTo(x, y + h * 0.235);
  ctx.bezierCurveTo(x + w * 0.25, y + h * 0.095, x + w * 0.6, y + h * 0.315, x + w, y + h * 0.175);
  ctx.stroke();
  /* a broad soft highlight across the face, so it reads as a surface */
  const sheen = ctx.createLinearGradient(x, y + h * 0.3, x + w, y + h * 0.8);
  sheen.addColorStop(0, 'rgba(255,255,255,0.10)');
  sheen.addColorStop(0.5, 'rgba(255,255,255,0.02)');
  sheen.addColorStop(1, 'rgba(255,255,255,0.09)');
  ctx.fillStyle = sheen;
  ctx.beginPath();
  ctx.moveTo(x, y + h * 0.24);
  ctx.bezierCurveTo(x + w * 0.25, y + h * 0.10, x + w * 0.6, y + h * 0.32, x + w, y + h * 0.18);
  ctx.lineTo(x + w, y + h * 0.85);
  ctx.bezierCurveTo(x + w * 0.6, y + h * 0.97, x + w * 0.25, y + h * 0.73, x, y + h * 0.87);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/** Cable: a drum of it, wound in visible layers. */
export function drawCableDrum(ctx, { x, y, w, h, colour = '#1E2226', wrap = '#C4692E' }) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const r = Math.min(w, h) * 0.46;
  ctx.save();
  ctx.fillStyle = shade(ctx, cx - r, cy, cx + r, cy, [
    [0, '#3B302A'], [0.5, '#2A221D'], [1, '#151210'],
  ]);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  /* the winding, as concentric turns with a break in each */
  for (let i = 0; i < 7; i += 1) {
    const rr = r * (0.34 + i * 0.088);
    ctx.strokeStyle = i % 2 ? colour : wrap;
    ctx.lineWidth = Math.max(1.5, r * 0.055);
    ctx.beginPath();
    ctx.arc(cx, cy, rr, 0.5 + i * 0.4, 0.5 + i * 0.4 + Math.PI * 1.65);
    ctx.stroke();
  }
  /* the core */
  ctx.fillStyle = '#0C0B0A';
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.30, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.30, 0, Math.PI * 2);
  ctx.stroke();
  /* one loose end, curling off the drum */
  ctx.strokeStyle = wrap;
  ctx.lineWidth = Math.max(1.6, r * 0.06);
  ctx.beginPath();
  ctx.moveTo(cx + r * 0.86, cy - r * 0.22);
  ctx.bezierCurveTo(cx + r * 1.20, cy + r * 0.10, cx + r * 0.92, cy + r * 0.62, cx + r * 1.16, cy + r * 0.86);
  ctx.stroke();
  ctx.restore();
}

/** Electronics: a chip, with legs, a die and a pin-one mark. */
export function drawChip(ctx, { x, y, w, h, colour = '#2A2D34' }) {
  const s = Math.min(w, h);
  const bx = x + (w - s) / 2;
  const by = y + (h - s) / 2;
  ctx.save();
  /* legs */
  ctx.fillStyle = '#B9BEC7';
  const legs = 7;
  for (let i = 0; i < legs; i += 1) {
    const off = s * (0.12 + i * (0.76 / (legs - 1)));
    ctx.fillRect(bx + off - s * 0.012, by - s * 0.055, s * 0.024, s * 0.06);
    ctx.fillRect(bx + off - s * 0.012, by + s * 0.995, s * 0.024, s * 0.06);
    ctx.fillRect(bx - s * 0.055, by + off - s * 0.012, s * 0.06, s * 0.024);
    ctx.fillRect(bx + s * 0.995, by + off - s * 0.012, s * 0.06, s * 0.024);
  }
  /* package */
  const g = shade(ctx, bx, by, bx + s, by + s, [
    [0, '#464B55'], [0.35, colour], [1, '#121418'],
  ]);
  ctx.fillStyle = g;
  roundRect(ctx, bx, by, s, s, s * 0.06);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.12)';
  ctx.lineWidth = 1;
  roundRect(ctx, bx, by, s, s, s * 0.06);
  ctx.stroke();
  /* the die, and its bond wires */
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fillRect(bx + s * 0.22, by + s * 0.22, s * 0.56, s * 0.56);
  ctx.fillStyle = 'rgba(196,151,60,0.75)';
  ctx.fillRect(bx + s * 0.31, by + s * 0.31, s * 0.38, s * 0.38);
  ctx.strokeStyle = 'rgba(255,226,160,0.5)';
  ctx.lineWidth = Math.max(0.6, s * 0.006);
  for (let i = 0; i < 9; i += 1) {
    const a = (i / 9) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(bx + s * 0.5 + Math.cos(a) * s * 0.19, by + s * 0.5 + Math.sin(a) * s * 0.19);
    ctx.lineTo(bx + s * 0.5 + Math.cos(a) * s * 0.27, by + s * 0.5 + Math.sin(a) * s * 0.27);
    ctx.stroke();
  }
  /* pin one */
  ctx.fillStyle = 'rgba(255,255,255,0.35)';
  ctx.beginPath();
  ctx.arc(bx + s * 0.12, by + s * 0.12, s * 0.028, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/** A plinth: what an object is displayed on when it is not in a room. */
export function drawPlinth(ctx, { x, y, w, h, colour = 'rgba(255,255,255,0.06)' }) {
  const g = shade(ctx, 0, y, 0, y + h, [[0, colour], [1, 'rgba(0,0,0,0.25)']]);
  ctx.fillStyle = g;
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(x, y, w, 1);
}

export const OBJECTS = {
  skyline: drawSkyline,
  smartphone: drawSmartphone,
  pine: drawPine,
  mill: drawMill,
  paper: drawPaperReam,
  rubber: drawRubberSheet,
  cable: drawCableDrum,
  chip: drawChip,
};
