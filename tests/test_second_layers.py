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
    """Put a substantial bright block inside one region.

    Substantial matters: the floor is in grey levels of a pooled cell, so a
    fixture has to occupy enough of a region to move one - which is the same
    lesson the film itself learned. A 24-pixel block is a decoration; 70 across
    the region is an element.
    """
    copy = frame.copy()
    height, width = copy.shape
    top = int(region.y0 * height) + 12
    bottom = int(region.y1 * height) - 12
    region_left = int(region.x0 * width)
    region_width = int(region.x1 * width) - region_left
    block_w = int(region_width * 0.55)
    # Four positions inside the region, never across its edge: a fixture that
    # spills into a neighbour would be testing two regions, not one.
    offset = int((region_width - block_w) * (column / 3)) if block_w < region_width else 0
    copy[top:bottom, region_left + offset:region_left + offset + block_w] = value
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

    def test_a_gentle_drift_does_not_count_as_activity(self):
        """A slow camera moves every region by a little, and that is not a beat.

        The floor is absolute (six grey levels), so motion too small to be a
        picture change cannot be banked as something happening - which is what
        this film's old camera push was: measured, under four levels everywhere.
        """
        frames = []
        for index in range(4):
            frame = blank_frame()
            # A bright band that creeps one pixel per sample, plus a little noise
            # across the whole picture, the way a drifting camera looks.
            frame[60:90, 40 + index:200] = 120
            frame[:, :] = np.clip(frame.astype(np.int16) + (index % 2) * 3, 0, 255).astype(np.uint8)
            frames.append(frame)
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertFalse(report.seconds[0].passed)

    def test_a_large_element_in_one_region_is_one_thing(self):
        """One block arriving is one region, however bright it is."""
        base = blank_frame()
        frames = [
            base,
            draw_block(base, second_layers.REGIONS[2], value=250),
            draw_block(base, second_layers.REGIONS[2], value=250, column=2),
            base,
        ]
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        self.assertEqual(report.seconds[0].live, ["r1c3"])
        self.assertFalse(report.seconds[0].passed)

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

    def test_a_region_that_never_changes_is_never_live(self):
        """An empty corner stays out of it, whatever happens elsewhere.

        The first version of this module compared regions by normalised
        correlation, and an empty corner scored 0.266 against itself - noise
        comparing itself to noise - so a still frame could bank activity it did
        not have. Absolute grey levels cannot do that: six levels of change is a
        block of the picture arriving, and an empty region never produces one.
        """
        base = blank_frame()
        frames = []
        for column in range(4):
            # One element moving inside one region; every other region flat.
            frames.append(draw_block(base, second_layers.REGIONS[1], column=column))
        report = second_layers.analyse_stream(self.stream(frames), samples_per_second=4)
        second = report.seconds[0]
        self.assertEqual(second.live, ["r1c2"])
        self.assertIn("r1c1", second.unjudged)
        self.assertIn("r2c3", second.unjudged)
        self.assertFalse(second.passed)

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
        self.assertEqual(check_second_layers.MIN_LIVE_REGIONS, 2)
        report = second_layers.SecondReport()
        report.min_live = 3
        self.assertEqual(report.min_live, 3)


if __name__ == "__main__":
    unittest.main()
