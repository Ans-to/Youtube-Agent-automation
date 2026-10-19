import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

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
        self.assertIn("offline structured plan", output.lower())

    def test_prompt_contains_action_verification_guard(self):
        task = {"id": "TEST-2", "title": "Alarm", "input": "Set an alarm"}
        prompt = agent.build_prompt(task, "plan", "", {})
        self.assertIn("Never say an alarm was set", prompt)
        self.assertIn("NOT performed or verified", prompt)



    def test_cycle_processes_only_requested_task_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "tasks.json"
            tasks_path.write_text(json.dumps([
                {"id": "TASK-1", "title": "First", "kind": "plan", "input": "Make a short plan", "status": "pending"},
                {"id": "TASK-2", "title": "Second", "kind": "plan", "input": "Make another plan", "status": "pending"},
            ]), encoding="utf-8")
            with patch.object(agent, "TASKS", tasks_path), patch.object(agent, "CONFIG", root / "config.json"), \
                 patch.object(agent, "OUTPUTS", root / "outputs"), patch.object(agent, "LOGS", root / "logs"):
                self.assertEqual(agent.cycle("TASK-2"), 1)
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            statuses = {task["id"]: task["status"] for task in tasks}
            self.assertEqual(statuses, {"TASK-1": "pending", "TASK-2": "completed"})

    def test_cycle_processes_multiple_tasks_when_no_id_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "tasks.json"
            tasks_path.write_text(json.dumps([
                {"id": "TASK-1", "title": "First", "kind": "plan", "input": "Make a short plan", "status": "pending"},
                {"id": "TASK-2", "title": "Second", "kind": "plan", "input": "Make another plan", "status": "queued"},
            ]), encoding="utf-8")
            with patch.object(agent, "TASKS", tasks_path), patch.object(agent, "CONFIG", root / "config.json"), \
                 patch.object(agent, "OUTPUTS", root / "outputs"), patch.object(agent, "LOGS", root / "logs"):
                self.assertEqual(agent.cycle(), 2)
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assertTrue(all(task["status"] == "completed" for task in tasks))

    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    agent.post_local_model(url, {}, 1)

if __name__ == "__main__":
    unittest.main()
