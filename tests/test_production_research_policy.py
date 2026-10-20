"""Regression tests for the content pipeline's research-first policy."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_studio.production import run_strict_quality_audit, should_collect_research
from video_studio.quality_audit import file_sha256


class ResearchPolicyTests(unittest.TestCase):
    def test_research_is_default_for_non_template_packages(self):
        self.assertTrue(should_collect_research(research_requested=False, render_template=False))

    def test_offline_template_smoke_stays_network_free_by_default(self):
        self.assertFalse(should_collect_research(research_requested=False, render_template=True))

    def test_explicit_research_is_honored_for_any_mode(self):
        self.assertTrue(should_collect_research(research_requested=True, render_template=True))


    def test_automatic_quality_audit_accepts_a_strict_report_bound_to_video(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            video = output_dir / "video.mp4"
            video.write_bytes(b"video bytes " * 100)
            report = {
                "file": str(video.resolve()),
                "video_sha256": file_sha256(video),
                "duration_seconds": 12.5,
                "audio_stream_count": 1,
                "warnings": [],
                "passed": True,
                "strict": True,
            }
            (output_dir / "video.qc.json").write_text(json.dumps(report), encoding="utf-8")
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            with patch("video_studio.production.subprocess.run", return_value=completed):
                self.assertEqual(run_strict_quality_audit(output_dir), report)

    def test_automatic_quality_audit_blocks_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="audit failed")
            with patch("video_studio.production.subprocess.run", return_value=completed):
                with self.assertRaises(RuntimeError):
                    run_strict_quality_audit(Path(directory))


if __name__ == "__main__":
    unittest.main()
