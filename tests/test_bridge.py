import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_hq_bridge", ROOT / "bridge" / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def test_self_test_covers_practice_and_motion_documents(self):
        result = bridge.run_self_test()
        self.assertTrue(result["ok"], result)
        checked = set(result["syntax_checked"])
        self.assertIn("practice.py", checked)
        self.assertIn("MOTION_DESIGN_SYSTEM.md", checked)
        self.assertIn("TRAINING.md", checked)

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
