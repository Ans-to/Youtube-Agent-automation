"""The check that catches a picture which has stopped moving.

The defect this guards against is not "no pixels changed". Grain changed every
pixel, every frame, in the film that shipped a twenty-second frozen title card,
and every existing freeze check passed it. The question that matters is whether
the *picture* is the same as half a second ago.

These tests are synthetic on purpose: they build the two cases by hand, so a
regression in any of the four steps (pooling, lag, magnitude threshold, span
grouping) fails here instead of being discovered by watching an eleven-minute
render.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover - the renderer needs numpy anyway
    HAVE_NUMPY = False

try:
    import repeat_frames
    HAVE_MODULE = True
except ImportError:  # pragma: no cover - same reason
    HAVE_MODULE = False
    repeat_frames = None

W, H, FPS = 192, 108, 10


def still_frames(count, *, seed=7, noise=12.0):
    """A static composition - dark background, one bright panel - plus grain."""
    rng = np.random.default_rng(seed)
    for _ in range(count):
        frame = np.full((H, W), 40.0)
        frame[30:70, 40:120] = 95.0
        frame[80:90, 40:120] = 60.0
        yield np.clip(frame + rng.normal(0.0, noise, (H, W)), 0, 255).astype(np.uint8)


def moving_frames(count, *, seed=3, step=14, noise=12.0):
    """The same composition, but the panel travels across the frame."""
    rng = np.random.default_rng(seed)
    for index in range(count):
        frame = np.full((H, W), 40.0)
        left = 6 + (index * step) % (W - 50)
        frame[30:70, left:left + 44] = 95.0
        frame[80:90, left:left + 44] = 60.0
        yield np.clip(frame + rng.normal(0.0, noise, (H, W)), 0, 255).astype(np.uint8)


@unittest.skipUnless(HAVE_NUMPY and HAVE_MODULE, "numpy is required for the repeat-frame check")
class RepeatFrameDetectionTests(unittest.TestCase):
    def test_a_still_picture_with_grain_is_called_still(self):
        report = repeat_frames.analyse_frames(still_frames(80), fps=FPS)
        self.assertGreaterEqual(report["longest_still_seconds"], 2.0,
                                "grain hid a frozen picture: " + str(report["spans"]))
        self.assertGreater(report["still_share_of_frames"], 0.8)

    def test_a_picture_that_moves_is_not_called_still(self):
        report = repeat_frames.analyse_frames(moving_frames(80), fps=FPS)
        self.assertEqual(report["spans"], [],
                         "a travelling panel was reported as a hold: " + str(report["spans"]))
        self.assertLess(report["still_share_of_frames"], 0.1)

    def test_one_span_covers_the_whole_hold(self):
        # 4 s of nothing, then movement, then 3 s of nothing again.
        frames = list(still_frames(40)) + list(moving_frames(20, seed=11)) + list(still_frames(30, seed=13))
        spans = repeat_frames.analyse_frames(frames, fps=FPS)["spans"]
        longest = spans[0]
        self.assertGreaterEqual(longest["seconds"], 2.5)
        self.assertLessEqual(longest["seconds"], 4.2)
        self.assertGreaterEqual(len(spans), 2)

    def test_short_holds_are_ignored(self):
        # Two frames of stillness at 10 fps is 0.2 s: below min_span_seconds.
        frames = list(moving_frames(30))
        frames += [frames[-1], frames[-1]]
        frames += list(moving_frames(30, seed=5))
        self.assertEqual(repeat_frames.analyse_frames(frames, fps=FPS)["spans"], [])

    def test_fps_must_be_positive(self):
        with self.assertRaises(ValueError):
            repeat_frames.analyse_frames(still_frames(2), fps=0)

    def test_a_frame_shorter_than_the_lag_is_reported_not_scored(self):
        report = repeat_frames.analyse_frames(still_frames(3), fps=FPS)
        self.assertEqual(report["judged_frames"], 0)
        self.assertEqual(report["spans"], [])


@unittest.skipUnless(HAVE_NUMPY and HAVE_MODULE, "numpy is required for the repeat-frame check")
class RepeatFrameVerdictTests(unittest.TestCase):
    def report(self, seconds, *, judged=200):
        return {
            "judged_frames": judged,
            "lag_seconds": 0.5,
            "spans": [{"start": 10.0, "end": 10.0 + seconds, "seconds": seconds}],
            "longest_still_seconds": seconds,
            "still_share_of_frames": 0.5,
            "sampled_frames": 220,
            "thresholds": {"sample_fps": 10.0},
            "mean_changed_share": 0.0,
        }

    def test_a_hold_over_the_limit_fails(self):
        verdict = repeat_frames.decide(self.report(2.4), 1.0)
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["status"], "failed")
        self.assertIn("FAILED", verdict["statement"])
        self.assertIn("2.4 s", verdict["statement"])
        self.assertIn("fix_hint", verdict)

    def test_a_hold_under_the_limit_passes(self):
        verdict = repeat_frames.decide(self.report(0.9), 1.0)
        self.assertTrue(verdict["passed"])
        self.assertIn("PASSED", verdict["statement"])

    def test_the_limit_is_a_parameter_not_a_constant(self):
        self.assertFalse(repeat_frames.decide(self.report(0.9), 0.5)["passed"])
        self.assertTrue(repeat_frames.decide(self.report(2.4), 3.0)["passed"])

    def test_a_check_that_could_not_run_never_passes(self):
        verdict = repeat_frames.decide(self.report(0.0, judged=0), 1.0)
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["status"], "too_short")
        self.assertIn("NOT RUN", verdict["statement"])


@unittest.skipUnless(HAVE_NUMPY and HAVE_MODULE, "numpy is required for the repeat-frame check")
class PoolingTests(unittest.TestCase):
    def test_blocks_are_the_mean_of_their_pixels(self):
        frame = np.zeros((12, 12), dtype=np.uint8)
        frame[:, 6:] = 100
        pooled = repeat_frames.pool(frame, blocks_x=2, blocks_y=1)
        self.assertEqual(pooled.shape, (1, 2))
        self.assertAlmostEqual(float(pooled[0, 0]), 0.0)
        self.assertAlmostEqual(float(pooled[0, 1]), 100.0)

    def test_a_partial_edge_block_is_trimmed_not_squashed(self):
        frame = np.zeros((10, 10), dtype=np.uint8)
        frame[:, 9:] = 255
        pooled = repeat_frames.pool(frame, blocks_x=3, blocks_y=3)
        self.assertEqual(pooled.shape, (3, 3))
        self.assertEqual(float(pooled.max()), 0.0,
                         "the bright right-hand column leaked into a block")

    def test_a_frame_too_small_to_pool_is_rejected(self):
        with self.assertRaises(ValueError):
            repeat_frames.pool(np.zeros((4, 4), dtype=np.uint8), blocks_x=16, blocks_y=9)


@unittest.skipUnless(HAVE_MODULE, "the repeat-frame module is missing")
class ReportingTests(unittest.TestCase):
    def test_timecode_reads_as_minutes_and_seconds(self):
        self.assertEqual(repeat_frames.timecode(0), "0:00")
        self.assertEqual(repeat_frames.timecode(75.9), "1:15")

    def test_the_report_shows_the_worst_spans_first(self):
        text = repeat_frames.format_report({
            "file": "/tmp/film.mp4",
            "statement": "REPEAT CHECK: FAILED - the picture is unchanged for 2.0 s at 0:10",
            "sampled_frames": 600,
            "lag_seconds": 0.5,
            "thresholds": {"sample_fps": 10.0},
            "spans": [{"start": 10.0, "end": 12.0, "seconds": 2.0}],
            "fix_hint": "cut it",
        })
        self.assertIn("film.mp4", text)
        self.assertIn("0:10 -> 0:12", text)
        self.assertIn("cut it", text)


class WiringTests(unittest.TestCase):
    """The check only protects the channel if the render actually runs it."""

    def test_the_render_driver_fails_a_film_that_holds(self):
        source = (ROOT / "tools" / "render_authored_film.py").read_text(encoding="utf-8")
        self.assertIn("measure_repeat_frames", source)
        self.assertIn("MAX_STILL_SECONDS = 1.0", source)
        self.assertIn('holds.get("status") == "passed"', source)

    def test_the_quality_audit_runs_the_same_check(self):
        source = (ROOT / "video_studio" / "quality_audit.py").read_text(encoding="utf-8")
        self.assertIn("repeat_frame_check", source)
        self.assertIn('"repeat_frames"', source)

    def test_there_is_a_standalone_command(self):
        path = ROOT / "tools" / "check_repeat_frames.py"
        self.assertTrue(path.is_file())
        spec = importlib.util.spec_from_file_location("check_repeat_frames", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.main(["/nonexistent/film.mp4"]), 2,
                         "a file that is not there must not look like a pass")


if __name__ == "__main__":
    unittest.main()
