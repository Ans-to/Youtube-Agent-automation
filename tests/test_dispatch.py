import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import dispatch


class AgentDispatcherTests(unittest.TestCase):
    def test_finds_specialist_role(self):
        role = dispatch.find_role("AGENT-09")
        self.assertIsNotNone(role)
        self.assertEqual(role["name"], "Script Architect")

    def test_unknown_role_returns_none(self):
        self.assertIsNone(dispatch.find_role("AGENT-99"))

    def test_disabled_model_is_explicit_template_mode(self):
        role = dispatch.find_role("AGENT-08")
        output = dispatch.run_role(role, "Review this claim", "No sources", {"model": {"enabled": False}})
        self.assertIn("Template mode only", output)
        self.assertIn("Fact Checker", output)

    def test_slug_removes_path_separators(self):
        self.assertNotIn("/", dispatch.safe_slug("../danger/task"))


if __name__ == "__main__":
    unittest.main()
