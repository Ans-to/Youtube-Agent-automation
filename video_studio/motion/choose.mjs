/**
 * Choosing a template by situation, not by habit.
 *
 * The owner's requirement for the library was not "have templates" - it was
 * "our motion graphics agent should know which template should be best for which
 * situation". A catalogue alone does not know anything; something has to decide,
 * and the decision has to be explainable, because a choice nobody can justify is
 * the reason a film ends up with the same card on every beat.
 *
 * So a situation names what the beat is *for* ("explain a number", "show a
 * sequence"), the templates declare which situations they serve, and
 * ``rankTemplates`` scores the candidates against the beat it actually has to
 * fill: how long it is, what props exist, which part of the frame is free, and
 * what the previous beat used.
 *
 * The score is built entirely from rules that are written down below, in a fixed
 * order, with no randomness. Two identical beats always produce the same choice,
 * which is what makes the film reproducible - and what lets a test assert it.
 *
 * The result carries its reasons. Any template the chooser rejects is returned
 * with the reason it was rejected, so the agent can say "not this one, because
 * the beat is 2.4 seconds and this template stops at 1.2" instead of guessing.
 */
import { TEMPLATES } from './library.mjs';

/**
 * What the beats in these films are actually for.
 *
 * ``wants`` is ordered: the first template listed is the one the situation is
 * named for, and gets the higher score when everything else is equal.
 */
export const SITUATIONS = {
  'opening-claim': {
    says: 'Open the film by stating the premise in one sentence.',
    wants: ['kinetic-headline', 'stack-push'],
  },
  'name-the-thing': {
    says: 'Put a name or a key figure on the frame so it can be remembered.',
    wants: ['kinetic-headline', 'count-up'],
  },
  'state-the-thesis': {
    says: 'State the idea the rest of the section argues for.',
    wants: ['fork-paths', 'compare-pair', 'kinetic-headline'],
  },
  'punchline': {
    says: 'Land a short line at the end of an argument, with nothing else on screen.',
    wants: ['stamp-lockup', 'kinetic-headline'],
  },
  'explain-a-number': {
    says: 'Show a figure the script claims, so it can be read rather than guessed.',
    wants: ['ring-gauge', 'budget-rail', 'count-up', 'bar-compare'],
  },
  'show-a-sequence': {
    says: 'Walk through steps in the order the narration reads them.',
    wants: ['matrix-grid', 'budget-rail', 'list-build', 'stack-push'],
  },
  'show-criteria': {
    says: 'List the conditions something has to meet, one at a time.',
    wants: ['matrix-grid', 'list-build'],
  },
  'make-a-comparison': {
    says: 'Put two options or two states against each other.',
    wants: ['fork-paths', 'compare-pair', 'bar-compare'],
  },
  'before-and-after': {
    says: 'Show what the same thing looked like before, and what it looks like now.',
    wants: ['compare-pair'],
  },
  'show-the-mechanism': {
    says: 'Reveal how something works by showing the actual commands or code.',
    wants: ['budget-rail', 'command-console', 'code-typing'],
  },
  'show-the-command': {
    says: 'Put one command on the frame and let it type.',
    wants: ['command-console', 'code-typing'],
  },
  'build-an-argument': {
    says: 'Add one more reason to a stack, so each one is felt as an addition.',
    wants: ['matrix-grid', 'stack-push', 'list-build'],
  },
  'recap': {
    says: 'Bring a section back to a short list of what it said.',
    wants: ['matrix-grid', 'list-build', 'stack-push'],
  },
  'hold-a-beat': {
    says: 'Fill a short pause between two big beats with real motion.',
    wants: ['sweep-rule', 'kinetic-headline'],
  },
  'punctuation': {
    says: 'Mark a change of section with something small and deliberate.',
    wants: ['sweep-rule'],
  },
};

/** The weights. Named, so a disagreement can be argued with a number. */
const WEIGHTS = {
  wanted: 3.0,
  wantedSecond: 2.0,
  fitsDuration: 1.5,
  cheapForShortBeat: 0.4,
  repeatOfPrevious: -2.5,
  usedRecently: -1.0,
};

/** How far past a template's own band a beat may go before it is refused. */
const HARD = { short: 0.6, long: 1.35 };

/**
 * Rank the templates that could fill this beat.
 *
 * Every template in the catalogue comes back, either scored or with a
 * ``rejected`` reason, because the rejected ones are the explanation.
 */
export function rankTemplates({
  situation, seconds, have = {}, region = null, previous = null, recent = [], limit = null,
}) {
  if (!SITUATIONS[situation]) {
    throw new Error(`Unknown situation "${situation}" (known: ${Object.keys(SITUATIONS).join(', ')})`);
  }
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new Error('rankTemplates needs the beat length in seconds');
  }
  const situationSpec = SITUATIONS[situation];

  const scored = TEMPLATES.map((template, order) => {
    const reasons = [];
    const wanted = situationSpec.wants.indexOf(template.id);
    if (wanted < 0) {
      // Not wrong, just not what the situation is for. It still competes, but it
      // has to win on fit alone.
      reasons.push(`${situation} does not call for it`);
    }

    const missing = template.needs.filter((need) => have[need] === undefined);
    if (missing.length) {
      return {
        id: template.id, score: -Infinity, order,
        rejected: `missing prop${missing.length > 1 ? 's' : ''}: ${missing.join(', ')}`,
      };
    }
    if (region && !template.regions.includes(region)) {
      return {
        id: template.id, score: -Infinity, order,
        rejected: `"${region}" is not one of its regions (${template.regions.join(', ')})`,
      };
    }
    if (seconds > template.maxSeconds * HARD.long) {
      return {
        id: template.id, score: -Infinity, order,
        rejected: `beat is ${seconds}s, it stops at ${template.maxSeconds}s`,
      };
    }
    if (seconds < template.minSeconds * HARD.short) {
      return {
        id: template.id, score: -Infinity, order,
        rejected: `beat is ${seconds}s, it needs at least ${template.minSeconds}s`,
      };
    }

    let score = 0;
    if (wanted === 0) {
      score += WEIGHTS.wanted;
      reasons.push(`the ${situation} situation is named for it`);
    } else if (wanted > 0) {
      score += WEIGHTS.wantedSecond;
      reasons.push(`it is second choice in ${situation}`);
    }
    if (seconds >= template.minSeconds && seconds <= template.maxSeconds) {
      score += WEIGHTS.fitsDuration;
      reasons.push(`its ${template.minSeconds}-${template.maxSeconds}s band covers ${seconds}s`);
    } else {
      // Inside the hard limits but outside its own band: usable, not ideal.
      const over = seconds > template.maxSeconds
        ? (seconds - template.maxSeconds) / template.maxSeconds
        : (template.minSeconds - seconds) / template.minSeconds;
      score -= over;
      reasons.push(`beat is ${seconds}s, slightly outside its comfortable band`);
    }
    if (seconds < 1.2 && template.cost === 'low') {
      score += WEIGHTS.cheapForShortBeat;
      reasons.push('cheap enough for a beat under 1.2s');
    }
    if (previous === template.id) {
      score += WEIGHTS.repeatOfPrevious;
      reasons.push('the previous beat used it');
    }
    if (recent.includes(template.id)) {
      score += WEIGHTS.usedRecently;
      reasons.push('it was used recently');
    }
    return { id: template.id, score, reasons, order };
  });

  scored.sort((a, b) => (b.score - a.score) || (a.order - b.order));
  return limit ? scored.slice(0, limit) : scored;
}

/**
 * The one template to use, or a thrown error that explains why there is none.
 *
 * The error text is meant to be read by a person: it lists every candidate and
 * the reason it was refused, so a missing case is obvious instead of silent.
 */
export function chooseTemplate(options) {
  const ranked = rankTemplates(options);
  const best = ranked.find((entry) => entry.rejected === undefined);
  if (!best) {
    const lines = ranked.map((entry) => `  ${entry.id}: ${entry.rejected}`).join('\n');
    throw new Error(`No template can fill this beat:\n${lines}`);
  }
  return best;
}

/** One line a person can read, for logs and for the PR thread. */
export function explainChoice(ranked, { situation, seconds } = {}) {
  const usable = ranked.filter((entry) => entry.rejected === undefined);
  const refused = ranked.filter((entry) => entry.rejected !== undefined);
  const head = usable.length
    ? `${situation} (${seconds}s): ${usable[0].id} - ${usable[0].reasons.join('; ') || 'only candidate'}`
    : `${situation} (${seconds}s): nothing fits`;
  const tail = refused.length
    ? `\nRefused: ${refused.map((entry) => `${entry.id} (${entry.rejected})`).join(', ')}`
    : '';
  return head + tail;
}
