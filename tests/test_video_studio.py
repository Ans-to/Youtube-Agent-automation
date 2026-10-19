import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import production
from captions import build_subtitles, validate_english_text, validate_subtitle_text


class VideoStudioTests(unittest.TestCase):
    def test_example_storyboard_is_valid(self):
        path = ROOT / "video_studio" / "storyboard.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["scenes"]), 1)
        self.assertTrue(1 <= data["fps"] <= 60)
        for scene in data["scenes"]:
            self.assertGreater(scene["duration_seconds"], 0)
            self.assertIn("headline", scene)

    def test_roster_has_fifty_two_unique_role_profiles(self):
        data = json.loads((ROOT / "agents" / "roster.json").read_text(encoding="utf-8"))
        agents = data["agents"]
        self.assertEqual(len(agents), 52)
        self.assertEqual(len({agent["id"] for agent in agents}), 52)
        self.assertIn("Motion Graphics Creative Director", {agent["name"] for agent in agents})
        self.assertIn("Motion Systems & Compositing Specialist", {agent["name"] for agent in agents})
        self.assertTrue(any(agent["approval_required"] for agent in agents))

    def test_fallback_is_explicitly_not_researched(self):
        result = production.fallback("Test topic")
        self.assertEqual(len(result["scenes"]), 4)
        self.assertIn("no web research was performed", result["script"])
        self.assertTrue(all(scene["duration_seconds"] > 0 for scene in result["scenes"]))
        self.assertTrue(all(scene.get("visual_type") in {"hero", "diagram", "code", "timeline"} for scene in result["scenes"]))



    def test_all_fallback_narration_is_english(self):
        result = production.fallback("Test topic")
        for index, scene in enumerate(result["scenes"], 1):
            with self.subTest(scene=index):
                self.assertEqual(validate_english_text(scene["narration"]), scene["narration"])

    def test_non_english_script_is_rejected_for_voiceover(self):
        with self.assertRaisesRegex(ValueError, "must be English"):
            validate_english_text("یہ اردو narration ہے")

    def test_subtitle_generation_emits_valid_srt_and_webvtt(self):
        storyboard = {
            "scenes": [
                {"duration_seconds": 4.0, "narration_duration_seconds": 3.2,
                 "narration": "English narration must always have matching subtitles."},
                {"duration_seconds": 3.0, "narration_duration_seconds": 2.4,
                 "narration": "Transitions should support the story, not distract."}
            ]
        }
        srt, vtt = build_subtitles(storyboard)
        report = validate_subtitle_text(srt, vtt)
        self.assertGreaterEqual(report["cue_count"], 2)
        self.assertIn("English narration must always have", srt)
        self.assertIn("matching subtitles.", srt)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertEqual(storyboard["scenes"][0]["caption"], storyboard["scenes"][0]["narration"])

    def test_subtitle_validation_rejects_empty_files(self):
        with self.assertRaisesRegex(ValueError, "required"):
            validate_subtitle_text("", "WEBVTT\\n")

    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    production.post_local_model(url, {}, 1)

if __name__ == "__main__":
    unittest.main()
