/**
 * Props: the objects a documentary points at.
 *
 * The first pass had a factory, a tower and a phone, which is the Nokia script
 * and nothing else. A health film needs a hospital corridor; a finance film
 * needs a contract and a banknote; a space film needs a rocket. This family is
 * the rest of the world's furniture.
 *
 * Same contract as every other shape: a box, a progress value, ink and accent.
 * Nothing here knows about timing.
 */

import { clamp } from '../ui.mjs';

const TAU = Math.PI * 2;

function box(ctx, x, y, w, h, r = 0) {
  ctx.beginPath();
  if (r > 0) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
    ctx.lineTo(x + rr, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
    ctx.lineTo(x, y + rr);
    ctx.quadraticCurveTo(x, y, x + rr, y);
    ctx.closePath();
  } else {
    ctx.rect(x, y, w, h);
  }
}

function lines(ctx, x, y, w, count, gap, colour, width, grow = 1) {
  ctx.fillStyle = colour;
  for (let i = 0; i < count; i += 1) {
    const len = w * (i % 3 === 2 ? 0.62 : 1) * grow;
    ctx.fillRect(x, y + i * gap, len, width);
  }
}

/** A person at a given height: head, shoulders, body. Used by crowd and scenes. */
function figure(ctx, cx, baseY, height, colour, widthScale = 1) {
  const head = height * 0.20;
  ctx.fillStyle = colour;
  ctx.beginPath();
  ctx.arc(cx, baseY - height + head, head * 0.62, 0, TAU);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(cx - height * 0.19 * widthScale, baseY);
  ctx.lineTo(cx - height * 0.15 * widthScale, baseY - height * 0.66);
  ctx.quadraticCurveTo(cx, baseY - height * 0.84, cx + height * 0.15 * widthScale, baseY - height * 0.66);
  ctx.lineTo(cx + height * 0.19 * widthScale, baseY);
  ctx.closePath();
  ctx.fill();
}

export const props = {
  /** A page of paper: the contract, the report, the patent. */
  document: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const pw = Math.min(w * 0.72, h * 0.7);
    const ph = pw * 1.34;
    const px = x + (w - pw) / 2;
    const py = y + (h - ph) / 2;
    ctx.save();
    ctx.translate(px + pw, py + ph);
    ctx.rotate(-0.04);
    ctx.translate(-(px + pw), -(py + ph));
    box(ctx, px, py, pw, ph, pw * 0.02);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.globalAlpha *= 0.35;
    ctx.lineWidth = Math.max(1, pw * 0.008);
    ctx.stroke();
    ctx.globalAlpha = 1;
    const pad = pw * 0.13;
    lines(ctx, px + pad, py + ph * 0.18, pw - pad * 2, 3, ph * 0.065, ink, ph * 0.012, clamp(p * 1.6));
    lines(ctx, px + pad, py + ph * 0.44, pw - pad * 2, 4, ph * 0.055, 'rgba(18,35,63,0.45)', ph * 0.010, clamp(p * 2 - 0.4));
    // A stamp, near the foot, as the thing that makes it official.
    if (p > 0.55) {
      const k = clamp((p - 0.55) / 0.25);
      ctx.globalAlpha = k;
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(1.5, pw * 0.022);
      ctx.beginPath();
      ctx.arc(px + pw * 0.68, py + ph * 0.82, pw * 0.13, 0, TAU);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(px + pw * 0.62, py + ph * 0.82);
      ctx.lineTo(px + pw * 0.67, py + ph * 0.86);
      ctx.lineTo(px + pw * 0.75, py + ph * 0.77);
      ctx.stroke();
    }
    ctx.restore();
  },

  /** A laid table with a lamp: the interior that says "office at night". */
  desk: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const top = y + h * 0.60;
    const left = x + w * 0.12;
    const right = x + w * 0.88;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, h * 0.016);
    ctx.beginPath();
    ctx.moveTo(left, top);
    ctx.lineTo(right, top);
    ctx.stroke();
    ctx.lineWidth = Math.max(1.5, h * 0.010);
    ctx.beginPath();
    ctx.moveTo(left + w * 0.04, top);
    ctx.lineTo(left + w * 0.04, y + h);
    ctx.moveTo(right - w * 0.04, top);
    ctx.lineTo(right - w * 0.04, y + h);
    ctx.stroke();
    // Lamp: a stem and a cone of light on the table.
    const lx = x + w * 0.24;
    ctx.beginPath();
    ctx.moveTo(lx, top);
    ctx.lineTo(lx, y + h * 0.20);
    ctx.lineTo(lx + w * 0.10, y + h * 0.13);
    ctx.stroke();
    const glow = ctx.createRadialGradient(lx, top, 2, lx, top, w * 0.26);
    glow.addColorStop(0, `rgba(180,118,42,${0.20 * clamp(p * 1.4)})`);
    glow.addColorStop(1, 'rgba(180,118,42,0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.moveTo(lx + w * 0.10, y + h * 0.13);
    ctx.lineTo(lx + w * 0.20, top);
    ctx.lineTo(lx - w * 0.04, top);
    ctx.closePath();
    ctx.fill();
    // A laptop, closed, and a cup: two props are enough to read as a desk.
    box(ctx, x + w * 0.46, top - h * 0.10, w * 0.20, h * 0.10, h * 0.01);
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.18 * clamp(p * 1.5);
    ctx.fill();
    ctx.globalAlpha /= Math.max(0.001, 0.18 * clamp(p * 1.5));
    ctx.strokeStyle = accent;
    ctx.beginPath();
    ctx.arc(x + w * 0.76, top - h * 0.05, h * 0.05, Math.PI, TAU);
    ctx.stroke();
  },

  /** An envelope: the letter, the offer, the memo. */
  envelope: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const ew = Math.min(w * 0.78, h * 1.5);
    const eh = ew * 0.66;
    const ex = x + (w - ew) / 2;
    const ey = y + (h - eh) / 2;
    box(ctx, ex, ey, ew, eh, ew * 0.03);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, eh * 0.03);
    ctx.stroke();
    // The flap, drawn open as p rises.
    const k = clamp(p * 1.4);
    ctx.beginPath();
    ctx.moveTo(ex, ey + eh);
    ctx.lineTo(ex + ew / 2, ey + eh * (0.42 + 0.5 * k));
    ctx.lineTo(ex + ew, ey + eh);
    ctx.stroke();
    // The letter rising out of it.
    if (p > 0.45) {
      const lift = (clamp((p - 0.45) / 0.4)) * eh * 0.5;
      ctx.fillStyle = '#FFFFFF';
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(1.2, eh * 0.02);
      box(ctx, ex + ew * 0.16, ey + eh * 0.30 - lift, ew * 0.68, eh * 0.5, ew * 0.01);
      ctx.fill();
      ctx.stroke();
      lines(ctx, ex + ew * 0.24, ey + eh * 0.44 - lift, ew * 0.5, 3, eh * 0.09, ink, eh * 0.022);
    }
  },

  /** A banknote: three bands and a value-disc, enough to read as money. */
  banknote: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const nw = Math.min(w * 0.82, h * 1.9);
    const nh = nw * 0.44;
    const nx = x + (w - nw) / 2;
    const ny = y + (h - nh) / 2;
    box(ctx, nx, ny, nw, nh, nh * 0.06);
    ctx.fillStyle = 'rgba(18,35,63,0.05)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, nh * 0.03);
    ctx.stroke();
    ctx.save();
    ctx.beginPath();
    ctx.rect(nx, ny, nw * clamp(p * 1.5), nh);
    ctx.clip();
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1, nh * 0.02);
    for (let i = 0; i < 6; i += 1) {
      ctx.beginPath();
      ctx.moveTo(nx + nw * (0.1 + i * 0.14), ny + nh * 0.15);
      ctx.lineTo(nx + nw * (0.05 + i * 0.14), ny + nh * 0.85);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(nx + nw * 0.72, ny + nh * 0.5, nh * 0.26, 0, TAU);
    ctx.stroke();
    ctx.restore();
  },

  /** A calendar: the deadline, the quarter, the release. */
  calendar: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cw = Math.min(w * 0.76, h * 0.86);
    const ch = cw * 1.06;
    const cx = x + (w - cw) / 2;
    const cy = y + (h - ch) / 2;
    box(ctx, cx, cy, cw, ch, cw * 0.04);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, cw * 0.012);
    ctx.stroke();
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.9;
    ctx.fillRect(cx, cy, cw, ch * 0.16);
    ctx.globalAlpha = 1;
    const cols = 4;
    const rows = 3;
    const gw = (cw * 0.86) / cols;
    const gh = (ch * 0.70) / rows;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const i = r * cols + c;
        const on = clamp((p - 0.2 - i * 0.05) * 4);
        if (on <= 0.02) continue;
        const last = i === cols * rows - 2;
        ctx.globalAlpha = on;
        ctx.fillStyle = last ? accent : 'rgba(18,35,63,0.16)';
        ctx.fillRect(cx + cw * 0.07 + c * gw, cy + ch * 0.24 + r * gh, gw * 0.62, gh * 0.6);
      }
    }
    ctx.globalAlpha = 1;
  },

  /** A newspaper: the front page, which is how a company gets old. */
  newspaper: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const pw = Math.min(w * 0.66, h * 0.72);
    const ph = pw * 1.3;
    const px = x + (w - pw) / 2;
    const py = y + (h - ph) / 2;
    box(ctx, px, py, pw, ph, pw * 0.01);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.globalAlpha *= 0.3;
    ctx.lineWidth = Math.max(1, pw * 0.006);
    ctx.stroke();
    ctx.globalAlpha = 1;
    // Masthead, rule, then columns.
    ctx.fillStyle = ink;
    ctx.fillRect(px + pw * 0.08, py + ph * 0.07, pw * 0.84 * clamp(p * 2), ph * 0.09);
    ctx.fillRect(px + pw * 0.08, py + ph * 0.19, pw * 0.84, Math.max(1, ph * 0.006));
    for (let c = 0; c < 2; c += 1) {
      lines(ctx, px + pw * (0.08 + c * 0.46), py + ph * 0.24, pw * 0.38, 9, ph * 0.045,
        'rgba(18,35,63,0.38)', ph * 0.008, clamp(p * 1.8 - c * 0.2));
    }
    // One photograph block, the accent of the page.
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.55 * clamp(p * 1.4 - 0.3);
    ctx.fillRect(px + pw * 0.08, py + ph * 0.70, pw * 0.38, ph * 0.22);
    ctx.globalAlpha = 1;
  },

  /** A television: the living room, the broadcast, the announcement. */
  tv: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const tw = Math.min(w * 0.84, h * 1.45);
    const th = tw * 0.62;
    const tx = x + (w - tw) / 2;
    const ty = y + (h - th) / 2;
    box(ctx, tx, ty, tw, th, tw * 0.05);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, tw * 0.014);
    ctx.stroke();
    // Screen, filling with signal.
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.10;
    ctx.fillRect(tx + tw * 0.07, ty + th * 0.10, tw * 0.86, th * 0.66);
    ctx.globalAlpha = 1;
    ctx.save();
    ctx.beginPath();
    ctx.rect(tx + tw * 0.07, ty + th * 0.10, tw * 0.86 * clamp(p * 1.6), th * 0.66);
    ctx.clip();
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1.4, tw * 0.012);
    ctx.beginPath();
    ctx.moveTo(tx + tw * 0.10, ty + th * 0.52);
    for (let i = 0; i <= 12; i += 1) {
      const xx = tx + tw * 0.10 + (i / 12) * tw * 0.80;
      const yy = ty + th * 0.52 + Math.sin(i * 0.9) * th * 0.12;
      ctx.lineTo(xx, yy);
    }
    ctx.stroke();
    ctx.restore();
    // Feet.
    ctx.strokeStyle = ink;
    ctx.beginPath();
    ctx.moveTo(tx + tw * 0.3, ty + th);
    ctx.lineTo(tx + tw * 0.24, ty + th * 1.10);
    ctx.moveTo(tx + tw * 0.7, ty + th);
    ctx.lineTo(tx + tw * 0.76, ty + th * 1.10);
    ctx.stroke();
  },

  /** An open laptop: the workspace, the engineer, the code. */
  laptop: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const lw = Math.min(w * 0.86, h * 1.7);
    const lh = lw * 0.60;
    const lx = x + (w - lw) / 2;
    const ly = y + (h - lh) / 2;
    // Lid.
    box(ctx, lx + lw * 0.08, ly, lw * 0.84, lh * 0.72, lw * 0.012);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, lw * 0.010);
    ctx.stroke();
    // Screen content.
    ctx.save();
    ctx.beginPath();
    ctx.rect(lx + lw * 0.12, ly + lh * 0.05, lw * 0.76 * clamp(p * 1.7), lh * 0.62);
    ctx.clip();
    ctx.fillStyle = accent;
    for (let r = 0; r < 4; r += 1) {
      for (let c = 0; c < 3; c += 1) {
        if ((r + c) % 3 === 0) continue;
        ctx.globalAlpha *= 0.55;
        ctx.fillRect(lx + lw * (0.15 + c * 0.13), ly + lh * (0.12 + r * 0.13), lw * 0.10, lh * 0.08);
        ctx.globalAlpha /= 0.55;
      }
    }
    ctx.restore();
    // Deck.
    ctx.beginPath();
    ctx.moveTo(lx, ly + lh * 0.78);
    ctx.lineTo(lx + lw, ly + lh * 0.78);
    ctx.lineTo(lx + lw * 0.94, ly + lh);
    ctx.lineTo(lx + lw * 0.06, ly + lh);
    ctx.closePath();
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.stroke();
  },

  /** A tablet: the meeting, the demo, the thing handed across a table. */
  tablet: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const tw = Math.min(w * 0.58, h * 0.46);
    const th = tw * 1.36;
    const tx = x + (w - tw) / 2;
    const ty = y + (h - th) / 2;
    box(ctx, tx, ty, tw, th, tw * 0.09);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, tw * 0.02);
    ctx.stroke();
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.08;
    box(ctx, tx + tw * 0.08, ty + th * 0.07, tw * 0.84, th * 0.86, tw * 0.06);
    ctx.fill();
    ctx.globalAlpha = 1;
    // A chart appearing on it.
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1.4, tw * 0.018);
    ctx.beginPath();
    ctx.moveTo(tx + tw * 0.20, ty + th * 0.66);
    const steps = 10;
    for (let i = 0; i <= steps * clamp(p * 1.4); i += 1) {
      ctx.lineTo(tx + tw * 0.20 + (i / steps) * tw * 0.60, ty + th * (0.66 - (i / steps) * 0.38));
    }
    ctx.stroke();
  },

  /** A watch: time, the wearable, the second screen. */
  watch: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.30;
    const cx = x + w / 2;
    const cy = y + h / 2;
    // Strap.
    ctx.fillStyle = ink;
    ctx.globalAlpha *= 0.16;
    ctx.fillRect(cx - r * 0.62, cy - r * 1.9, r * 1.24, r * 1.5);
    ctx.fillRect(cx - r * 0.62, cy + r * 0.4, r * 1.24, r * 1.5);
    ctx.globalAlpha = 1;
    box(ctx, cx - r, cy - r, r * 2, r * 2, r * 0.36);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, r * 0.09);
    ctx.stroke();
    // Face marks.
    ctx.strokeStyle = 'rgba(18,35,63,0.28)';
    ctx.lineWidth = Math.max(1, r * 0.05);
    for (let i = 0; i < 12; i += 1) {
      const a = (i / 12) * TAU;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r * 0.76, cy + Math.sin(a) * r * 0.76);
      ctx.lineTo(cx + Math.cos(a) * r * 0.86, cy + Math.sin(a) * r * 0.86);
      ctx.stroke();
    }
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1.8, r * 0.10);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx, cy - r * 0.5 * clamp(p * 1.3));
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + r * 0.38 * clamp(p * 1.3), cy);
    ctx.stroke();
  },

  /** A satellite: the coverage, the network in the sky. */
  satellite: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const s = Math.min(w, h) * 0.22;
    const cx = x + w / 2;
    const cy = y + h / 2;
    // Body.
    box(ctx, cx - s * 0.5, cy - s * 0.4, s, s * 0.8, s * 0.12);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, s * 0.08);
    ctx.stroke();
    // Panels.
    [-1, 1].forEach((side) => {
      const pw = s * 0.9 * clamp(p * 1.5);
      ctx.fillStyle = accent;
      ctx.globalAlpha *= 0.45;
      ctx.fillRect(cx + side * s * 0.55 + (side < 0 ? -pw : 0), cy - s * 0.26, pw, s * 0.52);
      ctx.globalAlpha /= 0.45;
      ctx.strokeStyle = ink;
      ctx.lineWidth = Math.max(1, s * 0.05);
      ctx.strokeRect(cx + side * s * 0.55 + (side < 0 ? -pw : 0), cy - s * 0.26, pw, s * 0.52);
    });
    // Dish.
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, s * 0.07);
    ctx.beginPath();
    ctx.arc(cx, cy + s * 0.55, s * 0.34, Math.PI * 1.1, Math.PI * 1.9);
    ctx.stroke();
    // Signal arcs down to the ground.
    if (p > 0.5) {
      ctx.strokeStyle = accent;
      ctx.globalAlpha *= clamp((p - 0.5) * 2);
      for (let i = 0; i < 3; i += 1) {
        ctx.beginPath();
        ctx.arc(cx, cy + s * 0.55, s * (0.55 + i * 0.3), Math.PI * 1.2, Math.PI * 1.8);
        ctx.stroke();
      }
    }
  },

  /** A cloud with nodes: the network, the platform, "the cloud". */
  'network-cloud': (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const cy = y + h * 0.46;
    const r = Math.min(w, h) * 0.18;
    const nodes = 6;
    ctx.strokeStyle = ink;
    ctx.globalAlpha *= 0.35;
    ctx.lineWidth = Math.max(1, r * 0.05);
    for (let i = 0; i < nodes; i += 1) {
      const a = (i / nodes) * TAU - Math.PI / 2;
      const nx = cx + Math.cos(a) * r * 2.1;
      const ny = cy + Math.sin(a) * r * 1.5;
      const k = clamp((p - i * 0.08) * 2.4);
      if (k <= 0) continue;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + (nx - cx) * k, cy + (ny - cy) * k);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // The cloud itself: three lobes and a base, filled white over the lines,
    // then outlined as one silhouette. Stroking the lobes separately left three
    // arcs with seams through them.
    const lobes = [
      [cx - r * 0.78, cy + r * 0.10, r * 0.62],
      [cx, cy - r * 0.22, r * 0.76],
      [cx + r * 0.80, cy + r * 0.10, r * 0.58],
    ];
    ctx.fillStyle = '#FFFFFF';
    lobes.forEach(([lx, ly, lr]) => {
      ctx.beginPath();
      ctx.arc(lx, ly, lr, 0, TAU);
      ctx.fill();
    });
    ctx.fillRect(cx - r * 1.34, cy + r * 0.16, r * 2.68, r * 0.56);
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, r * 0.09);
    lobes.forEach(([lx, ly, lr], i) => {
      // Only the outward-facing arc of each lobe: a full outline of three
      // circles reads as three bubbles, not a cloud.
      const from = i === 0 ? Math.PI * 0.55 : (i === 1 ? Math.PI * 1.02 : Math.PI * 1.52);
      const to = i === 0 ? Math.PI * 1.55 : (i === 1 ? Math.PI * 1.98 : Math.PI * 2.45);
      ctx.beginPath();
      ctx.arc(lx, ly, lr, from, to);
      ctx.stroke();
    });
    ctx.beginPath();
    ctx.moveTo(cx - r * 1.34, cy + r * 0.17);
    ctx.lineTo(cx - r * 1.34, cy + r * 0.62);
    ctx.lineTo(cx + r * 1.34, cy + r * 0.62);
    ctx.lineTo(cx + r * 1.34, cy + r * 0.17);
    ctx.stroke();
    // Nodes around it.
    for (let i = 0; i < nodes; i += 1) {
      const a = (i / nodes) * TAU - Math.PI / 2;
      const k = clamp((p - i * 0.08) * 2.4);
      if (k <= 0.5) continue;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * r * 2.1, cy + Math.sin(a) * r * 1.5, r * 0.18, 0, TAU);
      ctx.fill();
    }
  },

  /** A crowd: not a market, a market of people. */
  crowd: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const rows = 3;
    const cols = 7;
    for (let r = rows - 1; r >= 0; r -= 1) {
      const per = cols - r;
      const height = h * (0.34 - r * 0.05);
      const baseY = y + h * (0.92 - r * 0.12);
      for (let c = 0; c < per; c += 1) {
        const i = r * cols + c;
        const on = clamp((p - i * 0.035) * 3);
        if (on <= 0) continue;
        const cx = x + w * 0.5 + (c - (per - 1) / 2) * w * (0.115 + r * 0.012);
        ctx.globalAlpha = on * (1 - r * 0.18);
        figure(ctx, cx, baseY, height * on, r === 0 ? ink : 'rgba(18,35,63,0.45)');
      }
    }
    ctx.globalAlpha = 1;
  },

  /** A flag on a pole: the country, the claim, the headquarters. */
  flag: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const px = x + w * 0.34;
    const top = y + h * 0.12;
    const bottom = y + h * 0.9;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, w * 0.014);
    ctx.beginPath();
    ctx.moveTo(px, bottom);
    ctx.lineTo(px, top);
    ctx.stroke();
    const fw = w * 0.44 * clamp(p * 1.3);
    const fh = h * 0.28;
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.75;
    ctx.beginPath();
    ctx.moveTo(px, top);
    ctx.quadraticCurveTo(px + fw * 0.5, top + fh * 0.10, px + fw, top + fh * 0.02);
    ctx.lineTo(px + fw, top + fh);
    ctx.quadraticCurveTo(px + fw * 0.5, top + fh * 1.06, px, top + fh);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1, w * 0.006);
    ctx.stroke();
  },

  /** A trophy: the win, the quarter, the award. */
  trophy: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const tw = Math.min(w * 0.44, h * 0.5);
    const top = y + h * 0.16;
    const bowlH = h * 0.36;
    const k = clamp(p * 1.3);
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h * (0.2 + 0.8 * k));
    ctx.clip();
    // Bowl.
    ctx.beginPath();
    ctx.moveTo(cx - tw / 2, top);
    ctx.quadraticCurveTo(cx, top + bowlH * 1.5, cx + tw / 2, top);
    ctx.closePath();
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.4, tw * 0.05);
    ctx.stroke();
    // Handles.
    [-1, 1].forEach((s) => {
      ctx.beginPath();
      ctx.arc(cx + s * tw * 0.5, top + bowlH * 0.28, tw * 0.20, s > 0 ? -0.9 : Math.PI - 0.9, s > 0 ? 0.9 : Math.PI + 0.9);
      ctx.stroke();
    });
    // Stem and base.
    ctx.beginPath();
    ctx.moveTo(cx, top + bowlH * 0.62);
    ctx.lineTo(cx, top + bowlH * 0.95);
    ctx.stroke();
    ctx.fillStyle = ink;
    ctx.fillRect(cx - tw * 0.30, top + bowlH * 0.95, tw * 0.60, h * 0.06);
    ctx.fillRect(cx - tw * 0.42, top + bowlH * 0.95 + h * 0.06, tw * 0.84, h * 0.05);
    ctx.restore();
  },

  /** A gear: the machine, the process, the thing that turns. */
  gear: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.34;
    const cx = x + w / 2;
    const cy = y + h / 2;
    const teeth = 10;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(clamp(p) * 0.9);
    ctx.beginPath();
    for (let i = 0; i < teeth; i += 1) {
      const a0 = (i / teeth) * TAU;
      const a1 = ((i + 0.5) / teeth) * TAU;
      const outer = r;
      const inner = r * 0.78;
      ctx.lineTo(Math.cos(a0) * outer, Math.sin(a0) * outer);
      ctx.lineTo(Math.cos(a1) * inner, Math.sin(a1) * inner);
    }
    ctx.closePath();
    ctx.fillStyle = 'rgba(18,35,63,0.10)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, r * 0.07);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, r * 0.34, 0, TAU);
    ctx.strokeStyle = accent;
    ctx.stroke();
    ctx.restore();
  },

  /** A conveyor with parts on it: the factory line, the assembly, the output. */
  conveyor: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const top = y + h * 0.66;
    const left = x + w * 0.06;
    const right = x + w * 0.94;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, h * 0.018);
    ctx.beginPath();
    ctx.moveTo(left, top);
    ctx.lineTo(right, top);
    ctx.stroke();
    ctx.lineWidth = Math.max(1.2, h * 0.010);
    ctx.strokeStyle = 'rgba(18,35,63,0.35)';
    const stripes = 12;
    for (let i = 0; i < stripes; i += 1) {
      const xx = left + (i / stripes) * (right - left);
      ctx.beginPath();
      ctx.moveTo(xx, top);
      ctx.lineTo(xx + w * 0.02, top + h * 0.07);
      ctx.stroke();
    }
    // Legs.
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, h * 0.012);
    [0.16, 0.84].forEach((k) => {
      ctx.beginPath();
      ctx.moveTo(x + w * k, top);
      ctx.lineTo(x + w * k, y + h * 0.9);
      ctx.stroke();
    });
    // Parts travelling along it.
    for (let i = 0; i < 3; i += 1) {
      const prog = (p * 1.4 + i / 3) % 1;
      const px = left + prog * (right - left);
      const on = Math.sin(Math.PI * prog);
      ctx.globalAlpha = clamp(on * 1.6);
      ctx.fillStyle = accent;
      ctx.fillRect(px - w * 0.035, top - h * 0.16, w * 0.07, h * 0.16);
    }
    ctx.globalAlpha = 1;
  },

  /** A coil of cable: the industry the phone company grew out of. */
  'cable-coil': (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.30;
    const cx = x + w / 2;
    const cy = y + h / 2;
    const turns = 4;
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(2, r * 0.10);
    for (let i = 0; i < turns; i += 1) {
      const k = clamp((p - i * 0.16) * 3);
      if (k <= 0) continue;
      ctx.globalAlpha = 0.85 - i * 0.10;
      ctx.beginPath();
      ctx.arc(cx, cy - (turns / 2 - i) * r * 0.22, r * (1 - i * 0.055), Math.PI * 0.15, Math.PI * 0.15 + TAU * 0.92 * k);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // The loose end.
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(2, r * 0.09);
    ctx.beginPath();
    ctx.moveTo(cx + r * 0.98, cy + r * 0.30);
    ctx.quadraticCurveTo(cx + r * 1.4, cy + r * 0.5, cx + r * 1.5, cy + r * 0.9 * clamp(p));
    ctx.stroke();
  },

  /** A sheet of rubber: a slab with a rolled edge - the original product. */
  'rubber-sheet': (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const sw = w * 0.8;
    const sh = h * 0.34;
    const sx = x + (w - sw) / 2;
    const sy = y + h * 0.42;
    const k = clamp(p * 1.3);
    ctx.beginPath();
    ctx.moveTo(sx, sy + sh * 0.4);
    ctx.quadraticCurveTo(sx + sw * 0.5, sy - sh * (0.3 - 0.2 * k), sx + sw, sy + sh * 0.4);
    ctx.lineTo(sx + sw, sy + sh);
    ctx.quadraticCurveTo(sx + sw * 0.5, sy + sh * 1.3, sx, sy + sh);
    ctx.closePath();
    ctx.fillStyle = 'rgba(18,35,63,0.12)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, h * 0.014);
    ctx.stroke();
    // A roll of it behind.
    ctx.save();
    ctx.globalAlpha *= 0.5;
    ctx.beginPath();
    ctx.arc(sx + sw * 0.86, sy - sh * 0.5, sh * 0.34, 0, TAU);
    ctx.stroke();
    ctx.restore();
  },

  /** A paper roll: the mill, 1865, the thing the company actually was. */
  'paper-roll': (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const r = Math.min(w, h) * 0.26;
    const cx = x + w / 2;
    const cy = y + h * 0.52;
    const k = clamp(p * 1.3);
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w * k, h);
    ctx.clip();
    // Two rolls side by side, one behind the other.
    ctx.fillStyle = '#FFFFFF';
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, r * 0.09);
    [[-0.7, 0.25], [0.55, 0]].forEach(([dx, dy]) => {
      ctx.beginPath();
      ctx.arc(cx + r * dx, cy + r * dy, r, 0, TAU);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx + r * dx, cy + r * dy, r * 0.16, 0, TAU);
      ctx.stroke();
    });
    ctx.restore();
    // The web of paper running away.
    ctx.strokeStyle = accent;
    ctx.lineWidth = Math.max(1.4, r * 0.07);
    ctx.beginPath();
    ctx.moveTo(cx + r * 1.45, cy);
    ctx.quadraticCurveTo(cx + r * 2.2, cy + h * 0.12, cx + r * 2.6, cy + h * 0.3 * k);
    ctx.stroke();
  },

  /** A rocket: the ambition, the launch, the new market. */
  rocket: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cx = x + w / 2;
    const bh = h * 0.66;
    const bw = Math.min(w * 0.28, bh * 0.34);
    const top = y + h * 0.10;
    ctx.save();
    ctx.translate(0, (1 - clamp(p * 1.2)) * h * 0.10);
    // Body.
    ctx.beginPath();
    ctx.moveTo(cx, top);
    ctx.quadraticCurveTo(cx + bw, top + bh * 0.28, cx + bw, top + bh * 0.78);
    ctx.lineTo(cx - bw, top + bh * 0.78);
    ctx.quadraticCurveTo(cx - bw, top + bh * 0.28, cx, top);
    ctx.closePath();
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, bw * 0.09);
    ctx.stroke();
    // Window.
    ctx.beginPath();
    ctx.arc(cx, top + bh * 0.34, bw * 0.30, 0, TAU);
    ctx.strokeStyle = accent;
    ctx.stroke();
    // Fins.
    [-1, 1].forEach((s) => {
      ctx.beginPath();
      ctx.moveTo(cx + s * bw, top + bh * 0.62);
      ctx.lineTo(cx + s * bw * 1.9, top + bh * 0.88);
      ctx.lineTo(cx + s * bw, top + bh * 0.84);
      ctx.closePath();
      ctx.fillStyle = accent;
      ctx.fill();
    });
    // Flame.
    const fl = clamp((p - 0.35) / 0.4);
    if (fl > 0) {
      ctx.globalAlpha = fl;
      ctx.beginPath();
      ctx.moveTo(cx - bw * 0.6, top + bh * 0.78);
      ctx.quadraticCurveTo(cx, top + bh * (1.05 + 0.25 * fl), cx + bw * 0.6, top + bh * 0.78);
      ctx.closePath();
      ctx.fillStyle = accent;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  },

  /** A shipping container: the logistics, the trade, the export. */
  container: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const cw = Math.min(w * 0.80, h * 1.8);
    const ch = cw * 0.44;
    const cx = x + (w - cw) / 2;
    const cy = y + (h - ch) / 2;
    box(ctx, cx, cy, cw, ch, ch * 0.04);
    ctx.fillStyle = 'rgba(18,35,63,0.08)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, ch * 0.035);
    ctx.stroke();
    // Corrugation.
    ctx.strokeStyle = 'rgba(18,35,63,0.30)';
    ctx.lineWidth = Math.max(1, ch * 0.02);
    const ribs = 9;
    for (let i = 1; i < ribs; i += 1) {
      const xx = cx + (i / ribs) * cw * clamp(p * 1.4);
      ctx.beginPath();
      ctx.moveTo(xx, cy + ch * 0.10);
      ctx.lineTo(xx, cy + ch * 0.90);
      ctx.stroke();
    }
    ctx.fillStyle = accent;
    ctx.globalAlpha *= 0.6;
    ctx.fillRect(cx + cw * 0.06, cy + ch * 0.20, cw * 0.18, ch * 0.24);
    ctx.globalAlpha = 1;
  },

  /** A truck: the delivery, the last mile, the fleet. */
  truck: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const tw = Math.min(w * 0.86, h * 1.9);
    const th = tw * 0.40;
    const tx = x + (w - tw) / 2;
    const ty = y + (h - th) * 0.5;
    const cabW = tw * 0.26;
    // Trailer.
    box(ctx, tx, ty, tw * 0.70, th * 0.72, th * 0.04);
    ctx.fillStyle = 'rgba(18,35,63,0.07)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.5, th * 0.04);
    ctx.stroke();
    // Cab.
    ctx.beginPath();
    ctx.moveTo(tx + tw * 0.70, ty + th * 0.72);
    ctx.lineTo(tx + tw * 0.70, ty + th * 0.22);
    ctx.lineTo(tx + tw * 0.86, ty + th * 0.22);
    ctx.quadraticCurveTo(tx + tw, ty + th * 0.30, tx + tw, ty + th * 0.72);
    ctx.closePath();
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.stroke();
    // Wheels, rotating with p.
    const wr = th * 0.20;
    const cyW = ty + th * 0.80;
    [0.14, 0.32, 0.56, 0.86].forEach((k, i) => {
      const wx = tx + tw * k;
      ctx.beginPath();
      ctx.arc(wx, cyW, wr, 0, TAU);
      ctx.fillStyle = '#FFFFFF';
      ctx.fill();
      ctx.strokeStyle = ink;
      ctx.stroke();
      const a = p * TAU * 2 + i;
      ctx.beginPath();
      ctx.moveTo(wx, cyW);
      ctx.lineTo(wx + Math.cos(a) * wr * 0.7, cyW + Math.sin(a) * wr * 0.7);
      ctx.strokeStyle = accent;
      ctx.stroke();
    });
    // Ground line.
    ctx.strokeStyle = 'rgba(18,35,63,0.25)';
    ctx.beginPath();
    ctx.moveTo(tx, cyW + wr + th * 0.05);
    ctx.lineTo(tx + tw, cyW + wr + th * 0.05);
    ctx.stroke();
  },

  /** A ship: the export, the port, the global trade. */
  ship: (ctx, { x, y, w, h, ink, accent, p = 1 }) => {
    const sw = Math.min(w * 0.90, h * 2.1);
    const sh = sw * 0.34;
    const sx = x + (w - sw) / 2;
    const sy = y + h * 0.40;
    // Hull.
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx + sw, sy);
    ctx.lineTo(sx + sw * 0.92, sy + sh * 0.52);
    ctx.quadraticCurveTo(sx + sw * 0.5, sy + sh * 0.72, sx + sw * 0.08, sy + sh * 0.52);
    ctx.closePath();
    ctx.fillStyle = 'rgba(18,35,63,0.10)';
    ctx.fill();
    ctx.strokeStyle = ink;
    ctx.lineWidth = Math.max(1.6, sh * 0.05);
    ctx.stroke();
    // Containers stacked on deck.
    const stacks = 5;
    for (let i = 0; i < stacks; i += 1) {
      const k = clamp((p - i * 0.10) * 2.4);
      if (k <= 0) continue;
      const bw = sw * 0.13;
      const bx = sx + sw * 0.12 + i * sw * 0.15;
      for (let r = 0; r < 2; r += 1) {
        ctx.globalAlpha = k;
        ctx.fillStyle = r === 0 ? accent : 'rgba(18,35,63,0.30)';
        ctx.fillRect(bx, sy - sh * (0.26 * (r + 1)), bw, sh * 0.24);
      }
    }
    ctx.globalAlpha = 1;
    // Water lines under the hull.
    ctx.strokeStyle = 'rgba(18,35,63,0.20)';
    ctx.lineWidth = Math.max(1, sh * 0.03);
    for (let i = 0; i < 3; i += 1) {
      ctx.beginPath();
      ctx.moveTo(sx - sw * 0.04, sy + sh * (0.70 + i * 0.12));
      ctx.quadraticCurveTo(sx + sw * 0.5, sy + sh * (0.64 + i * 0.12), sx + sw * 1.04, sy + sh * (0.70 + i * 0.12));
      ctx.stroke();
    }
  },
};

export const PROP_IDS = Object.keys(props);
export default props;
