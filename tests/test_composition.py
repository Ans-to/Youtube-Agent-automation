"""Tests for the composition check.

The point of this check is that decoration cannot satisfy it. These tests build
the two cases that matter: a picture that is genuinely rearranged, and a picture
that is only wearing noise, and prove the verdict is different for each.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from video_studio import composition  # noqa: E402 - path set up above
import check_composition  # noqa: E402 - path set up above

# The project resolves FFmpeg in one place, including the imageio wheel that
# carries a binary on machines with no system package.
FFMPEG = composition.resolve_ffmpeg()


def thumbnails(*, count: int, change_every: int, base: int = 60) -> list[np.ndarray]:
    """A stream of 9x16 thumbnails: a new arrangement every ``change_every`` frames."""
    stream = []
    for index in range(count):
        layout = index // max(1, change_every)
        grid = np.zeros((composition.GRID_Y, composition.GRID_X), dtype=np.float32)
        # A bar whose position and width depend on the layout: a real rearrangement.
        column = (layout * 3) % composition.GRID_X
        grid[2:4, column:column + 4] = base
        grid[6, : max(1, (layout * 5) % composition.GRID_X)] = base - 20
        stream.append(grid)
    return stream


class SimilarityTests(unittest.TestCase):
    def test_a_layout_is_identical_to_itself(self):
        grid = np.zeros((9, 16), dtype=np.float32)
        grid[2, 4] = 100.0
        self.assertAlmostEqual(composition.similarity(grid, grid), 1.0, places=6)

    def test_brightness_and_contrast_do_not_count_as_change(self):
        # A fade: the same arrangement, dimmer. A viewer sees the same picture.
        grid = np.zeros((9, 16), dtype=np.float32)
        grid[2, 4] = 100.0
        self.assertAlmostEqual(composition.similarity(grid, grid * 0.4), 1.0, places=6)

    def test_two_flat_frames_are_the_same_picture(self):
        # The trap that made a still image look like movement: normalising noise
        # produces confident nonsense, so flat frames are never compared.
        black = np.zeros((9, 16), dtype=np.float32)
        noise = np.random.RandomState(7).normal(0.0, 0.8, (9, 16)).astype(np.float32)
        self.assertEqual(composition.similarity(black, noise), 1.0)
        self.assertFalse(composition.has_structure(noise))

    def test_a_moved_panel_is_a_different_arrangement(self):
        first = np.zeros((9, 16), dtype=np.float32)
        first[2:5, 1:6] = 90.0
        second = np.zeros((9, 16), dtype=np.float32)
        second[2:5, 9:14] = 90.0
        self.assertLess(composition.similarity(first, second), composition.CHANGE_BREAK)


class AnalyseTests(unittest.TestCase):
    def test_a_frozen_picture_is_one_hold_of_its_whole_length(self):
        frozen = [np.full((9, 16), 40.0, dtype=np.float32)] * 40
        report = composition.analyse_signatures(frozen, fps=2.0)
        self.assertEqual(len(report.holds), 1)
        self.assertEqual(report.holds[0].seconds, 20.0)

    def test_a_flat_card_with_noise_is_still_one_hold(self):
        rng = np.random.RandomState(3)
        noisy = [rng.normal(20.0, 0.6, (9, 16)).astype(np.float32) for _ in range(40)]
        report = composition.analyse_signatures(noisy, fps=2.0)
        self.assertEqual(len(report.holds), 1, "noise must not be read as movement")
        self.assertEqual(report.structures, 0)

    def test_a_picture_that_changes_every_four_seconds_reads_as_such(self):
        report = composition.analyse_signatures(
            thumbnails(count=40, change_every=8), fps=2.0)
        self.assertEqual(len(report.holds), 5)
        for hold in report.holds:
            self.assertAlmostEqual(hold.seconds, 4.0, places=3)

    def test_holds_cover_the_whole_file_without_gaps(self):
        report = composition.analyse_signatures(
            thumbnails(count=31, change_every=7), fps=2.0)
        self.assertEqual(report.holds[0].start, 0.0)
        self.assertAlmostEqual(report.holds[-1].end, 15.5, places=3)
        for first, second in zip(report.holds, report.holds[1:]):
            self.assertAlmostEqual(first.end, second.start, places=3)

    def test_no_frames_is_an_empty_report_rather_than_a_crash(self):
        report = composition.analyse_signatures([], fps=2.0)
        self.assertEqual(report.holds, [])
        self.assertEqual(report.duration_seconds, 0.0)


class VerdictTests(unittest.TestCase):
    def test_a_slideshow_fails_and_names_the_worst_hold(self):
        report = composition.analyse_signatures(
            thumbnails(count=120, change_every=120), fps=2.0)   # one 60 s layout
        verdict = composition.decide(report)
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["status"], "failed")
        self.assertIn("60.0 s", verdict["statement"])
        self.assertIn("0:00", verdict["statement"])

    def test_a_film_that_recuts_often_passes(self):
        report = composition.analyse_signatures(
            thumbnails(count=120, change_every=8), fps=2.0)     # a cut every 4 s
        verdict = composition.decide(report)
        self.assertTrue(verdict["passed"], verdict["statement"])
        self.assertEqual(verdict["compositions"], 15)

    def test_an_eight_second_hold_inside_a_lively_film_passes(self):
        stream = thumbnails(count=400, change_every=8)
        stream = stream + [stream[-1].copy() for _ in range(16)]   # 8 s
        report = composition.analyse_signatures(stream, fps=2.0)
        self.assertTrue(composition.decide(report)["passed"])

    def test_a_single_hold_over_the_limit_fails_however_short_the_share(self):
        # 600 s of cuts and one 15 s hold: 2.4% of the film. It still fails,
        # because the rule is about the frame a viewer is looking at, not the
        # average. The share is reported so the size of the job is visible.
        lively = thumbnails(count=1200, change_every=8)
        # A layout of its own, so the hold is exactly the 30 frames added and not
        # merged with whatever was on screen before it.
        plateau = np.zeros((composition.GRID_Y, composition.GRID_X), dtype=np.float32)
        plateau[7, :] = 80.0
        plateau[0, 0] = 40.0
        held = [plateau.copy() for _ in range(30)]
        verdict = composition.decide(
            composition.analyse_signatures(lively + held, fps=2.0))
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["status"], "failed")
        self.assertLess(verdict["share_over_limit"], 0.05)
        self.assertEqual(verdict["spans"][0]["seconds"], 15.0)

    def test_a_file_too_short_to_judge_is_not_a_pass(self):
        verdict = composition.decide(composition.analyse_signatures([], fps=2.0))
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["status"], "not_run")

    def test_the_limits_are_reported_so_a_verdict_can_be_audited(self):
        verdict = composition.decide(composition.analyse_signatures(
            thumbnails(count=20, change_every=5), fps=2.0))
        self.assertEqual(verdict["limit_seconds"], composition.MAX_HOLD_SECONDS)
        self.assertIn("share_over_limit", verdict)

    def test_the_report_is_readable_and_mentions_the_fix(self):
        verdict = composition.decide(composition.analyse_signatures(
            thumbnails(count=60, change_every=60), fps=2.0))
        text = composition.format_report(verdict)
        self.assertIn("COMPOSITION: FAILED", text)
        self.assertIn("worst holds", text)
        self.assertIn("Cut inside the scene", text)


@unittest.skipIf(FFMPEG is None, "FFmpeg is not installed")
class RealFileTests(unittest.TestCase):
    """End to end, including the case the whole check exists for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _frozen_with_grain(self, seconds: int = 16) -> Path:
        path = self.dir / "frozen.mp4"
        subprocess.run([
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x101014:s=320x180:d=%d" % seconds,
            "-vf", "noise=alls=28:allf=t", "-r", "30", str(path),
        ], check=True)
        return path

    def test_a_frozen_frame_wearing_grain_fails(self):
        verdict = composition.analyse_video(self._frozen_with_grain())
        self.assertFalse(verdict["passed"], verdict["statement"])
        self.assertEqual(verdict["compositions"], 1)

    def test_the_character_film_passes(self):
        film = ROOT / "docs" / "media" / "stickman-film.mp4"
        if not film.is_file():
            self.skipTest("the reference film is not in this checkout")
        verdict = composition.analyse_video(film)
        self.assertTrue(verdict["passed"], verdict["statement"])

    def test_a_missing_file_raises_rather_than_passing(self):
        with self.assertRaises(FileNotFoundError):
            composition.analyse_video(self.dir / "nope.mp4")


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_composition.py"), *args],
            capture_output=True, text=True, check=False,
        )

    def test_a_missing_file_is_bad_input(self):
        result = self._run(str(self.dir / "nope.mp4"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such video", result.stderr)

    @unittest.skipIf(FFMPEG is None, "FFmpeg is not installed")
    def test_a_slideshow_exits_non_zero(self):
        path = self.dir / "still.mp4"
        subprocess.run([
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x101014:s=320x180:d=16",
            "-vf", "drawbox=x=20:y=20:w=60:h=20:color=white:t=fill",
            "-r", "30", str(path),
        ], check=True)
        result = self._run(str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("COMPOSITION: FAILED", result.stdout)

    @unittest.skipIf(FFMPEG is None, "FFmpeg is not installed")
    def test_json_mode_is_machine_readable(self):
        path = self.dir / "still.mp4"
        subprocess.run([
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x101014:s=320x180:d=16",
            "-vf", "drawbox=x=20:y=20:w=60:h=20:color=white:t=fill",
            "-r", "30", str(path),
        ], check=True)
        result = self._run(str(path), "--json")
        payload = json.loads(result.stdout)
        self.assertFalse(payload["passed"])
        self.assertIn("longest_hold_seconds", payload)


if __name__ == "__main__":
    unittest.main()
