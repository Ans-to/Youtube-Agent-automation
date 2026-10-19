import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "video_studio" / "validate_render.py"
SPEC = importlib.util.spec_from_file_location("validate_render", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class AudioStatsTests(unittest.TestCase):
    def test_parses_normal_audio_measurements(self):
        stderr = "[Parsed_volumedetect_0] mean_volume: -22.4 dB\n[Parsed_volumedetect_0] max_volume: -2.1 dB\n"
        self.assertEqual(VALIDATOR.parse_audio_stats(stderr),
                         {"peak_dbfs": -2.1, "mean_dbfs": -22.4})

    def test_rejects_missing_measurements_instead_of_assuming_pass(self):
        with self.assertRaisesRegex(ValueError, "cannot pass on missing measurements"):
            VALIDATOR.parse_audio_stats("FFmpeg completed but no volume stats were emitted.")

    def test_parses_silent_audio_as_negative_infinity(self):
        stderr = "[Parsed_volumedetect_0] mean_volume: -inf dB\n[Parsed_volumedetect_0] max_volume: -inf dB\n"
        stats = VALIDATOR.parse_audio_stats(stderr)
        self.assertEqual(stats["peak_dbfs"], float("-inf"))
        self.assertEqual(stats["mean_dbfs"], float("-inf"))


if __name__ == "__main__":
    unittest.main()
