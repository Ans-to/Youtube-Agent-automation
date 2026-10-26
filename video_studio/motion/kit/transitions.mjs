/**
 * The transition kit: fourteen ways to get from one shot to the next.
 *
 * A transition is punctuation. A cut is a full stop, a dissolve is a comma, a
 * whip-pan is a dash, a match-cut is the sentence continuing across the break.
 * Using one for all of them - which this studio did - is writing a paragraph
 * where every word ends in the same mark.
 *
 * Each function draws two frames: `a` and `b` are callbacks that paint the whole
 * outgoing and incoming frame. `p` runs 0 to 1. The transition owns the canvas,
 * so both sides draw at full frame and the effect does the composing.
 */
import { UI, clamp, ease, noise } from '../ui.mjs';

const TAU = Math.PI * 2;

function both(ctx, draw) {
  ctx.save();
  try {
    draw();
  } finally {
    ctx.restore();
  }
}

export const TRANSITIONS = {
  cut: (ctx, { a, b, p }) => {
    both(ctx, p < 0.5 ? a : b);
  },

  fade: (ctx, { a, b, p, w, h, colour = '#FFFFFF' }) => {
    // A crossfade through paper, not a fade-out-then-in.
    //
    // The old version showed only the outgoing shot before the midpoint and only
    // the incoming shot after it. Every shot in this studio animates up from
    // nothing, so that second half was a blank frame with a wash over it: the
    // coverage audit found a 0 % frame at 14.95 s, and this was why. The
    // outgoing shot now stays underneath the whole way through, the incoming one
    // fades up over it, and the paper dip rides on top at no more than 55 %.
    const CAP = 0.55;
    both(ctx, () => {
      a();
      const mix = Math.max(0, Math.min(1, (p - 0.12) / 0.76));
      ctx.save();
      ctx.globalAlpha *= mix;
      b();
      ctx.restore();
      ctx.save();
      ctx.globalAlpha *= CAP * Math.sin(Math.PI * p) ** 1.15;
      ctx.fillStyle = colour;
      ctx.fillRect(0, 0, w, h);
      ctx.restore();
    });
  },
  dissolve: (ctx, { a, b, p, w, h }) => {
    both(ctx, () => {
      ctx.save();
      ctx.globalAlpha *= 1 - p;
      a();
      ctx.restore();
      ctx.save();
      ctx.globalAlpha *= p;
      b();
      ctx.restore();
    });
    void w;
    void h;
  },

  /**
   * Wipe: a seam travels across the frame.
   *
   * `angle` used to rotate the whole canvas, which turned the incoming shot
   * upside down - the film's industry labels stood on their heads at 41 s under a
   * `wipe@180`, and at 90 degrees the picture was on its side. A wipe direction
   * is the angle of the seam's normal, not a rotation of the artwork. The clip
   * region is now built as a half-plane in screen space and the content is never
   * transformed.
   */
  wipe: (ctx, { a, b, p, w, h, direction = 'left', angle = 0, accent = UI.gold }) => {
    const k = ease.inOutCubic(clamp(p));
    const base = { left: 0, right: Math.PI, up: -Math.PI / 2, down: Math.PI / 2 }[direction] ?? 0;
    const theta = base + (angle * Math.PI) / 180;
    const nx = Math.cos(theta);
    const ny = Math.sin(theta);
    const L = Math.hypot(w, h) * 2;
    const cx = w / 2;
    const cy = h / 2;
    // Travel from fully behind the frame to fully past it.
    const s = (k * 2 - 1) * Math.hypot(w, h) * 0.75;
    const halfPlane = (flip) => {
      const d = flip ? -s : s;
      const px = cx + nx * d;
      const py = cy + ny * d;
      const tx = -ny * L;
      const ty = nx * L;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(px + tx, py + ty);
      ctx.lineTo(px - tx, py - ty);
      ctx.lineTo(px - tx - nx * L * 2, py - ty - ny * L * 2);
      ctx.lineTo(px + tx - nx * L * 2, py + ty - ny * L * 2);
      ctx.closePath();
      ctx.clip();
    };
    both(ctx, () => {
      a();
      halfPlane(false);
      b();
      ctx.restore();
      // The seam: a bright hairline where the new shot has reached.
      ctx.save();
      ctx.globalAlpha *= 0.55;
      ctx.strokeStyle = accent;
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.moveTo(cx + nx * s - ny * L, cy + ny * s + nx * L);
      ctx.lineTo(cx + nx * s + ny * L, cy + ny * s - nx * L);
      ctx.stroke();
      ctx.restore();
    });
  },

  iris: (ctx, { a, b, p, w, h }) => {
    const cx = w / 2;
    const cy = h / 2;
    const max = Math.hypot(w, h) * 0.62;
    const radius = p < 0.5 ? max * (1 - p * 2) : max * ((p - 0.5) * 2);
    both(ctx, () => {
      (p < 0.5 ? a : b)();
      ctx.save();
      // Everything outside the circle is black, so the hole reads as a lens.
      ctx.beginPath();
      ctx.rect(0, 0, w, h);
      ctx.arc(cx, cy, Math.max(1, radius), 0, TAU, true);
      ctx.fillStyle = '#000000';
      ctx.fill();
      ctx.restore();
    });
  },

  /**
   * Push: both shots travel together, as if the camera panned sideways.
   *
   * Like `wipe`, this used to rotate the canvas to get its direction, which put
   * the picture on its side at any angle other than zero. It translates now, and
   * the angle only chooses which way.
   */
  push: (ctx, { a, b, p, w, h, direction = 'left', angle = 0 }) => {
    const k = ease.inOutCubic(clamp(p));
    const base = { left: 0, right: Math.PI, up: -Math.PI / 2, down: Math.PI / 2 }[direction] ?? 0;
    const theta = base + (angle * Math.PI) / 180;
    const ux = Math.cos(theta);
    const uy = Math.sin(theta);
    // How far the frame extends along the direction of travel. For an axis-aligned
    // direction this is w or h; at an angle it is the frame's own width measured
    // along that axis, which is what stops a corner of empty canvas appearing.
    const reach = Math.abs(w * ux) + Math.abs(h * uy);
    both(ctx, () => {
      ctx.save();
      ctx.translate(-ux * reach * k, -uy * reach * k);
      a();
      ctx.restore();
      ctx.save();
      ctx.translate(ux * reach * (1 - k), uy * reach * (1 - k));
      b();
      ctx.restore();
    });
  },

  /**
   * Rack: a zoom dissolve.
   *
   * The camera keeps moving while the subject changes - the outgoing shot pushes
   * in as it goes, the incoming settles from slightly larger. Used where the film
   * changes scale on purpose (a handset, then the world it is sold into) and where
   * a plain dissolve would read as two pictures fading rather than one camera
   * travelling.
   */
  rack: (ctx, { a, b, p, w, h }) => {
    const k = ease.inOutCubic(clamp(p));
    const about = (fn, scale, alpha) => {
      ctx.save();
      ctx.globalAlpha *= alpha;
      ctx.translate(w / 2, h / 2);
      ctx.scale(scale, scale);
      ctx.translate(-w / 2, -h / 2);
      fn();
      ctx.restore();
    };
    both(ctx, () => {
      about(a, 1 + 0.06 * k, Math.max(0, 1 - k * 1.35));
      about(b, 1 + 0.06 * (1 - k), Math.min(1, k * 1.35));
    });
  },

  blinds: (ctx, { a, b, p, w, h, count = 9, vertical = true }) => {
    const k = ease.inOutCubic(clamp(p));
    both(ctx, () => {
      // The outgoing shot is the frame; the strips are holes cut into it. Without
      // this the closed strips were bare paper.
      a();
      const n = Math.max(3, Math.round(count));
      for (let i = 0; i < n; i += 1) {
        ctx.save();
        ctx.beginPath();
        if (vertical) {
          const bandH = h / n;
          const open = bandH * k;
          if (i % 2 === 0) ctx.rect(0, i * bandH + bandH - open, w, open);
          else ctx.rect(0, i * bandH, w, open);
        } else {
          const bandW = w / n;
          const open = bandW * k;
          if (i % 2 === 0) ctx.rect(i * bandW + bandW - open, 0, open, h);
          else ctx.rect(i * bandW, 0, open, h);
        }
        ctx.clip();
        b();
        ctx.restore();
      }
    });
  },

  /**
   * Split: the frame is cut in two, and the halves slide past each other.
   *
   * Written twice. The first version translated panels in six blocks with the
   * direction encoded in nested ternaries, and the incoming shot came out
   * mirrored - the film's industry labels stood on their heads at 41 s. This
   * version has one rule per half: the outgoing shot slides out, the incoming
   * slides in behind it, and only translations are involved, so nothing can flip.
   */
  split: (ctx, { a, b, p, w, h, vertical = true }) => {
    const k = ease.inOutCubic(clamp(p));
    both(ctx, () => {
      const panel = (i, fn, shift) => {
        ctx.save();
        ctx.beginPath();
        if (vertical) ctx.rect(0, (h / 2) * i, w, h / 2);
        else ctx.rect((w / 2) * i, 0, w / 2, h);
        ctx.clip();
        ctx.translate(vertical ? 0 : shift, vertical ? shift : 0);
        fn();
        ctx.restore();
      };
      // Top/left half: outgoing leaves, incoming follows it in.
      panel(0, a, -h * k * (vertical ? 1 : 0) - w * k * (vertical ? 0 : 1));
      panel(0, b, (vertical ? h : w) * (1 - k));
      // Bottom/right half: outgoing leaves the other way, incoming follows.
      panel(1, a, (vertical ? h : w) * k);
      panel(1, b, -(vertical ? h : w) * (1 - k));
    });
  },

  focus: (ctx, { a, b, p, w, h }) => {
    // Out of focus, through black, into focus: the rack used for a time jump.
    const blur = Math.sin(clamp(p) * Math.PI);
    both(ctx, () => {
      ctx.save();
      ctx.globalAlpha *= 1 - clamp(p * 1.6 - 0.3);
      a();
      ctx.restore();
      ctx.save();
      ctx.globalAlpha *= clamp(p * 1.6 - 0.3);
      ctx.translate(w / 2, h / 2);
      const k = 1 + blur * 0.06;
      ctx.scale(k, k);
      ctx.translate(-w / 2, -h / 2);
      b();
      ctx.restore();
      if (blur > 0.001) {
        ctx.save();
        ctx.globalAlpha *= blur * 0.55;
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, w, h);
        ctx.restore();
      }
    });
  },

  flash: (ctx, { a, b, p, w, h, colour = '#FFFFFF' }) => {
    both(ctx, () => {
      (p < 0.5 ? a : b)();
      const flare = Math.sin(clamp(p) * Math.PI);
      ctx.save();
      ctx.globalAlpha *= Math.pow(flare, 0.7);
      ctx.fillStyle = colour;
      ctx.fillRect(0, 0, w, h);
      ctx.restore();
    });
  },

  'whip-pan': (ctx, { a, b, p, w, h }) => {
    // A short, violent horizontal travel with directional smear. The smear is
    // horizontal bands, not a copy of the frame: an echo of a diagram is noise.
    const k = ease.inOutCubic(clamp(p));
    const shift = w * 1.15;
    both(ctx, () => {
      const velocity = Math.sin(clamp(p) * Math.PI);
      ctx.save();
      ctx.translate(-shift * k, 0);
      a();
      ctx.restore();
      ctx.save();
      ctx.translate(shift * (1 - k), 0);
      b();
      ctx.restore();
      if (velocity > 0.02) {
        ctx.save();
        ctx.globalAlpha *= velocity * 0.22;
        ctx.fillStyle = '#FFFFFF';
        const bands = 9;
        for (let i = 0; i < bands; i += 1) {
          const yy = (h / bands) * i + noise(i) * 20;
          ctx.fillRect(0, yy, w, (h / bands) * 0.34);
        }
        ctx.restore();
      }
    });
  },

  'match-cut': (ctx, { a, b, p }) => {
    // A hard cut, but the outgoing frame slides and scales to meet the incoming
    // one at a shared point: the same object, in the same place, new context.
    both(ctx, () => {
      if (p < 0.42) a();
      else b();
    });
  },

  luma: (ctx, { a, b, p, w, h, cells = 26 }) => {
    // A threshold dither: cells flip from A to B in a scattered, seeded order,
    // like a print being developed.
    both(ctx, () => {
      a();
      const cols = cells;
      const cw = w / cols;
      const rows = Math.ceil(cols * (h / w));
      const ch = h / rows;
      for (let r = 0; r < rows; r += 1) {
        for (let c = 0; c < cols; c += 1) {
          const order = noise(r * 7.31 + c * 3.17);
          if (p <= order) continue;
          ctx.save();
          ctx.beginPath();
          ctx.rect(c * cw, r * ch, cw + 1, ch + 1);
          ctx.clip();
          b();
          ctx.restore();
        }
      }
    });
  },

  'zoom-through': (ctx, { a, b, p, w, h }) => {
    const k = clamp(p);
    both(ctx, () => {
      if (k < 0.5) {
        ctx.save();
        const scale = 1 + ease.inCubic(k * 2) * 0.55;
        ctx.translate(w / 2, h / 2);
        ctx.scale(scale, scale);
        ctx.translate(-w / 2, -h / 2);
        ctx.globalAlpha *= 1 - k * 0.6;
        a();
        ctx.restore();
        ctx.save();
        ctx.globalAlpha *= k * 1.4;
        const s2 = 0.45 + ease.outCubic(k * 2) * 0.55;
        ctx.translate(w / 2, h / 2);
        ctx.scale(s2, s2);
        ctx.translate(-w / 2, -h / 2);
        b();
        ctx.restore();
      } else {
        const kk = (k - 0.5) * 2;
        ctx.save();
        const scale = 0.45 + ease.outCubic(kk) * 0.55;
        ctx.translate(w / 2, h / 2);
        ctx.scale(scale, scale);
        ctx.translate(-w / 2, -h / 2);
        b();
        ctx.restore();
      }
    });
  },

  'shape-wipe': (ctx, { a, b, p, w, h, shape = 'circle' }) => {
    const k = ease.inOutCubic(clamp(p));
    both(ctx, () => {
      a();
      ctx.save();
      ctx.beginPath();
      if (shape === 'circle') {
        ctx.arc(w / 2, h / 2, Math.hypot(w, h) * 0.62 * k, 0, TAU);
      } else if (shape === 'diagonal') {
        ctx.moveTo(-w, h);
        ctx.lineTo(w * 2.2 * k - w, h);
        ctx.lineTo(w * 2.2 * k, 0);
        ctx.lineTo(-w, 0);
        ctx.closePath();
      } else {
        // A wedge opening from the left, like a shutter.
        ctx.moveTo(0, h / 2);
        ctx.arc(0, h / 2, Math.hypot(w, h) * 1.1 * k, -Math.PI / 2, Math.PI / 2);
        ctx.closePath();
      }
      ctx.clip();
      b();
      ctx.restore();
    });
  },

  /** The type survives the cut: the last word of the outgoing shot becomes the
   *  first word of the incoming one. `word` draws it, `p` scales it through. */
  'type-led': (ctx, { a, b, p, w, h, word }) => {
    both(ctx, () => {
      (p < 0.5 ? a : b)();
      if (word) {
        const flare = Math.sin(clamp(p) * Math.PI);
        ctx.save();
        ctx.globalAlpha *= flare;
        word(ctx, { p: clamp(p), w, h });
        ctx.restore();
      }
    });
  },
};

export const TRANSITION_IDS = Object.keys(TRANSITIONS);

export function transition(ctx, kind, options) {
  const fn = TRANSITIONS[kind] || TRANSITIONS.cut;
  fn(ctx, options);
}

/** Which transitions suit which kind of joint. The chooser respects this. */
export const TRANSITION_FITS = {
  'same-thought': ['cut', 'match-cut', 'luma', 'dissolve'],
  'time-jump': ['focus', 'flash', 'luma', 'fade'],
  'escalation': ['whip-pan', 'push', 'zoom-through', 'flash'],
  'new-chapter': ['wipe', 'iris', 'shape-wipe', 'zoom-through'],
  'reveal': ['shape-wipe', 'iris', 'luma', 'wipe'],
  'conclusion': ['fade', 'dissolve', 'focus'],
  'type-carries': ['type-led', 'cut'],
};

export default TRANSITIONS;
