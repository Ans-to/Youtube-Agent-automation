import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import camera, transitions  # noqa: E402


class TransitionTests(unittest.TestCase):
    def test_professional_set_has_six_designed_edits(self):
        self.assertEqual(set(transitions.PRO_TRANSITIONS),
                         {"cut", "whip-pan", "masked-reveal", "morph", "glitch", "match-cut"})

    def test_powerpoint_transitions_are_named_as_forbidden(self):
        self.assertEqual(transitions.FORBIDDEN_TRANSITIONS,
                         {"push", "wipe-left", "wipe-right", "dissolve"})

    def test_legacy_names_upgrade_to_designed_equivalents(self):
        self.assertEqual(transitions.upgrade("fade", "corporate"), "morph")
        self.assertEqual(transitions.upgrade("wipe-left", "corporate"), "masked-reveal")
        self.assertEqual(transitions.upgrade("slide-right", "edgy"), "whip-pan")
        self.assertEqual(transitions.upgrade("zoom", "cinematic"), "match-cut")
        self.assertEqual(transitions.upgrade("dissolve", "playful"), "glitch")
        self.assertEqual(transitions.upgrade("push", "minimalist"), "masked-reveal")

    def test_pro_names_pass_through(self):
        self.assertEqual(transitions.upgrade("match-cut", "edgy"), "match-cut")

    def test_unknown_transition_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "Unknown transition"):
            transitions.normalize("star-wipe")

    def test_frame_counts_stay_inside_the_designed_range(self):
        self.assertEqual(transitions.frames_for("cut", 60), 0)
        self.assertEqual(transitions.frames_for("whip-pan", 30), 9)
        self.assertEqual(transitions.frames_for("whip-pan", 30, seconds=5.0), 14)
        self.assertGreaterEqual(transitions.frames_for("masked-reveal", 30, seconds=0.01), 9)
        with self.assertRaisesRegex(ValueError, "fps"):
            transitions.frames_for("morph", 120)

    def test_plan_checks_repetition(self):
        issues = transitions.plan_issues(["cut", "glitch", "glitch", "glitch"])
        self.assertTrue(any("repeats three times" in issue for issue in issues))
        issues = transitions.plan_issues(["whip-pan", "whip-pan"])
        self.assertTrue(any("same transition" in issue for issue in issues))
        self.assertEqual(transitions.plan_issues(["cut", "morph", "masked-reveal", "match-cut"]), [])

    def test_plan_rejects_forbidden_names(self):
        issues = transitions.plan_issues(["cut", "wipe-left"])
        self.assertTrue(any("forbidden" in issue for issue in issues))

    def test_selection_never_repeats_the_previous_transition(self):
        for tone in ("corporate", "edgy", "minimalist", "cinematic", "playful"):
            previous = None
            for index in range(6):
                choice = transitions.select(index, tone, previous)
                self.assertNotEqual(choice, previous, msg="%s at %d" % (tone, index))
                previous = choice

    def test_catalogue_is_complete(self):
        data = transitions.catalogue()
        self.assertEqual(len(data["professional"]), 6)
        self.assertEqual(data["legacy"]["fade"], "morph")
        self.assertIn("push", data["forbidden"])


class CameraTests(unittest.TestCase):
    def test_push_in_moves_toward_the_frame(self):
        start = camera.sample("push-in", 0.0)
        end = camera.sample("push-in", 1.0)
        self.assertEqual(start["scale"], 1.0)
        self.assertGreater(end["scale"], 1.0)

    def test_pan_left_and_right_move_in_opposite_directions(self):
        left = camera.sample("pan-left", 1.0, amplitude=1.0)
        right = camera.sample("pan-right", 1.0, amplitude=1.0)
        self.assertLess(left["offset_x"], 0)
        self.assertGreater(right["offset_x"], 0)

    def test_crane_and_tilt_move_vertically(self):
        self.assertLess(camera.sample("crane-up", 1.0, amplitude=1.0)["offset_y"], 0)
        self.assertGreater(camera.sample("tilt-down", 1.0, amplitude=1.0)["offset_y"], 0)

    def test_drift_curves_rather_than_travelling_straight(self):
        mid = camera.sample("drift", 0.5)
        edge = camera.sample("drift", 0.05)
        self.assertNotEqual(mid["rotation_degrees"], edge["rotation_degrees"])
        self.assertNotEqual(mid["offset_x"], edge["offset_x"])

    def test_rotation_stays_level_enough_for_text(self):
        for move in camera.MOVES:
            for step in (0.1, 0.5, 0.9):
                value = camera.sample(move, step, amplitude=2.0)["rotation_degrees"]
                self.assertLess(abs(value), 1.0, msg=move)

    def test_unknown_move_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown camera move"):
            camera.sample("dolly-zoom", 0.5)

    def test_static_camera_does_nothing(self):
        self.assertEqual(camera.sample("static", 0.5),
                         {"move": "static", "scale": 1.0, "offset_x": 0.0,
                          "offset_y": 0.0, "rotation_degrees": 0.0})

    def test_shake_decays_over_time(self):
        at_impact = camera.shake_offsets(1.0, 0.02)
        later = camera.shake_offsets(1.0, 0.5)
        self.assertGreater(abs(at_impact["x"]), abs(later["x"]))

    def test_depth_of_field_blurs_away_from_the_focal_plane(self):
        focused = camera.dof(0.5, aperture=0.8)
        far = camera.dof(0.0, aperture=0.8)
        self.assertEqual(focused["blur_px"], 0.0)
        self.assertGreater(far["blur_px"], 0)
        self.assertLess(far["opacity"], 1.0)

    def test_parallax_increases_with_frame_and_depth(self):
        self.assertGreater(camera.parallax(0.8, 30), camera.parallax(0.2, 30))
        self.assertGreater(camera.parallax(0.5, 60), camera.parallax(0.5, 30))

    def test_camera_selection_respects_data_shots(self):
        self.assertEqual(camera.select(3, "edgy", purpose="data"), "static")
        self.assertNotEqual(camera.select(1, "cinematic"), "static")

    def test_amplitude_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "amplitude"):
            camera.sample("push-in", 0.5, amplitude=3)


if __name__ == "__main__":
    unittest.main()
