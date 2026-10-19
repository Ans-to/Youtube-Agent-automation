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

    def test_ceo_json_parser_filters_approval_and_duplicate_roles(self):
        roles = {item["id"]: item for item in orchestrate.dispatch.load_json(
            orchestrate.dispatch.ROSTER, {}
        ).get("agents", [])}
        assignments = orchestrate.parse_ceo_assignments(
            '{"assignments":['
            '{"agent_id":"AGENT-09","task":"Write the script"},'
            '{"agent_id":"AGENT-50","task":"Approve publishing"},'
            '{"agent_id":"AGENT-09","task":"Duplicate"},'
            '{"agent_id":"AGENT-08","task":"Review factual claims"}]}',
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
            self.assertEqual(results[0]["status"], "blocked")
            run_tool.assert_not_called()

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
