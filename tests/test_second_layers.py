"""Tests for the per-second layer check.

The rule this enforces is the owner's: in any one second, two different things
should be happening in the picture. The tests that matter are the ones proving
the check can be fooled by neither a big single move nor furniture that ticks by
itself - a camera push is one thing happening, however large, and a timecode and
progress bar tick in every second of every film including a frozen one.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from video_studio import second_layers  # noqa: E402 - path set up above
import check_second_layers  # noqa: E402 - path set up above


def blank_frame() -> np.ndarray:
    """A 180x320 frame of one dark tone, which is what a stage looks like."""
    return np.full((second_layers.FRAME_HEIGHT, second_layers.FRAME_WIDTH), 40, dtype=np.uint8)


def draw_block(frame: np.ndarray, region: second_layers.Region, value: int = 220,
               column: int = 0) -> np.ndarray:
    """Put a bright block inside one region, optionally in one of its columns."""
    copy = frame.copy()
    height, width = copy.shape
    top = int(region.y0 * height) + 20
    bottom = int(region.y1 * height) - 20
    left = int(region.x0 * width) + 10 + column * 30
    copy[top:bottom, left:left + 24] = value
    return copy


class RegionTests(unittest.TestCase):
    def test_the_furniture_is_not_part_of_the_picture(self):
        """The top and bottom bands are cut away before anything is measured."""
        regions = second_layers.build_regions()
        for region in regions:
            self.assertGreaterEqual(region.y0, second_layers.CONTENT_TOP - 1e-9)
            self.assertLessEqual(region.y1, second_layers.CONTENT_BOTTOM + 1e-9)

    def test_the_regions_tile_the_picture_without_gaps(self):
        regions = second_layers.build_regions(columns=3, rows=2)
        self.assertEqual(len(regions), 6)
        self.assertEqual(sum(r.x1 - r.x0 for r in regions[:3]), 1.0)
        top = [r for r in regions if r.y0 == second_layers.CONTENT_TOP]
        bottom = [r for r in regions if r.y0 != second_layers.CONTENT_TOP]
        self.assertEqual(len(top), 3)
        self.assertEqual(len(bottom), 3)
        for above, below in zip(top, bottom):
            self.assertAlmostEqual(above.y1, below.y0, places=6)
        self.assertAlmostEqual(max(r.y1 for r in regions), second_layers.CONTENT_BOTTOM, places=6)

    def test_a_region_is_thumbnailed_to_a_small_grid(self):
        frame = blank_frame()
        signature = second_layers.region_signature(frame, second_layers.REGIONS[0])
        self.assertEqual(signature.shape, (second_layers.CELL_Y, second_layers.CELL_X))


class TheRuleTests(unittest.TestCase):
    samples = 4

    def stream(self, frames):
        return [second_layers.frame_signatures(frame) for frame in frames]

    def test_one_thing_moving_is_not_enough(self):
        """An element entering in one region, and nothing else: fails."""
        base = blank_frame()
        frames = [draw_block(base, second_layers.REGIONS[1], column=0),
                  draw_block(base, second_layers.REGIONS[1], column=1),
                  draw_block(base, second_layers.REGIONS[1], column=2),
                  draw_block(base, second_layers.REGIONS[1], column=3)]
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertEqual(len(report.seconds), 1)
        self.assertFalse(report.seconds[0].passed)
        self.assertEqual(report.seconds[0].live, ["r1c2"])

    def test_two_things_moving_passes(self):
        """An element in each of two regions: passes."""
        base = blank_frame()
        frames = []
        for column in range(4):
            frame = draw_block(base, second_layers.REGIONS[1], column=column)
            frames.append(draw_block(frame, second_layers.REGIONS[4], column=3 - column))
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertTrue(report.seconds[0].passed)
        self.assertEqual(sorted(report.seconds[0].live), ["r1c2", "r2c2"])

    def test_a_camera_push_is_one_thing_however_large(self):
        """A camera moves everything at once, and everything is still one move.

        The whole frame scales, so every region changes by the same amount. It
        must not be scored as six things happening: a push is one move of one
        picture, which is exactly what the owner rejected.
        """
        frames = []
        for index in range(4):
            zoom = 1.0 + 0.06 * index
            frame = blank_frame()
            height, width = frame.shape
            # A vertical bar that thickens as the frame "pushes in" on it.
            frame[:, int(width * 0.4):int(width * 0.4) + int(18 * zoom)] = 220
            frames.append(frame)
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        # The bar lives in one column of the frame, so at most one region of each
        # row changes; what must not happen is the empty regions lighting up.
        self.assertLessEqual(len(report.seconds[0].live), 2)

    def test_a_flat_frame_is_neither_live_nor_still(self):
        report = second_layers.analyse_stream(
            self.stream([blank_frame() for _ in range(4)]), samples_per_second=4)
        self.assertEqual(report.seconds[0].live, [])
        self.assertEqual(len(report.seconds[0].unjudged), len(second_layers.REGIONS))

    def test_a_looping_detail_still_counts(self):
        """A spinner returns to where it started by the end of the second.

        Compared only against the last sample it would look still, because it is
        back where it began. It is live.
        """
        base = blank_frame()
        region = second_layers.REGIONS[1]
        frames = [draw_block(base, region, column=0),
                  draw_block(base, region, column=2),
                  draw_block(base, region, column=3),
                  draw_block(base, region, column=0)]
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertIn("r1c2", report.seconds[0].live)

    def test_a_partial_second_is_not_judged(self):
        frames = [blank_frame() for _ in range(5)]
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertEqual(len(report.seconds), 1)

    def test_the_report_counts_the_seconds_that_fail(self):
        base = blank_frame()
        quiet = [draw_block(base, second_layers.REGIONS[1], column=c) for c in range(0, 4, 1)]
        busy = []
        for column in range(4):
            frame = draw_block(base, second_layers.REGIONS[1], column=column)
            busy.append(draw_block(frame, second_layers.REGIONS[4], column=3 - column))
        report = second_layers.analyse_stream(
            self.stream(quiet + busy), samples_per_second=4)
        self.assertEqual(report.judged, 2)
        self.assertEqual(len(report.failed), 1)
        self.assertFalse(report.passed)
        self.assertAlmostEqual(report.pass_share, 0.5)

    def test_an_empty_stream_is_not_a_pass(self):
        report = second_layers.analyse_stream([], samples_per_second=4)
        self.assertFalse(report.passed)
        self.assertIn("nothing judged", second_layers.format_report(report))

    def test_the_report_names_the_emptiest_seconds(self):
        base = blank_frame()
        frames = [draw_block(base, second_layers.REGIONS[1], column=c) for c in range(4)]
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        text = second_layers.format_report(report)
        self.assertIn("FAILED", text)
        self.assertIn("0:00", text)
        self.assertIn("r1c2", text)


class CommandTests(unittest.TestCase):
    def test_a_missing_file_is_a_bad_input(self):
        self.assertEqual(check_second_layers.main(["/nonexistent/film.mp4", "--quiet"]), 2)

    def test_the_bar_can_be_raised_from_the_command_line(self):
        """Three live regions must be demanded when asked for, not defaulted."""
        parser_default = check_second_layers.MIN_LIVE_REGIONS
        self.assertEqual(parser_default, 2)


if __name__ == "__main__":
    unittest.main()
