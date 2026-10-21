/**
 * Animation for the character rig: cycles, layers and speech.
 *
 * A pose here is never a static target. Every cycle returns a pose *and* the
 * secondary motion that belongs with it — breathing, weight shift, head
 * stabilisation, overlap — so the figure is alive between the key poses too.
 *
 * All functions are pure and deterministic: the same `t` always produces the
 * same pose, which is what lets frames render out of order or on CI.
 */

import {
  BONES, BONE_INDEX, solve, twoBoneIK, springSettle, clamp01, lerp, span, ease,
  sampleVisemes, blinkAt, VISEMES,
} from './rig.mjs';

const HIP_HEIGHT = (() => {
  // distance from hips to the floor in the rest pose
  const rest = solve({}, { x: 0, y: 0, scale: 1 });
  return rest.footL.end[1] - rest.hips.origin[1];
})();

export const GROUND = { hipHeight: HIP_HEIGHT };

/** Smallest deterministic noise in [-1,1] for handheld camera and idle drift. */
function hash(n) {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
  return s - Math.floor(s);
}
export function noise1(x) {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  return lerp(hash(i) * 2 - 1, hash(i + 1) * 2 - 1, u);
}

/** Breathing, applied to the chest and shoulders only. */
function breathe(pose, t, amount = 1) {
  const phase = Math.sin(t * 1.35 * Math.PI * 2);
  pose.chest = (pose.chest || 0) + phase * 0.012 * amount;
  pose.shoulderL = (pose.shoulderL || 0) - phase * 0.010 * amount;
  pose.shoulderR = (pose.shoulderR || 0) - phase * 0.010 * amount;
  pose.neck = (pose.neck || 0) + phase * 0.008 * amount;
  return phase;
}

/** Head look-at expressed in radians; returns the local angles that do it. */
function lookAt(pose, solved, point) {
  const head = solved.head;
  const cx = head.origin[0];
  const cy = head.origin[1];
  const want = Math.atan2(point[1] - cy, point[0] - cx) - Math.PI / 2;
  const delta = Math.atan2(Math.sin(want - solved.head.world), Math.cos(want - solved.head.world));
  pose.head = (pose.head || 0) + delta * 0.55;
  pose.neck = (pose.neck || 0) + delta * 0.25;
  return delta;
}

/**
 * Idle: weight shifts side to side, breathing, occasional glance, restrained
 * sway in the arms so the silhouette is never frozen.
 */
export function idlePose(t, opts = {}) {
  const pose = {};
  const sway = Math.sin(t * 0.55 * Math.PI * 2);
  pose.hips = sway * 0.030;
  pose.spine = -sway * 0.042;
  pose.chest = sway * 0.012;
  breathe(pose, t, opts.breathe === undefined ? 1 : opts.breathe);
  pose.armL = 0.05 * sway + 0.02 * Math.sin(t * 1.1 * Math.PI * 2);
  pose.armR = -0.05 * sway - 0.02 * Math.sin(t * 1.1 * Math.PI * 2 + 0.6);
  pose.forearmL = 0.10 + 0.03 * Math.sin(t * 0.9 * Math.PI * 2);
  pose.forearmR = -0.10 - 0.03 * Math.sin(t * 0.9 * Math.PI * 2 + 0.5);
  pose.head = 0.055 * Math.sin(t * 0.42 * Math.PI * 2) + 0.025 * Math.sin(t * 1.7);
  pose.neck = 0.02 * Math.sin(t * 0.42 * Math.PI * 2);
  return pose;
}

/**
 * Walk cycle with planted feet.
 * @param {number} t seconds
 * @param {number} stride seconds per full cycle (two steps)
 * @param {number} hipX screen-space x of the hips
 * @param {number} groundY screen-space floor line
 * @param {number} scale
 */
export function walkPose(t, { stride = 1.1, hipX = 0, groundY = 0, scale = 1, speed = 1 } = {}) {
  const pose = {};
  const phase = (t / stride) % 1;
  const bob = Math.abs(Math.sin(phase * Math.PI * 2)) * 6 * scale;
  const hipY = groundY - HIP_HEIGHT * scale - bob;

  // foot placement: each foot is planted for the stance half of the cycle, then
  // swings forward; the ankle x is derived from the phase, not hand-keyed
  const step = 150 * scale * speed;
  const footX = (offset) => {
    const p = (phase + offset) % 1;
    if (p < 0.5) return hipX - step + p * 4 * step;          // planted, body passes over
    const swing = (p - 0.5) * 2;
    return hipX + step - swing * 2 * step;                    // in the air
  };
  const lift = (offset) => {
    const p = (phase + offset) % 1;
    if (p < 0.5) return 0;
    return Math.sin((p - 0.5) * 2 * Math.PI) * 46 * scale;
  };

  // Solve the hips at the origin, then give IK targets relative to the hips in
  // world space: solved bone lengths already carry the root scale.
  const footY = (offset) => groundY - lift(offset);
  const base = solve(pose, { x: 0, y: 0, scale });
  const ankle = 34 * scale;
  const leftX = footX(0) - hipX;
  const rightX = footX(0.5) - hipX;
  const leftY = footY(0) - hipY;
  const rightY = footY(0.5) - hipY;

  Object.assign(pose, twoBoneIK(base, 'thighL', 'shinL', [leftX, leftY - ankle], 1));
  Object.assign(pose, twoBoneIK(base, 'thighR', 'shinR', [rightX, rightY - ankle], -1));
  pose.footL = -solveFoot(base, 'shinL', pose, lift(0) > 1 ? 0.35 : 0);
  pose.footR = -solveFoot(base, 'shinR', pose, lift(0.5) > 1 ? 0.35 : 0);

  // arms counter-swing the legs, with the elbow trailing (overlap)
  const swing = Math.sin(phase * Math.PI * 2);
  pose.armL = -swing * 0.32;
  pose.armR = swing * 0.32;
  pose.forearmL = 0.30 + Math.sin(phase * Math.PI * 2 - 0.5) * 0.16;
  pose.forearmR = -0.30 - Math.sin(phase * Math.PI * 2 - 0.5) * 0.16;
  pose.spine = 0.03 + swing * 0.02;
  pose.chest = -swing * 0.05;
  pose.hips = swing * 0.06;
  breathe(pose, t, 0.6);
  pose.head = -swing * 0.03;
  return { pose, hips: { x: hipX, y: hipY, scale } };
}

function solveFoot(base, shin, pose, toe) {
  const rest = BONES[BONE_INDEX.get(shin === 'shinL' ? 'footL' : 'footR')].rest;
  return base[shin].world + pose[shin] + rest - toe;
}

/** A wave that starts at `at` and runs for `dur`; the wrist leads the forearm. */
export function wavePose(t, { at = 0, dur = 1.6, scale = 1 } = {}) {
  const pose = {};
  const enter = ease.outCubic(span(t, at, at + 0.45));
  const leave = ease.inCubic(span(t, at + dur - 0.35, at + dur));
  const up = enter * (1 - leave);
  if (up <= 0) return pose;
  const base = solve(pose, { x: 0, y: 0, scale });
  // beside and above the head: forward of the shoulder, high enough to read
  const target = [300 * scale, -1040 * scale];
  const ik = twoBoneIK(base, 'armL', 'forearmL', target, 1);
  const shake = Math.sin((t - at) * 9.5) * 0.22 * up;
  pose.armL = ik.armL * up + shake;
  pose.forearmL = ik.forearmL * up + shake * 0.6;
  pose.handL = Math.sin((t - at) * 9.5 - 0.7) * 0.25 * up;
  pose.browRaiseAmt = 0.6 * up;
  pose.head = up * 0.05;
  return pose;
}

/**
 * Speaking: the mouth is driven by a viseme timeline, and the head/body get the
 * small accents speech actually produces — a nod on stressed syllables, a brow
 * lift on questions, and shoulders that move with emphasis.
 */
export function speechLayer(pose, t, timeline, opts = {}) {
  const viseme = sampleVisemes(timeline, t);
  const energy = clamp01(viseme.open * 1.4);
  pose.head = (pose.head || 0) + Math.sin(t * 3.1) * 0.012 + energy * 0.05;
  pose.neck = (pose.neck || 0) + energy * 0.02;
  pose.chest = (pose.chest || 0) + energy * 0.02;
  pose.browRaise = (opts.brow === undefined ? 0.15 : opts.brow) + energy * 0.35;
  return viseme;
}

/**
 * Compose a full character frame.
 *
 * @returns {{solved: object, viseme: object, blink: number, browRaise: number, scale: number}}
 */
export function characterFrame(t, spec = {}) {
  const scale = spec.scale === undefined ? 1 : spec.scale;
  const groundY = spec.groundY === undefined ? 0 : spec.groundY;
  const mode = spec.mode || 'idle';

  let pose;
  let hips;
  if (mode === 'walk') {
    const walked = walkPose(t, {
      stride: spec.stride || 1.15,
      hipX: spec.hipX || 0,
      groundY,
      scale,
      speed: spec.speed || 1,
    });
    pose = walked.pose;
    hips = { x: walked.hips.x, y: walked.hips.y, scale };
  } else {
    pose = idlePose(t, { breathe: spec.breathe });
    const bob = Math.sin(t * 0.55 * Math.PI * 2) * 5 * scale;
    hips = { x: spec.hipX || 0, y: groundY - HIP_HEIGHT * scale - bob, scale };
  }

  if (spec.gesture > 0.01) {
    // a conversational beat: the free arm lifts, elbow leads, hand trails
    const lift = spec.gesture;
    pose.armR = (pose.armR || 0) + lift * 0.55;
    pose.forearmR = (pose.forearmR || 0) - lift * 0.85;
    pose.chest = (pose.chest || 0) - lift * 0.03;
    pose.head = (pose.head || 0) + lift * 0.04;
  }

  if (spec.wave) {
    const wave = wavePose(t, { at: spec.wave.at, dur: spec.wave.dur, scale });
    Object.assign(pose, wave, { browRaise: wave.browRaiseAmt || 0 });
  }

  let viseme = VISEMES.REST;
  if (spec.speech && spec.speech.timeline) {
    viseme = speechLayer(pose, t, spec.speech.timeline, { brow: spec.speech.brow });
  }

  if (spec.lookAt) {
    const halfway = solve(pose, hips);
    lookAt(pose, halfway, spec.lookAt);
  }

  const breath = 1 + Math.sin(t * 1.35 * Math.PI * 2) * 0.012;
  const blink = blinkAt(spec.blinks || [], t);
  const solved = solve(pose, hips);
  return {
    solved,
    viseme,
    blink,
    browRaise: clamp01(pose.browRaise || 0),
    scale,
    breath,
  };
}

/** Build a viseme timeline from words, evenly spaced inside a window. */
export function speechTimeline(words, { start = 0, end = 2, seed = 1 } = {}) {
  const picks = ['AA', 'AE', 'E', 'I', 'O', 'U', 'MBP', 'FV', 'L', 'WQ'];
  const spanSeconds = end - start;
  const per = spanSeconds / words.length;
  const timeline = [];
  words.forEach((word, index) => {
    const at0 = start + index * per;
    const syllables = Math.max(1, Math.min(4, Math.round(word.length / 2.6)));
    for (let s = 0; s < syllables; s += 1) {
      const at = at0 + ((s + 0.5) / syllables) * per * 0.86;
      const pick = picks[(index * 3 + s * 7 + Math.floor(hash(seed + index * 13 + s) * 10)) % picks.length];
      timeline.push({ at, viseme: pick, hold: Math.max(0.05, (per / syllables) * 0.55) });
    }
  });
  return timeline;
}

/** Blink schedule that never repeats exactly: 2.4-5.2 s apart, deterministic. */
export function blinkSchedule(duration, seed = 3) {
  const times = [];
  let t = 1.2 + hash(seed) * 1.8;
  while (t < duration) {
    times.push(t);
    t += 2.4 + hash(seed + times.length * 4.7) * 2.8;
  }
  return times;
}

export { springSettle, BONES, HIP_HEIGHT };
