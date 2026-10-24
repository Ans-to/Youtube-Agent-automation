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
 *   flash   reserved. The old one. It is still here, but it is used at most once
 *           in the film - on the last cut - so it reads as punctuation.
 *
 * Each function draws only over the incoming frame, so they compose with the
 * picture rather than replacing it. All of them are under 0.45 s; nothing here
 * is a camera move and none of them moves the whole frame against itself, which
 * is what the owner rejected as shake.
 */
import { clamp, span, ease } from './ui.mjs';

export const TRANSITIONS = ['cut', 'wipe', 'iris', 'push', 'flash'];

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
  if (p <= 0) {
    ctx.drawImage(a, 0, 0);
    return;
  }
  if (p >= 1 || kind === 'cut') {
    ctx.drawImage(b, 0, 0);
    return;
  }
  ctx.save();
  // The ground is the incoming frame everywhere the mask does not reach, so a
  // slow reveal never shows an empty canvas behind it.
  ctx.drawImage(b, 0, 0);

  if (kind === 'wipe') {
    // A hard edge crossing left to right, in the direction of reading, with a
    // 40-pixel accent band on its leading edge.
    const x = ease.inOutCubic(p) * (w + 80) - 40;
    ctx.beginPath();
    ctx.rect(0, 0, x, h);
    ctx.clip();
    ctx.drawImage(a, 0, 0);
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.fillStyle = accent;
    const edge = Math.min(w, Math.max(-40, x));
    ctx.fillRect(edge - 4, 0, 10, h);
    ctx.restore();
    return;
  }

  if (kind === 'iris') {
    // The outgoing shot is inside a shrinking circle; the incoming one is
    // everywhere else. The circle is drawn as a ring on its own edge, which is
    // the same mark the film puts around a word.
    // The outgoing shot stays visible *inside* the closing circle, which is the
    // classic iris and the only version a viewer can read: the old picture
    // shrinks to a dot on top of the new one. The first attempt masked the other
    // way round, so the outgoing frame lived in the corners and the transition
    // was invisible.
    const r = (1 - ease.inOutCubic(p)) * Math.hypot(w, h) * 0.58;
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, Math.max(0, r), 0, Math.PI * 2);
    ctx.clip();
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

  if (kind === 'flash') {
    const f = span(p, 0, 0.5);
    if (f <= 0) { ctx.drawImage(a, 0, 0); return; }
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
  ctx.restore();
}

