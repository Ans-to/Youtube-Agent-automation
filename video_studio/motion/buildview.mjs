/**
 * The build view: the thing being made, on the right of the frame.
 *
 * What was here before was a terminal listing `git init`, `git add .` and
 * `git commit` on a 0.75-second metronome. It scrolled whether or not anything
 * was being built, and the owner's note was exact: while the narration says
 * "build it by describing it", the side of the screen is scrolling a list that
 * has nothing to do with the sentence. A panel that moves on its own clock is
 * decoration pretending to be information.
 *
 * This replaces it with the product itself. A browser window showing the book
 * list being built, advanced by the *narration line*, so the panel can only ever
 * show the state of the thing at the moment it is being described:
 *
 *   line 0  an empty page
 *   line 1  the title arrives
 *   line 2  rows of books arrive, one at a time
 *   line 3  the search field appears
 *   line 4  the pointer clicks it, the query types, the list filters
 *
 * At the repository steps the same window becomes the repo, the pull request and
 * the checks - the screens the narration is actually about - because the point
 * is not "an app", it is "the thing he is talking about".
 *
 * Two rules carry over from the rest of the film:
 *   * nothing scrolls on its own timer. A command appears as a pill at the
 *     moment it happens and leaves again.
 *   * the frame is 1080x1480 in design units, inside the right column, clear of
 *     the caption band: no other layer may be drawn there.
 */
import { UI, clamp, span, ease, text, measure, panel, roundRect } from './ui.mjs';

/** The window, in design units of a 3840x2160 frame. */
// 330 put the window's browser bar and its title behind the rail, which is drawn
// over it at y 130-530: on a still of 0:13 the panel was a blank white sheet with
// no page title and no rows, because everything meaningful was under the rail.
// 572 clears it and still leaves the foot above the caption band at 1868.
export const WINDOW = { x: 2700, y: 572, w: 1080, h: 1238 };

const CHROME = 84;      // the browser bar
const PAD = 44;         // body padding
const STATUS = 96;      // the strip along the foot of the window

/** The demo product, which is the one this film builds. */
const BOOKS = ['Dune', 'Piranesi', 'The Overstory', 'Klara and the Sun', 'Piranesi'];

/**
 * What each scene's window shows as the narration moves through it.
 *
 * One entry per stage, not per line: a stage holds until the next one is
 * reached, which is what stops the panel flickering through a state nobody
 * described. ``query`` types itself character by character once the pointer has
 * clicked the field, so the filtering is something the viewer watches happen.
 */
const STAGES = {
  title: [
    { app: true, hint: 'empty page' },
    { app: true, title: 'BOOKS I HAVE READ', rows: [] },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 2) },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'du' },
  ],
  statement: [
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'du' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'dune' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'dune', tag: '40 lines' },
  ],
  pipeline: [
    { repo: true, files: [], branch: 'main', message: 'empty repository' },
    { repo: true, files: [['index.html', 'new']], branch: 'main' },
    { repo: true, files: [['index.html', 'new'], ['books.json', 'new']], branch: 'main' },
    { repo: true, files: [['index.html', 'new'], ['books.json', 'new'], ['README.md', 'new']], branch: 'main' },
  ],
  github: [
    { repo: true, files: [], branch: 'main', message: 'no commits yet', command: 'gh repo create book-list' },
    { repo: true, files: [['README.md', 'new']], branch: 'main', command: 'git add README.md' },
    { repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', command: 'git commit -m "first"' },
  ],
  connect: [
    { repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', chip: 'arena connected' },
    { repo: true, files: [['README.md', 'new'], ['index.html', 'new']], branch: 'main', chip: 'one repo, no more' },
  ],
  prompt: [
    { app: true, prompt: 'build a book list', rows: [] },
    { app: true, prompt: 'build a book list', title: 'BOOKS I HAVE READ', rows: [] },
    { app: true, prompt: 'build a book list, no framework', title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 3) },
  ],
  agent: [
    { repo: true, files: [['index.html', 'new'], ['books.json', 'new']], branch: 'agent/book-list' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'agent/book-list' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new'], ['README.md', 'edit']], branch: 'agent/book-list', command: 'git push -u origin agent/book-list' },
  ],
  diff: [
    { diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add']] },
    { diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add'], ['+ on("input", filter)', 'add']] },
    { diff: true, branch: 'agent/book-list', lines: [['+ const search = el("input")', 'add'], ['+ on("input", filter)', 'add'], ['- // old list', 'del']] },
  ],
  checks: [
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pending']] },
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], command: 'npm run build' },
  ],
  merge: [
    { checks: true, branch: 'agent/book-list', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], chip: 'ready' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'merged', command: 'gh pr merge --squash' },
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'merged', command: 'git push origin main' },
  ],
  feature: [
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'pi' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'pir' },
  ],
  revert: [
    { repo: true, files: [['index.html', 'edit']], branch: 'main', chip: 'reverted', command: 'gh pr revert 12' },
    { repo: true, files: [['index.html', 'new']], branch: 'main', chip: 'clean', command: 'git checkout -- .' },
  ],
  patterns: [
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, tag: 'outcome named' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, tag: 'constraint stated' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, tag: 'error pasted' },
  ],
  safety: [
    { repo: true, files: [['.env', 'ignored'], ['index.html', 'edit']], branch: 'main', chip: 'key in settings' },
    { repo: true, files: [['.env', 'ignored'], ['index.html', 'edit']], branch: 'main', chip: 'not in the repo' },
  ],
  habits: [
    { repo: true, files: [['index.html', 'edit']], branch: 'agent/search', chip: 'branch per change' },
    { checks: true, branch: 'agent/search', rows: [['tests', 'pass'], ['lint', 'pass']], chip: 'merge only green' },
    { repo: true, files: [['README.md', 'edit']], branch: 'main', chip: 'readme as you go' },
  ],
  recap: [
    { repo: true, files: [['index.html', 'edit'], ['books.json', 'new']], branch: 'main', chip: 'repo' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true },
    { checks: true, branch: 'main', rows: [['tests', 'pass'], ['lint', 'pass'], ['build', 'pass']], chip: 'checks' },
  ],
  outro: [
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, chip: 'live' },
    { app: true, title: 'BOOKS I HAVE READ', rows: BOOKS.slice(0, 4), search: true, query: 'dune', chip: 'live' },
  ],
};

/** The stage this scene is at, given the line being spoken. */
export function stageFor(kind, lineIndex) {
  const stages = STAGES[kind] ?? STAGES.title;
  const index = clamp(lineIndex, 0, stages.length - 1);
  return stages[index];
}

/** A row of the app's list, with the whole row sliding up into place. */
function drawAppRow(ctx, { x, y, w, h, value, p, dark }) {
  if (p <= 0) return;
  const e = ease.outCubic(clamp(p));
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2.2);
  ctx.translate(0, (1 - e) * h * 0.7);
  ctx.fillStyle = dark ? 'rgba(255,255,255,0.04)' : 'rgba(11,11,12,0.035)';
  ctx.fillRect(x, y, w, h - 4);
  ctx.fillStyle = UI.red;
  ctx.fillRect(x, y, 10, h - 4);
  text(ctx, value, x + 44, y + h * 0.62, {
    size: 46, weight: 700, family: 'Space Grotesk',
    color: dark ? UI.white : UI.ink, maxWidth: w - 88,
  });
  ctx.restore();
}

/** The browser chrome: traffic lights and the address of what is on screen. */
function drawChrome(ctx, { box, address }) {
  roundRect(ctx, box.x, box.y, box.w, box.h, 22);
  ctx.fillStyle = '#101014';
  ctx.fill();
  ctx.strokeStyle = '#2E2E36';
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.fillStyle = '#17171C';
  roundRect(ctx, box.x, box.y, box.w, CHROME, 22);
  ctx.fill();
  ['#FF5F57', '#FEBC2E', '#28C840'].forEach((colour, i) => {
    ctx.beginPath();
    ctx.arc(box.x + 42 + i * 34, box.y + CHROME / 2, 10, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
  });
  const pill = { x: box.x + 160, y: box.y + 18, w: box.w - 200, h: CHROME - 36 };
  roundRect(ctx, pill.x, pill.y, pill.w, pill.h, 16);
  ctx.fillStyle = '#0B0B0E';
  ctx.fill();
  text(ctx, address, pill.x + 24, pill.y + pill.h * 0.66, {
    size: 30, weight: 500, family: 'Inter', color: UI.faint, maxWidth: pill.w - 48,
  });
}

/** What the app looks like at this stage. */
function drawApp(ctx, { body, stage, lineLocal }) {
  // The page itself: light, because a real page is light and because it makes
  // the drawn interface read as a product rather than as a diagram.
  roundRect(ctx, body.x, body.y, body.w, body.h, 12);
  ctx.fillStyle = '#F7F7F9';
  ctx.fill();

  if (stage.hint) {
    ctx.save();
    ctx.strokeStyle = 'rgba(11,11,12,0.22)';
    ctx.lineWidth = 4;
    ctx.setLineDash([16, 12]);
    roundRect(ctx, body.x + PAD, body.y + PAD, body.w - PAD * 2, body.h - PAD * 2, 12);
    ctx.stroke();
    ctx.restore();
    text(ctx, stage.hint, body.x + body.w / 2, body.y + body.h / 2, {
      size: 40, weight: 600, family: 'Inter', color: 'rgba(11,11,12,0.34)', align: 'center',
    });
    return;
  }

  let cursorY = body.y + PAD + 46;
  if (stage.prompt) {
    roundRect(ctx, body.x + PAD, body.y + PAD, body.w - PAD * 2, 96, 14);
    ctx.fillStyle = UI.ink;
    ctx.fill();
    text(ctx, '> ' + stage.prompt, body.x + PAD + 26, body.y + PAD + 60, {
      size: 32, weight: 600, family: 'Inter', color: UI.gold, maxWidth: body.w - PAD * 2 - 52,
    });
    cursorY = body.y + PAD + 96 + 64;
  }

  if (stage.title) {
    text(ctx, stage.title, body.x + PAD, cursorY, {
      size: 58, weight: 700, family: 'Space Grotesk', color: UI.ink,
      maxWidth: body.w - PAD * 2,
    });
    ctx.fillStyle = UI.red;
    ctx.fillRect(body.x + PAD, cursorY + 22, 120, 8);
    cursorY += 96;
  }

  const rows = stage.rows ?? [];
  const rowH = Math.min(120, (body.h - (cursorY - body.y) - PAD - 120) / Math.max(rows.length, 1));
  rows.forEach((value, i) => {
    // Rows arrive on the line, one after another: the build is what the panel is
    // for, so it happens in front of the viewer rather than already being done.
    const at = i * 0.22;
    const p = span(lineLocal, at, at + 0.4);
    drawAppRow(ctx, {
      x: body.x + PAD, y: cursorY + i * rowH, w: body.w - PAD * 2, h: rowH,
      value, p, dark: false,
    });
  });

  if (stage.search) {
    const field = searchRect(body);
    roundRect(ctx, field.x, field.y, field.w, field.h, 14);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = stage.focus ? UI.gold : 'rgba(11,11,12,0.2)';
    ctx.lineWidth = stage.focus ? 6 : 3;
    ctx.stroke();
    // a magnifier: a ring and a handle, drawn as two strokes
    ctx.save();
    ctx.strokeStyle = 'rgba(11,11,12,0.45)';
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.arc(field.x + 46, field.y + field.h / 2 - 4, 16, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(field.x + 58, field.y + field.h / 2 + 8);
    ctx.lineTo(field.x + 70, field.y + field.h / 2 + 20);
    ctx.stroke();
    ctx.restore();
    const query = stage.query ?? '';
    text(ctx, query || 'search', field.x + 100, field.y + field.h * 0.64, {
      size: 38, weight: 600, family: 'Inter',
      color: query ? UI.ink : 'rgba(11,11,12,0.34)', maxWidth: field.w - 160,
    });
    if (stage.caret) {
      ctx.fillStyle = UI.ink;
      ctx.fillRect(field.x + 104 + (query ? measure(ctx, query, { size: 38, weight: 600 }) : 0),
        field.y + field.h * 0.24, 5, field.h * 0.52);
    }
  }

  if (stage.tag) {
    const w = measure(ctx, stage.tag, { size: 30, weight: 700 }) + 56;
    roundRect(ctx, body.x + body.w - PAD - w, body.y + PAD, w, 62, 31);
    ctx.fillStyle = UI.gold;
    ctx.fill();
    text(ctx, stage.tag, body.x + body.w - PAD - w / 2, body.y + PAD + 42, {
      size: 30, weight: 700, family: 'Inter', color: UI.ink, align: 'center',
    });
  }
}

/** Where the search field is, so the pointer can be aimed at it. */
export function searchRect(body) {
  return {
    x: body.x + PAD,
    y: body.y + body.h - 150,
    w: body.w - PAD * 2,
    h: 96,
  };
}

/** A file list, a diff or a checks list - the repository screens. */
function drawRepo(ctx, { body, stage, lineLocal }) {
  roundRect(ctx, body.x, body.y, body.w, body.h, 12);
  ctx.fillStyle = '#101014';
  ctx.fill();

  text(ctx, 'book-list', body.x + PAD, body.y + PAD + 34, {
    size: 40, weight: 700, family: 'Space Grotesk', color: UI.white,
  });
  // the branch chip: what branch the work is actually on
  const branch = stage.branch ?? 'main';
  const bw = measure(ctx, branch, { size: 28, weight: 600 }) + 72;
  roundRect(ctx, body.x + body.w - PAD - bw, body.y + PAD + 4, bw, 58, 14);
  ctx.fillStyle = 'rgba(242,194,48,0.16)';
  ctx.fill();
  ctx.strokeStyle = UI.gold;
  ctx.lineWidth = 3;
  ctx.stroke();
  text(ctx, branch, body.x + body.w - PAD - bw / 2, body.y + PAD + 44, {
    size: 28, weight: 600, family: 'Inter', color: UI.gold, align: 'center', maxWidth: bw - 30,
  });

  let y = body.y + PAD + 120;

  if (stage.files) {
    if (!stage.files.length) {
      text(ctx, 'no files yet', body.x + PAD, y + 20, {
        size: 34, weight: 500, family: 'Inter', color: 'rgba(255,255,255,0.4)',
      });
    }
    stage.files.forEach(([name, state], i) => {
      const p = span(lineLocal, i * 0.2, i * 0.2 + 0.4);
      if (p <= 0) return;
      const colour = state === 'new' ? UI.green : state === 'ignored' ? UI.faint : UI.gold;
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2);
      ctx.fillStyle = colour;
      ctx.beginPath();
      ctx.arc(body.x + PAD + 12, y + 18, 10, 0, Math.PI * 2);
      ctx.fill();
      text(ctx, name, body.x + PAD + 46, y + 30, {
        size: 36, weight: 500, family: 'Inter', color: UI.white, maxWidth: body.w - PAD * 2 - 200,
      });
      text(ctx, state === 'new' ? 'added' : state === 'ignored' ? 'ignored' : 'changed', body.x + body.w - PAD, y + 30, {
        size: 26, weight: 600, family: 'Inter', color: colour, align: 'right',
      });
      ctx.restore();
      y += 74;
    });
  }

  if (stage.lines) {
    stage.lines.forEach(([value, kind], i) => {
      const p = span(lineLocal, i * 0.24, i * 0.24 + 0.4);
      if (p <= 0) return;
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2);
      ctx.fillStyle = kind === 'add' ? 'rgba(46,158,91,0.18)' : 'rgba(196,22,28,0.18)';
      ctx.fillRect(body.x + PAD - 16, y - 4, body.w - PAD * 2 + 32, 62);
      text(ctx, value, body.x + PAD, y + 42, {
        size: 32, weight: 500, family: 'Inter',
        color: kind === 'add' ? '#7FE0A4' : '#F08A8E', maxWidth: body.w - PAD * 2,
      });
      ctx.restore();
      y += 74;
    });
  }

  if (stage.rows) {
    stage.rows.forEach(([name, state], i) => {
      const p = span(lineLocal, i * 0.24, i * 0.24 + 0.4);
      if (p <= 0) return;
      const colour = state === 'pass' ? UI.green : state === 'fail' ? UI.red : UI.faint;
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * clamp(p * 2);
      // the tick plate: the same one the pull-request scene uses on the film
      roundRect(ctx, body.x + PAD, y + 2, 56, 56, 12);
      ctx.fillStyle = state === 'pass' ? UI.green : 'rgba(255,255,255,0.08)';
      ctx.fill();
      if (state === 'pass') {
        ctx.strokeStyle = UI.white;
        ctx.lineWidth = 6;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(body.x + PAD + 14, y + 30);
        ctx.lineTo(body.x + PAD + 25, y + 42);
        ctx.lineTo(body.x + PAD + 44, y + 16);
        ctx.stroke();
      }
      text(ctx, name, body.x + PAD + 84, y + 42, {
        size: 36, weight: 600, family: 'Inter', color: UI.white,
      });
      text(ctx, state, body.x + body.w - PAD, y + 42, {
        size: 26, weight: 600, family: 'Inter', color: colour, align: 'right',
      });
      ctx.restore();
      y += 82;
    });
  }

  if (stage.message) {
    text(ctx, stage.message, body.x + PAD, y + 30, {
      size: 30, weight: 500, family: 'Inter', color: 'rgba(255,255,255,0.42)',
    });
  }
}

/**
 * The whole panel: window, screen, status, and the command pill.
 *
 * ``lineLocal`` is the time since the current narration line started, which is
 * what every arrival inside the panel is timed against - never a wall clock.
 */
export function buildView(ctx, { kind, lineIndex, lineLocal, t, h = 2160 }) {
  const stage = stageFor(kind, lineIndex);
  const box = { ...WINDOW };
  const address = stage.repo || stage.diff || stage.checks
    ? 'github.com/you/book-list'
    : 'localhost:3000';
  const body = {
    x: box.x + 24,
    y: box.y + CHROME + 20,
    w: box.w - 48,
    h: box.h - CHROME - STATUS - 56,
  };

  drawChrome(ctx, { box, address });

  if (stage.app) drawApp(ctx, { body, stage, lineLocal });
  else drawRepo(ctx, { body, stage, lineLocal });

  // The status strip: the one line of truth about the build. It carries a block
  // that travels along it every beat, so the panel is never completely still
  // between two stages - and it is the only thing in the window that moves on
  // the beat rather than on the narration.
  const stripY = box.y + box.h - STATUS - 8;
  ctx.fillStyle = '#141419';
  roundRect(ctx, box.x + 24, stripY, box.w - 48, STATUS - 16, 12);
  ctx.fill();
  const facts = [];
  if (stage.branch) facts.push(stage.branch);
  if (stage.files) facts.push(stage.files.length + ' files');
  if (stage.checks) facts.push(stage.rows.filter(([, state]) => state === 'pass').length + '/' + stage.rows.length + ' checks');
  if (stage.chip) facts.push(stage.chip);
  if (stage.tag) facts.push(stage.tag);
  if (!facts.length) facts.push(stage.repo ? 'no commits yet' : 'one page, no framework');
  text(ctx, facts.join('   ·   '), box.x + 48, stripY + 52, {
    size: 28, weight: 600, family: 'Inter', color: UI.faint, maxWidth: box.w - 220,
  });
  const travel = (t % 1.5) / 1.5;
  ctx.fillStyle = UI.gold;
  ctx.fillRect(box.x + 48 + travel * (box.w - 220), stripY + STATUS - 34, 120, 6);

  // The command, only at the moment it happens.
  if (stage.command) {
    const p = span(lineLocal, 0.1, 0.45);
    const gone = span(lineLocal, 2.0, 2.5);
    const alpha = clamp(p * 1.6) * (1 - gone);
    if (alpha > 0) {
      const label = stage.command;
      const w = Math.min(body.w - 40, measure(ctx, label, { size: 30, weight: 600, family: 'Inter' }) + 72);
      const pill = { x: body.x + 20, y: body.y + 16, w, h: 66 };
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * alpha;
      roundRect(ctx, pill.x, pill.y, pill.w, pill.h, 33);
      ctx.fillStyle = UI.ink;
      ctx.fill();
      ctx.strokeStyle = UI.gold;
      ctx.lineWidth = 3;
      ctx.stroke();
      text(ctx, label, pill.x + 34, pill.y + 44, {
        size: 30, weight: 600, family: 'Inter', color: UI.gold, maxWidth: pill.w - 68,
      });
      ctx.restore();
    }
  }

  return {
    box,
    body,
    stage,
    search: stage.app && stage.search ? searchRect(body) : null,
  };
}

export const BUILD_WINDOW = WINDOW;
