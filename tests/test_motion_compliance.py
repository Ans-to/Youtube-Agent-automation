import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import compliance, direction  # noqa: E402

BRIEF = {
    "title": "Every Frame Is Code",
    "goal": "Show that the studio renders everything locally, with no services.",
    "tone": "cinematic",
    "platform": "youtube-4k",
    "scenes": [
        {"purpose": "hook", "headline": "Every frame is code.",
         "subhead": "A deterministic motion studio.", "duration_seconds": 4, "visual_type": "hero"},
        {"purpose": "process", "headline": "Nothing is filmed.",
         "subhead": "Geometry is generated per frame.", "duration_seconds": 4,
         "visual_type": "diagram", "visual_nodes": ["BRIEF", "COMPILER", "FRAMES"]},
        {"purpose": "proof", "headline": "Same input. Same pixels.",
         "subhead": "Reproducible output.", "duration_seconds": 4,
         "visual_type": "comparison", "comparison_left": ["First run"],
         "comparison_right": ["Same input"]},
    ],
}


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        compiled = direction.compile_brief(BRIEF)
        self.sheet = compiled["direction"]
        self.storyboard = compiled["storyboard"]

    def test_a_compiled_brief_passes_every_applicable_clause(self):
        report = compliance.audit_storyboard(self.storyboard, self.sheet)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["statement"], "MOTION SPEC: PASSED - No violations detected.")
        self.assertGreaterEqual(report["summary"]["passed"], 15)
        self.assertIn("MG-2.2-COMPOSITION", report["verified_machine"])

    def test_report_lists_what_was_not_checked(self):
        report = compliance.audit_storyboard(self.storyboard, self.sheet)
        ids = [item["id"] for item in report["not_checked"]]
        self.assertEqual(ids, ["MG-4.1-BEAT-SYNC"])
        text = compliance.format_report(report)
        self.assertIn("Not checked", text)
        self.assertIn("Aesthetic sign-off", text)

    def test_legacy_transition_fails_and_names_the_fix(self):
        broken = copy.deepcopy(self.storyboard)
        broken["scenes"][1]["transition_in"] = "wipe-left"
        report = compliance.audit_storyboard(broken, self.sheet)
        ids = [item["id"] for item in report["violations"]]
        self.assertIn("MG-3.4-TRANSITIONS", ids)
        detail = next(item["detail"] for item in report["violations"] if item["id"] == "MG-3.4-TRANSITIONS")
        self.assertIn("wipe-left", detail)
        self.assertIn("masked-reveal", detail)

    def test_linear_easing_is_rejected(self):
        broken = copy.deepcopy(self.storyboard)
        broken["scenes"][1]["easing"] = "linear"
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-3.1-EASING", [item["id"] for item in report["violations"]])

    def test_missing_grade_is_rejected(self):
        broken = copy.deepcopy(self.storyboard)
        broken["style"].pop("grade")
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-2.4-GRADE", [item["id"] for item in report["violations"]])

    def test_1080p_master_fails_the_resolution_clause(self):
        broken = copy.deepcopy(self.storyboard)
        broken["width"], broken["height"] = 1920, 1080
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-2.1-RESOLUTION", [item["id"] for item in report["violations"]])

    def test_placeholder_copy_is_rejected(self):
        broken = copy.deepcopy(self.storyboard)
        broken["scenes"][0]["headline"] = "Lorem ipsum dolor sit amet"
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-5.3-PLACEHOLDER", [item["id"] for item in report["violations"]])

    def test_dense_frames_are_rejected(self):
        broken = copy.deepcopy(self.storyboard)
        broken["scenes"][0]["headline"] = " ".join("word%d" % index for index in range(40))
        broken["scenes"][0]["subhead"] = " ".join("more%d" % index for index in range(10))
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-6.1-DENSITY", [item["id"] for item in report["violations"]])

    def test_locked_off_camera_is_rejected(self):
        broken = copy.deepcopy(self.storyboard)
        for scene in broken["scenes"]:
            scene["camera_motion"] = "static"
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertIn("MG-3.5-CAMERA", [item["id"] for item in report["violations"]])

    def test_missing_direction_is_not_a_pass_for_timeline_checks(self):
        report = compliance.audit_storyboard(self.storyboard, None)
        ids = [item["id"] for item in report["not_checked"]]
        self.assertIn("MG-5.1-TIMELINE", ids)
        self.assertIn("MG-5.2-LAYERS", ids)
        self.assertNotIn("MG-5.1-TIMELINE", report["verified_machine"])

    def test_beat_sync_fails_when_cues_ignore_the_grid(self):
        beats = [0.23 + index * 0.5 for index in range(30)]
        report = compliance.audit_storyboard(self.storyboard, self.sheet, beats=beats)
        self.assertIn("MG-4.1-BEAT-SYNC", [item["id"] for item in report["violations"]])

    def test_beat_sync_passes_when_cues_land_on_the_grid(self):
        beats = [0.0, 4.0, 8.0, 12.0]
        report = compliance.audit_storyboard(self.storyboard, self.sheet, beats=beats)
        self.assertEqual(report["violations"], [])
        self.assertIn("MG-4.1-BEAT-SYNC", report["verified_machine"])

    def test_statement_reports_the_violation_count(self):
        broken = copy.deepcopy(self.storyboard)
        broken["scenes"][1]["easing"] = "linear"
        report = compliance.audit_storyboard(broken, self.sheet)
        self.assertEqual(report["statement"],
                         "MOTION SPEC: FAILED - %d violation(s) detected." % len(report["violations"]))

    def test_structure_limits_flag_empty_storyboards(self):
        report = compliance.audit_storyboard({"width": 3840, "height": 2160, "fps": 30, "scenes": []}, None)
        self.assertIn("MG-6.2-LIMITS", [item["id"] for item in report["violations"]])

    def test_non_object_storyboard_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            compliance.audit_storyboard([], None)


if __name__ == "__main__":
    unittest.main()
