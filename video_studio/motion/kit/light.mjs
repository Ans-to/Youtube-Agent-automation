/**
 * Light and material.
 *
 * The shapes were flat fills on a white field, which is why the first frames
 * looked like a slide deck: nothing in the picture had been lit. Five passes
 * carry almost all of the difference between "diagram" and "film" -
 *
 *   vignette   the corners fall away, so the eye goes to the centre
 *   bloom      the one bright thing throws a little light around it
 *   grain      a paper tooth that stops gradients from banding at 720p
 *   tone       a warm paper wash and a film curve
 *   focus      depth of field, a real blur at depth
 *
 * All are pure functions of a frame number, so a render is repeatable.
 */

import { createCanvas, DOMMatrix } from '@napi-rs/canvas';

/* -------------------------------------------------------------------------
 * Deterministic noise
 * ---------------------------------------------------------------------- */

/** xorshift: same seed, same sequence. Math.random would flash frame to frame. */
export function noise(seed) {
  let s = (seed * 2654435761) >>> 0;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

let grainTileCache = null;

/**
 * A grain tile, made once and reused.
 *
 * Per-pixel grain on a 1280x720 frame is 921,600 fills and takes longer than
 * drawing the frame. A 256px tile of varying dots, tiled and shifted per frame,
 * is indistinguishable at this grain size and costs one fillRect.
 */
function grainTile(size = 256) {
  if (grainTileCache && grainTileCache.size === size) return grainTileCache;
  const tile = createCanvas(size, size);
  const ctx = tile.getContext('2d');
  const rnd = noise(7);
  for (let i = 0; i < size * 9; i += 1) {
    const x = rnd() * size;
    const y = rnd() * size;
    const a = 0.02 + rnd() * 0.05;
    ctx.fillStyle = rnd() > 0.5 ? `rgba(255,255,255,${a})` : `rgba(18,35,63,${a})`;
    ctx.fillRect(x, y, 1, 1);
  }
  grainTileCache = { size, tile };
  return grainTileCache;
}

/* -------------------------------------------------------------------------
 * Passes
 * ---------------------------------------------------------------------- */

/** Corners fall away. `strength` 0..1; 0.35 is a documentary vignette. */
export function vignette(ctx, W, H, strength = 0.35, colour = '18,35,63') {
  const g = ctx.createRadialGradient(W * 0.5, H * 0.46, Math.min(W, H) * 0.18, W * 0.5, H * 0.5, Math.max(W, H) * 0.74);
  g.addColorStop(0, `rgba(${colour},0)`);
  g.addColorStop(0.65, `rgba(${colour},${strength * 0.28})`);
  g.addColorStop(1, `rgba(${colour},${strength})`);
  ctx.save();
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

/** A light thrown around the one bright thing in frame. */
export function bloom(ctx, W, H, at = [0.5, 0.5], radius = 0.4, strength = 0.14, colour = '180,118,42') {
  const cx = at[0] * W;
  const cy = at[1] * H;
  const r = radius * Math.max(W, H);
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  g.addColorStop(0, `rgba(${colour},${strength})`);
  g.addColorStop(0.45, `rgba(${colour},${strength * 0.32})`);
  g.addColorStop(1, `rgba(${colour},0)`);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.fillStyle = g;
  ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
  ctx.restore();
}

/**
 * Paper tooth. Shifted per frame so it crawls, the way film grain does, rather
 * than sitting still like a dirty screen.
 */
export function grain(ctx, W, H, frameIndex = 0, amount = 1) {
  const { size, tile } = grainTile();
  const rnd = noise(frameIndex + 1);
  const ox = -Math.floor(rnd() * size);
  const oy = -Math.floor(rnd() * size);
  ctx.save();
  ctx.globalAlpha = 0.5 * amount;
  const pattern = ctx.createPattern(tile, 'repeat');
  if (pattern && pattern.setTransform && DOMMatrix) {
    pattern.setTransform(new DOMMatrix().translateSelf(ox, oy));
  }
  ctx.fillStyle = pattern || 'rgba(0,0,0,0)';
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

/**
 * The film curve.
 *
 * A warm paper wash over everything plus a gentle contrast lift: this is what
 * makes five unrelated shots look like they came off the same stock. Applied
 * last, on the whole frame, never per element.
 */
export function tone(ctx, W, H, options = {}) {
  const {
    // A wash is a tint, not a filter. At 0.16 the whole film went sepia and
    // every shot wore the same parchment; the value that reads as "shot on the
    // same stock" without colouring the picture is nearer a tenth of that.
    wash = 'rgba(250,247,240,0.05)',
    lift = 0.02,
    warmth = null,
  } = options;
  ctx.save();
  ctx.fillStyle = wash;
  ctx.fillRect(0, 0, W, H);
  if (warmth) {
    ctx.fillStyle = warmth;
    ctx.fillRect(0, 0, W, H);
  }
  if (lift > 0) {
    // Screen-blend a faint white: lifts the blacks off pure paper so the frame
    // reads as photographed rather than printed.
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = `rgba(255,255,255,${lift})`;
    ctx.fillRect(0, 0, W, H);
  }
  ctx.restore();
}

/**
 * Depth of field, as a real blur.
 *
 * `ctx.filter` exists in this canvas, so this is a genuine gaussian rather than
 * a fake. Draw the layer into an offscreen, blur it, composite back.
 */
export function withFocus(ctx, W, H, blurPx, draw) {
  if (!blurPx || blurPx < 0.2) {
    draw(ctx);
    return;
  }
  const layer = createCanvas(W, H);
  const lctx = layer.getContext('2d');
  draw(lctx);
  ctx.save();
  ctx.filter = `blur(${blurPx.toFixed(2)}px)`;
  ctx.drawImage(layer, 0, 0);
  ctx.restore();
}

/**
 * Everything at once, in the order a real grade happens: material, then light,
 * then grain on top of both.
 */
/* -------------------------------------------------------------------------
 * Print: the dot screen and the paper tooth
 * ---------------------------------------------------------------------- */

let HALFTONE = null;
let TOOTH = null;

/**
 * A dot screen, made once and tiled.
 *
 * Real halftone varies the dot size with the tone underneath, which needs a dot
 * per cell per frame - twenty-five thousand fills on every one of a thousand
 * frames. A fixed screen at low opacity does the job that matters here: it stops
 * the picture looking like vector art on a clean field and starts it looking
 * printed. Cached, because the tile never changes.
 */
function halftoneTile(cell = 5, radius = 1.35) {
  if (HALFTONE && HALFTONE.cell === cell) return HALFTONE.canvas;
  const size = cell * 8;
  const canvas = createCanvas(size, size);
  const c = canvas.getContext('2d');
  c.clearRect(0, 0, size, size);
  c.fillStyle = '#000';
  // A 45 degree screen is the classic print angle: a square grid reads as a mesh.
  for (let y = 0; y < 8; y += 1) {
    for (let x = 0; x < 8; x += 1) {
      const ox = (y % 2) * (cell / 2);
      c.beginPath();
      c.arc(x * cell + ox + cell / 2, y * cell + cell / 2, radius, 0, Math.PI * 2);
      c.fill();
    }
  }
  HALFTONE = { cell, canvas };
  return canvas;
}

function toothTile() {
  if (TOOTH) return TOOTH;
  const size = 192;
  const canvas = createCanvas(size, size);
  const c = canvas.getContext('2d');
  const img = c.createImageData(size, size);
  let seed = 991;
  for (let i = 0; i < size * size; i += 1) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const v = (seed % 255);
    img.data[i * 4] = v;
    img.data[i * 4 + 1] = v;
    img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = 255;
  }
  c.putImageData(img, 0, 0);
  TOOTH = canvas;
  return canvas;
}

/**
 * Put the picture on paper.
 *
 * `screen` is the dot texture, multiplied in so it darkens evenly and the paper
 * still shows through. `tooth` is a soft-light grain on top, which is what makes
 * a flat fill look like ink sitting on a fibre rather than a polygon.
 */
export function riso(ctx, W, H, { screen = 0.10, tooth = 0.10, cell = 5 } = {}) {
  if (screen > 0) {
    ctx.save();
    ctx.globalCompositeOperation = 'multiply';
    ctx.globalAlpha = screen;
    const pattern = ctx.createPattern(halftoneTile(cell), 'repeat');
    ctx.fillStyle = pattern;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
  if (tooth > 0) {
    ctx.save();
    ctx.globalCompositeOperation = 'soft-light';
    ctx.globalAlpha = tooth;
    const pattern = ctx.createPattern(toothTile(), 'repeat');
    ctx.fillStyle = pattern;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
}

export function grade(ctx, W, H, options = {}) {
  const {
    frame = 0,
    vignetteStrength = 0.28,
    grainAmount = 1,
    bloomAt = null,
    bloomStrength = 0.07,
    paper = true,
    lift = 0.02,
    riso: risoScreen = 0.11,
    tooth = 0.10,
    cell = 5,
  } = options;
  if (bloomAt) bloom(ctx, W, H, bloomAt, 0.42, bloomStrength);
  vignette(ctx, W, H, vignetteStrength);
  if (paper) tone(ctx, W, H, { lift });
  grain(ctx, W, H, frame, grainAmount);
  // Last, over the grain: the print is the topmost layer of the material.
  if (risoScreen > 0 || tooth > 0) riso(ctx, W, H, { screen: risoScreen, tooth, cell });
}

export const LIGHT_PASSES = ['vignette', 'bloom', 'grain', 'tone', 'focus'];
