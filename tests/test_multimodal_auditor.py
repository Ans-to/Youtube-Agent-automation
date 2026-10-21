import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "video_studio" / "multimodal_auditor.py"
SPEC = importlib.util.spec_from_file_location("multimodal_auditor", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class MultimodalAuditorTests(unittest.TestCase):
    def complete_coverage(self):
        return {name: "complete" for name in AUDIT.REQUIRED_CAPABILITIES}

    def test_clean_complete_audit_uses_required_pass_message(self):
        report = AUDIT.build_report({
            "duration_seconds": 90,
            "coverage": self.complete_coverage(),
            "findings": [],
        })
        self.assertEqual(report["audit_status"], "PASSED")
        self.assertEqual(report["summary"], "AUDIT STATUS: PASSED - No violations detected.")
        self.assertEqual(report["coverage"]["missing_capabilities"], [])

    def test_missing_detector_coverage_never_claims_pass(self):
        report = AUDIT.build_report({"duration_seconds": 20, "coverage": {}, "findings": []})
        self.assertEqual(report["audit_status"], "INCOMPLETE")
        self.assertGreater(len(report["coverage"]["missing_capabilities"]), 0)

    def test_timestamped_finding_has_required_output_fields(self):
        report = AUDIT.build_report({
            "duration_seconds": 120,
            "coverage": self.complete_coverage(),
            "findings": [{
                "start_seconds": 5.2, "end_seconds": 8.9, "rule": "violence_gore",
                "description": "Two people appear to strike each other.",
                "confidence": 0.91, "source": "vision_temporal_v1",
            }],
        })
        self.assertEqual(report["audit_status"], "FLAGGED")
        finding = report["findings"][0]
        self.assertEqual(finding["Timestamp"], "00:00:05 - 00:00:08")
        self.assertEqual(finding["Violation Category"], "Content Safety")
        self.assertEqual(finding["Rule Broken"], "Violence & Gore")
        self.assertEqual(finding["Confidence Score"], "91%")
        self.assertIn("Description", finding)

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "confidence"):
            AUDIT.build_report({
                "coverage": self.complete_coverage(),
                "findings": [{"start": 0, "end": 1, "rule": "profanity",
                              "description": "bad", "confidence": 1.2}],
            })

    def test_rejects_end_before_start(self):
        with self.assertRaisesRegex(ValueError, "precedes"):
            AUDIT.build_report({
                "coverage": self.complete_coverage(),
                "findings": [{"start": 5, "end": 2, "rule": "profanity",
                              "description": "bad", "confidence": 0.8}],
            })

    def test_rejects_event_beyond_video_duration(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            AUDIT.build_report({
                "duration_seconds": 10, "coverage": self.complete_coverage(),
                "findings": [{"start": 9, "end": 12, "rule": "profanity",
                              "description": "bad", "confidence": 0.8}],
            })

    def test_formats_hours_longer_than_one_day(self):
        self.assertEqual(AUDIT.timestamp(90061), "25:01:01")


if __name__ == "__main__":
    unittest.main()
