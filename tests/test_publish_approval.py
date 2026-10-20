import json
import tempfile
import unittest
from pathlib import Path

from video_studio.publish_youtube import sha256, validate_approval, claim_upload_attempt


class PublishApprovalTests(unittest.TestCase):
    def make_package(self, directory):
        root = Path(directory)
        video = root / "video.mp4"
        video.write_bytes(b"fake video bytes for approval hashing")
        script = root / "script.md"
        script.write_text("approved narration", encoding="utf-8")
        storyboard = root / "storyboard.json"
        storyboard.write_text("{\"scenes\": []}", encoding="utf-8")
        qc_report_path = root / "video.qc.json"
        qc_report = {
            "file": str(video.resolve()),
            "video_sha256": sha256(video),
            "duration_seconds": 12.5,
            "audio_stream_count": 1,
            "warnings": [],
            "passed": True,
            "strict": True,
        }
        qc_report_path.write_text(json.dumps(qc_report), encoding="utf-8")
        metadata = {
            "title": "Approved title",
            "description": "Approved description",
            "tags": ["AI", "Technology"],
            "privacy": "private",
            "made_for_kids": "no",
        }
        approval = {
            "approved": True,
            "package_dir": str(root.resolve()),
            "video_file": str(video.resolve()),
            "video_sha256": sha256(video),
            "script_sha256": sha256(script),
            "storyboard_sha256": sha256(storyboard),
            "quality_audit_passed": True,
            "qc_report_sha256": sha256(qc_report_path),
            "approved_metadata": {**metadata, "tags": list(metadata["tags"])},
        }
        return video, metadata, approval

    def test_accepts_exact_video_and_metadata_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            self.assertEqual(validate_approval(approval, video.resolve(), metadata), metadata)

    def test_rejects_reuse_of_approval_after_successful_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["upload"] = {
                "uploaded": True,
                "video_id": "already-uploaded-id",
                "privacy": "private",
            }
            with self.assertRaisesRegex(ValueError, "already been used for an upload"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_reuse_when_previous_upload_outcome_is_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["upload"] = {
                "status": "in_progress",
                "uploaded": False,
                "outcome": "unknown_until_confirmed",
            }
            with self.assertRaisesRegex(ValueError, "uncertain outcome"):
                validate_approval(approval, video.resolve(), metadata)

    def test_claim_persists_fail_closed_marker_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            claimed, approved = claim_upload_attempt(approval_path, video.resolve(), metadata, "private")
            self.assertEqual(approved, metadata)
            self.assertEqual(claimed["upload"]["status"], "in_progress")
            self.assertEqual(claimed["upload"]["video_sha256"], sha256(video))
            saved = json.loads(approval_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["upload"]["status"], "in_progress")
            with self.assertRaisesRegex(ValueError, "uncertain outcome"):
                validate_approval(saved, video.resolve(), metadata)
            self.assertFalse(Path(str(approval_path) + ".upload.lock").exists())

    def test_claim_refuses_an_existing_upload_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval_path = Path(directory) / "approval.json"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            Path(str(approval_path) + ".upload.lock").write_text("other process", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Another upload process"):
                claim_upload_attempt(approval_path, video.resolve(), metadata, "private")
            saved = json.loads(approval_path.read_text(encoding="utf-8"))
            self.assertNotIn("upload", saved)

    def test_does_not_reject_incomplete_upload_record(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["upload"] = {"uploaded": False}
            self.assertEqual(validate_approval(approval, video.resolve(), metadata), metadata)

    def test_rejects_changed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            metadata["privacy"] = "public"
            with self.assertRaisesRegex(ValueError, "differs from the approved record"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_modified_video_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            video.write_bytes(b"changed after approval")
            with self.assertRaisesRegex(ValueError, "Video changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_script_changed_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            (Path(directory) / "script.md").write_text("changed narration", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Script changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_storyboard_changed_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            (Path(directory) / "storyboard.json").write_text("{\"scenes\": [\"changed\"]}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Storyboard changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_wrong_package_path(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["package_dir"] = str(Path(directory).parent.resolve())
            with self.assertRaisesRegex(ValueError, "parent directory"):
                validate_approval(approval, video.resolve(), metadata)


if __name__ == "__main__":
    unittest.main()
