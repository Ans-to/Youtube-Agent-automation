/**
 * The motion kit: every way something can arrive, leave, or behave.
 *
 * An entrance is only half of motion design. The other half is what a thing does
 * while it is on screen - a line that draws itself, a column that grows, a shape
 * that breathes - and the moves that take it away. A documentary holds a picture
 * for three seconds; if nothing in it is alive, those three seconds are a slide.
 *
 * Everything here is a *wrapped* draw: you hand it a function that draws the
 * artwork, and it applies the move. That means any shape from the kit, any block
 * of type, any composition at all can be animated by any move without the two
 * knowing about each other.
 *
 * Determinism matters: no Math.random, no Date, no frame counter. A move is a
 * pure function of its progress, so the film renders the same frame twice.
 */
import { UI, clamp, lerp, noise, span, ease } from '../ui.mjs';

const TAU = Math.PI * 2;
const out = (x) => ease.outCubic(clamp(x));
const back = (x) => {
  const t = clamp(x);
  const c = 1.70158;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
};

/** Save, run, restore - balanced even when the drawing throws. */
function wrapped(ctx, draw) {
  ctx.save();
  try {
    draw();
  } finally {
    ctx.restore();
  }
}

function clipped(ctx, x, y, w, h, draw) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, Math.max(1, w), Math.max(1, h));
  ctx.clip();
  try {
    draw();
  } finally {
    ctx.restore();
  }
}

/**
 * Arrivals.
 *
 * Each takes `p` (0 at the first frame of the move, 1 when it has landed) and a
 * `box` describing where the artwork lives. `draw` paints the artwork.
 */
export const ENTRANCES = {
  'draw-on': (ctx, { p, box, accent }, draw) => {
    const edge = box.x + box.w * out(p);
    clipped(ctx, box.x, box.y, edge - box.x, box.h, draw);
    ctx.save();
    ctx.globalAlpha *= 0.55 * (1 - p * 0.4);
    ctx.fillStyle = accent;
    ctx.fillRect(edge - Math.max(2, box.w * 0.0025), box.y + box.h * 0.06,
      Math.max(2, box.w * 0.0025), box.h * 0.88);
    ctx.restore();
  },

  wipe: (ctx, { p, box, accent, direction = 'up' }, draw) => {
    const depth = box.h * ease.inOutCubic(clamp(p));
    const horizontal = direction === 'left' || direction === 'right';
    if (horizontal) {
      const w = box.w * out(p);
      const x = direction === 'left' ? box.x : box.x + box.w - w;
      clipped(ctx, x, box.y, w, box.h, draw);
      return;
    }
    const y = direction === 'down' ? box.y + box.h - depth : box.y;
    clipped(ctx, box.x, y, box.w, depth, draw);
    ctx.save();
    ctx.globalAlpha *= 0.5 * (1 - p);
    ctx.fillStyle = accent;
    ctx.fillRect(box.x, (direction === 'down' ? y : y + depth) - Math.max(2, box.h * 0.006),
      box.w, Math.max(2, box.h * 0.006));
    ctx.restore();
  },

  iris: (ctx, { p, box, accent, centre = null, reach = 0.55 }, draw) => {
    const cx = centre ? centre.x : box.x + box.w / 2;
    const cy = centre ? centre.y : box.y + box.h / 2;
    // `reach` is the reasoning lever: an opening that just clears the artwork
    // and one that sweeps well past it are different arrivals.
    const radius = Math.hypot(box.w, box.h) * reach * out(p);
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(1, radius), 0, TAU);
    ctx.clip();
    wrapped(ctx, draw);
    ctx.restore();
    ctx.save();
    ctx.globalAlpha *= 0.35 * (1 - p);
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, box.h * 0.008);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, TAU);
    ctx.stroke();
    ctx.restore();
  },

  scan: (ctx, { p, box, accent }, draw) => {
    const front = box.y + box.h * out(Math.min(1, p * 1.12));
    const band = Math.max(6, box.h * 0.16);
    clipped(ctx, box.x, box.y, box.w, front - box.y, draw);
    clipped(ctx, box.x, Math.max(box.y, front - band), box.w, band, () => {
      ctx.save();
      ctx.globalAlpha *= 0.72;
      draw();
      ctx.restore();
    });
    ctx.save();
    ctx.globalAlpha *= 0.85;
    ctx.fillStyle = accent;
    ctx.fillRect(box.x, front - Math.max(1.5, box.h * 0.004), box.w, Math.max(1.5, box.h * 0.004));
    ctx.restore();
  },

  'slit-scan': (ctx, { p, box, strips = 8 }, draw) => {
    const stripW = box.w / strips;
    const wave = Math.min(1, p * 2.2);
    for (let i = 0; i < strips; i += 1) {
      const arrive = clamp((wave - (Math.floor(i / 2) / 4) * 0.75) / 0.25);
      if (arrive <= 0) continue;
      const grow = out(arrive);
      const shift = (i % 2 === 0 ? -1 : 1) * box.h * 0.12 * (1 - grow);
      ctx.save();
      ctx.beginPath();
      ctx.rect(box.x + i * stripW, box.y, stripW + 1, box.h);
      ctx.clip();
      ctx.translate(0, shift);
      ctx.globalAlpha *= 0.35 + 0.65 * grow;
      draw();
      ctx.restore();
    }
  },

  whip: (ctx, { p, box, ink }, draw) => {
    const slide = -box.w * 0.5 * (1 - out(p));
    ctx.save();
    ctx.translate(slide, 0);
    for (let i = 1; i <= 3; i += 1) {
      ctx.save();
      ctx.globalAlpha *= (0.18 * (1 - p)) / i;
      ctx.fillStyle = ink;
      ctx.fillRect(box.x - box.w * 0.012 * i, box.y + box.h * 0.12 * i, box.w, Math.max(2, box.h * 0.006));
      ctx.restore();
    }
    wrapped(ctx, draw);
    ctx.restore();
  },

  squash: (ctx, { p, box, amount = 1 }, draw) => {
    const k = back(p);
    ctx.save();
    ctx.translate(box.x + box.w / 2, box.y + box.h);
    ctx.scale(1 - (0.10 * amount) * (1 - k), 1 - (0.06 * amount) * (1 - k));
    ctx.translate(-(box.x + box.w / 2), -(box.y + box.h));
    wrapped(ctx, draw);
    ctx.restore();
  },

  stamp: (ctx, { p, box, accent }, draw) => {
    const s = 1 + 0.22 * (1 - back(p));
    ctx.save();
    ctx.translate(box.x + box.w / 2, box.y + box.h / 2);
    ctx.scale(s, s);
    ctx.translate(-(box.x + box.w / 2), -(box.y + box.h / 2));
    ctx.globalAlpha *= Math.min(1, 0.25 + p * 1.6);
    wrapped(ctx, draw);
    ctx.restore();
    ctx.save();
    ctx.globalAlpha *= 0.30 * (1 - p);
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, box.h * 0.01);
    ctx.strokeRect(box.x - box.h * 0.03 * p, box.y - box.h * 0.03 * p,
      box.w + box.h * 0.06 * p, box.h + box.h * 0.06 * p);
    ctx.restore();
  },

  assembly: (ctx, { p, box, accent }, draw) => {
    const slide = (1 - out(p)) * box.w * 0.10;
    clipped(ctx, box.x, box.y, box.w / 2 + 1, box.h, () => {
      ctx.save();
      ctx.translate(-slide, 0);
      draw();
      ctx.restore();
    });
    clipped(ctx, box.x + box.w / 2, box.y, box.w / 2 + 1, box.h, () => {
      ctx.save();
      ctx.translate(slide, 0);
      draw();
      ctx.restore();
    });
    if (p > 0.55) {
      ctx.save();
      ctx.globalAlpha *= (0.5 * (1 - p)) / 0.45;
      ctx.fillStyle = accent;
      ctx.fillRect(box.x + box.w / 2 - Math.max(1.5, box.w * 0.003), box.y, Math.max(3, box.w * 0.006), box.h);
      ctx.restore();
    }
  },

  /** A mask shaped like something else: type revealed through a circle, a wedge,
   *  a band. Used for a cut that is part of the sentence rather than decoration. */
  'shape-mask': (ctx, { p, box, shape = 'circle' }, draw) => {
    const k = out(p);
    ctx.save();
    ctx.beginPath();
    if (shape === 'circle') {
      ctx.arc(box.x + box.w / 2, box.y + box.h / 2, Math.hypot(box.w, box.h) * 0.55 * k, 0, TAU);
    } else if (shape === 'wedge') {
      const cx = box.x;
      const cy = box.y + box.h;
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, Math.hypot(box.w, box.h) * 1.1 * k, -Math.PI / 2, 0);
      ctx.closePath();
    } else {
      // A horizontal band that grows from the centre out.
      const h = box.h * k;
      ctx.rect(box.x, box.y + (box.h - h) / 2, box.w, h);
    }
    ctx.clip();
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Rise from below with a soft fade: the calmest arrival, for reflection. */
  rise: (ctx, { p, box, distance = 0.16 }, draw) => {
    ctx.save();
    ctx.globalAlpha *= clamp(p * 1.4);
    ctx.translate(0, (1 - out(p)) * box.h * distance);
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Fragments: the artwork appears as shards that settle into place. */
  shatter: (ctx, { p, box, cols = 5, rows = 3 }, draw) => {
    const cw = box.w / cols;
    const ch = box.h / rows;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const seed = noise(r * 11.3 + c * 4.7);
        const order = (r * cols + c) / (cols * rows);
        const arrive = clamp((p - order * 0.45) / 0.55);
        if (arrive <= 0) continue;
        const k = out(arrive);
        const dx = (1 - k) * cw * (seed - 0.5) * 2.4;
        const dy = (1 - k) * ch * (seed - 0.5) * 2.4;
        ctx.save();
        ctx.beginPath();
        ctx.rect(box.x + c * cw, box.y + r * ch, cw + 0.5, ch + 0.5);
        ctx.clip();
        ctx.globalAlpha *= 0.35 + 0.65 * k;
        ctx.translate(dx, dy);
        draw();
        ctx.restore();
      }
    }
  },
};

/**
 * Behaviours: what a thing does while it is on screen.
 *
 * These are not entrances - they run for the whole shot. `t` is the shot's own
 * clock and `seconds` its length, so a behaviour can pace itself to the beat
 * rather than to an arbitrary loop.
 */
export const BEHAVIOURS = {
  /** A slow, single-direction push. A camera move, never a shake. */
  push: (ctx, { t, seconds, box, amount = 0.06 }, draw) => {
    const k = 1 + amount * clamp(t / Math.max(0.001, seconds));
    ctx.save();
    ctx.translate(box.x + box.w / 2, box.y + box.h / 2);
    ctx.scale(k, k);
    ctx.translate(-(box.x + box.w / 2), -(box.y + box.h / 2));
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Drift: a very small lateral float. Gives a held diagram air without shake. */
  drift: (ctx, { t, seconds, box, amount = 0.012 }, draw) => {
    const phase = (t / Math.max(0.001, seconds)) * Math.PI;
    ctx.save();
    ctx.translate(Math.sin(phase) * box.w * amount, 0);
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Parallax: layers move at different rates as the shot progresses. */
  parallax: (ctx, { t, seconds, box, depth = 0.3, amount = 0.04 }, draw) => {
    const k = clamp(t / Math.max(0.001, seconds));
    ctx.save();
    ctx.translate(-box.w * amount * depth * k, -box.h * amount * 0.4 * depth * k);
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Breathe: a scale pulse of a couple of percent, on a slow cycle. */
  breathe: (ctx, { t, box, rate = 0.35, amount = 0.02 }, draw) => {
    const k = 1 + Math.sin(t * rate * TAU) * amount;
    ctx.save();
    ctx.translate(box.x + box.w / 2, box.y + box.h / 2);
    ctx.scale(k, k);
    ctx.translate(-(box.x + box.w / 2), -(box.y + box.h / 2));
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** Pulse: opacity throb, for a live indicator or a heartbeat. */
  pulse: (ctx, { t, rate = 1.1, amount = 0.25 }, draw) => {
    ctx.save();
    ctx.globalAlpha *= 1 - amount + Math.abs(Math.sin(t * rate * Math.PI)) * amount;
    wrapped(ctx, draw);
    ctx.restore();
  },

  /** A light sweep across the artwork: the glint that says "premium". */
  'light-sweep': (ctx, { t, seconds, box, colour = '#FFFFFF', width = 0.22 }, draw) => {
    wrapped(ctx, draw);
    const k = clamp(t / Math.max(0.001, seconds));
    const bandW = box.w * width;
    const x = box.x - bandW + (box.w + bandW * 2) * ease.inOutCubic(k);
    ctx.save();
    ctx.beginPath();
    ctx.rect(box.x, box.y, box.w, box.h);
    ctx.clip();
    const grad = ctx.createLinearGradient(x, 0, x + bandW, 0);
    grad.addColorStop(0, 'rgba(255,255,255,0)');
    grad.addColorStop(0.5, colour === '#FFFFFF' ? 'rgba(255,255,255,0.30)' : colour);
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = grad;
    ctx.fillRect(x, box.y, bandW, box.h);
    ctx.restore();
  },

  /** Shimmer: a horizontal band of texture that slides, like foil. */
  shimmer: (ctx, { t, box, accent }, draw) => {
    wrapped(ctx, draw);
    ctx.save();
    ctx.beginPath();
    ctx.rect(box.x, box.y, box.w, box.h);
    ctx.clip();
    ctx.globalAlpha *= 0.10;
    ctx.fillStyle = accent;
    for (let i = 0; i < 5; i += 1) {
      const x = box.x + ((t * 0.16 + i * 0.2) % 1) * box.w;
      ctx.fillRect(x, box.y, box.w * 0.06, box.h);
    }
    ctx.restore();
  },

  /** Threshold: the artwork resolves out of noise, like a print developing. */
  develop: (ctx, { t, seconds, box, seed = 1 }, draw) => {
    const k = clamp(t / Math.max(0.001, seconds));
    const bands = 14;
    for (let i = 0; i < bands; i += 1) {
      const order = noise(i * 3.7 + seed);
      const arrive = clamp((k - order * 0.7) / 0.3);
      if (arrive <= 0) continue;
      ctx.save();
      ctx.beginPath();
      ctx.rect(box.x, box.y + (box.h / bands) * i, box.w, box.h / bands + 0.5);
      ctx.clip();
      ctx.globalAlpha *= arrive;
      draw();
      ctx.restore();
    }
  },
};

/**
 * Departures. A shot that ends by vanishing is a shot that ended by default;
 * these let the leaving be part of the sentence.
 */
export const EXITS = {
  fade: (ctx, { p, draw }) => {
    ctx.save();
    ctx.globalAlpha *= 1 - clamp(p);
    wrapped(ctx, draw);
    ctx.restore();
  },

  'push-out': (ctx, { p, box, draw }) => {
    const k = 1 + 0.10 * ease.inCubic(clamp(p));
    ctx.save();
    ctx.globalAlpha *= 1 - clamp(p);
    ctx.translate(box.x + box.w / 2, box.y + box.h / 2);
    ctx.scale(k, k);
    ctx.translate(-(box.x + box.w / 2), -(box.y + box.h / 2));
    wrapped(ctx, draw);
    ctx.restore();
  },

  wipe: (ctx, { p, box, direction = 'up', draw }) => {
    const k = out(p);
    ctx.save();
    if (direction === 'up') {
      ctx.beginPath();
      ctx.rect(box.x, box.y + box.h * k, box.w, box.h * (1 - k) + 1);
    } else {
      ctx.beginPath();
      ctx.rect(box.x, box.y, box.w, box.h * (1 - k));
    }
    ctx.clip();
    wrapped(ctx, draw);
    ctx.restore();
  },

  dissolve: (ctx, { p, box, draw, seed = 2 }) => {
    const bands = 16;
    for (let i = 0; i < bands; i += 1) {
      const order = noise(i * 5.1 + seed);
      const gone = clamp((clamp(p) - order * 0.6) / 0.4);
      if (gone >= 1) continue;
      ctx.save();
      ctx.beginPath();
      ctx.rect(box.x, box.y + (box.h / bands) * i, box.w, box.h / bands + 0.5);
      ctx.clip();
      ctx.globalAlpha *= 1 - gone;
      draw();
      ctx.restore();
    }
  },

  'slide-away': (ctx, { p, box, direction = 'left', draw }) => {
    const k = ease.inCubic(clamp(p));
    ctx.save();
    ctx.globalAlpha *= 1 - k;
    ctx.translate(direction === 'left' ? -box.w * 0.35 * k : box.w * 0.35 * k, 0);
    wrapped(ctx, draw);
    ctx.restore();
  },
};

export const MOTION = { ENTRANCES, BEHAVIOURS, EXITS };

export function applyEntrance(ctx, kind, options, draw) {
  const fn = ENTRANCES[kind] || ENTRANCES['draw-on'];
  if (options.p >= 1) {
    wrapped(ctx, draw);
    return;
  }
  if (options.p <= 0) return;
  fn(ctx, options, draw);
}

export function applyBehaviour(ctx, kind, options, draw) {
  const fn = BEHAVIOURS[kind];
  if (!fn) {
    wrapped(ctx, draw);
    return;
  }
  fn(ctx, options, draw);
}

export function applyExit(ctx, kind, options, draw) {
  const fn = EXITS[kind];
  if (!fn || options.p <= 0) {
    wrapped(ctx, draw);
    return;
  }
  // The exit moves take their artwork in the options object rather than as a
  // second argument, because each one uses it in a different place (inside a
  // clip, inside a transform, twice). Injecting it here keeps that signature
  // honest and keeps the caller from having to remember which family it is.
  fn(ctx, { ...options, draw });
}

export { lerp, span };
export default MOTION;
