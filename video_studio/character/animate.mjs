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

/**
 * How far the *shoe* reaches below the ankle line.
 *
 * `HIP_HEIGHT` measures hips to ankle, but the artwork draws a shoe that wraps
 * the ankle (`drawShoe` centres a rect of 0.40 * foot length on it). Standing
 * the figure with its hips exactly `HIP_HEIGHT` above the floor therefore buried
 * the soles roughly 30 units into the ground. The floor is where the sole is,
 * not where the ankle is, so every grounded pose adds this offset.
 */
const SOLE = (() => {
  const rest = solve({}, { x: 0, y: 0, scale: 1 });
  return rest.footL.length * 0.20;
})();

export const GROUND = { hipHeight: HIP_HEIGHT, sole: SOLE };


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
  const hipY = groundY - (HIP_HEIGHT + SOLE) * scale - bob;

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
  // the ankle sits one sole above the floor, so the shoe lands on the line
  const ankle = SOLE * scale;
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
 * Read one audio frame. The envelope may be a plain number (loudness only) or
 * `{open, bright}`; the second form is what the pipeline writes now.
 */
function readAudioFrame(sample) {
  if (sample === null || sample === undefined) return { open: 0, bright: 0.5, vis: null };
  if (typeof sample === 'number') return { open: clamp01(sample), bright: 0.5, vis: null };
  // `vis` is a *measured* viseme from the acoustic analyser (formant-based
  // articulation). When it is present the mouth is drawn from it directly
  // instead of being reconstructed from loudness.
  const raw = sample.vis || sample.viseme || null;
  let vis = null;
  if (raw && typeof raw === 'object') {
    vis = {
      open: clamp01(raw.open || 0),
      wide: clamp01(raw.wide === undefined ? 0.5 : raw.wide),
      round: clamp01(raw.round === undefined ? 0.3 : raw.round),
      teeth: clamp01(raw.teeth || 0),
      press: clamp01(raw.press || 0),
    };
  }
  return {
    open: clamp01(sample.open === undefined ? sample.openness : sample.open),
    bright: sample.bright === undefined ? 0.5 : clamp01(sample.bright),
    vis,
  };
}

/**
 * Mouth shapes measured from the voice, not guessed from the caption.
 *
 * The previous layer multiplied a *text-derived* viseme timeline by the audio
 * envelope. The envelope only scaled whatever shape the text had picked, so the
 * mouth could be nearly shut on a loud syllable and wide open in a pause: the
 * picture had motion but no sync. This layer reads two real measurements per
 * video frame — RMS openness and spectral centroid — and builds the mouth from
 * them, so loudness sets the jaw and vowel colour sets the shape.
 *
 * @param {number} t seconds
 * @param {(t:number)=>number|{open:number,bright:number}} envelope
 */
export function mouthFromAudio(t, envelope, opts = {}) {
  if (typeof envelope !== 'function') return { ...VISEMES.REST };
  const now = readAudioFrame(envelope(t));
  const before = readAudioFrame(envelope(t - 0.033));
  const after = readAudioFrame(envelope(t + 0.033));

  // --- measured articulation ------------------------------------------------
  // When the analyser supplied a viseme, use it. The mouth then reflects which
  // sounds are being made (a /p/ closure, an /s/, an open /a/) rather than how
  // loud the frame is, which is the difference between lip sync and a flap.
  if (now.vis) {
    const blend = (a, b) => (b && b.vis ? (a + b.vis.open) * 0.5 : a);
    const lead = now.vis;
    const prev = before.vis;
    const next = after.vis;
    // a little temporal shaping only: the analyser already smoothed coarticulation
    const open = clamp01(lead.open * 0.86 + blend(lead.open, next) * 0.14);
    const wide = clamp01(prev && next ? (lead.wide * 0.7 + prev.wide * 0.15 + next.wide * 0.15) : lead.wide);
    const round = clamp01(prev && next ? (lead.round * 0.7 + prev.round * 0.15 + next.round * 0.15) : lead.round);
    const teeth = clamp01(lead.teeth);
    const press = clamp01(lead.press);
    return { open, wide, round, teeth, press };
  }

  // Jaw: fast attack (a syllable is already open when its energy peaks) and a
  // slower release, plus a little anticipation from the frame ahead so the mouth
  // is not permanently one frame behind the voice.
  const attack = Math.max(now.open, after.open * 0.9);
  const release = Math.max(now.open, before.open * 0.55);
  // A held loud note must not pin the jaw at 1.0 for four seconds, but the mouth
  // also has to *open* on a loud frame: normalising to a mean level left the
  // face nearly still. The energy is mapped through a floor-and-ceiling window
  // and the fast fluctuation of speech supplies the rest of the articulation.
  const motion = Math.abs(now.open - before.open) + Math.abs(after.open - now.open) * 0.6;
  const articulation = clamp01(motion * 2.6);
  const level = clamp01((Math.max(attack * 0.75 + release * 0.25, now.open) - 0.10) / 0.80);
  // The opening floor only applies while there is speech to open for; silence is
  // still an explicit closure, never a half-open mouth.
  const voiced = clamp01((now.open - 0.06) / 0.22);
  const jaw = clamp01((0.18 + level * 0.72) * clamp01(0.78 + 0.22 * articulation)) * voiced;

  // Silence is not "closed by default": it is an explicit closure, which is
  // what makes a /m/ at the end of a word read as a mouth that shut.
  if (jaw < 0.08) {
    return { open: 0.02, wide: 0.28, round: 0.10, teeth: 0, press: 0.9 };
  }

  const bright = clamp01(now.bright * 0.7 + Math.max(now.bright, after.bright) * 0.3);
  const wide = lerp(0.16, 0.94, bright) * lerp(0.55, 1, clamp01(jaw * 1.6));
  const round = lerp(0.82, 0.10, bright);
  const teeth = clamp01((bright - 0.35) * 1.6) * clamp01(jaw * 1.4) * 0.85;
  const press = clamp01((0.22 - jaw) / 0.22) * 0.7;
  return { open: jaw, wide, round, teeth, press };
}

/**
 * Speaking layer: the mouth comes from `mouthFromAudio`, and the head/neck/chest
 * get the accents speech actually produces — a small nod per stressed syllable,
 * a brow lift, shoulders that move with emphasis.
 */
export function speechLayer(pose, t, timeline, opts = {}) {
  const viseme = typeof opts.envelope === 'function'
    ? mouthFromAudio(t, opts.envelope)
    : sampleVisemes(timeline, t);
  const energy = clamp01((viseme.open || 0) * 1.4);
  // Syllable-synchronous head accent: the head lifts on the attack and settles
  // on the release, so the neck is never still while the mouth is working.
  const accent = clamp01((viseme.open || 0)) * 0.085;
  const settle = Math.sin(t * 2.3) * 0.012;
  pose.head = (pose.head || 0) + accent + settle;
  pose.neck = (pose.neck || 0) + accent * 0.45;
  pose.chest = (pose.chest || 0) + accent * 0.35;
  // shoulders and free arm take a small counter-beat: the body answers speech
  pose.armR = (pose.armR || 0) - accent * 0.22;
  pose.forearmR = (pose.forearmR || 0) + accent * 0.30;
  pose.spine = (pose.spine || 0) + accent * 0.18;
  pose.browRaise = (opts.brow === undefined ? 0.15 : opts.brow) + clamp01(viseme.open || 0) * 0.45;
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
    hips = { x: spec.hipX || 0, y: groundY - (HIP_HEIGHT + SOLE) * scale - bob, scale };
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
    viseme = speechLayer(pose, t, spec.speech.timeline, {
      brow: spec.speech.brow,
      envelope: spec.speech.envelope,
    });
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
