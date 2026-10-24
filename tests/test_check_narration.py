"""Tests for the narration gate.

The gate exists because a film shipped with a formant read at 213 words per
minute, one audible breath in eleven minutes, and every other check green. These
tests build that narration deliberately, prove the gate rejects it, and prove it
accepts a read a person could follow.
"""
import json
import math
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_narration

RATE = 16000


def write_wav(path: Path, samples, rate: int = RATE) -> Path:
    data = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((data * 32767).astype("<i2").tobytes())
    return path


def tone(seconds: float, rate: int = RATE, frequency: float = 180.0, level: float = 0.3):
    """A steady vowel-ish tone: enough structure for the speech detector."""
    count = int(seconds * rate)
    t = np.arange(count) / rate
    return level * np.sin(2 * math.pi * frequency * t)


def silence(seconds: float, rate: int = RATE):
    return np.zeros(int(seconds * rate))


def build_narration(sentence_seconds, pause_seconds, sentences, gap_seconds=0.0):
    """A synthetic read: tone, pause, tone, pause, ... one entry per sentence."""
    pieces = []
    if gap_seconds:
        pieces.append(silence(gap_seconds))
    for index in range(sentences):
        pieces.append(tone(sentence_seconds))
        if index < sentences - 1:
            pieces.append(silence(pause_seconds))
    return np.concatenate(pieces)


class MeasurementTests(unittest.TestCase):
    def test_a_fast_read_is_reported_as_fast(self):
        # 20 sentences of 1.2 s with 0.1 s between them: no air at all.
        samples = build_narration(1.2, 0.1, 20)
        result = check_narration.verdict(check_narration.analyse(samples, RATE, words=300))
        self.assertFalse(result.listenable)
        self.assertTrue(any("words per minute" in item for item in result.failures))

    def test_a_read_with_no_air_fails_on_rests(self):
        # Six words a second sounds brisk but acceptable; 0.1 s of pause does not.
        samples = build_narration(2.0, 0.1, 12)
        result = check_narration.verdict(check_narration.analyse(samples, RATE, words=120))
        self.assertFalse(result.listenable)
        self.assertTrue(any("no air" in item for item in result.failures))

    def test_a_listenable_read_passes(self):
        # 12 sentences of 2 s (about 150 wpm at ~5 words a sentence) with 0.9 s of
        # air between them, which is 27 rests a minute.
        samples = build_narration(2.0, 0.9, 12)
        result = check_narration.verdict(check_narration.analyse(samples, RATE, words=60))
        self.assertTrue(result.listenable, result.failures)
        self.assertGreaterEqual(result.breaths_per_minute, check_narration.MIN_BREATHS_PER_MINUTE)

    def test_a_single_long_silence_is_not_air(self):
        # One 5 s gap and otherwise no rests: the old failure mode, hidden inside
        # an average that looks generous.
        samples = np.concatenate([
            build_narration(2.0, 0.05, 10),
            silence(5.0),
            build_narration(2.0, 0.05, 10),
        ])
        result = check_narration.verdict(check_narration.analyse(samples, RATE, words=200))
        self.assertAlmostEqual(result.longest_pause, 5.0, delta=0.05)
        self.assertFalse(result.listenable)

    def test_a_lead_in_silence_is_not_counted_as_a_pause(self):
        samples = build_narration(2.0, 0.9, 6, gap_seconds=3.0)
        result = check_narration.analyse(samples, RATE, words=30)
        self.assertEqual(result.longest_pause, 0.9)

    def test_an_empty_narration_fails_instead_of_dividing_by_zero(self):
        result = check_narration.verdict(check_narration.analyse(np.zeros(0), RATE, words=10))
        self.assertFalse(result.listenable)
        self.assertIn("empty", result.failures[0])

    def test_a_constant_tone_has_no_pauses_rather_than_infinite_ones(self):
        result = check_narration.analyse(tone(8.0), RATE, words=20)
        self.assertEqual(result.pauses, 0)
        self.assertEqual(result.longest_pause, 0.0)

    def test_loudness_is_only_judged_at_the_mix_stage(self):
        samples = build_narration(2.0, 0.9, 12)
        result = check_narration.analyse(samples, RATE, words=60)
        result.lufs = -21.0
        voice = check_narration.verdict(result, check_narration.STAGE_VOICE)
        self.assertTrue(voice.listenable, voice.failures)
        mixed = check_narration.verdict(result, check_narration.STAGE_MIX)
        self.assertFalse(mixed.listenable)
        self.assertTrue(any("LUFS" in item for item in mixed.failures))

    def test_a_hot_mix_is_rejected(self):
        result = check_narration.analyse(build_narration(2.0, 0.9, 12), RATE, words=60)
        result.lufs = -14.0
        result.true_peak_db = 0.4
        result = check_narration.verdict(result, check_narration.STAGE_MIX)
        self.assertFalse(result.listenable)
        self.assertTrue(any("true peak" in item for item in result.failures))


class WordCountTests(unittest.TestCase):
    def test_words_come_from_what_is_spoken_not_from_the_written_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lines.json"
            path.write_text(json.dumps({"lines": [
                {"text": "*Every* frame is code.", "spoken": "Every frame is code."},
                {"text": "github dot com"},
            ]}), encoding="utf-8")
            self.assertEqual(check_narration.count_words(path), 4 + 3)

    def test_a_malformed_file_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lines.json"
            path.write_text(json.dumps({"nope": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                check_narration.count_words(path)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_narration.py"), *args],
            capture_output=True, text=True, check=False,
        )

    def test_a_missing_file_is_bad_input_not_a_crash(self):
        result = self._run("--wav", str(self.dir / "nope.wav"), "--words", "10")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such narration", result.stderr)

    def test_a_missing_word_count_is_refused(self):
        path = write_wav(self.dir / "v.wav", build_narration(2.0, 0.9, 4))
        result = self._run("--wav", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("no word count", result.stderr)

    def test_an_unlistenable_file_exits_non_zero_and_names_the_reason(self):
        path = write_wav(self.dir / "bad.wav", build_narration(1.2, 0.1, 20))
        result = self._run("--wav", str(path), "--words", "300")
        self.assertEqual(result.returncode, 1)
        self.assertIn("NARRATION: FAIL", result.stdout)
        self.assertIn("words per minute", result.stdout)

    def test_json_mode_is_machine_readable(self):
        path = write_wav(self.dir / "good.wav", build_narration(2.0, 0.9, 12))
        result = self._run("--wav", str(path), "--words", "60", "--json")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["listenable"])
        self.assertEqual(payload["pauses"], 11)
        self.assertGreaterEqual(payload["breaths_per_minute"], 4.0)

    def test_quiet_mode_prints_nothing_when_the_read_passes(self):
        path = write_wav(self.dir / "good.wav", build_narration(2.0, 0.9, 12))
        result = self._run("--wav", str(path), "--words", "60", "--quiet")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
