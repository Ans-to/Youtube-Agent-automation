import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import curves  # noqa: E402


class CurveTests(unittest.TestCase):
    def test_every_curve_starts_at_zero_and_ends_at_one(self):
        for name in curves.CURVES:
            self.assertAlmostEqual(curves.ease(name, 0.0), 0.0, places=6, msg=name)
            self.assertAlmostEqual(curves.ease(name, 1.0), 1.0, places=6, msg=name)

    def test_sampling_is_bounded_and_complete(self):
        values = curves.sample("editorial", 24)
        self.assertEqual(len(values), 24)
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 1.0)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in values))

    def test_editorial_is_symmetric_and_weighted(self):
        self.assertAlmostEqual(curves.ease("editorial", 0.5), 0.5, places=6)
        self.assertLess(curves.ease("editorial", 0.25), 0.25)
        self.assertGreater(curves.ease("editorial", 0.75), 0.75)

    def test_entrance_departs_fast_and_lands_softly(self):
        velocity = curves.velocity_profile("entrance", 48)
        self.assertGreater(velocity[0], velocity[-1] * 10)
        self.assertGreater(curves.ease("entrance", 0.1), 0.4)

    def test_settle_overshoots_once_and_returns(self):
        self.assertGreater(curves.peak_overshoot("settle"), 0.02)
        self.assertAlmostEqual(curves.ease("settle", 1.0), 1.0, places=6)
        self.assertTrue(curves.is_monotonic("settle") or curves.peak_overshoot("settle") > 0)

    def test_linear_is_named_but_rejected(self):
        self.assertTrue(curves.is_linear_like("linear"))
        for name in curves.CURVES:
            if name == "linear":
                continue
            self.assertFalse(curves.is_linear_like(name), msg=name)
            self.assertTrue(curves.CURVES[name].character)

    def test_forbidden_curve_is_declared(self):
        self.assertIn("linear", curves.FORBIDDEN_CURVES)

    def test_unknown_curve_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "Unknown easing curve"):
            curves.ease("vibes", 0.5)
        with self.assertRaisesRegex(ValueError, "Unknown easing curve"):
            curves.curve("easings")

    def test_invalid_progress_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            curves.ease("editorial", math.nan)
        with self.assertRaisesRegex(ValueError, "finite"):
            curves.ease("editorial", math.inf)

    def test_bezier_x_control_points_are_validated(self):
        with self.assertRaisesRegex(ValueError, "x control points"):
            curves.bezier_y_at_x(0.5, 1.2, 0.0, 0.4, 1.0)

    def test_clamping_outside_the_unit_interval(self):
        self.assertEqual(curves.ease("editorial", -3), 0.0)
        self.assertEqual(curves.ease("editorial", 9), 1.0)

    def test_description_is_machine_readable(self):
        report = curves.describe("settle")
        self.assertEqual(report["name"], "settle")
        self.assertEqual(len(report["control_points"]), 4)
        self.assertGreater(report["peak_overshoot"], 0)
        self.assertIn("character", report)

    def test_sample_requires_two_points(self):
        with self.assertRaisesRegex(ValueError, "at least two points"):
            curves.sample("editorial", 1)


if __name__ == "__main__":
    unittest.main()
