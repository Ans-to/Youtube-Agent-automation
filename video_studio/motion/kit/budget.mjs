/**
 * Never twice in the film.
 *
 * The owner's rule is absolute: no transition, entrance, behaviour, exit or type
 * move may appear twice anywhere in the video. Not "not twice in a row" - once.
 *
 * A rule like that is only real if the vocabulary is bigger than the shot count,
 * so this module does two things:
 *
 *   1. expands each technique into its genuinely distinct parameterisations -
 *      a wipe at eight angles is eight transitions, a blind at four strip counts
 *      is four - which turns 16 transition kinds into 45 usable joins;
 *   2. allocates them across the whole film, refusing to reuse a token, and
 *      fails loudly with the exact shortfall if the film asks for more than the
 *      vocabulary can supply.
 *
 * Refusing is the important part. A silent fallback to `cut` would mean the rule
 * held only until nobody was looking.
 */

const hash = (s) => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
};

/** Every distinct join the transition layer can actually draw. */
function transitionPool() {
  const out = [];
  const angles = [0, 45, 90, 135, 180, 225, 270, 315];
  angles.forEach((angle) => out.push({ kind: 'wipe', label: `wipe@${angle}`, options: { angle } }));
  angles.forEach((angle) => out.push({ kind: 'push', label: `push@${angle}`, options: { angle } }));
  [5, 7, 9, 11].forEach((count) => {
    out.push({ kind: 'blinds', label: `blinds-v${count}`, options: { count, vertical: true } });
    out.push({ kind: 'blinds', label: `blinds-h${count}`, options: { count, vertical: false } });
  });
  out.push({ kind: 'split', label: 'split-v', options: { vertical: true } });
  out.push({ kind: 'split', label: 'split-h', options: { vertical: false } });
  ['circle', 'wedge', 'band'].forEach((shape) => out.push({ kind: 'shape-wipe', label: `shape-wipe-${shape}`, options: { shape } }));
  [12, 20, 26, 34].forEach((cells) => out.push({ kind: 'luma', label: `luma-${cells}`, options: { cells } }));
  out.push({ kind: 'fade', label: 'fade-paper', options: { colour: '#FAF8F3' } });
  out.push({ kind: 'fade', label: 'fade-ink', options: { colour: '#12233F' } });
  out.push({ kind: 'flash', label: 'flash-paper', options: { colour: '#FFFFFF' } });
  out.push({ kind: 'flash', label: 'flash-ink', options: { colour: '#12233F' } });
  ['cut', 'dissolve', 'iris', 'focus', 'whip-pan', 'match-cut', 'zoom-through', 'type-led']
    .forEach((kind) => out.push({ kind, label: kind, options: {} }));
  return out;
}

/** Entrances, with the direction and shape variants that are visibly different. */
function entrancePool() {
  const out = [];
  ['left', 'right', 'up', 'down'].forEach((direction) => {
    out.push({ kind: 'wipe', label: `wipe-${direction}`, options: { direction } });
  });
  ['left', 'right', 'up', 'down'].forEach((direction) => {
    out.push({ kind: 'draw-on', label: `draw-on-${direction}`, options: { direction } });
  });
  ['circle', 'wedge', 'band'].forEach((shape) => {
    out.push({ kind: 'shape-mask', label: `shape-mask-${shape}`, options: { shape } });
  });
  [5, 9].forEach((cols) => out.push({ kind: 'shatter', label: `shatter-${cols}`, options: { cols, rows: 3 } }));
  [0.35, 0.55, 0.85].forEach((reach) => out.push({ kind: 'iris', label: `iris-${reach}`, options: { reach } }));
  [0.05, 0.08, 0.12, 0.16, 0.22, 0.28, 0.40]
    .forEach((distance) => out.push({ kind: 'rise', label: `rise-${distance}`, options: { distance } }));
  [0.4, 0.6, 0.8, 1.4, 1.8]
    .forEach((amount) => out.push({ kind: 'squash', label: `squash-${amount}`, options: { amount } }));
  [0.06, 0.10, 0.18].forEach((slide) => out.push({ kind: 'assembly', label: `assembly-${slide}`, options: { slide } }));
  [0.14, 0.22, 0.34].forEach((scale) => out.push({ kind: 'stamp', label: `stamp-${scale}`, options: { scale } }));
  ['cut', 'scan', 'slit-scan', 'whip'].forEach((kind) => out.push({ kind, label: kind, options: {} }));
  return out;
}

function behaviourPool() {
  const out = [];
  [0.012, 0.03].forEach((amount) => out.push({ kind: 'drift', label: `drift-${amount}`, options: { amount } }));
  [0.04, 0.09].forEach((amount) => out.push({ kind: 'push', label: `push-${amount}`, options: { amount } }));
  [0.25, 0.5].forEach((depth) => out.push({ kind: 'parallax', label: `parallax-${depth}`, options: { depth } }));
  [0.35, 0.6].forEach((rate) => out.push({ kind: 'breathe', label: `breathe-${rate}`, options: { rate } }));
  [0.6, 1.1].forEach((rate) => out.push({ kind: 'pulse', label: `pulse-${rate}`, options: { rate } }));
  [0.16, 0.3].forEach((width) => out.push({ kind: 'light-sweep', label: `sweep-${width}`, options: { width } }));
  [1, 2, 3].forEach((seed) => out.push({ kind: 'develop', label: `develop-${seed}`, options: { seed } }));
  out.push({ kind: 'shimmer', label: 'shimmer', options: {} });
  return out;
}

function exitPool() {
  const out = [];
  ['up', 'down'].forEach((direction) => out.push({ kind: 'wipe', label: `wipe-${direction}`, options: { direction } }));
  ['left', 'right'].forEach((direction) => out.push({ kind: 'slide-away', label: `slide-${direction}`, options: { direction } }));
  [1, 3].forEach((seed) => out.push({ kind: 'dissolve', label: `dissolve-${seed}`, options: { seed } }));
  out.push({ kind: 'fade', label: 'fade', options: {} });
  out.push({ kind: 'push-out', label: 'push-out', options: {} });
  return out;
}

function typePool() {
  // Type moves are not parameterised: a scramble is a scramble. Fifteen is the
  // ceiling, so a film with type in more than fifteen shots has to change some
  // shots rather than repeat a move.
  return ['word-stagger', 'letter-stagger', 'mask-slide', 'roll', 'scramble', 'typewriter',
    'weight-ramp', 'scale-pop', 'path-text', 'karaoke', 'emphasis', 'underline',
    'counter', 'split-flap', 'squeeze'].map((kind) => ({ kind, label: kind, options: {} }));
}

export const POOLS = {
  transition: transitionPool(),
  entrance: entrancePool(),
  behaviour: behaviourPool(),
  exit: exitPool(),
  type: typePool(),
};

export function poolSizes() {
  return Object.fromEntries(Object.entries(POOLS).map(([k, v]) => [k, v.length]));
}

/**
 * Deal every shot a unique token in each category.
 *
 * The order is not random and not sequential. A sequential deal would put every
 * wipe next to every other wipe; a hash of the shot id scatters the vocabulary
 * through the film while staying deterministic, so the same shot list always
 * produces the same edit.
 */
export function allocate(shots, { categories = ['transition', 'entrance', 'behaviour', 'exit', 'type'], strict = true } = {}) {
  const used = Object.fromEntries(categories.map((c) => [c, new Set()]));
  // Two different parameterisations of one family still look like the same idea
  // twice when they are adjacent - two shape-wipes in a row read as a repeat
  // even though the circle and the band are different clips.
  const lastKind = Object.fromEntries(categories.map((c) => [c, null]));
  // A technique is a *family*, not a label. Two lumas at different cell sizes
  // are the same idea twice, so the first pass insists on a kind nobody has
  // used; only when every kind is spent does it allow a second parameterisation.
  const usedKinds = Object.fromEntries(categories.map((c) => [c, new Set()]));
  const out = shots.map((shot, index) => {
    const copy = { ...shot };
    categories.forEach((category) => {
      const pool = POOLS[category];
      if (!pool) return;
      // Only deal type moves to shots that actually carry type.
      if (category === 'type' && !shot.carriesType) return;
      const start = hash(`${shot.id}:${category}`) % pool.length;
      let picked = null;
      let freshKind = null;
      let fallback = null;
      for (let step = 0; step < pool.length; step += 1) {
        const candidate = pool[(start + step) % pool.length];
        if (used[category].has(candidate.label)) continue;
        if (!fallback) fallback = candidate;
        const kindUnused = !usedKinds[category].has(candidate.kind);
        if (kindUnused && candidate.kind !== lastKind[category]) { picked = candidate; break; }
        if (kindUnused && !freshKind) freshKind = candidate;
      }
      picked = picked || freshKind || fallback;
      if (!picked) {
        const shortfall = `${category}: the film needs ${index + 1}, the vocabulary has ${pool.length}`;
        if (strict) throw new Error(`no unused ${category} left for shot ${shot.id} - ${shortfall}`);
        return;
      }
      used[category].add(picked.label);
      lastKind[category] = picked.kind;
      if (usedKinds[category].has(picked.kind)) copy.kindRepeats = true;
      usedKinds[category].add(picked.kind);
      copy[category] = { kind: picked.kind, label: picked.label, options: picked.options };
    });
    return copy;
  });
  return out;
}

/**
 * Deal unique entrances, behaviours and exits to every *layer*, across the
 * whole film.
 *
 * The rule is about what a viewer sees, and a viewer sees layer entrances, not
 * shot-level metadata. Eight shots with three layers each is twenty-four
 * arrivals, which the entrance pool can cover; a long film with sixty shots
 * cannot, and this refuses rather than quietly repeating.
 */
export function allocateLayers(shots, { strict = false } = {}) {
  const used = { entrance: new Set(), behaviour: new Set(), exit: new Set() };
  const repeats = [];
  const out = shots.map((shot) => {
    const layers = (shot.layers || []).map((layer) => {
      const copy = { ...layer };
      ['entrance', 'behaviour', 'exit'].forEach((category) => {
        const authored = layer[category];
        if (!authored) return;
        const pool = POOLS[category];
        // Keep the family the shot asked for and vary only its parameters.
        //
        // The first version dealt any unused entrance to any layer, which looked
        // like a stronger rule and was a worse film: a caption got a circle mask,
        // and a phone got an entrance that clipped to its box while the drawing
        // overflowed it, so the phone appeared sliced down one side. Motion is
        // grammar here - a rise belongs on a caption - so uniqueness is arranged
        // inside a family, not across them.
        const variants = pool.filter((candidate) => candidate.kind === authored && !used[category].has(candidate.label));
        if (!variants.length) {
          repeats.push(`${layer.id}: ${category} "${authored}" could not be varied`);
          copy[`_${category}Label`] = authored;
          copy[`_${category}Repeat`] = true;
          return;
        }
        const picked = variants[0];
        used[category].add(picked.label);
        copy[category] = picked.kind;
        const optionsKey = category === 'behaviour' ? 'behaviourOptions' : `${category}Options`;
        copy[optionsKey] = { ...(copy[optionsKey] || {}), ...picked.options };
        copy[`_${category}Label`] = picked.label;
      });
      return copy;
    });
    return { ...shot, layers };
  });
  if (strict && repeats.length) throw new Error(`layer motion could not be made unique:\n${repeats.join('\n')}`);
  out.repeats = repeats;
  return out;
}

/**
 * Does the film keep the rule? Returns a list of every repeat, by category.
 *
 * The film's own hand-written tokens are counted too: if two shots both say
 * `transitionIn: 'luma'`, that is a repeat whether or not the allocator was used.
 */
export function auditNoRepeat(shots) {
  const notes = [];
  const seen = { transition: new Map(), entrance: new Map(), behaviour: new Map(), exit: new Map(), type: new Map() };
  const read = (shot, category) => {
    const token = shot[category];
    if (!token) return null;
    if (typeof token === 'string') return token;
    return token.label || token.kind || null;
  };
  shots.forEach((shot) => {
    Object.keys(seen).forEach((category) => {
      const token = read(shot, category);
      if (!token) return;
      if (seen[category].has(token)) {
        notes.push(`"${token}" is used twice: ${seen[category].get(token)} and ${shot.id}`);
      } else {
        seen[category].set(token, shot.id);
      }
    });
    // Layers carry their own entrances and behaviours, and those are what a
    // viewer actually sees.
    (shot.layers || []).forEach((layer) => {
      ['entrance', 'behaviour', 'exit'].forEach((category) => {
        const token = layer[`_${category}Label`] || (typeof layer[category] === 'string' ? layer[category] : null);
        if (!token) return;
        const key = `${category}:${token}`;
        if (seen[category].has(key)) {
          notes.push(`"${token}" (${category}) is used twice: ${seen[category].get(key)} and ${layer.id}`);
        } else {
          seen[category].set(key, layer.id);
        }
      });
    });
  });
  return notes;
}

export default { POOLS, allocate, auditNoRepeat, poolSizes };
