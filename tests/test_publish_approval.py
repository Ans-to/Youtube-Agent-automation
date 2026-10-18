import tempfile
import unittest
from pathlib import Path

from video_studio.publish_youtube import sha256, validate_approval


class PublishApprovalTests(unittest.TestCase):
    def make_package(self, directory):
        root = Path(directory)
        video = root / "video.mp4"
        video.write_bytes(b"fake video bytes for approval hashing")
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
            "approved_metadata": metadata,
        }
        return video, metadata, approval

    def test_accepts_exact_video_and_metadata_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
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

    def test_rejects_wrong_package_path(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["package_dir"] = str(Path(directory).parent.resolve())
            with self.assertRaisesRegex(ValueError, "parent directory"):
                validate_approval(approval, video.resolve(), metadata)


if __name__ == "__main__":
    unittest.main()
