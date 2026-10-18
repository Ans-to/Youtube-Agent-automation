import unittest

import agent


class AgentTests(unittest.TestCase):
    def test_safe_id_removes_path_separators(self):
        self.assertEqual(agent.safe_id("../../TASK-0007"), "TASK-0007")

    def test_safe_id_has_fallback(self):
        self.assertEqual(agent.safe_id("///"), "TASK")

    def test_plan_fallback_is_explicit_about_template_mode(self):
        task = {"id": "TEST-1", "title": "Checklist", "input": "Make a small checklist"}
        output = agent.fallback(task, "plan", "")
        self.assertIn("# Checklist", output)
        self.assertIn("Template mode only", output)

    def test_prompt_contains_action_verification_guard(self):
        task = {"id": "TEST-2", "title": "Alarm", "input": "Set an alarm"}
        prompt = agent.build_prompt(task, "plan", "", {})
        self.assertIn("Never say an alarm was set", prompt)
        self.assertIn("NOT performed or verified", prompt)


if __name__ == "__main__":
    unittest.main()
