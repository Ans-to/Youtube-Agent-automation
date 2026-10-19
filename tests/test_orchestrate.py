import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import orchestrate


class CEODelegationTests(unittest.TestCase):
    def test_heuristic_delegation_is_task_specific_and_has_quality_gate(self):
        assignments, mode = orchestrate.heuristic_assignments(
            "Create a faceless Urdu YouTube video with premium motion graphics and captions"
        )
        ids = [item["agent_id"] for item in assignments]
        self.assertEqual(mode, "heuristic_no_model")
        self.assertIn("AGENT-09", ids)
        self.assertIn("AGENT-51", ids)
        self.assertIn("AGENT-52", ids)
        self.assertIn("AGENT-08", ids)
        self.assertNotIn("AGENT-01", ids)
        self.assertNotIn("AGENT-50", ids)
        self.assertLessEqual(len(ids), 8)

    def test_youtube_automation_studio_routes_to_software_specialists(self):
        assignments, mode = orchestrate.heuristic_assignments(
            "Build my YouTube automation agent studio with specialist roles"
        )
        ids = [item["agent_id"] for item in assignments]
        self.assertEqual(mode, "heuristic_no_model")
        self.assertIn("AGENT-46", ids)
        self.assertIn("AGENT-47", ids)
        self.assertIn("AGENT-48", ids)
        self.assertNotIn("AGENT-09", ids)
        self.assertNotIn("AGENT-51", ids)
        self.assertNotIn("AGENT-52", ids)

    def test_enabled_ceo_model_plan_is_used_when_json_is_valid(self):
        roles = {item.get("id"): item for item in orchestrate.dispatch.load_json(
            orchestrate.dispatch.ROSTER, {}
        ).get("agents", [])}
        planned = '{"assignments":[{"agent_id":"AGENT-09","task":"Write the script"}]}'
        with patch.object(orchestrate.dispatch, "run_role", return_value=planned) as run_role:
            assignments, mode = orchestrate.plan_delegation(
                "Create a YouTube script",
                "",
                {"model": {"enabled": True}},
                roles,
            )
        self.assertEqual(mode, "ceo_model_delegation")
        self.assertEqual([item["agent_id"] for item in assignments], ["AGENT-09", "AGENT-08"])
        self.assertEqual(run_role.call_args.args[0]["id"], "AGENT-01")

    def test_ceo_json_parser_filters_approval_and_duplicate_roles(self):
        roles = {item["id"]: item for item in orchestrate.dispatch.load_json(
            orchestrate.dispatch.ROSTER, {}
        ).get("agents", [])}
        assignments = orchestrate.parse_ceo_assignments(
            '{"assignments":['
            '{"agent_id":"AGENT-08","task":"Review factual claims"},'
            '{"agent_id":"AGENT-09","task":"Write the script"},'
            '{"agent_id":"AGENT-50","task":"Approve publishing"},'
            '{"agent_id":"AGENT-09","task":"Duplicate"}]}',
            roles,
        )
        ids = [item["agent_id"] for item in assignments]
        self.assertEqual(ids, ["AGENT-09", "AGENT-08"])
        self.assertEqual(assignments[0]["task"], "Write the script")

    def test_product_request_routes_to_fixed_product_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            destination = workspace / "run-1"
            destination.mkdir(parents=True)
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "_run_fixed_tool", return_value={"tool": "product_studio", "status": "completed"}) as run_tool:
                results = orchestrate.run_builtin_tools(
                    "Build a digital product prototype for textile invoice reconciliation",
                    destination,
                    {"model": {"enabled": False}},
                )
            self.assertEqual(results[0]["tool"], "product_studio")
            self.assertEqual(results[0]["status"], "completed")
            self.assertIn("build_product.py", run_tool.call_args.args[1][1])

    def test_small_web_app_request_routes_clean_user_request_to_product_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            destination = workspace / "run-1"
            destination.mkdir(parents=True)
            request = "Build a small web app for matching textile invoices."
            wrapped = (
                "TASK TYPE: draft\nTASK TITLE: Invoice matcher\nUSER REQUEST:\n" + request
                + "\n\nREQUIRED OUTCOME: produce the requested usable deliverable, not just advice."
            )
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "_run_fixed_tool", return_value={"tool": "product_studio", "status": "completed"}) as run_tool:
                results = orchestrate.run_builtin_tools(
                    wrapped,
                    destination,
                    {"model": {"enabled": False}},
                )
            self.assertEqual(results[0]["tool"], "product_studio")
            command = run_tool.call_args.args[1]
            self.assertEqual(command[command.index("--idea") + 1], request)
            self.assertNotIn("TASK TYPE", command[command.index("--idea") + 1])

    def test_youtube_automation_software_does_not_trigger_video_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            destination = workspace / "run-1"
            destination.mkdir(parents=True)
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "_run_fixed_tool") as run_tool:
                results = orchestrate.run_builtin_tools(
                    "Build my YouTube automation agent studio with specialist roles",
                    destination,
                    {"model": {"enabled": False}},
                )
            self.assertEqual(results, [])
            run_tool.assert_not_called()

    def test_video_builder_does_not_substitute_template_for_full_video_without_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            destination = workspace / "run-1"
            destination.mkdir(parents=True)
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "_run_fixed_tool") as run_tool:
                results = orchestrate.run_builtin_tools(
                    "Create and render a full YouTube video about AI agents to MP4",
                    destination,
                    {"model": {"enabled": False}},
                )
            self.assertEqual(results[0]["tool"], "video_render")
            self.assertEqual(results[0]["status"], "blocked")
            run_tool.assert_called_once()
            command = run_tool.call_args.args[1]
            self.assertIn("production.py", command[1])
            self.assertNotIn("--render", command)
            self.assertIn("--research", command)

    def test_pipeline_status_is_blocked_when_full_render_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            output = workspace / "run-video"
            roles = orchestrate.dispatch.load_json(orchestrate.dispatch.ROSTER, {}).get("agents", [])
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "WORKSPACE", workspace), \
                 patch.object(orchestrate.dispatch, "run_role", return_value="# Draft\n\nTemplate-only stage output"), \
                 patch.object(orchestrate, "_run_fixed_tool", return_value={"tool": "video_studio", "status": "completed"}):
                _, manifest = orchestrate.run_pipeline(
                    "Create and render a full YouTube video about AI agents to MP4",
                    output_dir=output,
                    config={"model": {"enabled": False}},
                )
            self.assertEqual(manifest["status"], "blocked")
            self.assertTrue(any(item.get("tool") == "video_render" and item.get("status") == "blocked"
                                for item in manifest["tool_runs"]))

    def test_explicit_reviewer_failure_is_preserved_in_pipeline_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            output = workspace / "run-review"
            def fake_role(role, task, context, cfg):
                if role["id"] == "AGENT-08":
                    return "# Review\n\nOVERALL QUALITY GATE: FAIL\n"
                return "# Deliverable\n\nDraft output for " + role["id"]
            with patch.object(orchestrate, "ROOT", root), \
                 patch.object(orchestrate, "WORKSPACE", workspace), \
                 patch.object(orchestrate.dispatch, "run_role", side_effect=fake_role):
                _, manifest = orchestrate.run_pipeline(
                    "Summarize the key facts and uncertainties about textile traceability",
                    output_dir=output,
                    config={"model": {"enabled": False}},
                )
            self.assertEqual(manifest["quality_gate"], "fail")
            self.assertEqual(manifest["status"], "review_failed")

    def test_pipeline_persists_ceo_plan_and_individual_deliverables(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            output = workspace / "run-1"
            roles = orchestrate.dispatch.load_json(orchestrate.dispatch.ROSTER, {}).get("agents", [])
            calls = []

            def fake_role(role, task, context, cfg):
                calls.append((role["id"], task))
                return "# Deliverable\n\nCompleted subtask for " + role["id"]

            with patch.object(orchestrate, "WORKSPACE", workspace), \
                 patch.object(orchestrate.dispatch, "run_role", side_effect=fake_role):
                destination, manifest = orchestrate.run_pipeline(
                    "Build a small software tool with documentation and quality checks",
                    output_dir=output,
                    config={"model": {"enabled": False}},
                )

            self.assertEqual(manifest["delegation_mode"], "heuristic_no_model")
            self.assertTrue((destination / "00-ceo-delegation.json").is_file())
            self.assertTrue((destination / "pipeline-status.json").is_file())
            self.assertGreaterEqual(len(calls), 2)
            saved_plan = json.loads((destination / "00-ceo-delegation.json").read_text(encoding="utf-8"))
            self.assertTrue(saved_plan["assignments"])
            for record in manifest["pipeline"]:
                if record.get("output_file"):
                    self.assertTrue((destination / record["output_file"]).is_file())
            self.assertTrue(all("CEO-ASSIGNED SUBTASK" in task for _, task in calls))


if __name__ == "__main__":
    unittest.main()
