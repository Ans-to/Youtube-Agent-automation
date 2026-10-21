import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import direction, transitions  # noqa: E402


def brief(**overrides):
    data = {
        "title": "Every Frame Is Code",
        "goal": "Show that the studio renders everything locally, with no services.",
        "tone": "cinematic",
        "platform": "youtube-4k",
        "scenes": [
            {"purpose": "hook", "headline": "Every frame is code.",
             "subhead": "A deterministic motion studio.", "duration_seconds": 4,
             "visual_type": "hero"},
            {"purpose": "process", "headline": "Nothing is filmed.",
             "subhead": "Geometry is generated per frame.", "duration_seconds": 4,
             "visual_type": "diagram", "visual_nodes": ["BRIEF", "COMPILER", "FRAMES"]},
            {"purpose": "proof", "headline": "Same input. Same pixels.",
             "subhead": "Reproducible output.", "duration_seconds": 4,
             "visual_type": "comparison", "comparison_left": ["First run"],
             "comparison_right": ["Same input"]},
        ],
    }
    data.update(overrides)
    return data


class DirectionTests(unittest.TestCase):
    def test_cinematic_four_k_compiles_to_30fps(self):
        compiled = direction.compile_brief(brief())
        sheet, storyboard = compiled["direction"], compiled["storyboard"]
        self.assertEqual((storyboard["width"], storyboard["height"]), (3840, 2160))
        self.assertEqual(storyboard["fps"], 30)
        self.assertEqual(sheet["tone"]["name"], "cinematic")
        self.assertEqual(sheet["canvas"]["aspect"], "16:9")

    def test_short_form_is_vertical_four_k_at_60fps(self):
        compiled = direction.compile_brief(brief(tone="edgy", platform="shorts-4k"))
        storyboard = compiled["storyboard"]
        self.assertEqual((storyboard["width"], storyboard["height"]), (2160, 3840))
        self.assertEqual(storyboard["fps"], 60)
        self.assertEqual(compiled["direction"]["canvas"]["aspect"], "9:16")

    def test_timeline_is_contiguous_and_labelled(self):
        sheet = direction.compile_brief(brief())["direction"]
        timeline = sheet["timeline"]
        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]["label"], "0:00-0:04")
        self.assertEqual(timeline[1]["label"], "0:04-0:08")
        self.assertEqual(timeline[-1]["end"], 12.0)
        for previous, current in zip(timeline, timeline[1:], strict=False):
            self.assertEqual(previous["end"], current["start"])
        self.assertIn("Intro", timeline[0]["beat"])
        self.assertIn("Outro", timeline[-1]["beat"])

    def test_first_scene_is_a_deliberate_cut(self):
        storyboard = direction.compile_brief(brief())["storyboard"]
        self.assertEqual(storyboard["scenes"][0]["transition_in"], "cut")

    def test_legacy_transitions_are_upgraded(self):
        data = brief()
        data["scenes"][1]["transition_in"] = "wipe-left"
        data["scenes"][2]["transition_in"] = "fade"
        storyboard = direction.compile_brief(data)["storyboard"]
        self.assertEqual(storyboard["scenes"][1]["transition_in"], "masked-reveal")
        self.assertEqual(storyboard["scenes"][2]["transition_in"], "morph")

    def test_none_becomes_a_named_cut(self):
        data = brief()
        data["scenes"][1]["transition_in"] = "none"
        storyboard = direction.compile_brief(data)["storyboard"]
        self.assertEqual(storyboard["scenes"][1]["transition_in"], "cut")
        self.assertEqual(storyboard["scenes"][1]["transition_frames"], 0)

    def test_every_scene_carries_animation_contract(self):
        storyboard = direction.compile_brief(brief())["storyboard"]
        for scene in storyboard["scenes"]:
            self.assertTrue(scene["masked"])
            self.assertIn(scene["easing"], ("editorial", "entrance", "exit", "settle", "snap", "glide", "dramatic"))
            self.assertGreaterEqual(scene["stagger_frames"], 0)
            self.assertGreaterEqual(scene["anticipation"], 0)
            self.assertLessEqual(scene["anticipation"], 0.25)
            self.assertIn(scene["transition_in"], transitions.PRO_TRANSITIONS)

    def test_timeline_names_hold_time_for_every_shot(self):
        sheet = direction.compile_brief(brief())["direction"]
        for shot in sheet["timeline"]:
            self.assertGreater(shot["hold_seconds"], 0)
            self.assertIn(shot["visual_type"], direction.VISUAL_TYPES)

    def test_layer_stack_is_back_to_front(self):
        layers = [layer["name"] for layer in direction.compile_brief(brief())["direction"]["layers"]]
        self.assertEqual(layers[0], "background")
        self.assertEqual(layers[-1], "ui")
        self.assertLess(layers.index("text"), layers.index("foreground"))

    def test_format_timeline_matches_the_requested_shape(self):
        text = direction.format_timeline(direction.compile_brief(brief())["direction"])
        self.assertIn("0:00-0:04", text)
        self.assertIn("Intro - Hook", text)
        self.assertIn("Layers:", text)

    def test_overlong_scene_produces_a_warning_not_a_crash(self):
        data = brief()
        data["scenes"][0]["headline"] = " ".join("word%d" % index for index in range(50))
        sheet = direction.compile_brief(data)["direction"]
        self.assertTrue(any("over 45" in warning for warning in sheet["warnings"]))

    def test_short_hold_for_long_copy_is_reported(self):
        data = brief()
        data["scenes"][0]["headline"] = "This headline needs more time to read than the shot allows"
        data["scenes"][0]["duration_seconds"] = 0.5
        sheet = direction.compile_brief(data)["direction"]
        self.assertTrue(any("needs" in warning for warning in sheet["warnings"]))

    def test_invalid_briefs_fail_loudly(self):
        for override, message in (
            ({"title": ""}, "title"),
            ({"goal": ""}, "goal"),
            ({"tone": "corporate-ish"}, "tone"),
            ({"platform": "tiktok"}, "platform"),
            ({"fps": 25}, "Frame rate"),
            ({"scenes": []}, "scenes"),
        ):
            with self.assertRaisesRegex(direction.BriefError, message):
                direction.compile_brief(brief(**override))

    def test_scene_validation_rejects_bad_types_and_durations(self):
        data = brief()
        data["scenes"][0]["visual_type"] = "hologram"
        with self.assertRaisesRegex(direction.BriefError, "visual_type"):
            direction.compile_brief(data)
        data = brief()
        data["scenes"][0]["duration_seconds"] = 0
        with self.assertRaisesRegex(direction.BriefError, "duration_seconds"):
            direction.compile_brief(data)

    def test_upgrade_storyboard_keeps_copy_and_upgrades_transitions(self):
        storyboard = json.loads((ROOT / "video_studio" / "storyboard.example.json").read_text())
        upgraded = direction.upgrade_storyboard(storyboard, tone="edgy")
        self.assertEqual(upgraded["scenes"][0]["transition_in"], "cut")
        self.assertEqual(upgraded["scenes"][1]["transition_in"], "masked-reveal")
        self.assertEqual(upgraded["style"]["tone"], "edgy")
        self.assertEqual(upgraded["scenes"][2]["headline"], storyboard["scenes"][2]["headline"])

    def test_summarize_storyboard_derives_a_timeline(self):
        storyboard = json.loads((ROOT / "video_studio" / "storyboard.example.json").read_text())
        sheet = direction.summarize_storyboard(storyboard, "cinematic")
        self.assertEqual(len(sheet["timeline"]), 4)
        self.assertEqual(sheet["timeline"][0]["start"], 0.0)
        self.assertEqual(sheet["timeline"][-1]["end"], 16.0)
        self.assertTrue(sheet["warnings"])

    def test_platform_capacities_are_declared(self):
        self.assertEqual(direction.PLATFORMS["broadcast-4k"]["width"], 3840)
        self.assertEqual(direction.PLATFORMS["shorts-1080"]["height"], 1920)
        with self.assertRaisesRegex(direction.BriefError, "Unknown platform"):
            direction.platform_canvas("vhs", "corporate")


if __name__ == "__main__":
    unittest.main()
