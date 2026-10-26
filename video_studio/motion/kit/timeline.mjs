/**
 * The timeline: shots, and the transitions between them.
 *
 * Until now `transitionIn` was a label on a shot. Nothing drew it. A rule about
 * transitions that nothing renders is a rule about metadata, so this module
 * exists to make the joins real: at the boundary between two shots, both are
 * drawn to their own canvases and the transition composites them.
 *
 * The join straddles the cut - half its length before the boundary, half after -
 * so a fifty-second film stays fifty seconds no matter how many joins it has.
 */

import { createCanvas } from '@napi-rs/canvas';
import { renderShot, totalDuration } from './stage.mjs';
import { TRANSITIONS } from './transitions.mjs';

/** Where each shot starts, in seconds. */
export function boundaries(shots) {
  let at = 0;
  return shots.map((shot) => {
    const start = at;
    at += shot.dur || 0;
    return { id: shot.id, start, end: at };
  });
}

/**
 * Which shots are on screen at time `t`, and how far through a join we are.
 *
 * @returns {{ from: number, to: number|null, p: number }} - from/to are indices;
 *   `p` is 0..1 across the join, and null when no join is happening.
 */
export function stateAt(spans, t, join = 0.6) {
  if (!spans.length) return { from: 0, to: null, p: null };
  for (let i = 0; i < spans.length; i += 1) {
    const span = spans[i];
    if (t < span.start) return { from: Math.max(0, i - 1), to: null, p: null };
    // The join plays *after* the cut, over the head of the incoming shot.
    //
    // Straddling the boundary looked correct on paper and was wrong on screen:
    // the incoming shot was on display half a second before it began, and since
    // every shot animates up from nothing, that half second was an empty frame
    // punched into a full one. Now the outgoing shot holds on its last frame
    // while the incoming one wipes in as it builds, which is how the transition
    // reads as an arrival instead of a gap.
    if (i < spans.length - 1 && t >= span.end && t < span.end + join) {
      return { from: i, to: i + 1, p: (t - span.end) / join };
    }
    if (t >= span.start && t < span.end) return { from: i, to: null, p: null };
  }
  return { from: spans.length - 1, to: null, p: null };
}

/**
 * Draw the film at time `t`.
 *
 * Two offscreen canvases are reused for every join, because allocating one per
 * frame is how a 1,500-frame render turns into a memory leak.
 */
export function createRenderer(shots, W, H, options = {}) {
  const { join = 0.6, background = '#FAF8F3', scale = 1 } = options;
  const spans = boundaries(shots);
  const dur = totalDuration(shots);
  // The join buffers are device-sized too, so a cut does not drop to the design
  // resolution for half a second while a transition plays.
  const DW = Math.round(W * scale);
  const DH = Math.round(H * scale);
  const bufA = createCanvas(DW, DH);
  const bufB = createCanvas(DW, DH);
  const ctxA = bufA.getContext('2d');
  const ctxB = bufB.getContext('2d');

  return {
    duration: dur,
    spans,
    render(ctx, t) {
      const state = stateAt(spans, t, join);
      const fromShot = shots[state.from];
      const fromLocal = t - spans[state.from].start;

      if (state.to === null) {
        renderShot(ctx, fromShot, fromLocal, W, H, { frame: Math.round(t * 30), background, scale });
        return { join: false, shot: fromShot.id };
      }

      const toShot = shots[state.to];
      const toLocal = Math.max(0, t - spans[state.to].start);
      // The outgoing shot is held on its final frame rather than advanced past
      // its own end, so a join never shows a shot that has already stopped.
      ctxA.setTransform(1, 0, 0, 1, 0, 0);
      ctxB.setTransform(1, 0, 0, 1, 0, 0);
      ctxA.clearRect(0, 0, DW, DH);
      ctxB.clearRect(0, 0, DW, DH);
      const held = Math.min(fromLocal, (fromShot.dur || 0) - 1 / 30);
      // Each shot paints its own ground into its own buffer.
      //
      // Leaving the background to the frame looked tidier and was wrong: a shot's
      // colours are chosen relative to its own paper, so an ink shot (cream marks
      // on near-black) composited over another shot's cream was invisible. A frame
      // has to be self-consistent before it can be dissolved into.
      renderShot(ctxA, fromShot, held, W, H, { frame: Math.round(t * 30), background, scale });
      renderShot(ctxB, toShot, toLocal, W, H, { frame: Math.round(t * 30), background, scale });

      // Hold the outgoing frame for the first third of the window, then play
      // the join. Every shot animates up from nothing, so a join that starts
      // immediately is a join into emptiness; a short hold lets the incoming
      // shot have something on screen before it is revealed.
      const visual = Math.max(0, Math.min(1, (state.p - 0.33) / 0.67));

      const token = toShot.transition || { kind: 'cut', options: {} };
      const kind = TRANSITIONS[token.kind] || TRANSITIONS.cut;
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, DW, DH);
      kind(ctx, {
        a: () => ctx.drawImage(bufA, 0, 0),
        b: () => ctx.drawImage(bufB, 0, 0),
        p: visual,
        w: DW,
        h: DH,
        palette: {},
        ...(token.options || {}),
      });
      ctx.restore();
      return { join: true, from: fromShot.id, to: toShot.id, p: state.p };
    },
  };
}

/**
 * How much of the film is a join. A montage with a join every second is a
 * different film from one that holds, and the pacing audit wants to know.
 */
export function joinBudget(shots, join = 0.6) {
  const intervals = boundaries(shots);
  const joins = Math.max(0, intervals.length - 1);
  const total = totalDuration(shots) || 1;
  return { joins, seconds: joins * join, share: (joins * join) / total };
}
