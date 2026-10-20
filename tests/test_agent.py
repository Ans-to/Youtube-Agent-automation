import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import agent


class AgentTests(unittest.TestCase):
    def fake_ceo_pipeline(self, task, context="", agent_ids=None, output_dir=None, config=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "01-result.md").write_text("CEO specialist deliverable", encoding="utf-8")
        manifest = {
            "delegation_mode": "heuristic_no_model",
            "model_enabled": False,
            "status": "draft",
            "ceo_assignments": [{"agent_id": "AGENT-02", "task": "Research the request"}],
            "pipeline": [{
                "sequence": 1, "agent_id": "AGENT-02", "role": "Research Lead",
                "assigned_task": "Research the request", "output_file": "01-result.md", "status": "draft_generated"
            }],
        }
        return output_dir, manifest

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
                 patch.object(agent, "OUTPUTS", root / "outputs"), patch.object(agent, "LOGS", root / "logs"), \
                 patch.object(agent, "WORKSPACE", root / "workspace"), patch.object(agent, "run_ceo_pipeline", side_effect=self.fake_ceo_pipeline):
                self.assertEqual(agent.cycle("TASK-2"), 1)
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            statuses = {task["id"]: task["status"] for task in tasks}
            self.assertEqual(statuses, {"TASK-1": "pending", "TASK-2": "completed"})
            self.assertIsNone(next(task for task in tasks if task["id"] == "TASK-2").get("worker_pid"))

    def test_cycle_processes_multiple_tasks_when_no_id_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "tasks.json"
            tasks_path.write_text(json.dumps([
                {"id": "TASK-1", "title": "First", "kind": "plan", "input": "Make a short plan", "status": "pending"},
                {"id": "TASK-2", "title": "Second", "kind": "plan", "input": "Make another plan", "status": "queued"},
            ]), encoding="utf-8")
            with patch.object(agent, "TASKS", tasks_path), patch.object(agent, "CONFIG", root / "config.json"), \
                 patch.object(agent, "OUTPUTS", root / "outputs"), patch.object(agent, "LOGS", root / "logs"), \
                 patch.object(agent, "WORKSPACE", root / "workspace"), patch.object(agent, "run_ceo_pipeline", side_effect=self.fake_ceo_pipeline):
                self.assertEqual(agent.cycle(), 2)
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assertTrue(all(task["status"] == "completed" for task in tasks))

    def test_interrupted_dead_worker_moves_to_human_action_without_replay(self):
        from datetime import datetime
        now = datetime.now().astimezone()
        task = {
            "id": "TASK-8", "status": "running", "worker_pid": 24680,
            "started_at": now.isoformat(), "output_file": "workspace/orchestration/task-TASK-8/result.md"
        }
        recovered = agent.recover_interrupted_tasks([task], now=now, alive_check=lambda pid: False)
        self.assertEqual(recovered, 1)
        self.assertEqual(task["status"], "needs_human_action")
        self.assertEqual(task["output_file"], "workspace/orchestration/task-TASK-8/result.md")
        self.assertEqual(task["interrupted_worker_pid"], 24680)
        self.assertNotIn("worker_pid", task)
        self.assertIn("explicit retry", task["error"].lower())

    def test_interrupted_task_with_live_worker_is_not_touched(self):
        from datetime import datetime
        now = datetime.now().astimezone()
        task = {"id": "TASK-9", "status": "running", "worker_pid": 24681, "started_at": now.isoformat()}
        recovered = agent.recover_interrupted_tasks([task], now=now, alive_check=lambda pid: True)
        self.assertEqual(recovered, 0)
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["worker_pid"], 24681)

    def test_legacy_running_task_uses_four_hour_fifteen_minute_grace(self):
        from datetime import datetime, timedelta
        now = datetime.now().astimezone()
        task = {
            "id": "TASK-10", "status": "running",
            "started_at": (now - timedelta(seconds=agent.LEGACY_RUNNING_TASK_GRACE_SECONDS - 60)).isoformat()
        }
        self.assertEqual(agent.recover_interrupted_tasks([task], now=now, alive_check=lambda pid: False), 0)
        self.assertEqual(task["status"], "running")
        task["started_at"] = (now - timedelta(seconds=agent.LEGACY_RUNNING_TASK_GRACE_SECONDS + 60)).isoformat()
        self.assertEqual(agent.recover_interrupted_tasks([task], now=now, alive_check=lambda pid: False), 1)
        self.assertEqual(task["status"], "needs_human_action")

    def test_legacy_running_task_with_invalid_timestamp_is_preserved(self):
        from datetime import datetime
        task = {"id": "TASK-11", "status": "running", "started_at": "not-a-timestamp"}
        self.assertEqual(agent.recover_interrupted_tasks([task], now=datetime.now().astimezone(), alive_check=lambda pid: False), 0)
        self.assertEqual(task["status"], "running")

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
