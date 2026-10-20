import importlib.util
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_hq_bridge", ROOT / "bridge" / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_seen_request_state_rejects_corrupt_or_invalid_state(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "seen-request-ids.json"
            self.assertEqual(bridge.load_seen_request_ids(state), set())
            state.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to process requests"):
                bridge.load_seen_request_ids(state)
            state.write_text('{"not": "a list"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid"):
                bridge.load_seen_request_ids(state)
            state.write_text('["../unsafe"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid"):
                bridge.load_seen_request_ids(state)
            state.write_text('["request-1", "request-1"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid"):
                bridge.load_seen_request_ids(state)

    def test_request_replay_state_blocks_completed_and_interrupted_requests(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(bridge.request_replay_state("request-1", root), "new")
            (root / "request-1.processing.json").write_text("{}", encoding="utf-8")
            self.assertEqual(bridge.request_replay_state("request-1", root), "interrupted")
            (root / "request-1.result.json").write_text("{}", encoding="utf-8")
            self.assertEqual(bridge.request_replay_state("request-1", root), "completed")

    def test_claim_request_is_exclusive_and_atomic(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(bridge.claim_request("request-1", Path(directory), "a" * 64))
            self.assertFalse(bridge.claim_request("request-1", Path(directory), "b" * 64))
            marker = json.loads((Path(directory) / "request-1.processing.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["request_sha256"], "a" * 64)

    def test_self_test_covers_practice_and_motion_documents(self):
        with patch.object(bridge, "PROJECT", ROOT):
            result = bridge.run_self_test()
        self.assertTrue(result["ok"], result)
        checked = set(result["syntax_checked"])
        self.assertIn("practice.py", checked)
        self.assertIn("piper_urdu_tts_adapter.py", checked)
        self.assertIn("quality_audit.py", checked)
        self.assertIn("run_quality_gate.py", checked)
        self.assertIn("config.example.json", checked)
        self.assertIn("MOTION_DESIGN_SYSTEM.md", checked)
        self.assertIn("TRAINING.md", checked)


    def test_get_file_reads_the_configured_inbox_branch(self):
        with patch.object(bridge, "BRANCH", "mobile-agent-inbox"), patch.object(
            bridge, "api_get", return_value={"type": "dir"}
        ) as api:
            bridge.get_file("bridge/requests", "token")
        api.assert_called_once_with(
            "/repos/" + bridge.REPO + "/contents/bridge/requests?ref=mobile-agent-inbox",
            "token",
        )

    def test_create_local_task_adds_approved_bounded_task_atomically(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project.mkdir(exist_ok=True)
            (project / "tasks.json").write_text(
                json.dumps([{"id": "TASK-0004", "status": "completed"}]),
                encoding="utf-8",
            )
            with patch.object(bridge, "PROJECT", project):
                result = bridge.create_local_task(
                    "Mobile task", "youtube_package", "Make a researched Urdu-English video draft."
                )
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["task_id"], "TASK-0005")
            self.assertEqual(result["status"], "queued")
            tasks = json.loads((project / "tasks.json").read_text(encoding="utf-8"))
            self.assertEqual(tasks[-1]["kind"], "youtube_package")
            self.assertEqual(tasks[-1]["status"], "pending")
            self.assertEqual(tasks[-1]["created_via"], "approved_github_mobile_bridge")

    def test_create_local_task_rejects_invalid_kind_and_oversized_input(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with patch.object(bridge, "PROJECT", project):
                bad_kind = bridge.create_local_task("Mobile task", "shell", "do anything")
                too_long = bridge.create_local_task("Mobile task", "draft", "x" * 16001)
            self.assertFalse(bad_kind["ok"])
            self.assertFalse(too_long["ok"])
            self.assertFalse((project / "tasks.json").exists())

    def test_mobile_task_result_exposes_only_task_id_and_status(self):
        public = bridge.public_result({
            "id": "create-task-1",
            "action": "create_task",
            "completed_at": "now",
            "result": {
                "ok": True, "task_id": "TASK-0005", "status": "queued",
                "input": "PRIVATE PROMPT", "project_path": "/private/path",
            },
        })
        self.assertEqual(public["result"]["task_id"], "TASK-0005")
        self.assertEqual(public["result"]["status"], "queued")
        self.assertNotIn("PRIVATE PROMPT", str(public))
        self.assertNotIn("/private/path", str(public))

    def test_valid_request_ids_are_path_safe(self):
        self.assertTrue(bridge.valid_request_id("self-test-004"))
        self.assertTrue(bridge.valid_request_id("run_task_12"))
        self.assertFalse(bridge.valid_request_id("../secret"))
        self.assertFalse(bridge.valid_request_id("id/with/slash"))
        self.assertFalse(bridge.valid_request_id(""))

    def test_public_result_does_not_publish_task_output_or_paths(self):
        response = {
            "id": "run-task-12",
            "action": "run_task",
            "completed_at": "2026-01-01T00:00:00+00:00",
            "result": {
                "ok": True,
                "task_id": "TASK-0009",
                "status": "completed",
                "stdout_tail": "PRIVATE PROMPT",
                "stderr_tail": "PRIVATE ERROR DETAIL",
                "output_file": "outputs/TASK-0009.md",
            },
        }
        public = bridge.public_result(response)
        serialized = str(public)
        self.assertNotIn("PRIVATE PROMPT", serialized)
        self.assertNotIn("PRIVATE ERROR DETAIL", serialized)
        self.assertNotIn("outputs/TASK-0009.md", serialized)
        self.assertEqual(public["result"]["status"], "completed")
        self.assertEqual(public["result"]["task_id"], "TASK-0009")

    def test_self_test_report_only_lists_expected_source_names(self):
        public = bridge.public_result({
            "id": "self-test-10",
            "action": "self_test",
            "completed_at": "now",
            "result": {
                "ok": True,
                "syntax_checked": ["agent.py", "dashboard.py", "/private/path"],
                "note": "private local note",
            },
        })
        self.assertEqual(public["result"]["syntax_checked"], ["agent.py", "dashboard.py"])
        self.assertNotIn("private local note", str(public))


if __name__ == "__main__":
    unittest.main()
