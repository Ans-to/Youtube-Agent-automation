/**
 * The other charts.
 *
 * A business film gets through bar, line and donut and then needs the ones that
 * carry an argument rather than a number: a heatmap for busy hours, a waterfall
 * for how a value got from A to B, a radar for a comparison of four things, a
 * Gantt for a plan, a bump chart for rank over time, a slope chart for two
 * dates, a box plot for a spread, a histogram for a distribution.
 *
 * All progress-driven, all deterministic, all pure functions of the box.
 */

import { clamp, noise } from '../ui.mjs';

const TAU = Math.PI * 2;

function frame(ctx, { x, y, w, h, ink }) {
  ctx.strokeStyle = ink;
  ctx.globalAlpha *= 0.28;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x + w, y + h);
  ctx.stroke();
  ctx.globalAlpha /= 0.28;
}

export const charts = {
  /** Heatmap: a grid that fills cell by cell, brighter as the value rises. */
  heatmap: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cols = 12;
    const rows = 6;
    const cw = w / cols;
    const ch = h / rows;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const i = r * cols + c;
        const appear = clamp((p * 1.7 - i / (cols * rows)) * 4);
        if (appear <= 0) continue;
        // A deterministic hill: busiest in the middle of the grid.
        const v = 0.12 + 0.88 * Math.exp(-(((c - cols * 0.55) ** 2) / 26 + ((r - rows * 0.4) ** 2) / 6));
        ctx.globalAlpha = appear * (0.12 + v * 0.78);
        ctx.fillStyle = accent;
        ctx.fillRect(x + c * cw + cw * 0.06, y + r * ch + ch * 0.06, cw * 0.88, ch * 0.88);
      }
    }
    ctx.globalAlpha = 1;
  },

  /** Waterfall: how a number got from where it started to where it ended. */
  waterfall: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const steps = [0.55, 0.18, -0.12, 0.10, -0.26, 0.15, -0.20];
    const bw = (w * 0.86) / steps.length;
    let level = 0.18;
    frame(ctx, { x, y, w, h, ink });
    steps.forEach((s, i) => {
      const k = clamp((p - i * 0.10) * 3);
      if (k <= 0) return;
      const from = level;
      const to = level + s;
      const top = 1 - Math.max(from, to);
      const height = Math.abs(s) * k;
      ctx.fillStyle = s >= 0 ? accent : ink;
      ctx.globalAlpha = 0.75 * k;
      ctx.fillRect(x + w * 0.07 + i * bw + bw * 0.12, y + h * (top + (Math.abs(s) - height)), bw * 0.76, h * height);
      ctx.globalAlpha = 1;
      // Connector to the next step.
      if (i < steps.length - 1) {
        ctx.strokeStyle = 'rgba(18,35,63,0.30)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x + w * 0.07 + i * bw + bw * 0.88, y + h * (1 - to));
        ctx.lineTo(x + w * 0.07 + (i + 1) * bw + bw * 0.12, y + h * (1 - to));
        ctx.stroke();
      }
      level = to;
    });
  },

  /** Radar: four axes, one shape, so a comparison reads at a glance. */
  radar: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const cy = y + h / 2;
    const r = Math.min(w, h) * 0.40;
    const axes = 5;
    // Grid.
    for (let ring = 1; ring <= 3; ring += 1) {
      ctx.beginPath();
      for (let i = 0; i <= axes; i += 1) {
        const a = (i / axes) * TAU - Math.PI / 2;
        const px = cx + Math.cos(a) * r * (ring / 3);
        const py = cy + Math.sin(a) * r * (ring / 3);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = 'rgba(18,35,63,0.16)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    for (let i = 0; i < axes; i += 1) {
      const a = (i / axes) * TAU - Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.strokeStyle = 'rgba(18,35,63,0.16)';
      ctx.stroke();
    }
    // The shape.
    const values = [0.86, 0.62, 0.74, 0.44, 0.70];
    ctx.beginPath();
    for (let i = 0; i <= axes; i += 1) {
      const idx = i % axes;
      const a = (idx / axes) * TAU - Math.PI / 2;
      const v = values[idx] * clamp(p * 1.3);
      const px = cx + Math.cos(a) * r * v;
      const py = cy + Math.sin(a) * r * v;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.28;
    ctx.fill();
    ctx.globalAlpha /= 0.28;
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1.4, r * 0.03);
    ctx.stroke();
  },

  /** Box plot: spread, median, and the two whiskers. */
  boxplot: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const groups = 4;
    const gw = w / groups;
    for (let i = 0; i < groups; i += 1) {
      const k = clamp((p - i * 0.12) * 3);
      if (k <= 0) continue;
      const seed = noise(i * 7.3 + 1);
      const lo = 0.22 + seed * 0.10;
      const hi = 0.68 + seed * 0.18;
      const q1 = lo + (hi - lo) * 0.28;
      const q3 = lo + (hi - lo) * 0.76;
      const med = lo + (hi - lo) * (0.42 + seed * 0.2);
      const cx = x + gw * (i + 0.5);
      const bw = gw * 0.34;
      const Y = (v) => y + h * (1 - v);
      ctx.strokeStyle = ink;
      ctx.lineWidth = Math.max(1.2, w * 0.004);
      ctx.globalAlpha = k;
      // Whiskers.
      ctx.beginPath();
      ctx.moveTo(cx, Y(lo));
      ctx.lineTo(cx, Y(hi));
      ctx.moveTo(cx - bw * 0.4, Y(lo));
      ctx.lineTo(cx + bw * 0.4, Y(lo));
      ctx.moveTo(cx - bw * 0.4, Y(hi));
      ctx.lineTo(cx + bw * 0.4, Y(hi));
      ctx.stroke();
      // Box.
      ctx.fillStyle = accent;
      ctx.globalAlpha = 0.22 * k;
      ctx.fillRect(cx - bw / 2, Y(q3), bw, Y(q1) - Y(q3));
      ctx.globalAlpha = k;
      ctx.strokeStyle = ink;
      ctx.strokeRect(cx - bw / 2, Y(q3), bw, Y(q1) - Y(q3));
      // Median.
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(2, w * 0.008);
      ctx.beginPath();
      ctx.moveTo(cx - bw / 2, Y(med));
      ctx.lineTo(cx + bw / 2, Y(med));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /** Histogram: a distribution, bars growing together. */
  histogram: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const bars = 14;
    const bw = w / bars;
    frame(ctx, { x, y, w, h, ink });
    for (let i = 0; i < bars; i += 1) {
      const centre = bars * 0.52;
      const v = Math.exp(-(((i - centre) ** 2) / (2 * (bars * 0.20) ** 2)));
      const k = clamp((p * 1.6 - i * 0.02) * 2);
      if (k <= 0) continue;
      const bh = h * (0.10 + v * 0.84) * k;
      ctx.fillStyle = i % 4 === 0 ? accent : ink;
      ctx.globalAlpha = i % 4 === 0 ? 0.85 : 0.55;
      ctx.fillRect(x + i * bw + bw * 0.10, y + h - bh, bw * 0.80, bh);
    }
    ctx.globalAlpha = 1;
  },

  /** Gantt: the plan, bars arriving in reading order. */
  gantt: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const rows = 6;
    const rh = h / rows;
    const starts = [0.05, 0.22, 0.30, 0.52, 0.60, 0.74];
    const spans = [0.30, 0.26, 0.34, 0.22, 0.30, 0.22];
    ctx.strokeStyle = 'rgba(18,35,63,0.10)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i += 1) {
      ctx.beginPath();
      ctx.moveTo(x + (w * i) / 4, y);
      ctx.lineTo(x + (w * i) / 4, y + h);
      ctx.stroke();
    }
    for (let r = 0; r < rows; r += 1) {
      const k = clamp((p - r * 0.09) * 3);
      if (k <= 0) continue;
      const bh = rh * 0.44;
      const bx = x + w * starts[r];
      const full = w * spans[r];
      ctx.fillStyle = r % 2 ? accent : ink;
      ctx.globalAlpha = (r % 2 ? 0.85 : 0.55) * k;
      ctx.fillRect(bx, y + r * rh + rh * 0.28, full * k, bh);
    }
    ctx.globalAlpha = 1;
  },

  /** Bump chart: rank over six periods, lines crossing without a legend. */
  bump: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const periods = 6;
    const series = 3;
    const ranks = [[0, 1, 1, 2, 1, 0], [1, 0, 2, 1, 0, 1], [2, 2, 0, 0, 2, 2]];
    const px = (i) => x + (i / (periods - 1)) * w;
    const py = (r) => y + (r / (series - 1)) * (h * 0.84);
    const colours = [ink, accent, 'rgba(18,35,63,0.45)'];
    for (let s = 0; s < series; s += 1) {
      const k = clamp(p * 1.2);
      ctx.strokeStyle = colours[s];
      ctx.lineWidth = s === 1 ? Math.max(2.4, w * 0.008) : Math.max(1.6, w * 0.005);
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      for (let i = 0; i <= (periods - 1) * k; i += 1) {
        const idx = Math.min(periods - 1, Math.floor(i));
        const frac = i - idx;
        const next = Math.min(periods - 1, idx + 1);
        const r = ranks[s][idx] + (ranks[s][next] - ranks[s][idx]) * frac;
        if (i === 0) ctx.moveTo(px(idx), py(r));
        else ctx.lineTo(px(i), py(r));
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    for (let s = 0; s < series; s += 1) {
      for (let i = 0; i < periods; i += 1) {
        const k = clamp((p * 1.6 - i / periods) * 3);
        if (k <= 0) continue;
        ctx.fillStyle = colours[s];
        ctx.beginPath();
        ctx.arc(px(i), py(ranks[s][i]), Math.max(2.4, w * 0.009) * k, 0, TAU);
        ctx.fill();
      }
    }
  },

  /** Slope chart: two dates, one line per subject, the whole story in the tilt. */
  slope: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const left = [[0.80, 0.62], [0.46, 0.30], [0.22, 0.72]];
    const x0 = x + w * 0.16;
    const x1 = x + w * 0.84;
    const Y = (v) => y + h * (1 - v);
    ctx.strokeStyle = 'rgba(18,35,63,0.14)';
    ctx.lineWidth = 1;
    [x0, x1].forEach((xx) => {
      ctx.beginPath();
      ctx.moveTo(xx, y + h * 0.04);
      ctx.lineTo(xx, y + h * 0.96);
      ctx.stroke();
    });
    left.forEach(([a, b], i) => {
      const k = clamp((p - i * 0.10) * 2.4);
      if (k <= 0) return;
      const colour = b > a ? accent : ink;
      ctx.strokeStyle = colour;
      ctx.lineWidth = Math.max(1.8, w * 0.006);
      ctx.beginPath();
      ctx.moveTo(x0, Y(a));
      ctx.lineTo(x0 + (x1 - x0) * k, Y(a + (b - a) * k));
      ctx.stroke();
      ctx.fillStyle = colour;
      [[x0, a], [x0 + (x1 - x0) * k, a + (b - a) * k]].forEach(([xx, v]) => {
        ctx.beginPath();
        ctx.arc(xx, Y(v), Math.max(2.6, w * 0.010), 0, TAU);
        ctx.fill();
      });
    });
  },
};

export const CHART_IDS = Object.keys(charts);
export default charts;
