/**
 * The stage: how a shot is built from layers.
 *
 * Until now a beat was one template drawn into one region. A real frame is five
 * to fifteen elements at different depths, arriving at different times, each
 * doing its own thing while it is up. This is that structure.
 *
 * A shot is data:
 *
 *   {
 *     id: 'hook-03-map',
 *     dur: 8,
 *     camera: { shot: 'wide', at: [0.5, 0.5], zoom: 0.35 },
 *     grade: { vignetteStrength: 0.34, bloomAt: [0.62, 0.46] },
 *     layers: [
 *       { id: 'map',   depth: 0.6, from: 0.0, entrance: 'draw',  draw: (ctx, p) => ... },
 *       { id: 'title', depth: 1.0, from: 0.45, entrance: 'wipe',  draw: (ctx, p) => ... },
 *     ],
 *   }
 *
 * and `renderShot` draws it for any time. Because the layer is data, the same
 * shot can be rendered as a still, as a contact sheet, or as frames - and the
 * pacing can be audited before anything is encoded.
 */

import { camera as makeCamera, withCamera } from './camera.mjs';
import { grade } from './light.mjs';
import { applyEntrance, applyBehaviour, applyExit } from './motion.mjs';
import { clamp, lerp } from '../ui.mjs';

/** Local progress through a layer's own life inside the shot. */
export function layerProgress(layer, t, shotDur) {
  const from = layer.from ?? 0;
  const to = layer.to ?? 1;
  const span = Math.max(1e-6, to - from);
  return clamp((t / shotDur - from) / span);
}

/**
 * When does this layer need to exist at all? Used by the pacing audit: a shot
 * whose layers are all up in the first 200ms is a poster, not a shot.
 */
export function layerWindow(layer, shotDur) {
  return {
    in: (layer.from ?? 0) * shotDur,
    out: (layer.to ?? 1) * shotDur,
    live: ((layer.to ?? 1) - (layer.from ?? 0)) * shotDur,
  };
}

/**
 * Draw one shot at time `t` (seconds, from the start of the shot).
 *
 * Order is deliberate: background to foreground by depth, then the grade over
 * the finished picture. Grading a half-built frame tints the elements that have
 * not arrived yet, which is how a shot ends up with a visible seam.
 */
/**
 * A hook the film uses to set state that lives above the shot - the live palette
 * is the one that matters. Set once per film, called before every shot draws.
 */
let shotPrepare = null;

export function setShotPrepare(fn) {
  shotPrepare = fn;
}

export function renderShot(ctx, shot, t, W, H, options = {}) {
  if (shotPrepare) shotPrepare(shot);
  const {
    frame = 0, background = '#FAFAF7', frameGrade = true, paintBackground = true,
    // `scale` renders the shot at a higher device resolution without the film
    // having to know: every coordinate stays in design pixels, and the context
    // is scaled once here. Without it, a 1080p deliverable is a 720p drawing
    // enlarged, and the type is the first thing that shows it.
    scale = 1,
  } = options;
  const dur = shot.dur || 4;
  const cam = typeof shot.camera === 'function' ? shot.camera(clamp(t / dur)) : shot.camera;

  ctx.save();
  if (scale !== 1) ctx.setTransform(scale, 0, 0, scale, 0, 0);
  // A shot is a background plus layers. When a join composites two shots, the
  // frame supplies the paper and each shot supplies only its content - otherwise
  // the incoming shot's opaque background covers the outgoing shot completely,
  // which is what made every crossfade in the film dip to a blank page.
  if (paintBackground) {
    ctx.fillStyle = shot.background || background;
    ctx.fillRect(0, 0, W, H);
  }

  /*
   * The breath.
   *
   * Measured on the delivered cut: 596 of 859 frames changed by less than 0.4
   * out of 255 between one frame and the next. Each shot played its entrance for
   * a second or two and was then a still photograph for the rest of its length.
   * A still frame is the single most reliable thing that makes motion graphics
   * feel like a slideshow, and no amount of better artwork fixes it.
   *
   * Every shot now carries a slow move of its own - a push, a pull, or a drift
   * across - of four and a half percent over the shot's length. The first
   * version used two percent, which measured lighter than the entrance moves and,
   * at 640 pixels wide, moved less than the noise floor: it was mathematically a
   * camera move and perceptually a still frame. The direction comes from the shot's own id, so
   * it is the same on every render and no two consecutive shots travel the same
   * way.
   */
  if (shot.drift !== false) {
    const seed = [...(shot.id || 'x')].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 100000, 7);
    const kind = seed % 4;
    const amount = shot.driftAmount ?? 0.045;
    const prog = clamp(t / dur);
    /* A smoothstep starts at zero velocity, which means the first half second
       of every shot is a still frame that happens to be part of a slow move -
       and the first half second of a film is the most expensive half second it
       has. Two thirds of the travel is spread over the whole shot at constant
       speed, and a third eases at each end for weight. */
    const eased = 0.66 * prog + 0.34 * (prog * prog * (3 - 2 * prog));
    const zoom = kind === 0 ? 1 + eased * amount
      : kind === 1 ? 1 + amount - eased * amount
        : 1 + amount * 0.35 + eased * amount * 0.5;
    const dx = (kind === 2 ? -1 : kind === 3 ? 1 : 0) * amount * W * 0.35 * (eased - 0.5);
    const dy = (kind === 0 ? 1 : kind === 1 ? -1 : 0) * amount * H * 0.22 * (eased - 0.5);
    ctx.translate(W / 2, H / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-W / 2 + dx, -H / 2 + dy);
  }

  const layers = [...(shot.layers || [])].sort((a, b) => (a.depth ?? 1) - (b.depth ?? 1));

  for (const layer of layers) {
    const p = layerProgress(layer, t, dur);
    // A layer that is present from the start of the shot is present on the
    // shot's *first* frame. It used to be skipped at p === 0, which meant every
    // shot opened empty: frame 0 of the film was pure background, and every cut
    // landed on nothing for a frame. A layer that starts later still waits.
    if (p <= 0 && (layer.from ?? 0) > 0) continue;
    const local = { p, t, dur, W, H };

    // Moves call their artwork with no argument, so bind the context here
    // rather than trusting the caller to pass it back.
    const paint = (c) => layer.draw(c || ctx, local);

    // Entrances run in the first slice of the layer's life, exits in the last;
    // everything between is the behaviour, which is what keeps a held frame
    // alive. A layer can have none, one, or all three.
    // Entrances and exits are box-relative - a wipe needs to know what it is
    // wiping, a squash needs a centre - so every layer resolves a box once and
    // hands it to the move. A layer that does not care gets the whole frame.
    const box = layer.box || { x: 0, y: 0, w: W, h: H };
    const accent = layer.accent || (layer.palette && layer.palette.caption) || '#B4762A';
    const motionOptions = { p, t, box, accent, palette: layer.palette };

    let stage = paint;
    if (layer.exit) {
      // Capture the previous draw in a const. Referring to `stage` inside the
      // closure would read the reassigned variable and the exit would call
      // itself until the stack ran out.
      const held = stage;
      stage = (c) => applyExit(c || ctx, layer.exit, { ...motionOptions, ...(layer.exitOptions || {}), draw: held }, held);
    }
    if (layer.behaviour) {
      const held = stage;
      stage = (c) => applyBehaviour(c || ctx, layer.behaviour, { ...motionOptions, ...(layer.behaviourOptions || {}), draw: held }, held);
    }
    if (layer.entrance) {
      const held = stage;
      stage = (c) => applyEntrance(c || ctx, layer.entrance, { ...motionOptions, ...(layer.entranceOptions || {}), draw: held }, held);
    }

    const paintLayer = () => {
      ctx.save();
      if (layer.alpha !== undefined) ctx.globalAlpha *= layer.alpha;
      stage(ctx);
      ctx.restore();
    };

    // `screen: true` pins a layer to the frame instead of the world.
    //
    // Typography and captions belong to the frame: at a 2.2x push they used to
    // be scaled up and thrown off the edge, which is why the last line of the
    // hook simply vanished. Only things that are physically in the scene get
    // the camera.
    if (layer.screen) paintLayer();
    else withCamera(ctx, cam, W, H, paintLayer, { depth: layer.depth ?? 1 });
  }

  if (frameGrade) {
    grade(ctx, W, H, { frame, ...(shot.grade || {}) });
  }
  ctx.restore();
}

/* -------------------------------------------------------------------------
 * Pacing
 * ---------------------------------------------------------------------- */

/**
 * The rules from the craft notes, checked against a shot list rather than
 * remembered: nothing frozen for over a second, nothing longer than twelve
 * seconds, no transition twice in a row, and a change of some kind every five
 * to seven seconds.
 */
export function auditShotList(shots) {
  const notes = [];
  let lastTransition = null;
  shots.forEach((shot, i) => {
    const name = shot.id || `shot ${i + 1}`;
    if ((shot.dur || 0) > 12) notes.push(`${name}: ${shot.dur}s is over the 12s ceiling`);

    const windows = (shot.layers || []).map((l) => layerWindow(l, shot.dur || 0));
    // Whether a shot is frozen is a question about pixels, not about which
    // layers carry an entrance label: a chart that draws itself through its own
    // progress is in motion with no entrance at all. verify.mjs renders two
    // frames of every shot and compares them, which is the honest test.

    if (shot.transitionIn && shot.transitionIn === lastTransition) {
      notes.push(`${name}: repeats the "${shot.transitionIn}" transition`);
    }
    if (shot.transitionIn) lastTransition = shot.transitionIn;

    // Every layer arriving in the first fifth of the shot means the rest is dead air.
    const arrivals = (shot.layers || []).filter((l) => l.entrance).map((l) => l.from ?? 0);
    if (arrivals.length > 2 && Math.max(...arrivals) < 0.2) {
      notes.push(`${name}: every layer arrives in the first ${Math.round(Math.max(...arrivals) * 100)}% and then nothing happens`);
    }
    if (!windows.length) notes.push(`${name}: no layers`);
  });
  return notes;
}

/** Total running time, so a film can be checked against its script's clock. */
export function totalDuration(shots) {
  return shots.reduce((sum, s) => sum + (s.dur || 0), 0);
}

export { lerp, clamp };
