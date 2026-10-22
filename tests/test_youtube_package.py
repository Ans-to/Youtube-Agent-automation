"""The upload package has to be usable, not decorative.

A chapter list that starts anywhere but 00:00 is silently ignored by YouTube, and
a chapter shorter than ten seconds is dropped, which can leave two chapters and
no list at all. Both failures are invisible until the video is published, so the
builder refuses them here instead.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import youtube_package  # noqa: E402


def film(scenes, duration=600.0):
    return {
        "title": "A film",
        "duration_seconds": duration,
        "scenes": [{"id": f"s{i}", "chapter": label, "start": start, "end": start + 30}
                   for i, (label, start) in enumerate(scenes)],
    }


class StampTests(unittest.TestCase):
    def test_under_an_hour_is_minutes_and_seconds(self):
        self.assertEqual(youtube_package.stamp(0), "00:00")
        self.assertEqual(youtube_package.stamp(605), "10:05")

    def test_over_an_hour_keeps_the_hours(self):
        self.assertEqual(youtube_package.stamp(3725), "1:02:05")


class ChapterTests(unittest.TestCase):
    def test_the_first_chapter_starts_at_zero(self):
        package = youtube_package.build(
            film([("Intro", 3.0), ("One", 60.0), ("Two", 120.0), ("Three", 180.0)]),
            title="T", description="", tags=None, site=None)
        self.assertEqual(package["chapters"][0]["at"], 0.0)
        self.assertTrue(package["chapters_ok"])

    def test_a_chapter_that_is_too_short_is_merged_away(self):
        package = youtube_package.build(
            film([("A", 0.0), ("B", 4.0), ("C", 90.0), ("D", 200.0)]),
            title="T", description="", tags=None, site=None)
        starts = [c["at"] for c in package["chapters"]]
        self.assertTrue(all(b - a >= 10 for a, b in zip(starts, starts[1:])), starts)
        self.assertNotIn(4.0, starts)

    def test_two_chapters_is_an_error_not_a_quiet_failure(self):
        with self.assertRaises(ValueError):
            youtube_package.build(film([("A", 0.0), ("B", 300.0)]),
                                  title="T", description="", tags=None, site=None)

    def test_a_chapter_at_the_very_end_is_trimmed(self):
        package = youtube_package.build(
            film([("A", 0.0), ("B", 120.0), ("C", 240.0), ("Last", 595.0)], duration=600.0),
            title="T", description="", tags=None, site=None)
        self.assertNotEqual(package["chapters"][-1]["label"], "Last")


class DescriptionTests(unittest.TestCase):
    def test_the_description_lists_every_chapter(self):
        package = youtube_package.build(
            film([("Intro", 0.0), ("Connect", 100.0), ("Merge", 200.0)]),
            title="T", description="A line about the video.", tags=["a"], site="github.com/x/y")
        text = package["description"]
        self.assertIn("A line about the video.", text)
        self.assertIn("01:40  Connect", text)
        self.assertIn("github.com/x/y", text)

    def test_no_duration_is_an_error(self):
        with self.assertRaises(ValueError):
            youtube_package.build({"scenes": []}, title="T", description="", tags=None, site=None)


class CommandLineTests(unittest.TestCase):
    def test_it_writes_a_file_beside_the_film(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "film.json"
            path.write_text(json.dumps(film([("Intro", 0.0), ("One", 120.0), ("Two", 240.0)])),
                            encoding="utf-8")
            code = youtube_package.main(["--film", str(path), "--title", "T",
                                         "--tags", "one, two"])
            self.assertEqual(code, 0)
            written = json.loads((Path(tmp) / "youtube.json").read_text(encoding="utf-8"))
            self.assertEqual(written["title"], "T")
            self.assertEqual(written["tags"], ["one", "two"])

    def test_a_missing_film_is_reported_not_crashed(self):
        self.assertEqual(youtube_package.main(["--film", "/nope/film.json", "--title", "T"]), 2)


if __name__ == "__main__":
    unittest.main()
