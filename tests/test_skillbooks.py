import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import dispatch


class SkillbookTests(unittest.TestCase):
    def test_every_roster_role_has_a_complete_skillbook(self):
        roster = json.loads((ROOT / "agents" / "roster.json").read_text(encoding="utf-8"))
        book = json.loads((ROOT / "agents" / "skillbooks.json").read_text(encoding="utf-8"))
        by_id = {profile["agent_id"]: profile for profile in book["profiles"]}
        self.assertEqual(set(by_id), {role["id"] for role in roster["agents"]})
        for role in roster["agents"]:
            with self.subTest(role=role["id"]):
                profile = by_id[role["id"]]
                self.assertEqual(profile["name"], role["name"])
                self.assertIsInstance(profile["workflow"], list)
                self.assertGreaterEqual(len(profile["workflow"]), 3)
                self.assertGreaterEqual(len(profile["quality_gates"]), 3)
                self.assertGreaterEqual(len(profile["failure_modes"]), 2)
                self.assertTrue(profile["deliverable_contract"])
                self.assertTrue(profile["practice_drill"])
                self.assertTrue(all(isinstance(step, str) for step in profile["workflow"]))
                self.assertTrue(all(isinstance(gate, str) for gate in profile["quality_gates"]))
                self.assertTrue(all(isinstance(mode, str) for mode in profile["failure_modes"]))

    def test_motion_roles_have_distinct_advanced_focus(self):
        director = dispatch.find_skill("AGENT-51")
        systems = dispatch.find_skill("AGENT-52")
        self.assertIn("art direction", director["expertise"].lower())
        self.assertIn("compositing", systems["expertise"].lower())
        self.assertNotEqual(director["deliverable_contract"], systems["deliverable_contract"])

    def test_human_approval_is_not_an_automatic_specialist(self):
        profile = dispatch.find_skill("AGENT-50")
        self.assertTrue(profile)
        self.assertIn("never auto-approve", profile["deliverable_contract"])


if __name__ == "__main__":
    unittest.main()
