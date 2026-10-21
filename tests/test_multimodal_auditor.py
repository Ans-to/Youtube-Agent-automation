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

    def test_findings_do_not_hide_missing_coverage(self):
        report = AUDIT.build_report({
            "duration_seconds": 10,
            "coverage": {},
            "findings": [{"start": 1, "end": 2, "rule": "profanity",
                          "description": "A profanity was detected.",
                          "confidence": 0.8}],
        })
        self.assertEqual(report["audit_status"], "INCOMPLETE")
        self.assertIn("INCOMPLETE", report["summary"])
        self.assertEqual(len(report["findings"]), 1)

    def test_detector_failure_is_reported_as_failed(self):
        coverage = self.complete_coverage()
        coverage["ocr"] = "failed"
        report = AUDIT.build_report({"duration_seconds": 10, "coverage": coverage, "findings": []})
        self.assertEqual(report["audit_status"], "INCOMPLETE")
        self.assertEqual(report["coverage"]["failed_capabilities"]["ocr"], "failed")

    def test_rejects_non_list_findings(self):
        with self.assertRaisesRegex(ValueError, "findings must be a list"):
            AUDIT.build_report({"coverage": self.complete_coverage(), "findings": {}})

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

    def test_technical_qc_converts_silence_black_frames_and_av_timing(self):
        findings = AUDIT.technical_findings({
            "duration_seconds": 12,
            "audio_stream_count": 1,
            "checks": {
                "black_frames": {"threshold_seconds": 0.2, "events": [
                    {"start": 3.0, "end": 3.5, "duration": 0.5}
                ]},
                "freezes": {"events": [
                    {"start": 6.0, "end": 9.0, "duration": 3.0}
                ]},
                "audio_silence": {"threshold_seconds": 1.5, "events": [
                    {"start": 1.0, "end": 3.0, "duration": 2.0}
                ]},
                "audio_timing": {"verified": False},
                "audio_loudness": {"available": True, "integrated_lufs": -30.0,
                                   "min_loudness_lufs": -24.0, "true_peak_dbfs": -0.5,
                                   "max_true_peak_dbfs": -1.0}
            }
        })
        self.assertEqual(
            [f["rule"] for f in findings],
            ["black_screen", "frozen_frame", "dead_air", "av_sync", "audio_levels", "audio_levels"],
        )
        report = AUDIT.build_report({
            "duration_seconds": 12,
            "coverage": self.complete_coverage(),
            "findings": findings,
        })
        self.assertEqual(report["audit_status"], "FLAGGED")
        self.assertEqual(len(report["findings"]), 6)

    def test_photosensitivity_screening_becomes_a_timestamped_flag(self):
        findings = AUDIT.technical_findings({
            "duration_seconds": 4,
            "audio_stream_count": 1,
            "checks": {
                "photosensitivity": {"available": True, "events": [{
                    "start": 1.0, "end": 1.8, "transition_count": 8, "window_seconds": 1.0
                }]}
            }
        })
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule"], "photosensitivity")
        self.assertEqual(findings[0]["start_seconds"], 1.0)
        report = AUDIT.build_report({
            "duration_seconds": 4,
            "coverage": self.complete_coverage(),
            "findings": findings,
        })
        self.assertEqual(report["audit_status"], "FLAGGED")
        self.assertEqual(report["findings"][0]["Violation Category"], "Technical QA")
        self.assertEqual(report["findings"][0]["Rule Broken"], "Rapid Flashing / Photosensitivity")

    def test_timestamp_rejects_invalid_minute_and_second_ranges(self):
        for invalid in ("00:61:00", "00:00:61"):
            with self.assertRaisesRegex(ValueError, "invalid timestamp"):
                AUDIT.parse_timestamp(invalid)

    def test_formats_hours_longer_than_one_day(self):
        self.assertEqual(AUDIT.timestamp(90061), "25:01:01")


if __name__ == "__main__":
    unittest.main()
