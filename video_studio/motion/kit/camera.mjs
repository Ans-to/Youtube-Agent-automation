/**
 * A camera.
 *
 * Every shape in this kit takes a box. Without a camera, "extreme close-up on
 * the phone" is impossible: you can only draw the phone bigger, which is not
 * the same thing, because everything else on the frame stays the same size.
 *
 * A camera is a transform and a focus distance. Applying one wraps whatever
 * draws inside it, so the same shot can be framed five ways without touching a
 * single shape - which is the whole reason the script's "camera slowly pushes
 * in" is now a one-line instruction rather than a redraw.
 *
 *     withCamera(ctx, cam, W, H, () => { draw the world });
 */

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/**
 * Shot sizes as a zoom factor about the frame centre.
 * The numbers are the ones a lens set actually gives you: a 4x jump between
 * "wide" and "extreme close" is roughly 24mm to 100mm on a full frame.
 */
export const SHOTS = {
  'extreme-wide': 0.82,
  wide: 1,
  medium: 1.42,
  'medium-close': 1.95,
  close: 2.7,
  'extreme-close': 4.0,
  macro: 6.2,
};

/**
 * @param shot     key of SHOTS, or a number
 * @param at       [x, y] focus point in frame units 0..1 (default centre)
 * @param from     [x, y] start point, for a drift during the shot
 * @param zoom     0..1 of the way from wide to `shot`, so a push is a value
 * @param rotate   degrees
 * @param focus    distance in frame units that is sharp; null = all sharp
 * @param blur     blur radius in px applied outside the focus depth
 */
export function camera(spec = {}) {
  const {
    shot = 'wide',
    at = [0.5, 0.5],
    from = null,
    zoom = 1,
    rotate = 0,
    push = 0,
    shake = 0,
  } = spec;
  const target = typeof shot === 'number' ? shot : (SHOTS[shot] ?? 1);
  const z = 1 + (target - 1) * clamp(zoom, 0, 1) + push;
  return {
    zoom: z,
    at,
    from,
    rotate,
    shake,
    // A camera is always a plain object so it can be logged, diffed and put in
    // a shot list. No closures - a closure cannot be compared.
  };
}

/**
 * Apply a camera for the duration of `draw`.
 *
 * `parallax` lets a caller offset a layer against the camera by depth: a distant
 * layer moves less than the frame, a near one more. That single number is the
 * difference between a flat composition and one with air in it.
 */
export function withCamera(ctx, cam, W, H, draw, options = {}) {
  const { depth = 1, anchor = null } = options;
  const c = typeof cam === 'string' ? camera({ shot: cam }) : (cam || camera());

  // Depth scales the camera's effect, not the layer's: 0 is painted on the sky,
  // 1 is at the focal plane, 2 is a foreground element.
  const z = 1 + (c.zoom - 1) * depth;
  const ax = (anchor ? anchor[0] : c.at[0]) * W;
  const ay = (anchor ? anchor[1] : c.at[1]) * H;
  const fx = c.from ? (c.from[0] - c.at[0]) * W * (1 - c.zoom) * depth : 0;
  const fy = c.from ? (c.from[1] - c.at[1]) * H * (1 - c.zoom) * depth : 0;

  ctx.save();
  ctx.translate(ax, ay);
  ctx.rotate(((c.rotate || 0) * Math.PI) / 180);
  ctx.scale(z, z);
  ctx.translate(-ax + fx, -ay + fy);
  draw();
  ctx.restore();
}

/**
 * A move between two cameras: the shot as written in a script
 * ("wide, slowly pushing to medium on the phone").
 *
 * Returns a camera for a given 0..1 progress through the move.
 */
export function move(fromCam, toCam, t) {
  const a = typeof fromCam === 'string' ? camera({ shot: fromCam }) : fromCam;
  const b = typeof toCam === 'string' ? camera({ shot: toCam }) : toCam;
  const e = ease(clamp(t, 0, 1));
  return {
    zoom: a.zoom + (b.zoom - a.zoom) * e,
    at: [a.at[0] + (b.at[0] - a.at[0]) * e, a.at[1] + (b.at[1] - a.at[1]) * e],
    from: a.from || b.from || null,
    rotate: (a.rotate || 0) + ((b.rotate || 0) - (a.rotate || 0)) * e,
  };
}

/**
 * Is this framing legal?
 *
 * Two rules from the craft notes, enforced here rather than remembered later:
 * no camera shake (the owner asked twice), and a push that is slow enough to
 * read as a move rather than a jump - under 0.06 zoom per second is a drift,
 * over 0.35 is a lurch.
 */
export function auditCamera(cam, seconds = 3, { moving = true } = {}) {
  const notes = [];
  if (cam.shake) notes.push('camera shake is not allowed');
  // A static close-up is not a fast move. Speed only means anything when the
  // camera is actually travelling, which is what `moving` says.
  const room = Math.abs((cam.zoom || 1) - 1);
  if (moving && room > 0 && room / Math.max(seconds, 0.1) > 0.35) {
    notes.push(`camera moves ${(room / seconds).toFixed(2)}x per second - too fast to read`);
  }
  if ((cam.rotate || 0) > 6) notes.push('dutch angle over 6 degrees reads as an error');
  return notes;
}
