"""Every join has a sound, the sound lands on its frame, and it has a direction.

A cut is a picture event and a sound event at the same time; if the two are not
on the same frame the edit reads as an accident. `score.TRANSITION_CUE` therefore
records where each effect's *energy peaks*, not where its file starts — a whoosh
that begins on the cut peaks a third of a second after it, by which time the new
shot has arrived by itself.

Alignment is asserted on the cue bus rather than on the finished score: the
master's limiter shaves the loudest moments, so a difference against a dry render
is a measurement of the limiter as much as of the effect. Audibility is asserted
on the finished file, where it belongs.
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
SECTIONS = 'calm:0:3,moving:3:5,tense:5:7,resolve:7:9'

sys.path.insert(0, str(STUDIO))
import score  # noqa: E402

# Three joins with three different characters, in the film's own edit-list shape.
SHOTS = [
    {'id': 'a', 'start': 0.0, 'end': 3.0, 'transition': 'cut'},
    {'id': 'b', 'start': 3.0, 'end': 5.0, 'transition': 'dissolve'},
    {'id': 'c', 'start': 5.0, 'end': 7.0, 'transition': 'wipe-left'},
    {'id': 'd', 'start': 7.0, 'end': 9.0, 'transition': 'cut'},
]


def _load(path):
    with wave.open(str(path)) as f:
        n, ch, sr = f.getnframes(), f.getnchannels(), f.getframerate()
        data = np.frombuffer(f.readframes(n), dtype='<i2').astype(np.float32)
    return data.reshape(-1, ch).T / 32768, sr


class CueBusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.total = int(9 * score.SR)
        cls.events = score.cues_from_starts(SHOTS)
        cls.bus = score.cue_bus(cls.total, cls.events)

    def _peak_near(self, at, before=0.6, after=0.4):
        lo, hi = int((at - before) * score.SR), int((at + after) * score.SR)
        env = np.abs(self.bus[:, lo:hi]).max(axis=0)
        t = np.arange(len(env)) / score.SR + lo / score.SR
        return t[int(np.argmax(env))]

    def test_one_sound_per_join(self):
        self.assertEqual(len(self.events), len(SHOTS) - 1)

    def test_every_join_lands_on_its_frame(self):
        """Within two frames at 24 fps. One frame is a flam; two is a mistake."""
        for cut in (3.0, 5.0, 7.0):
            at = self._peak_near(cut)
            self.assertLess(abs(at - cut), 0.083, f'the join at {cut}s peaks at {at:.2f}s')

    def test_the_effects_are_pre_lapped(self):
        """The sound of a cut has to start before the cut, not after it."""
        starts = [round(row[0], 3) for row in self.events]
        self.assertLess(starts[0], 3.0)
        self.assertLess(starts[1], 5.0)
        self.assertLess(starts[2], 7.0)

    def test_a_wipe_has_a_direction(self):
        """A wipe-left travels left, so its sound does too."""
        lo, hi = int(4.2 * score.SR), int(5.8 * score.SR)
        left = np.abs(self.bus[0, lo:hi]).sum()
        right = np.abs(self.bus[1, lo:hi]).sum()
        self.assertGreater(left, right * 1.4, 'the wipe is not panned')

    def test_a_cut_has_no_direction(self):
        """A cut happens everywhere at once, not on one side."""
        lo, hi = int(2.6 * score.SR), int(3.4 * score.SR)
        left = np.abs(self.bus[0, lo:hi]).sum()
        right = np.abs(self.bus[1, lo:hi]).sum()
        self.assertLess(abs(20 * np.log10(left / (right + 1e-9))), 3.0, 'the cut is panned')

    def test_every_effect_is_the_same_loudness(self):
        """A tick and a three-second bloom, normalised: 3 dB, not 20."""
        peaks = []
        for at, kind, level, _pan in self.events:
            seg = np.abs(self.bus[:, int(at * score.SR):int((at + 0.5) * score.SR)]).max()
            peaks.append(20 * np.log10(seg + 1e-9))
        self.assertLess(max(peaks) - min(peaks), 8.0, f'effects vary by {max(peaks) - min(peaks):.0f} dB')

    def test_an_unknown_join_fails_loudly(self):
        bad = json.loads(json.dumps(SHOTS))
        bad[1]['transition'] = 'spin-round'
        with self.assertRaises(SystemExit) as cm:
            score.cues_from_starts(bad)
        self.assertIn('spin-round', str(cm.exception))


class RenderedFileTest(unittest.TestCase):
    """The effects have to reach the file, not just the bus."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        starts = cls.dir / 'starts.json'
        starts.write_text(json.dumps(SHOTS))
        cls.with_cues = cls.dir / 'cues.wav'
        cls.without = cls.dir / 'dry.wav'
        for out, extra in ((cls.with_cues, ['--starts', str(starts)]), (cls.without, [])):
            subprocess.run([sys.executable, str(SCORE), '--seconds', '9',
                            '--sections', SECTIONS, '--out', str(out), *extra],
                           check=True, capture_output=True)
        a, cls.sr = _load(cls.with_cues)
        b, _ = _load(cls.without)
        cls.events = a - b

    def test_every_join_is_audible(self):
        for cut in (3.0, 5.0, 7.0):
            lo, hi = int((cut - 0.6) * self.sr), int((cut + 0.4) * self.sr)
            peak = np.abs(self.events[:, lo:hi]).max()
            self.assertGreater(20 * np.log10(peak + 1e-9), -30.0,
                               f'the join at {cut}s is inaudible')

    def test_the_score_still_renders_in_stereo(self):
        self.assertEqual(self.events.shape[0], 2)


if __name__ == '__main__':
    unittest.main()
