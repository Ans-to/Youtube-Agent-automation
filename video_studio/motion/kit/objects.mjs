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
 * A city with air in it.
 *
 * The first skyline was four hard-edged rectangles at four different greys, and
 * at 1080p it read as a bar chart lying on its side. What makes a city read is
 * not more buildings, it is **depth**: each layer is further away, so it is
 * lighter, lower in contrast, smaller in detail, and moves less. Add the haze
 * between the layers, the glow where the streets are, and something in the
 * foreground to look past, and the frame stops being flat.
 *
 * `parallax` (in units of frame width) moves the near layers more than the far
 * ones. `haze` is [r,g,b] of the air, which is also the colour the far buildings
 * fade toward.
 */
export function drawCityscape(ctx, {
  x, y, w, h,
  seed = 1,
  p = 1,
  t = 0,
  parallax = 0,
  layers = 5,
  near = '#080605',
  haze = '#8C4A20',
  window = '#FFC46A',
  lit = 0.5,
  horizon = 0.72,
}) {
  /*
   * The composition is a skyline seen from across the water: sky above, a city
   * standing on a single ground line, and the near buildings tall enough to push
   * into the sky. The first attempt put each layer on its own rising ground and
   * gave the near one a height of half the frame, which is how a city turns into
   * a black wall - the near towers simply filled the picture.
   */
  const hz = y + h * horizon;

  /* sky: dark overhead, thick and warm at the city */
  const air = ctx.createLinearGradient(0, y, 0, hz);
  air.addColorStop(0, '#070404');
  air.addColorStop(0.40, '#25110A');
  air.addColorStop(0.76, '#7A3E1C');
  air.addColorStop(1, '#EDA25C');
  ctx.save();
  ctx.globalAlpha *= clamp(p * 2.6);
  ctx.fillStyle = air;
  ctx.fillRect(x - w, y - h, w * 3, hz - y + h);
  ctx.restore();

  /* sun: below the rooftops, so the towers stand in front of it */
  const sx = x + w * 0.30;
  const sun = ctx.createRadialGradient(sx, hz, 0, sx, hz, h * 0.50);
  sun.addColorStop(0, 'rgba(255,238,200,0.95)');
  sun.addColorStop(0.08, 'rgba(255,214,150,0.55)');
  sun.addColorStop(0.30, 'rgba(244,168,88,0.16)');
  sun.addColorStop(1, 'rgba(234,146,72,0)');
  ctx.save();
  ctx.globalAlpha *= clamp(p * 2.4);
  ctx.fillStyle = sun;
  ctx.fillRect(x - w, y - h, w * 3, hz - y + h);
  ctx.restore();

  const lift = (k) => {
    const a = [1, 3, 5].map((i) => parseInt(near.slice(i, i + 2), 16));
    const b = [1, 3, 5].map((i) => parseInt(haze.slice(i, i + 2), 16));
    return a.map((v, i) => Math.round(v + (b[i] - v) * k));
  };

  /* far to near; every layer stands on the same line */
  for (let L = 0; L < layers; L += 1) {
    const d = layers === 1 ? 0.6 : L / (layers - 1);
    const airK = Math.pow(1 - d, 1.5);
    const tallest = h * (0.06 + Math.pow(d, 1.3) * 0.40);
    const px = parallax * w * (0.05 + d * 0.95);
    const base = lift(0.58 * airK + 0.02);
    const dark = base.map((v) => Math.round(v * 0.40));
    const glass = Math.round(255 - airK * 60);

    const rise = clamp((p - L * 0.05) * 2.6);
    if (rise <= 0) continue;

    ctx.save();
    ctx.translate(px, (1 - rise) * h * 0.05);

    let cx = x - w * 0.15;
    let i = 0;
    while (cx < x + w * 1.15) {
      const n1 = noise(seed * 17.3 + L * 131.7 + i * 5.13);
      const n2 = noise(seed * 7.9 + L * 57.1 + i * 3.77);
      const n3 = noise(seed * 3.1 + L * 23.9 + i * 9.41);
      const bw = w * (0.012 + n1 * (0.022 + d * 0.058));
      const bh = tallest * (0.18 + Math.pow(n2, 1.7) * 0.82) * rise;
      const top = hz - bh;
      const tint = 0.80 + n3 * 0.40;

      ctx.fillStyle = shade(ctx, cx, 0, cx + bw, 0, [
        [0, `rgb(${Math.round(base[0] * tint)},${Math.round(base[1] * tint)},${Math.round(base[2] * tint)})`],
        [0.70, `rgb(${Math.round(dark[0] * tint)},${Math.round(dark[1] * tint)},${Math.round(dark[2] * tint)})`],
        [1, `rgb(${Math.round(dark[0] * 0.75)},${Math.round(dark[1] * 0.75)},${Math.round(dark[2] * 0.75)})`],
      ]);
      ctx.fillRect(cx, top, bw, bh + h * 0.02);

      /* crown / setback / mast */
      if (n2 > 0.55 && d > 0.25) {
        const cw = bw * (0.36 + n3 * 0.28);
        ctx.fillRect(cx + (bw - cw) / 2, top - bh * 0.05, cw, bh * 0.05);
      }
      if (n2 > 0.80 && d > 0.5) {
        ctx.fillRect(cx + bw * 0.47, top - bh * 0.12, Math.max(1, bw * 0.04), bh * 0.12);
      }

      /* windows: a grid that fits the face, or a scatter of pixels when the
         building is too far away to have one */
      const cellW = bw / (4 + Math.round(n3 * 3));
      if (cellW >= 5 && bh > h * 0.05) {
        const cols = Math.max(1, Math.floor(bw / cellW));
        const cellH = cellW * 1.7;
        const rows = Math.max(1, Math.floor((bh * 0.72) / cellH));
        const ww = cellW * 0.44;
        const wh = Math.max(1, cellH * 0.38);
        for (let r = 0; r < rows; r += 1) {
          for (let c = 0; c < cols; c += 1) {
            const wl = noise(seed * 5.7 + i * 31 + r * 7.3 + c * 2.1 + L * 11);
            if (wl < 1 - lit) continue;
            ctx.fillStyle = `rgba(${glass},${Math.round(glass * 0.72)},${Math.round(glass * 0.34)},${(0.20 + wl * 0.55) * (0.35 + d * 0.65)})`;
            ctx.fillRect(cx + cellW * 0.30 + c * cellW, top + cellH * 0.45 + r * cellH, ww, wh);
          }
        }
      } else {
        const dots = Math.round((bh / h) * 22);
        for (let r = 0; r < dots; r += 1) {
          const wl = noise(seed * 2.3 + i * 13 + r * 5.9 + L);
          if (wl < 0.72) continue;
          ctx.fillStyle = `rgba(${glass},${Math.round(glass * 0.72)},${Math.round(glass * 0.34)},0.26)`;
          ctx.fillRect(cx + bw * (0.15 + noise(wl * 31) * 0.70), top + bh * (0.10 + wl * 0.80), 1.3, 1.7);
        }
      }
      cx += bw * (0.95 + n3 * 0.12);
      i += 1;
    }

    /* air in front of the layer, thickest at the ground */
    const hzRgb = [1, 3, 5].map((i2) => parseInt(haze.slice(i2, i2 + 2), 16));
    const band = ctx.createLinearGradient(0, hz - tallest, 0, hz + h * 0.02);
    band.addColorStop(0, `rgba(${hzRgb[0]},${hzRgb[1]},${hzRgb[2]},0)`);
    band.addColorStop(0.6, `rgba(150,84,42,${0.10 * (1 - d)})`);
    band.addColorStop(1, `rgba(206,124,62,${0.34 * (1 - d)})`);
    ctx.fillStyle = band;
    ctx.fillRect(x - w, hz - tallest, w * 3, tallest + h * 0.02);
    ctx.restore();
  }

  /* the ground plane: wet, and carrying the last of the sky */
  const st = ctx.createLinearGradient(0, hz - h * 0.01, 0, y + h);
  st.addColorStop(0, 'rgba(226,138,70,0)');
  st.addColorStop(0.02, 'rgba(198,104,48,0.22)');
  st.addColorStop(0.07, 'rgba(58,28,14,0.72)');
  st.addColorStop(0.22, 'rgba(12,7,5,0.96)');
  st.addColorStop(1, 'rgba(4,3,2,1)');
  ctx.save();
  ctx.globalAlpha *= clamp(p * 2.4);
  ctx.fillStyle = st;
  ctx.fillRect(x - w, hz, w * 3, y + h - hz);
  /* reflections running down the wet street */
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 18; i += 1) {
    const rx = x + noise(seed * 3.7 + i * 2.3) * w;
    const rl = (h - (hz - y)) * (0.12 + noise(seed + i * 1.7) * 0.55);
    const rg = ctx.createLinearGradient(0, hz, 0, hz + rl);
    rg.addColorStop(0, 'rgba(255,186,104,0.20)');
    rg.addColorStop(1, 'rgba(255,186,104,0)');
    ctx.fillStyle = rg;
    ctx.fillRect(rx, hz, 1.4 + noise(i) * 2.2, rl);
  }
  ctx.restore();
}

/**
 * Something to look past: the roof of the building the camera is standing on,
 * a parapet, a water tank, an antenna. A city with no foreground is a backdrop.
 */
/**
 * The foreground: the roof the camera is standing on.
 *
 * Not a building - a parapet across the bottom of the frame, a water tank and a
 * television aerial standing above it, both cropped by the edges. The first
 * version drew the tank whole and centred, and it read as a house on legs.
 *
 * @param baseline  y of the top of the parapet, in canvas units
 */
export function drawRooftop(ctx, { x, y, w, h, baseline, colour = '#040302' }) {
  const top = baseline ?? y;
  ctx.save();

  /* the parapet itself, board-built, with a coping stone catching the sky */
  ctx.fillStyle = shade(ctx, 0, top, 0, top + h, [
    [0, '#1E140D'], [0.25, '#0B0705'], [1, colour],
  ]);
  ctx.fillRect(x - w * 2, top, w * 5, h);
  ctx.fillStyle = 'rgba(255,178,104,0.30)';
  ctx.fillRect(x - w * 2, top, w * 5, Math.max(1, h * 0.05));
  ctx.strokeStyle = 'rgba(0,0,0,0.60)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 26; i += 1) {
    const jx = x - w * 2 + (w * 5 * i) / 26;
    ctx.beginPath();
    ctx.moveTo(jx, top + h * 0.06);
    ctx.lineTo(jx, top + h);
    ctx.stroke();
  }

  /* the aerial, at the left, cropped by the frame edge */
  const ax = x + w * 0.145;
  const ah = h * 4.2;
  ctx.strokeStyle = 'rgba(8,6,5,0.98)';
  ctx.lineWidth = Math.max(1.4, w * 0.004);
  ctx.beginPath();
  ctx.moveTo(ax, top);
  ctx.lineTo(ax, top - ah);
  ctx.stroke();
  for (let i = 0; i < 5; i += 1) {
    const ey = top - ah * (0.46 + i * 0.125);
    const ew = w * (0.062 - i * 0.008);
    ctx.beginPath();
    ctx.moveTo(ax - ew, ey);
    ctx.lineTo(ax + ew, ey);
    ctx.stroke();
  }

  /* the water tank, at the right, cropped by the frame edge */
  const tw = w * 0.062;
  const th = h * 3.1;
  const tx = x + w * 0.845;
  const ty = top - th;
  ctx.fillStyle = shade(ctx, tx, 0, tx + tw, 0, [[0, '#181009'], [1, '#050403']]);
  ctx.fillRect(tx, ty, tw, th);
  /* its lid, and the rim light along the top of it */
  ctx.beginPath();
  ctx.moveTo(tx - tw * 0.05, ty);
  ctx.lineTo(tx + tw * 0.5, ty - th * 0.16);
  ctx.lineTo(tx + tw * 1.05, ty);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,180,110,0.26)';
  ctx.lineWidth = Math.max(1, w * 0.0028);
  ctx.beginPath();
  ctx.moveTo(tx - tw * 0.05, ty);
  ctx.lineTo(tx + tw * 0.5, ty - th * 0.16);
  ctx.lineTo(tx + tw * 1.05, ty);
  ctx.stroke();
  /* two hoops, so the tank reads as a tank */
  ctx.strokeStyle = 'rgba(0,0,0,0.55)';
  ctx.beginPath();
  ctx.moveTo(tx, ty + th * 0.34);
  ctx.lineTo(tx + tw, ty + th * 0.34);
  ctx.moveTo(tx, ty + th * 0.66);
  ctx.lineTo(tx + tw, ty + th * 0.66);
  ctx.stroke();
  /* the frame it stands on, going down out of frame */
  ctx.fillStyle = '#040302';
  ctx.fillRect(tx + tw * 0.12, ty + th, tw * 0.06, top - ty - th + h * 0.02);
  ctx.fillRect(tx + tw * 0.80, ty + th, tw * 0.06, top - ty - th + h * 0.02);
  ctx.restore();
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

/**
 * A pine, as a stack of skirts over a trunk.
 *
 * Three flat triangles read as a triangle. The tier edges are what make it a
 * tree, so each skirt is a shaded cone with a lit left edge, a dark right side,
 * and a small scallop where it meets the one below.
 */
export function drawPine(ctx, {
  x, y, w, h,
  colour = '#1D3B32', dark = '#0A1512', rim = 'rgba(190,214,180,0.22)',
}) {
  ctx.save();
  /* trunk */
  const tg = shade(ctx, x + w * 0.46, 0, x + w * 0.56, 0, [
    [0, '#2A2119'], [1, '#120D09'],
  ]);
  ctx.fillStyle = tg;
  ctx.fillRect(x + w * 0.455, y + h * 0.74, w * 0.09, h * 0.26);

  const tiers = 5;
  for (let i = 0; i < tiers; i += 1) {
    const k = i / (tiers - 1);
    const top = y + h * (0.02 + k * 0.62);
    const bot = y + h * (0.26 + k * 0.62);
    const half = w * (0.16 + k * 0.34);
    const cx = x + w * 0.5;
    const g = shade(ctx, cx - half, 0, cx + half, 0, [
      [0, colour],
      [0.45, colour],
      [1, dark],
    ]);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(cx, top);
    /* the underside scallops outward, which is what a fir does */
    ctx.quadraticCurveTo(cx + half * 0.45, bot - (bot - top) * 0.30, cx + half, bot - (bot - top) * 0.10);
    ctx.quadraticCurveTo(cx + half * 0.30, bot + (bot - top) * 0.04, cx, bot + (bot - top) * 0.02);
    ctx.quadraticCurveTo(cx - half * 0.30, bot + (bot - top) * 0.04, cx - half, bot - (bot - top) * 0.10);
    ctx.quadraticCurveTo(cx - half * 0.45, bot - (bot - top) * 0.30, cx, top);
    ctx.closePath();
    ctx.fill();
    /* rim light on the left of each skirt */
    ctx.strokeStyle = rim;
    ctx.lineWidth = Math.max(0.8, w * 0.008);
    ctx.beginPath();
    ctx.moveTo(cx, top);
    ctx.quadraticCurveTo(cx - half * 0.45, bot - (bot - top) * 0.30, cx - half, bot - (bot - top) * 0.10);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * The mill, at night, in 1865.
 *
 * The first version was a light grey box with a triangle on top and a row of
 * glowing rectangles; it read at thumbnail size and fell apart at 1080p. A
 * building seen at night has a stone foot, board walls with a grain, a roof with
 * two planes and an eave that throws a shadow, a chimney that tapers and smokes,
 * windows set back behind frames, and a wet forecourt that catches their light.
 *
 * `t` drives the wheel, the smoke and the water.
 */
export function drawMill(ctx, { x, y, w, h, t = 0, smoke = 1, wheel = 1, lit = 1 }) {
  const bodyTop = y + h * 0.34;
  const bodyBot = y + h * 0.93;
  const bx = x + w * 0.10;
  const bw = w * 0.72;
  const cx = bx + bw * 0.5;
  const roofH = h * 0.22;

  /* water in front of the building, before anything stands on it */
  ctx.save();
  const waterTop = bodyBot - h * 0.02;
  const water = ctx.createLinearGradient(0, waterTop, 0, y + h);
  water.addColorStop(0, '#101A1C');
  water.addColorStop(0.4, '#080F11');
  water.addColorStop(1, '#04080A');
  ctx.fillStyle = water;
  ctx.fillRect(x - w * 1.4, waterTop, w * 3.8, h * 0.16);
  for (let i = 0; i < 11; i += 1) {
    const wy = waterTop + h * (0.006 + i * 0.012);
    const wobble = Math.sin(t * 0.8 + i) * w * 0.01;
    ctx.strokeStyle = `rgba(226,180,92,${0.05 - i * 0.004})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x - w * 1.4 + wobble, wy);
    ctx.lineTo(x + w * 2.4 + wobble, wy);
    ctx.stroke();
  }
  ctx.restore();

  /* ---------------------------------------------------------- chimney -- */
  const chW = w * 0.055;
  const chX = cx + bw * 0.24;
  const chTop = y + h * 0.02;
  const chH = bodyTop - chTop + h * 0.06;
  ctx.save();
  /* the stack tapers a little, as brick stacks do */
  const cg = shade(ctx, chX, 0, chX + chW, 0, [
    [0, '#4A3B2E'], [0.35, '#2E241B'], [0.75, '#1A140F'], [1, '#100C09'],
  ]);
  ctx.fillStyle = cg;
  ctx.beginPath();
  ctx.moveTo(chX + chW * 0.10, chTop);
  ctx.lineTo(chX + chW * 0.90, chTop);
  ctx.lineTo(chX + chW, bodyTop + h * 0.04);
  ctx.lineTo(chX, bodyTop + h * 0.04);
  ctx.closePath();
  ctx.fill();
  /* courses */
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 16; i += 1) {
    const ly = chTop + (chH * i) / 16;
    const inset = (chW * 0.05) * (i / 16);
    ctx.beginPath();
    ctx.moveTo(chX + inset, ly);
    ctx.lineTo(chX + chW - inset, ly);
    ctx.stroke();
  }
  /* a lighter course now and then, so the brick is not a stripe sequence */
  for (let i = 0; i < 16; i += 3) {
    const ly = chTop + (chH * i) / 16;
    ctx.fillStyle = 'rgba(255,220,170,0.05)';
    ctx.fillRect(chX + chW * 0.08, ly, chW * 0.84, chH / 32);
  }
  /* cap */
  ctx.fillStyle = '#0D0A08';
  ctx.fillRect(chX - chW * 0.14, chTop - h * 0.012, chW * 1.28, h * 0.018);
  ctx.fillStyle = 'rgba(255,210,150,0.10)';
  ctx.fillRect(chX - chW * 0.14, chTop - h * 0.012, chW * 1.28, h * 0.004);
  ctx.restore();

  /* smoke: hotter and tighter at the mouth, wide and thin above */
  if (smoke > 0) {
    ctx.save();
    for (let i = 0; i < 14; i += 1) {
      const age = (t * 0.16 + i * 0.083) % 1;
      const px = chX + chW / 2 + Math.sin(age * 2.4 + i * 0.7) * w * 0.05 + age * w * 0.16;
      const py = chTop - age * h * 0.62;
      const r = w * (0.012 + age * 0.085);
      const a = (1 - age) * 0.16 * smoke;
      const g = ctx.createRadialGradient(px, py, 0, px, py, r * 2.4);
      g.addColorStop(0, `rgba(206,198,186,${a})`);
      g.addColorStop(0.5, `rgba(180,172,160,${a * 0.5})`);
      g.addColorStop(1, 'rgba(160,152,142,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(px, py, r * 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  /* ------------------------------------------------------------- shed -- */
  ctx.save();
  /* stone foot */
  const foot = bodyBot - h * 0.10;
  const sg = shade(ctx, bx, foot, bx, bodyBot, [[0, '#2A2723'], [1, '#141210']]);
  ctx.fillStyle = sg;
  ctx.fillRect(bx, foot, bw, bodyBot - foot);
  ctx.strokeStyle = 'rgba(0,0,0,0.45)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i += 1) {
    const rowY = foot + (bodyBot - foot) * (i / 5);
    ctx.beginPath(); ctx.moveTo(bx, rowY); ctx.lineTo(bx + bw, rowY); ctx.stroke();
    for (let j = 0; j < 9; j += 1) {
      const jx = bx + bw * ((j + (i % 2) * 0.5) / 9);
      ctx.beginPath(); ctx.moveTo(jx, rowY); ctx.lineTo(jx, rowY + (bodyBot - foot) / 5); ctx.stroke();
    }
  }

  /* boarded wall: vertical boards under a raking light */
  const wallG = shade(ctx, bx, 0, bx + bw, 0, [
    [0, '#524434'], [0.28, '#3E3327'], [0.72, '#2A221A'], [1, '#191410'],
  ]);
  ctx.fillStyle = wallG;
  ctx.fillRect(bx, bodyTop, bw, foot - bodyTop);
  ctx.strokeStyle = 'rgba(0,0,0,0.28)';
  ctx.lineWidth = 1;
  const boards = 22;
  for (let i = 1; i < boards; i += 1) {
    const bx2 = bx + (bw * i) / boards;
    ctx.beginPath(); ctx.moveTo(bx2, bodyTop); ctx.lineTo(bx2, foot); ctx.stroke();
  }
  /* two or three boards catch the light differently */
  for (const i of [3, 11, 17]) {
    ctx.fillStyle = 'rgba(255,214,160,0.045)';
    ctx.fillRect(bx + (bw * i) / boards, bodyTop, bw / boards, foot - bodyTop);
  }

  /* eave shadow across the top of the wall */
  const eave = ctx.createLinearGradient(0, bodyTop, 0, bodyTop + h * 0.10);
  eave.addColorStop(0, 'rgba(0,0,0,0.65)');
  eave.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = eave;
  ctx.fillRect(bx, bodyTop, bw, h * 0.10);
  ctx.restore();

  /* ------------------------------------------------------------- roof -- */
  ctx.save();
  /* two planes: the slope toward the moon is lighter than the one away from it */
  const leftRole = shade(ctx, bx, bodyTop - roofH, cx, bodyTop, [
    [0, '#2C3D34'], [1, '#16211C'],
  ]);
  ctx.fillStyle = leftRole;
  ctx.beginPath();
  ctx.moveTo(bx - w * 0.055, bodyTop + h * 0.006);
  ctx.lineTo(cx, bodyTop - roofH);
  ctx.lineTo(cx, bodyTop + h * 0.006);
  ctx.closePath();
  ctx.fill();
  const rightRole = shade(ctx, cx, bodyTop - roofH, bx + bw, bodyTop, [
    [0, '#141E19'], [1, '#0A100D'],
  ]);
  ctx.fillStyle = rightRole;
  ctx.beginPath();
  ctx.moveTo(cx, bodyTop - roofH);
  ctx.lineTo(bx + bw + w * 0.055, bodyTop + h * 0.006);
  ctx.lineTo(cx, bodyTop + h * 0.006);
  ctx.closePath();
  ctx.fill();
  /* shingle courses, following the pitch */
  ctx.strokeStyle = 'rgba(0,0,0,0.30)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 7; i += 1) {
    const k = i / 7;
    ctx.beginPath();
    ctx.moveTo(bx - w * 0.055 + (cx - bx + w * 0.055) * k, bodyTop + h * 0.006 - roofH * k);
    ctx.lineTo(cx, bodyTop + h * 0.006 - roofH * k);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, bodyTop + h * 0.006 - roofH * k);
    ctx.lineTo(bx + bw + w * 0.055 - (bx + bw + w * 0.055 - cx) * k, bodyTop + h * 0.006 - roofH * k);
    ctx.stroke();
  }
  /* ridge and fascias */
  ctx.strokeStyle = 'rgba(226,200,150,0.22)';
  ctx.lineWidth = Math.max(1, w * 0.003);
  ctx.beginPath();
  ctx.moveTo(bx - w * 0.055, bodyTop + h * 0.006);
  ctx.lineTo(cx, bodyTop - roofH);
  ctx.lineTo(bx + bw + w * 0.055, bodyTop + h * 0.006);
  ctx.stroke();
  /* the eave board itself, with thickness */
  ctx.fillStyle = '#0A0F0C';
  ctx.fillRect(bx - w * 0.055, bodyTop + h * 0.004, bw + w * 0.11, h * 0.012);
  ctx.restore();

  /* ---------------------------------------------------------- windows -- */
  const winCount = 5;
  const winW = bw * 0.080;
  const winH = h * 0.20;
  const winY = bodyTop + h * 0.16;
  for (let i = 0; i < winCount; i += 1) {
    const wx = bx + bw * (0.065 + i * 0.152);
    /* the reveals: the wall is thick, so the opening has an edge */
    ctx.fillStyle = '#0A0806';
    ctx.fillRect(wx - winW * 0.10, winY - winH * 0.06, winW * 1.2, winH * 1.12);
    /* the light behind the glass */
    const glow = ctx.createLinearGradient(0, winY, 0, winY + winH);
    glow.addColorStop(0, `rgba(255,206,124,${0.95 * lit})`);
    glow.addColorStop(1, `rgba(226,150,62,${0.85 * lit})`);
    ctx.fillStyle = glow;
    ctx.fillRect(wx, winY, winW, winH);
    /* mullion and transom */
    ctx.fillStyle = 'rgba(20,14,8,0.85)';
    ctx.fillRect(wx + winW * 0.46, winY, winW * 0.08, winH);
    ctx.fillRect(wx, winY + winH * 0.44, winW, winH * 0.06);
    /* light spilling onto the boards under the sill */
    const spill = ctx.createRadialGradient(
      wx + winW / 2, winY + winH, 0,
      wx + winW / 2, winY + winH, winW * 1.9,
    );
    spill.addColorStop(0, `rgba(255,196,110,${0.20 * lit})`);
    spill.addColorStop(1, 'rgba(255,196,110,0)');
    ctx.fillStyle = spill;
    ctx.fillRect(wx - winW, winY, winW * 3, winH * 1.6);
  }

  /* the door, with a lamp over it */
  const dw2 = bw * 0.085;
  const dx2 = bx + bw * 0.845;
  const dy2 = foot - h * 0.20;
  ctx.fillStyle = '#0C0907';
  ctx.fillRect(dx2 - dw2 * 0.08, dy2 - h * 0.012, dw2 * 1.16, h * 0.212);
  const doorG = shade(ctx, dx2, 0, dx2 + dw2, 0, [[0, '#4A3A27'], [1, '#241B12']]);
  ctx.fillStyle = doorG;
  ctx.fillRect(dx2, dy2, dw2, foot - dy2);
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.fillRect(dx2 + dw2 * 0.47, dy2, dw2 * 0.06, foot - dy2);
  const lamp = ctx.createRadialGradient(dx2 + dw2 / 2, dy2 - h * 0.02, 0, dx2 + dw2 / 2, dy2 - h * 0.02, w * 0.09);
  lamp.addColorStop(0, `rgba(255,214,140,${0.55 * lit})`);
  lamp.addColorStop(1, 'rgba(255,214,140,0)');
  ctx.fillStyle = lamp;
  ctx.fillRect(dx2 - w * 0.1, dy2 - h * 0.1, w * 0.2, h * 0.2);

  /* ------------------------------------------------------------- wheel -- */
  if (wheel > 0) {
    const wx = bx - w * 0.015;
    const wy = bodyBot - h * 0.12;
    const wr = h * 0.16;
    ctx.save();
    ctx.translate(wx, wy);
    /* the wheel is lit from the building side and dark on the far side */
    ctx.rotate(t * 0.5);
    ctx.strokeStyle = 'rgba(214,186,140,0.55)';
    ctx.lineWidth = Math.max(1.4, wr * 0.085);
    ctx.beginPath(); ctx.arc(0, 0, wr, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = Math.max(1.2, wr * 0.06);
    ctx.beginPath(); ctx.arc(0, 0, wr * 0.72, 0, Math.PI * 2); ctx.stroke();
    ctx.lineWidth = Math.max(1, wr * 0.038);
    for (let i = 0; i < 12; i += 1) {
      const a = (i / 12) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * wr * 0.14, Math.sin(a) * wr * 0.14);
      ctx.lineTo(Math.cos(a) * wr, Math.sin(a) * wr);
      ctx.stroke();
      /* paddles */
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * wr, Math.sin(a) * wr);
      ctx.lineTo(Math.cos(a + 0.22) * wr * 1.16, Math.sin(a + 0.22) * wr * 1.16);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(226,200,156,0.85)';
    ctx.beginPath(); ctx.arc(0, 0, wr * 0.10, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    /* the wheel's reflection in the water */
    ctx.save();
    ctx.globalAlpha = 0.16;
    ctx.translate(wx, bodyBot * 2 - wy + h * 0.02);
    ctx.scale(1, -1);
    ctx.strokeStyle = 'rgba(214,186,140,0.7)';
    ctx.lineWidth = Math.max(1.2, wr * 0.07);
    ctx.beginPath(); ctx.arc(0, 0, wr, 0, Math.PI * 2); ctx.stroke();
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
  skyline: drawCityscape,
  cityscape: drawCityscape,
  smartphone: drawSmartphone,
  pine: drawPine,
  mill: drawMill,
  paper: drawPaperReam,
  rubber: drawRubberSheet,
  cable: drawCableDrum,
  chip: drawChip,
};
