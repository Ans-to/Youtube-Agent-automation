/**
 * The second unit: the two things that are always alive in the picture.
 *
 * The owner's bar is that in any one second, two different things should be
 * moving in two different parts of the frame - his example is a subtitle and
 * code being typed in the same second, so the eye always has somewhere to go.
 *
 * These two elements are the floor under every scene:
 *
 *   * the rail names the step you are in and steps a block along it on the beat;
 *   * the build window shows the product being made, advanced by the narration
 *     line, so it can only ever show the state of the thing at the moment it is
 *     being described.
 *
 * The second one used to be a terminal that scrolled a list of git commands on
 * its own 0.75-second clock. The owner's note was that while the narration says
 * "build it by describing it", the side of the frame is scrolling something with
 * nothing to do with the sentence. It is gone; `buildview.mjs` replaces it. The
 * command still appears, but only as a pill at the moment it happens, and then
 * it leaves.
 *
 * Why these positions: the picture is measured as a 3x2 grid with the furniture
 * bands removed, so the rail sits in the top-right cell and the window in the
 * two cells below it. Neither overlaps a scene's title, which is set from the
 * left.
 */
import { UI, clamp, span, ease, text, roundRect, cursor, clickRing } from './ui.mjs';
import { buildView, CARD } from './buildview.mjs';

// Design units. The canvas is 3840x2160 and everything is drawn in those units.
const RAIL = { x: 2560, y: 130, w: 1240, h: 400 };

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
 * The rail moves on this clock. It is not tied to the narration, and that is on
 * purpose: the point of the second unit is that something is always happening,
 * including in the half-second gaps between spoken words. The film's own staging
 * still follows the voice; this is the floor underneath it.
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
  void phase;
}

/**
 * The pointer, which now clicks the product.
 *
 * It travels to the search field on the line where the search is introduced,
 * presses it, and the typing that filters the list starts on the press. The
 * previous version clicked a scrolling list of commands; before that it roamed
 * the frame on a sine and pressed nothing at all. A pointer exists to press
 * something, and what it presses has to be visible and has to answer.
 */
function purposefulPointer(ctx, { lineLocal, from, to }) {
  if (!to) return;
  // Slower than the old sidebar pointer: on a card this size the eye has to
  // follow the travel, so it gets 0.55 s and a visible hover before the press.
  const travel = span(lineLocal, 0.05, 0.6);
  const press = 0.6;
  if (lineLocal > 1.9) return;
  const e = ease.inOutCubic(travel);
  const x = from.x + (to.x - from.x) * e;
  const y = from.y + (to.y - from.y) * e;
  const alpha = clamp(travel * 3) * (1 - span(lineLocal, 1.6, 1.9));
  if (alpha <= 0) return;
  if (lineLocal >= press && lineLocal <= press + 0.5) {
    clickRing(ctx, to.x, to.y, span(lineLocal, press, press + 0.5), {
      colour: UI.green, radius: 110,
    });
  }
  // 2x the old size. The reference's pointer is about 4.5 % of frame width,
  // which on this canvas is 170 design units - it is a character, not a speck.
  cursor(ctx, x, y, {
    alpha,
    press: clamp(1 - Math.abs(lineLocal - press) / 0.12),
    scale: 2.2,
  });
}

/**
 * The rail, and the product card when the line calls for it.
 *
 * The card is a shot, not furniture: on the lines that are *about* the product
 * it covers the frame (scene and rail included) and back again. On every other
 * line the frame belongs to the scene and to the rail. That is the difference
 * the reference film made plain - a UI demo shows the interface when it is the
 * subject, and shows type when the type is the subject. It never parks the
 * product in a corner and animates it at 23 px.
 */
export function secondUnit(ctx, {
  scene, t, local, pointer = true, h = 2160, rail = true, palette = 'dark', card = null,
}) {
  const lineIndex = scene.lines.reduce((count, line) => (line.start <= t ? count + 1 : count), 0) - 1;
  const current = scene.lines[Math.max(0, lineIndex)];
  const lineLocal = current ? t - current.start : 0;
  const index = Math.max(0, lineIndex);
  const view = buildView(ctx, { kind: scene.kind, lineIndex: index, lineLocal, t, h, palette, forceCard: card });

  if (view) {
    // Card beat: the rail would be half-covered by the card, so it stands down
    // and the card carries the beat on its own - rows arriving, typing, pointer.
    if (pointer) {
      const target = view.focus ?? view.search ?? (view.body ? { x: view.body.x + view.body.w * 0.6, y: view.body.y + 300, w: view.body.w * 0.4, h: 190 } : null);
      // The press cycle repeats inside a long card beat, so a card beat is never
      // a still frame: something is either travelling, pressing, or answering
      // for the whole of it.
      // Presses are placed where the card's own arrival schedule puts them, so
      // the pointer is always pressing the thing that is about to answer.
      const pressAt = (view.stage.late || []).filter((x) => x.row || x.focusRow !== undefined).map((x) => x.at);
      const cycle = pressAt.length
        ? (lineLocal < pressAt[0] ? lineLocal : pressAt.reduce((a, b) => (lineLocal >= b ? b : a), pressAt[0]) + (lineLocal % 0.4))
        : lineLocal % 2.6;
      purposefulPointer(ctx, {
        lineLocal: cycle,
        from: { x: CARD.x + CARD.w - 300, y: CARD.y + CARD.h - 120 },
        // A row is pressed at three-quarters across, so the pointer never sits on
        // the word it is pressing; the search field is pressed at its centre.
        to: target
          ? view.focus
            ? { x: target.x + target.w * 0.72, y: target.y + target.h * 0.55 }
            : { x: target.x + target.w * 0.5, y: target.y + target.h * 0.55 }
          : null,
      });
    }
    return;
  }

  // On the typographic stage there is no rail: the reference has nothing in its
  // frame but the words, and a black box in the corner would be one more thing
  // competing with them. The stage passes rail = false.
  if (rail) stepRail(ctx, { scene, t });
  void local;
}
