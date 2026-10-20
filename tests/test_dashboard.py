import unittest

import dashboard


class DashboardWorkflowTests(unittest.TestCase):
    def tearDown(self):
        active = dashboard.ACTIVE_WORKFLOW
        if active:
            dashboard.release_workflow(active)

    def test_enqueue_task_creates_ceo_managed_pending_task(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "tasks.json"
            with patch.object(dashboard, "TASKS", queue):
                task_id = dashboard.enqueue_task("Video: AI agents", "youtube_package", "Create a video")
            tasks = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual(task_id, "TASK-0001")
            self.assertEqual(tasks[0]["status"], "pending")
            self.assertEqual(tasks[0]["research_status"], "pending")
            self.assertEqual(tasks[0]["kind"], "youtube_package")

    def test_enqueue_task_preserves_long_script_input_without_truncation(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "tasks.json"
            long_script = "Scene direction. " * 700
            with patch.object(dashboard, "TASKS", queue):
                task_id = dashboard.enqueue_task("Long script", "youtube_package", long_script)
            tasks = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual(tasks[0]["id"], task_id)
            self.assertEqual(tasks[0]["input"], long_script.strip())
            self.assertGreater(len(tasks[0]["input"]), 6000)

    def test_enqueue_task_rejects_inputs_over_safety_limit(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "tasks.json"
            with patch.object(dashboard, "TASKS", queue):
                with self.assertRaisesRegex(ValueError, "16,000"):
                    dashboard.enqueue_task("Too long", "youtube_package", "x" * 16001)

    def test_running_queue_records_trigger_startup_recovery_sweep(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "tasks.json"
            queue.write_text(json.dumps([{"id": "TASK-9", "status": "running"}]), encoding="utf-8")
            with patch.object(dashboard, "TASKS", queue):
                self.assertTrue(dashboard.has_running_tasks())
                self.assertFalse(dashboard.has_pending_tasks())
                queue.write_text(json.dumps([{"id": "TASK-9", "status": "needs_human_action"}]), encoding="utf-8")
                self.assertFalse(dashboard.has_running_tasks())

    def test_start_task_runner_launches_background_worker(self):
        from unittest.mock import patch
        with patch.object(dashboard, "RUNNING", False), patch.object(dashboard.threading, "Thread") as thread:
            started, active = dashboard.start_task_runner()
            self.assertTrue(started)
            self.assertEqual(active, "")
            thread.return_value.start.assert_called_once()
            dashboard.release_workflow("task runner")

    def test_attach_task_progress_reads_only_valid_task_progress_path(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress_path = root / "workspace" / "orchestration" / "task-TASK-0007" / "pipeline-progress.json"
            progress_path.parent.mkdir(parents=True)
            progress_path.write_text(json.dumps({"phase": "Specialist stage 2/4", "completed_stages": 1, "total_stages": 4}), encoding="utf-8")
            with patch.object(dashboard, "BASE", root):
                tasks = dashboard.attach_task_progress([{"id": "TASK-0007", "status": "running"}, {"id": "../unsafe", "status": "running"}])
            self.assertEqual(tasks[0]["progress"]["phase"], "Specialist stage 2/4")
            self.assertNotIn("progress", tasks[1])

    def test_release_workflow_resumes_pending_queue_exactly_once(self):
        from unittest.mock import patch
        dashboard.ACTIVE_WORKFLOW = "video workflow"
        with patch.object(dashboard, "RUNNING", False), \
             patch.object(dashboard, "has_pending_tasks", return_value=True), \
             patch.object(dashboard, "start_task_runner", return_value=(True, "")) as start:
            dashboard.release_workflow("video workflow")
        start.assert_called_once_with()
        self.assertEqual(dashboard.ACTIVE_WORKFLOW, "")

    def test_release_workflow_does_not_resume_when_name_does_not_own_gate(self):
        from unittest.mock import patch
        dashboard.ACTIVE_WORKFLOW = "different workflow"
        with patch.object(dashboard, "RUNNING", False), \
             patch.object(dashboard, "has_pending_tasks", return_value=True), \
             patch.object(dashboard, "start_task_runner") as start:
            dashboard.release_workflow("video workflow")
        start.assert_not_called()
        self.assertEqual(dashboard.ACTIVE_WORKFLOW, "different workflow")
        dashboard.release_workflow("different workflow")

    def test_workflow_gate_allows_only_one_active_workflow(self):
        claimed, active = dashboard.try_claim_workflow("test workflow")
        self.assertTrue(claimed)
        self.assertEqual(active, "")
        claimed_again, current = dashboard.try_claim_workflow("another workflow")
        self.assertFalse(claimed_again)
        self.assertEqual(current, "test workflow")
        dashboard.release_workflow("test workflow")
        claimed_after_release, _ = dashboard.try_claim_workflow("another workflow")
        self.assertTrue(claimed_after_release)

    def test_dashboard_exposes_ceo_intake_and_disables_manual_specialist_selection(self):
        for action in ('action="/generate-video"', 'action="/build-product"', 'action="/run-pipeline"', 'CEO Command Deck', 'CEO-managed queue', 'AGENT-01 (CEO) chooses the specialists', 'Direct specialist runs and manual role selection are disabled', 'progressMarkup(t)'):
            with self.subTest(action=action):
                self.assertIn(action, dashboard.HTML_PAGE)
        self.assertNotIn('name="agents"', dashboard.HTML_PAGE)
        self.assertNotIn('OPTIONAL SPECIALIST OVERRIDE', dashboard.HTML_PAGE)
        self.assertNotIn('action="/practice-agent"', dashboard.HTML_PAGE)
        self.assertNotIn('Specialist practice lab', dashboard.HTML_PAGE)
        self.assertNotIn('practiceAgent', dashboard.HTML_PAGE)
        self.assertNotIn('trainingInfo', dashboard.HTML_PAGE)

    def test_direct_specialist_route_is_blocked(self):
        import inspect
        source = inspect.getsource(dashboard.Handler.do_POST)
        self.assertIn('if path == "/practice-agent":', source)
        self.assertIn('Direct specialist execution is disabled', source)
        self.assertNotIn('agents" / "practice.py', source)

    def test_video_and_product_outputs_are_reported_in_state(self):
        state = dashboard.task_state()
        self.assertIn("video_running", state)
        self.assertIn("video_output", state)
        self.assertIn("product_running", state)
        self.assertIn("product_output", state)
        self.assertIn("training_running", state)
        self.assertIn("training_output", state)

    def test_output_markdown_renderer_formats_headings_and_lists(self):
        rendered = dashboard.render_markdown_safe("# Heading\n\n- first\n- second")
        self.assertIn("<h1>Heading</h1>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<li>first</li>", rendered)
        self.assertIn("<li>second</li>", rendered)

    def test_output_markdown_renderer_escapes_untrusted_html(self):
        rendered = dashboard.render_markdown_safe("<script>alert(1)</script>")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
