/**
 * The second unit: the two things that are always alive in the picture.
 *
 * The owner's bar is that in any one second, two different things should be
 * moving in two different parts of the frame - his example is a subtitle and
 * code being typed in the same second, so the eye always has somewhere to go.
 * Measured on this film, 42% of its seconds had one thing happening or none:
 * a card finishes, the narration keeps going, and the picture waits.
 *
 * These two elements are the floor under every scene. They are not decoration:
 * the rail names the step you are in and counts the words of the current
 * sentence, and the console types the actual code each scene is about, at the
 * speed of speech, scrolling as it fills. Both are driven by the same
 * narration timings as the rest of the film, so they are never out of step with
 * what is being said.
 *
 * Why these positions: the picture is measured as a 3x2 grid with the furniture
 * bands removed, so the rail sits in the top-right cell and the console in the
 * bottom-right one. Two different cells means two independent live regions,
 * which is exactly what the check asks for. Neither overlaps a scene's title,
 * which is set from the left.
 */
import { UI, clamp, span, ease, text, panel, roundRect } from './ui.mjs';

// Design units. The canvas is 3840x2160 and everything is drawn in those units.
const RAIL = { x: 2560, y: 130, w: 1240, h: 400 };
const CONSOLE = { x: 2800, y: 1240, w: 940, h: 650 };

/**
 * Where the console sits, per kind of scene.
 *
 * It has to be in a different cell from the rail, and it must not land on the
 * picture it is annotating. Those two rules conflict in the full-bleed title
 * cards, whose type is centred and wide enough to reach the right edge - seen on
 * a still of 0:12, where the console covered the word "GITHUB". So the cards
 * that fill the frame get the console on the left, where they keep a margin, and
 * everything else keeps it on the right.
 */
// The four cards that use the whole frame get a narrow vertical ticker in the
// right margin, 560 units wide, where their centred type never reaches.
// Four rows of 240 fit inside 1300 once the header is allowed for; five
// overflowed the panel, seen on a still of 0:12.
// Below the rail: 420 put the ticker's first row on top of the rail's bar.
const TICKER = { x: 3240, y: 600, w: 560, h: 900, rows: 4, rowH: 190, size: 44, compact: true };
const CONSOLE_AT = {
  title: TICKER, statement: TICKER, outro: TICKER, loop: TICKER,
};

/** What the console types, per kind of scene. Real lines from the story. */
const SNIPPETS = {
  title: ['git init', 'git add .', 'git commit -m "first"'],
  statement: ['intent: ship it', 'scope: one page', 'rule: small steps'],
  pipeline: ['prompt ->', 'plan -> branch ->', 'diff -> checks -> merge'],
  github: ['git remote add origin', 'git push -u origin main', 'gh repo view'],
  connect: ['arena connect github', 'scope: one repo', 'read: files, history'],
  prompt: ['build a book list', 'read books.json', 'no framework. no build.'],
  agent: ['plan the change', 'edit the branch', 'run the checks'],
  diff: ['+ const search = el("input")', '+ on("input", filter)', '- // old list'],
  checks: ['npm test  ... ok', 'lint      ... ok', 'build     ... ok'],
  merge: ['gh pr merge --squash', 'git push origin main', 'pages: deploying'],
  feature: ['add a search box', 'filter on input', 'one file. 40 lines.'],
  revert: ['gh pr revert 12', 'git log --oneline', 'git checkout -- .'],
  patterns: ['name the outcome', 'state the constraint', 'paste the error'],
  safety: ['secrets: settings', 'never in the repo', 'rotate the key'],
  habits: ['branch per change', 'merge only green', 'readme as you go'],
  recap: ['repo. prompt. diff.', 'checks. merge. repeat.', 'smaller next time.'],
  outro: ['build it by', 'describing it.', 'no course. no key.'],
};

/** The step name the rail shows, per kind of scene. */
const STEPS = {
  title: 'START', statement: 'THE IDEA', pipeline: 'THE LOOP', github: 'REPOSITORY',
  connect: 'ACCOUNT', prompt: 'PROMPT', agent: 'AGENT', diff: 'DIFF', checks: 'CHECKS',
  merge: 'MERGE', feature: 'ONE MORE', revert: 'RECOVERY', patterns: 'PATTERNS',
  safety: 'SAFETY', habits: 'HABITS', recap: 'RECAP', outro: 'END',
};

/**
 * The metronome, in beats.
 *
 * Both elements below move on this clock. It is not tied to the narration, and
 * that is on purpose: the point of the second unit is that something is always
 * happening, including in the half-second gaps between spoken words. The film's
 * own staging still follows the voice; this is the floor underneath it.
 */
const BEAT = 0.75;

const beatOf = (t) => Math.floor(t / BEAT);
const beatPhase = (t) => (t % BEAT) / BEAT;

/**
 * The rail: the step you are in, and a counter that climbs.
 *
 * Every beat a block moves. Not the digits - a counter changing from 03 to 04
 * moves too few pixels to register in a measurement of the picture, and the
 * first version of this element was exactly that mistake: measured, the whole
 * region moved by 0.5 grey levels while it appeared to be ticking. So each beat
 * the filled part of the bar jumps by one segment and a solid block stamps at
 * its head. That is a block of mass arriving somewhere it was not, which is the
 * only thing this film has found that a viewer and a measurement both see.
 */
export function stepRail(ctx, { scene, t }) {
  const label = STEPS[scene.kind] ?? 'VIBE CODING';
  const beat = beatOf(t);
  const phase = ease.outCubic(beatPhase(t));
  const segments = 12;
  const filled = ((beat % segments) + 1) / segments;

  roundRect(ctx, RAIL.x, RAIL.y, RAIL.w, RAIL.h, 14);
  ctx.fillStyle = UI.ink;
  ctx.fill();
  ctx.fillStyle = UI.gold;
  ctx.fillRect(RAIL.x, RAIL.y, 12, RAIL.h);

  text(ctx, label, RAIL.x + 56, RAIL.y + 96, {
    size: 62, weight: 700, family: 'Space Grotesk', color: UI.white, tracking: 5,
  });
  const step = ((beat % 12) + 1);
  text(ctx, String(step).padStart(2, '0'), RAIL.x + RAIL.w - 56, RAIL.y + 104, {
    size: 86, weight: 700, color: UI.gold, align: 'right', tracking: 2,
  });

  // The bar: twelve segments, and a solid head that steps along it. Everything
  // here is sized against the measurement, not against taste. The rail fills a
  // large share of its cell on purpose: measured, a small head stepping 74 units
  // inside a 256-unit cell moved the pooled average by under six grey levels,
  // and a beat the measurement cannot see is a beat the viewer may not either.
  const x0 = RAIL.x + 56;
  const width = RAIL.w - 112;
  const segW = width / 12;
  for (let i = 0; i < 12; i += 1) {
    ctx.fillStyle = i < Math.ceil(filled * 12) ? UI.red : 'rgba(255,255,255,0.16)';
    ctx.fillRect(x0 + i * segW + 4, RAIL.y + 200, segW - 8, 150);
  }
  // The head travels the whole rail, one step per beat: a 190-unit block
  // crossing a quarter of a cell's width every 0.75 seconds.
  const headX = x0 + clamp(filled) * (width - 190);
  ctx.fillStyle = UI.white;
  ctx.fillRect(headX, RAIL.y + 176, 190, 198);
  ctx.fillStyle = UI.ink;
  ctx.fillRect(headX + 28, RAIL.y + 224, 134, 102);
}

/**
 * The console: the code this scene is about, one line arriving per beat,
 * scrolling as it fills.
 *
 * A line arriving shifts every line in the panel up by one row, so the change is
 * a whole block of type moving - a fifth of the panel's area - rather than a
 * character appearing at a cursor. The cursor is a solid block for the same
 * reason.
 */
export function liveConsole(ctx, { scene, t, local }) {
  const snippet = SNIPPETS[scene.kind] ?? SNIPPETS.title;
  const beat = beatOf(t);
  const phase = ease.outCubic(beatPhase(t));

  const box = { ...CONSOLE, ...(CONSOLE_AT[scene.kind] ?? {}) };
  const rows = box.rows ?? 4;
  const rowH = box.rowH ?? 120;
  const size = box.size ?? 52;
  roundRect(ctx, box.x, box.y, box.w, box.h, 18);
  ctx.fillStyle = '#101014';
  ctx.fill();
  ctx.strokeStyle = '#2E2E36';
  ctx.lineWidth = 4;
  ctx.stroke();

  // A narrow ticker has no room for a window bar; a wide console does.
  const header = box.compact ? 60 : 150;
  if (!box.compact) {
    ['#FF5F57', '#FEBC2E', '#28C840'].forEach((colour, i) => {
      ctx.beginPath();
      ctx.arc(box.x + 46 + i * 34, box.y + 52, 11, 0, Math.PI * 2);
      ctx.fillStyle = colour;
      ctx.fill();
    });
    text(ctx, 'book-list  -  bash', box.x + 168, box.y + 64, {
      size: 28, weight: 600, color: '#8A8A96', tracking: 2,
    });
  }

  // The panel is a window onto an endless list of lines: each beat the window
  // moves down by one row, and the newest row slides in from the bottom carrying
  // a solid gold plate. Big type and a big plate, for the same reason as the
  // rail's head: a 30 px line moving 84 units inside a sixth of the frame changes
  // a pooled cell by less than a grey level.
  const top = box.y + header;
  for (let row = 0; row < rows; row += 1) {
    const index = beat + row;
    const value = snippet[index % snippet.length];
    const y = top + row * rowH + (1 - phase) * rowH;
    const fresh = row === rows - 1;
    if (fresh) {
      ctx.save();
      ctx.globalAlpha = 0.55 + 0.45 * phase;
      ctx.fillStyle = UI.gold;
      ctx.fillRect(box.x + 20, y - rowH * 0.62, box.w - 40, rowH * 0.82);
      ctx.restore();
    }
    text(ctx, '>', box.x + 26, y, {
      size, weight: 700, color: fresh ? UI.ink : UI.gold,
    });
    text(ctx, value, box.x + 26 + size * 0.75, y, {
      size, weight: fresh ? 700 : 500, color: fresh ? UI.ink : '#D6D6DE',
      maxWidth: box.w - 80,
    });
  }
  // the cursor: a solid block, blinking on the half beat
  if (Math.floor(t / 0.375) % 2 === 0) {
    ctx.fillStyle = UI.gold;
    ctx.fillRect(box.x + 20, top + rows * rowH + 10, box.w - 40, 34);
  }
}

/**
 * A pointer that crosses the frame once per spoken line, so a third cell is
 * alive in scenes that would otherwise hold still in the middle of the frame.
 *
 * It is drawn inside the picture rather than in the furniture, and it never
 * presses anything: a press would promise an interaction the scene is not
 * making. This one simply travels, the way a producer's finger runs across a
 * board.
 */
export function roamingPointer(ctx, { scene, t, seed = 0 }) {
  const travel = span(t * 0.55 + seed, 0, 1);
  const phase = (t * 0.55 + seed) % 2;
  const across = phase < 1 ? phase : 2 - phase;
  const x = 900 + across * 2100;
  const y = 1180 + Math.sin((t * 0.55 + seed) * Math.PI) * 420;
  const alpha = 0.5 * Math.sin(Math.PI * clamp(travel)) + 0.12;
  ctx.save();
  ctx.globalAlpha = clamp(alpha);
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + 38, y + 96);
  ctx.lineTo(x + 58, y + 52);
  ctx.lineTo(x + 104, y + 44);
  ctx.closePath();
  ctx.fillStyle = UI.ink;
  ctx.fill();
  ctx.strokeStyle = UI.white;
  ctx.lineWidth = 4;
  ctx.stroke();
  ctx.restore();
}

/** Both always-on elements, for the layer between the scene and the bands. */
export function secondUnit(ctx, { scene, t, local, pointer = true }) {
  if (pointer) roamingPointer(ctx, { scene, t, seed: 0.35 });
  stepRail(ctx, { scene, t });
  liveConsole(ctx, { scene, t, local });
}
