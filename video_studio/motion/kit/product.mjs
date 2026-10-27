/**
 * A drawn 1994 handset, and a room to put it in.
 *
 * The kit's `phone-classic` shape is a rounded rectangle with a grid of keys: it
 * reads as an icon, and an icon is what made the film look like a slide deck. A
 * product on screen has to be *modelled* - tapered, shaded across its width,
 * with a recessed display, bevelled keys, a specular band and a contact shadow.
 *
 * Everything here is paths and gradients, so it is resolution independent and
 * costs nothing to license. Angles are in radians; `t` is seconds.
 */
import { roundRect, clamp, lerp, noise } from '../ui.mjs';

/** Brightness scale on a hex colour - a liquid-crystal panel, dimming. */
const scale = (hex, k) => {
  const v = [1, 3, 5].map((i) => Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * k)));
  return `#${v.map((x) => x.toString(16).padStart(2, '0')).join('')}`;
};

/* ------------------------------------------------------------ the body ---- */

/**
 * The silhouette of a 2110: a tall slab that tapers ~6% toward the top, with a
 * short antenna stub standing off the upper-left shoulder.
 */
function bodyPath(ctx, w, h, taper = 0.94) {
  const r = w * 0.16;
  const tw = w * taper;
  const topY = h * 0.055;
  ctx.beginPath();
  ctx.moveTo(w / 2 - tw / 2 + r, topY);
  ctx.lineTo(w / 2 + tw / 2 - r, topY);
  ctx.quadraticCurveTo(w / 2 + tw / 2, topY, w / 2 + tw / 2, topY + r);
  ctx.lineTo(w, h - r * 1.1);
  ctx.quadraticCurveTo(w, h, w - r * 1.1, h);
  ctx.lineTo(r * 1.1, h);
  ctx.quadraticCurveTo(0, h, 0, h - r * 1.1);
  ctx.lineTo(w / 2 - tw / 2, topY + r);
  ctx.quadraticCurveTo(w / 2 - tw / 2, topY, w / 2 - tw / 2 + r, topY);
  ctx.closePath();
}

/**
 * Draw the handset. Origin is the top-left of its bounding box.
 *
 *   facing  0 = straight on, +/-1 = turned hard left/right. Used to shift the
 *           specular band and squeeze the far edge, which is enough to sell a
 *           slow turn without a 3D pipeline.
 *   glow    strength of the display's spill onto the body.
 */
export function drawHandset(ctx, {
  x = 0, y = 0, w = 200, h = 420,
  facing = 0,
  rotate = 0,
  screen = 'menu',
  glow = 1,
  shadow = true,
  antenna = true,
  body = ['#4A4E55', '#191B1F', '#33363C'],
  keyInk = 'rgba(226,224,214,0.82)',
  bezel = '#0D0E10',
  lcd = '#8FA88A',
} = {}) {
  const H = h;
  const W = w;
  ctx.save();
  ctx.translate(x + W / 2, y + H / 2);
  if (rotate) ctx.rotate(rotate);
  ctx.translate(-W / 2, -H / 2);

  /* contact shadow: two passes, tight and wide, so it sits on a surface */
  if (shadow) {
    ctx.save();
    const g = ctx.createRadialGradient(W * 0.5, H * 1.01, 0, W * 0.5, H * 1.01, W * 0.95);
    g.addColorStop(0, 'rgba(0,0,0,0.55)');
    g.addColorStop(0.55, 'rgba(0,0,0,0.20)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(W * 0.5, H * 1.005, W * 0.78, H * 0.045, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  /* External antenna stub; later models such as the 3210 used an internal one. */
  if (antenna) {
    ctx.save();
    ctx.fillStyle = body[1];
    roundRect(ctx, W * 0.175, H * -0.020, W * 0.115, H * 0.115, W * 0.045);
    ctx.fill();
    const ag = ctx.createLinearGradient(W * 0.175, 0, W * 0.29, 0);
    ag.addColorStop(0, 'rgba(255,255,255,0.20)');
    ag.addColorStop(0.5, 'rgba(255,255,255,0.03)');
    ag.addColorStop(1, 'rgba(0,0,0,0.45)');
    ctx.fillStyle = ag;
    roundRect(ctx, W * 0.175, H * -0.020, W * 0.115, H * 0.115, W * 0.045);
    ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    roundRect(ctx, W * 0.178, H * -0.022, W * 0.109, H * 0.018, W * 0.04);
    ctx.fill();
    ctx.restore();
  }

  /* the slab: shaded across its width to imply a curved surface */
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.5)';
  ctx.shadowBlur = W * 0.16;
  ctx.shadowOffsetY = H * 0.012;
  const face = ctx.createLinearGradient(W * (0.10 + facing * 0.10), 0, W * (0.92 + facing * 0.06), 0);
  face.addColorStop(0, body[0]);
  face.addColorStop(0.16, body[2]);
  face.addColorStop(0.42, body[1]);
  face.addColorStop(0.72, body[2]);
  face.addColorStop(1, body[1]);
  ctx.fillStyle = face;
  bodyPath(ctx, W, H);
  ctx.fill();
  ctx.restore();

  /* specular band: a narrow bright streak that slides with `facing` */
  ctx.save();
  bodyPath(ctx, W, H);
  ctx.clip();
  const sx = W * (0.30 + facing * 0.22);
  const sg = ctx.createLinearGradient(sx - W * 0.14, 0, sx + W * 0.20, 0);
  sg.addColorStop(0, 'rgba(255,255,255,0)');
  sg.addColorStop(0.42, 'rgba(255,255,255,0.17)');
  sg.addColorStop(0.56, 'rgba(255,255,255,0.05)');
  sg.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = sg;
  ctx.fillRect(0, 0, W, H);

  /* right edge falls off into shadow, left edge catches a rim of light */
  const rim = ctx.createLinearGradient(W * 0.72, 0, W, 0);
  rim.addColorStop(0, 'rgba(0,0,0,0)');
  rim.addColorStop(1, 'rgba(0,0,0,0.55)');
  ctx.fillStyle = rim;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.lineWidth = Math.max(1, W * 0.008);
  bodyPath(ctx, W, H);
  ctx.stroke();

  /* earpiece: a slot, not a line */
  ctx.fillStyle = bezel;
  roundRect(ctx, W * 0.34, H * 0.085, W * 0.32, H * 0.012, H * 0.006);
  ctx.fill();
  /* brand plate */
  ctx.fillStyle = 'rgba(255,255,255,0.30)';
  roundRect(ctx, W * 0.40, H * 0.115, W * 0.20, H * 0.008, H * 0.004);
  ctx.fill();
  ctx.restore();

  /* ------------------------------------------------------------ display -- */
  const dx = W * 0.155;
  const dy = H * 0.155;
  const dw = W * 0.69;
  const dh = H * 0.235;
  ctx.save();
  /* recess: dark inner shadow all round */
  ctx.fillStyle = bezel;
  roundRect(ctx, dx - W * 0.045, dy - H * 0.014, dw + W * 0.09, dh + H * 0.028, W * 0.045);
  ctx.fill();

  // The panel's gradient is built *from* `lcd`, so a caller can take the screen
  // dark - it was three hard-coded greens and the panel stayed lit no matter what
  // colour was asked for.
  const lg = ctx.createLinearGradient(0, dy, 0, dy + dh);
  lg.addColorStop(0, scale(lcd, 0.78));
  lg.addColorStop(0.18, lcd);
  lg.addColorStop(1, scale(lcd, 1.14));
  ctx.fillStyle = lg;
  roundRect(ctx, dx, dy, dw, dh, W * 0.02);
  ctx.fill();

  /* what is on the screen */
  ctx.save();
  roundRect(ctx, dx, dy, dw, dh, W * 0.02);
  ctx.clip();
  ctx.fillStyle = 'rgba(18,26,18,0.88)';
  const px = dx + dw * 0.07;
  const py = dy + dh * 0.20;
  const cell = Math.max(1.5, W * 0.022);
  if (screen === 'menu') {
    ctx.font = `700 ${cell * 2.1}px "Inter", sans-serif`;
    ctx.fillText('MENU', px, py + cell * 2);
    ctx.fillText('1 Calls', px, py + cell * 5.2);
    ctx.fillText('2 Messages', px, py + cell * 8.2);
    /* signal bars, rising */
    for (let i = 0; i < 5; i += 1) {
      ctx.fillRect(dx + dw * 0.80 - i * cell * 1.35, py + cell * 2.2 - i * cell * 0.55, cell * 0.85, cell * (0.8 + i * 0.55));
    }
  } else if (screen === 'ring') {
    /* an incoming call: the name, and a wave that moves */
    ctx.font = `700 ${cell * 2.0}px "Inter", sans-serif`;
    ctx.fillText('CALLING...', px, py + cell * 2.4);
    ctx.beginPath();
    for (let i = 0; i <= dw * 0.8; i += 1) {
      const tt = i / (dw * 0.8);
      const yy = py + cell * 6 + Math.sin(tt * 14 + (glow > 0 ? Date.now() * 0 : 0)) * cell * 1.1 * Math.sin(tt * Math.PI);
      if (i === 0) ctx.moveTo(px + i, yy); else ctx.lineTo(px + i, yy);
    }
    ctx.lineWidth = Math.max(1, cell * 0.4);
    ctx.strokeStyle = 'rgba(18,26,18,0.88)';
    ctx.stroke();
  }
  ctx.restore();

  /* glass: a hard diagonal reflection, and a soft bloom in the corner */
  ctx.save();
  roundRect(ctx, dx, dy, dw, dh, W * 0.02);
  ctx.clip();
  ctx.fillStyle = 'rgba(255,255,255,0.13)';
  ctx.beginPath();
  ctx.moveTo(dx - W * 0.1, dy + dh);
  ctx.lineTo(dx + dw * 0.52, dy - dh * 0.2);
  ctx.lineTo(dx + dw * 0.74, dy - dh * 0.2);
  ctx.lineTo(dx - W * 0.1, dy + dh * 1.35);
  ctx.closePath();
  ctx.fill();
  if (glow > 0) {
    const b = ctx.createRadialGradient(dx + dw * 0.5, dy + dh * 0.5, 0, dx + dw * 0.5, dy + dh * 0.5, dw * 0.8);
    b.addColorStop(0, `rgba(196,224,168,${0.22 * glow})`);
    b.addColorStop(1, 'rgba(196,224,168,0)');
    ctx.fillStyle = b;
    ctx.fillRect(dx, dy, dw, dh);
  }
  ctx.restore();

  /* spill from the display onto the body below it */
  if (glow > 0) {
    const sp = ctx.createRadialGradient(W * 0.5, dy + dh, 0, W * 0.5, dy + dh, H * 0.30);
    sp.addColorStop(0, `rgba(160,200,150,${0.16 * glow})`);
    sp.addColorStop(1, 'rgba(160,200,150,0)');
    ctx.fillStyle = sp;
    ctx.beginPath();
    ctx.rect(0, dy + dh * 0.6, W, H * 0.40);
    ctx.fill();
  }
  ctx.restore();

  /* ------------------------------------------------------------- keypad -- */
  const kTop = H * 0.455;
  const kBot = H * 0.935;
  const cols = 3;
  const rows = 4;
  const padL = W * 0.135;
  const padW = W * 0.73;
  const kw = padW / cols;
  const kh = (kBot - kTop) / rows;
  // Number on top, letters beneath - the real layout. Drawn as one string they
  // overran the key cap, which is how a model starts looking like a toy.
  const labels = [
    [['1', ''], ['2', 'ABC'], ['3', 'DEF']],
    [['4', 'GHI'], ['5', 'JKL'], ['6', 'MNO']],
    [['7', 'PQRS'], ['8', 'TUV'], ['9', 'WXYZ']],
    [['*', ''], ['0', '+'], ['#', '']],
  ];
  ctx.save();
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const kx = padL + c * kw + kw * 0.09;
      const ky = kTop + r * kh + kh * 0.11;
      const ww = kw * 0.82;
      const hh = kh * 0.72;
      /* key well: the body dips here */
      ctx.fillStyle = 'rgba(0,0,0,0.34)';
      roundRect(ctx, kx + ww * 0.04, ky + hh * 0.10, ww, hh, W * 0.045);
      ctx.fill();
      /* key cap: lighter on top, darker at the base, so it reads as raised */
      const kg = ctx.createLinearGradient(0, ky, 0, ky + hh);
      kg.addColorStop(0, 'rgba(226,224,214,0.30)');
      kg.addColorStop(0.34, 'rgba(150,150,146,0.26)');
      kg.addColorStop(1, 'rgba(52,54,58,0.55)');
      ctx.fillStyle = kg;
      roundRect(ctx, kx, ky, ww, hh, W * 0.040);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.10)';
      ctx.lineWidth = Math.max(1, W * 0.006);
      roundRect(ctx, kx, ky, ww, hh, W * 0.040);
      ctx.stroke();
      /* label: the digit, then the letters under it */
      const [digit, letters] = labels[r][c];
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = keyInk;
      ctx.font = `600 ${W * 0.105}px "Inter", sans-serif`;
      ctx.fillText(digit, kx + ww / 2, ky + hh * (letters ? 0.36 : 0.5));
      if (letters) {
        ctx.font = `600 ${W * 0.040}px "Inter", sans-serif`;
        ctx.fillStyle = 'rgba(226,224,214,0.42)';
        ctx.fillText(letters, kx + ww / 2, ky + hh * 0.735);
      }
    }
  }
  ctx.restore();

  /* seam where the front shell meets the base */
  ctx.save();
  ctx.strokeStyle = 'rgba(0,0,0,0.45)';
  ctx.lineWidth = Math.max(1, W * 0.010);
  ctx.beginPath();
  ctx.moveTo(W * 0.06, H * 0.992);
  ctx.quadraticCurveTo(W * 0.5, H * 1.006, W * 0.94, H * 0.992);
  ctx.stroke();
  ctx.restore();

  ctx.restore();
}

/* --------------------------------------------------------------- a room ---- */

/**
 * A dark studio: a cool-to-black gradient wall, a soft practical light behind
 * the subject, a floor plane, and dust that drifts. Deterministic in `t`.
 */
export function drawStudio(ctx, { w, h, t = 0, horizon = 0.72, warm = '#C9A227', cool = '#0A0D12', intensity = 1 }) {
  const wall = ctx.createLinearGradient(0, 0, 0, h * horizon);
  wall.addColorStop(0, '#05070A');
  wall.addColorStop(1, '#0E1319');
  ctx.fillStyle = wall;
  ctx.fillRect(0, 0, w, h * horizon + 1);

  /* floor */
  const floor = ctx.createLinearGradient(0, h * horizon, 0, h);
  floor.addColorStop(0, '#131820');
  floor.addColorStop(1, '#05070A');
  ctx.fillStyle = floor;
  ctx.fillRect(0, h * horizon, w, h * (1 - horizon));

  /* practical: a lamp behind and above the subject */
  const lx = w * 0.52;
  const ly = h * 0.30;
  const halo = ctx.createRadialGradient(lx, ly, 0, lx, ly, w * 0.55);
  halo.addColorStop(0, `rgba(255,240,214,${0.16 * intensity})`);
  halo.addColorStop(0.25, `rgba(255,214,150,${0.07 * intensity})`);
  halo.addColorStop(1, 'rgba(255,214,150,0)');
  ctx.fillStyle = halo;
  ctx.fillRect(0, 0, w, h);

  /* a shaft of light from the top right, drawn as a soft wedge */
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  /* fade the wedge across its width as well as down it, or its edges read as
     two hard diagonal lines lying on top of the frame */
  const shaft = ctx.createLinearGradient(w * 0.16, 0, w * 0.78, 0);
  shaft.addColorStop(0, 'rgba(214,196,160,0)');
  shaft.addColorStop(0.45, `rgba(222,204,168,${0.075 * intensity})`);
  shaft.addColorStop(0.62, `rgba(222,204,168,${0.060 * intensity})`);
  shaft.addColorStop(1, 'rgba(214,196,160,0)');
  ctx.fillStyle = shaft;
  ctx.beginPath();
  ctx.moveTo(w * 0.54, -h * 0.05);
  ctx.lineTo(w * 0.78, -h * 0.05);
  ctx.lineTo(w * 0.52, h * 0.82);
  ctx.lineTo(w * 0.16, h * 0.82);
  ctx.closePath();
  ctx.fill();
  ctx.restore();

  /* horizon line: one hairline, the width of the frame */
  ctx.save();
  const hr = ctx.createLinearGradient(0, 0, w, 0);
  hr.addColorStop(0, 'rgba(201,162,39,0)');
  hr.addColorStop(0.5, `rgba(201,162,39,${0.30 * intensity})`);
  hr.addColorStop(1, 'rgba(201,162,39,0)');
  ctx.fillStyle = hr;
  ctx.fillRect(0, h * horizon, w, 1);
  ctx.restore();

  /* dust */
  ctx.save();
  for (let i = 0; i < 70; i += 1) {
    const seed = i * 7.13;
    const sx = noise(seed) * w;
    const drift = Math.sin(t * 0.35 + seed) * w * 0.012;
    const rise = ((noise(seed + 1) * h + t * (5 + noise(seed + 2) * 12)) % h);
    const sy = h - rise;
    const a = (0.05 + noise(seed + 3) * 0.16) * intensity;
    ctx.fillStyle = `rgba(232,226,210,${a})`;
    ctx.beginPath();
    ctx.arc(sx + drift, sy, 0.7 + noise(seed + 4) * 1.5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

/**
 * The subject's reflection in the floor.
 *
 * Mirrored about the point where the object meets the ground - `mirrorAt` - not
 * about the horizon. Mirrored about the horizon a standing object reflects at
 * the wrong distance and appears to hover.
 */
export function drawReflection(ctx, drawFn, { h, mirrorAt, alpha = 0.20, fadeTo = 1 }) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, mirrorAt, 4000, h - mirrorAt);
  ctx.clip();
  ctx.globalAlpha *= alpha;
  ctx.translate(0, mirrorAt * 2);
  ctx.scale(1, -1);
  drawFn();
  ctx.restore();
  /* the reflection dies away with distance, as a wet floor does */
  ctx.save();
  const g = ctx.createLinearGradient(0, mirrorAt, 0, h * fadeTo);
  g.addColorStop(0, 'rgba(0,0,0,0.05)');
  g.addColorStop(1, 'rgba(8,10,13,0.92)');
  ctx.fillStyle = g;
  ctx.fillRect(0, mirrorAt, 4000, h * fadeTo - mirrorAt);
  ctx.restore();
}
