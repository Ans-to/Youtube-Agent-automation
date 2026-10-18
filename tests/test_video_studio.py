import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))
import production


class VideoStudioTests(unittest.TestCase):
    def test_example_storyboard_is_valid(self):
        path = ROOT / "video_studio" / "storyboard.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["scenes"]), 1)
        self.assertTrue(1 <= data["fps"] <= 60)
        for scene in data["scenes"]:
            self.assertGreater(scene["duration_seconds"], 0)
            self.assertIn("headline", scene)

    def test_roster_has_fifty_unique_roles(self):
        data = json.loads((ROOT / "agents" / "roster.json").read_text(encoding="utf-8"))
        agents = data["agents"]
        self.assertEqual(len(agents), 50)
        self.assertEqual(len({agent["id"] for agent in agents}), 50)
        self.assertTrue(any(agent["approval_required"] for agent in agents))

    def test_fallback_is_explicitly_not_researched(self):
        result = production.fallback("Test topic")
        self.assertEqual(len(result["scenes"]), 4)
        self.assertIn("no web research was performed", result["script"])
        self.assertTrue(all(scene["duration_seconds"] > 0 for scene in result["scenes"]))


if __name__ == "__main__":
    unittest.main()
