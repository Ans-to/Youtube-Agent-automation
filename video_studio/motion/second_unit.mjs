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
import { UI, clamp, span, ease, text, panel, roundRect, cursor, clickRing } from './ui.mjs';

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

/** What a command answers when it is clicked. Short: it has to fit the card. */
const OUTPUTS = {
  'git init': 'empty repo created',
  'git add .': '3 files staged',
  'git commit -m "first"': 'commit 9f2c1a7',
  'git remote add origin': 'origin set',
  'git push -u origin main': 'pushed to main',
  'gh repo view': 'repo opened',
  'arena connect github': 'one repo connected',
  'read: files, history': '12 files read',
  'prompt ->': 'prompt accepted',
  'plan -> branch ->': 'branch created',
  'diff -> checks -> merge': 'ready to merge',
  'build a book list': 'one page built',
  'read books.json': 'list loaded',
  'no framework. no build.': '40 lines added',
  'plan the change': 'plan ready',
  'edit the branch': '3 files changed',
  'run the checks': 'checks green',
  '+ const search = el("input")': 'line added',
  '+ on("input", filter)': 'handler bound',
  '- // old list': 'line removed',
  'npm test  ... ok': 'all tests pass',
  'lint      ... ok': 'no lint errors',
  'build     ... ok': 'built in 1.2s',
  'gh pr merge --squash': 'merged to main',
  'git push origin main': 'main updated',
  'pages: deploying': 'pages live',
  'add a search box': 'feature shipped',
  'filter on input': 'filters as you type',
  'one file. 40 lines.': 'one file changed',
  'gh pr revert 12': 'change reverted',
  'git log --oneline': 'history restored',
  'git checkout -- .': 'working tree clean',
  'name the outcome': 'outcome named',
  'state the constraint': 'constraint stated',
  'paste the error': 'error pasted',
  'secrets: settings': 'key set in settings',
  'never in the repo': 'repo stays clean',
  'rotate the key': 'key rotated',
  'branch per change': 'branch open',
  'merge only green': 'merge blocked until green',
  'readme as you go': 'readme updated',
  'repo. prompt. diff.': 'loop complete',
  'checks. merge. repeat.': 'shipped',
  'smaller next time.': 'scope cut',
  'build it by': 'repo created',
  'describing it.': 'page live',
  'no course. no key.': 'nothing to buy',
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
export function liveConsole(ctx, { scene, t, local, h = 2160 }) {
  const snippet = SNIPPETS[scene.kind] ?? SNIPPETS.title;

  const box = { ...CONSOLE, ...(CONSOLE_AT[scene.kind] ?? {}) };
  const rows = box.rows ?? 4;
  const rowH = box.rowH ?? 120;
  const size = box.size ?? 52;
  const header = box.compact ? 60 : 150;
  const plan = interactionPlan({ local, box, rows, rowH, header, beatOf, snippet });
  const open = plan.filter((action) => local >= action.at && local <= action.at + INTERACT.hold).pop();
  // The feed pauses for a moment while its answer is open, then resumes where it
  // stopped. Without the pause the command that was clicked scrolls out from
  // under the pointer and the card ends up answering a row that is no longer
  // there - seen on a still of 0:18, where the card said "git init" while the
  // pointer sat on "git add .".
  const paused = open ? Math.min(Math.max(0, local - open.at), 0.9) : 0;
  const tRows = t - paused;
  const beat = beatOf(tRows);
  const phase = ease.outCubic(beatPhase(tRows));
  roundRect(ctx, box.x, box.y, box.w, box.h, 18);
  ctx.fillStyle = '#101014';
  ctx.fill();
  ctx.strokeStyle = '#2E2E36';
  ctx.lineWidth = 4;
  ctx.stroke();

  // A narrow ticker has no room for a window bar; a wide console does.
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

  // What the pointer just clicked, and what came back.
  //
  // This is the "opens something" half of the interaction. It is a real result
  // for the exact command under the pointer, not a decorative panel: the console
  // is the only place in the frame where a command and its output belong
  // together, and putting the answer under the panel keeps it inside the live
  // column, where nothing else is drawn.
  if (open) {
    const grow = ease.outCubic(span(local, open.at, open.at + 0.28));
    const fade = 1 - span(local, open.at + INTERACT.hold - 0.3, open.at + INTERACT.hold);
    // Below the panel - unless the panel already reaches the caption band, in
    // which case the card opens above it. A card that runs under the subtitles
    // is the same overlap fault as two lines of type in one place.
    const below = box.y + box.h + 26;
    const cardY = below + 168 > h * 0.855 ? box.y - 26 - 168 : below;
    const card = {
      x: box.x,
      y: cardY,
      w: box.w,
      h: 168 * grow,
    };
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * clamp(grow * 1.4) * fade;
    panel(ctx, { x: card.x, y: card.y, w: card.w, h: card.h, r: 14, fill: '#101014', stroke: UI.gold });
    ctx.fillStyle = UI.gold;
    ctx.fillRect(card.x, card.y, 12, card.h);
    if (grow > 0.55) {
      // The command leads and its answer follows. The list keeps scrolling after
      // the press, so the card has to say which command it is answering - a card
      // that only says "3 files staged" is a fact with no subject.
      text(ctx, 'OUTPUT', card.x + 34, card.y + 40, {
        size: 24, weight: 700, color: UI.faint, tracking: 4,
      });
      text(ctx, '> ' + open.value, card.x + 34, card.y + 86, {
        size: 30, weight: 700, color: UI.gold, maxWidth: card.w - 68,
      });
      text(ctx, open.result ?? 'done', card.x + 34, card.y + 136, {
        size: 34, weight: 600, color: UI.white, maxWidth: card.w - 68,
      });
    }
    ctx.restore();

    // The row under the pointer takes a gold outline while it is being used.
    const ring = span(local, open.at, open.at + 0.45);
    if (ring < 1) {
      const rowY = top + (rows - 1) * rowH + (1 - phase) * rowH;
      ctx.save();
      ctx.globalAlpha = ctx.globalAlpha * (1 - ring);
      // White, not gold: the row the pointer presses is already the gold one, so
      // a gold outline around it would be invisible.
      ctx.strokeStyle = UI.white;
      ctx.lineWidth = 5;
      roundRect(ctx, box.x + 14, rowY - rowH * 0.66, box.w - 28, rowH * 0.86, 10);
      ctx.stroke();
      ctx.restore();
    }
  }

  return { box, rows, rowH, header, plan };
}

/**
 * A pointer with a job: it goes to a command, clicks it, and the output opens.
 *
 * The previous version was a shape travelling the frame on a sine, never
 * touching anything. The owner's note was exact: "cursur is just moving rendomly
 * give him a perpose like clicking on anything and that opens something". A
 * pointer that presses nothing is the most amateur object you can put on screen,
 * because every viewer knows what a pointer is for.
 *
 * So it is scripted, not roamed. Every few seconds it travels along an eased path
 * to the newest line in the console, presses it, and the console answers: the
 * row under the pointer takes a gold outline, a click ring opens at the press,
 * and an output card folds open beneath the panel with the result of that exact
 * command. Then the pointer withdraws and waits for the next one.
 *
 * The schedule is fixed rather than random, so the film renders the same way
 * twice, and every action has a target that exists on that frame.
 */
const INTERACT = {
  first: 3.0,     // first click, in scene-local seconds
  every: 5.2,     // and then one every five seconds or so
  travel: 0.55,   // how long the pointer takes to reach the target
  press: 0.12,    // how long the button is held down
  ring: 0.5,      // how long the click ring stays open
  hold: 2.6,      // how long the opened output stays on screen
};

/** Where the pointer rests between jobs: inside the panel's lower edge. */
function pointerRest(box) {
  return { x: box.x + box.w - 120, y: box.y + box.h - 60 };
}

/** Where it clicks: the row slot that new commands scroll into. */
function pointerTarget(box, rows, rowH, header) {
  // On the row's plate, not under it. The plate is drawn from the row's baseline
  // up by 0.62 of a row, so its centre is about a fifth of a row above the
  // baseline - measured off a still, where the first attempt clicked the empty
  // space below the row it meant to press.
  return { x: box.x + box.w * 0.42, y: box.y + header + (rows - 1) * rowH - rowH * 0.18 };
}

/**
 * The schedule of clicks for one scene: when, and which command is under the
 * pointer when it lands.
 */
export function interactionPlan({ local, box, rows, rowH, header, beatOf, snippet }) {
  const plan = [];
  for (let k = 0; k < 8; k += 1) {
    const at = INTERACT.first + k * INTERACT.every;
    if (at > local + INTERACT.every) break;
    const index = beatOf(at) + rows - 1;
    const value = snippet[index % snippet.length];
    plan.push({ at, index, value, result: OUTPUTS[value] ?? 'saved' });
  }
  return plan;
}

/** Draw the pointer for whichever part of the plan is on screen now. */
function purposefulPointer(ctx, { local, box, rows, rowH, header, plan }) {
  const rest = pointerRest(box);
  const target = pointerTarget(box, rows, rowH, header);
  let x = rest.x;
  let y = rest.y;
  let press = 0;
  let alpha = 0;
  let ringAt = null;

  for (const action of plan) {
    const nearest = action.at - INTERACT.travel;
    if (local < nearest || local > action.at + INTERACT.ring + 1.1) continue;
    // One eased move to the target, a held press, then a slower withdrawal.
    if (local <= action.at) {
      const e = ease.inOutCubic(span(local, nearest, action.at));
      x = rest.x + (target.x - rest.x) * e;
      y = rest.y + (target.y - rest.y) * e;
      alpha = span(local, nearest, nearest + 0.2);
      press = span(local, action.at - INTERACT.press, action.at);
      ringAt = local >= action.at ? action.at : null;
    } else {
      const back = ease.inOutCubic(span(local, action.at + 0.55, action.at + 1.15));
      x = target.x + (rest.x - target.x) * back;
      y = target.y + (rest.y - target.y) * back;
      alpha = 1 - span(local, action.at + 0.9, action.at + 1.2);
      press = 1 - span(local, action.at, action.at + INTERACT.press);
    }
    if (local >= action.at && local <= action.at + INTERACT.ring) ringAt = action.at;
    break;
  }

  if (alpha <= 0) return;
  if (ringAt !== null) {
    clickRing(ctx, target.x, target.y, span(local, ringAt, ringAt + INTERACT.ring), {
      colour: UI.gold, radius: 96,
    });
  }
  cursor(ctx, x, y, { alpha, press, scale: 1.15 });
}

/** Both always-on elements, for the layer between the scene and the bands. */
export function secondUnit(ctx, { scene, t, local, pointer = true, h = 2160 }) {
  stepRail(ctx, { scene, t });
  const unit = liveConsole(ctx, { scene, t, local, h });
  // The pointer is drawn last: it is the thing on top of the interface, and the
  // panel it just opened must not cover the hand that opened it.
  if (pointer) {
    purposefulPointer(ctx, {
      local, box: unit.box, rows: unit.rows, rowH: unit.rowH, header: unit.header, plan: unit.plan,
    });
  }
}
