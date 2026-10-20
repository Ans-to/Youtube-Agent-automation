import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import orchestrate


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "workspace").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_video_package(self, rendered=False):
        package = self.root / "workspace" / "orchestration" / "task-1" / "video-production"
        package.mkdir(parents=True)
        (package / "script.md").write_text("# Demo\n\nA valid test script.\n", encoding="utf-8")
        storyboard = {
            "title": "Validation fixture",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "scenes": [{"headline": "A test scene", "duration_seconds": 1}],
        }
        (package / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
        package_status = {
            "status": "template_demo",
            "publishable": False,
            "published": False,
            "human_review_required": True,
        }
        result = {
            "tool": "video_studio",
            "status": "completed",
            "artifact_dir": "workspace/orchestration/task-1/video-production",
            "render_expected": rendered,
        }
        if rendered:
            video = package / "video.mp4"
            video.write_bytes(b"V" * 2048)
            digest = hashlib.sha256(video.read_bytes()).hexdigest()
            package_status.update({
                "status": "technical_qa_passed_waiting_for_human_review",
                "quality_audit_passed": True,
                "quality_report_video_sha256": digest,
            })
            (package / "video.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nDemo\n", encoding="utf-8")
            (package / "video.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nDemo\n", encoding="utf-8")
            (package / "video.qc.json").write_text(json.dumps({
                "strict": True, "passed": True, "video_sha256": digest
            }), encoding="utf-8")
        (package / "package-status.json").write_text(json.dumps(package_status), encoding="utf-8")
        return result, package

    def test_video_package_must_exist_and_be_well_formed(self):
        result, _ = self.write_video_package()
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed")
        self.assertEqual(result["status"], "completed")

    def test_render_is_failed_when_mp4_subtitles_or_quality_report_are_missing(self):
        result, _ = self.write_video_package(rendered=True)
        package = self.root / result["artifact_dir"]
        (package / "video.mp4").unlink()
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("video.mp4" in error for error in checks[0]["errors"]))

    def test_render_requires_strict_pass_and_a_hash_bound_to_exact_mp4(self):
        result, package = self.write_video_package(rendered=True)
        report_path = package / "video.qc.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["video_sha256"] = "incorrect-hash"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("hash does not match" in error for error in checks[0]["errors"]))

    def test_product_html_status_and_zip_are_verified(self):
        base = self.root / "workspace" / "orchestration" / "task-2" / "product-prototype"
        product = base / "utility"
        product.mkdir(parents=True)
        (product / "index.html").write_text("<!doctype html><html><head></head><body>Utility</body></html>", encoding="utf-8")
        (product / "README.md").write_text("# Utility\n\nDraft prototype.\n", encoding="utf-8")
        status = {
            "status": "draft",
            "generated_by": "deterministic_template",
            "external_patterns_found": [],
            "human_review_required": True,
            "published": False,
        }
        (product / "product-status.json").write_text(json.dumps(status), encoding="utf-8")
        with zipfile.ZipFile(base / "utility.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(product / "index.html", arcname="utility/index.html")
        result = {
            "tool": "product_studio",
            "status": "completed",
            "artifact_dir": "workspace/orchestration/task-2/product-prototype",
        }
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed")
        self.assertEqual(result["status"], "completed")

    def test_product_missing_archive_is_not_reported_as_success(self):
        base = self.root / "workspace" / "orchestration" / "task-3" / "product-prototype"
        product = base / "utility"
        product.mkdir(parents=True)
        (product / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
        (product / "README.md").write_text("# Draft", encoding="utf-8")
        (product / "product-status.json").write_text(json.dumps({
            "status": "draft", "external_patterns_found": [],
            "human_review_required": True, "published": False,
        }), encoding="utf-8")
        result = {
            "tool": "product_studio",
            "status": "completed",
            "artifact_dir": "workspace/orchestration/task-3/product-prototype",
        }
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("utility.zip" in error for error in checks[0]["errors"]))

    def test_artifact_path_cannot_escape_workspace(self):
        result = {
            "tool": "video_studio",
            "status": "completed",
            "artifact_dir": "../outside",
        }
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("escapes" in error for error in checks[0]["errors"]))


if __name__ == "__main__":
    unittest.main()
