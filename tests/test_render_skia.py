import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import validate_frames  # noqa: E402

# A real 7x5 JPEG produced by Skia, used to test header parsing without
# depending on an encoder being installed on the test machine.
MINIMAL_JPEG = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/4gHYSUNDX1BST0ZJTEUAAQEAAAHIAAAAAAQwAABtbnRyUkdCIFhZWiAH4AABAAEAAAAA"
    "AABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAAAADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlkZXNjAAAA8AAAACRyWFlaAAABFAAAABRnWFlaAAABKAAAABRiWFlaAAABPAAA"
    "ABR3dHB0AAABUAAAABRyVFJDAAABZAAAAChnVFJDAAABZAAAAChiVFJDAAABZAAAAChjcHJ0AAABjAAAADxtbHVjAAAAAAAA"
    "AAEAAAAMZW5VUwAAAAgAAAAcAHMAUgBHAEJYWVogAAAAAAAAb6IAADj1AAADkFhZWiAAAAAAAABimQAAt4UAABjaWFlaIAAA"
    "AAAAACSgAAAPhAAAts9YWVogAAAAAAAA9tYAAQAAAADTLXBhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAA"
    "AABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADb/2wBDAAMCAgMC"
    "AgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkF"
    "BQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAFAAcDASIAAhEB"
    "AxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAABv/E"
    "ABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AIkAPQp//9k="
)


class JpegFrameValidationTests(unittest.TestCase):
    def test_jpeg_dimensions_are_parsed_from_the_frame_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame-000000.jpg"
            path.write_bytes(base64.b64decode(MINIMAL_JPEG))
            self.assertEqual(validate_frames.jpeg_size(path), (7, 5))

    def test_a_jpeg_sequence_validates_against_its_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(3):
                (Path(tmp) / ("frame-%06d.jpg" % index)).write_bytes(base64.b64decode(MINIMAL_JPEG))
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"width": 7, "height": 5, "frame_count": 3}))
            report = validate_frames.validate(tmp, manifest)
            self.assertTrue(report["valid"])
            self.assertEqual(report["format"], "jpg")

    def test_a_mismatched_jpeg_dimension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "frame-000000.jpg").write_bytes(base64.b64decode(MINIMAL_JPEG))
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"width": 8, "height": 5, "frame_count": 1}))
            with self.assertRaisesRegex(ValueError, "Wrong frame dimensions"):
                validate_frames.validate(tmp, manifest)

    def test_a_gap_in_the_sequence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index in (0, 2):
                (Path(tmp) / ("frame-%06d.jpg" % index)).write_bytes(base64.b64decode(MINIMAL_JPEG))
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"width": 7, "height": 5, "frame_count": 2}))
            with self.assertRaisesRegex(ValueError, "gap"):
                validate_frames.validate(tmp, manifest)


class SkiaRendererScriptTests(unittest.TestCase):
    def setUp(self):
        self.script = ROOT / "video_studio" / "render_skia.js"
        self.source = self.script.read_text(encoding="utf-8")

    def test_the_script_is_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(  # noqa: S603 - fixed argv, resolved binary, no shell
            [node, "--check", str(self.script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_it_reuses_render_html_instead_of_reimplementing_the_visuals(self):
        self.assertIn("render.html", self.source)
        self.assertIn("window.drawFrame", self.source)
        self.assertIn("drawTransitionFrame", self.source)

    def test_it_enforces_the_same_limits_as_the_browser_renderer(self):
        self.assertIn("MAX_FRAMES = 30000", self.source)
        self.assertIn("MAX_SECONDS = 1000", self.source)
        self.assertIn("width < 320 || width > 3840", self.source)
        self.assertIn("height < 180 || height > 3840", self.source)

    def test_a_missing_canvas_library_exits_with_cannot_run(self):
        self.assertIn("@napi-rs/canvas is not installed", self.source)
        self.assertIn("process.exit(3)", self.source)

    def test_it_reports_missing_fonts_instead_of_falling_back_silently(self):
        self.assertIn("bundled fonts did not register", self.source)


if __name__ == "__main__":
    unittest.main()
