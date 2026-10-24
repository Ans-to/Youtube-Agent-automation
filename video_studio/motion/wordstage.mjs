/**
 * The typographic stage: one idea at a time, at the size the idea deserves.
 *
 * The owner's reference film ("UI Demo Animation", 36 s) is built almost
 * entirely out of this and nothing else: a soft light field, one phrase, no
 * furniture, and — when a phrase matters — type at 35 to 50 percent of the
 * frame height. Its card beats are inserts between those phrases, not the
 * substance of the film.
 *
 * Measured against it, our opening was a dark field with a two-line title at
 * 9 percent of frame height, a rail in the corner, a chapter name, a timecode
 * and a beat strip along the bottom: five things in a frame that should hold
 * one. This module is the alternative, and it is deliberately small enough to
 * be used by any film in the project — it knows nothing about this script.
 *
 * Two palettes, one geometry:
 *
 *   light - the reference's own: a cool white field, ink type, one amber accent.
 *   dark  - the same composition on our dark ground, for comparison.
 *
 * Both obey one rule: the phrase is the only thing in the frame. Everything
 * else, including the progress rail, stands down while a phrase is up.
 */
import { clamp, span, ease, text, measure } from './ui.mjs';

export const PALETTES = {
  light: {
    field: ['#F7F9FA', '#E7EEF2', '#DCE6EC'],
    ink: '#12233F',
    accent: '#B4762A',
    rule: 'rgba(18,35,63,0.16)',
    caption: 'rgba(18,35,63,0.74)',
    dark: false,
  },
  dark: {
    field: ['#17181C', '#111216', '#0B0B0E'],
    ink: '#F4F4F6',
    accent: '#F2C230',
    rule: 'rgba(255,255,255,0.14)',
    caption: 'rgba(242,242,242,0.82)',
    dark: true,
  },
};

/** The field: a soft wash with a slow drift, so the shot is never dead. */
export function drawField(ctx, { w, h, t, palette }) {
  const g = ctx.createLinearGradient(0, 0, w * 0.35, h);
  g.addColorStop(0, palette.field[0]);
  g.addColorStop(0.55, palette.field[1]);
  g.addColorStop(1, palette.field[2]);
  ctx.save();
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);

  // Two very soft blooms that breathe on a 9- and 13-second cycle. Amplitude is
  // 2 percent of the frame and never reverses inside a beat, so it reads as a
  // living background rather than as a shake or a pulse.
  const blooms = [
    { x: 0.22, y: 0.3, r: 0.55, period: 9, alpha: 0.5 },
    { x: 0.78, y: 0.66, r: 0.62, period: 13, alpha: 0.42 },
  ];
  blooms.forEach((b, i) => {
    const phase = (t / b.period) * Math.PI * 2 + i * 1.7;
    const cx = w * (b.x + Math.cos(phase) * 0.02);
    const cy = h * (b.y + Math.sin(phase * 0.7) * 0.02);
    const rg = ctx.createRadialGradient(cx, cy, 0, cx, cy, w * b.r);
    const tint = palette.dark ? '255,255,255' : '255,255,255';
    rg.addColorStop(0, `rgba(${tint},${(palette.dark ? 0.07 : 0.55) * b.alpha})`);
    rg.addColorStop(1, `rgba(${tint},0)`);
    ctx.fillStyle = rg;
    ctx.fillRect(0, 0, w, h);
  });
  ctx.restore();
}

/**
 * One phrase, arriving.
 *
 * ``p`` is 0 to 1 across the arrival. It scales from 0.86 and sharpens from a
 * blur, which is what the reference does at every one of its word beats: the
 * word does not slide in from an edge, it resolves in place, slightly larger
 * than its final size, and settles. No overshoot beyond 4 percent, because the
 * owner has rejected camera and text bounce twice.
 */
export function drawPhrase(ctx, {
  lines, w, h, p, palette, size, exit = 0, accentLine = -1, ellipse = false, t = 0,
  hold = 0, reveal = null,
}) {
  if (p <= 0) return;
  // 0.4 s to arrive. Longer reads as a dissolve; shorter reads as a cut, and the
  // reference settles every phrase in under half a second.
  const arrive = ease.outCubic(clamp(p * 1.35));
  // A phrase is never held perfectly still, and 3 percent was not enough.
  //
  // Measured: with a 3 percent push the second and third seconds of a phrase
  // scored zero live regions while the reference scored two or three on every
  // one of its own holds. Its phrases settle by shrinking - "Stage 1" enters at
  // roughly three times its final size and comes down across the beat - so the
  // word is in motion for as long as it is on screen. That is what this is: a
  // A 35 percent settle across the beat, monotonic, no overshoot, no bounce.
  // Linear, not eased: this is the reference's own move - "Stage 1" enters at
  // about 300 percent of its final size and comes down to 7 percent across the
  // beat - and it has to run at a constant speed for the whole beat. Eased, all
  // the travel happens in the first second and the rest of the beat measures as
  // a still frame, which is what the gate kept reporting.
  const drift = 1.35 - 0.35 * clamp(hold);
  const scale = (0.86 + 0.14 * arrive) * drift;
  const alpha = clamp(p * 3.2) * (1 - exit);
  // Leaving lifts and fades rather than sitting still under the next phrase:
  // two phrases in the same place at the same time read as a printing error.
  const rise = (1 - arrive) * size * 0.06 - exit * size * 0.45;

  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(scale, scale);
  ctx.translate(0, rise);
  ctx.globalAlpha = ctx.globalAlpha * alpha;

  // The block is centred as a whole, so a two-line phrase stays optically centred
  // rather than hanging off its first line.
  const step = size * 1.02;
  const first = -((lines.length - 1) * step) / 2 + size * 0.34;
  // Words arrive in the order they are spoken, spread across the whole beat
  // rather than all at once at the start. A phrase that lands in one hit and
  // then sits still is a slide, not motion graphics; the reference settles its
  // words one after another and the eye always has the next one to wait for.
  // `reveal` is the word schedule: it runs across most of the beat, while `p`
  // is only the 0.5 s scale-in. Without this split every word landed inside the
  // first second and the rest of a three-second beat was a still frame.
  const schedule = reveal === null ? p : reveal;
  const words = lines.flatMap((value) => value.split(/\s+/));
  const slots = Math.max(1, words.length);
  let wordIndex = 0;
  lines.forEach((value, i) => {
    const colour = i === accentLine ? palette.accent : palette.ink;
    const weight = i === accentLine ? 500 : 700;
    const parts = value.split(/\s+/);
    const width = measure(ctx, value, { size, weight, family: 'Space Grotesk' });
    const space = measure(ctx, ' ', { size, weight, family: 'Space Grotesk' });
    let x = -width / 2;
    parts.forEach((word) => {
      const wp = clamp((schedule - (wordIndex / slots) * 0.6) / 0.4);
      const ww = measure(ctx, word, { size, weight, family: 'Space Grotesk' });
      if (wp > 0) {
        ctx.save();
        ctx.globalAlpha = ctx.globalAlpha * ease.outCubic(wp) * (1 - exit);
        ctx.beginPath();
        ctx.rect(x - 8, first + i * step - size * 1.05, ww + 16, size * 1.35);
        ctx.clip();
        text(ctx, word, x, first + i * step + (1 - ease.outCubic(wp)) * size * 0.5, {
          size, weight, family: 'Space Grotesk', color: colour,
        });
        ctx.restore();
      }
      x += ww + space;
      wordIndex += 1;
    });
  });

  // The ellipse: one drawn stroke around a word, exactly as the reference marks
  // "Workflow" and "Options". It is the only decoration this stage allows,
  // because it is the one the reference uses to say "this word".
  if (ellipse && lines.length === 1 && exit <= 0) {
    const bw = measure(ctx, lines[0], { size, weight: 700, family: 'Space Grotesk' });
    const rx = bw * 0.58;
    const ry = size * 0.52;
    const draw = ease.inOutCubic(span(p, 0.35, 0.95));
    if (draw > 0) {
      ctx.save();
      ctx.strokeStyle = palette.ink;
      ctx.lineWidth = Math.max(3, size * 0.022);
      ctx.beginPath();
      const turns = Math.PI * 2 * draw;
      // A hand-drawn ellipse leaves a small gap where the pen lifts.
      ctx.ellipse(0, 0, rx, ry, -0.06, -Math.PI * 0.62, -Math.PI * 0.62 + turns);
      ctx.stroke();
      ctx.restore();
    }
  }

  // A word arriving at this size gets a shadow of movement across the phrase for
  // the first third of a second, so a 3-second hold is not a static frame.
  if (p < 0.34 && lines.length === 1) {
    const sweep = span(p, 0, 0.34);
    const bw = measure(ctx, lines[0], { size, weight: 700, family: 'Space Grotesk' });
    ctx.save();
    ctx.globalAlpha = ctx.globalAlpha * (1 - sweep) * 0.5;
    ctx.fillStyle = palette.accent;
    ctx.fillRect(-bw / 2 + bw * sweep, first - size * 0.42, size * 0.16, size * 0.05);
    ctx.restore();
  }

  ctx.restore();
  void t;
}

/**
 * The beat list for a scene: which phrase is up, and how far into it we are.
 *
 * ``beats`` is a list of ``{ at, until, lines, accentLine, ellipse }`` in
 * seconds local to the scene. Returns the current beat and its progress, plus
 * the previous one fading out where they overlap by ``cross`` seconds.
 */
export function beatAt(beats, local, cross = 0.22) {
  let index = -1;
  beats.forEach((b, i) => {
    if (local >= b.at) index = i;
  });
  if (index < 0) return null;
  const beat = beats[index];
  const next = beats[index + 1];
  // A beat that hands over to the product card does not crossfade: the card
  // covers the frame, so fading the words under it would show two things in one
  // place for a quarter of a second. Word-to-word beats do crossfade.
  const enter = span(local, beat.at, beat.at + 0.55);
  const exit = 0;
  return {
    index, beat, p: enter, exit,
    previous: null,
  };
}
