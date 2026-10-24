/**
 * The house timings: how long anything in this film is allowed to take.
 *
 * Every effect used to carry its own number, written where it was used - 0.42
 * here, 0.55 there, 0.9 somewhere else - so the only way to answer "how long is
 * a mark" was to grep for it, and the only way to keep the film consistent was
 * to remember. ``howardc38/motion-fx-lab`` solves this with one table
 * (``DEFAULT_DUR``) that every effect reads from, which is not a new idea and is
 * the right one: a film has a tempo, and tempo belongs in one place.
 *
 * The numbers are not invented. The researched floor for a state change is
 * Material 3's - 400 ms to enter decelerating, 200 ms to exit accelerating,
 * 300 ms to change - with a hard ceiling of 700 ms, above which a change stops
 * reading as an answer to the viewer and starts reading as a slow render.
 *
 * Two kinds of entry live here, and they are not held to the same ceiling:
 *
 *   arrival  something enters, leaves or changes. Capped at 700 ms.
 *   light    a pass of light across a surface. A light pass is not an event that
 *            answers a press; it is ambience with a beginning and an end, and
 *            capping it at 700 ms would make it a flicker. Capped at 1.2 s.
 *   cycle    a loop that repeats for the length of a shot: the stage sheen. It
 *            is not an event at all, so none of the event ceilings apply; the
 *            only thing worth asserting is that it is slow enough not to read as
 *            a pulse. Capped at 30 s.
 *
 * ``audit()`` returns everything that breaks its own ceiling, and a test runs it,
 * so a future edit that types 0.9 next to a word arrival fails the suite instead
 * of quietly making one beat feel different from the other twenty.
 */

/** The ceiling for anything that enters, leaves or changes state. */
export const ARRIVAL_MAX = 0.7;

/** The ceiling for a light pass. */
export const LIGHT_MAX = 1.2;

/** The ceiling for a repeating cycle. */
export const CYCLE_MAX = 30;

export const DURATIONS = {
  /** A shot change. Long enough to read as a device, short enough to be a cut. */
  transition: { seconds: 0.42, kind: 'arrival', what: 'a shot change' },
  /** The defocus handover, which needs longer because softness reads slower. */
  focus: { seconds: 0.55, kind: 'arrival', what: 'a defocus handover' },
  /** The ring that answers a press. */
  ripple: { seconds: 0.54, kind: 'arrival', what: 'a press ripple' },
  /** One pass of light across a plate as it lands. */
  sweep: { seconds: 0.9, kind: 'light', what: 'a pass of light' },
  /** The sheen crossing the whole stage on a slow cycle. */
  sheen: { seconds: 7.5, kind: 'cycle', what: 'the stage sheen cycle' },
};

/** One entry's length in seconds. Throws on a name that is not in the table. */
export function seconds(name) {
  const entry = DURATIONS[name];
  if (!entry) throw new Error(`no house timing called ${name}`);
  return entry.seconds;
}

/** The ceiling an entry is held to. */
export function ceiling(name) {
  const entry = DURATIONS[name];
  if (!entry) throw new Error(`no house timing called ${name}`);
  if (entry.kind === 'light') return LIGHT_MAX;
  if (entry.kind === 'cycle') return CYCLE_MAX;
  return ARRIVAL_MAX;
}

/**
 * Every entry that breaks its own ceiling, or is malformed.
 *
 * Returns a list of sentences rather than a boolean, because the useful thing is
 * which one is wrong and by how much.
 */
export function audit() {
  const problems = [];
  for (const [name, entry] of Object.entries(DURATIONS)) {
    if (!(entry.seconds > 0)) {
      problems.push(`${name}: ${entry.seconds} is not a length`);
      continue;
    }
    if (!['arrival', 'light', 'cycle'].includes(entry.kind)) {
      problems.push(`${name}: unknown kind ${entry.kind}`);
      continue;
    }
    const limit = ceiling(name);
    if (entry.seconds > limit) {
      problems.push(`${name}: ${entry.seconds}s is over its ${limit}s ceiling (${entry.kind})`);
    }
    if (!entry.what) problems.push(`${name}: no description`);
  }
  return problems;
}
