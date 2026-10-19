import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "video_studio" / "quality_audit.py"
SPEC = importlib.util.spec_from_file_location("quality_audit", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class QualityAuditParsingTests(unittest.TestCase):
    def test_parses_black_intervals(self):
        text = "black_start:1.000 black_end:1.300 black_duration:0.300"
        self.assertEqual(AUDIT.intervals(text, r"black_start:([0-9.]+)",
                                         r"black_end:([0-9.]+)"),
                         [{"start": 1.0, "end": 1.3, "duration": 0.3}])

    def test_ignores_unmatched_intervals_fail_safely(self):
        self.assertEqual(AUDIT.intervals("black_start:2.000", r"black_start:([0-9.]+)",
                                         r"black_end:([0-9.]+)"), [])

    def test_detects_silence_continuing_to_eof(self):
        events = AUDIT.parse_silence_events("silence_start:8.000", 10.0)
        self.assertEqual(events, [{"start": 8.0, "end": 10.0, "duration": 2.0,
                                   "continues_to_eof": True}])

    def test_pairs_closed_silence_intervals(self):
        events = AUDIT.parse_silence_events(
            "silence_start:1.000 silence_end:2.000", 5.0)
        self.assertEqual(events, [{"start": 1.0, "end": 2.0, "duration": 1.0}])

    def test_missing_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "missing or too small"):
                AUDIT.audit(Path(tmp) / "missing.mp4")


if __name__ == "__main__":
    unittest.main()
