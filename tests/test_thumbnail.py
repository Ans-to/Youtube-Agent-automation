"""The thumbnail is a poster, not a frame.

Half of a video's fate is decided before anyone presses play, so the thumbnail
gets the same treatment as the film: built by code from the brief, and checked
against the rules that decide whether it works at the size it is actually seen.

These tests read the real PNG the generator writes. A thumbnail that is blank, or
that puts its promise somewhere YouTube covers with a duration badge, fails here
rather than in a feed.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
GENERATOR = STUDIO / "films" / "thumbnail.mjs"
BRIEF = ROOT / "video_studio" / "briefs" / "review-ai-code.json"
DELIVERED = ROOT / "docs" / "media" / "review-ai-code-thumbnail.png"

NODE = shutil.which("node")


def ink_share(png: Path, region=(0.0, 0.0, 1.0, 1.0)) -> float:
    """Share of pixels in a region that are darker than the pale field."""
    from PIL import Image
    image = Image.open(png).convert("L")
    width, height = image.size
    x0, y0, x1, y1 = region
    box = image.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)))
    pixels = list(box.getdata())
    dark = sum(1 for value in pixels if value < 170)
    return dark / max(1, len(pixels))


class TheThumbnailIsDrawnFromTheBrief(unittest.TestCase):
    def setUp(self):
        if NODE is None:
            self.skipTest("node is unavailable")
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "thumbnail.png"
        result = subprocess.run(
            [NODE, str(GENERATOR), "--brief", str(BRIEF), "--out", str(self.out)],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=180, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-800:])
        self.report = json.loads(result.stdout)

    def tearDown(self):
        if hasattr(self, "tmp"):
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_words_are_short_enough_to_read_in_a_feed(self):
        self.assertGreaterEqual(self.report["words"], 2)
        self.assertLessEqual(self.report["words"], 5)

    def test_it_is_the_size_youtube_wants(self):
        self.assertEqual(self.report["size"], "1280x720")

    def test_the_figure_is_on_it(self):
        """The claim is the biggest object: the left third has to carry ink."""
        self.assertGreater(ink_share(self.out, (0.03, 0.2, 0.42, 0.8)), 0.10)

    def test_the_bottom_right_corner_is_left_alone(self):
        """YouTube prints the duration there. Anything under it is lost."""
        self.assertLess(ink_share(self.out, (0.80, 0.78, 1.0, 1.0)), 0.03)

    def test_the_promise_is_not_a_blank_field(self):
        self.assertGreater(ink_share(self.out, (0.48, 0.2, 0.95, 0.8)), 0.05)

    def test_a_brief_with_no_thumbnail_line_is_refused(self):
        broken = self.tmp / "broken.json"
        brief = json.loads(BRIEF.read_text(encoding="utf-8"))
        brief["thumbnail"] = {"line": ""}
        broken.write_text(json.dumps(brief), encoding="utf-8")
        result = subprocess.run(
            [NODE, str(GENERATOR), "--brief", str(broken), "--out", str(self.tmp / "x.png")],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=180, check=False,
        )
        self.assertNotEqual(result.returncode, 0, "a poster with no promise was accepted")


class TheDeliveredThumbnailExists(unittest.TestCase):
    def test_the_file_ships_with_the_film(self):
        self.assertTrue(DELIVERED.is_file(), "docs/media/review-ai-code-thumbnail.png is missing")

    def test_it_has_contrast_at_feed_size(self):
        """Shrunk to 320 px and back, the composition must still be there."""
        if not DELIVERED.is_file():
            self.skipTest("no delivered thumbnail")
        from PIL import Image
        image = Image.open(DELIVERED).convert("L")
        small = image.resize((320, 180), Image.LANCZOS)
        values = list(small.getdata())
        self.assertGreater(max(values) - min(values), 120, "the poster is a grey rectangle")


if __name__ == "__main__":
    unittest.main()
