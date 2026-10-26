/**
 * Transitions: how one shot hands the frame to the next.
 *
 * The film had exactly one, used at every cut: a white flash plus speed lines.
 * Thirty-odd times. The owner's note was "don't always use the same transition",
 * and the reason one is not enough is that a transition is a sentence of its
 * own - it says how the two shots are related:
 *
 *   cut     nothing in common, so nothing is drawn. A hard cut is the most
 *           confident transition there is and the least tiring when the shots
 *           already share a ground, which the typographic stage's do.
 *   wipe    the next shot is the same place, further along. A hard-edged band
 *           crosses the frame, so the new picture is revealed left to right in
 *           the direction of reading.
 *   iris    the next shot is a detail of the one before - a thing zoomed into.
 *           A circle opens from the centre of the frame.
 *   push    the next shot moves the argument somewhere else. The outgoing frame
 *           is shoved up and out by the incoming one, with a soft leading edge.
 *   focus   the next shot is the same subject seen from further out - a detail
 *           releasing back to its context. The outgoing frame softens out of
 *           focus instead of being masked away, which is how a camera leaves a
 *           close-up and the one thing an iris cannot say: an iris goes in,
 *           this comes back out. Taken from the blur-in primitive in
 *           howardc38/motion-fx-lab, reimplemented here on Canvas 2D filters.
 *   flash   reserved. The old one. It is still here, but it is used at most once
 *           in the film - on the last cut - so it reads as punctuation.
 *
 * Each function draws only over the incoming frame, so they compose with the
 * picture rather than replacing it. All of them are under 0.45 s; nothing here
 * is a camera move and none of them moves the whole frame against itself, which
 * is what the owner rejected as shake.
 */
import { clamp, span, ease } from './ui.mjs';

export const TRANSITIONS = ['cut', 'wipe', 'iris', 'push', 'focus', 'flash'];

/**
 * Pick a transition for a cut.
 *
 * Deliberately not random: the same situation always gets the same transition,
 * so the film is predictable to a viewer and a rule rather than a mood. The
 * order also guarantees no two neighbouring cuts use the same device, because
 * the caller passes the one it used last.
 *
 * ``situation`` is one of:
 *   'same-place'   the next shot continues the one before (stage to card)
 *   'new-idea'     a new sentence, same scene
 *   'new-scene'    a new chapter
 *   'detail'       the next shot is a closer look at the same thing
 *   'final'        the last cut of the film
 */
export function chooseTransition(situation, previous = 'cut') {
  const preferred = {
    'same-place': 'iris',
    'new-idea': 'cut',
    'new-scene': 'wipe',
    detail: 'push',
    release: 'focus',
    final: 'flash',
  }[situation] || 'cut';
  if (preferred !== previous) return preferred;
  // Never repeat: fall back to the next device in the list, in a fixed order.
  const order = TRANSITIONS.filter((t) => t !== previous && t !== 'flash');
  const index = (TRANSITIONS.indexOf(preferred) + 1) % TRANSITIONS.length;
  for (let i = 0; i < TRANSITIONS.length; i += 1) {
    const candidate = TRANSITIONS[(index + i) % TRANSITIONS.length];
    if (candidate !== previous && order.includes(candidate)) return candidate;
  }
  return 'cut';
}

/**
 * Composite two finished frames: ``a`` is the shot leaving, ``b`` the shot
 * arriving.
 *
 * Both are real renders of their own moment - this is what makes the transition
 * a transition. Half a band painted over one frame is decoration; a mask over
 * two frames is a shot change.
 */
export function reveal(ctx, { kind, p, a, b, w, h, accent = '#F2C230' }) {
  // Composite in device pixels.
  //
  // ``a`` and ``b`` are full-resolution canvases and ``w``/``h`` are the output
  // size in pixels, but the caller draws its picture in design units with a
  // scale transform on the context. Compositing these images without resetting
  // that transform draws the outgoing shot at a quarter size in the corner,
  // which is exactly what happened the first time this module was reached in a
  // render - a bug elsewhere had meant it never ran, so the fault sat here
  // unseen.
  //
  // Everything is inside one save/restore pair, closed in a ``finally``, so an
  // early return cannot leave the context with a transform or a clip that
  // belongs to a transition that is over. The previous version had three
  // branches with unbalanced saves; one of them closed a save it never opened,
  // which silently discarded the caller's transform for the rest of the frame.
  ctx.save();
  try {
    ctx.setTransform(1, 0, 0, 1, 0, 0);

    if (p <= 0) {
      ctx.drawImage(a, 0, 0);
      return;
    }
    if (p >= 1 || kind === 'cut') {
      ctx.drawImage(b, 0, 0);
      return;
    }

    // The ground is the incoming frame everywhere the mask does not reach, so a
    // reveal never shows an empty canvas behind it.
    ctx.drawImage(b, 0, 0);

    if (kind === 'wipe') {
      // A hard edge crossing left to right, in the direction of reading, with a
      // narrow accent band riding its leading edge.
      //
      // The incoming shot is revealed behind the edge, not the outgoing one
      // exposed in front of it. Those two are not the same thing and the first
      // was written the wrong way round: it ended the transition showing the old
      // picture in full and then snapped to the new one, so the wipe was a
      // hundredth of a second from a hard cut with a band drawn on top. Measured
      // on the render, the frame at 19.65 was still the whole outgoing shot.
      const x = ease.inOutCubic(p) * (w + 80) - 40;
      ctx.drawImage(a, 0, 0);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, Math.max(0, x), h);
      ctx.clip();
      ctx.drawImage(b, 0, 0);
      ctx.restore();
      const edge = Math.min(w, Math.max(-40, x));
      ctx.save();
      ctx.fillStyle = accent;
      ctx.fillRect(edge - 4, 0, 10, h);
      ctx.restore();
      return;
    }

    if (kind === 'iris') {
      // The outgoing shot is inside a shrinking circle and the incoming one is
      // everywhere else. This is the only direction a viewer can read: the old
      // picture shrinks to a dot on top of the new one. Masking the other way
      // leaves the outgoing frame in the corners and the transition is invisible.
      const close = ease.inOutCubic(p);
      const reach = Math.hypot(w, h) * 0.58;
      const r = (1 - close) * reach;
      ctx.save();
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, Math.max(0, r), 0, Math.PI * 2);
      ctx.clip();
      // The old shot shrinks *into* the circle rather than being cropped by it.
      // Cropped, a circle closing over a sentence shows a fragment of it -
      // "SCRIBING I" floating over the new shot - and the word is cut in a place
      // the eye reads as a mistake. Scaled, the whole previous picture recedes to
      // a point, which is what an iris means.
      const s2 = Math.max(0.001, r / reach);
      ctx.translate(w / 2, h / 2);
      ctx.scale(s2, s2);
      ctx.translate(-w / 2, -h / 2);
      ctx.drawImage(a, 0, 0);
      ctx.restore();
      if (r > 2) {
        ctx.save();
        ctx.strokeStyle = accent;
        ctx.lineWidth = 8;
        ctx.beginPath();
        ctx.arc(w / 2, h / 2, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
      return;
    }

    if (kind === 'push') {
      // The outgoing shot is shoved up and out by the incoming one, with a soft
      // shadow on its lower edge so it reads as a sheet of paper, not a bug.
      const y = -ease.inOutCubic(p) * h;
      ctx.save();
      ctx.shadowColor = 'rgba(0,0,0,0.28)';
      ctx.shadowBlur = 60;
      ctx.shadowOffsetY = 30;
      ctx.drawImage(a, 0, y);
      ctx.restore();
      return;
    }

    if (kind === 'focus') {
      // The outgoing shot defocuses out of the way instead of being masked away:
      // the camera pulling back out of a detail. The incoming frame is already
      // down, so this only paints ``a`` on top with a growing blur and a falling
      // alpha. Canvas filters are real in this renderer - checked before this was
      // written, a pixel ten pixels off a filled bar moved from 255 to 226 under
      // a 10-pixel blur - so the effect is in the pixels and not only in the
      // property.
      const soft = ease.inOutCubic(p);
      ctx.save();
      ctx.globalAlpha = 1 - soft;
      ctx.filter = `blur(${(soft * 26).toFixed(2)}px)`;
      ctx.drawImage(a, 0, 0);
      ctx.restore();
      return;
    }

    if (kind === 'flash') {
      const f = span(p, 0, 0.5);
      if (f <= 0) {
        ctx.drawImage(a, 0, 0);
        return;
      }
      ctx.drawImage(a, 0, 0);
      const faded = ease.outExpo(f);
      ctx.save();
      ctx.fillStyle = `rgba(255,255,255,${(1 - faded) * 0.62})`;
      ctx.fillRect(0, 0, w, h);
      ctx.restore();
      if (f > 0.35) {
        ctx.save();
        ctx.globalAlpha = span(f, 0.35, 1);
        ctx.drawImage(b, 0, 0);
        ctx.restore();
      }
      return;
    }

    ctx.drawImage(b, 0, 0);
  } finally {
    ctx.restore();
  }
}
