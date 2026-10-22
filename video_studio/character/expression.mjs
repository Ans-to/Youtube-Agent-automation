/**
 * Expression and acting for the drawn character.
 *
 * A stick figure that only opens and closes its mouth is a puppet, not a
 * performer. This module supplies the two things that make it read as acting:
 *
 * 1. **A face with a state.** Eyebrows that angle, eyes that narrow, a mouth that
 *    curves — not just opens. Expressions are named, blendable, and derived from
 *    what the line actually says.
 * 2. **A body with an attitude.** Weight shifting onto one hip, a lean into the
 *    camera on a strong line, a nod on a stressed syllable. Small angles, applied
 *    to the existing rig, so nothing here re-implements the skeleton.
 *
 * Everything is a pure function of (time, cues): the same frame always draws the
 * same face, which is what lets frames render out of order.
 */

/** A neutral face and the deviations that make the rest. */
export const NEUTRAL = {
  /** Brow height. 0 sits the brows low and settled; 1 lifts them. */
  brow: 0.18,
  /**
   * Brow angle. Positive tips the inner ends up — challenge, pushback, an
   * argument. Negative lifts the inner ends — worry, a question, sympathy.
   */
  browAngle: 0,
  /** 0 = closed, 1 = wide. Blinking multiplies this, it does not replace it. */
  eyeOpen: 1,
  /** Narrowing from below: 1 is a hard squint. Independent of `eyeOpen`. */
  squint: 0,
  /** Mouth curve: -1 frown, 0 flat, +1 smile. */
  smile: 0.12,
  /** How wide the mouth is held, independent of the curve. */
  wide: 0.5,
  /** Head tilt in radians, positive tips the head to the figure's left. */
  tilt: 0,
  /** Chin down (positive) or up (negative). */
  pitch: 0,
};

/** Ready-made faces. Blend between them; never hand-tune numbers in a scene. */
export const EXPRESSIONS = {
  rest: { ...NEUTRAL },
  /** Talking on the level: brows alive, mouth relaxed. */
  talk: { brow: 0.30, browAngle: 0.05, eyeOpen: 0.94, squint: 0.06, smile: 0.06, wide: 0.55 },
  /** Warm, pleased. The default for a friendly explainer. */
  smile: { brow: 0.34, browAngle: -0.08, eyeOpen: 0.9, squint: 0.14, smile: 0.62, wide: 0.62 },
  /** Genuinely delighted: eyes crease, brows high. */
  grin: { brow: 0.62, browAngle: 0.0, eyeOpen: 0.72, squint: 0.42, smile: 0.86, wide: 0.74, tilt: 0.03 },
  /** A question: brows up in the middle, head tipped. */
  question: { brow: 0.68, browAngle: -0.42, eyeOpen: 1.06, squint: 0, smile: -0.06, wide: 0.52, tilt: 0.07 },
  /** Thinking: off to one side, one brow down, eyes narrowed. */
  think: { brow: 0.24, browAngle: 0.30, eyeOpen: 0.86, squint: 0.34, smile: 0.0, wide: 0.44, tilt: -0.09, pitch: -0.03 },
  /** Surprise: everything open. */
  surprise: { brow: 0.95, browAngle: -0.28, eyeOpen: 1.24, squint: 0, smile: 0.06, wide: 0.42, tilt: 0.02 },
  /** Making a point: brows down and in, eyes hard, mouth set. */
  stern: { brow: 0.05, browAngle: 0.58, eyeOpen: 0.82, squint: 0.30, smile: -0.22, wide: 0.46 },
  /** Caught out: inner brows up, mouth pulled down. */
  worry: { brow: 0.5, browAngle: -0.55, eyeOpen: 1.0, squint: 0, smile: -0.4, wide: 0.4 },
  /** The line that matters: eyes wide, mouth open, chin leading. */
  emphatic: { brow: 0.58, browAngle: 0.22, eyeOpen: 1.1, squint: 0.05, smile: 0.24, wide: 0.62, pitch: -0.02 },
};

export const EXPRESSION_NAMES = Object.keys(EXPRESSIONS);

/** Linear blend of two expressions, field by field. */
export function blendExpression(a, b, k) {
  const t = Math.min(1, Math.max(0, k));
  const out = {};
  for (const key of Object.keys(NEUTRAL)) {
    const av = a[key] === undefined ? NEUTRAL[key] : a[key];
    const bv = b[key] === undefined ? NEUTRAL[key] : b[key];
    out[key] = av + (bv - av) * t;
  }
  return out;
}

/** A smooth 0..1 ramp, so an expression arrives rather than switches. */
const smooth = (x) => {
  const v = Math.min(1, Math.max(0, x));
  return v * v * (3 - 2 * v);
};
const ramp = (t, start, duration) => smooth(duration <= 0 ? 1 : (t - start) / duration);

/**
 * Pick the face a line is spoken with, from its punctuation and its words.
 *
 * This is deliberately shallow — it reads signals, not meaning. A question mark
 * asks for raised inner brows, an exclamation for a wider eye, a contrast word
 * ("but", "twice", "never") for a harder brow. That is enough for a character
 * that has to look like it means what it says.
 */
export function expressionForLine(text) {
  const value = String(text || '').trim();
  const lower = value.toLowerCase();
  if (!value) return 'rest';
  // A question mark, or a line that *opens* with an interrogative. A clause that
  // merely begins with a verb ("is drawn twice") is a continuation, not a
  // question, and giving it raised brows made a statement look uncertain.
  if (value.endsWith('?') || /^(why|how|what|when|where|who|which)\b/.test(lower)) {
    return 'question';
  }
  if (value.endsWith('!')) return 'emphatic';
  if (/\b(never|not|but|instead|wrong|stop|careful|only)\b/.test(lower)) return 'stern';
  if (/\b(imagine|think|remember|wonder|maybe)\b/.test(lower)) return 'think';
  if (/\b(thanks|please|great|nice|love|welcome)\b/.test(lower)) return 'smile';
  if (/\b(amazing|incredible|huge|wow)\b/.test(lower)) return 'grin';
  return 'talk';
}

/**
 * Turn a line list into an expression track.
 *
 * Each cue holds a face and a blend window: the expression arrives over the first
 * ~0.3 s of the line and leaves over the last ~0.25 s, so two lines with
 * different feelings never cut between faces on a single frame.
 */
export function expressionCues(lines, { attack = 0.32, release = 0.26 } = {}) {
  return lines.map((line) => ({
    // A line can name its own face. Guessing from keywords is a fallback for
    // scripted lines that do not, not a substitute for directing the scene: every
    // line in a keyword-guessed film came out as the same pleasant "talk" face.
    expression: line.expression || expressionForLine(line.text),
    start: line.start,
    end: line.end,
    attack: Math.min(attack, Math.max(0.12, (line.end - line.start) * 0.5)),
    release: Math.min(release, Math.max(0.1, (line.end - line.start) * 0.4)),
  }));
}

/**
 * The face at `t`, from a cue list.
 *
 * Between lines the character returns to `rest`, and the return is eased rather
 * than switched, for the same reason a cut between faces reads as a mistake.
 */
export function expressionAt(t, cues) {
  // The base is the resting face, and every cue blends *from* whatever has been
  // accumulated so far. Starting from the first cue's face instead made the first
  // frame of a line jump the whole way in one step — a visible pop — because a
  // weight of zero was treated as "adopt the target" rather than "add nothing".
  let face = EXPRESSIONS.rest;
  // The resting face counts as one layer of its own, so the first cue blends in
  // gradually instead of snapping on at full strength.
  let weight = 1;
  for (const cue of cues) {
    const inAmount = ramp(t, cue.start, cue.attack);
    const outAmount = 1 - ramp(t, cue.end, cue.release);
    const amount = Math.min(inAmount, outAmount) * (cue.holdWeight === undefined ? 1 : cue.holdWeight);
    if (amount <= 0) continue;
    const target = EXPRESSIONS[cue.expression] || EXPRESSIONS.talk;
    // Layers add rather than replace: a strong line inside a soft scene keeps the
    // soft scene's base and adds to it, so faces compose instead of fighting.
    const total = weight + amount;
    face = blendExpression(face, target, amount / total);
    weight = Math.min(total, 1.6);
  }
  return face;
}

/**
 * Acting beats: what the body is doing while the face talks.
 *
 * Weight moves onto one hip per phrase and back, a nod lands on the stressed
 * word, and a lean pushes toward the camera on the line that matters. These are
 * angles on the existing rig — the same rig the walk uses — so a film can switch
 * between speaking and walking without the body changing shape.
 */
export function actingAt(t, cues, { energy = 1 } = {}) {
  let weight = 0;
  let nod = 0;
  let lean = 0;
  let emphasis = 0;
  for (const cue of cues) {
    const inside = t >= cue.start - 0.2 && t <= cue.end + 0.35;
    if (!inside) continue;
    const phase = Math.min(1, Math.max(0, (t - cue.start) / Math.max(0.2, cue.end - cue.start)));
    // Weight settles onto the figure's right early in a phrase and drifts back.
    weight += Math.sin(phase * Math.PI) * 0.035 * cue.weight;
    // One nod per phrase, peaking on the stressed beat.
    nod += Math.sin(phase * Math.PI) * 0.05 * cue.weight;
    lean += Math.sin(phase * Math.PI) * 0.03 * cue.weight;
    // The gesture arm lifts on the opening beat and settles by the end.
    emphasis = Math.max(emphasis, Math.sin(Math.min(1, phase * 1.6) * Math.PI) * cue.weight);
  }
  return {
    weight: weight * energy,
    nod: nod * energy,
    lean: lean * energy,
    gesture: emphasis * energy,
  };
}

/** Build the cue list the actor uses, from the film's own lines and score. */
export function actingCues(lines, { emphasisWords = [] } = {}) {
  return lines.map((line, index) => {
    const lower = String(line.text || '').toLowerCase();
    const stressed = emphasisWords.some((word) => word && lower.includes(String(word).toLowerCase()));
    const strong = line.text.trim().endsWith('!') || stressed;
    return {
      start: line.start,
      end: line.end,
      weight: strong ? 1.25 : index === 0 ? 0.9 : 1,
      emphasis: strong,
    };
  });
}
