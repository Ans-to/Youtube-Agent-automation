/**
 * The motion library: our own reusable templates, with the rules attached.
 *
 * The owner asked for a stock library of motion-graphics templates and then, on
 * seeing why stock cannot work here, for our own. This is that library, and the
 * important part is not the drawing code - it is the metadata. A template that
 * is just a drawing function gets used in the wrong place, which is how a film
 * ends up with three phrases printed on one spot and a diagram drawn under a
 * caption band.
 *
 * So every template carries its own contract:
 *
 *   ``purpose``     one sentence, in the film's language, of what it is for.
 *   ``when``        the situations it is the right answer to.
 *   ``avoid``       the situations where it is the wrong answer, and why.
 *   ``minSeconds``  the shortest beat it can carry without feeling rushed.
 *   ``maxSeconds``  the longest beat before it is a held frame.
 *   ``needs``       the props the caller must supply. Missing props are a bug,
 *                   not a default.
 *   ``regions``     the areas of the frame it is allowed to draw in.
 *   ``cost``        ``low`` or ``medium`` draw weight, for slow machines.
 *   ``sample``      a working set of props, so the template can be rendered and
 *                   measured by the self-check instead of trusted.
 *
 * ``drawTemplate`` enforces the contract at the call site: an unknown id, a
 * region the template does not own, or a beat outside its duration band throws
 * rather than rendering something wrong. That is deliberate. The failure we are
 * designing against is not a crash - it is a frame that looks plausible and is
 * wrong, which nobody notices until the owner does.
 *
 * Two rules run through every draw function below:
 *   * nothing shakes. No jitter, no wobble, no camera movement. Movement is one
 *     direction, eased, then still.
 *   * type never touches type. Every word is masked to its own box, and every
 *     draw is confined to the region it was handed.
 */
import { UI, clamp, span, ease, text, measure, panel, rule } from './ui.mjs';
import { kineticWords } from './kinetic.mjs';

/**
 * Areas of the frame that belong to something else, and must stay empty.
 *
 * ``live`` is the column on the right where the second unit runs; ``caption`` is
 * the subtitle band at the foot. A template that draws into either is wrong even
 * if it looks fine on its own, because the film puts the ticker and the subtitle
 * there on every frame.
 */
export const RESERVED = {
  live: { x: 0.83, y: 0.03, w: 0.16, h: 0.86 },
  caption: { x: 0.0, y: 0.865, w: 1.0, h: 0.135 },
};

/**
 * The regions templates may use, as fractions of the frame.
 *
 * Seven is enough to stage any beat in this film without inventing a new block
 * of coordinates at every call site - and the reason call sites used to drift is
 * that they each carried their own numbers.
 */
export const REGIONS = {
  title: { x: 0.10, y: 0.34, w: 0.64, h: 0.30 },
  hero: { x: 0.08, y: 0.10, w: 0.66, h: 0.24 },
  stage: { x: 0.08, y: 0.36, w: 0.66, h: 0.26 },
  floor: { x: 0.08, y: 0.64, w: 0.66, h: 0.16 },
  band: { x: 0.06, y: 0.46, w: 0.70, h: 0.10 },
  split: { x: 0.06, y: 0.22, w: 0.70, h: 0.42 },
  ledger: { x: 0.08, y: 0.12, w: 0.44, h: 0.52 },
};

/** A region in pixels, for a frame of ``w`` by ``h``. */
export function regionRect(name, w, h) {
  const r = REGIONS[name];
  if (!r) throw new Error(`Unknown region "${name}" (known: ${Object.keys(REGIONS).join(', ')})`);
  return { x: Math.round(r.x * w), y: Math.round(r.y * h), w: Math.round(r.w * w), h: Math.round(r.h * h) };
}

/** Shrink a size until the value fits the width available. */
function fitSize(ctx, value, { family = 'Space Grotesk', weight = 700, maxWidth, cap, floor = 26, tracking = 0 }) {
  let size = Math.round(cap);
  while (size > floor && measure(ctx, value, { size, weight, family, tracking }) > maxWidth) size -= 2;
  return size;
}

/** The words in a string, as the kinetic setter counts them. */
const countWords = (value) => String(value || '').split(/\s+/).filter(Boolean).length;

/**
 * How fast a phrase should be set inside a beat of ``seconds``.
 *
 * Every template derives its stagger the same way, so a phrase in a one-second
 * beat and the same phrase in a three-second beat move at the same pace instead
 * of the short one flickering past.
 */
function pace(seconds, words) {
  return {
    stagger: clamp((seconds * 0.42) / Math.max(1, words), 0.05, 0.14),
    duration: clamp(seconds * 0.34, 0.22, 0.6),
  };
}

/* ------------------------------------------------------------------ templates */

/**
 * A line of type that performs itself, with an optional second row underneath.
 *
 * The workhorse. Used for an opening claim, a name, a punchline, or any beat
 * whose whole content is a sentence.
 */
function kineticHeadline(ctx, {
  box, local, seconds, text: line, subtext = '', size = null, subSize = null,
  colour = UI.white, subColour = UI.gold, emphasis = {}, subEmphasis = {}, dy = 0,
}) {
  const cap = size ?? Math.min(box.h * (subtext ? 0.52 : 0.78), box.w * 0.2);
  const rows = [{
    value: line,
    size: fitSize(ctx, line, { maxWidth: box.w, cap, floor: 40, tracking: -4 }),
    colour,
    emphasis,
  }];
  if (subtext) {
    const small = subSize ?? rows[0].size * 0.78;
    rows.push({
      value: subtext,
      size: fitSize(ctx, subtext, { maxWidth: box.w, cap: small, floor: 32, tracking: 2 }),
      colour: subColour,
      emphasis: subEmphasis,
    });
  }
  const ys = rows.length === 1
    ? [box.y + box.h * 0.58]
    : [box.y + box.h * 0.36, box.y + box.h * 0.74];
  let spoken = 0;
  rows.forEach((row, i) => {
    const words = countWords(row.value);
    const { stagger, duration } = pace(seconds, words + spoken);
    kineticWords(ctx, {
      text: row.value,
      x: box.x + box.w / 2,
      y: ys[i] + dy,
      size: row.size,
      weight: 700,
      family: 'Space Grotesk',
      colour: row.colour,
      emphasis: row.emphasis,
      align: 'center',
      local,
      start: spoken * 0.09,
      stagger,
      duration,
      tracking: i === 0 ? -4 : 2,
      maxWidth: box.w,
    });
    spoken += words;
  });
}

/**
 * A number that counts to its value.
 *
 * Only for a figure the script actually claims. A counted number is the one
 * piece of motion in this library that makes a promise, so it must not be used
 * for decoration.
 */
function countUp(ctx, {
  box, local, seconds, value = 0, from = 0, prefix = '', suffix = '', label = '',
  colour = UI.white, accent = UI.gold,
}) {
  const p = clamp(local / Math.min(seconds * 0.75, 1.6));
  const e = ease.outCubic(p);
  const shown = Math.round(from + (value - from) * e);
  const rendered = `${prefix}${shown}${suffix}`;
  const size = fitSize(ctx, `${prefix}${value}${suffix}`, {
    maxWidth: box.w * 0.9, cap: box.h * (label ? 0.62 : 0.86), floor: 60,
  });
  text(ctx, rendered, box.x + box.w / 2, box.y + box.h * (label ? 0.56 : 0.74), {
    size, weight: 700, family: 'Space Grotesk', color: colour, align: 'center',
  });
  rule(ctx, box.x + box.w * 0.34, box.y + box.h * 0.66, box.w * 0.32, {
    progress: e, colour: accent, thickness: Math.max(4, size * 0.05),
  });
  if (label) {
    const labelSize = fitSize(ctx, label, { maxWidth: box.w * 0.9, cap: box.h * 0.18, floor: 22, family: 'Inter', weight: 600, tracking: 2 });
    const words = countWords(label);
    const { stagger, duration } = pace(seconds * 0.4, words);
    kineticWords(ctx, {
      text: label, x: box.x + box.w / 2, y: box.y + box.h * 0.84,
      size: labelSize, weight: 600, family: 'Inter', colour: UI.faint,
      align: 'center', local: local - seconds * 0.25, start: 0,
      stagger, duration, tracking: 2, maxWidth: box.w,
    });
  }
}

/**
 * A list that builds one row at a time.
 *
 * For a sequence, a checklist, or anything the narration reads as items. Rows
 * arrive in the order they are spoken; nothing is on screen before its line.
 */
function listBuild(ctx, {
  box, local, seconds, items = [], colour = UI.white, accent = UI.gold,
}) {
  const rows = items.map((item) => (typeof item === 'string' ? { name: item } : item));
  if (!rows.length) return;
  const rowH = Math.min(box.h / rows.length, box.h * 0.34);
  const size = Math.min(rowH * 0.34, fitSize(ctx, rows[0].name, {
    maxWidth: box.w * 0.8, cap: rowH * 0.36, floor: 22, tracking: 1,
  }));
  rows.forEach((row, i) => {
    const at = (seconds * 0.62) * (i / rows.length);
    const p = span(local, at, at + Math.min(0.4, seconds * 0.25));
    if (p <= 0) return;
    const e = ease.outCubic(p);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 1.8);
    const y = box.y + i * rowH + rowH * 0.52;
    // The marker is a plate, not a bullet: it is the same tick the pull-request
    // scene uses, so a checklist reads the same everywhere in the film.
    const plate = Math.min(rowH * 0.5, 64);
    ctx.fillStyle = row.state === 'fail' ? UI.red : accent;
    ctx.fillRect(box.x, y - plate * 0.7, plate * 0.22, plate * 1.2);
    text(ctx, row.name, box.x + plate * 0.9, y, {
      size, weight: 700, family: 'Space Grotesk', color: row.colour ?? colour, tracking: 1,
    });
    ctx.restore();
  });
}

/**
 * Two things side by side, with a divider that draws between them.
 *
 * For before/after, wrong/right, or two options. The divider drawing downward is
 * the second motion: the labels alone would be a static pair.
 */
function comparePair(ctx, {
  box, local, seconds, left = 'BEFORE', right = 'AFTER',
  leftItems = [], rightItems = [], colour = UI.white, accent = UI.gold,
}) {
  const gap = Math.max(28, box.w * 0.07);
  const w = (box.w - gap) / 2;
  const p = clamp(local / Math.min(seconds * 0.5, 0.9));
  const e = ease.outCubic(p);
  const headSize = fitSize(ctx, `${left}${right}`, { maxWidth: w * 0.9, cap: box.h * 0.17, floor: 20, tracking: 2 });
  [[left, leftItems, box.x], [right, rightItems, box.x + w + gap]].forEach(([title, items, x], side) => {
    const local0 = local - side * seconds * 0.08;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(local0 / 0.22);
    panel(ctx, {
      x, y: box.y, w, h: box.h, r: 24,
      fill: side === 1 ? 'rgba(242,194,48,0.14)' : 'rgba(255,255,255,0.06)',
      stroke: side === 1 ? accent : 'rgba(255,255,255,0.18)',
    });
    text(ctx, title, x + w / 2, box.y + box.h * 0.24, {
      size: headSize, weight: 700, family: 'Space Grotesk',
      color: side === 1 ? accent : colour, align: 'center', tracking: 2,
    });
    items.slice(0, 3).forEach((item, i) => {
      const rowSize = fitSize(ctx, item, { maxWidth: w * 0.84, cap: box.h * 0.15, floor: 18, family: 'Inter', weight: 600 });
      text(ctx, item, x + w / 2, box.y + box.h * (0.48 + i * 0.17), {
        size: rowSize, weight: 600, color: colour, align: 'center',
      });
    });
    ctx.restore();
  });
  // The divider draws down between the two halves.
  ctx.save();
  ctx.fillStyle = accent;
  const dx = box.x + w + gap / 2 - 3;
  ctx.fillRect(dx, box.y, 6, box.h * e);
  ctx.restore();
}

/**
 * Code that types itself, one line at a time, with a caret.
 *
 * For the moment the film has to show the mechanism rather than describe it.
 */
function codeTyping(ctx, {
  box, local, seconds, lines = [], size = null, colour = '#F2F2F2', accent = UI.gold,
}) {
  if (!lines.length) return;
  const lineH = Math.min(box.h / lines.length, box.h * 0.4);
  const fontSize = size ?? Math.min(lineH * 0.42, fitSize(ctx, lines.reduce((a, b) => (a.length > b.length ? a : b)), {
    maxWidth: box.w * 0.92, cap: lineH * 0.44, floor: 16, family: 'Inter', weight: 500,
  }));
  const total = lines.reduce((sum, line) => sum + line.length, 0) || 1;
  const typed = Math.min(total, Math.floor((local / Math.max(0.2, seconds * 0.82)) * total));
  let used = 0;
  lines.forEach((line, i) => {
    if (used >= typed) return;
    const take = Math.max(0, Math.min(line.length, typed - used));
    used += line.length;
    const y = box.y + i * lineH + lineH * 0.66;
    ctx.save();
    ctx.font = `500 ${fontSize}px "Inter"`;
    ctx.fillStyle = colour;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    const shown = line.slice(0, take);
    ctx.fillText(shown, box.x, y);
    if (take < line.length || i === lines.length - 1) {
      const caretW = Math.max(3, fontSize * 0.08);
      const caretX = box.x + ctx.measureText(shown).width + fontSize * 0.1;
      ctx.fillStyle = accent;
      ctx.fillRect(caretX, y - fontSize * 0.82, caretW, fontSize * 1.02);
    }
    ctx.restore();
  });
}

/**
 * Horizontal bars that grow to their values.
 *
 * For a comparison of two to five numbers. Labels come from the caller; the
 * template never invents a figure.
 */
function barCompare(ctx, {
  box, local, seconds, labels = [], values = [], colour = UI.gold, track = 'rgba(255,255,255,0.12)',
}) {
  const n = Math.min(labels.length, values.length);
  if (!n) return;
  const top = Math.max(...values.slice(0, n).map((v) => Math.abs(v))) || 1;
  const rowH = Math.min(box.h / n, box.h * 0.42);
  const labelW = box.w * 0.28;
  const labelSize = fitSize(ctx, labels[0], { maxWidth: labelW - 16, cap: rowH * 0.4, floor: 16, family: 'Inter', weight: 600 });
  for (let i = 0; i < n; i += 1) {
    const at = (seconds * 0.55) * (i / n);
    const p = span(local, at, at + Math.min(0.55, seconds * 0.3));
    if (p <= 0) continue;
    const e = ease.outCubic(p);
    const y = box.y + i * rowH;
    const barH = Math.min(rowH * 0.42, 96);
    const trackX = box.x + labelW;
    const trackW = box.w - labelW - box.w * 0.10;
    text(ctx, labels[i], box.x, y + barH * 0.78, {
      size: labelSize, weight: 600, family: 'Inter', color: UI.faint,
    });
    ctx.save();
    ctx.fillStyle = track;
    ctx.fillRect(trackX, y, trackW, barH);
    ctx.fillStyle = colour;
    ctx.fillRect(trackX, y, trackW * (Math.abs(values[i]) / top) * e, barH);
    ctx.restore();
    text(ctx, String(values[i]), trackX + trackW + box.w * 0.02, y + barH * 0.78, {
      size: labelSize, weight: 700, family: 'Inter', color: UI.white,
    });
  }
}

/**
 * A rule that sweeps across the frame and leaves a label at its head.
 *
 * The cheapest honest motion in the library: for the second or so between two
 * big beats, when the alternative is a held frame.
 */
function sweepRule(ctx, {
  box, local, seconds, label = '', colour = UI.gold,
}) {
  const p = clamp(local / Math.max(0.2, seconds * 0.55));
  const e = ease.outCubic(p);
  const y = box.y + box.h * 0.5;
  const thickness = Math.max(4, box.h * 0.06);
  ctx.save();
  ctx.fillStyle = colour;
  ctx.fillRect(box.x, y, box.w * e, thickness);
  // The head: a block riding the end of the rule while it draws.
  const head = Math.max(10, thickness * 2.4);
  ctx.globalAlpha = ctx.globalAlpha * (1 - clamp((p - 0.75) / 0.25));
  ctx.fillRect(box.x + box.w * e - head, y - (head - thickness) / 2, head, head);
  ctx.restore();
  if (label) {
    const size = fitSize(ctx, label, { maxWidth: box.w, cap: box.h * 0.34, floor: 18, family: 'Inter', weight: 700, tracking: 3 });
    const words = countWords(label);
    const { stagger, duration } = pace(seconds, words);
    kineticWords(ctx, {
      text: label, x: box.x, y: y - box.h * 0.16,
      size, weight: 700, family: 'Inter', colour: UI.faint,
      align: 'left', local: local - seconds * 0.12, start: 0,
      stagger, duration, tracking: 3, maxWidth: box.w,
    });
  }
}

/**
 * Slabs that stack up, each new one pushing the ones below it.
 *
 * The one template that solves the "held frame" problem structurally: the push
 * moves every slab already on screen, so an arrival is never one object moving in
 * a still frame.
 */
function stackPush(ctx, {
  box, local, seconds, items = [], colour = UI.white, accent = UI.red, highlight = 1,
}) {
  const rows = items.map((item) => (typeof item === 'string' ? { text: item } : item));
  if (!rows.length) return;
  const slot = Math.min(box.h / Math.max(rows.length, 2.2), box.h * 0.34);
  const slabH = slot * 0.86;
  const step = (seconds * 0.62) / rows.length;
  rows.forEach((row, i) => {
    const at = i * step;
    const p = span(local, at, at + Math.min(0.5, Math.max(0.3, step * 0.9)));
    if (p <= 0) return;
    const e = ease.outBack(clamp(p * 1.2));
    // Every slab that arrived before this one scoots up to make room.
    const scoot = i < rows.length - 1 ? ease.outCubic(span(local, at + step - 0.35, at + step)) * slot * 0.5 : 0;
    const y = box.y + box.h - (i + 1) * slot + (1 - e) * slot * 1.1 - scoot;
    const isHighlight = i === highlight;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 1.7);
    panel(ctx, {
      x: box.x, y, w: box.w, h: slabH, r: 18,
      fill: isHighlight ? 'rgba(242,194,48,0.16)' : 'rgba(255,255,255,0.06)',
      stroke: isHighlight ? UI.gold : 'rgba(255,255,255,0.16)',
    });
    ctx.fillStyle = isHighlight ? UI.gold : accent;
    ctx.fillRect(box.x, y, Math.max(8, slabH * 0.09), slabH);
    const labelSize = fitSize(ctx, row.text, {
      maxWidth: box.w - slabH * 0.3, cap: slabH * 0.44, floor: 18, tracking: 1,
    });
    const words = countWords(row.text);
    const { stagger, duration } = pace(Math.max(0.4, step), words);
    kineticWords(ctx, {
      text: row.text, x: box.x + slabH * 0.32, y: y + slabH * 0.62,
      size: labelSize, weight: 700, family: 'Space Grotesk',
      colour: isHighlight ? UI.gold : colour, tracking: 1,
      local: local - at, start: 0, stagger, duration, maxWidth: box.w - slabH * 0.3,
    });
    ctx.restore();
  });
}

/* ------------------------------------------------------------------- catalogue */

/**
 * The catalogue. Order matters only for tie-breaking in the chooser.
 *
 * ``when`` and ``avoid`` are the part the motion agent reads. They are written
 * as situations, not as adjectives, because "use it for a list" is actionable
 * and "use it for energy" is not.
 */
export const TEMPLATES = [
  {
    id: 'kinetic-headline',
    name: 'Kinetic headline',
    purpose: 'Sets one spoken sentence as type that performs itself, word by word, with an optional second row.',
    when: ['opening-claim', 'name-the-thing', 'state-the-thesis', 'punchline'],
    avoid: [
      'More than twelve words: at that length the arrival outlasts the line.',
      'A beat that also needs a diagram or a list: this template owns its whole region.',
    ],
    minSeconds: 0.35,
    maxSeconds: 3.2,
    needs: ['text'],
    regions: ['title', 'hero'],
    cost: 'low',
    sample: { text: 'BUILD IT', subtext: 'BY DESCRIBING IT', subEmphasis: { 2: '#FFFFFF' } },
    draw: kineticHeadline,
  },
  {
    id: 'count-up',
    name: 'Count up',
    purpose: 'Counts a number the script actually claims, with its label and a rule under it.',
    when: ['explain-a-number', 'name-the-thing'],
    avoid: [
      'Any figure the script does not state: a counted number is a factual claim.',
      'A beat under a second: the count is unreadable below that.',
    ],
    minSeconds: 1.0,
    maxSeconds: 4.0,
    needs: ['value'],
    regions: ['stage', 'hero'],
    cost: 'low',
    sample: { value: 40, prefix: '', suffix: '', label: 'LINES OF CODE' },
    draw: countUp,
  },
  {
    id: 'list-build',
    name: 'List build',
    purpose: 'Builds a list one row at a time, in the order the narration reads it.',
    when: ['show-a-sequence', 'show-criteria', 'recap'],
    avoid: [
      'More than four items in a short beat: the rows arrive too fast to read.',
      'A single item: that is a headline, not a list.',
    ],
    minSeconds: 1.5,
    maxSeconds: 7.0,
    needs: ['items'],
    regions: ['ledger', 'stage'],
    cost: 'low',
    sample: { items: ['Read the issue', 'Ask one question', 'Open the pull request'] },
    draw: listBuild,
  },
  {
    id: 'compare-pair',
    name: 'Compare pair',
    purpose: 'Puts two things side by side and draws a divider between them.',
    when: ['make-a-comparison', 'before-and-after'],
    avoid: [
      'Two long paragraphs: each half fits three short lines at most.',
      'A comparison the script does not make: don\'t stage an argument nobody said.',
    ],
    minSeconds: 1.5,
    maxSeconds: 5.0,
    needs: ['left', 'right'],
    regions: ['split'],
    cost: 'medium',
    sample: { left: 'TYPING', right: 'DESCRIBING', leftItems: ['Syntax', 'Line by line'], rightItems: ['Intent', 'Whole feature'] },
    draw: comparePair,
  },
  {
    id: 'code-typing',
    name: 'Code typing',
    purpose: 'Types code or commands onto the frame, with a caret.',
    when: ['show-the-mechanism', 'show-the-command'],
    avoid: [
      'Code the film does not show elsewhere: it dates the piece.',
      'Long lines: they are clipped, not wrapped, by design.',
    ],
    minSeconds: 1.5,
    maxSeconds: 6.0,
    needs: ['lines'],
    regions: ['stage', 'ledger'],
    cost: 'low',
    sample: { lines: ['git add .', 'git commit -m "first"'] },
    draw: codeTyping,
  },
  {
    id: 'bar-compare',
    name: 'Bar compare',
    purpose: 'Grows bars to their values, so two or three numbers can be read at a glance.',
    when: ['explain-a-number', 'make-a-comparison'],
    avoid: [
      'More than five bars: the labels stop fitting.',
      'Invented data. Every value must come from the script.',
    ],
    minSeconds: 2.0,
    maxSeconds: 6.0,
    needs: ['labels', 'values'],
    regions: ['stage'],
    cost: 'medium',
    sample: { labels: ['Before', 'After'], values: [20, 40] },
    draw: barCompare,
  },
  {
    id: 'sweep-rule',
    name: 'Sweep rule',
    purpose: 'A rule crosses the region with a small label at its head; the beat-filler that is still motion.',
    when: ['hold-a-beat', 'punctuation'],
    avoid: [
      'Anything over 1.2 seconds: below that length it is a transition, above it it is a held frame with a line on it.',
      'A beat that carries information: this template says nothing.',
    ],
    minSeconds: 0.3,
    maxSeconds: 1.2,
    needs: [],
    regions: ['band', 'floor'],
    cost: 'low',
    sample: { label: 'NEXT' },
    draw: sweepRule,
  },
  {
    id: 'stack-push',
    name: 'Stack push',
    purpose: 'Stacks labelled slabs, each arrival pushing everything already on screen.',
    when: ['show-a-sequence', 'build-an-argument'],
    avoid: [
      'More than four slabs: the stack runs out of region.',
      'A beat whose items are not parallel in kind.',
    ],
    minSeconds: 1.5,
    maxSeconds: 5.5,
    needs: ['items'],
    regions: ['stage', 'floor'],
    cost: 'medium',
    sample: { items: ['PLAIN ENGLISH', 'THE AGENT WRITES', 'ON GITHUB'], highlight: 1 },
    draw: stackPush,
  },
];

/** Look a template up, or throw. */
export function templateById(id) {
  const found = TEMPLATES.find((t) => t.id === id);
  if (!found) throw new Error(`Unknown motion template "${id}"`);
  return found;
}

/**
 * Draw a template, enforcing its contract.
 *
 * Throws if the id is unknown, the region is not one the template owns, or the
 * beat length is outside the template's band. A thrown error at render time is
 * the cheap failure; the expensive one is a plausible frame nobody questions.
 */
export function drawTemplate(ctx, id, options) {
  const template = templateById(id);
  const { w, h, region, seconds, local = 0 } = options;
  if (!w || !h) throw new Error(`drawTemplate("${id}") needs the frame size as w and h`);
  if (!template.regions.includes(region)) {
    throw new Error(`"${id}" cannot draw in region "${region}" (it owns: ${template.regions.join(', ')})`);
  }
  if (!Number.isFinite(seconds)) {
    throw new Error(`drawTemplate("${id}") needs the beat length in seconds`);
  }
  if (seconds < template.minSeconds || seconds > template.maxSeconds) {
    throw new Error(
      `"${id}" is built for beats of ${template.minSeconds}-${template.maxSeconds}s, got ${seconds}s. `
      + 'Ask the chooser for a template that fits the beat instead of stretching this one.',
    );
  }
  for (const need of template.needs) {
    if (options[need] === undefined) throw new Error(`"${id}" needs the prop "${need}"`);
  }
  const box = regionRect(region, w, h);
  ctx.save();
  template.draw(ctx, { ...options, box });
  ctx.restore();
}

/** The catalogue as plain data, for the agent map and the checkers. */
export function describeLibrary() {
  return TEMPLATES.map(({ draw, ...rest }) => ({ ...rest }));
}
