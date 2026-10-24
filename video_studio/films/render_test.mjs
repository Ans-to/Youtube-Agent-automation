/**
 * A thirty-second render test: "One keystroke, one change".
 *
 * This is not a scene from the long film. It is a short piece built to exercise
 * the parts of the pipeline that are expensive to discover late: a typing beat
 * that has to land on a character, a pointer that has to press something and be
 * answered, kinetic type at its largest, every transition device, and sound that
 * is caused by the picture rather than laid over it.
 *
 * The script, in full, in thirty seconds:
 *
 *   0.0-5.4   You type "fix the login page" and press enter.      keys, click
 *   5.4-11.6  The agent writes the fix, line by line, and commits.  keys, pops
 *   11.6-17.6 Type: NO CODE / ONE KEY / A WORKING PAGE.            soft pops
 *   17.6-21.6 The test suite runs, line by line.                   pops
 *   21.6-30.0 PRESS ENTER, pressed, and out.                       click, fade
 *
 * One timeline drives both media. Every sound is a cue written from the same
 * constant that draws the thing that made it - ``EV.enterPress`` is both the
 * moment the key is drawn pressed and the moment the click is written - so a
 * click cannot drift away from the press that caused it.
 *
 *   node video_studio/films/render_test.mjs --out frames --width 1920
 *   node video_studio/films/render_test.mjs --out stills --width 1280 --still 2,8,16
 *   node video_studio/films/render_test.mjs --cues        # shots and cue sheet
 *
 * The sound is synthesised from that sheet by tools/render_test_film.py, which
 * also mixes, masters, muxes and reports. No samples, no downloads, no licences.
 */
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

import { GlobalFonts, createCanvas } from '@napi-rs/canvas';
import {
  UI, clamp, lerp, span, ease, text, measure, roundRect, panel, chip, cursor,
  clickRing, rule, checkRow,
} from '../motion/ui.mjs';
import { PALETTES, STAGE_MARGIN, SETTLE_MAX, drawField, drawPhrase } from '../motion/wordstage.mjs';
import { reveal } from '../motion/transitions.mjs';
import { seconds as houseSeconds } from '../motion/timings.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');

const DESIGN_W = 3840;
const DESIGN_H = 2160;
const DURATION = 30;
const FPS = 30;

// -------------------------------------------------------------------- options
function parseArgs(argv) {
  const opts = { out: 'frames', width: 1920, height: null, quality: 90, from: 0, to: null, still: null, quiet: false, cues: false, look: 'light' };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = () => argv[(i += 1)];
    if (flag === '--out') opts.out = value();
    else if (flag === '--width') opts.width = Number(value());
    else if (flag === '--quality') opts.quality = Number(value());
    else if (flag === '--from') opts.from = Number(value());
    else if (flag === '--to') opts.to = Number(value());
    else if (flag === '--still') opts.still = value().split(',').map(Number);
    else if (flag === '--quiet') opts.quiet = true;
    else if (flag === '--cues') opts.cues = true;
    // Accepted so the shared determinism checker can drive this film the same
    // way it drives the long one. There is only one look here: the owner chose
    // light and the dark stage is reference material, so asking for dark is an
    // error rather than something quietly ignored.
    else if (flag === '--look') opts.look = value();
    else throw new Error(`Unknown option: ${flag}`);
  }
  opts.height = opts.height || Math.round((opts.width * DESIGN_H) / DESIGN_W / 2) * 2;
  return opts;
}

const OPTS = parseArgs(process.argv.slice(2));
if (OPTS.look !== 'light') throw new Error(`render_test is light only, not ${OPTS.look}`);
const W = DESIGN_W;
const H = DESIGN_H;
const SCALE = OPTS.width / W;

const FACES = [
  ['Inter', 'inter-latin-400-normal.woff2'],
  ['Inter', 'inter-latin-600-normal.woff2'],
  ['Inter', 'inter-latin-700-normal.woff2'],
  ['Space Grotesk', 'space-grotesk-latin-700-normal.woff2'],
];
for (const [family, file] of FACES) {
  GlobalFonts.registerFromPath(path.join(STUDIO, 'fonts', file), family);
}

// --------------------------------------------------------------------- script
/**
 * The one table both media read.
 *
 * ``arrive`` is the device that brings the shot in. No two shots next to each
 * other use the same one - ``check_plan`` in the tool refuses a film where they
 * do, because "don't always use the same transition" is a standing note.
 */
const SHOTS = [
  { id: 'prompt', start: 0.0, end: 5.4, arrive: 'cut' },
  { id: 'work', start: 5.4, end: 9.8, arrive: 'push' },
  // Each phrase sits somewhere different relative to the frame. Three lines in a
  // row on the same anchor is a slide deck, not type design; the owner's note on
  // the first kinetic pass was exactly this, so placement lives in the shot table.
  { id: 'type1', start: 9.8, end: 12.0, arrive: 'wipe', phrase: 'NO CODE', size: 0.20, at: [0, 0.02] },
  { id: 'type2', start: 12.0, end: 14.2, arrive: 'cut', phrase: 'ONE KEY', accent: true, size: 0.245, at: [0.185, 0.105] },
  { id: 'type3', start: 14.2, end: 16.4, arrive: 'push', phrase: 'A WORKING PAGE', size: 0.165, at: [0.01, 0.155] },
  { id: 'done', start: 16.4, end: 20.4, arrive: 'focus' },
  { id: 'final', start: 20.4, end: 25.2, arrive: 'cut', phrase: 'PRESS ENTER', size: 0.24, at: [0.02, 0.0] },
  { id: 'close', start: 25.2, end: 30.0, arrive: 'wipe', phrase: 'SHIPPED.', accent: true, size: 0.27, at: [0.0, 0.06] },
];

const EV = {
  typeStart: 1.35,
  // A hand is not a metronome: eight or nine characters a second with a little
  // unevenness. A fixed table, not a random number - the same frame has to render
  // the same picture every time.
  typeStep: 0.115,
  typeWobble: [0.014, -0.009, 0.021, 0.0, -0.016, 0.007],
  typeText: 'fix the login page',
  enterPress: 3.45,
  // The request leaves the field and becomes the job the next shot is running.
  sendStart: 3.9,
  sendEnd: 5.2,
  // The agent writes the fix, one line at a time.
  streamStart: 5.9,
  streamStep: 0.52,
  commitPress: 9.15,
  commit: 9.6,
  // The suite runs, one result at a time.
  testStart: 16.7,
  testStep: 0.45,
  receipt: 19.7,
  // The close: the key arrives, is pressed, and the word lands after it.
  keyArrive: 22.6,
  finalPress: 23.9,
  tailFade: 27.4,
  frameOut: 28.4,
};

/** Every character of the prompt, timed the way it is typed. */
function keystrokes() {
  const times = [];
  let at = EV.typeStart;
  [...EV.typeText].forEach((_, i) => {
    times.push(at);
    at += EV.typeStep + EV.typeWobble[i % EV.typeWobble.length];
  });
  return times;
}
const KEYS = keystrokes();

/** The fix, as the agent writes it. ``+`` and ``-`` are a diff. */
const DIFF = [
  ['-', 'if (!session) {'],
  ['-', '  return null;'],
  ['+', "if (!session) return redirect('/login');"],
  ['+', 'const user = await users.byId(session.uid);'],
  ['+', "if (!user) return redirect('/login');"],
  ['+', "return render('login', { user });"],
  ['+', 'test.login.rendersForUser();'],
];

/** The suite, as it reports. */
const TESTS = [
  'login page loads',
  'password field works',
  'session cookie is set',
  'signed-out redirects',
  'no new warnings',
  'no console errors',
];

/**
 * The sound cue sheet.
 *
 * ``kind`` maps to the procedural synthesiser in video_studio/audio_design.py.
 * Gains are low: this is a UI, not a trailer. The key gain is set against the
 * bed rather than by ear - at 0.085 the strokes sat 1.6 dB above the kick on
 * average, which is a typing shot with no typing in it.
 */
function cueSheet() {
  const cues = [];
  const add = (at, kind, gain, length) => cues.push({
    at: Math.round(at * 1000) / 1000, kind, gain, length,
  });

  add(0.10, 'whoosh', 0.10, 0.55);
  // Typing starts before the box has finished arriving, as it does in life.
  for (const at of KEYS) add(at, 'key', 0.52, 0.05);
  add(EV.enterPress, 'click', 0.24, 0.16);
  add(EV.enterPress + 0.42, 'pop', 0.16, 0.22);
  add(EV.sendStart, 'whoosh', 0.12, 0.7);

  add(SHOTS[1].start, 'whoosh', 0.18, 0.45);
  // One soft tick per line the agent writes. The gain falls as the list grows, so
  // the last line is the quietest, and the rhythm reads as work rather than as a
  // drum roll.
  DIFF.forEach((_, i) => {
    add(EV.streamStart + i * EV.streamStep, 'key', 0.22 - i * 0.012, 0.05);
  });
  add(EV.commitPress, 'click', 0.2, 0.14);
  add(EV.commit, 'pop', 0.18, 0.26);

  add(SHOTS[2].start, 'whoosh', 0.16, 0.45);
  add(SHOTS[2].start + 0.45, 'pop', 0.12, 0.24);
  add(SHOTS[3].start + 0.2, 'pop', 0.11, 0.24);
  add(SHOTS[4].start + 0.2, 'pop', 0.11, 0.24);

  add(SHOTS[5].start, 'whoosh', 0.19, 0.5);
  add(SHOTS[5].start + 0.1, 'swell', 0.1, 0.9);
  TESTS.forEach((_, i) => add(EV.testStart + i * EV.testStep + 0.04, 'pop', 0.12, 0.16));
  add(EV.receipt, 'pop', 0.17, 0.26);

  add(SHOTS[6].start + 0.05, 'impact', 0.16, 0.5);
  add(EV.keyArrive + 0.2, 'pop', 0.12, 0.22);
  add(EV.finalPress, 'click', 0.22, 0.14);
  add(SHOTS[7].start + 0.05, 'impact', 0.15, 0.5);
  add(EV.tailFade + 0.1, 'swell', 0.12, 1.2);

  return cues.sort((a, b) => a.at - b.at);
}

/** The whole plan, as one document: the picture's shots and the sound's cues. */
function plan() {
  return {
    duration: DURATION,
    shots: SHOTS.map(({ id, start, end, arrive }) => ({ id, start, end, arrive: arrive || 'cut' })),
    cues: cueSheet(),
  };
}

if (OPTS.cues) {
  process.stdout.write(JSON.stringify(plan(), null, 2) + '\n');
  process.exit(0);
}

// ---------------------------------------------------------------- composition
const M = W * STAGE_MARGIN;
const palette = PALETTES.light;
const canvas = createCanvas(OPTS.width, OPTS.height);
const ctx = canvas.getContext('2d');
const canvasA = createCanvas(OPTS.width, OPTS.height);
const canvasB = createCanvas(OPTS.width, OPTS.height);
const ctxA = canvasA.getContext('2d');
const ctxB = canvasB.getContext('2d');

function shotAt(t) {
  return SHOTS.find((shot) => t >= shot.start && t < shot.end) || SHOTS[SHOTS.length - 1];
}

function shotIndex(shot) {
  return SHOTS.findIndex((s) => s.id === shot.id);
}

/**
 * One phrase of type, on the stage margin, arriving letter by letter.
 *
 * The phrase is fitted against the *largest* size it is ever drawn at, not its
 * resting size. The stage settles every phrase from ``SETTLE_MAX`` down to 1
 * across its beat, scaled around the left margin, so a phrase fitted to the full
 * column at rest is 35 percent too wide for its first second. "A WORKING PAGE"
 * ran off the right edge of the frame for exactly that reason, and it only
 * showed up in the contact sheet; the stills at the end of the beat were inside
 * the frame.
 */
function phrase(target, { value, local, size = 0.2, accent = false, out = 0, column = null }) {
  const base = Math.min(W, H) * size;
  const usable = column === null ? W * (1 - 2 * STAGE_MARGIN) : column;
  const natural = measure(target, value, { size: base, weight: 700, family: 'Space Grotesk' });
  const fitted = Math.min(base, (base * usable) / (SETTLE_MAX * Math.max(natural, 1)));
  drawPhrase(target, {
    lines: [value], w: W, h: H, p: span(local, 0, 0.45), palette,
    size: fitted, exit: out, accentLine: accent ? 0 : -1,
    t: local, hold: clamp(local / 2.4),
    // Starting the schedule before zero means a hard cut lands with the first
    // word already coming up. Started at zero, the frame after a cut was an empty
    // field for a fifth of a second, which reads as a dropped frame.
    reveal: span(local, -0.08, 1.5), left: M,
  });
}

/**
 * A bar that fills, over its own track.
 *
 * Always in motion, always for a reason the shot can name: a request being sent,
 * an agent working, a suite running. It is not enough on its own - the gate needs
 * changes big enough to see - but a shot without it has dead seconds in it.
 */
function bar(target, { x, y, w, progress, colour = palette.accent, thickness = 10 }) {
  if (progress <= 0) return;
  target.save();
  target.fillStyle = palette.rule;
  target.fillRect(x, y, w, thickness);
  target.restore();
  rule(target, x, y, w, { progress: clamp(progress), colour, thickness });
}

/** The film's small header: chapter on the margin, with a rule that fills. */
function header(target, local, shot, number) {
  const size = Math.round(H * 0.03);
  const y = H * 0.045;
  // The chapter label belongs to the shot that owns it, so it arrives after the
  // change has finished and not during it. Fading in from zero at the cut meant
  // two labels sat on the same words in the same place for a whole transition,
  // which is the exact thing the owner has rejected twice: text over text. The
  // outgoing label still recedes with its own picture, which reads as the old
  // shot leaving rather than as doubled type.
  const cut = shot.arrive === 'cut' ? 0
    : shot.arrive === 'focus' ? houseSeconds('focus') : houseSeconds('transition');
  const arrives = span(local, cut * 0.5, cut * 0.5 + 0.3);
  target.save();
  target.globalAlpha = target.globalAlpha * clamp(local * 2) * arrives;
  text(target, 'RENDER TEST', M, y, { size, weight: 700, family: 'Inter', color: palette.accent, tracking: 8 });
  const wChapter = measure(target, 'RENDER TEST', { size, weight: 700, family: 'Inter', tracking: 8 });
  text(target, number, M + wChapter + size * 1.2, y, { size, weight: 700, family: 'Inter', color: palette.ink, tracking: 8 });
  const width = wChapter + size * 1.2
    + measure(target, number, { size, weight: 700, family: 'Inter', tracking: 8 });
  rule(target, M, y + H * 0.028, width, {
    progress: ease.inOutCubic(clamp(local / (shot.end - shot.start))),
    colour: palette.accent, thickness: 4,
  });
  target.restore();
}

// ---------------------------------------------------------------- shot: prompt
function drawPrompt(target, local) {
  drawField(target, { w: W, h: H, t: local, palette });
  // The title is out of the way before the request starts to travel. It used to
  // still be full size and full strength when the request flew from the field up
  // to the top of the frame, and the request crossed it: two lines of type in the
  // same place, which is the one thing that has been rejected twice.
  phrase(target, {
    value: 'PRESS ENTER', local: local - 0.05, size: 0.115,
    out: span(local, 3.8, 4.5),
  });

  const box = { x: M, y: H * 0.6, w: W * 0.62, h: H * 0.13 };
  const arrive = span(local, 0.9, 1.35);
  const leave = span(local, EV.sendStart, EV.sendEnd);
  const size = Math.round(H * 0.052);
  const textX = box.x + 90;
  const baseline = box.y + box.h * 0.62;

  // The field. It lifts away once the request has been sent, so the last second
  // of the shot is the request leaving rather than a card sitting still.
  target.save();
  target.globalAlpha = target.globalAlpha * arrive * (1 - leave);
  roundRect(target, box.x, box.y + (1 - ease.outCubic(arrive)) * 40 - leave * H * 0.06, box.w, box.h, 40);
  target.fillStyle = UI.window;
  target.fill();
  target.strokeStyle = UI.line2;
  target.lineWidth = 4;
  target.stroke();
  target.restore();

  // The characters appear one at a time, at the times the keys are heard.
  const typed = [...EV.typeText];
  const count = KEYS.filter((at) => at <= local).length;
  let cursorX = textX;
  for (let i = 0; i < count; i += 1) {
    const glyph = typed[i];
    const age = clamp((local - KEYS[i]) / 0.12);
    target.save();
    target.globalAlpha = target.globalAlpha * (0.55 + 0.45 * age)
      * (1 - span(local, EV.sendStart, EV.sendStart + 0.35));
    text(target, glyph, cursorX, baseline - (1 - ease.outCubic(age)) * size * 0.12 - leave * H * 0.06, {
      size, weight: 600, family: 'Inter', color: UI.text,
    });
    target.restore();
    cursorX += measure(target, glyph, { size, weight: 600, family: 'Inter' });
  }

  const typing = local >= EV.typeStart && count < typed.length;
  const blink = typing ? 1 : (Math.floor((local - EV.typeStart) / 0.5) % 2 === 0 ? 1 : 0);
  if (local > 1.1 && blink && leave <= 0) {
    target.fillStyle = palette.accent;
    target.fillRect(cursorX + 6, baseline - size * 0.82, 7, size * 1.15);
  }

  // The key: pressed at EV.enterPress, answered at once.
  const key = { x: box.x, y: box.y + box.h + 90, w: 470, h: 150 };
  const press = clamp(1 - Math.abs(local - EV.enterPress) / 0.16);
  target.save();
  target.globalAlpha = target.globalAlpha * arrive * (1 - leave);
  target.translate(key.x + key.w / 2, key.y + key.h / 2);
  target.scale(1 - press * 0.04, 1 - press * 0.04);
  target.translate(-(key.x + key.w / 2), -(key.y + key.h / 2));
  roundRect(target, key.x, key.y, key.w, key.h, 44);
  target.fillStyle = press > 0 ? UI.ink : UI.window;
  target.fill();
  target.strokeStyle = press > 0 ? UI.ink : UI.line2;
  target.lineWidth = 4;
  target.stroke();
  text(target, 'ENTER', key.x + key.w / 2, key.y + key.h * 0.64, {
    size: Math.round(H * 0.036), weight: 700, family: 'Inter', align: 'center',
    color: press > 0 ? UI.white : UI.text, tracking: 10,
  });
  target.restore();

  const ringP = span(local, EV.enterPress, EV.enterPress + houseSeconds('ripple'));
  if (ringP > 0 && ringP < 1) {
    target.save();
    target.globalAlpha = target.globalAlpha * (1 - leave);
    clickRing(target, key.x + key.w / 2, key.y + key.h / 2, ringP,
      { colour: palette.accent, radius: 120 });
    target.restore();
  }

  // The request itself: it lifts out of the field and travels up to where the
  // next shot's card will be, shrinking as it goes. This is the one big move in
  // the last second of the shot, and it is the sentence: what you typed becomes
  // the job.
  const flight = ease.inOutCubic(span(local, EV.sendStart + 0.35, EV.sendEnd));
  if (flight > 0) {
    const from = { x: textX, y: baseline };
    const to = { x: M, y: H * 0.2 };
    const scale = lerp(1, 0.42, flight);
    target.save();
    target.globalAlpha = target.globalAlpha * (0.9 - flight * 0.15);
    target.translate(lerp(from.x, to.x, flight), lerp(from.y, to.y, flight));
    target.scale(scale, scale);
    text(target, EV.typeText, 0, 0, {
      size, weight: 600, family: 'Inter', color: UI.text,
    });
    target.restore();
  }

  // The pointer travels to the key and presses it. One move, one destination.
  const travel = span(local, EV.enterPress - 1.2, EV.enterPress - 0.15);
  const px = lerp(box.w * 0.2, key.x + key.w * 0.62, ease.inOutCubic(travel));
  const py = lerp(box.y + box.h * 1.9, key.y + key.h * 0.55, ease.inOutCubic(travel));
  target.save();
  target.globalAlpha = target.globalAlpha * (1 - leave);
  cursor(target, px, py, { alpha: clamp(travel * 1.4), press });
  target.restore();

  header(target, local, SHOTS[0], '01');
}

// ------------------------------------------------------------------ shot: work
/**
 * A row that wipes in, filled.
 *
 * Cards are where this film nearly failed the gate, and the reason was that
 * everything on them was text: a line of 40-pixel type on a 3840-wide frame is
 * three pixels tall by the time the checker has it at 320, and three pixels of
 * new text is not a change anyone can see. A filled band appearing is. So every
 * row arrives as a band that wipes open from its left edge, with its text on
 * top - which is also what a diff looks like when it is being written.
 */
function band(target, { x, y, w, h, progress, fill, text: label, colour, size, prefix = '' }) {
  if (progress <= 0) return;
  const open = ease.outCubic(clamp(progress));
  target.save();
  target.globalAlpha = target.globalAlpha * open;
  roundRect(target, x, y, Math.max(8, w * open), h, h * 0.34);
  target.fillStyle = fill;
  target.fill();
  target.restore();
  if (label) {
    target.save();
    target.globalAlpha = target.globalAlpha * open;
    if (prefix) {
      text(target, prefix, x + 26, y + h * 0.66, {
        size, weight: 700, family: 'Inter', color: colour,
      });
    }
    text(target, label, x + (prefix ? 62 : 26), y + h * 0.66, {
      size, weight: 500, family: 'Inter', color: UI.text,
    });
    target.restore();
  }
}

function drawWork(target, local) {
  drawField(target, { w: W, h: H, t: local, palette });
  const card = { x: W * 0.09, y: H * 0.13, w: W * 0.76, h: H * 0.64 };
  const arrive = span(local, 0, 0.32);
  target.save();
  target.globalAlpha = target.globalAlpha * arrive;
  panel(target, { ...card, r: 44, fill: UI.window, stroke: UI.line, shadow: 40 });
  text(target, 'the agent, working', card.x + 90, card.y + 116, {
    size: Math.round(H * 0.032), weight: 700, family: 'Inter', color: palette.ink,
  });
  text(target, EV.typeText, card.x + 90, card.y + 172, {
    size: Math.round(H * 0.023), weight: 500, family: 'Inter', color: UI.dim,
  });
  target.restore();

  // The diff, one band at a time. The band is the change the eye catches; the
  // text is what it says.
  const bandH = Math.round(H * 0.050);
  const gap = Math.round(H * 0.059);
  const top = card.y + 232;
  DIFF.forEach(([sign, line], i) => {
    const at = EV.streamStart - SHOTS[1].start + i * EV.streamStep;
    const p = span(local, at, at + 0.2);
    if (p <= 0) return;
    const plus = sign === '+';
    band(target, {
      x: card.x + 80, y: top + i * gap, w: card.w - 160, h: bandH, progress: p,
      fill: plus ? '#CFE9D9' : '#F0DADA', text: line,
      colour: plus ? '#186B3C' : '#9A4A4A', size: Math.round(H * 0.024), prefix: sign,
    });
  });

  // The run clock and the bar: the card says it is working continuously.
  text(target, Math.max(0, local).toFixed(1) + 's', card.x + card.w - 90, card.y + 116, {
    size: Math.round(H * 0.025), weight: 500, family: 'Inter', color: UI.faint, align: 'right',
  });
  // The commit button becomes the plate that says it landed: one object changing
  // state, not two objects on top of each other. It sits under the last row, not
  // on it - the bands run the full width of the card, and a black pill dropped on
  // top of one reads as a mistake however pale the band is.
  const button = { x: card.x + card.w - 640, y: top + DIFF.length * gap + 12, w: 560, h: 108 };
  const press = clamp(1 - Math.abs(local - (EV.commitPress - SHOTS[1].start)) / 0.16);
  const done = span(local, EV.commit - SHOTS[1].start, EV.commit - SHOTS[1].start + 0.3);
  if (done < 1) {
    target.save();
    target.globalAlpha = target.globalAlpha * (1 - done);
    target.translate(button.x + button.w / 2, button.y + button.h / 2);
    target.scale(1 - press * 0.04, 1 - press * 0.04);
    target.translate(-(button.x + button.w / 2), -(button.y + button.h / 2));
    roundRect(target, button.x, button.y, button.w, button.h, 54);
    target.fillStyle = UI.ink;
    target.fill();
    text(target, 'commit', button.x + button.w / 2, button.y + button.h * 0.64, {
      size: Math.round(H * 0.026), weight: 700, family: 'Inter', align: 'center',
      color: UI.white, tracking: 6,
    });
    target.restore();
  }
  if (done > 0) {
    const scale = lerp(0.94, 1, ease.outCubic(done));
    target.save();
    target.globalAlpha = target.globalAlpha * done;
    target.translate(button.x + button.w * 0.5, button.y + button.h * 0.5);
    target.scale(scale, scale);
    target.translate(-(button.x + button.w * 0.5), -(button.y + button.h * 0.5));
    roundRect(target, button.x, button.y, button.w, button.h, 54);
    target.fillStyle = '#E4F3EA';
    target.fill();
    target.fillStyle = UI.green;
    target.beginPath();
    target.arc(button.x + 58, button.y + 54, 11, 0, Math.PI * 2);
    target.fill();
    text(target, 'committed  3f2a91e', button.x + 96, button.y + 68, {
      size: Math.round(H * 0.024), weight: 600, family: 'Inter', color: '#186B3C',
    });
    target.restore();
  }

  const ringP = span(local, EV.commitPress - SHOTS[1].start, EV.commitPress - SHOTS[1].start + houseSeconds('ripple'));
  if (ringP > 0 && ringP < 1) {
    clickRing(target, button.x + button.w * 0.5, button.y + button.h * 0.5, ringP,
      { colour: palette.accent, radius: 110 });
  }

  const travel = span(local, EV.commitPress - SHOTS[1].start - 1.0, EV.commitPress - SHOTS[1].start - 0.15);
  cursor(target,
    lerp(card.x + card.w * 0.92, button.x + button.w * 0.5, ease.inOutCubic(travel)),
    lerp(button.y + 320, button.y + button.h * 0.55, ease.inOutCubic(travel)),
    { alpha: clamp(travel * 1.4), press });

  header(target, local, SHOTS[1], '02');
}

// ------------------------------------------------------------- shot: the type
function drawType(target, local, shot) {
  drawField(target, { w: W, h: H, t: local, palette });
  const out = span(local, shot.end - shot.start - 0.22, shot.end - shot.start);
  const [dx, dy] = shot.at || [0, 0];
  const anchor = M + W * dx;
  target.save();
  // The stage scales around its own anchor, so moving the anchor is a translate
  // of the whole stage, and the column left over has to be declared so the fit
  // still keeps the phrase inside the safe area.
  target.translate(W * dx, H * dy);
  phrase(target, {
    value: shot.phrase, local, size: shot.size,
    accent: !!shot.accent, out, column: W * (1 - STAGE_MARGIN) - anchor,
  });
  target.restore();
  header(target, local, shot, `0${shotIndex(shot) + 1}`);
}

// ------------------------------------------------------------------ shot: done
function drawDone(target, local) {
  drawField(target, { w: W, h: H, t: local, palette });
  const card = { x: M, y: H * 0.15, w: W * 0.76, h: H * 0.64 };
  const arrive = span(local, 0, 0.32);
  target.save();
  target.globalAlpha = target.globalAlpha * arrive;
  panel(target, { ...card, r: 44, fill: UI.window, stroke: UI.line, shadow: 40 });
  text(target, 'what landed', card.x + 90, card.y + 120, {
    size: Math.round(H * 0.032), weight: 700, family: 'Inter', color: palette.ink,
  });
  target.restore();

  // The suite reports a line at a time, each one as a band with its tick already
  // on it. Same device as the diff: a filled row is a change you can see.
  const bandH = Math.round(H * 0.058);
  const gap = Math.round(H * 0.072);
  const top = card.y + 220;
  TESTS.forEach((name, i) => {
    const at = EV.testStart - SHOTS[5].start + i * EV.testStep;
    const p = span(local, at, at + 0.22);
    if (p <= 0) return;
    const y = top + i * gap;
    band(target, {
      x: card.x + 80, y, w: card.w - 160, h: bandH, progress: p,
      fill: '#CFE9D9', text: name, colour: '#186B3C',
      size: Math.round(H * 0.025), prefix: '✓',
    });
    target.save();
    target.globalAlpha = target.globalAlpha * clamp((p - 0.5) * 2);
    text(target, `${320 + i * 47} ms`, card.x + card.w - 120, y + bandH * 0.66, {
      size: Math.round(H * 0.022), weight: 500, family: 'Inter', color: UI.dim, align: 'right',
    });
    target.restore();
  });

  bar(target, {
    x: card.x + 80, y: card.y + card.h - 58, w: card.w - 160,
    progress: span(local, 0.4, EV.receipt - SHOTS[5].start), thickness: 8,
  });

  const plateAt = EV.receipt - SHOTS[5].start;
  const plateP = span(local, plateAt, plateAt + 0.42);
  if (plateP > 0) {
    const receipt = 'committed 3f2a91e  ·  6 checks passed';
    const w2 = measure(target, receipt, { size: Math.round(H * 0.023), weight: 600, family: 'Inter' }) + 170;
    const y2 = top + TESTS.length * gap + 6;
    target.save();
    target.globalAlpha = target.globalAlpha * clamp(plateP * 2);
    roundRect(target, card.x + 80, y2 + (1 - ease.outCubic(plateP)) * 24, w2, 92, 46);
    target.fillStyle = '#DCEFE3';
    target.fill();
    text(target, receipt, card.x + 110, y2 + 58, {
      size: Math.round(H * 0.023), weight: 600, family: 'Inter', color: '#186B3C',
    });
    target.restore();
  }
  header(target, local, SHOTS[5], '06');
}

// ----------------------------------------------------------------- shot: final
function drawFinal(target, local, shot) {
  drawField(target, { w: W, h: H, t: local, palette });
  phrase(target, { value: shot.phrase, local, size: shot.size, column: W * (1 - STAGE_MARGIN) - (M + W * (shot.at ? shot.at[0] : 0)) });

  // The key arrives from the right edge and lands under the words, big enough to
  // be an object rather than an icon. Same device as the opening, sized up: the
  // film opened on a key and closes on one.
  const key = { w: W * 0.4, h: H * 0.135, y: H * 0.63 };
  const arrive = ease.outCubic(span(local, EV.keyArrive - shot.start, EV.keyArrive - shot.start + 0.9));
  const press = clamp(1 - Math.abs(local - (EV.finalPress - shot.start)) / 0.18);
  if (arrive > 0) {
    const x = lerp(W * 0.86, M, arrive);
    target.save();
    target.translate(x + key.w / 2, key.y + key.h / 2);
    target.scale(1 - press * 0.05, 1 - press * 0.05);
    target.translate(-(x + key.w / 2), -(key.y + key.h / 2));
    roundRect(target, x, key.y, key.w, key.h, 46);
    target.fillStyle = press > 0 ? UI.ink : UI.window;
    target.fill();
    target.strokeStyle = press > 0 ? UI.ink : UI.line2;
    target.lineWidth = 4;
    target.stroke();
    text(target, 'ENTER', x + key.w / 2, key.y + key.h * 0.64, {
      size: Math.round(H * 0.038), weight: 700, family: 'Inter', align: 'center',
      color: press > 0 ? UI.white : UI.text, tracking: 10,
    });
    target.restore();
    const ringP = span(local, EV.finalPress - shot.start, EV.finalPress - shot.start + houseSeconds('ripple'));
    if (ringP > 0 && ringP < 1) {
      clickRing(target, x + key.w / 2, key.y + key.h / 2, ringP,
        { colour: palette.accent, radius: 140 });
    }
  }
  header(target, local, shot, '07');
}

// ----------------------------------------------------------------- shot: close
function drawClose(target, local, shot) {
  drawField(target, { w: W, h: H, t: local, palette });
  const out = span(local, EV.tailFade - shot.start, DURATION - shot.start);
  const [dx, dy] = shot.at || [0, 0];
  const anchor = M + W * dx;
  target.save();
  target.translate(W * dx, H * dy);
  phrase(target, {
    value: shot.phrase, local, size: shot.size, accent: !!shot.accent, out,
    column: W * (1 - STAGE_MARGIN) - anchor,
  });
  target.restore();

  // The whole frame goes to the field at the end. A fade is a change in every
  // cell of the frame, and it is the one moment in the film where that is the
  // point: nothing is left, and the last thing said stays said.
  const fade = span(local, EV.frameOut - shot.start, DURATION - shot.start);
  if (fade > 0) {
    target.save();
    target.globalAlpha = fade;
    target.fillStyle = palette.field[0];
    target.fillRect(0, 0, W, H);
    target.restore();
  }
  header(target, local, shot, '08');
}

const DRAW = {
  prompt: drawPrompt,
  work: drawWork,
  type1: drawType,
  type2: drawType,
  type3: drawType,
  done: drawDone,
  final: drawFinal,
  close: drawClose,
};

/**
 * Every draw ends where it started.
 *
 * The prompt panel opened a ``save()`` and never closed it, and its alpha was
 * multiplied by an arrival that is zero for the first second. ``restore`` never
 * ran, so ``globalAlpha`` stayed zero: the frame drew the panel and then nothing
 * else, and because the leak survives the render, every later frame in that
 * process came out completely blank. Rendering one still at a time hid it - the
 * first render always looks fine - and only the contact sheet, where a dozen
 * stills share a process, showed the black frames.
 */
function guard(target, where) {
  if (Math.abs(target.globalAlpha - 1) > 1e-6) {
    throw new Error(`globalAlpha leaked to ${target.globalAlpha} after ${where}`);
  }
}

function paint(target, shot, at) {
  target.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  target.clearRect(0, 0, W, H);
  const local = at - shot.start;
  DRAW[shot.id](target, local, shot);
  guard(target, `paint ${shot.id}`);
}

function render(t) {
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const shot = shotAt(t);

  // A shot change is composited from two real frames, the same way the long film
  // does it: the outgoing shot is painted at its own last frame, the incoming one
  // at ``t``, and the mask runs between them.
  const cutSeconds = shot.arrive === 'focus' ? houseSeconds('focus') : houseSeconds('transition');
  const tp = shot.arrive ? span(t, shot.start, shot.start + cutSeconds) : 1;
  if (shot.arrive && shot.arrive !== 'cut' && tp < 1) {
    const previous = SHOTS[Math.max(0, shotIndex(shot) - 1)];
    paint(ctxA, previous, Math.min(previous.end - 0.03, shot.start - 0.03));
    paint(ctxB, shot, t);
    reveal(ctx, { kind: shot.arrive, p: tp, a: canvasA, b: canvasB, w: OPTS.width, h: OPTS.height, accent: palette.accent });
    return;
  }
  DRAW[shot.id](ctx, t - shot.start, shot);

  // The film opens from the field, so the first frame is not a hard edge.
  const fadeIn = 1 - span(t, 0, 0.3);
  if (fadeIn > 0) {
    ctx.save();
    ctx.globalAlpha = fadeIn;
    ctx.fillStyle = palette.field[0];
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }
  guard(ctx, `render @ ${t.toFixed(2)}s`);
}

// ---------------------------------------------------------------------- writer
const TOTAL_FRAMES = Math.round(DURATION * FPS);

function main() {
  const outDir = path.resolve(OPTS.out);
  fs.mkdirSync(outDir, { recursive: true });
  if (!OPTS.quiet) console.log(`plan -> ${path.join(outDir, 'plan.json')}`);
  fs.writeFileSync(path.join(outDir, 'plan.json'), JSON.stringify(plan(), null, 2));

  if (OPTS.still) {
    for (const seconds of OPTS.still) {
      render(seconds);
      const file = path.join(outDir, `still-${seconds.toFixed(2)}.jpg`);
      fs.writeFileSync(file, canvas.toBuffer('image/jpeg', OPTS.quality));
      if (!OPTS.quiet) console.log(`still ${seconds.toFixed(2)}s -> ${file}`);
    }
    return;
  }

  const from = Math.max(0, Math.round(OPTS.from));
  const to = Math.min(TOTAL_FRAMES, OPTS.to === null ? TOTAL_FRAMES : Math.round(OPTS.to));
  const started = Date.now();
  for (let frame = from; frame < to; frame += 1) {
    render(frame / FPS);
    fs.writeFileSync(
      path.join(outDir, `frame-${String(frame).padStart(6, '0')}.jpg`),
      canvas.toBuffer('image/jpeg', OPTS.quality),
    );
    if (!OPTS.quiet && (frame - from) % 90 === 0) {
      const rate = (frame - from + 1) / ((Date.now() - started) / 1000);
      console.log(`frame ${frame}/${to} (${rate.toFixed(1)} fps)`);
    }
  }
  if (!OPTS.quiet) console.log(`done: ${to - from} frames -> ${outDir}`);
}

main();
