/**
 * A small UI kit for drawing interfaces in motion.
 *
 * Every "screenshot" in the film is drawn here: a browser window, a repository
 * page, a diff, a checks list, a chat panel. Nothing is captured, embedded or
 * licensed — an interface is rounded rectangles and text, which means it can be
 * animated at any resolution and can never be out of date with a screenshot.
 *
 * All units are design pixels at 3840x2160. The caller scales the context; the
 * kit never reads the canvas size.
 */

export const UI = {
  ink: '#0B0B0C',
  ink2: '#17171A',
  stage: '#D8D8DC',
  stage2: '#C6C6CC',
  window: '#FBFBFC',
  window2: '#F1F1F4',
  line: '#DCDCE2',
  line2: '#C4C4CD',
  text: '#17171A',
  dim: '#6B6B75',
  faint: '#9A9AA5',
  gold: '#F2C230',
  red: '#C4161C',
  green: '#2E9E5B',
  blue: '#2F6FEB',
  white: '#FFFFFF',
};

export const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
export const lerp = (a, b, t) => a + (b - a) * t;
export const span = (t, a, b) => clamp((t - a) / (b - a || 1));
export const ease = {
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  inCubic: (x) => x * x * x,
  outExpo: (x) => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
  inOutCubic: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outBack: (x) => (x <= 0 ? 0 : 1 + 2.2 * Math.pow(x - 1, 3) + 1.2 * Math.pow(x - 1, 2)),
  outQuint: (x) => 1 - Math.pow(1 - x, 5),
};

/** Deterministic hash noise — the film must render the same frame twice. */
export function noise(seed) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h - radius);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
  ctx.lineTo(x + radius, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

export function panel(ctx, { x, y, w, h, r = 28, fill = UI.window, stroke = UI.line, alpha = 1, shadow = 0 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha);
  if (shadow) {
    ctx.shadowColor = `rgba(8,8,12,${0.18 * shadow})`;
    ctx.shadowBlur = 60 * shadow;
    ctx.shadowOffsetY = 18 * shadow;
  }
  roundRect(ctx, x, y, w, h, r);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  ctx.shadowColor = 'rgba(0,0,0,0)';
  if (stroke) {
    ctx.lineWidth = 3;
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
  ctx.restore();
}

/** Text with tracking, because a UI at 4K needs air between letters. */
export function text(ctx, value, x, y, opts = {}) {
  const {
    size = 44, weight = 600, family = 'Inter', color = UI.text,
    align = 'left', alpha = 1, tracking = 0, baseline = 'alphabetic', maxWidth = null,
  } = opts;
  ctx.save();
  // Multiply into whatever the caller set rather than replacing it. Replacing
  // it meant a block of `ctx.globalAlpha = p` around a group of labels faded the
  // panels and left the type fully solid, which is how half the film's fades
  // were quietly doing nothing.
  ctx.globalAlpha = ctx.globalAlpha * alpha;
  ctx.font = `${weight} ${size}px "${family}"`;
  ctx.fillStyle = color;
  ctx.textBaseline = baseline;
  if (!tracking) {
    ctx.textAlign = align;
    if (maxWidth) ctx.fillText(value, x, y, maxWidth);
    else ctx.fillText(value, x, y);
    ctx.restore();
    return ctx.measureText(value).width;
  }
  // Manual tracking: canvas has no letter-spacing, so each glyph is placed.
  const chars = [...value];
  const widths = chars.map((c) => ctx.measureText(c).width);
  const total = widths.reduce((a, b) => a + b, 0) + tracking * (chars.length - 1);
  let cursor = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
  ctx.textAlign = 'left';
  chars.forEach((c, i) => {
    ctx.fillText(c, cursor, y);
    cursor += widths[i] + tracking;
  });
  ctx.restore();
  return total;
}

/** Width of a string in a given style, without leaving the context changed. */
export function measure(ctx, value, { size = 44, weight = 600, family = 'Inter', tracking = 0 } = {}) {
  ctx.save();
  ctx.font = `${weight} ${size}px "${family}"`;
  const chars = [...String(value)];
  const width = chars.reduce((total, c) => total + ctx.measureText(c).width, 0)
    + tracking * Math.max(0, chars.length - 1);
  ctx.restore();
  return width;
}

/** Words revealed one at a time; used by every statement and title. */
export function wordsIn(ctx, value, x, y, opts = {}) {
  const {
    size = 120, weight = 700, family = 'Space Grotesk', color = UI.text,
    progress = 1, stagger = 0.08, rise = 40, align = 'left', lineHeight = size * 1.12,
    alpha = 1, tracking = 0,
  } = opts;
  const lines = String(value).split('\n');
  let index = 0;
  lines.forEach((line, li) => {
    const words = line.split(' ');
    let width = 0;
    ctx.save();
    ctx.font = `${weight} ${size}px "${family}"`;
    const measured = words.map((w) => ctx.measureText(w).width + (tracking ? tracking * w.length : 0));
    width = measured.reduce((a, b) => a + b, 0) + size * 0.26 * (words.length - 1);
    let cursor = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    words.forEach((word, wi) => {
      const p = clamp((progress - (index * stagger)) / 0.55);
      const e = ease.outExpo(p);
      ctx.globalAlpha = ctx.globalAlpha * (alpha * clamp(p * 2.2));
      text(ctx, word, cursor, y + li * lineHeight + (1 - e) * rise, {
        size, weight, family, color: opts.colorFor ? opts.colorFor(index) : color, tracking,
      });
      cursor += measured[wi] + size * 0.26;
      index += 1;
    });
    ctx.restore();
  });
  return index;
}

/**
 * A browser window: chrome, tab, address pill, and a content rectangle.
 * Returns the content box so a caller can draw the page inside it.
 */
export function browser(ctx, {
  x, y, w, h, url = 'github.com', alpha = 1, scaleIn = 1, title = '', dark = false,
}) {
  const outer = { x, y, w, h };
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha);
  ctx.translate(x + w / 2, y + h / 2);
  ctx.scale(scaleIn, scaleIn);
  ctx.translate(-(x + w / 2), -(y + h / 2));

  panel(ctx, { w, h, x, y, r: 34, fill: dark ? '#141418' : UI.window, stroke: dark ? '#2A2A31' : UI.line, shadow: 1 });

  const barH = 92;
  ctx.save();
  roundRect(ctx, x, y, w, h, 34);
  ctx.clip();
  ctx.fillStyle = dark ? '#1B1B20' : '#EFEFF3';
  ctx.fillRect(x, y, w, barH);

  // window buttons
  const dots = ['#FF5F57', '#FEBC2E', '#28C840'];
  dots.forEach((colour, i) => {
    ctx.beginPath();
    ctx.arc(x + 52 + i * 34, y + barH / 2, 11, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.globalAlpha = ctx.globalAlpha * (alpha * 0.9);
    ctx.fill();
  });
  ctx.globalAlpha = ctx.globalAlpha * (alpha);

  // tab
  const tabW = Math.min(w * 0.34, 720);
  panel(ctx, {
    x: x + 176, y: y + 16, w: tabW, h: barH - 24, r: 16,
    fill: dark ? '#2A2A31' : UI.white, stroke: null,
  });
  text(ctx, title || url, x + 200, y + barH / 2 + 2, {
    size: 30, weight: 600, color: dark ? '#DADAe0' : UI.dim, maxWidth: tabW - 60,
  });

  // address pill
  const pillX = x + 176 + tabW + 28;
  const pillW = w - (pillX - x) - 48;
  panel(ctx, {
    x: pillX, y: y + 18, w: pillW, h: barH - 28, r: 999,
    fill: dark ? '#101014' : UI.white, stroke: dark ? '#2A2A31' : UI.line,
  });
  // a small lock, drawn not typed: a text glyph would fall back to a box
  ctx.strokeStyle = UI.faint;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(pillX + 46, y + 48, 10, Math.PI, 0);
  ctx.stroke();
  ctx.beginPath();
  ctx.roundRect ? ctx.roundRect(pillX + 36, y + 47, 20, 17, 4) : ctx.rect(pillX + 36, y + 47, 20, 17);
  ctx.stroke();
  text(ctx, url, pillX + 74, y + barH / 2 + 2, {
    size: 30, weight: 500, color: dark ? '#B9B9C4' : '#4A4A55', maxWidth: pillW - 120,
  });
  ctx.restore();

  ctx.restore();
  // The content box, and only the content box. Spreading the outer rectangle in
  // after it silently replaced y with the window's own top, so every page drew
  // over its own tab bar and address pill.
  return {
    ...outer,
    x: x + 6, y: y + barH + 6, w: w - 12, h: h - barH - 12,
    window: outer,
  };
}

/** A pointer, so a click can be shown rather than described. */
export function cursor(ctx, x, y, { alpha = 1, press = 0, scale = 1 } = {}) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha);
  ctx.translate(x, y);
  ctx.scale(scale * (1 - press * 0.12), scale * (1 - press * 0.12));
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(0, 62);
  ctx.lineTo(16, 47);
  ctx.lineTo(28, 70);
  ctx.lineTo(42, 63);
  ctx.lineTo(30, 41);
  ctx.lineTo(51, 40);
  ctx.closePath();
  ctx.fillStyle = UI.white;
  ctx.fill();
  ctx.lineWidth = 4;
  ctx.strokeStyle = UI.ink;
  ctx.stroke();
  ctx.restore();
}

/** A click ring, expanding from a point. */
export function clickRing(ctx, x, y, progress, { colour = UI.gold, radius = 90 } = {}) {
  if (progress <= 0 || progress >= 1) return;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * ((1 - progress) * 0.9);
  ctx.strokeStyle = colour;
  ctx.lineWidth = 8 * (1 - progress) + 2;
  ctx.beginPath();
  ctx.arc(x, y, radius * ease.outQuint(progress), 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

/**
 * A code block with a typewriter reveal.
 *
 * `lines` are plain strings; a leading `+` or `-` marks a diff line. Syntax
 * colouring is deliberately absent: this is a teaching film, and a viewer needs
 * to read the words, not admire a theme.
 */
export function codeBlock(ctx, lines, {
  x, y, size = 38, lineHeight = 62, progress = 1, colour = UI.text, dim = UI.faint,
  gutter = true, numberFrom = 1,
}) {
  const shown = progress * lines.length;
  lines.forEach((line, i) => {
    if (i > shown) return;
    const partial = clamp(shown - i);
    const value = partial >= 1 ? line : line.slice(0, Math.ceil(line.length * partial));
    const yy = y + i * lineHeight;
    if (gutter) {
      text(ctx, String(numberFrom + i), x - 34, yy, { size: size * 0.8, color: dim, align: 'right', weight: 500 });
    }
    text(ctx, value, x, yy, { size, weight: 500, color: colour, family: 'Inter' });
  });
  return y + Math.min(lines.length, Math.ceil(shown)) * lineHeight;
}

/** One row of a pull-request check list. */
export function checkRow(ctx, { x, y, w, name, state = 'pending', progress = 1, detail = '' }) {
  const colour = state === 'pass' ? UI.green : state === 'fail' ? UI.red : UI.faint;
  const cy = y + 34;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (progress);
  // icon: a tick, a cross, or a spinner
  ctx.beginPath();
  ctx.arc(x + 26, cy, 24, 0, Math.PI * 2);
  if (state === 'pending') {
    ctx.strokeStyle = colour;
    ctx.lineWidth = 6;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x + 26, cy, 24, -Math.PI / 2, -Math.PI / 2 + (progress % 1) * Math.PI * 1.4);
    ctx.strokeStyle = UI.ink;
    ctx.stroke();
  } else {
    ctx.fillStyle = colour;
    ctx.fill();
    ctx.strokeStyle = UI.white;
    ctx.lineWidth = 7;
    ctx.lineCap = 'round';
    ctx.beginPath();
    if (state === 'pass') {
      ctx.moveTo(x + 14, cy + 1);
      ctx.lineTo(x + 23, cy + 11);
      ctx.lineTo(x + 39, cy - 11);
    } else {
      ctx.moveTo(x + 16, cy - 10);
      ctx.lineTo(x + 36, cy + 10);
      ctx.moveTo(x + 36, cy - 10);
      ctx.lineTo(x + 16, cy + 10);
    }
    ctx.stroke();
  }
  text(ctx, name, x + 74, cy + 10, { size: 38, weight: 600, color: UI.text, maxWidth: w - 320 });
  if (detail) {
    text(ctx, detail, x + w - 24, cy + 10, { size: 32, weight: 500, color: UI.dim, align: 'right' });
  }
  ctx.restore();
}

/** A label chip: the small caps pill used for steps and states. */
export function chip(ctx, value, { x, y, colour = UI.ink, fill = null, size = 30, alpha = 1, pad = 22 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha);
  ctx.font = `700 ${size}px "Inter"`;
  const w = ctx.measureText(value).width + pad * 2;
  const h = size * 2.1;
  if (fill) {
    roundRect(ctx, x, y, w, h, h / 2);
    ctx.fillStyle = fill;
    ctx.fill();
  }
  text(ctx, value, x + w / 2, y + h / 2 + size * 0.36, {
    size, weight: 700, color: colour, align: 'center', tracking: size * 0.06,
  });
  ctx.restore();
  return w;
}

/** A thin rule that draws on. */
export function rule(ctx, x, y, w, { progress = 1, colour = UI.gold, thickness = 6, alpha = 1 } = {}) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha);
  ctx.fillStyle = colour;
  ctx.fillRect(x, y, w * clamp(progress), thickness);
  ctx.restore();
}

/**
 * The reference film's signature: a crescent slash that whips across the frame.
 *
 * Two arcs, thin and thicker, sweeping along an angle. Used on impacts and
 * chapter changes, never on a still — a slash is a movement, not a decoration.
 */
export function slash(ctx, { x, y, length = 1400, angle = -0.35, progress = 0, width = 26, colour = UI.white, alpha = 1 }) {
  if (progress <= 0 || progress >= 1) return;
  const grow = ease.outQuint(clamp(progress * 1.6));
  const fade = 1 - clamp((progress - 0.55) / 0.45);
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha * fade);
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.beginPath();
  ctx.moveTo(-length / 2 * grow, 0);
  ctx.quadraticCurveTo(0, -length * 0.10, length / 2 * grow, -length * 0.03);
  ctx.strokeStyle = colour;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(-length / 2 * grow, width * 1.6);
  ctx.quadraticCurveTo(0, -length * 0.10 + width * 1.6, length / 2 * grow, -length * 0.03 + width * 1.2);
  ctx.lineWidth = width * 0.34;
  ctx.stroke();
  ctx.restore();
}

/** Speed lines behind a subject: the frame's own velocity. */
export function speedLines(ctx, { x, y, w, h, progress = 1, count = 22, colour = UI.ink, alpha = 0.22, angle = 0 }) {
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha * clamp(progress));
  ctx.translate(x, y);
  ctx.rotate(angle);
  for (let i = 0; i < count; i += 1) {
    const n = noise(i * 3.7 + 1);
    const yy = (n - 0.5) * h;
    const len = w * (0.25 + noise(i * 7.1) * 0.7);
    const xx = (noise(i * 11.3) - 0.5) * w * 0.6 - len * clamp(progress);
    ctx.fillStyle = colour;
    ctx.fillRect(xx, yy, len, 3 + noise(i * 5.5) * 5);
  }
  ctx.restore();
}

/** Shards flying out from an impact point. */
export function shards(ctx, { x, y, progress = 0, count = 12, radius = 700, colour = UI.ink, alpha = 1 }) {
  if (progress <= 0 || progress >= 1) return;
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (alpha * (1 - progress) ** 1.4);
  for (let i = 0; i < count; i += 1) {
    const angle = (i / count) * Math.PI * 2 + noise(i) * 0.6;
    const dist = radius * ease.outQuint(progress) * (0.5 + noise(i * 3.3) * 0.8);
    const size = 18 + noise(i * 9.1) * 46;
    ctx.save();
    ctx.translate(x + Math.cos(angle) * dist, y + Math.sin(angle) * dist);
    ctx.rotate(angle + noise(i * 2.2) * 2);
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(size, size * 0.28);
    ctx.lineTo(size * 0.4, size * 0.7);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
  ctx.restore();
}

/** The reference's rainbow streak, used exactly once, at the end. */
export function rainbowStreak(ctx, { x, y, w, h, progress = 0 }) {
  if (progress <= 0 || progress >= 1) return;
  const colours = ['#FF3B30', '#FF9500', '#F2C230', '#34C759', '#2F6FEB', '#AF52DE'];
  ctx.save();
  ctx.globalAlpha = ctx.globalAlpha * (0.9 * (1 - Math.abs(progress - 0.5) * 1.2));
  ctx.translate(x, y);
  ctx.rotate(-0.22);
  colours.forEach((colour, i) => {
    ctx.beginPath();
    ctx.moveTo(-w / 2, (i - 2.5) * h * 0.16);
    ctx.quadraticCurveTo(0, (i - 2.5) * h * 0.16 - h * 0.5 * progress, w / 2, (i - 2.5) * h * 0.1);
    ctx.strokeStyle = colour;
    ctx.lineWidth = h * 0.09;
    ctx.lineCap = 'round';
    ctx.stroke();
  });
  ctx.restore();
}
