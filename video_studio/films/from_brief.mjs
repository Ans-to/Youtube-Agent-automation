#!/usr/bin/env node
/**
 * A film from a brief.
 *
 * Every previous film in this repository was hand-authored: thousands of lines
 * of drawing code for one video about one subject. That is how the rules were
 * learned, and it does not scale. This file is the scale. It reads a brief
 * (title, promise, sections, narration) and composes a motion-graphics film out
 * of the same library, the same type stage and the same transitions.
 *
 * It adds no new visual language. What it adds is *selection*:
 *
 *   - a section names a **situation** ("show-a-sequence"), and the library's own
 *     chooser picks a template that fits that situation, that beat length and
 *     that region (`video_studio/motion/choose.mjs`);
 *   - a section longer than a template's own beat limit is cut into several
 *     beats with different templates. A nine-second section is not one picture
 *     held for nine seconds; it is three pictures that each do something;
 *   - a template only ever draws inside a region it owns, and a headline phrase
 *     only ever goes in a region the template does *not* own, so two things can
 *     never be printed on top of each other;
 *   - transitions come from `chooseTransition`, which refuses to repeat the
 *     previous device, because "don't always use the same transition" is a
 *     standing note from the owner;
 *   - the shot lengths come from the narration when a `lines.json` exists, so
 *     picture, captions and voice share one clock.
 *
 *   node video_studio/films/from_brief.mjs --brief video_studio/briefs/demo.json --out frames --width 1280
 *   node video_studio/films/from_brief.mjs --brief ... --voice-lines voice/lines.json --out frames
 *   node video_studio/films/from_brief.mjs --brief ... --still 2,9 --out stills
 *   node video_studio/films/from_brief.mjs --brief ... --plan-only
 *
 * Anything a brief gets wrong is an error with the reason in it: an unknown
 * situation, a template asked for a prop it does not take, a line too long for
 * the caption band, two sections sharing a line id. A film that renders from a
 * broken brief is worse than a film that refuses to.
 */
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

import { GlobalFonts, createCanvas } from '@napi-rs/canvas';
import { clamp, span, text, measure, roundRect } from '../motion/ui.mjs';
import { PALETTES, drawField, drawPhrase } from '../motion/wordstage.mjs';
import { chooseTransition, reveal } from '../motion/transitions.mjs';
import { REGIONS, RESERVED, describeLibrary, drawTemplate } from '../motion/library.mjs';
import { SITUATIONS, chooseTemplate, explainChoice, rankTemplates } from '../motion/choose.mjs';
import { seconds as houseSeconds } from '../motion/timings.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');

const DESIGN_W = 3840;
const DESIGN_H = 2160;
const CAPTION_LINE_MAX = 42;   // broadcast caption line limit
const CAPTION_LINES_MAX = 2;
const WORDS_PER_SECOND = 2.6;  // measured narration pace; used only without a voice
// The beat length the studio aims for. The library is *designed* around three
// seconds, but a three-second beat spends its last second and a half holding a
// sentence that has finished arriving: measured, that produced 89% near-static
// frames. Cutting each section into ~1.8 s beats keeps the picture in arrival,
// which is also what the owner asked for when he said "about one second chunks".
// Templates that hold a list and reveal its rows one at a time. They own a
// section, not a beat: the rows stay where they arrived, so swapping the layout
// halfway through the list (list-build to stack-push and back) makes the whole
// list jump between two arrangements every two seconds.
const ROW_TEMPLATES = new Set(['list-build', 'stack-push', 'code-typing', 'matrix-grid', 'budget-rail']);
const TARGET_BEAT = 1.8;
const MAX_BEAT = 2.4;
const PAD_HEAD = 0.28;
const PAD_TAIL = 0.42;

// -------------------------------------------------------------------- options
function parseArgs(argv) {
  const opts = {
    brief: null, voiceLines: null, out: 'frames', width: 1280, height: null,
    quality: 90, from: 0, to: null, still: null, quiet: false, planOnly: false,
    plan: false, fps: null,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = () => argv[(i += 1)];
    if (flag === '--brief') opts.brief = value();
    else if (flag === '--voice-lines') opts.voiceLines = value();
    else if (flag === '--out') opts.out = value();
    else if (flag === '--width') opts.width = Number(value());
    else if (flag === '--height') opts.height = Number(value());
    else if (flag === '--quality') opts.quality = Number(value());
    else if (flag === '--from') opts.from = Number(value());
    else if (flag === '--to') opts.to = Number(value());
    else if (flag === '--still') opts.still = value().split(',').map(Number);
    else if (flag === '--quiet') opts.quiet = true;
    else if (flag === '--plan-only') opts.planOnly = true;
    else if (flag === '--plan') opts.plan = true;
    else if (flag === '--fps') opts.fps = Number(value());
    else throw new Error(`unknown option: ${flag}`);
  }
  if (!opts.brief) throw new Error('--brief is required (see video_studio/briefs/)');
  opts.height = opts.height || Math.round((opts.width * DESIGN_H) / DESIGN_W / 2) * 2;
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
const W = DESIGN_W;
const H = DESIGN_H;
const SCALE = OPTS.width / W;

for (const [family, file] of [
  ['Inter', 'inter-latin-400-normal.woff2'],
  ['Inter', 'inter-latin-600-normal.woff2'],
  ['Inter', 'inter-latin-700-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
]) {
  GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
}

// --------------------------------------------------------------------- brief
const LIBRARY = describeLibrary();
const TEMPLATES = new Map(LIBRARY.map((entry) => [entry.id, entry]));

function words(value) {
  return String(value).trim().split(/\s+/).filter(Boolean);
}

function loadBrief(file) {
  const brief = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  const problems = [];
  if (!brief.title) problems.push('title is missing');
  if (!Array.isArray(brief.sections) || brief.sections.length === 0) {
    problems.push('sections must be a non-empty array');
  }
  if (brief.look && !PALETTES[brief.look]) {
    problems.push(`look ${brief.look} is not one of ${Object.keys(PALETTES)}`);
  }
  const seenSections = new Set();
  const seenLines = new Set();
  // Narration line ids are assigned here, in reading order, when the brief does
  // not give them. `tools/brief_to_voice.py` numbers the same lines the same
  // way, which is how the picture finds its timings: the voice file is keyed by
  // id, not by position, so an inserted sentence cannot silently shift the film.
  let nextLineId = 0;
  (brief.sections || []).forEach((section, index) => {
    const where = `section ${index + 1} (${section.id || 'no id'})`;
    if (!section.id) problems.push(`${where}: id is missing`);
    else if (seenSections.has(section.id)) problems.push(`${where}: duplicate id`);
    seenSections.add(section.id);
    if (!SITUATIONS[section.situation]) {
      problems.push(`${where}: situation ${JSON.stringify(section.situation)} is not one of ${Object.keys(SITUATIONS).join(', ')}`);
    }
    if (!Array.isArray(section.lines) || section.lines.length === 0) {
      problems.push(`${where}: needs at least one narration line`);
    }
    (section.lines || []).forEach((line) => {
      if (!line || !line.text) problems.push(`${where}: a narration line has no text`);
      nextLineId += 1;
      if (line && !line.id) line.id = `L${String(nextLineId).padStart(3, '0')}`;
      if (line && line.id) {
        if (seenLines.has(line.id)) problems.push(`${where}: duplicate line id ${line.id}`);
        seenLines.add(line.id);
      }
    });
    if (section.template && !TEMPLATES.has(section.template)) {
      problems.push(`${where}: template ${section.template} is not in the library`);
    }
    if (section.props && section.template) {
      for (const need of TEMPLATES.get(section.template).needs) {
        if (section.props[need] === undefined) {
          problems.push(`${where}: template ${section.template} needs prop "${need}"`);
        }
      }
    }
  });
  if (problems.length) {
    throw new Error(`the brief cannot make a film:\n  ${problems.join('\n  ')}`);
  }
  return brief;
}

/** Every template that can draw with the props this section carries. */
function candidateTemplates(section) {
  const have = section.props || {};
  const ordered = [
    ...(section.template ? [section.template] : []),
    ...((SITUATIONS[section.situation] || {}).wants || []),
    ...LIBRARY.map((entry) => entry.id),
  ].filter((id, index, all) => all.indexOf(id) === index);
  const usable = ordered.filter((id) => TEMPLATES.has(id)
    && TEMPLATES.get(id).needs.every((need) => have[need] !== undefined));
  if (!usable.length) {
    throw new Error(
      `section ${section.id}: no template can draw with the props given `
      + `(${Object.keys(have).join(', ') || 'none'})`,
    );
  }
  return usable;
}

function chooseFor(section) {
  // The chooser refuses a template whose props the brief does not carry, so the
  // props are part of the question rather than something added afterwards.
  const seconds = section.seconds || TARGET_BEAT;
  const options = {
    situation: section.situation,
    seconds,
    have: section.props || {},
    region: section.region || null,
  };
  const ranked = rankTemplates(options);
  try {
    const best = chooseTemplate(options);
    return { id: best.id, reason: explainChoice(ranked, { situation: section.situation, seconds }) };
  } catch (error) {
    throw new Error(`section ${section.id}: ${error.message}`);
  }
}

// ------------------------------------------------------------------ timeline
function loadLineTimings(file) {
  if (!file) return null;
  const data = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  const rows = Array.isArray(data) ? data : (data.lines || []);
  const timings = new Map();
  for (const row of rows) {
    if (!row || !row.id) continue;
    const start = Number(row.start);
    const end = Number(row.end);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      timings.set(row.id, {
        start, end,
        words: Array.isArray(row.word_times) && row.word_times.length ? row.word_times : null,
      });
    }
  }
  return timings.size ? timings : null;
}

/** Strip a word down to what is actually printed: no case, no punctuation. */
function bare(word) {
  return String(word).toLowerCase().replace(/[^a-z0-9']/g, '');
}

/**
 * Every word of a section with the time it is spoken, in order.
 *
 * When the voice file carries per-word timings they are used directly. Without
 * them (a timed script from somewhere else) each line's own measured duration is
 * divided across its words, which is what `voiceover.word_timings` does in the
 * pipeline that produces the file.
 */
function speechOf(lines) {
  const out = [];
  for (const line of lines) {
    const parts = line.words && line.words.length ? line.words : null;
    if (parts) {
      for (const word of parts) out.push({ text: word.text, start: word.start, end: word.end });
      continue;
    }
    const tokens = words(line.text);
    const span = Math.max(0.001, line.end - line.start);
    const per = span / Math.max(1, tokens.length);
    tokens.forEach((token, index) => out.push({
      text: token,
      start: line.start + index * per,
      end: line.start + (index + 1) * per,
    }));
  }
  return out;
}

/**
 * The spoken words cut at the points a speaker breathes.
 *
 * A clause is what a person hears as one piece of a sentence, so it is the
 * largest thing that can be put on screen at once without splitting a thought
 * down the middle - and the smallest thing that still carries a meaning.
 */
function clausesOf(speech) {
  const clauses = [];
  let current = [];
  for (const word of speech) {
    current.push(word);
    if (/[.!?,;:]$/.test(String(word.text).replace(/["')\]]+$/, ''))) {
      clauses.push(current);
      current = [];
    }
  }
  if (current.length) clauses.push(current);
  return clauses.map((group) => ({
    text: group.map((word) => String(word.text).replace(/^["'(\[]+|["')\]]+$/g, '')).join(' ')
      .replace(/[.,;:!?]+$/, '').trim(),
    start: group[0].start,
    end: group[group.length - 1].end,
    words: group,
  })).filter((clause) => clause.text);
}

/** The first time `phrase` is spoken inside `speech`, or null if it never is. */
function firstSpokenAt(phrase, speech) {
  const want = words(phrase).map(bare).filter(Boolean);
  if (!want.length) return 0;
  let cursor = 0;
  let first = null;
  for (const token of want) {
    while (cursor < speech.length && bare(speech[cursor].text) !== token) cursor += 1;
    if (cursor >= speech.length) return null;
    if (first === null) first = speech[cursor].start;
    cursor += 1;
  }
  return first;
}

function estimateSeconds(section, index) {
  const count = (section.lines || []).reduce((total, line) => total + words(line.text).length, 0);
  // Words plus a breath per sentence, then a floor and a ceiling. Every third
  // section is deliberately longer: uniform beat length is the pacing fault the
  // craft gate reports as "sd/mean too low", and it is a property of the film,
  // so the studio decides it here instead of hoping it emerges.
  const spoken = count / WORDS_PER_SECOND + 0.45 * (section.lines || []).length;
  const shape = index % 3 === 2 ? 1.22 : 1.0;
  return clamp(spoken * shape, 2.8, 9.5);
}

/** Cut a section into beats that the library can actually draw.
 *
 * The ceiling is the *tightest* template in the candidate list, not the most
 * generous: a section that names a punchline can only use a template that tops
 * out at 3.2 s, so a 3.4 s section becomes two beats rather than one that the
 * template would refuse. Rounding up matters - rounding to nearest is how the
 * first version produced a 3.32 s beat for a 3.2 s template and stopped.
 */
function beatLengths(seconds, candidates, maxBeats = Infinity) {
  const most = Math.max(...candidates.map((id) => TEMPLATES.get(id).maxSeconds));
  const cap = Math.min(MAX_BEAT, Math.min(most, 6.0));
  let count = Math.max(1, Math.ceil(seconds / cap - 1e-6));
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const each = seconds / count;
    if (candidates.some((id) => withinBand(id, each))) break;
    count += 1;
  }
  // A short line cut into many beats leaves one word alone on the frame, and a
  // single word held for a second and a half reads as a stutter rather than as
  // emphasis. When the narration for a section is only a few words, hold the
  // line instead - but only if a template still covers the longer beat.
  const limited = Math.max(1, Math.min(count, maxBeats));
  if (limited < count && candidates.some((id) => withinBand(id, seconds / limited))) {
    count = limited;
  }
  return Array.from({ length: count }, () => seconds / count);
}

// Templates that can reveal their content a piece at a time as the beats pass.
// A comparison or a number has no "next piece": repeating it is a frozen frame.
// A template that builds its rows across a section (matrix-grid, budget-rail) is
// not on this list on purpose: it is one picture for the whole section, drawn on
// the section's clock, so cutting the section into 2-second beats would only
// re-draw the same diagram five times.
const PROGRESSIVE = new Set(['kinetic-headline', 'list-build', 'stack-push', 'code-typing']);

function withinBand(id, seconds) {
  const meta = TEMPLATES.get(id);
  // Strictly the template's own window: the library refuses a beat outside it
  // rather than stretching the drawing to fill time, and that refusal is right.
  return seconds >= meta.minSeconds - 0.02 && seconds <= meta.maxSeconds + 0.02;
}


/**
 * The template for one beat.
 *
 * The library's chooser does the work: it scores the situation, the beat length
 * and the props, and it *penalises a template the previous beat used*. That
 * penalty is the difference between a section that shows one sentence three
 * times and a section that makes three different pictures out of it - the fault
 * that made the first generated cut fail its composition and hold gates.
 */
function templateForBeat(section, candidates, seconds, previous, recent, beatIndex) {
  // A section that named its template gets that template on every beat. Swapping
  // the picture halfway through a section is not variety, it is a jump cut inside
  // a thought: the diagram grows, it does not become a different diagram.
  if (section.template) {
    if (!candidates.includes(section.template)) {
      throw new Error(`section ${section.id}: ${section.template} cannot draw with the props given`);
    }
    if (!withinBand(section.template, seconds)) {
      const meta = TEMPLATES.get(section.template);
      throw new Error(
        `section ${section.id}: ${section.template} takes ${meta.minSeconds}-${meta.maxSeconds}s beats, `
        + `and this one is ${seconds.toFixed(2)}s. Retime the narration or choose another template.`,
      );
    }
    return section.template;
  }
  const ranked = rankTemplates({
    situation: section.situation,
    seconds,
    have: section.props || {},
    previous,
    recent,
  });
  const fitting = ranked.filter((entry) => entry.rejected === undefined
    && candidates.includes(entry.id) && withinBand(entry.id, seconds));
  if (!fitting.length) {
    const meta = candidates.map((id) => `${id} ${TEMPLATES.get(id).minSeconds}-${TEMPLATES.get(id).maxSeconds}s`);
    throw new Error(
      `section ${section.id}: a ${seconds.toFixed(2)}s beat fits none of the usable templates `
      + `(${meta.join(', ')}). Shorten the narration for this section.`,
    );
  }
  return fitting[0].id;
}

/**
 * What kind of picture a section makes, so a cut can be chosen by relationship.
 *
 * A transition is a sentence: it says how two shots are related. "Same place,
 * further along" wants a cut or an iris; "a closer look at the thing just named"
 * wants a push; "back out to the statement" wants a release; the last cut of a
 * film is allowed punctuation. Picking by rotation gave the film
 * wipe, iris, wipe, iris, wipe - five chapters that read as one alternating
 * mechanical flourish, which is the same fault the owner rejected as "always
 * the same transition", only doubled.
 */
function picKind(section) {
  if (section.kind === 'hook') return 'statement';
  if (section.kind === 'payoff') return 'decision';
  if (section.kind === 'recap') return 'recap';
  if (section.kind === 'outro') return 'outro';
  const template = section.template
    || ((SITUATIONS[section.situation] || {}).wants || [])[0] || '';
  if (['fork-paths', 'matrix-grid', 'ring-gauge', 'budget-rail', 'command-console',
    'compare-pair', 'bar-compare', 'list-build', 'stack-push', 'count-up',
    'code-typing'].includes(template)) return 'diagram';
  return 'statement';
}

/** The situation a cut is made in, as the transition chooser names it. */
function arrivalSituation(from, to) {
  if (to === 'outro') return 'final';
  if (to === 'recap') return 'release';
  if (from === 'statement' && to === 'diagram') return 'detail';    // a closer look
  if (from === 'diagram' && to === 'statement') return 'release';   // back out
  if (from === 'diagram' && to === 'decision') return 'detail';     // the argument lands
  // Two diagrams in a row are the same room, further along. A hard cut is the
  // most confident transition there is, and the least tiring when the ground is
  // already shared - a device between every pair of diagrams is a flourish.
  if (from === 'diagram' && to === 'diagram') return 'new-idea';
  return 'new-scene';
}

function buildSections(brief, timings) {
  const palette = PALETTES[brief.look || 'light'];
  let previousTransition = 'cut';
  const previousKinds = [];
  let cursor = 0;

  return brief.sections.map((section, index) => {
    const candidates = candidateTemplates(section);
    let start;
    let end;
    let lines;
    let found = null;
    if (timings) {
      found = section.lines
        .filter((line) => line.id && timings.has(line.id))
        .map((line) => ({ id: line.id, text: line.text, ...timings.get(line.id) }))
        .sort((a, b) => a.start - b.start);
      if (found.length !== section.lines.length) {
        throw new Error(`section ${section.id}: ${section.lines.length - found.length} narration line(s) have no timing in the voice file`);
      }
      start = Math.max(0, found[0].start - PAD_HEAD);
      end = found[found.length - 1].end + PAD_TAIL;
      lines = found.map((line) => ({ ...line, start: line.start - start, end: line.end - start }));
    } else {
      const seconds = section.seconds || estimateSeconds(section, index);
      start = cursor;
      end = cursor + seconds;
      const unit = (end - start) / section.lines.length;
      lines = section.lines.map((line, i) => ({
        id: line.id || `${section.id}-${i + 1}`,
        text: line.text,
        start: i * unit + unit * 0.12,
        end: (i + 1) * unit - unit * 0.08,
      }));
    }
    cursor = end;

    // What is said, and when. Everything the picture prints is chosen from this,
    // so the frame can only ever show words the narrator is saying at that
    // moment - the fault the owner reported as "what we see and what is being
    // talked about are totally different".
    const absolute = timings
      ? found
      : lines.map((line) => ({ ...line, start: line.start + start, end: line.end + start }));
    const speech = speechOf(absolute);
    const clauses = clausesOf(speech);

    // Authored copy - the rows of a list, the lines of a command, the two halves
    // of a comparison - is held to the same rule. It is allowed to condense the
    // sentence ("Ten: running it" for "ten seconds running it"), never to
    // introduce words nobody says.
    const authored = [];
    if (Array.isArray(section.props?.items)) authored.push(...section.props.items);
    if (Array.isArray(section.props?.lines)) authored.push(...section.props.lines);
    if (section.props?.left) authored.push(section.props.left);
    if (section.props?.right) authored.push(section.props.right);
    if (section.props?.label) authored.push(section.props.label);
    if (Array.isArray(section.props?.segments)) {
      authored.push(...section.props.segments.map((segment) => segment.label).filter(Boolean));
    }
    const unsaid = authored.filter((phrase) => firstSpokenAt(phrase, speech) === null);
    if (unsaid.length) {
      throw new Error(
        `section ${section.id}: the picture would print ${unsaid.map((p) => JSON.stringify(p)).join(', ')}`
        + ` but the narration never says ${unsaid.length > 1 ? 'those words' : 'that'}.`
        + `\n  spoken: ${absolute.map((line) => line.text).join(' ')}`
        + '\n  Rewrite the on-screen copy as words from the narration, or rewrite the narration.',
      );
    }

    const seconds = end - start;
    // The words that will be drawn, not the words that will be spoken: a
    // headline's own text is what gets cut into beats.
    const drawn = (section.props && section.props.text)
      || section.lines.map((line) => line.text || '').join(' ');
    const words = String(drawn).split(/\s+/).filter(Boolean).length;
    // What the section will actually draw decides whether it can be cut up: a
    // section that names its template is judged on that template, not on the
    // whole candidate list, which contains templates it will never use.
    const progressive = section.template
      ? PROGRESSIVE.has(section.template)
      : candidates.some((id) => PROGRESSIVE.has(id));
    // A named template is also the only template whose band matters: cutting a
    // section into beats that this template cannot carry is the failure mode.
    const bandCandidates = section.template ? [section.template] : candidates;
    const byWords = Math.max(1, Math.floor(words / 2));
    let lengths;
    const codeLines = section.template === 'code-typing' && Array.isArray(section.props?.lines)
      ? section.props.lines.length : 0;
    if (codeLines === 1 && seconds <= 6.0) {
      // One command is one picture. Cutting it in two would retype the same line
      // on the next beat, and a typing animation that restarts reads as a glitch.
      lengths = [seconds];
    } else if (progressive) {
      lengths = beatLengths(seconds, bandCandidates, byWords);
    } else {
      // A comparison or a number cannot show a new piece on each beat, so the
      // section is cut into the fewest beats that still fit the template's
      // window. Cutting it to the usual 1.8 s beat would draw the same picture
      // three times, which is the frozen frame the repeat gate exists to catch.
      const meta = TEMPLATES.get(section.template || candidates[0]);
      const fewest = Math.max(1, Math.ceil(seconds / (meta.maxSeconds - 0.02)));
      // ...and never so many that a beat falls under the template's floor.
      const usable = Math.max(1, Math.min(fewest, Math.floor(seconds / meta.minSeconds) || 1));
      lengths = Array.from({ length: usable }, () => seconds / usable);
    }
    const beats = [];
    let beatStart = start;
    let previousTemplate = null;
    const recentTemplates = [];
    let rowTemplateLock = null;
    lengths.forEach((length, beatIndex) => {
      // A section may name a template per beat - the closing card is a different
      // kind of object from the line that introduces it. Anything it names must
      // still be in the library, take the props this section carries, and fit
      // the beat, so this is staging, not a way around the contract.
      const staged = Array.isArray(section.beats) && section.beats.length
        ? section.beats[Math.min(beatIndex, section.beats.length - 1)]
        : null;
      if (staged) {
        const meta = TEMPLATES.get(staged);
        if (!meta) throw new Error(`section ${section.id}: beat template ${staged} is not in the library`);
        for (const need of meta.needs) {
          if (section.props?.[need] === undefined) {
            throw new Error(`section ${section.id}: beat template ${staged} needs prop "${need}"`);
          }
        }
      }
      const chosen = staged
        ? staged
        : templateForBeat(section, candidates, length, previousTemplate, recentTemplates, beatIndex);
      // One list, one layout. The beat still changes - a new row arrives - but the
      // arrangement may not.
      const template = rowTemplateLock && ROW_TEMPLATES.has(chosen) ? rowTemplateLock : chosen;
      if (ROW_TEMPLATES.has(template)) rowTemplateLock = template;
      previousTemplate = template;
      recentTemplates.push(template);
      if (recentTemplates.length > 2) recentTemplates.shift();
      const meta = TEMPLATES.get(template);
      const region = (staged && meta.regions.includes(meta.regions[0]) && !meta.regions.includes(section.region))
        ? meta.regions[0]
        : (section.region || meta.regions[0]);
      if (!meta.regions.includes(region)) {
        throw new Error(`section ${section.id}: ${template} cannot draw in ${region} (owns ${meta.regions.join(', ')})`);
      }
      beats.push({
        id: `${section.id}-${beatIndex + 1}`,
        beatIndex,
        template,
        region,
        seconds: length,
        start: beatStart,
        end: beatStart + length,
      });
      beatStart += length;
    });

    const arrive = section.arrive || chooseTransition(
      arrivalSituation(previousKinds[previousKinds.length - 1], picKind(section)),
      previousTransition,
    );
    previousTransition = arrive;
    previousKinds.push(picKind(section));

    return {
      id: section.id,
      index: index + 1,
      heading: section.heading || section.id,
      kind: section.kind || 'section',
      situation: section.situation,
      start,
      end,
      seconds,
      arrive,
      lines,
      speech,
      clauses,
      palette,
      props: section.props || {},
      beats,
      reason: section.template ? 'named by the brief' : chooseFor(section).reason,
    };
  });
}

const BRIEF = loadBrief(OPTS.brief);
const TIMINGS = loadLineTimings(OPTS.voiceLines);
const SECTIONS = buildSections(BRIEF, TIMINGS);
const SHOTS = SECTIONS.flatMap((section) => section.beats.map((beat) => ({ ...beat, section })));

/**
 * What each beat prints, in one string.
 *
 * Recorded once, on the beat, for two reasons: the caption check below needs to
 * know whether the frame is already saying these words, and the plan file
 * publishes it so the picture can be audited against the narration without
 * decoding a single frame.
 */
function shownTextOf(shot) {
  const drawn = propsForBeat(shot.section, shot, shot.section.beats.length, shot.section.palette);
  const label = (item) => (typeof item === 'string' ? item : (item.name ?? item.text ?? ''));
  const said = (item) => typeof item === 'object' && typeof item.at === 'number'
    ? item.at <= (shot.end - shot.section.start) + 0.05 : true;
  if (Array.isArray(drawn.segments)) {
    // Only the segments already spoken, and the label is what is read: the value
    // is a numeral on the rail, not a word anybody says.
    const upTo = shot.end - shot.section.start + 0.05;
    return drawn.segments
      .filter((segment) => typeof segment.at !== 'number' || segment.at <= upTo)
      .map((segment) => segment.label || String(segment.value ?? ''))
      .filter(Boolean).join(' | ');
  }
  if (drawn.value !== undefined) return `${drawn.value} ${drawn.label ?? ''}`.trim();
  return drawn.text
    || (Array.isArray(drawn.items)
      ? drawn.items.filter(said).map(label).filter(Boolean).join(' | ') : null)
    || (Array.isArray(drawn.lines) ? drawn.lines.join(' | ') : null)
    || [drawn.left, drawn.right].filter(Boolean).join(' | ')
    || '';
}
for (const shot of SHOTS) shot.shownText = shownTextOf(shot);
const DURATION = Math.max(...SHOTS.map((shot) => shot.end));
const FPS = Number(OPTS.fps) || Number(BRIEF.fps) || 30;

for (let i = 1; i < SECTIONS.length; i += 1) {
  if (SECTIONS[i].start < SECTIONS[i - 1].end - 0.001) {
    throw new Error(`sections ${SECTIONS[i - 1].id} and ${SECTIONS[i].id} overlap in time; the voice timings are out of order`);
  }
}

function shotIndexAt(t) {
  for (let i = SHOTS.length - 1; i >= 0; i -= 1) {
    if (t >= SHOTS[i].start - 1e-6) return i;
  }
  return 0;
}

// ------------------------------------------------------------------- captions
/** Wrap one spoken line into at most two caption lines, never splitting a word. */
function wrapCaption(value) {
  const parts = String(value).trim().split(/\s+/);
  const lines = [''];
  for (const word of parts) {
    const current = lines[lines.length - 1];
    if (!current.length) lines[lines.length - 1] = word;
    else if (`${current} ${word}`.length <= CAPTION_LINE_MAX) lines[lines.length - 1] = `${current} ${word}`;
    else lines.push(word);
  }
  return lines.length > CAPTION_LINES_MAX ? null : lines;
}

for (const section of SECTIONS) {
  for (const line of section.lines) {
    const wrapped = wrapCaption(line.text);
    if (!wrapped) {
      throw new Error(
        `line ${line.id || '(unnamed)'} is too long for the caption band at `
        + `${CAPTION_LINE_MAX} chars x ${CAPTION_LINES_MAX} lines. Shorten the sentence in the brief `
        + 'rather than shrinking the type.',
      );
    }
    line.captionLines = wrapped;
  }
}

// ------------------------------------------------------------------ creative
const hair = (palette) => (palette.dark ? 'rgba(255,255,255,0.16)' : 'rgba(18,35,63,0.14)');

/**
 * The colours a template draws in, from the film's palette.
 *
 * Every template in the library defaults to white type and a gold accent, which
 * is correct on the dark stage and invisible on the light one: the first brief
 * render came out as white words on a white field. The palette is the film's
 * decision, so it is supplied here, and anything the brief states explicitly
 * still wins.
 */
function themedProps(template, section, palette) {
  const theme = { colour: palette.ink, accent: palette.accent };
  if (template === 'kinetic-headline') theme.subColour = palette.accent;
  if (template === 'bar-compare') theme.track = hair(palette);
  return { ...theme, ...(section.props || {}) };
}
const kicker = (palette) => (palette.dark ? 'rgba(255,255,255,0.62)' : 'rgba(18,35,63,0.62)');

/**
 * The chrome every beat carries: which chapter this is, and how far through the
 * section we are.
 *
 * It is chrome, not decoration. The number and the heading are the only things
 * continuous across a cut, so a viewer who looks away for three seconds knows
 * where they are when they return. The rule fills across the section, which is
 * also a beat's guaranteed motion when a template's own arrival has settled.
 */
function chrome(ctx, shot, sectionLocal) {
  const section = shot.section;
  const margin = W * 0.055;
  const top = H * 0.062;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * span(sectionLocal, 0, 0.35);
  const numberSize = Math.round(H * 0.030);
  const number = String(section.index).padStart(2, '0');
  text(ctx, number, margin, top + H * 0.016, {
    size: numberSize, weight: 700, family: 'Space Grotesk',
    color: section.palette.accent, tracking: 6,
  });
  const numberWidth = measure(ctx, `${number} `, {
    size: numberSize, weight: 700, family: 'Space Grotesk', tracking: 6,
  });
  text(ctx, section.heading.toUpperCase(), margin + numberWidth + H * 0.018, top + H * 0.016, {
    size: Math.round(H * 0.021), weight: 600, family: 'Inter',
    color: kicker(section.palette), tracking: 5,
  });
  ctx.restore();

  // A big, quiet numeral in the empty right column. It drifts for the whole
  // section, which is what guarantees that no two frames a second apart are
  // identical even when a template has finished its arrival and is holding a
  // sentence - and it sits in a part of the frame no template uses.
  const drift = clamp(sectionLocal / Math.max(0.001, section.seconds));
  ctx.save();
  // Lower right, under everything the templates use and above the caption band.
  ctx.globalAlpha = ctx.globalAlpha * (section.palette.dark ? 0.12 : 0.085);
  text(ctx, String(section.index).padStart(2, '0'), W * 0.958, H * (0.815 + drift * 0.035), {
    size: Math.round(H * 0.135), weight: 700, family: 'Space Grotesk',
    color: section.palette.ink, align: 'right',
  });
  ctx.restore();

  const ruleY = top + H * 0.032;
  const thickness = Math.max(2, H * 0.0016);
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.9;
  ctx.fillStyle = hair(section.palette);
  ctx.fillRect(margin, ruleY, W - margin * 2, thickness);
  ctx.fillStyle = section.palette.accent;
  ctx.fillRect(margin, ruleY, (W - margin * 2) * clamp(sectionLocal / Math.max(0.001, section.seconds)), thickness);
  ctx.restore();
}

/** The caption band. Reserved by the library, so no template may draw here. */
function captions(ctx, section, sectionLocal, shot) {
  // A kinetic headline *is* the caption on that beat: it is the clause being
  // spoken, at reading size, in the middle of the frame. Printing the same
  // sentence again along the bottom is the mistake a template makes when nobody
  // is comparing the two layers.
  // A kinetic headline is the clause being spoken, in the middle of the frame at
  // reading size. Printing the sentence again along the bottom is the mistake
  // that made the picture feel like two things talking at once.
  if (shot && shot.template === 'kinetic-headline') return;
  // Words the picture has already printed on this beat. A caption that repeats
  // them is the same sentence twice on one frame - that is what a viewer reads as
  // "the picture and the voice are not the same thing".
  const shown = new Set(shot && shot.shownText
    ? shot.shownText.split(/\s+/).map(bare).filter(Boolean) : []);
  const band = RESERVED.caption;
  const x = band.x * W + W * 0.055;
  const y = band.y * H + band.h * H * 0.34;
  const size = Math.round(H * 0.0305);
  const step = size * 1.32;
  for (const line of section.lines) {
    if (sectionLocal < line.start - 0.02 || sectionLocal > line.end + 0.18) continue;
    // If the picture already carries most of this cue, the caption band is a
    // second copy of the same sentence, and a viewer reads it as a mistake. The
    // test is coverage, not equality: "Ten seconds running it yourself" over a row
    // that says "Ten seconds running it" is still a duplicate.
    const cue = line.captionLines.join(' ').split(/\s+/).map(bare).filter(Boolean);
    const covered = cue.filter((word) => shown.has(word)).length;
    if (cue.length && covered / cue.length >= 0.6) continue;
    const appear = clamp(span(sectionLocal, line.start - 0.02, line.start + 0.16) * 2.2);
    const leave = span(sectionLocal, line.end + 0.02, line.end + 0.18);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * appear * (1 - leave);
    line.captionLines.forEach((row, rowIndex) => {
      text(ctx, row, x, y + rowIndex * step, {
        size, weight: 600, family: 'Inter', color: section.palette.caption,
      });
    });
    // The underline walks with the reading, so the caption is never a still
    // block: it is the one thing on screen that moves at speech pace.
    const width = Math.max(...line.captionLines.map((row) => measure(ctx, row, {
      size, weight: 600, family: 'Inter',
    })));
    const swept = width * clamp((sectionLocal - line.start) / Math.max(0.2, line.end - line.start));
    ctx.fillStyle = section.palette.accent;
    ctx.fillRect(x, y + line.captionLines.length * step * 0.72, swept, Math.max(2, H * 0.0022));
    ctx.restore();
  }
}

/** Words split into `count` chunks, in order, so repeated beats say new words. */
function splitWords(text, count) {
  const parts = String(text).split(/\s+/).filter(Boolean);
  if (count <= 1 || parts.length < count) return [text];
  // Evenly, not in fixed-size blocks: dealing five words into three beats by
  // taking two at a time leaves a beat with one word on it, and one word alone
  // on a full frame is not emphasis, it is a mistake.
  const base = Math.floor(parts.length / count);
  const extra = parts.length % count;
  const chunks = [];
  let cursor = 0;
  for (let index = 0; index < count; index += 1) {
    const take = base + (index < extra ? 1 : 0);
    chunks.push(parts.slice(cursor, cursor + take).join(' '));
    cursor += take;
  }
  return chunks;
}

/**
 * What a template draws on this beat.
 *
 * A section cut into three beats must not draw the same picture three times:
 * that is a stutter, and the repeat gate is right to call it a frozen frame. So
 * repeated beats reveal the section's content progressively - a list gains its
 * next row, a code block gains its next line, a headline says its next words -
 * and anything that cannot be revealed progressively (a comparison, a number)
 * simply is not repeated: it is given the whole section as one beat.
 */
/**
 * The words on screen on this beat, taken from the words being spoken on it.
 *
 * The old version split the section's authored headline evenly across its beats,
 * so the type said "SHIP IT, OR" while the narrator was still on "an agent just
 * opened a pull request". Now the headline is the clause the narrator is
 * actually in the middle of: a section is cut where the speaker breathes, and
 * each beat shows the clause it covers. A long clause is trimmed to the groups
 * of words in front of the beat rather than being printed entire and unread.
 */
function headlineForBeat(section, beat) {
  const clauses = section.clauses || [];
  if (!clauses.length) return null;
  const overlap = clauses.map((clause) => Math.max(
    0, Math.min(clause.end, beat.end) - Math.max(clause.start, beat.start)));
  let index = overlap.indexOf(Math.max(...overlap));
  if (Math.max(...overlap) <= 0.01) {
    // A beat in a pause between clauses: hold the last clause that had started.
    index = clauses.reduce((found, clause, at) => (clause.start <= beat.end ? at : found), 0);
  }
  const clause = clauses[index];
  // Sentence case, not capitals. A spoken sentence set in caps is shouting: it
  // reads as a caption over a stock photo, which is the look the owner called a
  // template. The film's display type is mixed case at weight 700, and only the
  // eyebrows, units and the closing stamp are set in caps - which is what makes
  // those read as labels instead of competing with the sentence.
  const parts = clause.text.split(' ');
  if (parts.length <= 6) return sentence(clause.text);
  // A long clause is spoken over more than one beat, so it is shown in two
  // halves and the beat picks the half it is covering. Printing all seven words
  // and holding them is how a headline ends up describing a sentence the
  // narrator finished two seconds ago.
  const split = Math.ceil(parts.length / 2);
  const first = clause.words.slice(0, split);
  const second = clause.words.slice(split);
  const secondStarts = second.length ? second[0].start : Infinity;
  const half = beat.start >= secondStarts ? second : first;
  return sentence(half.map((word) => String(word.text).replace(/[.,;:!?]+$/, '')).join(' '));
}

/** A phrase set the way a sentence is set: first letter up, full stops off. */
function sentence(value) {
  const text = String(value).replace(/[.,;:!?]+\s*$/, '').trim();
  if (!text) return text;
  return text[0].toUpperCase() + text.slice(1);
}

function propsForBeat(section, beat, beatCount, palette) {
  const props = themedProps(beat.template, section, palette);
  const speech = section.speech || [];

  if (beat.template === 'kinetic-headline' || beat.template === 'stamp-lockup') {
    const fromSpeech = speech.length ? headlineForBeat(section, beat) : null;
    props.text = fromSpeech || props.text;
    props.subtext = fromSpeech ? '' : props.subtext;
    return props;
  }

  if (beat.template === 'list-build' || beat.template === 'stack-push'
      || beat.template === 'matrix-grid') {
    // Both spellings: list-build reads `name`, stack-push reads `text`.
    const items = (props.items || []).map((item) => {
      if (typeof item === 'string') return { name: item, text: item };
      return { text: item.name ?? item.text, ...item, name: item.name ?? item.text };
    });
    if (!speech.length) return props;
    // A row arrives when its words are said, not on an even clock. The time goes
    // with the row, because the row is drawn from the section's clock: it appears
    // once, where it will stay, and later beats do not replay its entrance.
    const start = section.start;
    const timed = items.map((item) => {
      const at = firstSpokenAt(item.name, speech);
      return { ...item, at: at === null ? null : Math.max(0, at - start) };
    }).filter((item) => item.at !== null);
    if (!timed.length) return props;
    props.items = timed;
    // The section's full list decides the layout, so a row that has not been
    // said yet does not move the rows that have.
    props.slots = items.length;
    return props;
  }

  if (beat.template === 'budget-rail') {
    const segments = (props.segments || []).map((item) => ({ ...item }));
    if (!speech.length) return props;
    const start = section.start;
    props.segments = segments.map((segment) => {
      const at = firstSpokenAt(segment.label ?? '', speech);
      return { ...segment, at: at === null ? null : Math.max(0, at - start) };
    }).filter((segment) => segment.at !== null);
    props.total = props.total ?? segments.reduce((sum, segment) => sum + (Number(segment.value) || 0), 0);
    return props;
  }

  if (beat.template === 'code-typing') {
    const lines = props.lines || [];
    if (!speech.length) return props;
    const shown = lines.filter((line) => {
      const at = firstSpokenAt(line, speech);
      return at !== null && at <= beat.end + 0.05;
    });
    props.lines = shown.length ? shown : lines.slice(0, 1);
    props.slots = lines.length;
    return props;
  }

  if (beat.template === 'count-up' && beat.beatIndex > 0) {
    props.from = props.value;
  }
  return props;
}

/**
 * The second unit: motion that belongs to the section rather than to a template.
 *
 * A template arrives, says its line and then holds, which is correct for the
 * sentence and fatal for the frame: the first generated cut measured 89 percent
 * near-static frames and failed the motion gate outright. The long hand-authored
 * film never had that problem because something was always moving that was not
 * the subject. This is that something, and it is deliberately quiet:
 *
 *   - a rail of ticks, one per narration line, each filling as its line is said;
 *   - four slim bars breathing at different periods, so no two frames half a
 *     second apart are identical even when the picture has settled;
 *   - dust: a slow drift of small marks across the empty right of the frame.
 *
 * All three are pure functions of the section clock, so the render is still
 * deterministic, and all three sit outside every template's region.
 */
/** An "18,35,63" string from a palette colour, for gradients that need alpha. */
function rgb(value) {
  const text = String(value).trim();
  if (text.startsWith('#')) {
    const hex = text.slice(1);
    const n = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
    return [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16)).join(',');
  }
  const nums = text.match(/[\d.]+/g);
  return nums ? nums.slice(0, 3).join(',') : '18,35,63';
}

/** The colour of the light that sweeps the ground, per palette. */
function tint0(palette) {
  return palette.dark ? '255,255,255' : '255,255,255';
}

/**
 * Film grain, over everything and under the captions.
 *
 * A gradient on a flat colour field bands: the encoder has to quantise a slow
 * ramp, and at 720p that shows as contour rings. A couple of percent of fine
 * noise costs almost nothing in bitrate and removes it completely - which is why
 * professional renders carry grain. It also gives the frame a floor of motion, so
 * a diagram that has finished building still looks alive.
 *
 * The tile is generated once from a fixed seed and offset per frame by an
 * integer, so the render stays deterministic: frame 100 always has the same
 * grain in the same place.
 */
let GRAIN_TILE = null;
function grainTile() {
  if (GRAIN_TILE) return GRAIN_TILE;
  const tile = createCanvas(256, 256);
  const tctx = tile.getContext('2d');
  const image = tctx.createImageData(256, 256);
  let seed = 0x9e3779b9;
  for (let i = 0; i < 256 * 256; i += 1) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const value = 118 + ((seed >>> 24) % 20);
    image.data[i * 4] = value;
    image.data[i * 4 + 1] = value;
    image.data[i * 4 + 2] = value;
    image.data[i * 4 + 3] = 255;
  }
  tctx.putImageData(image, 0, 0);
  GRAIN_TILE = tile;
  return GRAIN_TILE;
}

function drawGrain(ctx, frameIndex, palette) {
  const tile = grainTile();
  const ox = (frameIndex * 37) % 256;
  const oy = (frameIndex * 61) % 256;
  ctx.save();
  ctx.globalCompositeOperation = 'overlay';
  ctx.globalAlpha = palette.dark ? 0.045 : 0.035;
  for (let x = -ox; x < W; x += 256) {
    for (let y = -oy; y < H; y += 256) ctx.drawImage(tile, x, y);
  }
  ctx.restore();
}

function secondUnit(ctx, section, sectionLocal, palette) {
  const t = sectionLocal;

  // Two large-area, low-contrast movers. Sparse type on a pale field gives the
  // frame-difference gate almost nothing to see between arrivals - measured, 88%
  // of frames read as static - so the field itself has to be alive. Both are
  // slow, both are wide, neither competes with the words.
  // A progress arc around the chapter numeral: it reads as the section's own
  // clock rather than as a shape someone left on the frame, and it is always
  // turning. The numeral stays the subject; the arc is its timer.
  const sweepProgress = clamp(t / Math.max(0.001, section.seconds));
  const arcX = W * 0.905;
  const arcY = H * 0.845;
  const arcR = H * 0.085;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.10;
  ctx.strokeStyle = palette.ink;
  ctx.lineWidth = W * 0.0035;
  ctx.beginPath();
  ctx.arc(arcX, arcY, arcR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = ctx.globalAlpha * 0.42;
  ctx.strokeStyle = palette.accent;
  ctx.lineWidth = W * 0.005;
  ctx.beginPath();
  ctx.arc(arcX, arcY, arcR, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.02, sweepProgress));
  ctx.stroke();
  ctx.restore();

  // A soft column of light crossing the frame, with a measuring line at its
  // leading edge. It runs *behind* the artwork, so it lights the ground the
  // diagram sits on instead of slicing the diagram - which is what the old
  // over-the-top version did, and it was the single worst thing in the picture.
  // Two passes, one wide and one narrow, at different speeds, so the sweep never
  // lands in the same place twice.
  const passes = [
    { period: 0.85, width: 0.26, alpha: 0.11, accent: false },
    { period: 1.45, width: 0.15, alpha: 0.14, accent: true },
  ];
  passes.forEach((pass) => {
    const at = (t / pass.period) % 1;
    const x = -W * 0.30 + at * W * 1.6;
    ctx.save();
    const gradient = ctx.createLinearGradient(x - W * pass.width, 0, x + W * pass.width, 0);
    gradient.addColorStop(0, pass.accent ? 'rgba(180,118,42,0)' : `rgba(${tint0(palette)},0)`);
    gradient.addColorStop(0.5, pass.accent
      ? `rgba(180,118,42,${pass.alpha})`
      : `rgba(${tint0(palette)},${pass.alpha})`);
    gradient.addColorStop(1, pass.accent ? 'rgba(180,118,42,0)' : `rgba(${tint0(palette)},0)`);
    ctx.globalAlpha = ctx.globalAlpha;
    ctx.fillStyle = gradient;
    ctx.fillRect(x - W * pass.width, 0, W * pass.width * 2, H);
    ctx.restore();
  });

  const cursorPass = ((t / 1.15) % 1);
  const cursorX = -W * 0.05 + cursorPass * W * 1.1;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.35;
  ctx.fillStyle = palette.accent;
  ctx.fillRect(cursorX, H * 0.10, Math.max(3, W * 0.0035), H * 0.72);
  ctx.restore();

  const bloomX = W * (0.46 + 0.26 * Math.cos((t / 3.1) * Math.PI * 2));
  const bloomY = H * (0.44 + 0.20 * Math.sin((t / 2.3) * Math.PI * 2));
  const bloom = ctx.createRadialGradient(bloomX, bloomY, 0, bloomX, bloomY, W * 0.38);
  const tint = palette.dark ? '255,255,255' : '255,255,255';
  bloom.addColorStop(0, `rgba(${tint},${palette.dark ? 0.16 : 0.46})`);
  bloom.addColorStop(1, `rgba(${tint},0)`);
  ctx.save();
  ctx.fillStyle = bloom;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();

  // A soft accent band crossing the frame, one pass every 2.1 s.
  const pass = ((t / 1.25) % 1);
  const bandX = -W * 0.35 + pass * W * 1.7;
  const grad = ctx.createLinearGradient(bandX, 0, bandX + W * 0.24, H * 0.18);
  grad.addColorStop(0, 'rgba(180,118,42,0)');
  grad.addColorStop(0.5, palette.dark ? 'rgba(242,194,48,0.14)' : 'rgba(180,118,42,0.15)');
  grad.addColorStop(1, 'rgba(180,118,42,0)');
  ctx.save();
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.moveTo(bandX, H * 0.16);
  ctx.lineTo(bandX + W * 0.09, H * 0.10);
  ctx.lineTo(bandX + W * 0.34, H * 0.80);
  ctx.lineTo(bandX + W * 0.25, H * 0.86);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
  const baseY = H * 0.79;
  const x0 = W * 0.055;

  // Ticks: one per line, filling across its own window.
  const tickW = W * 0.016;
  const tickGap = W * 0.006;
  section.lines.forEach((line, i) => {
    const filled = clamp((t - line.start) / Math.max(0.25, (line.end - line.start) * 0.85));
    if (filled <= 0) return;
    const height = H * (0.012 + 0.010 * filled);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (0.30 + 0.35 * filled);
    ctx.fillStyle = filled >= 1 ? palette.accent : palette.ink;
    ctx.fillRect(x0 + i * (tickW + tickGap), baseY - height, tickW, height);
    ctx.restore();
  });
  const railEnd = x0 + section.lines.length * (tickW + tickGap);
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.16;
  ctx.fillStyle = palette.ink;
  ctx.fillRect(x0, baseY, railEnd - x0, Math.max(1, H * 0.0012));
  ctx.restore();

  // Meter: four bars, four periods, no shared phase. Cheap and continuous.
  const meterX = W * 0.895;
  const periods = [0.61, 0.83, 1.07, 0.72];
  periods.forEach((period, i) => {
    const pulse = 0.35 + 0.65 * Math.abs(Math.sin((t / period) * Math.PI + i * 1.1));
    const height = H * 0.085 * pulse;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.45;
    ctx.fillStyle = i % 2 === 0 ? palette.accent : palette.ink;
    ctx.fillRect(meterX + i * W * 0.018, H * 0.70 - height, W * 0.009, height);
    ctx.restore();
  });

  // Dust: deterministic drift, wrapping at the top of its band.
  const band = { top: H * 0.30, bottom: H * 0.62, left: W * 0.78, right: W * 0.985 };
  for (let i = 0; i < 44; i += 1) {
    const seed = (i * 2654435761) % 1000 / 1000;
    const speed = 0.09 + seed * 0.16;
    const span = band.bottom - band.top;
    const y = band.bottom - ((t * speed * H + seed * span) % span);
    const x = band.left + ((seed * 977 + i * 61) % 1000) / 1000 * (band.right - band.left)
      + Math.sin(t * 0.6 + i) * W * 0.004;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (0.14 + 0.16 * seed);
    ctx.fillStyle = palette.ink;
    const size = H * (0.0035 + 0.0035 * seed);
    ctx.fillRect(x, y, size, size);
    ctx.restore();
  }
}

/**
 * The ambient architecture: large shapes that give every frame a structure.
 *
 * A diagram beat has its own geometry. A statement beat had nothing but a line of
 * type in an empty field, which is why the film read as text on a background even
 * after the diagrams arrived. Each section now carries two or three big, quiet
 * forms behind the artwork - a ring, an arc, a plate, a dotted field - chosen from
 * the section index so every chapter has a different silhouette and no two
 * chapters look like the same slide.
 *
 * They are drawn from the section's clock, so they move through the beats instead
 * of restarting on each one, and at four to seven percent opacity they are felt
 * before they are seen. Nothing rotates fast, nothing pulses, nothing shakes: the
 * drift is one direction, at about a hundredth of the frame per second.
 */
function ambientArt(ctx, section, sectionLocal, palette) {
  const t = sectionLocal;
  const ink = palette.ink;
  const accent = palette.accent;
  const alpha = (value) => { ctx.globalAlpha = ctx.globalAlpha * value; };
  const families = [
    // A ring and an arc: the film's measuring motif, off the right edge.
    () => {
      const cx = W * (0.84 + 0.03 * Math.sin(t * 0.21));
      const cy = H * (0.34 + 0.012 * Math.cos(t * 0.17));
      ctx.save();
      ctx.strokeStyle = ink;
      alpha(0.09);
      ctx.lineWidth = W * 0.012;
      ctx.beginPath();
      ctx.arc(cx, cy, W * 0.20, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = accent;
      alpha(0.32);
      ctx.lineWidth = W * 0.005;
      ctx.beginPath();
      ctx.arc(cx, cy, W * 0.20, -Math.PI * 0.5 + t * 0.12, Math.PI * 0.1 + t * 0.12);
      ctx.stroke();
      ctx.restore();
    },
    // Two plates crossing: a diptych behind the sentence.
    () => {
      ctx.save();
      ctx.translate(W * (0.74 + 0.008 * Math.sin(t * 0.13)), H * 0.30);
      ctx.rotate(-0.32 + 0.012 * Math.sin(t * 0.11));
      ctx.fillStyle = ink;
      alpha(0.085);
      ctx.fillRect(-W * 0.11, -H * 0.30, W * 0.22, H * 0.60);
      ctx.fillStyle = accent;
      alpha(0.22);
      ctx.fillRect(W * 0.02, -H * 0.22, W * 0.05, H * 0.44);
      ctx.restore();
    },
    // A dotted field with a hard rule through it: the ledger motif.
    () => {
      ctx.save();
      ctx.fillStyle = ink;
      alpha(0.18);
      for (let i = 0; i < 90; i += 1) {
        const seed = ((i * 2654435761) % 1000) / 1000;
        const x = W * (0.62 + ((seed * 613) % 1000) / 1000 * 0.36);
        const y = H * (0.14 + ((seed * 977) % 1000) / 1000 * 0.62) + Math.sin(t * 0.4 + i) * H * 0.004;
        const size = Math.max(1.5, H * (0.002 + seed * 0.003));
        ctx.fillRect(x, y, size, size);
      }
      ctx.fillStyle = accent;
      alpha(0.26);
      ctx.fillRect(W * 0.70, H * (0.16 + 0.02 * Math.sin(t * 0.15)), W * 0.0016, H * 0.52);
      ctx.restore();
    },
    // Stacked bars: the measure motif, half off the frame.
    () => {
      ctx.save();
      const base = H * 0.60;
      for (let i = 0; i < 5; i += 1) {
        const level = 0.35 + 0.3 * Math.abs(Math.sin(t * 0.18 + i * 0.9));
        const h = H * 0.26 * level;
        ctx.fillStyle = i % 2 ? accent : ink;
        alpha(i % 2 ? 0.24 : 0.10);
        ctx.fillRect(W * (0.80 + i * 0.042), base - h, W * 0.028, h);
      }
      ctx.restore();
    },
  ];
  const chosen = [
    families[section.index % families.length],
    families[(section.index + 2) % families.length],
  ];
  // A slow push across the section, no camera involved: the whole ambient layer
  // grows by six percent and slides a little, so every frame of a beat differs
  // from the one before it over a large area. It is the difference between a
  // still image with a light on it and a picture that is alive. One direction,
  // bounded, never reversing, and no shake.
  const push = 1 + 0.06 * clamp(t / Math.max(0.001, section.seconds));
  ctx.save();
  ctx.translate(W * 0.5, H * 0.5);
  ctx.scale(push, push);
  ctx.translate(-W * 0.5 - W * 0.012 * clamp(t / Math.max(0.001, section.seconds)), -H * 0.5);
  chosen.forEach((draw) => draw());
  ctx.restore();
  ctx.globalAlpha = 1;
}

/**
 * Motion that belongs to the frame rather than to any one picture.
 *
 * A diagram arrives, builds, and then holds. Held is right for the thought and
 * wrong for the medium: measured on the first cut, 72% of frames were
 * near-static, which is a slideshow with a soundtrack. This layer keeps the
 * frame alive underneath every template without competing with it:
 *
 *   - drift: small marks travelling slowly up the frame, wrapping at the top.
 *     Deterministic from the section clock, so the render stays reproducible.
 *   - a meter: four slim bars breathing at different periods, so no two frames a
 *     second apart are identical even when a diagram has finished building.
 *   - the line rail: one tick per sentence in the section, filling as each line
 *     is spoken. It is the film's own progress bar and it moves at speech pace.
 *
 * All of it sits outside every template region's busy area and above the caption
 * band, and its contrast is deliberately low: it is felt, not read.
 */
function motionField(ctx, section, sectionLocal, palette) {
  const t = sectionLocal;
  // Drift.
  for (let i = 0; i < 26; i += 1) {
    const seed = ((i * 2654435761) % 997) / 997;
    const speed = H * (0.022 + seed * 0.035);
    const spanY = H * 0.62;
    const y = H * 0.86 - ((t * speed + seed * spanY) % spanY);
    const x = W * (0.04 + ((seed * 631 + i * 37) % 1000) / 1000 * 0.52) + Math.sin(t * 0.5 + i) * W * 0.002;
    const size = Math.max(2, H * (0.0022 + seed * 0.0035));
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (0.10 + seed * 0.10);
    ctx.fillStyle = i % 5 === 0 ? palette.accent : palette.ink;
    ctx.fillRect(x, y, size, size);
    ctx.restore();
  }

  // The meter: four bars, four periods, never in step.
  const periods = [0.83, 1.07, 1.31, 1.61];
  const baseY = H * 0.70;
  periods.forEach((period, i) => {
    const level = 0.25 + 0.75 * Math.abs(Math.sin((t / period) * Math.PI + i * 0.7));
    const height = H * 0.075 * level;
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * 0.34;
    ctx.fillStyle = i % 2 ? palette.ink : palette.accent;
    ctx.fillRect(W * (0.895 + i * 0.021), baseY - height, W * 0.011, height);
    ctx.restore();
  });

  // The line rail: one tick per sentence, filling in order.
  const lines = section.lines || [];
  if (lines.length) {
    const y = H * 0.80;
    const x0 = W * 0.055;
    const tickW = W * 0.012;
    const gap = W * 0.006;
    lines.forEach((line, i) => {
      const progress = clamp((sectionLocal - line.start) / Math.max(0.2, line.end - line.start));
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * (0.18 + 0.55 * progress);
      ctx.fillStyle = progress > 0 ? palette.accent : palette.ink;
      ctx.fillRect(x0 + i * (tickW + gap), y, tickW, H * 0.007 * (0.5 + progress));
      ctx.restore();
    });
  }
}

/**
 * The ground a beat stands on.
 *
 * This used to be a white rounded card behind every picture, which made a
 * full-frame film look like a slide deck: the artwork sat in a box and the frame
 * around it was dead. There is no card any more. What replaces it is a ground
 * the artwork is *on*:
 *
 *   - a twelve-column grid, drawn as hairlines at six percent opacity. Barely
 *     visible, and the reason the diagrams line up with each other;
 *   - a horizon across the frame at the height a chart's baseline sits, which
 *     the rail and the dial both key to;
 *   - the beat block, which still walks the four corners so consecutive beats
 *     never share a silhouette.
 *
 * All of it sits below the contrast of the artwork, so nothing competes with the
 * sentence being said.
 */
function beatPlate(ctx, shot, section, beatLocal) {
  const arrive = span(beatLocal, 0, 0.34);
  const palette = section.palette;
  const ink = palette.dark ? '255,255,255' : '18,35,63';
  const margin = W * 0.055;
  const settle = 1 - (1 - clamp(arrive)) ** 3;

  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.032 * settle;
  ctx.fillStyle = `rgba(${ink},1)`;
  const columns = 12;
  for (let i = 1; i < columns; i += 1) {
    const x = margin + ((W - margin * 2) * i) / columns;
    ctx.fillRect(x, H * 0.10, Math.max(1, W * 0.0006), H * 0.72);
  }
  ctx.restore();

  // The horizon: the line every chart in the film hangs from.
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.12 * settle;
  ctx.fillStyle = `rgba(${ink},1)`;
  ctx.fillRect(margin, H * 0.655, (W - margin * 2) * settle, Math.max(1, H * 0.0013));
  ctx.restore();

  // A tonal field, one per beat, bleeding off an edge of the frame.
  //
  // This is what replaced the white card, and it has to do the card's job
  // without the card's look: a large area of the frame that changes on every
  // beat, so no two beats share a composition and the picture keeps moving.
  // It bleeds past the frame edge on purpose - a panel with all four corners
  // visible is a card; a panel that runs off the frame is a shadow on the ground.
  const fields = [
    { x: -0.30, y: -0.10, w: 0.46, h: 0.92, from: -1 },
    { x: 0.86, y: 0.02, w: 0.42, h: 0.92, from: 1 },
    { x: 0.10, y: 0.86, w: 0.72, h: 0.34, from: -1 },
    { x: -0.34, y: 0.04, w: 0.34, h: 0.96, from: 1 },
  ];
  const field = fields[shot.beatIndex % fields.length];
  const enter = span(beatLocal, 0, 0.55);
  const fieldSettle = 1 - (1 - clamp(enter)) ** 3;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.05 * fieldSettle;
  const fieldX = W * (field.x + field.from * ((1 - fieldSettle) * 0.05 + beatLocal * 0.010));
  const gradient = ctx.createLinearGradient(fieldX, H * field.y, fieldX + W * field.w, H * (field.y + field.h));
  gradient.addColorStop(0, `rgba(${ink},0.95)`);
  gradient.addColorStop(0.55, `rgba(${ink},0.35)`);
  gradient.addColorStop(1, `rgba(${ink},0)`);
  ctx.fillStyle = gradient;
  ctx.fillRect(fieldX, H * field.y, W * field.w, H * field.h);
  ctx.restore();

  // The block: its corner follows the beat, and it slides in with the ground.
  const corners = [
    [0.055, 0.115], [0.845, 0.115], [0.055, 0.705], [0.845, 0.705],
  ];
  const corner = corners[shot.beatIndex % corners.length];
  const blockW = W * 0.055;
  const blockH = H * 0.055;
  const slide = (1 - arrive) * W * 0.03;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.85 * arrive;
  ctx.fillStyle = section.palette.accent;
  ctx.fillRect(W * corner[0] - slide, H * corner[1], blockW, blockH);
  ctx.restore();
}

function paint(target, shot, at) {
  const section = shot.section;
  const sectionLocal = at - section.start;
  // Clamped: during any pre-roll before the first beat starts, the frame used
  // to compose a shot with a negative local time, which every reveal reads as
  // "not yet" - so the film opened on a pale, empty field for its first second.
  const beatLocal = Math.max(0, at - shot.start);
  target.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  target.clearRect(0, 0, W, H);
  drawField(target, { w: W, h: H, t: sectionLocal + section.start * 0.17, palette: section.palette });

  // Ambient motion first, artwork on top. The second unit used to be painted
  // after the template, so its travelling line ran straight through the dial and
  // the rail - a scanner cutting the picture in half.
  ambientArt(target, section, sectionLocal, section.palette);
  motionField(target, section, sectionLocal, section.palette);
  secondUnit(target, section, sectionLocal, section.palette);
  beatPlate(target, shot, section, beatLocal);

  // A template that builds rows animates *within* its picture: the row slides in,
  // the row fades up. Handing it the beat's clock makes every stored row replay
  // its entrance on every new beat, so the list flickers and two rows overlap
  // mid-slide. Those templates get the section's clock instead - the rows arrive
  // once, in order, and stay put for the rest of the section.
  const rowTemplate = ROW_TEMPLATES.has(shot.template);
  const templateLocal = rowTemplate ? sectionLocal : beatLocal;
  const templateSeconds = rowTemplate ? section.seconds : shot.seconds;
  target.save();
  // A diagram that builds its own rows must not also be faded in on every beat:
  // the row is the entrance, and a global fade on top of it makes the whole
  // picture ghost in and out inside a section - soft, and the reason a solid
  // bar looked like tinted glass. Single-object templates keep a short fade,
  // because they arrive whole.
  target.globalAlpha = rowTemplate ? 1 : span(beatLocal, 0, 0.22);
  // A slow push on the artwork across its section: the picture dollies in by
  // three percent and drifts a hair, one direction, eased, never reversing. This
  // is a camera move, not a camera shake - the frame is not thrown about, it is
  // leaning in - and it is what keeps a finished diagram from being a still.
  const region = REGIONS[shot.region];
  const push = 1 + 0.055 * clamp(templateLocal / Math.max(0.001, templateSeconds));
  const anchorX = (region.x + region.w / 2) * W;
  const anchorY = (region.y + region.h / 2) * H;
  target.save();
  target.translate(anchorX - W * 0.004 * clamp(templateLocal / Math.max(0.001, templateSeconds)), anchorY);
  target.scale(push, push);
  target.translate(-anchorX, -anchorY);
  drawTemplate(target, shot.template, {
    w: W, h: H, region: shot.region, seconds: templateSeconds, local: templateLocal,
    palette: section.palette, t: templateLocal, storedRows: rowTemplate,
    ...propsForBeat(section, shot, section.beats.length, section.palette),
  });
  target.restore();
  target.restore();

  chrome(target, shot, sectionLocal);
  drawGrain(target, Math.round(at * FPS), section.palette);
  drawGrain(target, Math.round(at * FPS), section.palette);
  captions(target, section, sectionLocal, shot);
  if (Math.abs(target.globalAlpha - 1) > 1e-6) {
    throw new Error(`globalAlpha leaked to ${target.globalAlpha} after beat ${shot.id}`);
  }
}

// ------------------------------------------------------------------ rendering
const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');
const canvasA = createCanvas(OPTS.width, OPTS.height);
const ctxA = canvasA.getContext('2d');
const canvasB = createCanvas(OPTS.width, OPTS.height);
const ctxB = canvasB.getContext('2d');

function render(t) {
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const index = shotIndexAt(t);
  const shot = SHOTS[index];

  // Beats inside a section cut; sections arrive with a device. A device on
  // every beat would be five transitions in two seconds, which is a slideshow.
  const arriving = index === 0 || shot.beatIndex === 0;
  const cutSeconds = shot.section.arrive === 'focus' ? houseSeconds('focus') : houseSeconds('transition');
  const tp = shot.section.arrive && shot.section.arrive !== 'cut'
    ? span(t, shot.start, shot.start + cutSeconds) : 1;
  if (arriving && shot.section.arrive !== 'cut' && index > 0 && tp < 1) {
    paint(ctxA, SHOTS[index - 1], Math.min(SHOTS[index - 1].end - 0.02, shot.start - 0.02));
    paint(ctxB, shot, t);
    reveal(ctx, {
      kind: shot.section.arrive, p: tp, a: canvasA, b: canvasB,
      w: OPTS.width, h: OPTS.height, accent: shot.section.palette.accent,
    });
    return;
  }
  paint(ctx, shot, t);

  const fadeIn = 1 - span(t, 0, 0.12);
  if (fadeIn > 0) {
    ctx.save();
    ctx.globalAlpha = fadeIn;
    ctx.fillStyle = SHOTS[0].section.palette.field[0];
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
}

// ----------------------------------------------------------------------- plan
function scoreCues() {
  const cues = [];
  for (const shot of SHOTS) {
    const first = shot.beatIndex === 0;
    cues.push({
      at: Number(Math.max(0, shot.start + 0.02).toFixed(3)),
      kind: shot.start < 0.05 ? 'swell' : (first ? 'whoosh' : 'pop'),
      gain: first ? 0.5 : 0.3,
      length: first ? 0.6 : 0.3,
    });
    if (shot.section.kind === 'payoff') {
      cues.push({ at: Number((shot.start + 0.3).toFixed(3)), kind: 'impact', gain: 0.55, length: 0.9 });
    }
    if (shot.section.kind === 'recap' && first) {
      cues.push({ at: Number((shot.start + 0.12).toFixed(3)), kind: 'riser', gain: 0.4, length: 0.8 });
    }
  }
  return cues.filter((cue) => cue.at < DURATION - 0.05);
}

function plan() {
  return {
    generator: 'video_studio/films/from_brief.mjs',
    brief: {
      slug: BRIEF.slug || path.basename(String(OPTS.brief), '.json'),
      title: BRIEF.title,
      promise: BRIEF.promise || null,
      hookType: BRIEF.hookType || null,
      thumbnail: BRIEF.thumbnail || null,
    },
    look: BRIEF.look || 'light',
    fps: FPS,
    width: W,
    height: H,
    duration_seconds: Number(DURATION.toFixed(3)),
    frames: Math.round(DURATION * FPS),
    voiced: Boolean(TIMINGS),
    sections: SECTIONS.map((section) => ({
      id: section.id, index: section.index, heading: section.heading, kind: section.kind,
      situation: section.situation, start: Number(section.start.toFixed(3)),
      end: Number(section.end.toFixed(3)), seconds: Number(section.seconds.toFixed(3)),
      arrive: section.arrive, reason: section.reason,
    })),
    // What each beat actually puts in front of the viewer, so the picture can be
    // audited against the narration without decoding frames: the plan says what
    // was drawn and the captions say what was said, and both carry times.
    shots: SHOTS.map((shot) => ({
      id: shot.id, section: shot.section.id, section_index: shot.section.index,
      beat: shot.beatIndex + 1,
      start: Number(shot.start.toFixed(3)), end: Number(shot.end.toFixed(3)),
      seconds: Number(shot.seconds.toFixed(3)),
      template: shot.template, region: shot.region,
      shows: shot.shownText || null,
    })),
    captions: SECTIONS.flatMap((section) => section.lines.map((line) => ({
      start: Number((section.start + line.start).toFixed(3)),
      end: Number((section.start + line.end).toFixed(3)),
      lines: line.captionLines,
      text: line.text,
    }))),
    score: scoreCues(),
  };
}

/** The two files the shared render tool reads: the plan, and the film itself. */
function writeFilm(outDir) {
  const film = {
    duration_seconds: Number(DURATION.toFixed(3)),
    fps: FPS,
    generator: 'video_studio/films/from_brief.mjs',
    title: BRIEF.title,
    shots: SECTIONS.map((section) => ({
      id: section.id,
      start: Number(section.start.toFixed(3)),
      end: Number(section.end.toFixed(3)),
      beats: section.beats.length,
      template: section.beats[0].template,
      arrive: section.arrive,
    })),
    // The sound design synthesises exactly these cues, so what is heard is what
    // the picture declared rather than a track laid over it.
    score: scoreCues(),
  };
  fs.writeFileSync(path.join(outDir, 'film.json'), JSON.stringify(film, null, 2));
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({
    width: OPTS.width,
    height: OPTS.height,
    fps: FPS,
    frame_count: Math.round(DURATION * FPS),
    duration_seconds: Number(DURATION.toFixed(3)),
    source: 'video_studio/films/from_brief.mjs',
    brief: path.basename(String(OPTS.brief)),
    voiced: Boolean(TIMINGS),
  }, null, 2));
}

function main() {
  const outDir = path.resolve(OPTS.out);
  fs.mkdirSync(outDir, { recursive: true });

  if (OPTS.plan) {
    // The shared renderer asks a film for its plan before deciding how to slice
    // the render; it reads `frames` and nothing else.
    const full = plan();
    writeFilm(outDir);
    process.stdout.write(JSON.stringify(full));
    return;
  }

  const planPath = path.join(outDir, 'plan.json');
  fs.writeFileSync(planPath, JSON.stringify(plan(), null, 2));
  writeFilm(outDir);
  if (!OPTS.quiet) {
    console.log(`${SECTIONS.length} sections, ${SHOTS.length} beats, ${DURATION.toFixed(1)}s, ${Math.round(DURATION * FPS)} frames -> ${planPath}`);
    for (const shot of SHOTS) {
      console.log(`  ${shot.id.padEnd(14)} ${shot.start.toFixed(2).padStart(7)}s  ${shot.template.padEnd(17)} ${shot.region.padEnd(6)}`);
    }
  }
  if (OPTS.planOnly) return;

  if (OPTS.still) {
    for (const seconds of OPTS.still) {
      render(seconds);
      const file = path.join(outDir, `still-${seconds.toFixed(2)}.jpg`);
      fs.writeFileSync(file, canvas.toBuffer('image/jpeg', OPTS.quality));
      if (!OPTS.quiet) console.log(`still ${seconds.toFixed(2)}s -> ${file}`);
    }
    return;
  }

  const total = Math.round(DURATION * FPS);
  const from = Math.max(0, Math.round(OPTS.from));
  const to = Math.min(total, OPTS.to === null ? total : Math.round(OPTS.to));
  const started = Date.now();
  for (let frame = from; frame < to; frame += 1) {
    render(frame / FPS);
    fs.writeFileSync(
      path.join(outDir, `frame-${String(frame).padStart(6, '0')}.jpg`),
      canvas.toBuffer('image/jpeg', OPTS.quality),
    );
    if (!OPTS.quiet && (frame - from) % 120 === 0) {
      const rate = (frame - from + 1) / ((Date.now() - started) / 1000);
      console.log(`frame ${frame}/${to} (${rate.toFixed(1)} fps)`);
    }
  }
  if (!OPTS.quiet) console.log(`done: ${to - from} frames -> ${outDir}`);
}

main();
