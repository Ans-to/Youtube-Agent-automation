"""The router must choose among real pipelines, and must refuse to invent one.

Phase 2 of the roadmap replaced the regex intent classifier with a routing layer.
The risk in that change is not that routing fails loudly — it is that it fails
*plausibly*: a model picks a pipeline id that looks right, an argument quietly
becomes a different kind of value, or a guard that used to be a regex stops
applying because a model now makes the decision.

These tests pin the contract:

* the catalog is the single source of truth for which pipelines exist and what
  arguments each accepts;
* the deterministic router reproduces the behaviour it replaced, exactly;
* a model may choose from the catalog and nothing else, and its arguments are
  validated rather than trusted;
* vetoes apply to model choices too, so routing can add coverage without
  removing a guard.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))
import routing  # noqa: E402
import tool_runtime  # noqa: E402

NO_MODEL = {"model": {"enabled": False}}
WITH_MODEL = {"model": {"enabled": True}}


def fake_model(payload):
    """A model call that always answers with `payload` (a dict is JSON-encoded)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return lambda prompt, max_tokens: text


class CatalogTest(unittest.TestCase):
    def test_ids_are_unique_and_executable(self):
        ids = [spec.id for spec in routing.PIPELINES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(routing.PIPELINES_BY_ID))
        for spec in routing.PIPELINES:
            self.assertTrue(spec.summary.strip(), spec.id)
            self.assertTrue(spec.executor.strip(), spec.id)
            self.assertIn(spec.deliverable, {"web", "document", "cli", "video_package", "product_prototype"})

    def test_tool_loop_pipelines_match_the_deliverable_kinds(self):
        # A pipeline that runs the tool loop must declare a kind the loop accepts.
        kinds = {routing.PIPELINES_BY_ID[pid].deliverable for pid in routing.TOOL_LOOP_PIPELINES}
        import tool_agent

        self.assertEqual(kinds, set(tool_agent.DELIVERABLES))

    def test_catalog_json_is_complete_and_round_trips(self):
        catalog = json.loads(routing.pipeline_catalog())
        self.assertEqual(len(catalog), len(routing.PIPELINES))
        by_id = {entry["id"]: entry for entry in catalog}
        self.assertIn("write_file", routing.tool_catalog())
        for pipeline_id, entry in by_id.items():
            self.assertEqual(entry["deliverable"], routing.PIPELINES_BY_ID[pipeline_id].deliverable)
            self.assertIsInstance(entry["args"], dict)
            self.assertNotIn("default", json.dumps(entry["args"]))

    def test_declared_arguments_validate_through_the_shared_validator(self):
        # The catalog's arg schemas are enforced by the same code that validates
        # the response, so a schema the validator cannot read is a silent hole.
        for spec in routing.PIPELINES:
            for name, schema in spec.arguments.items():
                schema_with_required = {"type": "object", "properties": {name: schema},
                                        "required": [], "additionalProperties": False}
                sample = {"string": "value", "number": 1.0, "boolean": True}[schema["type"]]
                if schema.get("enum"):
                    sample = schema["enum"][0]
                if schema.get("pattern"):
                    sample = "abc"
                tool_runtime.validate_arguments({name: sample}, schema_with_required)

    def test_tool_catalog_matches_a_real_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = tool_runtime.WorkspaceSandbox(directory, allow_exec=False)
            registry = tool_runtime.ToolRegistry(sandbox)
            self.assertEqual(registry.prompt_catalog(), tool_runtime.default_tool_catalog(allow_exec=False))
            self.assertEqual(registry.catalog_json(), json.dumps(
                tool_runtime.default_tool_catalog(allow_exec=False),
                ensure_ascii=False, separators=(",", ":"))[:6000])

    def test_run_command_is_absent_unless_execution_is_enabled(self):
        names = [entry["name"] for entry in json.loads(routing.tool_catalog())]
        self.assertIn("write_file", names)
        self.assertNotIn("run_command", names)


class DeterministicRoutingTest(unittest.TestCase):
    """The no-model path must not change behaviour, only move it."""

    def route(self, goal, cfg=NO_MODEL):
        return routing.route_task(goal, cfg)

    def test_product_request_keeps_its_pipeline(self):
        route = self.route("Build a digital product prototype for textile invoice reconciliation")
        self.assertEqual(route.pipelines, ["product_prototype"])
        self.assertEqual(route.mode, "heuristic")

    def test_web_request_keeps_its_pipeline(self):
        for goal in ("Build a small web app for matching textile invoices.",
                     "Build a portfolio site for a photographer",
                     "Create a landing page for a bakery"):
            with self.subTest(goal=goal):
                self.assertEqual(self.route(goal).pipelines, ["web_build"])

    def test_automation_studio_is_not_a_video(self):
        # The regression that started the old special case: the word "YouTube"
        # must not turn a software request into a render.
        route = self.route("Build my YouTube automation agent studio with specialist roles")
        self.assertEqual(route.pipelines, [])

    def test_video_request_carries_topic_format_and_render_intent(self):
        route = self.route("Create and render a full YouTube video about AI agents to MP4")
        self.assertEqual(route.pipelines, ["video_production"])
        args = route.requests[0].args
        self.assertTrue(args["render"])
        self.assertEqual(args["format"], "long")
        self.assertIn("AI agents", args["topic"])

    def test_shorts_and_language_override_are_carried_as_arguments(self):
        route = self.route("Create a short-form video about invoice matching, "
                           "narration language: English")
        args = route.requests[0].args
        self.assertEqual(args["format"], "shorts")
        self.assertEqual(args["language"], "en")
        self.assertFalse(args["render"])

    def test_document_and_cli_requests_reach_the_tool_loop(self):
        self.assertEqual(self.route("Write a changelog for the v2 release").pipelines,
                         ["document_deliverable"])
        self.assertEqual(self.route("Draft release notes for version 2.0").pipelines,
                         ["document_deliverable"])
        self.assertEqual(self.route("Build a CLI that dedupes photo records").pipelines,
                         ["cli_tool"])
        self.assertEqual(self.route("Make me a command-line tool that reconciles two CSV files").pipelines,
                         ["cli_tool"])

    def test_named_cli_argument_is_extracted(self):
        route = self.route("Build a CLI called photo-dedupe that removes duplicate records")
        self.assertEqual(route.requests[0].args.get("name"), "photo-dedupe")

    def test_a_concrete_artifact_suppresses_the_product_fallback(self):
        for goal in ("Build a website for a bakery",
                     "Write a report about bakery sales",
                     "Build a CLI that lists bakery orders"):
            with self.subTest(goal=goal):
                self.assertNotIn("product_prototype", self.route(goal).pipelines)

    def test_questions_and_plans_route_to_nothing(self):
        for goal in ("What is a knowledge graph?",
                     "Explain how to build a website",
                     "Summarise this CSV into a report",
                     "Review my landing page",
                     "How do I structure a changelog?"):
            with self.subTest(goal=goal):
                self.assertEqual(self.route(goal).pipelines, [])

    def test_a_first_person_request_inside_an_explanation_still_routes(self):
        route = self.route("Explain the trade-offs, then write me a changelog for v2")
        self.assertEqual(route.pipelines, ["document_deliverable"])

    def test_intake_wrapper_does_not_change_routing(self):
        wrapped = ("TASK TYPE: draft\nTASK TITLE: Invoice matcher\nUSER REQUEST:\n"
                   "Build a small web app for matching textile invoices."
                   "\n\nREQUIRED OUTCOME: produce the requested usable deliverable, not just advice.")
        route = self.route(wrapped)
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertEqual(routing.extract_intent(wrapped), "Build a small web app for matching textile invoices.")

    def test_routing_only_decides(self):
        # No sandbox, no file, no subprocess: the router returns a decision and
        # the caller executes it.
        before = set(ROOT.joinpath("workspace").glob("projects/*")) if (
            ROOT / "workspace" / "projects").is_dir() else set()
        route = self.route("Build a website for a bakery")
        after = set(ROOT.joinpath("workspace").glob("projects/*")) if (
            ROOT / "workspace" / "projects").is_dir() else set()
        self.assertEqual(before, after)
        self.assertTrue(all(isinstance(request.args, dict) for request in route.requests))


class VideoInstructionTest(unittest.TestCase):
    """Instructions are read from the request, not left to the chooser."""

    def test_instructions_are_parsed_from_the_request(self):
        parsed = routing.video_instructions(
            "Create and render a short-form video with voice about invoice matching "
            "in Urdu narration, target minutes: 3")
        self.assertTrue(parsed["render"])
        self.assertTrue(parsed["with_voice"])
        self.assertEqual(parsed["format"], "shorts")
        self.assertEqual(parsed["language"], "ur-en")
        self.assertEqual(parsed["target_minutes"], 3.0)

    def test_a_package_request_asks_for_no_render(self):
        parsed = routing.video_instructions("Create a YouTube video about AI agents")
        self.assertFalse(parsed["render"])
        self.assertFalse(parsed["with_voice"])
        self.assertEqual(parsed["format"], "long")

    def test_an_impossible_length_is_ignored_rather_than_clamped(self):
        self.assertNotIn("target_minutes", routing.video_instructions("video, target minutes: 900"))
        self.assertNotIn("target_minutes", routing.video_instructions("video, target minutes: 0.1"))

    def test_heuristic_route_uses_the_same_instructions(self):
        route = routing.route_task("Create a short-form video about X with voice", NO_MODEL)
        args = route.requests[0].args
        self.assertEqual(args["format"], "shorts")
        self.assertFalse(args["render"])


class AdvisoryPolicyTest(unittest.TestCase):
    def test_model_cannot_claim_an_advisory_request(self):
        route = routing.route_task(
            "Explain how to structure a changelog", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "document_deliverable", "args": {}}]}))
        self.assertEqual(route.pipelines, [])
        self.assertTrue(route.advisory)
        self.assertTrue(any("analysis or advice" in veto for veto in route.vetoed))

    def test_a_request_with_no_build_verb_is_vetoed(self):
        route = routing.route_task(
            "The quarterly numbers for the board", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "document_deliverable"}]}))
        self.assertEqual(route.pipelines, [])
        self.assertTrue(any("no build verb" in veto for veto in route.vetoed))


class ModelRoutingTest(unittest.TestCase):
    def test_model_choice_is_accepted_with_validated_arguments(self):
        route = routing.route_task(
            "Make me a data report for the Q3 operations review", WITH_MODEL,
            model_call=fake_model({"pipelines": [
                {"id": "document_deliverable", "args": {"title": "Q3 operations review"},
                 "why": "a written report was requested"}], "notes": "clear"}))
        self.assertEqual(route.mode, "model")
        self.assertEqual(route.pipelines, ["document_deliverable"])
        self.assertEqual(route.requests[0].args["title"], "Q3 operations review")
        self.assertEqual(route.notes, "clear")
        self.assertEqual(route.agreement, "model_only")

    def test_model_reaches_a_pipeline_the_patterns_do_not(self):
        route = routing.route_task(
            "Make me a data report", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "document_deliverable"}]}))
        self.assertEqual(route.pipelines, ["document_deliverable"])
        self.assertEqual(route.heuristic, [])

    def test_unknown_pipeline_is_rejected_not_executed(self):
        route = routing.route_task(
            "Build a website for a bakery", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "shell_exec", "args": {"cmd": "ls"}}]}))
        self.assertEqual(route.pipelines, [])
        self.assertTrue(any("unknown pipeline" in item for item in route.rejected))

    def test_unknown_argument_is_dropped_but_the_pipeline_survives(self):
        route = routing.route_task(
            "Build a website for a bakery", WITH_MODEL,
            model_call=fake_model({"pipelines": [
                {"id": "web_build", "args": {"title": "Bakery", "shell": "rm -rf /"}}]}))
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertEqual(route.requests[0].args, {"title": "Bakery"})
        self.assertTrue(any("unknown argument 'shell'" in item for item in route.rejected))

    def test_argument_types_and_bounds_are_enforced(self):
        route = routing.route_task(
            "Build a CLI called photo-dedupe", WITH_MODEL,
            model_call=fake_model({"pipelines": [
                {"id": "cli_tool", "args": {"name": "Photo Dedupe!"}}]}))
        self.assertEqual(route.pipelines, ["cli_tool"])
        self.assertEqual(route.requests[0].args, {})
        self.assertTrue(any("invalid format" in item for item in route.rejected))

    def test_prefix_argument_is_rejected_rather_than_truncated(self):
        route = routing.route_task(
            "Build a website for a bakery", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "web_build", "args": {"title": "x" * 400}}]}))
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertTrue(any("at most 100 characters" in item for item in route.rejected))

    def test_duplicate_and_extra_tool_loop_pipelines_are_dropped(self):
        route = routing.route_task(
            "Build a website and a CLI for a bakery", WITH_MODEL,
            model_call=fake_model({"pipelines": [
                {"id": "web_build"}, {"id": "cli_tool"}, {"id": "web_build"}]}))
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertTrue(any("tool-loop pipeline is already selected" in item for item in route.rejected))
        self.assertTrue(any("duplicate pipeline" in item for item in route.rejected))

    def test_empty_choice_is_a_decision_not_a_failure(self):
        route = routing.route_task("Build a website for a bakery", WITH_MODEL,
                                   model_call=fake_model({"pipelines": []}))
        self.assertEqual(route.mode, "model")
        self.assertEqual(route.pipelines, [])
        self.assertEqual(route.agreement, "model_chose_nothing")

    def test_unparseable_answer_falls_back_to_the_deterministic_route(self):
        route = routing.route_task("Build a website for a bakery", WITH_MODEL,
                                   model_call=fake_model("I would build a website."))
        self.assertEqual(route.mode, "heuristic_after_rejected_plan")
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertTrue(route.rejected)

    def test_model_failure_falls_back_to_the_deterministic_route(self):
        def broken(prompt, max_tokens):
            raise TimeoutError("local model timed out")

        route = routing.route_task("Build a website for a bakery", WITH_MODEL, model_call=broken)
        self.assertEqual(route.mode, "heuristic_after_model_error")
        self.assertEqual(route.pipelines, ["web_build"])

    def test_agreement_is_recorded_for_every_model_decision(self):
        cases = {
            "Build a website for a bakery": "match",
            "Write a changelog for v2": "differs",
        }
        for goal, expected in cases.items():
            with self.subTest(goal=goal):
                route = routing.route_task(
                    goal, WITH_MODEL,
                    model_call=fake_model({"pipelines": [{"id": "web_build"}]}))
                self.assertEqual(route.agreement, expected)

    def test_disagreement_is_visible_rather_than_silent(self):
        # The deterministic patterns miss "build me a landing page"; the model
        # catches it. The record keeps both so the gap can be closed later.
        route = routing.route_task(
            "Explain the trade-offs, then build me a landing page", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "web_build"}]}))
        self.assertEqual(route.pipelines, ["web_build"])
        self.assertEqual(route.heuristic, [])
        self.assertEqual(route.agreement, "model_only")


class VetoTest(unittest.TestCase):
    def test_model_cannot_route_an_automation_studio_to_the_video_builder(self):
        route = routing.route_task(
            "Build my YouTube automation agent studio with specialist roles", WITH_MODEL,
            model_call=fake_model({"pipelines": [
                {"id": "video_production", "args": {"topic": "automation"}}]}))
        self.assertEqual(route.pipelines, [])
        self.assertTrue(any("automation studio" in veto for veto in route.vetoed))

    def test_video_veto_does_not_block_a_real_video_request(self):
        route = routing.route_task(
            "Create a YouTube video about automation", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "video_production",
                                                  "args": {"topic": "automation"}}]}))
        self.assertEqual(route.pipelines, ["video_production"])
        self.assertEqual(route.vetoed, [])

    def test_every_pipeline_declares_a_policy_string(self):
        for spec in routing.PIPELINES:
            self.assertTrue(spec.policy, spec.id)


class PromptTest(unittest.TestCase):
    def test_prompt_names_the_catalog_tools_and_task(self):
        prompt = routing.build_route_prompt("Write a changelog for v2")
        self.assertIn("PIPELINE CATALOG", prompt)
        self.assertIn("TOOLS THE TOOL-LOOP", prompt)
        for spec in routing.PIPELINES:
            self.assertIn(spec.id, prompt)
        self.assertIn("Write a changelog for v2", prompt)
        self.assertLessEqual(len(prompt), routing.MAX_PROMPT_CHARS)

    def test_prompt_contains_no_operator_state(self):
        prompt = routing.build_route_prompt("Write a changelog for v2")
        lowered = prompt.lower()
        for secret in ("api_key", "token", "password", "workspace/"):
            self.assertNotIn(secret, lowered)


class RouteRecordTest(unittest.TestCase):
    def test_record_is_json_safe_and_explains_itself(self):
        route = routing.route_task(
            "Build a website for a bakery", WITH_MODEL,
            model_call=fake_model({"pipelines": [{"id": "web_build"},
                                                 {"id": "nope"}]}))
        record = json.loads(json.dumps(route.as_dict()))
        for key in ("mode", "pipelines", "requests", "heuristic_pipelines", "agreement",
                    "advisory", "vetoed", "rejected", "notes"):
            self.assertIn(key, record)
        self.assertEqual(record["pipelines"], ["web_build"])
        self.assertEqual(record["heuristic_pipelines"], ["web_build"])
        self.assertTrue(record["rejected"])


class LanguageTest(unittest.TestCase):
    def test_explicit_narration_language_wins_and_topic_mentions_do_not(self):
        self.assertEqual(routing.requested_narration_language("Narration language: English."), "en")
        self.assertEqual(routing.requested_narration_language("Use Urdu narration for this explainer."), "ur-en")
        self.assertIsNone(routing.requested_narration_language("Create a video about Urdu literature."))


if __name__ == "__main__":
    unittest.main()
