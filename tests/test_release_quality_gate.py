"""Fail-closed tests for technical QA and the YouTube release gate."""
import json
import tempfile
import unittest
from pathlib import Path

from video_studio.quality_audit import file_sha256
from video_studio.release_gate import validate_qc_report
from video_studio.publish_youtube import validate_approval


class ReleaseQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"test video bytes " * 256)
        self.script = self.root / "script.md"
        self.script.write_text("# Reviewed script\n", encoding="utf-8")
        self.storyboard = self.root / "storyboard.json"
        self.storyboard.write_text('{"scenes": []}\n', encoding="utf-8")
        self.qc_path = self.root / "video.qc.json"
        self.report = {
            "file": str(self.video),
            "video_sha256": file_sha256(self.video),
            "duration_seconds": 12.5,
            "audio_stream_count": 1,
            "warnings": [],
            "passed": True,
            "strict": True,
        }
        self.write_report()
        self.metadata = {
            "title": "Test title",
            "description": "Test description",
            "tags": ["test"],
            "privacy": "private",
            "made_for_kids": "no",
        }
        self.approval = {
            "approved": True,
            "video_file": str(self.video),
            "video_sha256": file_sha256(self.video),
            "package_dir": str(self.root),
            "script_sha256": file_sha256(self.script),
            "storyboard_sha256": file_sha256(self.storyboard),
            "approved_metadata": self.metadata,
            "quality_audit_passed": True,
            "qc_report_sha256": file_sha256(self.qc_path),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_report(self):
        self.qc_path.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")

    def test_strict_passing_report_is_accepted(self):
        self.assertTrue(validate_qc_report(self.report, self.video))

    def test_non_strict_report_is_rejected(self):
        report = dict(self.report, strict=False)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_failed_report_is_rejected(self):
        report = dict(self.report, passed=False)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_report_for_different_video_is_rejected(self):
        report = dict(self.report, video_sha256="0" * 64)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_report_with_warnings_or_no_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_qc_report(dict(self.report, warnings=["black frame"]), self.video)
        with self.assertRaises(ValueError):
            validate_qc_report(dict(self.report, audio_stream_count=0), self.video)

    def test_upload_requires_unchanged_passing_audit(self):
        approved = validate_approval(self.approval, self.video, self.metadata)
        self.assertEqual(approved, self.metadata)
        self.qc_path.write_text(json.dumps(dict(self.report, passed=False)), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_approval(self.approval, self.video, self.metadata)

    def test_upload_rejects_approval_without_qc_binding(self):
        approval = dict(self.approval)
        approval.pop("qc_report_sha256")
        with self.assertRaises(ValueError):
            validate_approval(approval, self.video, self.metadata)


if __name__ == "__main__":
    unittest.main()
