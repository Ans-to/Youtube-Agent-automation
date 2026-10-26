/**
 * The director: which transition, and why.
 *
 * The kit has sixteen transitions and that was the problem. Nothing chose them;
 * `allocate()` dealt one per shot from a pool, which is how a film about a phone
 * company ended up cutting through horizontal blinds and a luma-keyed grid of
 * cells. Those are clever. They are not what an editor does, and a viewer reads
 * "clever" as amateur.
 *
 * A documentary cuts for a reason, and there are only a handful of reasons:
 *
 *   beat      something changes. Cut. Hard, on the word.
 *   time      time passes, or the film stays in the same place and pulls back.
 *             Dissolve, slow.
 *   chapter   a new section of the story. Dip to paper and come back.
 *   era       a period opens - a date, a place, a company before it was a company.
 *             Iris.
 *   motion    the film physically continues in one direction. Wipe, or push.
 *   rack      the camera moves while the subject changes. A zoom dissolve.
 *   momentum  the film pushes on. Both shots travel together.
 *
 * Each role names the transitions that express it, in order of preference. The
 * director takes the next unused kind, so the rule from the owner - never the
 * same technique twice in one film - still holds, and it holds *within* a
 * professional vocabulary instead of across sixteen gimmicks.
 */

export const ROLES = {
  beat: {
    why: 'something changes',
    kinds: ['cut'],
  },
  time: {
    why: 'time passes in the same place',
    kinds: ['dissolve'],
  },
  chapter: {
    why: 'a new section begins',
    kinds: ['fade'],
  },
  era: {
    why: 'a period opens',
    kinds: ['iris'],
  },
  motion: {
    why: 'the film continues in one direction',
    kinds: ['wipe', 'push'],
  },
  rack: {
    why: 'the camera moves while the subject changes',
    kinds: ['rack'],
  },
  momentum: {
    why: 'the film pushes on and does not stop',
    kinds: ['push'],
  },
};

/** The order a director reaches for them when a role's first choice is spent. */
const FALLBACK = ['dissolve', 'cut', 'fade', 'wipe', 'push', 'iris', 'rack'];

/**
 * Deal transitions by role, never repeating a kind.
 *
 * @param {Array} shots  each may carry `transitionRole` and `roleWhy`
 * @returns {Array} the shots with a `transition` token on every shot but the first
 */
export function direct(shots) {
  const used = new Set();
  const reasons = [];
  const out = shots.map((shot, index) => {
    if (index === 0) return { ...shot, transition: null, transitionWhy: 'opening frame' };
    const role = shot.transitionRole || 'beat';
    const entry = ROLES[role];
    if (!entry) throw new Error(`unknown transition role ${role}`);
    let kind = entry.kinds.find((k) => !used.has(k));
    let why = entry.why;
    if (!kind) {
      kind = FALLBACK.find((k) => !used.has(k));
      why = `${entry.why} (a ${kind}, because ${entry.kinds[0]} was already used)`;
    }
    if (!kind) throw new Error(`out of transitions at ${shot.id}; there are more joins than kinds`);
    used.add(kind);
    reasons.push({ at: shot.id, kind, why, role });
    const token = transitionToken(kind, shot, shots[index - 1]);
    return { ...shot, transition: token, transitionWhy: why };
  });
  return Object.assign(out, { reasons });
}

/** A kind plus the parameterisation the shot asks for. */
function transitionToken(kind, shot, previous) {
  const labels = {
    cut: 'cut',
    dissolve: 'dissolve',
    // The label leads with the kind, always: `fade-paper`, not `dip-paper`, so a
    // shot list can be parsed and so a reviewer can see what the join actually is.
    fade: `fade-${shot.dip || 'paper'}`,
    iris: 'iris',
    rack: 'rack',
  };
  const options = {};
  if (kind === 'fade') {
    // Dip through the ground being left, not a colour in between. A cream wash
    // over an ink shot produces mid-grey, which reads as a grading error; dipping
    // to the outgoing shot's own paper and rising into the next one is how a
    // chapter break is actually done.
    options.colour = shot.dipColour
      || (previous && previous.palette && previous.palette.paper)
      || '#F1E7D4';
  }
  if (kind === 'wipe' || kind === 'push') {
    const spec = shot.roleMotion || {};
    options.direction = spec.direction || 'left';
    options.angle = spec.angle || 0;
    // A wipe labels itself by the direction the seam travels, not by an angle the
    // viewer cannot see in a shot list.
    return { kind, label: `${kind}-${options.direction}`, options };
  }
  return { kind, label: labels[kind] || kind, options };
}

export default direct;
