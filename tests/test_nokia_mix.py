"""The documentary mix exports the actual clock and measurable separate buses."""
import json
import math
import tempfile
import unittest
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    raise unittest.SkipTest("numpy is required for the narration mixer") from None

from video_studio import narrate
from video_studio.nokia_audit import measure_stems


class NokiaMixTests(unittest.TestCase):
    def test_ducking_smoother_matches_direct_convolution_across_blocks(self):
        rng = np.random.default_rng(42)
        signal = rng.random(4217).astype(np.float32)
        for width in (7, 8, 101):
            kernel = np.hanning(width)
            kernel /= kernel.sum()
            expected = np.convolve(signal, kernel, mode='same')
            actual = narrate.smooth_same(signal, kernel, block_size=137)
            self.assertEqual(len(actual), len(expected))
            np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-6)
        # Shorter signals preserve numpy's 'same' behavior too.
        signal = np.array([0.0, 1.0, 1.0], dtype=np.float32)
        kernel = np.ones(8, dtype=np.float64) / 8
        np.testing.assert_allclose(narrate.smooth_same(signal, kernel),
                                   np.convolve(signal, kernel, mode='same'), atol=1e-6)

    def test_mix_emits_aligned_stems_and_the_real_shot_clock(self):
        sr = narrate.SR
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            voice_dir = root / "voice"
            voice_dir.mkdir()
            seconds = 0.7
            tone = (0.25 * np.sin(2 * math.pi * 220 * np.arange(int(sr * seconds)) / sr)).astype(np.float32)
            for i in (1, 2):
                narrate.V.write_wav(voice_dir / f"{i}.wav", tone)
            timing = [{"shot": "a", "file": "1.wav", "vo": seconds, "text": "First line."},
                      {"shot": "b", "file": "2.wav", "vo": seconds, "text": "Second line."}]
            (voice_dir / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
            starts = [{"id": "a", "start": 0, "end": 1.5, "voStart": 0.3},
                      {"id": "b", "start": 1.5, "end": 3.0, "voStart": 1.8}]
            starts_path = root / "starts.json"
            starts_path.write_text(json.dumps(starts), encoding="utf-8")
            bed = (0.1 * np.sin(2 * math.pi * 130 * np.arange(sr * 3) / sr)).astype(np.float32)
            score = root / "score.wav"
            narrate.V.write_wav(score, bed)
            out = root / "master.wav"
            placed_path = root / "voice-timing.json"
            narrate.mix(voice_dir, score, out, duck=0.8, starts_path=starts_path,
                        target_lufs=-14, ceiling_dbfs=-1.5,
                        timing_out=placed_path, stems_dir=root)
            placed = json.loads(placed_path.read_text())
            self.assertEqual([row["start"] for row in placed], [0.3, 1.8])
            self.assertEqual([row["end"] for row in placed], [1.0, 2.5])
            voice, _ = narrate.read_wav(root / "voice-stem.wav")
            music, _ = narrate.read_wav(root / "music-stem.wav")
            with wave.open(str(out), "rb") as handle:
                self.assertEqual(handle.getnframes(), sr * 3)
                channels = handle.getnchannels()
                master = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
                master = master.reshape(-1, channels).astype(np.float32) / 32768
            self.assertEqual(channels, 2)
            # Both channels are the sum of the measured buses, without the old
            # circular stereo delay wrapping the ending to the beginning.
            self.assertLess(float(np.max(np.abs(master[:, 0] - (voice + music)))), 4 / 32768)
            self.assertTrue(np.array_equal(master[:, 0], master[:, 1]))
            measured = measure_stems(root / "voice-stem.wav", root / "music-stem.wav", 3)
            self.assertGreater(measured["voice_above_music_db"], 6)

    def test_voice_wav_cannot_disagree_with_recorded_timing(self):
        sr = narrate.SR
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            voice_dir = root / "voice"
            voice_dir.mkdir()
            narrate.V.write_wav(voice_dir / "1.wav", np.ones(sr, np.float32) * 0.1)
            (voice_dir / "timing.json").write_text(json.dumps([
                {"shot": "a", "file": "1.wav", "vo": 0.5, "text": "hello"}]))
            starts = root / "starts.json"
            starts.write_text(json.dumps([{"id": "a", "start": 0, "end": 2, "voStart": 0.3}]))
            score = root / "score.wav"
            narrate.V.write_wav(score, np.ones(sr * 2, np.float32) * 0.01)
            with self.assertRaisesRegex(ValueError, "duration does not match"):
                narrate.mix(voice_dir, score, root / "out.wav", starts_path=starts)
            self.assertFalse((root / "out.wav").exists())

    def test_score_clock_mismatch_is_refused_before_output(self):
        sr = narrate.SR
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            voice_dir = root / "voice"
            voice_dir.mkdir()
            narrate.V.write_wav(voice_dir / "1.wav", np.ones(sr // 2, np.float32) * 0.1)
            (voice_dir / "timing.json").write_text(json.dumps([
                {"shot": "a", "file": "1.wav", "vo": 0.5, "text": "hello"}]))
            starts = root / "starts.json"
            starts.write_text(json.dumps([{"id": "a", "start": 0, "end": 2, "voStart": 0.3}]))
            score = root / "score.wav"
            narrate.V.write_wav(score, np.zeros(sr, np.float32))
            with self.assertRaisesRegex(ValueError, "score duration"):
                narrate.mix(voice_dir, score, root / "out.wav", starts_path=starts)
            self.assertFalse((root / "out.wav").exists())


if __name__ == "__main__":
    unittest.main()
