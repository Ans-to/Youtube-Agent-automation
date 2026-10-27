/**
 * Optics: the difference between a drawing and a photograph.
 *
 * The film was clean. Every edge was a hard vector edge, every highlight stopped
 * dead at the colour it was given, and the frame had no light in it beyond what
 * each layer painted. That reads as a diagram, and no amount of extra props
 * fixes it - it is a rendering problem, not a content problem.
 *
 * A camera does four things to a bright scene that a drawing does not:
 *
 *   bloom      light spills out of a highlight into its surroundings
 *   halation   that spill is warmer than the source, because it scatters in the
 *              emulsion and bounces off the back of the film
 *   falloff    the lens dims toward the corners, and the falloff is optical,
 *              not a linear ramp
 *   grain      the image has texture, and the texture moves between frames
 *
 * This module applies all four to a finished frame. The blur is hand-written: the
 * canvas build this studio renders on does not implement `ctx.filter`, so a
 * gaussian posted through the context silently does nothing - which is the same
 * class of bug as the missing fonts, and is why it is measured rather than
 * trusted.
 */
import { createCanvas } from '@napi-rs/canvas';
import { clamp, noise } from '../ui.mjs';

/* --------------------------------------------------------------- blur ---- */

/** One separable box pass over a Float32 RGB buffer. */
function boxPass(src, dst, w, h, r, horizontal) {
  const inv = 1 / (r * 2 + 1);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      let r0 = 0;
      let g0 = 0;
      let b0 = 0;
      for (let k = -r; k <= r; k += 1) {
        const xx = horizontal ? clamp(x + k, 0, w - 1) : x;
        const yy = horizontal ? y : clamp(y + k, 0, h - 1);
        const i = (yy * w + xx) * 3;
        r0 += src[i]; g0 += src[i + 1]; b0 += src[i + 2];
      }
      const o = (y * w + x) * 3;
      dst[o] = r0 * inv; dst[o + 1] = g0 * inv; dst[o + 2] = b0 * inv;
    }
  }
}

/** Three box passes: close enough to a gaussian that the eye cannot tell. */
function blurBuffer(buf, w, h, radius) {
  const tmp = new Float32Array(buf.length);
  let a = buf;
  let b = tmp;
  for (let pass = 0; pass < 3; pass += 1) {
    boxPass(a, b, w, h, Math.max(1, Math.round(radius / 2)), true);
    boxPass(b, a, w, h, Math.max(1, Math.round(radius / 2)), false);
  }
  return a;
}

/* ------------------------------------------------------------ the pass ---- */

let TILE = null;

/** One tile of deterministic grain, re-used for every frame at an offset. */
function grainTile(size = 256) {
  if (TILE) return TILE;
  const c = createCanvas(size, size);
  const x = c.getContext('2d');
  const img = x.createImageData(size, size);
  for (let i = 0; i < size * size; i += 1) {
    const v = 128 + (noise(i * 1.37) - 0.5) * 190;
    img.data[i * 4] = v;
    img.data[i * 4 + 1] = v;
    img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  TILE = c;
  return c;
}

/**
 * Apply the optics to a frame that has already been drawn into `ctx`.
 *
 * @param {CanvasRenderingContext2D} ctx  the frame, finished
 * @param {object} opts
 *   source   a canvas holding the same frame (required for the bright pass)
 *   w, h     frame size
 *   frame    frame index, so grain and dust differ frame to frame
 *   bloom    strength, 0..1 (0 disables)
 *   halation strength, 0..1
 *   grain    strength, 0..1
 *   vignette strength, 0..1
 *   threshold the luminance above which a pixel counts as a highlight
 *   tint     { r, g, b } multipliers applied to the halation
 */
/* ------------------------------------------------------------ buffers ---- */

/**
 * The bright-pass canvases, kept between frames.
 *
 * They used to be created per frame, and a 1080p render died 176 frames in:
 * every `createCanvas` in this build leaves a native allocation that V8 does
 * not account for, so twelve hours of frame buffers became a resident set the
 * OOM reaper collects by killing the process. One set per size, reused.
 */
const BUFFERS = new Map();

function buffers(sw, sh) {
  const key = `${sw}x${sh}`;
  let b = BUFFERS.get(key);
  if (!b) {
    const small = createCanvas(sw, sh);
    const glow = createCanvas(sw, sh);
    const halo = createCanvas(sw, sh);
    const gctx = glow.getContext('2d');
    const hctx = halo.getContext('2d');
    b = {
      small, sctx: small.getContext('2d'),
      glow, gctx, halo, hctx,
      gimg: gctx.createImageData(sw, sh),
      himg: hctx.createImageData(sw, sh),
      buf: new Float32Array(sw * sh * 3),
      wide: new Float32Array(sw * sh * 3),
      warm: new Float32Array(sw * sh * 3),
    };
    BUFFERS.set(key, b);
  }
  return b;
}

export function optics(ctx, {
  source, w, h, frame = 0,
  bloom = 0.5, halation = 0.35, grain = 0.22, vignette = 0.5,
  threshold = 0.62, tint = { r: 1.0, g: 0.72, b: 0.52 },
} = {}) {
  if (bloom > 0 && source) {
    // Bright pass at quarter resolution: a bloom is a low-frequency effect, and
    // paying for it at full resolution is paying for detail nobody can see.
    const sw = Math.max(2, Math.round(w / 4));
    const sh = Math.max(2, Math.round(h / 4));
    const b = buffers(sw, sh);
    const { small, sctx, glow, gctx, halo, hctx } = b;
    sctx.clearRect(0, 0, sw, sh);
    sctx.drawImage(source, 0, 0, sw, sh);

    const px = sctx.getImageData(0, 0, sw, sh).data;
    const buf = b.buf;
    buf.fill(0);
    for (let i = 0, p = 0; i < px.length; i += 4, p += 3) {
      const lum = (0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255;
      // Soft knee: a hard threshold makes bloom pop as objects cross it.
      const k = clamp((lum - threshold) / Math.max(1e-3, 1 - threshold));
      const s = k * k * (3 - 2 * k);
      buf[p] = px[i] * s;
      buf[p + 1] = px[i + 1] * s;
      buf[p + 2] = px[i + 2] * s;
    }

    const wide = blurBuffer(b.wide.set(buf) || b.wide, sw, sh, 9);
    const gimg = b.gimg;
    for (let i = 0, p = 0; i < gimg.data.length; i += 4, p += 3) {
      gimg.data[i] = Math.min(255, wide[p]);
      gimg.data[i + 1] = Math.min(255, wide[p + 1]);
      gimg.data[i + 2] = Math.min(255, wide[p + 2]);
      gimg.data[i + 3] = 255;
    }
    gctx.putImageData(gimg, 0, 0);

    /* halation: the same energy, blurred wider and pushed warm */
    if (halation > 0) {
      const warm = blurBuffer(b.warm.set(buf) || b.warm, sw, sh, 16);
      const himg = b.himg;
      for (let i = 0, p = 0; i < himg.data.length; i += 4, p += 3) {
        himg.data[i] = Math.min(255, warm[p] * tint.r);
        himg.data[i + 1] = Math.min(255, warm[p + 1] * tint.g);
        himg.data[i + 2] = Math.min(255, warm[p + 2] * tint.b);
        himg.data[i + 3] = 255;
      }
      hctx.putImageData(himg, 0, 0);
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = halation * 0.55;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(halo, 0, 0, w, h);
      ctx.restore();
    }

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = bloom * 0.85;
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(glow, 0, 0, w, h);
    ctx.restore();
  }

  /* falloff: an optical vignette follows the square of the radius */
  if (vignette > 0) {
    const cx = w * 0.5;
    const cy = h * 0.48;
    const g = ctx.createRadialGradient(cx, cy, h * 0.16, cx, cy, h * 1.02);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(0.55, `rgba(0,0,0,${0.10 * vignette})`);
    g.addColorStop(0.82, `rgba(0,0,0,${0.34 * vignette})`);
    g.addColorStop(1, `rgba(0,0,0,${0.62 * vignette})`);
    ctx.save();
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
  }

  /* grain: overlaid, not added, so it lives in the mid-tones and leaves black
     alone - which is what film grain does */
  if (grain > 0) {
    const tile = grainTile();
    const ox = Math.floor(noise(frame * 3.17) * 256);
    const oy = Math.floor(noise(frame * 7.31) * 256);
    ctx.save();
    ctx.globalCompositeOperation = 'overlay';
    ctx.globalAlpha = grain * 0.30;
    for (let y = -oy; y < h; y += 256) {
      for (let x = -ox; x < w; x += 256) ctx.drawImage(tile, x, y);
    }
    ctx.restore();
  }
}

/**
 * A frame buffer to grade through, allocated once per renderer.
 * Copying the frame costs one blit; the bright pass needs the finished picture.
 */
export function frameBuffer(w, h) {
  const canvas = createCanvas(w, h);
  return { canvas, ctx: canvas.getContext('2d') };
}

/** How much of this shot's light should bloom. */
export function opticsFor(shot) {
  const o = shot.optics || {};
  return {
    bloom: o.bloom ?? 0.45,
    halation: o.halation ?? 0.30,
    grain: o.grain ?? 0.20,
    vignette: o.vignette ?? 0.35,
    threshold: o.threshold ?? 0.60,
    tint: o.tint || { r: 1.0, g: 0.72, b: 0.52 },
  };
}
