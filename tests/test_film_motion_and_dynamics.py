"""Two things the delivered cut failed on, turned into gates.

Both were found by measuring the shipped file rather than by looking at it.

* **Motion.** 596 of the film's 859 frames changed by less than 0.4 out of 255
  from the frame before. Every shot played its entrance and then sat still for
  the rest of its length - a slideshow with a camera push at each cut, and no
  contact sheet can show it. The check here renders one held shot twice, a
  second apart, and requires that a measurable part of the frame moved.

* **Dynamics.** Fifty-seven seconds of score sat inside seven decibels, because
  `score.build()` normalised the whole render to one target. The check renders
  two sections at opposite ends of the level table and requires a real gap
  between them.
"""
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / 'video_studio'
SCORE = STUDIO / 'score.py'


def _node(script, *args, cwd=STUDIO):
    out = subprocess.run(['node', '--input-type=module', '-e', script, *args],
                         cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return out.stdout


# Render one shot at two moments. The layer is a still image by design: whatever
# movement shows up is the stage's, which is exactly what is under test.
PROBE = """
import { createCanvas } from '@napi-rs/canvas';
import { renderShot } from './motion/kit/stage.mjs';

const W = 320, H = 180;
const shot = {
  id: 'probe-shot',
  background: '#000',
  layers: [{
    id: 'still',
    draw: (ctx) => { ctx.fillStyle = '#fff'; ctx.fillRect(W * 0.42, H * 0.42, W * 0.16, H * 0.16); },
  }],
};
const canvas = createCanvas(W, H);
const ctx = canvas.getContext('2d');
const sample = (t) => {
  ctx.clearRect(0, 0, W, H);
  renderShot(ctx, shot, t, W, H, { dur: 5 });
  const d = ctx.getImageData(0, 0, W, H).data;
  const out = [];
  for (let i = 0; i < d.length; i += 4) out.push(d[i]);
  return out;
};
const a = sample(0.5);
const b = sample(1.5);
let moved = 0, total = 0, dx = 0, dy = 0;
for (let y = 0; y < H; y += 1) {
  for (let x = 0; x < W; x += 1) {
    const i = y * W + x;
    total += 1;
    if (Math.abs(a[i] - b[i]) > 6) {
      moved += 1;
      if (x > 1 && a[i - 1] === a[i]) continue;
    }
  }
}
/* the centre of mass of the bright square, at each end */
const com = (p) => {
  let sx = 0, sy = 0, n = 0;
  for (let y = 0; y < H; y += 1) {
    for (let x = 0; x < W; x += 1) {
      if (p[y * W + x] > 128) { sx += x; sy += y; n += 1; }
    }
  }
  return n ? [sx / n, sy / n] : [0, 0];
};
const [ax, ay] = com(a);
const [bx, by] = com(b);
console.log(JSON.stringify({ movedShare: moved / total, dx: bx - ax, dy: by - ay, width: W }));
"""


class HeldShotStillTest(unittest.TestCase):
    """A shot that has finished entering must still be moving."""

    @classmethod
    def setUpClass(cls):
        cls.probe = json.loads(_node(PROBE).strip().splitlines()[-1])

    def test_the_frame_changes_between_two_seconds_of_a_hold(self):
        self.assertGreater(self.probe['movedShare'], 0.004,
                           'a held shot is a still photograph: nothing moved')

    def test_the_move_is_a_camera_and_not_a_whip_pan(self):
        """Four and a half percent over the shot: a drift, not a pan."""
        drift = max(abs(self.probe['dx']), abs(self.probe['dy'])) / self.probe['width']
        self.assertGreater(drift, 0.0, 'the frame is frozen')
        self.assertLess(drift, 0.06, f'the camera travels {drift:.1%} of the frame in a second')


class ScoreDynamicsTest(unittest.TestCase):
    """A quiet passage has to be quieter than a loud one."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / 'dynamics.wav'
        # the quietest and the loudest section in the table, back to back
        subprocess.run([sys.executable, str(SCORE), '--seconds', '16',
                        '--sections', 'sparse:0:8,build:8:16', '--out', str(cls.out)],
                       check=True, capture_output=True)

    @staticmethod
    def _rms(path, start, end):
        with wave.open(str(path)) as f:
            sr, channels = f.getframerate(), f.getnchannels()
            f.setpos(int(start * sr))
            data = np.frombuffer(f.readframes(int((end - start) * sr)), dtype='<i2')
        data = data.reshape(-1, channels).astype(np.float32).mean(axis=1) / 32768
        return 20 * np.log10(max(float(np.sqrt((data ** 2).mean())), 1e-9))

    def test_the_two_sections_are_far_apart(self):
        quiet, loud = self._rms(self.out, 1.0, 7.0), self._rms(self.out, 9.0, 15.0)
        gap = loud - quiet
        self.assertGreater(gap, 6.0, f'the score is flat: the two sections are {gap:.1f} dB apart')

    def test_every_section_carries_its_own_level(self):
        sys.path.insert(0, str(STUDIO))
        import score
        levels = set()
        for name, row in score.SECTIONS.items():
            self.assertEqual(len(row), 6, f'{name} has no level')
            levels.add(row[5])
        self.assertGreaterEqual(len(levels), 5, 'the sections share one loudness')


class ScoreContinuityTest(unittest.TestCase):
    """The bed may breathe; it may not leave the room.

    The owner's note on the delivered cut was "there is silence in scenes", and
    measuring the mix said they were right on three counts: every section's pad
    faded out inside its own length (so the bed was 1.2 s quiet before every cut
    while the next one took 0.9 s to arrive), the "too late" beat sat at -24 dBFS
    RMS for six seconds, and the last 1.25 s of the film was digital silence
    because the score ended with a two-second fade.

    A bed is allowed to be quiet. It is not allowed to stop.
    """

    SECTIONS = ('tense:0:5,sparse:5:11,history:11:17,moving:17:23,build:23:29,'
                'resolve:29:35')

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / 'continuity.wav'
        subprocess.run([sys.executable, str(SCORE), '--seconds', '35',
                        '--sections', cls.SECTIONS, '--out', str(cls.out)],
                       check=True, capture_output=True)

    def _envelope(self, win=0.05):
        with wave.open(str(self.out)) as f:
            sr, channels = f.getframerate(), f.getnchannels()
            data = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2')
        data = data.reshape(-1, channels).astype(np.float32).mean(axis=1) / 32768
        hop = int(sr * win)
        n = len(data) // hop
        return np.array([
            20 * np.log10(max(float(np.sqrt((data[i * hop:(i + 1) * hop] ** 2).mean())), 1e-9))
            for i in range(n)
        ]), sr, len(data)

    def test_no_hole_opens_inside_the_film(self):
        env, _, _ = self._envelope()
        quiet = env < -32.0
        runs, start = [], None
        for i, q in enumerate(quiet):
            if q and start is None:
                start = i
            elif not q and start is not None:
                runs.append((start * 0.05, i * 0.05))
                start = None
        if start is not None:
            runs.append((start * 0.05, len(env) * 0.05))
        holes = [r for r in runs if r[1] - r[0] >= 0.15]
        self.assertEqual(holes, [], f"the score drops out at {holes}")

    def test_the_beat_before_a_cut_is_not_the_quietest_thing_in_the_film(self):
        """The bed has to be present going *into* a cut, not fading out of it."""
        env, _, _ = self._envelope()
        for cut in (5, 11, 17, 23, 29):
            with self.subTest(cut=cut):
                before = env[int((cut - 0.8) / 0.05):int(cut / 0.05)]
                self.assertGreater(float(np.mean(before)), -30.0,
                                   f"the bed is {np.mean(before):.1f} dBFS into the cut at {cut}s")

    def test_the_film_ends_on_sound(self):
        env, sr, n = self._envelope()
        tail = env[int((n / sr - 0.4) / 0.05):]
        self.assertGreater(float(np.min(tail)), -40.0,
                           f"the last 400 ms fade to {np.min(tail):.1f} dBFS")


if __name__ == '__main__':
    unittest.main()
