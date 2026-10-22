import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import principles  # noqa: E402


class PrincipleTests(unittest.TestCase):
    def test_anticipation_moves_backwards_before_the_action(self):
        self.assertEqual(principles.anticipate(0.0), 0.0)
        dip = principles.anticipate(0.09, lead=0.18, amount=0.08)
        self.assertLess(dip, 0.0)
        self.assertGreaterEqual(dip, -0.08)
        self.assertAlmostEqual(principles.anticipate(0.36, lead=0.18), 0.0, places=6)
        self.assertEqual(principles.anticipate(0.9, lead=0.18), 0.0)

    def test_anticipation_never_exceeds_its_budget(self):
        values = [principles.anticipate(index / 100, lead=0.2, amount=0.05) for index in range(101)]
        self.assertGreaterEqual(min(values), -0.05 - 1e-9)
        self.assertLessEqual(max(values), 0.0)

    def test_anticipation_parameters_are_checked(self):
        with self.assertRaisesRegex(ValueError, "lead"):
            principles.anticipate(0.1, lead=0.7)
        with self.assertRaisesRegex(ValueError, "amount"):
            principles.anticipate(0.1, amount=0.9)

    def test_settle_crosses_the_target(self):
        self.assertGreater(principles.overshoot_settle(0.5), 1.0)
        self.assertAlmostEqual(principles.overshoot_settle(1.0), 1.0, places=6)

    def test_follow_through_starts_and_finishes_later(self):
        self.assertEqual(principles.follow_through(0.10, delay=0.12), 0.0)
        self.assertLess(principles.follow_through(0.50, delay=0.12), 1.0)
        self.assertEqual(principles.follow_through(1.0, delay=0.12), 1.0)

    def test_stagger_delays_are_ordered_and_normalised(self):
        delays = principles.stagger_delays(5, gap=0.05)
        self.assertEqual(delays[0], 0.0)
        self.assertEqual(delays[-1], 1.0)
        self.assertEqual(delays, sorted(delays))

    def test_stagger_frames_respect_the_cap(self):
        frames = principles.stagger_delays_frames(10, gap_frames=4, cap_frames=18)
        self.assertEqual(frames[0], 0)
        self.assertEqual(frames[-1], 18)

    def test_squash_is_never_applied_to_rigid_graphics(self):
        self.assertEqual(principles.squash_stretch(1.0, allow=False), (1.0, 1.0))

    def test_organic_squash_preserves_volume(self):
        stretch, squash = principles.squash_stretch(0.9, amount=0.1, allow=True)
        self.assertGreater(stretch, 1.0)
        self.assertLess(squash, 1.0)
        self.assertAlmostEqual(stretch * squash, 1.0, places=6)

    def test_hold_window_has_a_real_plateau(self):
        window = principles.hold_window(4.0, in_fraction=0.18, out_fraction=0.16)
        self.assertAlmostEqual(window["in"] + window["hold"] + window["out"], 4.0, places=6)
        self.assertGreater(window["hold"], 2.0)
        self.assertEqual(principles.phase_at(0.05, window), "in")
        self.assertEqual(principles.phase_at(0.5, window), "hold")
        self.assertEqual(principles.phase_at(0.95, window), "out")

    def test_hold_window_rejects_impossible_fractions(self):
        with self.assertRaisesRegex(ValueError, "leave time"):
            principles.hold_window(2.0, in_fraction=0.6, out_fraction=0.5)
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            principles.hold_window(0)

    def test_impact_shake_decays(self):
        first = principles.impact_shake(0.03, intensity=1.0)
        later = principles.impact_shake(0.6, intensity=1.0)
        self.assertGreaterEqual(abs(first[0]), abs(later[0]))
        self.assertGreaterEqual(abs(first[1]), abs(later[1]))

    def test_parallax_scales_with_depth(self):
        far = principles.parallax_rate(0.1)
        near = principles.parallax_rate(0.9)
        self.assertGreater(near, far)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            principles.parallax_rate(1.4)

    def test_reading_time_has_a_floor(self):
        self.assertGreaterEqual(principles.reading_time_seconds(1), 0.8)
        self.assertGreater(principles.reading_time_seconds(40), principles.reading_time_seconds(4))

    def test_the_twelve_principles_are_documented(self):
        self.assertEqual(len(principles.PRINCIPLES), 14)
        self.assertIn("anticipation", principles.PRINCIPLES)
        self.assertIn("follow_through", principles.PRINCIPLES)


if __name__ == "__main__":
    unittest.main()
