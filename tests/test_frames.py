import json
import struct
import tempfile
import unittest
from pathlib import Path

from video_studio.validate_frames import PNG_SIGNATURE, validate


def fake_png(width, height):
    return PNG_SIGNATURE + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"


class FrameValidationTests(unittest.TestCase):
    def test_validates_frame_count_and_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            for index in range(2):
                (frames / ("frame-%06d.png" % index)).write_bytes(fake_png(320, 568) + b"x" * 100)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"width": 320, "height": 568, "frame_count": 2}), encoding="utf-8")
            result = validate(frames, manifest)
            self.assertTrue(result["valid"])
            self.assertEqual(result["frame_count"], 2)

    def test_rejects_wrong_frame_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            (frames / "frame-000000.png").write_bytes(fake_png(1920, 1080) + b"x" * 100)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"width": 1080, "height": 1920, "frame_count": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Wrong frame dimensions"):
                validate(frames, manifest)


if __name__ == "__main__":
    unittest.main()
