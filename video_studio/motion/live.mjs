#!/usr/bin/env node
/**
 * Beat engine for the tutorial film.
 *
 * A screen-teaching film fails the moment its picture stops: a diagram that is
 * finished at second 2 and still on screen at second 12 is a slide, however many
 * pixels of grain are moving on top of it. This module supplies the two things
 * that keep a held composition alive without asking the viewer to re-read it:
 *
 *   - `pulse()`   a small, eased push-in on every narration beat, relaxing back
 *                 over half a second. It is the film's breath.
 *   - `spotlight()`  a moving light that follows the narration across the content,
 *                 so the frame is always being lit rather than merely displayed.
 *
 * Both are content-layer effects: they are measured by the film's motion probe,
 * unlike grain, drifting dots or the camera, which are excluded on purpose.
 */

import { clamp, ease, lerp } from './ui.mjs';

/** Every narration beat: the start of a line, and its midpoint. */
export function beatsOf(lines, scene) {
  const beats = [];
  for (const line of lines) {
    beats.push(Math.max(scene.start, line.start - 0.06));
    beats.push(line.start + (line.end - line.start) * 0.5);
  }
  return beats;
}

/** Which beat we are on, and how far through its accent we are. */
export function beatState(lines, scene, t) {
  const beats = beatsOf(lines, scene);
  let index = 0;
  for (let i = 0; i < beats.length; i += 1) {
    if (t >= beats[i]) index = i;
  }
  const at = beats[index];
  const since = t - at;
  return {
    beats,
    index,
    since,
    // 0 at the beat, 1 once the accent has relaxed. The accent itself is the
    // first 0.55 s, which is about the length of a syllable.
    accent: 1 - ease.outCubic(clamp(since / 0.55)),
    progress: clamp(since / Math.max(0.6, (beats[index + 1] ?? at + 1.6) - at)),
  };
}

/**
 * The push-in. Returns a scale and a drift in design units.
 *
 * 2.4% at the accent is enough to be seen at 1080p and small enough never to
 * read as a zoom; the drift keeps consecutive beats from landing on the same
 * framing, so two beats never produce the same picture.
 */
export function pulse(state, t = 0) {
  // A camera does not shake.
  //
  // This used to return a wandering dx/dy plus a third of a degree of roll that
  // never settled - a hand-held effect. On a frame full of drawn interface the
  // owner read it, correctly, as the picture jittering, and named it as the kind
  // of effect an amateur video uses to fake motion. It also fought the type: text
  // that is still in its own layer but sliding in the frame is still text that
  // will not sit down.
  //
  // What is left is a slow, even breath of scale - two and a half percent at
  // most, no translation, no rotation. It keeps the frame from being frozen
  // between beats without ever looking like a mistake.
  const accent = 0.012 * state.accent;
  const breath = 0.005 * Math.sin(t * 0.42) + 0.002 * Math.sin(t * 0.19 + 1.1);
  return {
    scale: 1 + accent + breath,
    dx: 0,
    dy: 0,
    roll: 0,
  };
}

/**
 * The light that follows the narration.
 *
 * It travels across the frame between beats and settles for the accent, so the
 * viewer's eye is pulled to the part of the screen being described. Drawn after
 * the content, so it lights whatever is underneath instead of covering it.
 */
export function spotlight(ctx, { w, h, t, state, dark = false }) {
  const { beats, index, since } = state;
  const next = beats[index + 1] ?? beats[index] + 1.6;
  const span = Math.max(0.4, next - beats[index]);
  const p = clamp(since / span);

  // A path across the content band, phased per beat so no two beats light the
  // same place. 0.16..0.84 of the width keeps the light on the work.
  const phase = (value) => 0.5 + 0.34 * Math.sin(value * 2.1 + index * 1.7);
  // The light never parks: a beat-to-beat travel plus a continuous orbit, so the
  // lit area is different in every frame of the film.
  const x = (lerp(phase(index), phase(index + 1), ease.inOutCubic(p))
    + 0.045 * Math.sin(t * 0.9)) * w;
  const y = (0.42 + 0.16 * Math.cos(index * 1.3 + p * 0.8) + 0.05 * Math.sin(t * 0.63)) * h;
  const radius = Math.max(w, h) * (0.32 + 0.05 * Math.sin(t * 0.6));

  const g = ctx.createRadialGradient(x, y, 0, x, y, radius);
  if (dark) {
    g.addColorStop(0, 'rgba(255,240,200,0.075)');
    g.addColorStop(0.55, 'rgba(255,240,200,0.028)');
    g.addColorStop(1, 'rgba(255,240,200,0)');
  } else {
    g.addColorStop(0, 'rgba(255,255,255,0.30)');
    g.addColorStop(0.55, 'rgba(255,255,255,0.12)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
  }
  ctx.save();
  // `soft-light` lifts the lit area without washing out the type underneath.
  ctx.globalCompositeOperation = dark ? 'soft-light' : 'soft-light';
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();
  return { x, y, radius };
}

/** A thin rule that reports where in the beat we are: a metronome, not decoration. */
export function beatTicks(ctx, { w, h, state, colour }) {
  const total = state.beats.length;
  if (!total) return;
  const x0 = 150;
  const width = w - 300;
  const step = width / total;
  for (let i = 0; i < total; i += 1) {
    const on = i <= state.index;
    const active = i === state.index;
    const height = active ? 26 : 12;
    ctx.fillStyle = active ? colour : on ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.16)';
    ctx.fillRect(x0 + i * step, h - 30 - height, Math.max(3, step * 0.35), height);
  }
}
