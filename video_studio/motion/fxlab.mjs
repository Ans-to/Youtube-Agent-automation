/**
 * How a picture arrives.
 *
 * Everything else in this studio answers *what* is drawn: a fork, a dial, a rail,
 * a grid. This file answers *how it lands*, and it exists because the owner's
 * rejection was not about layout at all - "it still uses the same generic typing
 * and no new motion graphics". The pictures were different; the arrival was
 * identical, every act, every film, so ten films felt like one film.
 *
 * The moves are ports of the motion basics in `howardc38/motion-fx-lab` (0BSD):
 * stroke reveals, clip wipes, iris openings, slit-scan type, press and squash,
 * exploded assembly. What transfers is the *idea* of each, not its pixels - our
 * renderer is Canvas 2D in Node, not a browser.
 *
 * Two rules hold here, because the film gates measure them:
 *
 *   - an entrance withholds the picture while it runs. A test draws the same
 *     artwork with the entrance at 20 % and counts ink: a move that shows the
 *     finished drawing and then animates a border is decoration, not an entrance.
 *   - an entrance has to suit the picture. A highlighter band through a ring
 *     gauge crosses the number; a stamp on a timeline implies a verdict. `FITS`
 *     is that constraint, and the chooser never leaves it.
 */

/** Every entrance this build knows. Order is the fallback preference. */
export const ENTRANCES = [
  'draw-on', 'wipe', 'iris', 'scan', 'highlighter',
  'slit-scan', 'whip', 'squash', 'stamp', 'assembly',
];

/**
 * Which entrances a template can carry.
 *
 * Read as "this picture, arriving this way, is still the same picture". A dial
 * can be drawn on, opened by an iris or scanned; a highlighter stroke across it
 * would mark the ring like a correction. A comparison can be assembled from two
 * halves because it *is* two halves; a list cannot, because a list arrives a row
 * at a time.
 */
export const FITS = {
  'kinetic-headline': ['highlighter', 'whip', 'slit-scan', 'draw-on', 'wipe'],
  'stamp-lockup': ['stamp', 'squash', 'iris', 'wipe'],
  'count-up': ['scan', 'squash', 'stamp', 'draw-on'],
  'ring-gauge': ['draw-on', 'iris', 'scan'],
  'bar-compare': ['draw-on', 'wipe', 'scan'],
  'compare-pair': ['assembly', 'wipe'],
  'fork-paths': ['assembly', 'draw-on', 'iris'],
  'list-build': ['slit-scan', 'assembly', 'wipe', 'scan'],
  'stack-push': ['slit-scan', 'assembly', 'wipe'],
  'matrix-grid': ['assembly', 'slit-scan', 'scan', 'stamp'],
  'budget-rail': ['draw-on', 'wipe', 'scan'],
  'command-console': ['scan', 'draw-on', 'wipe'],
  'code-typing': ['scan', 'draw-on'],
  'sweep-rule': ['squash', 'wipe'],
  'dot-gauge': ['draw-on', 'stamp', 'scan', 'squash'],
  'timeline-rail': ['draw-on', 'wipe', 'scan'],
  'overlap-pair': ['assembly', 'iris', 'draw-on'],
  'exploded-stack': ['assembly', 'draw-on', 'scan'],
};

/**
 * The entrance families that suit a kind of beat, before the picture has a say.
 *
 * A claim is set as type, so it can be struck through with a marker or snapped
 * in strips. A number is scanned or counted. A comparison is assembled from its
 * halves. A sequence arrives in order. A verdict is pressed on.
 */
const BY_SITUATION = {
  'opening-claim': ['draw-on', 'whip', 'slit-scan', 'highlighter'],
  'name-the-thing': ['scan', 'draw-on', 'stamp'],
  'state-the-thesis': ['assembly', 'draw-on', 'iris'],
  'punchline': ['stamp', 'squash', 'iris'],
  'explain-a-number': ['draw-on', 'scan', 'iris', 'squash'],
  'show-a-sequence': ['wipe', 'slit-scan', 'draw-on', 'scan'],
  'show-criteria': ['slit-scan', 'assembly', 'wipe', 'stamp'],
  'make-a-comparison': ['assembly', 'wipe', 'iris'],
  'before-and-after': ['assembly', 'wipe', 'iris'],
  'show-the-mechanism': ['draw-on', 'wipe', 'scan', 'assembly'],
  'show-the-command': ['scan', 'draw-on'],
  'build-an-argument': ['slit-scan', 'assembly', 'wipe'],
  'recap': ['slit-scan', 'wipe', 'draw-on'],
  'hold-a-beat': ['squash', 'wipe'],
  'punctuation': ['squash', 'wipe'],
};

/** How long an entrance takes. Long enough to read as a move, short enough that
 *  the picture is on screen for most of its beat. */
export const ENTRANCE_SECONDS = 0.56;

const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);

/** A stable 0..1 from a string: FNV-1a, then a fractional tail. */
export function seedOf(text) {
  let hash = 0x811c9dc5;
  const value = String(text);
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return (hash % 100000) / 100000;
}

/**
 * Pick the entrance for one act.
 *
 * `previous` is the film's own history, most recent first. Three passes, in
 * order of preference: a move this film has not used at all, a move it has not
 * used in its last two acts, and finally anything that fits. The seed only
 * breaks ties, so two films with the same situation still open differently.
 */
export function chooseEntrance(situation, previous = [], seedText = '', template = null) {
  const fits = FITS[template] || ENTRANCES;
  const shortlist = BY_SITUATION[situation] || ENTRANCES;
  const allowed = shortlist.filter((kind) => fits.includes(kind));
  let base = allowed.length ? allowed : fits.filter((kind) => shortlist.includes(kind));
  if (!base.length) base = fits;
  const unused = base.filter((kind) => !previous.includes(kind));
  const fresh = base.filter((kind) => !previous.slice(0, 2).includes(kind));
  const seed = seedOf(`${situation}:${seedText}:${template || ''}`);
  const pick = (pool) => {
    if (!pool.length) return null;
    const index = Math.floor(seed * pool.length + 1e-9) % pool.length;
    return pool[index];
  };
  // A film's last act is never allowed to repeat the act before it; when the
  // pool has nothing else left, the pool wins over the rule, and the widening is
  // explicit rather than silent.
  const noRepeat = fresh.filter((kind) => kind !== previous[0]);
  return pick(noRepeat) || pick(unused) || pick(fresh) || pick(base)
    || base.find((kind) => kind !== previous[0]) || fits[0];
}

/** Save, run, restore - balanced even when the drawing throws. */
function clipped(ctx, region, draw) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(region.x, region.y, region.w, region.h);
  ctx.clip();
  try {
    draw();
  } finally {
    ctx.restore();
  }
}

function irisClip(ctx, cx, cy, radius, draw) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(1, radius), 0, Math.PI * 2);
  ctx.clip();
  try {
    draw();
  } finally {
    ctx.restore();
  }
}

const easeOut = (x) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
const easeInOut = (x) => {
  const t = Math.min(1, Math.max(0, x));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};
/** Overshoot, for a move that lands rather than glides. */
const backOut = (x) => {
  const t = Math.min(1, Math.max(0, x));
  const c = 1.70158;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
};

/**
 * Draw `artwork` as an entrance.
 *
 * `p` is progress, 0 at the first frame of the move and 1 when it has landed.
 * `box` is where the artwork lives, in the current user space; `ink` and `accent`
 * are colours the move may use for its own marks (a pen line, a marker band, a
 * motion trail). Everything is drawn inside save/restore, so a caller can wrap a
 * template and not worry about leaked clip or alpha - the film asserts on that.
 */
export function applyEntrance(ctx, {
  kind = 'draw-on', p = 1, box, accent = '#B4762A', ink = '#12233F', seed = 0.5,
}, draw) {
  const t = Math.min(1, Math.max(0, p));
  const x = box.x;
  const y = box.y;
  const w = box.w;
  const h = box.h;
  const cx = x + w / 2;
  const cy = y + h / 2;
  // Before the move starts, nothing of it has landed; at 1 it is simply drawn.
  if (t >= 1) {
    draw();
    return;
  }

  if (kind === 'draw-on') {
    // A pen draws the picture in from one side, with the nib visible at the edge.
    const edge = x + w * easeOut(t);
    clipped(ctx, { x, y, w: Math.max(1, edge - x), h }, draw);
    ctx.save();
    ctx.globalAlpha = 0.55 * (1 - t * 0.4);
    ctx.fillStyle = accent;
    ctx.fillRect(edge - Math.max(2, w * 0.0025), y + h * 0.06,
      Math.max(2, w * 0.0025), h * 0.88);
    ctx.restore();
    return;
  }

  if (kind === 'wipe') {
    // A hard horizontal reveal: no soft edge anywhere, so it reads as a board
    // being uncovered rather than a fade.
    const depth = h * easeInOut(t);
    clipped(ctx, { x, y, w, h: Math.max(1, depth) }, draw);
    ctx.save();
    ctx.globalAlpha = 0.5 * (1 - t);
    ctx.fillStyle = accent;
    ctx.fillRect(x, y + depth - Math.max(2, h * 0.006), w, Math.max(2, h * 0.006));
    ctx.restore();
    return;
  }

  if (kind === 'iris') {
    const radius = Math.max(w, h) * 0.62 * easeOut(t);
    irisClip(ctx, cx, cy, radius, draw);
    ctx.save();
    ctx.globalAlpha = 0.35 * (1 - t);
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, h * 0.008);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    return;
  }

  if (kind === 'scan') {
    // The passed area is fully drawn; a narrow band crosses the rest. The band
    // carries no light of its own - a glowing full-height band reads as a smudge
    // across the frame rather than as a scanner.
    const front = y + h * easeOut(Math.min(1, t * 1.12));
    const band = Math.max(6, h * 0.16);
    clipped(ctx, { x, y, w, h: Math.max(1, front - y) }, draw);
    clipped(ctx, { x, y: Math.max(y, front - band), w, h: band }, () => {
      ctx.save();
      ctx.globalAlpha = 0.72;
      draw();
      ctx.restore();
    });
    ctx.save();
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = accent;
    ctx.fillRect(x, front - Math.max(1.5, h * 0.004), w, Math.max(1.5, h * 0.004));
    ctx.restore();
    return;
  }

  if (kind === 'highlighter') {
    // A marker stroke *behind* the words, not over them: the band is drawn first,
    // the type sits on it, and the stroke stops where the line stops. A
    // full-width band over a dial or a chart is vandalism, which is why this move
    // is only offered for type-led pictures.
    const midY = y + h * 0.44;
    const bandH = Math.max(10, h * 0.15);
    const bandW = w * 0.62 * easeOut(t);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.34;
    ctx.fillStyle = accent;
    ctx.fillRect(x + w * 0.06, midY - bandH * 0.5, bandW, bandH);
    ctx.globalAlpha = ctx.globalAlpha * 0.9;
    ctx.fillRect(x + w * 0.06 + bandW, midY - bandH * 0.5,
      Math.max(3, w * 0.005), bandH);
    ctx.restore();
    draw();
    return;
  }

  if (kind === 'slit-scan') {
    // Vertical strips that snap into place. All eight start together on purpose:
    // per-strip delays tore the frame for half a second, which reads as a broken
    // encode, not as a move.
    // Four waves of two columns. The columns of a wave start together - per-strip
    // delays tore the frame for half a second and read as a broken encode - but
    // the waves are late enough that the picture is genuinely incomplete while
    // the move runs.
    const strips = 8;
    const stripW = w / strips;
    const wave = Math.min(1, t * 2.2);         // all eight landed by ~45 % of the move
    for (let i = 0; i < strips; i += 1) {
      const arrive = clamp((wave - (Math.floor(i / 2) / 4) * 0.75) / 0.25);
      if (arrive <= 0) continue;
      const grow = easeOut(arrive);
      const shift = (i % 2 === 0 ? -1 : 1) * h * 0.12 * (1 - grow);
      const sx = x + i * stripW;
      ctx.save();
      ctx.beginPath();
      ctx.rect(sx, y, stripW + 1, h);
      ctx.clip();
      ctx.translate(0, shift);
      ctx.globalAlpha = ctx.globalAlpha * (0.35 + 0.65 * grow);
      draw();
      ctx.restore();
    }
    return;
  }

  if (kind === 'whip') {
    // The picture slides in with a short trail behind it. The trail is three
    // hairlines, not a copy of the artwork: an echo of a diagram is noise.
    const slide = -w * 0.5 * (1 - easeOut(t));
    ctx.save();
    ctx.translate(slide, 0);
    for (let i = 1; i <= 3; i += 1) {
      ctx.save();
      ctx.globalAlpha = 0.18 * (1 - t) / i;
      ctx.fillStyle = ink;
      ctx.fillRect(x - w * 0.012 * i, y + h * 0.12 * i, w, Math.max(2, h * 0.006));
      ctx.restore();
    }
    draw();
    ctx.restore();
    return;
  }

  if (kind === 'squash') {
    // Lands with squash and stretch: wide and short on contact, then settles.
    const k = backOut(t);
    const sx = 0.90 + 0.10 * k;
    const sy = 0.94 + 0.06 * k;
    ctx.save();
    ctx.translate(cx, y + h);
    ctx.scale(sx, sy);
    ctx.translate(-cx, -(y + h));
    draw();
    ctx.restore();
    return;
  }

  if (kind === 'stamp') {
    // Pressed on: arrives large, overshoots past its size, settles. The ring is
    // one echo, fading, so the press has weight without a rippling target.
    const s = 1 + 0.22 * (1 - backOut(t));
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(s, s);
    ctx.translate(-cx, -cy);
    ctx.globalAlpha = ctx.globalAlpha * Math.min(1, 0.25 + t * 1.6);
    draw();
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = 0.30 * (1 - t);
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, h * 0.01);
    ctx.strokeRect(x - h * 0.03 * t, y - h * 0.03 * t,
      w + h * 0.06 * t, h + h * 0.06 * t);
    ctx.restore();
    return;
  }

  if (kind === 'assembly') {
    // Two halves arrive from opposite sides and meet. Each half is drawn once,
    // inside a clip, translated by its own slide: the halves are not re-drawn
    // twice at different offsets, which is what doubled the artwork in the first
    // version of this move.
    const slide = (1 - easeOut(t)) * w * 0.10;
    clipped(ctx, { x, y, w: w / 2 + 1, h }, () => {
      ctx.save();
      ctx.translate(-slide, 0);
      draw();
      ctx.restore();
    });
    clipped(ctx, { x: x + w / 2, y, w: w / 2 + 1, h }, () => {
      ctx.save();
      ctx.translate(slide, 0);
      draw();
      ctx.restore();
    });
    if (t > 0.55) {
      ctx.save();
      ctx.globalAlpha = 0.5 * (1 - t) / 0.45;
      ctx.fillStyle = accent;
      ctx.fillRect(cx - Math.max(1.5, w * 0.003), y, Math.max(3, w * 0.006), h);
      ctx.restore();
    }
    return;
  }

  // Unknown kind: draw it rather than refuse. The catalogue check is what stops
  // an unknown name reaching a film.
  draw();
}

export default { ENTRANCES, FITS, ENTRANCE_SECONDS, seedOf, chooseEntrance, applyEntrance };
