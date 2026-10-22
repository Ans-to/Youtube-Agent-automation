/**
 * A 2D character rig: hierarchy, analytic IK, springs and pose blending.
 *
 * This module is pure maths — no canvas, no DOM — so it can be tested in
 * isolation and reused by any renderer. Angles are radians, local to the parent
 * bone, and measured in canvas space (0 points +x, +pi/2 points down).
 *
 * Bone convention:
 *   origin = parent.end + rotate(offset, parentWorldAngle - parentRestWorld)
 *   end    = origin + length * (cos(world), sin(world))
 *
 * Offsets are authored in the rest pose, so a bone attached to the left shoulder
 * stays on the left shoulder when the chest leans, without re-authoring numbers.
 */

export const TAU = Math.PI * 2;

export const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
export const lerp = (a, b, t) => a + (b - a) * t;
export const span = (t, a, b) => clamp01((t - a) / (b - a));
export const mix = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];

/** Easing registry. There is no linear curve here on purpose. */
export const ease = {
  outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inExpo: (x) => (x <= 0 ? 0 : Math.pow(2, 10 * (x - 1))),
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  inCubic: (x) => x * x * x,
  inOutCubic: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outQuart: (x) => 1 - Math.pow(1 - x, 4),
  outBack: (x) => (x <= 0 ? 0 : 1 + 2.4 * Math.pow(x - 1, 3) + 1.6 * Math.pow(x - 1, 2)),
  anticipate: (x) => (x <= 0 ? 0 : x < 0.22
    ? -0.16 * Math.sin((x / 0.22) * Math.PI)
    : ease.outCubic((x - 0.22) / 0.78)),
  /** Overshoot then settle: the standard "arrive with weight" curve. */
  settle: (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    return 1 - Math.exp(-6.2 * x) * Math.cos(7.4 * x);
  },
};

/**
 * Rest skeleton. `rest` is the local angle in the default standing pose;
 * `offset` is where the bone attaches inside its parent's rest frame.
 */
export const BONES = [
  // hips sit at the origin of the figure; everything above is negative y
  { name: 'hips', parent: null, length: 0, rest: 0, offset: [0, 0] },
  { name: 'spine', parent: 'hips', length: 172, rest: -Math.PI / 2, offset: [0, 0] },
  { name: 'chest', parent: 'spine', length: 208, rest: 0, offset: [0, 0] },
  { name: 'neck', parent: 'chest', length: 34, rest: 0, offset: [0, 0] },
  { name: 'head', parent: 'neck', length: 290, rest: 0, offset: [0, 0] },

  // Shoulders attach 46px below the neck base and 132px out, so the deltoid
  // lands on the shoulder line instead of the jaw. Left is +x on screen.
  { name: 'shoulderL', parent: 'chest', length: 54, rest: Math.PI * 0.5, offset: [84, 32] },
  { name: 'armL', parent: 'shoulderL', length: 225, rest: Math.PI * 0.5 - 0.12, offset: [0, 0] },
  { name: 'forearmL', parent: 'armL', length: 205, rest: 0.12, offset: [0, 0] },
  { name: 'handL', parent: 'forearmL', length: 86, rest: 0.05, offset: [0, 0] },

  { name: 'shoulderR', parent: 'chest', length: 54, rest: -Math.PI * 0.5, offset: [-84, 32] },
  { name: 'armR', parent: 'shoulderR', length: 225, rest: -Math.PI * 0.5 + 0.12, offset: [0, 0] },
  { name: 'forearmR', parent: 'armR', length: 205, rest: -0.12, offset: [0, 0] },
  { name: 'handR', parent: 'forearmR', length: 86, rest: -0.05, offset: [0, 0] },

  { name: 'thighL', parent: 'hips', length: 220, rest: Math.PI / 2, offset: [72, 10] },
  { name: 'shinL', parent: 'thighL', length: 226, rest: 0, offset: [0, 0] },
  { name: 'footL', parent: 'shinL', length: 128, rest: -Math.PI / 2, offset: [0, 0] },

  { name: 'thighR', parent: 'hips', length: 220, rest: Math.PI / 2, offset: [-72, 10] },
  { name: 'shinR', parent: 'thighR', length: 226, rest: 0, offset: [0, 0] },
  { name: 'footR', parent: 'shinR', length: 128, rest: -Math.PI / 2, offset: [0, 0] },
];

export const BONE_INDEX = new Map(BONES.map((b, i) => [b.name, i]));

/** Bones in draw order, back arm/leg first, head last. Renderers can rely on it. */
export const DRAW_ORDER = [
  'armR', 'forearmR', 'handR', 'thighR', 'shinR', 'footR',
  'spine', 'chest', 'hips',
  'thighL', 'shinL', 'footL',
  'neck', 'head',
  'armL', 'forearmL', 'handL', 'shoulderL', 'shoulderR',
];

/** Rest world angle per bone, computed once. */
const REST_WORLD = (() => {
  const out = {};
  for (const bone of BONES) {
    out[bone.name] = bone.parent ? out[bone.parent] + bone.rest : bone.rest;
  }
  return out;
})();

export const restWorld = (name) => REST_WORLD[name];

/** A neutral standing pose: every bone at its rest angle. */
export function neutralPose() {
  const pose = {};
  for (const bone of BONES) pose[bone.name] = 0;
  return pose;
}

/**
 * Solve the whole skeleton for a pose.
 * @param {Record<string, number>} pose local angle offsets added to each rest angle
 * @param {{x:number,y:number,angle?:number,scale?:number}} root hips placement
 * @returns {Record<string,{origin:number[],end:number[],angle:number,world:number}>}
 */
export function solve(pose, root = { x: 0, y: 0, angle: 0, scale: 1 }) {
  const out = {};
  const rootAngle = root.angle || 0;
  const rootScale = root.scale === undefined ? 1 : root.scale;
  for (const bone of BONES) {
    const local = (pose[bone.name] || 0) + bone.rest;
    if (!bone.parent) {
      const origin = [root.x, root.y];
      const world = rootAngle + local;
      out[bone.name] = {
        name: bone.name,
        length: bone.length * rootScale,
        restLength: bone.length,
        scale: rootScale,
        origin,
        end: [origin[0] + Math.cos(world) * bone.length * rootScale,
          origin[1] + Math.sin(world) * bone.length * rootScale],
        angle: local,
        world,
      };
      continue;
    }
    const parent = out[bone.parent];
    const parentBone = BONES[BONE_INDEX.get(bone.parent)];
    const turn = parent.world - (REST_WORLD[bone.parent] + rootAngle);
    const ox = bone.offset[0] * rootScale;
    const oy = bone.offset[1] * rootScale;
    const origin = [
      parent.end[0] + ox * Math.cos(turn) - oy * Math.sin(turn),
      parent.end[1] + ox * Math.sin(turn) + oy * Math.cos(turn),
    ];
    const world = parent.world + local;
    out[bone.name] = {
      name: bone.name,
      length: bone.length * rootScale,
      restLength: bone.length,
      scale: rootScale,
      parent: bone.parent,
      parentLength: parentBone.length,
      origin,
      end: [origin[0] + Math.cos(world) * bone.length * rootScale,
        origin[1] + Math.sin(world) * bone.length * rootScale],
      angle: local,
      world,
    };
  }
  return out;
}

/**
 * Analytic two-bone IK.
 *
 * Returns the *local* rotations that put the end of `b` on `target`, assuming
 * the chain hangs off `parentName`. `bend` is +1 or -1 and picks the elbow side;
 * without it the joint would pop between solutions.
 */
export function twoBoneIK(solved, upperName, lowerName, target, bend = 1) {
  const upper = BONES[BONE_INDEX.get(upperName)];
  const lower = BONES[BONE_INDEX.get(lowerName)];
  const parentWorld = solved[upper.parent] ? solved[upper.parent].world : 0;
  const origin = solved[upperName].origin;

  const dx = target[0] - origin[0];
  const dy = target[1] - origin[1];
  const rawDist = Math.hypot(dx, dy);
  // solved lengths are already world-space (root scale applied); the authored
  // BONES table is unscaled, so read the lengths off the solve, not the table
  const l1 = solved[upperName].length;
  const l2 = solved[lowerName].length;
  const dist = Math.min(Math.max(rawDist, Math.abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3);

  const toTarget = Math.atan2(dy, dx);
  const cosA = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist);
  const a = Math.acos(Math.min(1, Math.max(-1, cosA)));
  const upperWorld = toTarget - bend * a;

  const joint = [origin[0] + Math.cos(upperWorld) * l1, origin[1] + Math.sin(upperWorld) * l1];
  const lowerWorld = Math.atan2(target[1] - joint[1], target[0] - joint[0]);

  return {
    [upperName]: upperWorld - parentWorld - upper.rest,
    [lowerName]: lowerWorld - upperWorld - lower.rest,
    joint,
    reachable: rawDist <= l1 + l2,
  };
}

/**
 * Critically-damped spring, integrated at a fixed step so a frame rendered at
 * 30 fps and the same frame re-rendered later always land on the same value.
 */
export function springStep(state, target, dt, stiffness = 120, damping = 18) {
  const accel = (target - state.value) * stiffness - state.velocity * damping;
  state.velocity += accel * dt;
  state.value += state.velocity * dt;
  return state;
}

/** Advance a spring from `from` to `to` over `seconds`, deterministically. */
export function springSettle(from, to, seconds, stiffness = 120, damping = 18, step = 1 / 240) {
  const state = { value: from, velocity: 0 };
  const steps = Math.max(1, Math.round(seconds / step));
  for (let i = 0; i < steps; i += 1) springStep(state, to, step, stiffness, damping);
  return state.value;
}

// ------------------------------------------------------------------ visemes
/**
 * Mouth shapes. Values are normalised: `open` is jaw drop, `wide` is corner
 * spread, `round` is lip rounding, `teeth` shows the upper row, `press` closes.
 */
export const VISEMES = {
  REST: { open: 0.05, wide: 0.30, round: 0.10, teeth: 0.0, press: 0.25 },
  AA: { open: 0.85, wide: 0.45, round: 0.10, teeth: 0.15, press: 0.0 },
  AE: { open: 0.62, wide: 0.62, round: 0.05, teeth: 0.30, press: 0.0 },
  E: { open: 0.34, wide: 0.78, round: 0.02, teeth: 0.55, press: 0.0 },
  I: { open: 0.24, wide: 0.86, round: 0.00, teeth: 0.60, press: 0.0 },
  O: { open: 0.60, wide: 0.12, round: 0.86, teeth: 0.05, press: 0.0 },
  U: { open: 0.30, wide: 0.05, round: 0.95, teeth: 0.0, press: 0.0 },
  MBP: { open: 0.00, wide: 0.26, round: 0.05, teeth: 0.0, press: 1.0 },
  FV: { open: 0.10, wide: 0.42, round: 0.02, teeth: 0.65, press: 0.35 },
  L: { open: 0.30, wide: 0.40, round: 0.05, teeth: 0.35, press: 0.0 },
  WQ: { open: 0.18, wide: 0.08, round: 0.80, teeth: 0.10, press: 0.0 },
};

/** Blend two viseme parameter sets. */
export function blendViseme(a, b, t) {
  const out = {};
  for (const key of Object.keys(VISEMES.REST)) out[key] = lerp(a[key], b[key], t);
  return out;
}

/**
 * Sample a viseme timeline. Events are `{ at, viseme, hold }`; between events the
 * mouth eases toward the next shape rather than jumping, and closes to REST
 * after `hold` seconds.
 */
export function sampleVisemes(timeline, t) {
  if (!timeline || !timeline.length) return { ...VISEMES.REST };
  let previous = { at: -1, viseme: 'REST', hold: 0.1 };
  for (const event of timeline) {
    if (event.at > t) break;
    previous = event;
  }
  const shape = VISEMES[previous.viseme] || VISEMES.REST;
  const openFor = (previous.hold || 0.1);
  const age = t - previous.at;
  // close briskly after the hold, so consonants read as closures
  const close = clamp01((age - openFor) / 0.06);
  const open = clamp01(age / 0.04);
  const amount = open * (1 - close);
  return blendViseme(VISEMES.REST, shape, amount);
}

/** Blink amount in [0,1]; 1 is fully closed. Deterministic given the schedule. */
export function blinkAt(times, t, duration = 0.14) {
  let value = 0;
  for (const at of times) {
    const local = (t - at) / duration;
    if (local <= 0 || local >= 1) continue;
    value = Math.max(value, Math.sin(Math.PI * local));
  }
  return value;
}

/**
 * Plant a foot: return the local ankle angles that put the foot flat on a given
 * ground height, with the ankle at `x`. Uses the leg IK, so knees bend the right
 * way and the character never floats or sinks.
 */
export function plantFoot(solved, side, ankleX, groundY, toe = 0) {
  const upper = side === 'L' ? 'thighL' : 'thighR';
  const lower = side === 'L' ? 'shinL' : 'shinR';
  const foot = side === 'L' ? 'footL' : 'footR';
  const S = solved[upper].scale === undefined ? 1 : solved[upper].scale;
  const hip = solved[upper].origin;
  const clearance = 34 * S; // ankle sits this far above the floor
  let tx = ankleX;
  let ty = groundY - clearance;

  // if the ankle is out of reach, pull it in rather than letting the solve clamp
  // silently and leave the foot floating somewhere else
  const dx = tx - hip[0];
  const dy = ty - hip[1];
  const dist = Math.hypot(dx, dy) || 1;
  const reach = (BONES[BONE_INDEX.get(upper)].length + BONES[BONE_INDEX.get(lower)].length) * S * 0.995;
  if (dist > reach) {
    tx = hip[0] + (dx / dist) * reach;
    ty = hip[1] + (dy / dist) * reach;
  }

  const ik = twoBoneIK(solved, upper, lower, [tx, ty], side === 'L' ? 1 : -1);
  // Compose the shin's angle from the *new* knee, not the one the leg had
  // before the IK ran. Using the pre-IK world left the planted foot slightly
  // rolled whenever the solve and the pose disagreed, which is exactly what
  // happens as soon as the leg proportions change.
  const upperBone = BONES[BONE_INDEX.get(upper)];
  const lowerBone = BONES[BONE_INDEX.get(lower)];
  const hipParent = upperBone.parent;
  const upperWorld = (hipParent ? solved[hipParent].world : 0) + ik[upper] + upperBone.rest;
  const parentWorld = upperWorld + ik[lower] + lowerBone.rest;
  const footRest = BONES[BONE_INDEX.get(foot)].rest;
  // world 0 is flat on the floor and pointing forward; +toe lifts the toes
  return { ...ik, [foot]: toe - parentWorld - footRest };
}
