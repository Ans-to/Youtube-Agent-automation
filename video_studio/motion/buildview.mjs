/**
 * The product card: the app, drawn as a shot.
 *
 * This replaces the sidebar window. The reason is a reference film the owner
 * supplied (36 s, "UI Demo Animation"). Measured against it, our panel was
 * wrong in a way that no amount of tidying could fix:
 *
 *   reference: one card, 82 % of frame width, rows at 58 px on a 1080p
 *              delivery, a title at 66 px, three rows visible, one of them
 *              outlined green where the pointer just clicked. Nothing else on
 *              screen. Soft background, one big drop shadow.
 *   ours:      a browser mock-up 540 px wide in a 1920 px frame, nine pieces of
 *              text between 14 and 29 px. Read as a thumbnail of an app.
 *
 * So the card is no longer furniture bolted to the right edge. It appears on
 * the lines that are about the product, takes the frame, and leaves. This also
 * removes the collision problem the sidebar created: scenes could be designed
 * full width again, because when the card is up it covers them and when it is
 * not it is absent - it never shares the frame with a scene's own type.
 *
 * Two rules come from the same reference and are enforced below:
 *
 *   * nothing a viewer must read is under 80 design units (40 px at 1080p),
 *     which is the legibility floor for video, and the reference's own row size
 *     is 116;
 *   * every state change is caused by something visible. The query types
 *     because the pointer pressed the field; the row outlines because the
 *     pointer pressed the row. Nothing here runs on a clock.
 *
 * Design units: the canvas is 3840x2160 and the caller has already scaled it.
 */
import { UI, clamp, span, ease, text, measure, roundRect } from './ui.mjs';

/** The card, centred. 73 % of the width, which at a 1080p delivery is 1400 px. */
export const CARD = { x: 520, y: 300, w: 2800, h: 1520 };

const PAD = 130;          // inner margin, generous on purpose
const ROW_H = 190;        // one row; the title inside it is 116
const ROW_GAP = 24;
const ROWS = 3;           // three is what fits; the reference shows three

/** Type scale. Everything readable is >= 80 design units = 40 px at 1080p. */
const T = { title: 132, sub: 84, row: 116, small: 80, mono: 84, glyph: 96 };

const BOOKS = ['Dune', 'Piranesi', 'The Overstory'];

/**
 * What the card shows, per narration line.
 *
 * `card: true` means this line is about the product and the card takes the
 * frame. A stage with no `card` is a line about an idea; the card is absent and
 * the scene owns the picture. Stages carry the state the line has *reached*,
 * never a state it is about to reach.
 */
const STAGES = {
  // 0-1 "build a real app" / "you describe it" - the page assembles.
  title: [
    { app: true, bare: true },
    // The card beat's own arrivals, timed from the line, not from a clock: this
    // beat lasts a whole sentence, and one arrival at the top of it leaves four
    // seconds of still frame.
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 1), typingRow: 0,
      // Arrivals every 1.1 s across a 5.6 s line, which is the reference's own
      // cadence. The first version spaced them 1.3 s apart from the wrong start
      // and two seconds in the middle of the line measured empty.
      late: [
        { at: 1.6, row: 'Piranesi', slot: 1, write: true },
        { at: 2.6, field: true },
        { at: 3.5, address: 'github.com/you/book-list' },
        { at: 4.5, focusRow: 1 },
        { at: 5.2, row: 'The Overstory', slot: 2, write: true },
      ] },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 2), search: true },
    // The press lands on the field, the letters type, and the list filters
    // from three rows to the one the viewer can see is the right answer.
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3),
      track: ['repository', 'pull request', 'working site'] },
  ],
  // "say what you want, look at the result" - the search is the result.
  statement: [
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true },
    // The pointer presses the result, so the row answers: ring, tick, count.
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: ['Dune'], search: true,
      query: 'dune', focus: 0, chip: '1 result' },
    { app: true, title: 'BOOKS I HAVE READ', rows: ['Dune'], search: true, query: 'dune', chip: '1 result' },
    { app: true, title: 'BOOKS I HAVE READ', rows: ['Dune'], search: true, query: 'dune', chip: '1 result' },
  ],
  pipeline: [
    { repo: true, files: [], branch: 'main', message: 'empty repository' },
    { card: true, repo: true, files: [['index.html', 'new']], branch: 'main' },
    { repo: true, files: [['index.html', 'new'], ['books.json', 'new']], branch: 'main' },
    { repo: true, files: [['index.html', 'new'], ['books.json', 'new'], ['README.md', 'new']], branch: 'main' },
  ],
  github: [
    { card: true, repo: true, files: [], branch: 'main', message: 'no commits yet', command: 'gh repo create book-list' },
    { repo: true, files: [['README.md', 'new']], branch: 'main', command: 'git add README.md' },
    { repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', command: 'git commit -m "first"' },
  ],
  connect: [
    { card: true, repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', chip: 'connected' },
    { repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', chip: 'one repo' },
  ],
  prompt: [
    { card: true, app: true, prompt: 'build a book list' },
    { app: true, prompt: 'build a book list', title: 'BOOKS I HAVE READ' },
    { app: true, prompt: 'build a book list', title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 2) },
  ],
  agent: [
    { card: true, repo: true, files: [['index.html', 'new'], ['books.json', 'new']], branch: 'agent/book-list' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'agent/book-list' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new'], ['README.md', 'edit']], branch: 'agent/book-list', command: 'git push' },
  ],
  diff: [
    { card: true, diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add']] },
    { diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add'], ['+ on("input", filter)', 'add']] },
    { diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add'], ['+ on("input", filter)', 'add'], ['- // old list', 'del']] },
  ],
  checks: [
    { card: true, checks: true, branch: 'agent/book-list', rows: [['tests', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], command: 'npm run build' },
  ],
  merge: [
    { card: true, checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], chip: 'ready' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'merged', command: 'gh pr merge' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'merged' },
  ],
  feature: [
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true,
      late: [{ at: 2.4, row: 'Klara and the Sun', slot: 3 }] },
    { app: true, title: 'BOOKS I HAVE READ', rows: ['Piranesi'], search: true, query: 'pi', focus: 0, chip: '1 result' },
    { app: true, title: 'BOOKS I HAVE READ', rows: ['Piranesi'], search: true, query: 'pir', chip: '1 result' },
  ],
  revert: [
    { card: true, repo: true, files: [['index.html', 'edit']], branch: 'main', chip: 'reverted', command: 'gh pr revert 12' },
    { repo: true, files: [['index.html', 'new']], branch: 'main', chip: 'clean' },
  ],
  patterns: [
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true, chip: 'outcome named' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true, chip: 'constraint stated' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true, chip: 'error pasted' },
  ],
  safety: [
    { card: true, repo: true, files: [['.env', 'ignored'], ['index.html', 'edit']], branch: 'main', chip: 'key in settings' },
    { repo: true, files: [['.env', 'ignored'], ['index.html', 'edit']], branch: 'main', chip: 'not in the repo' },
  ],
  habits: [
    { card: true, repo: true, files: [['index.html', 'edit']], branch: 'agent/search', chip: 'branch per change' },
    { checks: true, branch: 'agent/search', rows: [['tests', 'pass'], ['lint', 'pass']], chip: 'merge only green' },
    { repo: true, files: [['README.md', 'edit']], branch: 'main', chip: 'readme as you go' },
  ],
  recap: [
    { card: true, repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'repo' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true },
    { checks: true, branch: 'main', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], chip: 'checks' },
  ],
  outro: [
    { card: true, app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3), search: true, chip: 'live' },
    { app: true, title: 'BOOKS I HAVE READ', rows: ['Dune'], search: true, query: 'dune', chip: 'live' },
  ],
};

export function stageFor(kind, lineIndex) {
  const stages = STAGES[kind] ?? STAGES.title;
  return stages[clamp(lineIndex, 0, stages.length - 1)];
}

/** The stage before this one in the same scene, for continuity. */
export function prevStageFor(kind, lineIndex) {
  const stages = STAGES[kind] ?? STAGES.title;
  const i = clamp(lineIndex, 0, stages.length - 1);
  return i > 0 ? stages[i - 1] : null;
}

/** True on the lines where the card owns the frame. */
export function cardBeat(kind, lineIndex) {
  return !!(stageFor(kind, lineIndex) || {}).card;
}

// ------------------------------------------------------------------ geometry
const body = () => ({ x: CARD.x + PAD, y: CARD.y + PAD, w: CARD.w - PAD * 2, h: CARD.h - PAD * 2 });

/** The first row sits under the heading block. */
const FIRST_ROW = 300;
const SEARCH_H = 168;

/**
 * Where the stack sits for a given stage.
 *
 * Content flows: heading, then rows, then the field. An early stage therefore
 * has a short stack with the page still filling in beneath it, which is what
 * building a page looks like - and the last stage fills the card exactly. The
 * earlier version pinned the field to the foot of the card, so a one-row state
 * was a row at the top and a field at the bottom with nothing between them.
 */
function layout(stage) {
  const b = body();
  const rows = Math.min(ROWS, (stage.rows || stage.files || stage.lines || []).length);
  const stack = [];
  for (let i = 0; i < rows; i += 1) {
    stack.push({ x: b.x, y: b.y + FIRST_ROW + i * (ROW_H + ROW_GAP), w: b.w, h: ROW_H });
  }
  // The field does not ride up and down with the row count. When a query
  // filters three rows down to one, a field that followed the stack would jump
  // a third of the card in the middle of the animation; pinned, the rows are
  // the only thing that moves, which is also the only thing the viewer is
  // watching.
  const below = b.y + FIRST_ROW + ROWS * (ROW_H + ROW_GAP) + 24;
  const search = stage.search ? { x: b.x, y: below, w: b.w, h: SEARCH_H } : null;
  return { body: b, rows: stack, search };
}

/** Where the search field sits, so the pointer knows what to press. */
export function searchRect(kind, lineIndex) {
  return layout(stageFor(kind, lineIndex)).search;
}

/** Where row `i` sits, so the pointer can press a row. */
export function rowRect(kind, lineIndex, i) {
  return layout(stageFor(kind, lineIndex)).rows[i] || null;
}

// -------------------------------------------------------------------- pieces
/** A row: the unit the reference builds the whole card out of. */
function drawRow(ctx, { x, y, w, h, label, p, focus, glyph, tone = 'light', sub }) {
  if (p <= 0) return;
  const e = ease.outCubic(clamp(p));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2.4);
  ctx.translate(0, (1 - e) * 46);
  roundRect(ctx, x, y, w, h, 28);
  ctx.fillStyle = focus ? UI.white : '#F3F3F6';
  ctx.fill();
  ctx.lineWidth = focus ? 7 : 3;
  ctx.strokeStyle = focus ? UI.green : '#DDDDE3';
  ctx.stroke();

  text(ctx, label, x + 58, y + h * 0.5 + 40, {
    size: T.row, weight: 600, family: 'Inter', color: tone === 'dim' ? UI.faint : UI.ink,
    maxWidth: w - 300,
  });
  if (sub) {
    text(ctx, sub, x + w - 58, y + h * 0.5 + 32, {
      size: T.small, weight: 600, family: 'Inter', color: UI.dim, align: 'right',
    });
  }
  if (glyph) {
    const g = { x: x + w - 58 - 120, y: y + (h - 120) / 2, s: 120 };
    roundRect(ctx, g.x, g.y, g.s, g.s, 30);
    ctx.fillStyle = '#CFDDF8';
    ctx.fill();
    ctx.strokeStyle = '#5B8DEF';
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.strokeStyle = '#22437F';
    ctx.lineWidth = 7;
    ctx.beginPath();
    if (glyph === 'tick') {
      ctx.moveTo(g.x + 36, g.y + 62);
      ctx.lineTo(g.x + 54, g.y + 82);
      ctx.lineTo(g.x + 86, g.y + 40);
    } else if (glyph === 'search') {
      ctx.arc(g.x + 54, g.y + 52, 24, 0, Math.PI * 2);
      ctx.moveTo(g.x + 72, g.y + 72);
      ctx.lineTo(g.x + 90, g.y + 90);
    } else {
      ctx.moveTo(g.x + 40, g.y + 46);
      ctx.lineTo(g.x + 84, g.y + 46);
    }
    ctx.stroke();
  }
  ctx.restore();
}

/** The browser bar, reduced to what is legible: three dots and the address. */
function drawBar(ctx, { address, alpha }) {
  if (alpha <= 0) return;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  ['#FF5F57', '#FEBC2E', '#28C840'].forEach((colour, i) => {
    ctx.beginPath();
    ctx.arc(CARD.x + PAD + 18 + i * 44, CARD.y + 78, 14, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
  });
  text(ctx, address, CARD.x + CARD.w - PAD, CARD.y + 100, {
    size: T.small, weight: 600, family: 'Inter', color: UI.faint, align: 'right',
  });
  ctx.restore();
}

/** The heading block, shared by every kind of card. */
function drawHead(ctx, { title, sub, chip, alpha }) {
  text(ctx, title, CARD.x + PAD, CARD.y + PAD + 148, {
    size: T.title, weight: 700, family: 'Space Grotesk', color: UI.ink,
    maxWidth: CARD.w - PAD * 2 - 460, alpha,
  });
  if (sub) {
    text(ctx, sub, CARD.x + PAD, CARD.y + PAD + 244, {
      size: T.sub, weight: 500, family: 'Inter', color: UI.dim, alpha,
    });
  }
  if (chip) {
    const w = measure(ctx, chip, { size: T.small, weight: 700, family: 'Inter' }) + 76;
    roundRect(ctx, CARD.x + CARD.w - PAD - w, CARD.y + PAD + 60, w, 104, 52);
    ctx.fillStyle = '#EAEAF0';
    ctx.fill();
    text(ctx, chip, CARD.x + CARD.w - PAD - w / 2, CARD.y + PAD + 130, {
      size: T.small, weight: 700, family: 'Inter', color: UI.ink, align: 'center', alpha,
    });
  }
}

/**
 * The track: the few things a sentence names, ticking over as it names them.
 *
 * This exists because of a dead second. On a card beat the rail stands down, so
 * the card is the only thing on screen; a card that has finished assembling is
 * a still frame, and a still frame is a failed product. The line here is "you
 * will have a repository, a pull request, and a working site" - three nouns, so
 * the card carries three items and lights one per beat. Same metronome as the
 * rail, tied to what is being said rather than to a counter.
 */
function drawTrack(ctx, { items, t }) {
  const b = body();
  const top = CARD.y + CARD.h - PAD - 104;
  const gap = 28;
  const w = (b.w - gap * (items.length - 1)) / items.length;
  const beat = Math.floor(t / 0.75);
  const phase = (t % 0.75) / 0.75;
  const current = beat % (items.length + 1);

  items.forEach((label, i) => {
    const x = b.x + i * (w + gap);
    const on = i <= current;
    roundRect(ctx, x, top, w, 104, 20);
    ctx.fillStyle = on ? '#EDF3FE' : '#F4F4F7';
    ctx.fill();
    ctx.strokeStyle = on ? '#5B8DEF' : '#E2E2E8';
    ctx.lineWidth = on ? 4 : 3;
    ctx.stroke();

    // The current item carries a block sliding through it and a bar filling
    // under it, so each beat has a beginning, a middle and an end.
    if (i === current) {
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * (1 - phase) * 0.95;
      ctx.fillStyle = '#5B8DEF';
      ctx.fillRect(x + 20 + ease.outCubic(phase) * (w - 76), top + 44, 32, 16);
      ctx.restore();
      ctx.fillStyle = '#5B8DEF';
      ctx.fillRect(x + 20, top + 88, (w - 40) * ease.outCubic(phase), 6);
    }
    text(ctx, label, x + 26, top + 62, {
      size: T.small, weight: 600, family: 'Inter',
      color: on ? UI.ink : UI.faint, maxWidth: w - 52,
    });
  });
}

// --------------------------------------------------------------------- cards
function drawApp(ctx, { stage, lineLocal, prev, t }) {
  drawBar(ctx, { address: 'localhost:3000', alpha: 1 });
  drawHead(ctx, {
    title: stage.title || 'BOOKS I HAVE READ',
    sub: stage.title ? 'one page, no framework' : 'nothing on the page yet',
    chip: stage.chip,
    alpha: 1,
  });

  const rows = stage.rows || [];
  const had = (prev && prev.rows ? prev.rows.length : 0);
  const L = layout(stage);
  // A query is not decoration: it filters. Rows that the new query excludes
  // leave as the letters type, which is the visible result of the press.
  const typing = stage.query && (!prev || prev.query !== stage.query)
    ? span(lineLocal, 0.7, 0.7 + stage.query.length * 0.06)
    : 1;
  if (prev && prev.rows && prev.rows.length > rows.length) {
    prev.rows.slice(rows.length, ROWS).forEach((name, i) => {
      const p = 1 - span(lineLocal, 0.62, 1.0);
      if (p <= 0) return;
      const slot = rows.length + i;
      drawRow(ctx, {
        x: L.body.x, y: L.body.y + FIRST_ROW + slot * (ROW_H + ROW_GAP), w: L.body.w, h: ROW_H,
        label: name, p, focus: false,
      });
    });
  }
  rows.slice(0, ROWS).forEach((name, i) => {
    const r = L.rows[i];
    // A row that was already on screen stays put. Only a genuinely new row
    // arrives, 0.15 s after the one before it. Re-entering every row on every
    // line was the panel flickering for no reason the narration gave.
    const p = i < had ? 1 : span(lineLocal, 0.15 + (i - had) * 0.15, 0.55 + (i - had) * 0.15);
    // A row can be written in rather than dropped in. That is what the line at
    // 0:12 says is happening - "an agent writes it, while you watch" - and a row
    // that assembles letter by letter is the only honest thing to show for it.
    const writing = stage.typingRow === i && !(prev && (prev.rows || []).length > i);
    const label = writing
      ? name.slice(0, Math.max(0, Math.ceil(
        span(lineLocal, 0.12, 0.12 + name.length * 0.09) * name.length)))
      : name;
    // A row with no characters yet is not drawn at all: an empty plate reads as
    // a broken component, not as a row being written.
    if (writing && !label) return;
    drawRow(ctx, {
      ...r, label: label || '\u200b', p,
      // The ring is the *result* of the pointer's press, so it lands after it.
      focus: stage.focus === i && lineLocal >= 0.62,
      glyph: stage.focus === i && lineLocal >= 0.62 ? 'tick' : null,
    });
  });

  if (stage.search && L.search) {
    const s = L.search;
    const p = prev && prev.search ? 1 : span(lineLocal, 0.2, 0.6);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2);
    roundRect(ctx, s.x, s.y, s.w, s.h, 28);
    ctx.fillStyle = UI.white;
    ctx.fill();
    ctx.strokeStyle = stage.query ? UI.green : '#DDDDE3';
    ctx.lineWidth = stage.query ? 7 : 3;
    ctx.stroke();
    // The magnifier, drawn rather than typed.
    ctx.strokeStyle = '#8A8A95';
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.arc(s.x + 74, s.y + s.h / 2 - 6, 26, 0, Math.PI * 2);
    ctx.moveTo(s.x + 94, s.y + s.h / 2 + 16);
    ctx.lineTo(s.x + 112, s.y + s.h / 2 + 34);
    ctx.stroke();
    // Typing starts on the press, not before it: the pointer causes it.
    const same = prev && prev.query === stage.query;
    const typed = !stage.query ? ''
      : same ? stage.query
      : stage.query.slice(0, Math.floor(span(lineLocal, 0.7, 0.7 + stage.query.length * 0.06) * (stage.query.length + 1)));
    text(ctx, typed || 'Search your books', s.x + 150, s.y + s.h * 0.5 + 38, {
      size: T.row, weight: 600, family: 'Inter',
      color: typed ? UI.ink : '#A6A6B0',
      maxWidth: s.w - 300,
    });
    if (typed) {
      const caretX = s.x + 150 + measure(ctx, typed, { size: T.row, weight: 600, family: 'Inter' }) + 8;
      ctx.fillStyle = UI.ink;
      ctx.globalAlpha = ctx.globalAlpha * (lineLocal % 1 < 0.55 ? 1 : 0);
      ctx.fillRect(caretX, s.y + 40, 8, s.h - 80);
    }
    ctx.restore();
  }

  if (stage.track) drawTrack(ctx, { items: stage.track, t });

  // A card beat lasts a whole narration line, which is five or six seconds, and
  // one arrival at the start of it leaves four seconds of still frame. The
  // reference never does that: its cards keep adding a row, a field, a result
  // while they are on screen. ``late`` is that schedule - the things that land
  // after the first one, at times measured from the line, not from a clock.
  if (stage.card && stage.late) {
    stage.late.forEach((step) => {
      const p2 = span(lineLocal, step.at, step.at + 0.4);
      if (p2 <= 0) return;
      if (step.field && !stage.search) {
        const s2 = { x: L.body.x, y: L.body.y + FIRST_ROW + ROWS * (ROW_H + ROW_GAP) + 24, w: L.body.w, h: SEARCH_H };
        ctx.save();
        ctx.globalAlpha = ctx.globalAlpha * clamp(p2 * 2);
        roundRect(ctx, s2.x, s2.y + (1 - ease.outCubic(p2)) * 40, s2.w, s2.h, 28);
        ctx.fillStyle = UI.white; ctx.fill();
        ctx.strokeStyle = '#DDDDE3'; ctx.lineWidth = 3; ctx.stroke();
        text(ctx, 'Search your books', s2.x + 150, s2.y + s2.h * 0.5 + 38, {
          size: T.row, weight: 600, family: 'Inter', color: '#A6A6B0', maxWidth: s2.w - 300,
        });
        ctx.restore();
      }
      if (step.row) {
        const slot = Math.min(ROWS - 1, (stage.rows || []).length + (step.slot || 0));
        const r2 = L.rows[slot] || { x: L.body.x, y: L.body.y + FIRST_ROW + slot * (ROW_H + ROW_GAP), w: L.body.w, h: ROW_H };
        const written = step.write
          ? step.row.slice(0, Math.max(0, Math.ceil(
            span(lineLocal, step.at, step.at + step.row.length * 0.075) * step.row.length)))
          : step.row;
        if (written) drawRow(ctx, { ...r2, label: written, p: step.write ? 1 : p2 });
      }
      if (step.focusRow !== undefined) {
        // The pointer's press lands, and the row answers: ring, tick, and the
        // row's own plate goes white. That is the reference's green outline,
        // caused by the press rather than appearing on a timer.
        const slot = Math.min(ROWS - 1, (stage.rows || []).length + (step.focusRow - 1));
        const r2 = L.rows[slot] || { x: L.body.x, y: L.body.y + FIRST_ROW + slot * (ROW_H + ROW_GAP), w: L.body.w, h: ROW_H };
        drawRow(ctx, { ...r2, label: step.row || (stage.late.find((x) => x.row) || {}).row || 'Piranesi',
          p: 1, focus: true, glyph: 'tick' });
      }
      if (step.address) {
        // "on GitHub": the address bar changes to the repository, wiped left to
        // right, so the sentence's own noun is the thing that arrives.
        // A pill grows leftwards behind the new address and the address fades in
        // on it. A five-character text swap alone is not a visible event at this
        // size; a plate arriving across the width of the bar is.
        const wipe = ease.outCubic(p2);
        const w2 = measure(ctx, step.address, { size: T.small, weight: 600, family: 'Inter' }) + 64;
        const right = CARD.x + CARD.w - PAD;
        ctx.save();
        roundRect(ctx, right - w2 * wipe, CARD.y + 44, w2 * wipe, 72, 36);
        ctx.fillStyle = '#E6F3EA';
        ctx.fill();
        ctx.globalAlpha = ctx.globalAlpha * clamp(p2 * 2);
        text(ctx, step.address, right, CARD.y + 100, {
          size: T.small, weight: 600, family: 'Inter', color: '#186B3C', align: 'right',
        });
        ctx.restore();
      }
    });
  }
  if (stage.prompt) {
    const r = L.rows[0] || { x: L.body.x, y: L.body.y + FIRST_ROW, w: L.body.w, h: ROW_H };
    drawRow(ctx, { ...r, label: '\u201c' + stage.prompt + '\u201d', p: 1, focus: true, glyph: 'arrow' });
  }
  if (stage.bare) {
    const b = L.body;
    ctx.save();
    ctx.strokeStyle = '#DDDDE3';
    ctx.lineWidth = 4;
    ctx.setLineDash([18, 16]);
    roundRect(ctx, b.x, b.y + FIRST_ROW, b.w, ROW_H * 2 + ROW_GAP, 28);
    ctx.stroke();
    ctx.restore();
  }
}

function drawRepo(ctx, { stage, lineLocal, prev }) {
  drawBar(ctx, { address: 'github.com/you/book-list', alpha: 1 });
  drawHead(ctx, {
    title: 'book-list',
    sub: stage.branch + '  ·  ' + ((stage.files || []).length) + ' files',
    chip: stage.chip,
    alpha: 1,
  });
  const files = stage.files || [];
  const had = (prev && prev.files ? prev.files.length : 0);
  const L = layout(stage);
  files.slice(0, ROWS).forEach(([name, state], i) => {
    const r = L.rows[i];
    drawRow(ctx, {
      ...r, label: name,
      p: i < had ? 1 : span(lineLocal, 0.15 + (i - had) * 0.15, 0.55 + (i - had) * 0.15),
      sub: state === 'new' ? 'added' : state === 'ignored' ? 'ignored' : 'changed',
      glyph: state === 'new' ? 'tick' : null,
    });
  });
  if (!files.length) {
    const b = body();
    text(ctx, stage.message || 'no commits yet', b.x, b.y + 300 + ROW_H * 0.62, {
      size: T.row, weight: 500, family: 'Inter', color: UI.faint,
    });
  }
}

function drawDiff(ctx, { stage, lineLocal, prev }) {
  drawBar(ctx, { address: 'github.com/you/book-list/pull/12/files', alpha: 1 });
  drawHead(ctx, { title: 'The diff', sub: stage.branch, alpha: 1 });
  const b = body();
  (stage.lines || []).slice(0, ROWS).forEach(([value, kind], i) => {
    const had = (prev && prev.lines ? prev.lines.length : 0);
    const p = i < had ? 1 : span(lineLocal, 0.15 + (i - had) * 0.2, 0.55 + (i - had) * 0.2);
    if (p <= 0) return;
    const y = b.y + 300 + i * (ROW_H + ROW_GAP);
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2);
    roundRect(ctx, b.x, y, b.w, ROW_H, 22);
    ctx.fillStyle = kind === 'add' ? '#EDF8F1' : '#FCEFF0';
    ctx.fill();
    ctx.fillStyle = kind === 'add' ? UI.green : UI.red;
    ctx.fillRect(b.x, y, 14, ROW_H);
    text(ctx, value, b.x + 52, y + ROW_H * 0.5 + 32, {
      size: T.mono, weight: 600, family: 'monospace',
      color: kind === 'add' ? '#186B3C' : '#8E1418', maxWidth: b.w - 120,
    });
    ctx.restore();
  });
}

function drawChecks(ctx, { stage, lineLocal, prev }) {
  drawBar(ctx, { address: 'github.com/you/book-list/actions', alpha: 1 });
  const passed = stage.rows.filter(([, s]) => s === 'pass').length;
  drawHead(ctx, {
    title: passed === stage.rows.length ? 'All green' : 'Running checks',
    sub: passed + ' of ' + stage.rows.length + ' passed  ·  ' + stage.branch,
    chip: stage.chip,
    alpha: 1,
  });
  const L = layout(stage);
  stage.rows.slice(0, ROWS).forEach(([name, state], i) => {
    const r = L.rows[i];
    const had = (prev && prev.rows ? prev.rows.length : 0);
    const appear = i < had ? 1 : span(lineLocal, 0.15 + (i - had) * 0.15, 0.55 + (i - had) * 0.15);
    drawRow(ctx, {
      ...r, label: name, p: appear,
      tone: state === 'pass' ? 'light' : 'dim',
      sub: state === 'pass' ? 'passed' : 'running',
      glyph: state === 'pass' ? 'tick' : null,
    });
  });
}

// --------------------------------------------------------------------- entry
/**
 * Draws the card. Returns the geometry the pointer needs, or null when this
 * line is not a card beat and the scene keeps the frame.
 */
export function buildView(ctx, {
  kind, lineIndex, lineLocal, t, h = 2160, palette = 'dark', forceCard = null,
}) {
  // `forceCard` exists because two tables now decide what is on screen: the
  // stage table below, and the phrase table in the film. When the film is
  // drawing the typographic stage it owns that decision, and the card must
  // appear only on the lines it says are product lines - otherwise a card can
  // cover a phrase the narration is speaking, which is the exact fault the
  // owner rejected in the sidebar.
  const stage = { ...stageFor(kind, lineIndex) };
  if (forceCard === false) return null;
  if (forceCard === true) stage.card = true;
  if (!stage.card) return null;

  const box = { ...CARD };
  const b = body();

  // The frame goes to a studio backdrop: solid, not a dimmed scene. The first
  // version left 14 % of the scene showing and the scene's own words read as
  // rubbish around the card's edges - a fragment saying "A REPO" beside an app
  // is the same fault as a panel unrelated to the sentence. Nothing from the
  // scene survives.
  ctx.save();
  if (palette === 'light') {
    // The reference's own ground: the same soft field the type beats sit on, so
    // a card insert is a shot in the same film rather than a dark rectangle
    // dropped into it.
    const grad = ctx.createLinearGradient(0, 0, 1400, h);
    grad.addColorStop(0, '#F7F9FA');
    grad.addColorStop(0.55, '#E7EEF2');
    grad.addColorStop(1, '#DCE6EC');
    ctx.fillStyle = grad;
    ctx.fillRect(-20, -20, 3880, h + 40);
  } else {
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, '#191A1E');
    grad.addColorStop(0.55, '#131418');
    grad.addColorStop(1, '#0C0C0F');
    ctx.fillStyle = grad;
    ctx.fillRect(-20, -20, 3880, h + 40);
    // A dot field, four units across, so the backdrop is a surface rather than a
    // void. Static: nothing here moves on its own.
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    for (let y = 60; y < h; y += 96) {
      for (let x = 60; x < 3840; x += 96) ctx.fillRect(x, y, 4, 4);
    }
  }
  ctx.restore();

  // The card arrives with a short push-in and then drifts almost imperceptibly
  // for the rest of the beat. Slow enough not to fight the row animations.
  const enter = ease.outCubic(span(lineLocal, 0, 0.42));
  // The card settles by 8 percent, linearly, across its five seconds. The
  // reference scales its cards by about 6 percent while they are up; eased, the
  // travel happens in the first second and the rest of the beat measures as a
  // still frame, which is exactly what the gate kept reporting for 0:09 to 0:12.
  const drift = 1.08 - 0.08 * clamp(lineLocal / 5);
  const scale = (0.955 + 0.045 * enter) * drift;
  ctx.save();
  ctx.translate(CARD.x + CARD.w / 2, CARD.y + CARD.h / 2);
  ctx.scale(scale, scale);
  ctx.translate(-(CARD.x + CARD.w / 2), -(CARD.y + CARD.h / 2));

  ctx.save();
  // A card on a light field separates by shadow, not by outline: the reference
  // uses a wide, soft, low-contrast shadow and no border at all.
  ctx.shadowColor = palette === 'light' ? 'rgba(22,42,66,0.28)' : 'rgba(0,0,0,0.45)';
  ctx.shadowBlur = 90;
  ctx.shadowOffsetY = 40;
  roundRect(ctx, box.x, box.y, box.w, box.h, 44);
  ctx.fillStyle = UI.window;
  ctx.fill();
  ctx.restore();

  ctx.globalAlpha = ctx.globalAlpha * clamp(enter * 3);
  const prev = prevStageFor(kind, lineIndex);
  if (stage.app) drawApp(ctx, { stage, lineLocal, prev, t });
  else if (stage.diff) drawDiff(ctx, { stage, lineLocal, prev });
  else if (stage.checks) drawChecks(ctx, { stage, lineLocal, prev });
  else drawRepo(ctx, { stage, lineLocal, prev });

  // The command, only while it is spoken.
  if (stage.command) {
    const p = span(lineLocal, 0.6, 0.95);
    const gone = span(lineLocal, 2.2, 2.7);
    const alpha = clamp(p * 1.6) * (1 - gone);
    if (alpha > 0) {
      const w = Math.min(b.w, measure(ctx, stage.command, { size: T.small, weight: 600, family: 'monospace' }) + 90);
      const pill = { x: b.x, y: box.y + box.h - PAD - 110, w, h: 110 };
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * alpha;
      roundRect(ctx, pill.x, pill.y, pill.w, pill.h, 55);
      ctx.fillStyle = UI.ink;
      ctx.fill();
      text(ctx, stage.command, pill.x + 45, pill.y + 72, {
        size: T.small, weight: 600, family: 'monospace', color: UI.gold, maxWidth: pill.w - 90,
      });
      ctx.restore();
    }
  }
  ctx.restore();

  const L = layout(stage);
  return {
    box, body: b, stage,
    search: stage.app && stage.search ? L.search : null,
    focus: typeof stage.focus === 'number' ? L.rows[stage.focus] : null,
    t,
  };
}

export const BUILD_WINDOW = CARD;
