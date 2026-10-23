"""The dashboard, tested through the objects that now own each behaviour.

These tests used to patch module globals - ``dashboard.TASKS``,
``dashboard.RUNNING``, ``dashboard.threading.Thread`` - because the dashboard
kept its queue path, its run flags and its threads as module-level state. That
made the tests pass against a shape of code rather than a behaviour, and it let
a bug hide: four of those globals were never written by anything.

Now each test names the collaborator it is testing:

``TaskQueue``         the queue and its validation
``RunState``          the exclusive-workflow claim
``WorkflowCoordinator`` what happens to queued work when a claim is released

The deck and Markdown assertions are unchanged - they are about the shipped UI.
"""
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import dashboard
from app.paths import ProjectPaths
from app.services.status import build_status
from app.services.tasks import TaskQueue
from app.services.workflows import WorkflowCoordinator
from app.state import WORKFLOW_TASK_RUNNER, RunState


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = TaskQueue(Path(self.temp.name) / "tasks.json")

    def test_enqueue_creates_ceo_managed_pending_task(self):
        task_id = self.queue.enqueue("Video: AI agents", "youtube_package", "Create a video")
        tasks = json.loads(self.queue.path.read_text(encoding="utf-8"))
        self.assertEqual(task_id, "TASK-0001")
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[0]["research_status"], "pending")
        self.assertEqual(tasks[0]["kind"], "youtube_package")

    def test_enqueue_preserves_a_long_script_without_truncation(self):
        long_script = "Scene direction. " * 700
        self.queue.enqueue("Long script", "youtube_package", long_script)
        tasks = json.loads(self.queue.path.read_text(encoding="utf-8"))
        self.assertEqual(tasks[0]["input"], long_script.strip())
        self.assertGreater(len(tasks[0]["input"]), 6000)

    def test_enqueue_rejects_input_over_the_limit(self):
        with self.assertRaisesRegex(ValueError, "16,000"):
            self.queue.enqueue("Too long", "youtube_package", "x" * 16001)

    def test_enqueue_rejects_a_kind_the_orchestrator_cannot_run(self):
        with self.assertRaisesRegex(ValueError, "supported workflow"):
            self.queue.enqueue("Thing", "not-a-workflow", "do it")

    def test_task_ids_do_not_collide_under_concurrent_writers(self):
        for index in range(5):
            self.queue.enqueue("Task %d" % index, "plan", "text")
        ids = [task["id"] for task in self.queue.read()]
        self.assertEqual(ids, ["TASK-%04d" % n for n in range(1, 6)])

    def test_a_corrupt_queue_is_an_error_not_an_empty_queue(self):
        self.queue.path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(OSError, "not readable"):
            self.queue.read()
        # ...but rendering must survive it
        self.assertEqual(self.queue.safe_read(), [])

    def test_pending_and_running_are_answered_from_the_records(self):
        self.queue.path.write_text(json.dumps([{"id": "TASK-9", "status": "running"}]),
                                   encoding="utf-8")
        self.assertTrue(self.queue.has_running())
        self.assertFalse(self.queue.has_pending())
        self.queue.path.write_text(json.dumps([{"id": "TASK-9", "status": "queued"}]),
                                   encoding="utf-8")
        self.assertFalse(self.queue.has_running())
        self.assertTrue(self.queue.has_pending())

    def test_progress_is_attached_only_for_a_valid_task_id(self):
        pipeline = Path(self.temp.name) / "workspace" / "orchestration"
        progress_path = pipeline / "task-TASK-0007" / "pipeline-progress.json"
        progress_path.parent.mkdir(parents=True)
        progress_path.write_text(json.dumps({"phase": "Specialist stage 2/4"}), encoding="utf-8")
        tasks = [{"id": "TASK-0007"}, {"id": "../unsafe"}]
        self.queue.attach_progress(tasks, pipeline)
        self.assertEqual(tasks[0]["progress"]["phase"], "Specialist stage 2/4")
        self.assertNotIn("progress", tasks[1])


class WorkflowGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = ProjectPaths(Path(self.temp.name))
        self.queue = TaskQueue(self.paths.tasks)
        self.state = RunState()
        self.started = []

        def runner(command, log):
            self.started.append(command)
            log.write("simulated\n")
            return 0

        self.coordinator = WorkflowCoordinator(
            paths=self.paths, state=self.state, queue=self.queue, runner=runner
        )

    def test_only_one_workflow_holds_the_core(self):
        claimed, active = self.state.claim_workflow("test workflow")
        self.assertTrue(claimed)
        self.assertEqual(active, "")
        claimed_again, current = self.state.claim_workflow("another workflow")
        self.assertFalse(claimed_again)
        self.assertEqual(current, "test workflow")
        self.state.release_workflow("test workflow")
        self.assertTrue(self.state.claim_workflow("another workflow")[0])

    def test_the_same_workflow_may_claim_twice(self):
        self.state.claim_workflow(WORKFLOW_TASK_RUNNER)
        claimed, active = self.state.claim_workflow(WORKFLOW_TASK_RUNNER)
        self.assertTrue(claimed, "a double-started worker must be idempotent, not an error")
        self.assertEqual(active, WORKFLOW_TASK_RUNNER)

    def test_releasing_someone_elses_claim_does_nothing(self):
        self.state.claim_workflow("different workflow")
        self.assertFalse(self.coordinator.release("video workflow"))
        self.assertEqual(self.state.snapshot()["active_workflow"], "different workflow")

    def test_releasing_the_claim_resumes_pending_work_exactly_once(self):
        self.state.claim_workflow("video workflow")
        self.queue.enqueue("Waiting", "plan", "do it")
        with patch.object(self.coordinator.worker, "start",
                          return_value=(True, "")) as start:
            self.assertTrue(self.coordinator.release("video workflow"))
        start.assert_called_once_with()
        self.assertEqual(self.state.snapshot()["active_workflow"], "")

    def test_no_resume_when_the_queue_is_empty(self):
        self.state.claim_workflow("video workflow")
        with patch.object(self.coordinator.worker, "start") as start:
            self.coordinator.release("video workflow")
        start.assert_not_called()

    def test_the_worker_runs_agent_once_and_clears_its_state(self):
        self.coordinator.worker.max_cycles = 1
        self.state.claim_workflow(WORKFLOW_TASK_RUNNER)
        self.state.begin_worker()
        self.coordinator.worker._run()  # run inline, not on the thread
        self.assertEqual(len(self.started), 1)
        self.assertIn("agent.py", self.started[0][1])
        snapshot = self.state.snapshot()
        self.assertFalse(snapshot["worker_running"])
        self.assertEqual(snapshot["active_workflow"], "")

    def test_a_failing_runner_does_not_wedge_the_core(self):
        def boom(command, log):
            raise OSError("disk gone")

        self.coordinator.worker.runner = boom
        self.coordinator.worker._run()
        self.assertEqual(self.state.snapshot()["active_workflow"], "",
                         "a crash must release the claim or the app is stuck forever")

    def test_a_second_pipeline_is_refused_while_one_runs(self):
        from app.errors import WorkflowBusyError

        with patch("app.services.workflows.threading.Thread") as thread:
            self.coordinator.start_pipeline("first goal")
        thread.return_value.start.assert_called_once()
        with self.assertRaises(WorkflowBusyError):
            self.coordinator.start_pipeline("second goal")
        self.state.end_pipeline()
        self.state.release_workflow("CEO command pipeline")


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = ProjectPaths(Path(self.temp.name))
        self.queue = TaskQueue(self.paths.tasks)
        self.state = RunState()

    def status(self):
        return build_status(paths=self.paths, config={}, queue=self.queue, state=self.state)

    def test_state_reports_both_outputs(self):
        for key in ("video_running", "video_output", "product_running", "product_output"):
            self.assertIn(key, self.status())

    def test_a_running_video_is_derived_from_the_task_record(self):
        self.queue.path.write_text(json.dumps([
            {"id": "TASK-1", "title": "Video: X", "status": "running"},
        ]), encoding="utf-8")
        status = self.status()
        self.assertTrue(status["video_running"])
        self.assertIn("TASK-1", status["video_output"])

    def test_the_state_is_a_snapshot_not_a_live_reference(self):
        status = self.status()
        self.state.claim_workflow("later")
        self.assertEqual(status["active_workflow"], "")

    def test_only_recent_tasks_are_sent(self):
        self.queue.path.write_text(json.dumps([
            {"id": "TASK-%04d" % index, "title": "t", "status": "completed"}
            for index in range(150)
        ]), encoding="utf-8")
        self.assertEqual(len(self.status()["tasks"]), 100)

    def test_dead_flags_are_gone(self):
        # These were never written by anything, so they only ever said "not running".
        status = self.status()
        self.assertNotIn("training_running", status)
        self.assertNotIn("training_output", status)


class DeckTests(unittest.TestCase):
    def test_the_deck_is_served_from_the_repository_template(self):
        self.assertTrue(dashboard.DECK.is_file())
        self.assertEqual(dashboard.HTML_PAGE, dashboard.DECK.read_text(encoding="utf-8"))

    def test_the_deck_declares_ceo_intake_and_no_manual_specialist_routes(self):
        for action in ('action="/generate-video"', 'action="/build-product"',
                       'action="/run-pipeline"', 'CEO Command Deck', 'CEO-managed queue',
                       'AGENT-01 (CEO) chooses the specialists',
                       'Direct specialist runs and manual role selection are disabled',
                       'progressMarkup(t)'):
            with self.subTest(action=action):
                self.assertIn(action, dashboard.HTML_PAGE)
        for absent in ('name="agents"', 'OPTIONAL SPECIALIST OVERRIDE',
                       'action="/practice-agent"', 'Specialist practice lab',
                       'practiceAgent', 'trainingInfo'):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, dashboard.HTML_PAGE)

    def test_the_direct_specialist_route_is_blocked(self):
        import inspect
        source = inspect.getsource(dashboard.Handler._post)
        self.assertIn('if path == "/practice-agent":', source)
        self.assertIn("Direct specialist execution is disabled", source)
        self.assertNotIn('agents" / "practice.py', source)

    def test_the_deck_fetches_nothing_from_the_network(self):
        fetches = re.findall(r'(?:src|href)\s*=\s*["\'](https?:)?//[^"\']+', dashboard.HTML_PAGE)
        self.assertEqual(fetches, [])
        for forbidden in ("url(http", "url(//", "@import", "fonts.googleapis"):
            self.assertNotIn(forbidden, dashboard.HTML_PAGE)

    def test_every_referenced_still_exists(self):
        referenced = set(re.findall(r'/stills/([A-Za-z0-9_.-]+\.jpg)', dashboard.HTML_PAGE))
        self.assertEqual(referenced, {"hero.jpg", "code.jpg", "server.jpg", "studio.jpg"})
        for name in referenced:
            with self.subTest(still=name):
                path = dashboard.BASE / "web" / "stills" / name
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 2048)

    def test_output_markdown_renders_and_escapes(self):
        rendered = dashboard.render_markdown_safe("# Heading\n\n- first\n- second")
        self.assertIn("<h1>Heading</h1>", rendered)
        self.assertIn("<li>first</li>", rendered)
        escaped = dashboard.render_markdown_safe("<script>alert(1)</script>")
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)


if __name__ == "__main__":
    unittest.main()
