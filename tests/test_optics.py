"""The optics have to do something, and have to be measured to prove it.

This studio had already been bitten twice by a library that fails quietly:
`ctx.filter = 'blur(...)'` does nothing in this canvas build, and a font family
that is not installed renders in the system default without a word. An optics
stage written on top of either would have looked like it was working.

So the test does not assert that the code ran. It asserts that a pixel which was
black before the pass has been lit by the bloom, that a highlight has spread, and
that the grain differs between two frames.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"

PROBE = r"""
import { createCanvas } from '@napi-rs/canvas';
import { optics, frameBuffer } from './motion/kit/optics.mjs';

const W = 320, H = 180;

/** Mean luminance of a square patch. A single pixel is not a measurement. */
const patch = (canvas, x, y, size = 6) => {
  const d = canvas.getContext('2d').getImageData(x, y, size, size).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += d[i];
  return sum / (d.length / 4);
};

const frame = createCanvas(W, H);
const ctx = frame.getContext('2d');
ctx.fillStyle = '#000';
ctx.fillRect(0, 0, W, H);
// a broad highlight, the size a lit window or a screen actually is
ctx.fillStyle = '#FFFFFF';
ctx.fillRect(W / 2 - 26, H / 2 - 26, 52, 52);

const beforeNear = patch(frame, W / 2 + 40, H / 2);
const beforeCorner = patch(frame, 4, 4);

const fb = frameBuffer(W, H);
fb.ctx.drawImage(frame, 0, 0);
optics(ctx, { source: fb.canvas, w: W, h: H, frame: 0, bloom: 0.7, halation: 0.4, grain: 0, vignette: 0, threshold: 0.5 });
const afterNear = patch(frame, W / 2 + 40, H / 2);
const afterCorner = patch(frame, 4, 4);

// grain, measured over a patch, on two consecutive frames
const grainOf = (f) => {
  const c = createCanvas(W, H);
  const x = c.getContext('2d');
  x.fillStyle = '#202020';
  x.fillRect(0, 0, W, H);
  optics(x, { source: null, w: W, h: H, frame: f, bloom: 0, halation: 0, grain: 0.6, vignette: 0 });
  return c;
};
const g0 = grainOf(0);
const g1 = grainOf(1);
const dx = g0.getContext('2d').getImageData(0, 0, W, H).data;
const dy = g1.getContext('2d').getImageData(0, 0, W, H).data;
let diff = 0;
for (let i = 0; i < dx.length; i += 4) diff += Math.abs(dx[i] - dy[i]);
const grainDiff = diff / (dx.length / 4);

// vignette
const v = createCanvas(W, H);
const vctx = v.getContext('2d');
vctx.fillStyle = '#808080';
vctx.fillRect(0, 0, W, H);
optics(vctx, { source: null, w: W, h: H, frame: 0, bloom: 0, halation: 0, grain: 0, vignette: 1 });
const corner = patch(v, 2, 2, 4);
const centre = patch(v, W / 2 - 3, H / 2 - 3, 6);

console.log(JSON.stringify({ beforeNear, beforeCorner, afterNear, afterCorner, grainDiff, corner, centre }));
"""


def probe() -> dict:
    out = subprocess.run(
        ["node", "--input-type=module", "-e", PROBE],
        cwd=STUDIO, capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        raise AssertionError(out.stderr[-3000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestOpticsActuallyRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = probe()

    def test_bloom_lights_pixels_that_were_black(self):
        self.assertLess(self.m["beforeNear"], 1, "the probe frame is not black where it should be")
        self.assertGreater(
            self.m["afterNear"], 4,
            "the bloom did not light a patch near the highlight - the blur is a no-op",
        )

    def test_bloom_falls_off_with_distance(self):
        # The corner is 150 px from a 4 px highlight; bloom must not reach it as
        # strongly as it reaches 14 px away.
        self.assertLess(self.m["afterCorner"], self.m["afterNear"])
        self.assertLess(self.m["afterCorner"], 12, "the bloom is flooding the whole frame")

    def test_grain_moves_between_frames(self):
        self.assertGreater(self.m["grainDiff"], 0.5, "the grain is identical on two frames")

    def test_vignette_darkens_the_corner_and_not_the_centre(self):
        self.assertLess(self.m["corner"], 70)
        self.assertGreater(self.m["centre"], 120)


class TestTheFilmRendersAtDeviceScale(unittest.TestCase):
    """A 1080p deliverable must not be a 720p drawing with more pixels."""

    def test_a_shot_renders_at_one_and_a_half_scale(self):
        script = r"""
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from './motion/kit/fonts.mjs';
import { createRenderer } from './motion/kit/timeline.mjs';
import { FILM, SIZE } from './films/nokia_atlas.mjs';
loadFonts();
const scale = 1.5;
const dw = Math.round(SIZE.W * scale), dh = Math.round(SIZE.H * scale);
const c = createCanvas(dw, dh);
const ctx = c.getContext('2d');
const r = createRenderer(FILM, SIZE.W, SIZE.H, { join: 0.45, background: FILM[0].background, scale });
ctx.clearRect(0, 0, dw, dh);
r.render(ctx, 3.6);
const d = ctx.getImageData(0, 0, dw, dh).data;
let lit = 0, sum = 0;
for (let i = 0; i < d.length; i += 4) { const v = d[i] + d[i+1] + d[i+2]; if (v > 90) lit++; sum += v; }
console.log(JSON.stringify({ dw, dh, lit, mean: sum / (dw * dh * 3) }));
"""
        out = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=STUDIO, capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(out.returncode, 0, out.stderr[-3000:])
        m = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual((m["dw"], m["dh"]), (1920, 1080))
        self.assertGreater(m["lit"], 20000, "almost nothing was drawn at 1080p")
        self.assertGreater(m["mean"], 8, "the frame is black at 1080p")


if __name__ == "__main__":
    unittest.main()
