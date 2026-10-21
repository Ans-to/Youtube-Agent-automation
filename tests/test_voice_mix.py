"""Ducking has to be measurable, not vibes.

The mix is judged on four numbers: the score really drops while the voice talks,
it comes back after, the sum does not clip, and the output is exactly as long as
the longer of the two inputs (so picture and sound stay locked).
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import voice_mix  # noqa: E402

RATE = 24000


def speech_like(seconds: float, spans, amplitude: float = 0.5, rate: int = RATE) -> np.ndarray:
    """Tone bursts where 'speech' happens, silence elsewhere."""
    signal = np.zeros(int(seconds * rate), dtype=np.float32)
    for start, end in spans:
        t = np.arange(int((end - start) * rate)) / rate
        burst = amplitude * np.sin(2 * math.pi * 180 * t) * (1 + 0.4 * np.sin(2 * math.pi * 5 * t))
        signal[int(start * rate):int(start * rate) + burst.size] += burst
    return signal


class LevelTests(unittest.TestCase):
    def test_gain_is_unity_without_speech(self):
        curve = np.zeros(100, dtype=np.float32)
        gain = voice_mix.db_to_gain(voice_mix.duck_db(curve, 8.5))
        self.assertTrue(np.allclose(gain, 1.0))

    def test_gain_drops_by_the_requested_depth(self):
        curve = np.ones(100, dtype=np.float32)
        gain = voice_mix.db_to_gain(voice_mix.duck_db(curve, 8.5))
        self.assertAlmostEqual(float(20 * np.log10(gain[0])), -8.5, places=3)

    def test_peak_limiter_leaves_quiet_audio_alone(self):
        signal = np.array([0.1, -0.2, 0.05], dtype=np.float32)
        self.assertTrue(np.array_equal(voice_mix.peak_limit(signal), signal))

    def test_peak_limiter_stops_overs(self):
        signal = np.full(1000, 3.0, dtype=np.float32)
        limited = voice_mix.peak_limit(signal)
        self.assertLessEqual(float(np.max(np.abs(limited))), 0.9)
        self.assertGreater(float(np.max(np.abs(limited))), 0.5)


class MixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.music = self.dir / "score.wav"
        self.voice = self.dir / "vo.wav"
        bed = 0.14 * np.sin(2 * math.pi * 220 * np.arange(RATE * 4) / RATE)
        voice_mix.write_wav(self.music, bed.astype(np.float32), RATE)
        voice_mix.write_wav(self.voice, speech_like(4.0, [(0.6, 1.4), (2.0, 3.2)]), RATE)
        self.out = self.dir / "mix.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_score_ducks_under_speech(self):
        info = voice_mix.mix(self.music, self.voice, self.out)
        self.assertGreater(info["duck_depth_db"], 0)
        self.assertGreater(info["duck_trigger_share"], 0.2)
        self.assertLess(info["mean_duck_db"], 0)

    def test_measured_duck_matches_the_curve(self):
        voice, rate = voice_mix.read_wav(self.voice)
        curve = voice_mix.speech_curve(voice, rate)
        speaking = float(np.mean(curve[int(0.8 * rate):int(1.3 * rate)]))
        gap = float(np.mean(curve[int(1.6 * rate):int(1.95 * rate)]))
        self.assertGreater(speaking, 0.8)
        self.assertLess(gap, 0.6)
        self.assertGreater(speaking, gap)

    def test_output_does_not_clip(self):
        info = voice_mix.mix(self.music, self.voice, self.out)
        self.assertLessEqual(info["peak"], 0.9)
        data, _ = voice_mix.read_wav(self.out)
        self.assertLessEqual(float(np.max(np.abs(data))), 0.9)

    def test_output_length_follows_the_longer_input(self):
        info = voice_mix.mix(self.music, self.voice, self.out)
        self.assertAlmostEqual(info["duration_seconds"], 4.0, places=2)
        data, rate = voice_mix.read_wav(self.out)
        self.assertEqual(rate, RATE)
        self.assertAlmostEqual(data.size / rate, 4.0, places=2)

    def test_a_shorter_voice_is_padded_not_truncating_the_score(self):
        short = self.dir / "short.wav"
        voice_mix.write_wav(short, speech_like(1.0, [(0.1, 0.5)]), RATE)
        info = voice_mix.mix(self.music, short, self.out)
        self.assertAlmostEqual(info["duration_seconds"], 4.0, places=2)

    def test_the_voice_is_above_the_bed(self):
        info = voice_mix.mix(self.music, self.voice, self.out)
        self.assertIsNotNone(info["voice_to_bed_db"])
        self.assertGreater(info["voice_to_bed_db"], 3.0)


if __name__ == "__main__":
    unittest.main()
