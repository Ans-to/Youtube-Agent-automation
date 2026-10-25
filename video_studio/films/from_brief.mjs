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
      timings.set(row.id, { start, end });
    }
  }
  return timings.size ? timings : null;
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
  if (beatIndex === 0 && section.template
      && candidates.includes(section.template) && withinBand(section.template, seconds)) {
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

function buildSections(brief, timings) {
  const palette = PALETTES[brief.look || 'light'];
  let previousTransition = 'cut';
  let cursor = 0;

  return brief.sections.map((section, index) => {
    const candidates = candidateTemplates(section);
    let start;
    let end;
    let lines;
    if (timings) {
      const found = section.lines
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
    const byWords = Math.max(1, Math.floor(words / 2));
    let lengths;
    if (progressive) {
      lengths = beatLengths(seconds, candidates, byWords);
    } else {
      // A comparison or a number cannot show a new piece on each beat, so the
      // section is cut into the fewest beats that still fit the template's
      // window. Cutting it to the usual 1.8 s beat would draw the same picture
      // three times, which is the frozen frame the repeat gate exists to catch.
      const meta = TEMPLATES.get(section.template || candidates[0]);
      const fewest = Math.max(1, Math.ceil(seconds / (meta.maxSeconds - 0.02)));
      lengths = Array.from({ length: fewest }, () => seconds / fewest);
    }
    const beats = [];
    let beatStart = start;
    let previousTemplate = null;
    const recentTemplates = [];
    lengths.forEach((length, beatIndex) => {
      const template = templateForBeat(section, candidates, length, previousTemplate, recentTemplates, beatIndex);
      previousTemplate = template;
      recentTemplates.push(template);
      if (recentTemplates.length > 2) recentTemplates.shift();
      const meta = TEMPLATES.get(template);
      const region = section.region || meta.regions[0];
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
      section.kind === 'recap' ? 'release'
        : section.kind === 'outro' ? 'final'
          : 'new-scene',
      previousTransition,
    );
    previousTransition = arrive;

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
function captions(ctx, section, sectionLocal) {
  const band = RESERVED.caption;
  const x = band.x * W + W * 0.055;
  const y = band.y * H + band.h * H * 0.34;
  const size = Math.round(H * 0.0305);
  const step = size * 1.32;
  for (const line of section.lines) {
    if (sectionLocal < line.start - 0.02 || sectionLocal > line.end + 0.18) continue;
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
function propsForBeat(section, beat, beatCount, palette) {
  const props = themedProps(beat.template, section, palette);
  if (beatCount <= 1) return props;
  const index = beat.beatIndex;
  if (beat.template === 'kinetic-headline') {
    const chunks = splitWords(props.text || '', beatCount);
    props.text = chunks[Math.min(index, chunks.length - 1)];
    return props;
  }
  if (beat.template === 'list-build' || beat.template === 'stack-push') {
    const items = props.items || [];
    const upto = Math.min(items.length, Math.ceil(((index + 1) / beatCount) * items.length));
    props.items = items.slice(0, Math.max(1, upto));
    return props;
  }
  if (beat.template === 'code-typing') {
    const lines = props.lines || [];
    const upto = Math.min(lines.length, index + 1);
    props.lines = lines.slice(0, Math.max(1, upto));
    return props;
  }
  if (beat.template === 'count-up' && index > 0) {
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

  // A cursor crossing the frame: a narrow, definite line rather than a wash. It
  // reads as the picture being measured, which is what the film is doing.
  const cursorPass = ((t / 2.2) % 1);
  const cursorX = -W * 0.05 + cursorPass * W * 1.1;
  ctx.save();
  // The cursor carries a soft column of light with it, so the pass reads as a
  // sweep of the field rather than as a wire crossing the frame - and it is the
  // contrast that keeps the frame difference honest.
  const halo = ctx.createLinearGradient(cursorX - W * 0.16, 0, cursorX + W * 0.04, 0);
  halo.addColorStop(0, 'rgba(18,35,63,0)');
  halo.addColorStop(0.75, palette.dark ? 'rgba(255,255,255,0.12)' : 'rgba(18,35,63,0.155)');
  halo.addColorStop(1, 'rgba(18,35,63,0)');
  ctx.globalAlpha = ctx.globalAlpha * 0.9;
  ctx.fillStyle = halo;
  ctx.fillRect(cursorX - W * 0.16, 0, W * 0.20, H);
  ctx.globalAlpha = ctx.globalAlpha * 0.34;
  ctx.fillStyle = palette.accent;
  ctx.fillRect(cursorX, H * 0.055, W * 0.0035, H * 0.89);
  ctx.restore();

  const bloomX = W * (0.42 + 0.20 * Math.cos((t / 3.1) * Math.PI * 2));
  const bloomY = H * (0.40 + 0.16 * Math.sin((t / 2.3) * Math.PI * 2));
  const bloom = ctx.createRadialGradient(bloomX, bloomY, 0, bloomX, bloomY, W * 0.38);
  const tint = palette.dark ? '255,255,255' : '255,255,255';
  bloom.addColorStop(0, `rgba(${tint},${palette.dark ? 0.10 : 0.33})`);
  bloom.addColorStop(1, `rgba(${tint},0)`);
  ctx.save();
  ctx.fillStyle = bloom;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();

  // A soft accent band crossing the frame, one pass every 2.1 s.
  const pass = ((t / 1.7) % 1);
  const bandX = -W * 0.35 + pass * W * 1.7;
  const grad = ctx.createLinearGradient(bandX, 0, bandX + W * 0.30, H * 0.18);
  grad.addColorStop(0, 'rgba(180,118,42,0)');
  grad.addColorStop(0.5, palette.dark ? 'rgba(242,194,48,0.12)' : 'rgba(180,118,42,0.16)');
  grad.addColorStop(1, 'rgba(180,118,42,0)');
  ctx.save();
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.moveTo(bandX, H * 0.10);
  ctx.lineTo(bandX + W * 0.16, H * 0.02);
  ctx.lineTo(bandX + W * 0.46, H * 0.86);
  ctx.lineTo(bandX + W * 0.30, H * 0.94);
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
 * The plate a beat sits on, and the block that marks which beat it is.
 *
 * Without them the film is pale type on a pale field, and at any distance that
 * is one continuous image: the composition gate measured a seventeen-second
 * "arrangement" across seven different beats, which is exactly what a viewer
 * would also see. The plate gives each beat an edge, and the block walks around
 * the four corners with the beat index, so consecutive beats never share a
 * silhouette even when they share a template.
 */
function beatPlate(ctx, shot, section, beatLocal) {
  const arrive = span(beatLocal, 0, 0.26);
  const palette = section.palette;
  const region = REGIONS[shot.region];
  const pad = W * 0.022;
  const box = {
    x: region.x * W - pad,
    y: region.y * H - pad * 0.6,
    w: region.w * W + pad * 2,
    h: region.h * H + pad * 1.2,
  };
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * 0.62 * arrive;
  roundRect(ctx, box.x, box.y, box.w, box.h, W * 0.012);
  ctx.fillStyle = palette.dark ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.66)';
  ctx.fill();
  ctx.restore();

  // The block: its corner follows the beat, and it slides in with the plate.
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

  beatPlate(target, shot, section, beatLocal);

  target.save();
  target.globalAlpha = span(beatLocal, 0, 0.3);
  drawTemplate(target, shot.template, {
    w: W, h: H, region: shot.region, seconds: shot.seconds, local: beatLocal,
    palette: section.palette, t: beatLocal,
    ...propsForBeat(section, shot, section.beats.length, section.palette),
  });
  target.restore();

  secondUnit(target, section, sectionLocal, section.palette);
  chrome(target, shot, sectionLocal);
  captions(target, section, sectionLocal);
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
    shots: SHOTS.map((shot) => ({
      id: shot.id, section: shot.section.id, section_index: shot.section.index,
      beat: shot.beatIndex + 1,
      start: Number(shot.start.toFixed(3)), end: Number(shot.end.toFixed(3)),
      seconds: Number(shot.seconds.toFixed(3)),
      template: shot.template, region: shot.region,
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
