import json
import tempfile
import unittest
from pathlib import Path

from tools.tool_agent import (
    MAX_STEPS,
    PlanError,
    build_plan_prompt,
    deterministic_plan,
    deterministic_site_files,
    execute_plan,
    parse_plan,
    run_tool_agent,
    verify_plan,
)
from tools.tool_runtime import ToolRegistry, WorkspaceSandbox


def planner_json(steps, verify=None):
    payload = {"steps": steps}
    if verify is not None:
        payload["verify"] = verify
    return "Here is the plan.\n" + json.dumps(payload) + "\nDone."


class PromptTests(unittest.TestCase):
    def test_prompt_states_rules_catalog_and_goal(self):
        prompt = build_plan_prompt("Build a site", '[{"name":"write_file"}]', allow_exec=False)
        self.assertIn("Build a site", prompt)
        self.assertIn("write_file", prompt)
        self.assertIn("Return JSON only", prompt)
        self.assertIn("run_command is not available", prompt)
        self.assertIn("no API keys", prompt)

    def test_prompt_advertises_exec_only_when_enabled(self):
        prompt = build_plan_prompt("Do work", "[]", allow_exec=True)
        self.assertIn("run_command is available", prompt)
        self.assertIn("no shell syntax", prompt)

    def test_prompt_includes_repair_feedback(self):
        prompt = build_plan_prompt("Do work", "[]", allow_exec=False, feedback="- write_file failed: limit")
        self.assertIn("PREVIOUS ATTEMPT FAILED", prompt)
        self.assertIn("write_file failed", prompt)


class ParsePlanTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.registry = ToolRegistry(WorkspaceSandbox(Path(self._directory.name)))

    def tearDown(self):
        self._directory.cleanup()

    def test_valid_plan_round_trips(self):
        plan = parse_plan(planner_json(
            [{"tool": "write_file", "args": {"path": "index.html", "content": "<!doctype html>"}, "why": "page"}],
            [{"path": "index.html", "contains": "<!doctype html>"}],
        ), self.registry, goal="site")
        self.assertEqual(plan.mode, "model")
        self.assertEqual(plan.steps[0].tool, "write_file")
        self.assertEqual(plan.steps[0].args["path"], "index.html")
        self.assertEqual(plan.verify[0].contains, "<!doctype html>")

    def test_unknown_tools_and_bad_arguments_are_dropped(self):
        plan = parse_plan(planner_json([
            {"tool": "delete_everything", "args": {}},
            {"tool": "write_file", "args": {"path": "../escape.txt", "content": "x"}},
            {"tool": "write_file", "args": {"path": "ok.txt", "content": "fine"}},
        ]), self.registry)
        self.assertEqual([step.args["path"] for step in plan.steps], ["ok.txt"])
        self.assertIn("unknown tool", plan.notes)
        self.assertEqual(plan.verify[0].path, "ok.txt")

    def test_plan_with_no_valid_steps_is_rejected(self):
        with self.assertRaises(PlanError):
            parse_plan(planner_json([{"tool": "run_command", "args": {}}]), self.registry)

    def test_non_json_and_empty_responses_are_rejected(self):
        for response in ("I cannot help with that.", "", "{}", '{"steps": []}'):
            with self.subTest(response=response):
                with self.assertRaises(PlanError):
                    parse_plan(response, self.registry)

    def test_step_budget_is_enforced(self):
        steps = [{"tool": "write_file", "args": {"path": f"f{index}.txt", "content": "x"}} for index in range(MAX_STEPS + 5)]
        plan = parse_plan(planner_json(steps), self.registry)
        self.assertEqual(len(plan.steps), MAX_STEPS)

    def test_verify_falls_back_to_written_paths(self):
        plan = parse_plan(planner_json([
            {"tool": "write_file", "args": {"path": "a.txt", "content": "a"}},
            {"tool": "write_file", "args": {"path": "b.txt", "content": "b"}},
        ]), self.registry)
        self.assertEqual([item.path for item in plan.verify], ["a.txt", "b.txt"])

    def test_verification_list_is_capped(self):
        steps = [{"tool": "write_file", "args": {"path": "a.txt", "content": "a"}}]
        verify = [{"path": f"v{index}.txt"} for index in range(50)]
        plan = parse_plan(planner_json(steps, verify), self.registry)
        self.assertEqual(len(plan.verify), 12)

    def test_non_loopback_file_paths_in_verify_are_kept_but_fail_later(self):
        plan = parse_plan(planner_json(
            [{"tool": "write_file", "args": {"path": "a.txt", "content": "a"}}],
            [{"path": "../outside.txt"}],
        ), self.registry)
        checks = verify_plan(self.registry, plan)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertIn("escapes", checks[0]["error"])


class DeterministicPlanTests(unittest.TestCase):
    def test_site_files_are_complete_and_offline(self):
        files = deterministic_site_files("Build a landing page for a textile invoice tool")
        self.assertEqual(set(files), {"index.html", "styles.css", "app.js", "README.md"})
        self.assertIn("<!doctype html>", files["index.html"])
        self.assertIn("connect-src 'none'", files["index.html"])
        self.assertNotIn("http://", files["index.html"])
        self.assertNotIn("https://", files["index.html"])
        self.assertIn("localStorage", files["app.js"])
        self.assertIn("Textile Invoice Tool", files["index.html"])

    def test_title_derivation_strips_verbs_and_articles(self):
        files = deterministic_site_files("Please create a simple responsive portfolio for a photographer")
        self.assertIn("<h1>Portfolio</h1>", files["index.html"])

    def test_deterministic_plan_writes_and_verifies(self):
        plan = deterministic_plan("Build a website for a bakery")
        self.assertEqual(plan.mode, "deterministic")
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(WorkspaceSandbox(directory))
            results = execute_plan(registry, plan)
            checks = verify_plan(registry, plan)
        self.assertTrue(all(result["status"] == "ok" for result in results))
        self.assertTrue(all(check["status"] == "passed" for check in checks))
        self.assertTrue(all("content" not in result for result in results))


class RunToolAgentTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name) / "workspace"

    def tearDown(self):
        self._directory.cleanup()

    def test_offline_run_produces_a_verified_scaffold(self):
        result = run_tool_agent("Build a website for a bakery", self.workspace, "TASK-1")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["mode"], "deterministic")
        self.assertTrue(result["verification"])
        self.assertTrue(all(check["status"] == "passed" for check in result["verification"]))
        self.assertIn("index.html", result["artifacts"])
        self.assertTrue(result["human_review_required"])
        sandbox = Path(self._directory.name) / "workspace" / "projects" / "task-1"
        for name in ("index.html", "app.js", "tool-plan.json", "tool-runs.json", "tool-summary.json"):
            with self.subTest(name=name):
                self.assertTrue((sandbox / name).is_file())
        summary = json.loads((sandbox / "tool-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "partial")

    def test_manifest_does_not_embed_file_bodies(self):
        result = run_tool_agent("Build a site", self.workspace, "TASK-2")
        serialized = json.dumps(result)
        self.assertNotIn("Offline project scaffold", serialized)
        self.assertNotIn("localStorage.setItem", serialized)
        self.assertNotIn(str(self.workspace), serialized)

    def test_model_plan_is_executed_and_verified(self):
        def model(prompt, max_tokens):
            return planner_json(
                [{"tool": "write_file", "args": {"path": "index.html", "content": "<!doctype html><h1>Hi</h1>"}}],
                [{"path": "index.html", "contains": "<h1>Hi</h1>"}],
            )

        result = run_tool_agent("Build a one-page site", self.workspace, "TASK-3", model_call=model)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["mode"], "model")
        self.assertEqual(result["artifacts"], ["index.html"])
        self.assertEqual(len(result["attempts"]), 1)

    def test_failed_verification_triggers_a_repair(self):
        calls = []

        def model(prompt, max_tokens):
            calls.append(prompt)
            if len(calls) == 1:
                return planner_json([{"tool": "write_file", "args": {"path": "index.html", "content": "stub"}}],
                                    [{"path": "index.html", "contains": "<h1>"}])
            return planner_json([{"tool": "write_file", "args": {"path": "index.html", "content": "<h1>Fixed</h1>"}}],
                                [{"path": "index.html", "contains": "<h1>"}])

        result = run_tool_agent("Build a page", self.workspace, "TASK-4", model_call=model)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["failed_checks"] == 0)
        self.assertIn("PREVIOUS ATTEMPT FAILED", calls[1])
        self.assertIn("required text is missing", calls[1])

    def test_garbage_model_output_falls_back_to_the_deterministic_scaffold(self):
        result = run_tool_agent("Build a page", self.workspace, "TASK-5", model_call=lambda prompt, tokens: "no json here")
        self.assertEqual(result["mode"], "deterministic")
        self.assertIn("planner error", json.loads(
            (self.workspace / "projects" / "task-5" / "tool-plan.json").read_text(encoding="utf-8")
        )["notes"])

    def test_persistent_failure_reports_failed_and_keeps_workspace(self):
        def model(prompt, max_tokens):
            return planner_json([{"tool": "write_file", "args": {"path": "a.txt", "content": "x"}}],
                                [{"path": "missing.txt"}])

        result = run_tool_agent("Do something", self.workspace, "TASK-6", model_call=model, max_repairs=1)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Not verified", result["note"])
        self.assertTrue((self.workspace / "projects" / "task-6").is_dir())

    def test_task_id_cannot_escape_the_workspace(self):
        result = run_tool_agent("Build a site", self.workspace, "../../etc")
        self.assertEqual(result["artifact_dir"], "projects/etc")
        self.assertFalse((self.workspace.parent / "etc").exists())

    def test_empty_goal_is_rejected(self):
        with self.assertRaises(ValueError):
            run_tool_agent("   ", self.workspace, "TASK-7")

    def test_exec_disabled_by_default(self):
        result = run_tool_agent("Build a site", self.workspace, "TASK-8")
        self.assertFalse(result["exec_enabled"])
        self.assertNotIn("run_command", {step["tool"] for step in result["steps"]})


if __name__ == "__main__":
    unittest.main()
