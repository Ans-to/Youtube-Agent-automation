import math
import random
import unittest

from video_studio.audit import audio, detectors


SR = 16_000


def tone(seconds=3.0, frequency=220.0, amplitude=0.3):
    return [
        amplitude * math.sin(2 * math.pi * frequency * index / SR)
        for index in range(int(SR * seconds))
    ]


def noise(seconds=3.0, amplitude=0.2, seed=1):
    # Deterministic test fixture, not a security primitive.
    generator = random.Random(seed)  # noqa: S311
    return [generator.uniform(-amplitude, amplitude) for _ in range(int(SR * seconds))]


def speech_like(seconds=4.0, seed=2):
    """Amplitude-modulated low-pass noise: syllable bursts separated by pauses."""
    generator = random.Random(seed)  # noqa: S311
    output = []
    previous = 0.0
    for index in range(int(SR * seconds)):
        previous = 0.85 * previous + 0.15 * generator.uniform(-1, 1)
        envelope = 1.0 if (index // 4000) % 2 == 0 else 0.0
        output.append(0.25 * envelope * previous)
    return output


class FeatureTests(unittest.TestCase):
    def test_fft_rejects_non_power_of_two(self):
        with self.assertRaises(ValueError):
            audio._fft([0.0] * 3, [0.0] * 3)

    def test_dbfs_floor_and_reference(self):
        self.assertEqual(audio.dbfs(0.0), -96.0)
        self.assertAlmostEqual(audio.dbfs(1.0), 0.0, places=6)
        self.assertAlmostEqual(audio.dbfs(0.5), -6.0206, places=3)

    def test_tonal_signal_concentrates_energy_in_one_band(self):
        profile = audio.analyze_samples(tone(frequency=200.0))
        self.assertTrue(profile.frames)
        self.assertGreater(profile.frames[0].low_ratio, 0.8)

    def test_white_noise_is_spectrally_flat(self):
        profile = audio.analyze_samples(noise())
        self.assertGreater(profile.frames[0].flatness, 0.2)
        self.assertGreater(profile.frames[0].zcr, 0.2)

    def test_empty_audio_is_handled(self):
        profile = audio.analyze_samples([])
        self.assertEqual(profile.frames, [])
        self.assertFalse(profile.music.present)
        self.assertEqual(profile.duration, 0.0)


class MusicEstimateTests(unittest.TestCase):
    def test_tonal_music_like_signal_is_detected(self):
        profile = audio.analyze_samples(tone(3.0))
        self.assertTrue(profile.music.present)
        self.assertGreater(profile.music.confidence, 50)
        self.assertIn("music bed", profile.music.reason)

    def test_white_noise_is_not_music(self):
        profile = audio.analyze_samples(noise(3.0))
        self.assertFalse(profile.music.present)

    def test_speech_like_pauses_reduce_music_confidently(self):
        profile = audio.analyze_samples(speech_like(4.0))
        self.assertFalse(profile.music.present)

    def test_silence_is_not_music(self):
        profile = audio.analyze_samples([0.0] * SR * 2)
        self.assertFalse(profile.music.present)
        self.assertIn("Too little audible audio", profile.music.reason)

    def test_estimate_is_labelled_a_heuristic(self):
        profile = audio.analyze_samples(tone(2.0))
        self.assertIn("behave", profile.music.reason.lower() + " behaves")
        # Confidence must never claim certainty.
        self.assertLessEqual(profile.music.confidence, 95.0)


class ClippingTests(unittest.TestCase):
    def test_clipped_signal_is_detected(self):
        clipped = [0.999 if index % 2 == 0 else -0.999 for index in range(SR * 2)]
        profile = audio.analyze_samples(clipped)
        self.assertTrue(profile.clipped_frames)
        findings = detectors.detect_clipping(profile)
        self.assertTrue(findings)
        self.assertEqual(findings[0].rule_id, "TQ-CLIPPING")
        self.assertIn("cannot be repaired", findings[0].description)

    def test_clean_signal_does_not_clip(self):
        profile = audio.analyze_samples(tone(amplitude=0.3))
        self.assertEqual(profile.clipped_frames, [])
        self.assertEqual(detectors.detect_clipping(profile), [])

    def test_peak_db_is_reported(self):
        profile = audio.analyze_samples(tone(amplitude=0.5))
        self.assertAlmostEqual(profile.peak_db, -6.02, places=1)


class LoudnessTests(unittest.TestCase):
    def test_quiet_program_is_flagged(self):
        profile = audio.analyze_samples(tone(amplitude=0.004))  # about -48 dBFS
        findings = detectors.detect_loudness(profile, min_seconds=1.0)
        self.assertTrue(findings)
        self.assertIn("dBFS", findings[0].description)

    def test_hot_program_is_flagged(self):
        profile = audio.analyze_samples(tone(amplitude=0.95), )  # about -0.4 dBFS
        findings = detectors.detect_loudness(profile, min_seconds=0.5)
        self.assertTrue(any("normalization" in finding.description for finding in findings))

    def test_reasonable_levels_pass(self):
        profile = audio.analyze_samples(tone(amplitude=0.2))  # about -14 dBFS
        self.assertEqual(detectors.detect_loudness(profile, min_seconds=0.5), [])


class LipSyncTests(unittest.TestCase):
    def test_aligned_mouth_motion_passes(self):
        rms = [(index * 0.1, 0.2 + 0.1 * (index % 5)) for index in range(100)]
        mouth = [(index * 0.1, 0.2 + 0.1 * (index % 5)) for index in range(100)]
        self.assertEqual(detectors.detect_lipsync(mouth, rms), [])

    def test_dead_mouth_is_flagged(self):
        rms = [(index * 0.1, 0.2 + 0.1 * (index % 5)) for index in range(100)]
        mouth = [(index * 0.1, 0.0) for index in range(100)]
        findings = detectors.detect_lipsync(mouth, rms)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "TQ-LIPSYNC")
        self.assertIn("do not correspond", findings[0].description)

    def test_delayed_mouth_is_flagged_with_direction(self):
        pattern = [1.0 if index % 10 == 0 else 0.0 for index in range(100)]
        rms = [(index * 0.1, value) for index, value in enumerate(pattern)]
        mouth = [(index * 0.1, pattern[index - 2]) for index in range(100)]
        findings = detectors.detect_lipsync(mouth, rms)
        self.assertEqual(len(findings), 1)
        self.assertIn("lags", findings[0].description)

    def test_insufficient_samples_are_ignored(self):
        self.assertEqual(detectors.detect_lipsync([(0.0, 0.1)], [(0.0, 0.1)]), [])


class FileAnalysisTests(unittest.TestCase):
    def test_analyze_file_returns_none_without_ffmpeg(self):
        from unittest.mock import patch

        with patch.object(audio.shutil, "which", return_value=None):
            self.assertIsNone(audio.analyze_file("whatever.mp4"))

    def test_invalid_sample_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            audio.analyze_samples([0.0] * 10, sample_rate=0)


if __name__ == "__main__":
    unittest.main()
