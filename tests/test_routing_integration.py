"""Routing, execution, and verification have to agree with each other.

The unit tests prove the router decides well and the tool loop builds what it is
asked for. These tests cover the seam between them: the pipeline the router chose
must be the artifact kind that was built, the artifact kind must be the contract
that was verified, and the decision must survive into the manifest. A seam like
this fails quietly — a document built as a web page still produces files — so
each test asserts the *evidence*, not just that files exist.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import orchestrate  # noqa: E402

NO_MODEL = {"model": {"enabled": False}}
WITH_MODEL = {"model": {"enabled": True, "base_url": "http://127.0.0.1:9/v1/chat/completions"}}


def route_model(*pipelines):
    """A routing model call that answers with exactly these pipeline ids."""
    payload = json.dumps({"pipelines": [{"id": item} for item in pipelines]})
    return lambda prompt, max_tokens: payload


class RunBuiltinToolsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.destination = self.root / "workspace" / "run-1"
        self.destination.mkdir(parents=True)
        patcher = patch.object(orchestrate, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tools(self, goal, cfg=NO_MODEL, model=None):
        sink = {}
        if model is not None:
            with patch.object(orchestrate, "routing_model_call", return_value=model):
                runs = orchestrate.run_builtin_tools(goal, self.destination, cfg,
                                                     route_sink=sink)
        else:
            runs = orchestrate.run_builtin_tools(goal, self.destination, cfg,
                                                 route_sink=sink)
        return runs, sink.get("route")

    def test_document_request_builds_and_verifies_a_document(self):
        runs, route = self.run_tools("Write a changelog for the v2 release")
        self.assertEqual(route.pipelines, ["document_deliverable"])
        self.assertEqual(len(runs), 1)
        result = runs[0]
        self.assertEqual(result["deliverable"], "document")
        self.assertEqual(result["selected_by"], "document_deliverable")
        self.assertEqual(result["generation_mode"], "deterministic_scaffold")
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        self.assertIn("document_structure_metadata_and_acceptance_criteria", checks[0]["checks"])

    def test_cli_request_builds_and_verifies_a_tool(self):
        runs, route = self.run_tools("Build a CLI called photo-dedupe that removes duplicate records")
        self.assertEqual(route.pipelines, ["cli_tool"])
        self.assertEqual(runs[0]["deliverable"], "cli")
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        self.assertIn("cli_parses_self_test_and_readme", checks[0]["checks"])

    def test_web_request_still_builds_a_web_page(self):
        runs, route = self.run_tools("Build a portfolio site for a photographer")
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertEqual(runs[0]["deliverable"], "web")
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])

    def test_model_route_reaches_a_document_the_patterns_miss(self):
        runs, route = self.run_tools("Make a data report for the Q3 operations review",
                                     WITH_MODEL, model=route_model("document_deliverable"))
        self.assertEqual(route.mode, "model")
        self.assertEqual(route.pipelines, ["document_deliverable"])
        self.assertEqual(route.heuristic, [])
        self.assertEqual(runs[0]["deliverable"], "document")

    def test_model_cannot_route_a_studio_to_the_video_builder(self):
        with patch.object(orchestrate, "_run_fixed_tool") as fixed_tool:
            runs, route = self.run_tools(
                "Build my YouTube automation agent studio with specialist roles",
                WITH_MODEL, model=route_model("video_production"))
        self.assertEqual(runs, [])
        fixed_tool.assert_not_called()
        self.assertTrue(any("automation studio" in veto for veto in route.vetoed))

    def test_routing_failure_does_not_stop_the_build(self):
        def broken(prompt, max_tokens):
            raise TimeoutError("local model timed out")

        runs, route = self.run_tools("Build a small web app for matching textile invoices.",
                                     WITH_MODEL, model=broken)
        self.assertEqual(route.mode, "heuristic_after_model_error")
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertEqual(runs[0]["tool"], "tool_agent")

    def test_voice_is_added_only_when_the_request_asks_for_it(self):
        # The old inline code read this phrase from the goal. Moving the decision
        # into the router must not lose it, so it stays a goal property.
        with patch.object(orchestrate, "_run_fixed_tool",
                          return_value={"tool": "video_studio", "status": "completed"}) as fixed_tool:
            self.run_tools("Create and render a video about AI agents with voice to MP4",
                           WITH_MODEL, model=route_model("video_production"))
        self.assertIn("--with-voice", fixed_tool.call_args.args[1])

        with patch.object(orchestrate, "_run_fixed_tool",
                          return_value={"tool": "video_studio", "status": "completed"}) as fixed_tool:
            self.run_tools("Create and render a video about AI agents to MP4",
                           WITH_MODEL, model=route_model("video_production"))
        self.assertNotIn("--with-voice", fixed_tool.call_args.args[1])

    def test_model_omitting_render_cannot_downgrade_an_explicit_mp4_request(self):
        # The model returned no arguments at all; the request still said "render
        # ... to MP4". Dropping that silently would be the worst outcome, so the
        # refusal is derived from the goal.
        with patch.object(orchestrate, "_run_fixed_tool",
                          return_value={"tool": "video_studio", "status": "completed"}) as fixed_tool:
            runs, route = self.run_tools(
                "Build a video about AI agents and render it to MP4",
                NO_MODEL, model=route_model("video_production"))
        self.assertEqual(route.requests[0].args, {})
        self.assertEqual(runs[0]["status"], "blocked")
        self.assertNotIn("--render", fixed_tool.call_args.args[1])

    def test_nothing_is_built_when_no_pipeline_fits(self):
        runs, route = self.run_tools("What is a knowledge graph?")
        self.assertEqual(runs, [])
        self.assertEqual(route.pipelines, [])
        self.assertTrue(route.notes)

    def test_blocked_render_keeps_the_package_and_the_refusal(self):
        with patch.object(orchestrate, "_run_fixed_tool",
                          return_value={"tool": "video_studio", "status": "completed"}) as fixed_tool:
            runs, route = self.run_tools(
                "Create and render a full YouTube video about AI agents to MP4")
        self.assertEqual(route.pipelines, ["video_production"])
        self.assertEqual([item["status"] for item in runs], ["blocked", "completed"])
        self.assertEqual(runs[0]["tool"], "video_render")
        command = fixed_tool.call_args.args[1]
        self.assertNotIn("--render", command)
        self.assertIn("production.py", command[1])


class ArtifactContractTest(unittest.TestCase):
    """A verified status must not be obtainable with dishonest artifacts."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.destination = self.root / "workspace" / "run-1"
        self.destination.mkdir(parents=True)

    def build(self, kind, goal):
        with patch.object(orchestrate, "ROOT", self.root):
            return orchestrate.run_builtin_tools(goal, self.destination, NO_MODEL)[0]

    def test_document_that_claims_ai_authorship_fails_verification(self):
        result = self.build("document", "Write a changelog for v2")
        metadata_path = self.root / result["artifact_dir"] / "deliverable.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["ai_generated"] = True
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("AI authorship" in error for error in checks[0]["errors"]))
        self.assertEqual(result["status"], "failed")

    def test_document_without_acceptance_criteria_fails_verification(self):
        result = self.build("document", "Write a changelog for v2")
        meta_path = self.root / result["artifact_dir"] / "deliverable.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata["acceptance_criteria"] = []
        meta_path.write_text(json.dumps(metadata), encoding="utf-8")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")

    def test_cli_with_a_syntax_error_fails_verification(self):
        result = self.build("cli", "Build a CLI that dedupes records")
        (self.root / result["artifact_dir"] / "tool.py").write_text("def main(:\n", encoding="utf-8")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("not valid Python" in error for error in checks[0]["errors"]))

    def test_deliverable_kind_must_match_the_summary(self):
        result = self.build("document", "Write a changelog for v2")
        summary_path = self.root / result["artifact_dir"] / "tool-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["deliverable"] = "web"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("does not match the run" in error for error in checks[0]["errors"]))


class PipelineEvidenceTest(unittest.TestCase):
    """The manifest has to explain why nothing — or something — was built."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def run_pipeline(self, goal):
        with (
            patch.object(orchestrate, "ROOT", self.root),
            patch.object(orchestrate, "WORKSPACE", self.workspace),
            patch.object(orchestrate.dispatch, "run_role",
                         side_effect=lambda role, task, context, cfg: "# Draft\n\nStage output for " + role["id"]),
        ):
            return orchestrate.run_pipeline(goal, output_dir=self.workspace / "run-route",
                                            config=NO_MODEL)

    def test_manifest_records_the_route_and_the_built_kind(self):
        destination, manifest = self.run_pipeline("Write a changelog for the v2 release")
        self.assertEqual(manifest["routing"]["pipelines"], ["document_deliverable"])
        self.assertEqual(manifest["routing"]["mode"], "heuristic")
        self.assertIn("agreement", manifest["routing"])
        self.assertEqual([run["deliverable"] for run in manifest["tool_runs"]], ["document"])
        self.assertTrue((destination / "routing.json").is_file())
        on_disk = json.loads((destination / "routing.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["pipelines"], ["document_deliverable"])
        self.assertEqual(destination, self.workspace / "run-route")

    def test_no_pipeline_run_still_records_why(self):
        destination, manifest = self.run_pipeline("What is a knowledge graph?")
        self.assertEqual(manifest["routing"]["pipelines"], [])
        self.assertEqual(manifest["tool_runs"], [])
        self.assertTrue((destination / "routing.json").is_file())

    def test_built_document_passes_the_pipeline_artifact_check(self):
        _, manifest = self.run_pipeline("Write a changelog for the v2 release")
        self.assertEqual(len(manifest["artifact_checks"]), 1)
        self.assertEqual(manifest["artifact_checks"][0]["status"], "passed",
                         manifest["artifact_checks"][0]["errors"])

    def test_routing_decision_is_bounded_and_serialisable(self):
        _, manifest = self.run_pipeline("Write a changelog for the v2 release")
        record = manifest["routing"]
        self.assertLessEqual(len(json.dumps(record)), 8000)
        self.assertNotIn(str(self.root), json.dumps(record))


if __name__ == "__main__":
    unittest.main()
