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

/** Straight-leg reach from hip to ankle, measured from the rest skeleton. */
const LEG_LENGTH = (() => {
  const rest = solve({}, { x: 0, y: 0, scale: 1 });
  return rest.thighL.length + rest.shinL.length;
})();

/**
 * How far a foot travels forward from the hips, as a fraction of leg length.
 *
 * This is not a taste knob: the hips drop by `sqrt(leg^2 - step^2)` on every
 * stride, so a long step over-bends the knee and a short one makes the figure
 * totter. 0.38 leaves a visible bend at the widest point of the stride.
 */
const STEP_FRACTION = 0.38;

/**
 * Half the distance between the two hip sockets, at scale 1.
 *
 * Feet are placed under their own socket rather than at some chosen width. Any
 * other width makes the IK solve a sideways knee: with the leg almost straight, a
 * few pixels of lateral error bows the knee tens of pixels — the duck stance.
 */
const SOCKET_HALF = (() => {
  const rest = solve({}, { x: 0, y: 0, scale: 1 });
  return Math.abs(rest.thighL.origin[0] - rest.thighR.origin[0]) / 2;
})();


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
/**
 * Linear blend of two poses. Used to cross-fade a walk into a stand.
 *
 * Every key either pose defines is present in the result, so the skeleton never
 * sees a missing bone and fall back to its rest angle mid-transition.
 */
export function blendPoses(a, b, k) {
  const out = {};
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    const av = a[key] === undefined ? 0 : a[key];
    const bv = b[key] === undefined ? 0 : b[key];
    out[key] = av * k + bv * (1 - k);
  }
  return out;
}

export function walkPose(t, {
  stride = 1.1, hipX = 0, groundY = 0, scale = 1, speed = 1,
  distance = null, step: stepArg = null,
} = {}) {
  const pose = {};
  // The rig is drawn front-on, so the walk is a front-view step cycle: the feet
  // keep their own side of the body and take turns leaving the floor, the hips
  // drop when both feet are down and sway over whichever leg is carrying the
  // weight, and the arms swing. A side-on cycle — feet trading places fore and
  // aft — scissors the legs through each other when the figure faces camera.
  //
  // The cycle is advanced by distance travelled when the caller knows it, so the
  // cadence follows the ground speed instead of the clock. Elapsed time is used
  // for a walk in place.
  const step = stepArg === null ? LEG_LENGTH * STEP_FRACTION * scale * speed : stepArg;
  const cycleLength = step * 4;
  const phase = distance === null
    ? (t / stride) % 1
    : ((distance % cycleLength) / cycleLength + 1) % 1;

  const leg = LEG_LENGTH * scale;
  const halfStance = SOCKET_HALF * scale;   // a foot sits under its own hip socket
  const liftHeight = leg * 0.085;
  // The pelvis never rises above the height at which the legs are straight: any
  // higher and the IK cannot reach, so the sole floats. The bob therefore goes
  // downward only, which is also how a walk works — you are lowest when both feet
  // are down. Kept small on purpose: in a front view a knee can only bend
  // sideways, so a deep bob would bow both knees out like a duck.
  const bobAmount = leg * 0.008;

  // 60% of the cycle on the floor, 40% in the air, so there is a moment when both
  // feet are down — that is where the body is lowest.
  const DUTY = 0.62;
  // Eased, not sine: a sine lift leaves the ground at full speed, which reads as
  // a jerk at toe-off. Squared sine starts and ends at rest.
  const lift = (offset) => {
    const p = (phase + offset) % 1;
    if (p < DUTY) return 0;
    const swing = (p - DUTY) / (1 - DUTY);
    const ease = Math.sin(swing * Math.PI) ** 2;
    return ease * liftHeight;
  };
  // How much of its length each leg loses while swinging: the drawn leg is pulled
  // toward the hip, so the foot leaves the floor without the knee bowing outward.
  const shorten = (offset) => 1 - lift(offset) / leg;
  // Squared, so the swing starts and ends at rest. A plain sine begins the swing
  // at full speed, and the hand — at the end of two long bones — turned that into
  // a visible snap: measured at 19 px per frame squared, seven times the head.
  const swingCurve = (offset) => {
    const p = (phase + offset) % 1;
    return p < DUTY ? 0 : Math.sin(((p - DUTY) / (1 - DUTY)) * Math.PI) ** 2;
  };

  // Weight shift: the pelvis travels over the supporting foot and back.
  const sway = Math.sin(phase * Math.PI * 2) * halfStance * 0.22;
  const hipRootX = hipX + sway;
  const bob = bobAmount * (0.5 + 0.5 * Math.cos(phase * Math.PI * 4));
  const hipY = groundY - SOLE * scale - leg + bob;

  const swing = Math.sin(phase * Math.PI * 2);
  pose.hips = swing * 0.02 + sway / Math.max(1, halfStance) * 0.05;
  pose.spine = -swing * 0.03;
  pose.chest = swing * 0.015;
  breathe(pose, t, 0.6);
  pose.head = -swing * 0.02;
  // Arms counter-swing. From the front the visible part is the elbow opening, so
  // the forearm leads and the upper arm follows it.
  pose.armL = 0.05 + swing * 0.07;
  pose.armR = -0.05 - swing * 0.07;
  // A calm arm. The first pass swung the forearm twice as far and the hand — at
  // the end of two long bones — whipped through the frame at 64 design px per
  // frame, five times walking speed.
  pose.forearmL = 0.10 + swingCurve(0.5) * 0.15;
  pose.forearmR = -0.10 - swingCurve(0) * 0.15;

  const ankle = SOLE * scale;
  const wantAnkleY = groundY - ankle;
  const upper = { armL: pose.armL, armR: pose.armR, forearmL: pose.forearmL, forearmR: pose.forearmR,
                  spine: pose.spine, chest: pose.chest, hips: pose.hips, head: pose.head,
                  shoulderL: pose.shoulderL, shoulderR: pose.shoulderR, neck: pose.neck };

  const build = (rootY) => {
    const draft = { ...upper };
    const base = solve(draft, { x: 0, y: 0, scale });
    // Feet are anchored to the ground the figure is walking over, not to the
    // swaying pelvis. Attaching them to the hip sockets — which move with the
    // weight shift — dragged a "planted" foot 22 px per frame, the exact skate the
    // distance-driven cycle exists to remove. The pelvis sways over a foot that
    // stays put; that is what a weight shift is.
    // `thighL` sits on the +x side of this rig, so it takes the +x foot.
    // Both feet are solved to the floor. A foot that is in the air is not lifted
    // by the solver: aiming the IK at a raised target bends the knee sideways,
    // because in a flat front view a bent leg has nowhere to go but out — measured
    // at 44% of the thigh, which reads as knock-knees. The lift is drawn instead,
    // by shortening that leg about its hip (see `legShorten`), which is exactly
    // the shortcut a 2D animator takes to push a leg toward the camera.
    // Both targets are on the floor, so neither knee has anywhere to bend.
    Object.assign(draft, twoBoneIK(base, 'thighL', 'shinL',
      [halfStance, groundY - rootY - ankle], 1));
    Object.assign(draft, twoBoneIK(base, 'thighR', 'shinR',
      [-halfStance, groundY - rootY - ankle], -1));
    // The foot stays flat to the floor; the drawing rolls it during the swing.
    draft.footL = -solveFoot(base, 'shinL', draft, 0);
    draft.footR = -solveFoot(base, 'shinR', draft, 0);
    return draft;
  };

  let rootY = hipY;
  let built = build(rootY);
  // The hip sockets do not sit on the pelvis root, so the first height is a few
  // pixels off. Settle it against the property that actually matters: a standing
  // leg is straight, so the socket-to-ankle distance equals the leg. Measuring
  // the ankle's height instead let the leg be a fraction too long, and the IK
  // answered that by bowing the knee sideways — visible as knock-knees.
  const straight = leg * 0.997;
  for (let pass = 0; pass < 4; pass += 1) {
    const trial = solve(built, { x: hipRootX, y: rootY, scale });
    const reach = Math.max(
      Math.hypot(trial.footL.origin[0] - trial.thighL.origin[0], trial.footL.origin[1] - trial.thighL.origin[1]),
      Math.hypot(trial.footR.origin[0] - trial.thighR.origin[0], trial.footR.origin[1] - trial.thighR.origin[1]),
    );
    const error = reach - straight;
    if (Math.abs(error) < 0.2) break;
    rootY += error;
    built = build(rootY);
  }
  Object.assign(pose, built);
  return {
    pose,
    hips: { x: hipRootX, y: rootY, scale },
    legShorten: { L: shorten(0), R: shorten(0.5) },
  };
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
  // Beside the head, not across it. At 300 the hand sat only 160 units outside
  // the shoulder, which put the forearm over the face — from the front that reads
  // as scratching, not waving. 540 clears the head circle (radius ~240) entirely.
  const target = [540 * scale, -1000 * scale];
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

  // Walk and idle are blended rather than switched on. A hard switch at the ends
  // of a walk cycle pops: every joint jumps by the difference between the two
  // poses in a single frame.
  const walkWeight = spec.walkWeight === undefined ? (mode === 'walk' ? 1 : 0) : clamp01(spec.walkWeight);
  const idleHips = () => {
    const bob = Math.sin(t * 0.55 * Math.PI * 2) * 5 * scale;
    return { x: spec.hipX || 0, y: groundY - (HIP_HEIGHT + SOLE) * scale - bob, scale };
  };

  let pose;
  let hips;
  let legShorten = { L: 1, R: 1 };
  if (walkWeight >= 0.999) {
    const walked = walkPose(t, {
      stride: spec.stride || 1.15,
      hipX: spec.hipX || 0,
      groundY,
      scale,
      speed: spec.speed || 1,
      distance: spec.distance === undefined ? null : spec.distance,
      step: spec.step === undefined ? null : spec.step,
    });
    pose = walked.pose;
    hips = { x: walked.hips.x, y: walked.hips.y, scale };
    legShorten = walked.legShorten;
  } else if (walkWeight <= 0.001) {
    pose = idlePose(t, { breathe: spec.breathe });
    hips = idleHips();
  } else {
    const walked = walkPose(t, {
      stride: spec.stride || 1.15,
      hipX: spec.hipX || 0,
      groundY,
      scale,
      speed: spec.speed || 1,
      distance: spec.distance === undefined ? null : spec.distance,
      step: spec.step === undefined ? null : spec.step,
    });
    const idle = idlePose(t, { breathe: spec.breathe });
    pose = blendPoses(walked.pose, idle, walkWeight);
    // A leg that is half in the walk is half as shortened: the same cross-fade the
    // pose gets, applied to the drawing.
    legShorten = {
      L: walked.legShorten.L * walkWeight + (1 - walkWeight),
      R: walked.legShorten.R * walkWeight + (1 - walkWeight),
    };
    const rest = idleHips();
    // Both axes have to come from the same blend. Blending only the height left
    // the pelvis's side-to-side weight shift to be switched on and off, which
    // dropped twenty pixels of travel into a single frame — every bone in the
    // figure spiked at once when the fade began.
    hips = {
      x: walked.hips.x * walkWeight + rest.x * (1 - walkWeight),
      y: walked.hips.y * walkWeight + rest.y * (1 - walkWeight),
      scale,
    };
  }

  // Acting: small angles on the existing joints. A figure that stands to
  // attention through a whole cut reads as a puppet however good its mouth is.
  if (spec.weight) {
    pose.hips = (pose.hips || 0) + spec.weight;
    pose.spine = (pose.spine || 0) - spec.weight * 0.7;
    pose.chest = (pose.chest || 0) + spec.weight * 0.3;
  }
  if (spec.nod) {
    pose.head = (pose.head || 0) + spec.nod;
    pose.neck = (pose.neck || 0) + spec.nod * 0.5;
  }
  if (spec.lean) {
    pose.spine = (pose.spine || 0) + spec.lean;
    pose.chest = (pose.chest || 0) + spec.lean * 0.4;
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
    legShorten,
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
