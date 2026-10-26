"""Tests for the subtitle writer used before a film is uploaded."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import film_subtitles  # noqa: E402


def lines_file(tmp: Path, lines: list[dict]) -> Path:
    path = tmp / "lines.json"
    path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
    return path


class SplitCueTests(unittest.TestCase):
    def test_a_short_line_is_one_cue(self):
        cues = film_subtitles.split_cue("One page, one prompt.", 1.0, 3.0)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0][2], "One page, one prompt.")
        self.assertAlmostEqual(cues[0][0], 1.0)
        self.assertAlmostEqual(cues[0][1], 3.0)

    def test_cues_never_overlap_and_cover_the_line(self):
        text = ("You describe what you want in plain English. An agent writes it, "
                "on GitHub, while you watch. Then you read the change.")
        cues = film_subtitles.split_cue(text, 4.0, 12.0)
        self.assertGreater(len(cues), 1)
        self.assertAlmostEqual(cues[0][0], 4.0)
        self.assertAlmostEqual(cues[-1][1], 12.0)
        for before, after in zip(cues, cues[1:]):
            self.assertAlmostEqual(before[1], after[0])
        self.assertEqual(" ".join(cue[2] for cue in cues), text)

    def test_text_is_never_dropped(self):
        cues = film_subtitles.split_cue(
            "Start with one page, one prompt, one pull request, then do it again tomorrow.",
            0.0, 9.0)
        self.assertEqual(" ".join(cue[2] for cue in cues),
                         "Start with one page, one prompt, one pull request, then do it again tomorrow.")

    def test_a_cue_fits_on_two_lines(self):
        for cue in film_subtitles.split_cue("An agent writes it, on GitHub, while you watch. " * 2,
                                            0.0, 20.0):
            wrapped = film_subtitles.wrap(cue[2])
            self.assertLessEqual(len(wrapped.splitlines()), film_subtitles.MAX_LINES)
            self.assertLessEqual(len(wrapped.splitlines()[0]), film_subtitles.MAX_CHARS)


class SubtitleFileTests(unittest.TestCase):
    def test_writes_valid_srt_and_vtt(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [
                {"id": "L001", "text": "This is how you build a real app.", "start": 0.0, "end": 2.5},
                {"id": "L002", "text": "An agent writes the change.", "start": 3.0, "end": 5.5},
            ])
            code = film_subtitles.main([str(lines),
                                        "--srt", str(tmp / "out.srt"),
                                        "--vtt", str(tmp / "out.vtt")])
            self.assertEqual(code, 0)
            srt = (tmp / "out.srt").read_text(encoding="utf-8")
            vtt = (tmp / "out.vtt").read_text(encoding="utf-8")
            self.assertTrue(vtt.startswith("WEBVTT"))
            self.assertIn("00:00:00,000 --> 00:00:02,500", srt)
            self.assertIn("An agent writes the change.", srt)

    def test_a_synthesiser_spelling_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [
                {"id": "L001", "text": "The code is on github dot com.", "start": 0.0, "end": 2.0},
            ])
            self.assertEqual(film_subtitles.main([str(lines),
                                                  "--srt", str(tmp / "out.srt"),
                                                  "--vtt", str(tmp / "out.vtt")]), 1)
            self.assertFalse((tmp / "out.srt").exists())

    def test_an_empty_line_list_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [{"id": "L001", "text": "   ", "start": 0.0, "end": 2.0}])
            self.assertEqual(film_subtitles.main([str(lines),
                                                  "--srt", str(tmp / "out.srt"),
                                                  "--vtt", str(tmp / "out.vtt")]), 1)

    def test_a_line_that_ends_before_it_starts_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [{"id": "L001", "text": "A line.", "start": 4.0, "end": 2.0}])
            self.assertEqual(film_subtitles.main([str(lines)]), 1)


class DriverTests(unittest.TestCase):
    def test_the_render_driver_writes_the_track_beside_the_film(self):
        import render_authored_film

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [
                {"id": "L001", "text": "You describe the page and the agent writes it.",
                 "start": 0.0, "end": 3.0},
            ])
            report = render_authored_film.write_subtitles(lines, tmp)
            self.assertEqual(report["cues"], 1)
            self.assertTrue((tmp / "film.srt").is_file())
            self.assertTrue((tmp / "film.vtt").read_text(encoding="utf-8").startswith("WEBVTT"))

    def test_the_driver_refuses_a_track_with_a_synthesiser_spelling(self):
        import render_authored_film

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            lines = lines_file(tmp, [
                {"id": "L001", "text": "It is on github dot io.", "start": 0.0, "end": 3.0},
            ])
            with self.assertRaises(RuntimeError):
                render_authored_film.write_subtitles(lines, tmp)
            self.assertFalse((tmp / "film.srt").exists())


if __name__ == "__main__":
    unittest.main()
