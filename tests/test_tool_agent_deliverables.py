"""The tool loop must be able to build something other than a web page.

Phase 2 extends the plan → act → verify → repair loop beyond web builds. A new
deliverable kind is only worth having if it is held to the same standard as the
web one: a fixed artifact contract, generated acceptance checks, an independent
post-build verification, and an honest label saying what was and was not written.

The two new kinds are deliberately modest. A document scaffold carries structure
and acceptance criteria, not research. A CLI scaffold carries working plumbing
and a self-test, not the task's actual algorithm. Both say so in the artifact
itself, because a labelled skeleton is useful and an unlabelled one is a lie.
"""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tool_agent  # noqa: E402


class ContractTest(unittest.TestCase):
    def test_every_kind_declares_a_contract_the_scaffold_meets(self):
        with tempfile.TemporaryDirectory():
            for kind in tool_agent.DELIVERABLES:
                with self.subTest(kind=kind):
                    plan = tool_agent.deterministic_plan("Write a changelog for v2",
                                                         deliverable=kind)
                    self.assertEqual(plan.deliverable, kind)
                    written = {step.args["path"]: step.args["content"] for step in plan.steps
                               if step.tool == "write_file"}
                    for name, needle in tool_agent.DELIVERABLE_CONTRACT[kind]:
                        self.assertIn(name, written)
                        self.assertIn(needle, written[name])
                    self.assertTrue(plan.verify)

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            tool_agent.normalise_deliverable("spreadsheet")
        with self.assertRaises(ValueError):
            tool_agent.deterministic_plan("Do work", deliverable="spreadsheet")

    def test_prompt_states_the_kind_and_its_primary_file(self):
        for kind in tool_agent.DELIVERABLES:
            with self.subTest(kind=kind):
                prompt = tool_agent.build_plan_prompt("Do the work", "[]", allow_exec=False,
                                                      deliverable=kind)
                self.assertIn("DELIVERABLE KIND: " + kind, prompt)
                primary = tool_agent.DELIVERABLE_CONTRACT[kind][0][0]
                self.assertIn(primary, prompt)

    def test_prompt_keeps_the_no_network_and_honesty_rules_for_documents(self):
        prompt = tool_agent.build_plan_prompt("Write a report", "[]", allow_exec=False,
                                              deliverable="document")
        self.assertIn("Write no fact you cannot support from the goal", prompt)
        self.assertIn("never placeholders", prompt)


class DocumentScaffoldTest(unittest.TestCase):
    def files(self):
        return tool_agent.deterministic_document_files(
            "Write a one-page project brief for the invoice tool")

    def test_markdown_is_structured_and_labelled(self):
        text = self.files()["deliverable.md"]
        self.assertTrue(text.startswith("# "))
        self.assertIn("## Acceptance criteria", text)
        self.assertIn("Deterministic scaffold", text)
        # The label has to be unambiguous about what was not done.
        self.assertIn("No language model wrote it", text)
        self.assertIn("no", text.lower())
        for section in tool_agent.DOCUMENT_SECTIONS:
            self.assertIn("## " + section, text)

    def test_metadata_is_machine_readable_and_honest(self):
        metadata = json.loads(self.files()["deliverable.json"])
        self.assertEqual(metadata["schema"], 1)
        self.assertEqual(metadata["deliverable"], "document")
        self.assertIs(metadata["ai_generated"], False)
        self.assertIs(metadata["research_performed"], False)
        self.assertIs(metadata["human_review_required"], True)
        self.assertEqual(metadata["sections"], list(tool_agent.DOCUMENT_SECTIONS))
        self.assertGreaterEqual(len(metadata["acceptance_criteria"]), 3)

    def test_heading_is_not_the_imperative_that_asked_for_it(self):
        for goal, expected in (
            ("Write a changelog for the v2 release", "# Changelog"),
            ("Draft release notes for version 2.0", "# Release notes"),
        ):
            with self.subTest(goal=goal):
                first = tool_agent.deterministic_document_files(goal)["deliverable.md"].splitlines()[0]
                self.assertEqual(first, expected)

    def test_goal_text_is_carried_and_bounded(self):
        metadata = json.loads(tool_agent.deterministic_document_files("x" * 5000)["deliverable.json"])
        self.assertLessEqual(len(metadata["goal"]), 300)

    def test_empty_goal_still_produces_a_document(self):
        text = tool_agent.deterministic_document_files("   ")["deliverable.md"]
        self.assertTrue(text.startswith("# "))


class CliScaffoldTest(unittest.TestCase):
    def test_generated_python_parses(self):
        source = tool_agent.deterministic_cli_files("Build a CLI that dedupes photos")["tool.py"]
        ast.parse(source)

    def test_self_test_actually_runs_and_passes(self):
        source = tool_agent.deterministic_cli_files("Build a CLI that dedupes photos")["tool.py"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tool.py"
            path.write_text(source, encoding="utf-8")
            completed = subprocess.run([sys.executable, str(path), "--self-test"],
                                       capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("self-test: ok", completed.stdout)

    def test_self_test_fails_loudly_when_the_rule_is_broken(self):
        source = tool_agent.deterministic_cli_files("Build a CLI")["tool.py"]
        broken = source.replace('assert dedupe(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]',
                                'assert dedupe(["a"]) == ["b"]')
        self.assertNotEqual(broken, source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tool.py"
            path.write_text(broken, encoding="utf-8")
            completed = subprocess.run([sys.executable, str(path), "--self-test"],
                                       capture_output=True, text=True, timeout=60)
        self.assertNotEqual(completed.returncode, 0)

    def test_it_processes_records_end_to_end(self):
        source = tool_agent.deterministic_cli_files("Build a CLI")["tool.py"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tool.py"
            records = Path(directory) / "records.txt"
            path.write_text(source, encoding="utf-8")
            records.write_text("  a  \nb\na\n\n", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(path), str(records), "--unique"],
                                       capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.split(), ["a", "b"])

    def test_name_is_taken_from_the_goal_when_not_supplied(self):
        files = tool_agent.deterministic_cli_files("Build a CLI called photo-dedupe that removes duplicates")
        self.assertIn("photo-dedupe", files["tool.py"])

    def test_explicit_name_wins_over_the_goal(self):
        files = tool_agent.deterministic_cli_files("Build a CLI called photo-dedupe", name="ledger")
        self.assertIn("ledger", files["tool.py"])
        self.assertNotIn("photo-dedupe —", files["tool.py"])

    def test_names_are_sanitised(self):
        files = tool_agent.deterministic_cli_files("Build a CLI", name="Photo Dedupe!!")
        self.assertIn("photo-dedupe", files["tool.py"])
        fallback = tool_agent.deterministic_cli_files("Build a CLI", name="!!")
        self.assertIn("records-tool", fallback["tool.py"])

    def test_readme_does_not_overclaim(self):
        readme = tool_agent.deterministic_cli_files("Build a CLI that dedupes photos")["README.md"]
        self.assertIn("--self-test", readme)
        self.assertIn("it does not do the job the goal describes", readme)


class RunTest(unittest.TestCase):
    def run_kind(self, kind, goal):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        result = tool_agent.run_tool_agent(goal, directory.name, "T-" + kind, deliverable=kind)
        return result, Path(directory.name) / "projects" / ("t-" + kind)

    def test_document_run_is_verified_and_labelled(self):
        result, root = self.run_kind("document", "Write a changelog for the v2 release")
        self.assertEqual(result["deliverable"], "document")
        # A deterministic scaffold is verified but is not model-authored work.
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["mode"], "deterministic")
        self.assertTrue(all(check["status"] == "passed" for check in result["verification"]))
        self.assertTrue((root / "deliverable.md").is_file())
        summary = json.loads((root / "tool-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["deliverable"], "document")
        self.assertIs(summary["human_review_required"], True)

    def test_cli_run_is_verified_and_records_the_kind(self):
        result, root = self.run_kind("cli", "Build a CLI that dedupes photo records")
        self.assertEqual(result["deliverable"], "cli")
        self.assertEqual(result["status"], "partial")
        self.assertTrue((root / "tool.py").is_file())
        self.assertTrue((root / "README.md").is_file())
        ast.parse((root / "tool.py").read_text(encoding="utf-8"))
        plan = json.loads((root / "tool-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["deliverable"], "cli")

    def test_web_default_is_unchanged(self):
        result, root = self.run_kind("web", "Build a portfolio site for a photographer")
        self.assertEqual(result["deliverable"], "web")
        self.assertTrue((root / "index.html").is_file())
        self.assertTrue((root / "app.js").is_file())

    def test_unknown_kind_is_refused_before_the_sandbox_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                tool_agent.run_tool_agent("Do work", directory, "T", deliverable="spreadsheet")
            self.assertFalse((Path(directory) / "projects").exists())

    def test_exec_enabled_cli_plan_runs_its_own_self_test(self):
        plan = tool_agent.deterministic_plan("Build a CLI", allow_exec=True, deliverable="cli")
        commands = [step for step in plan.steps if step.tool == "run_command"]
        for step in commands:
            self.assertEqual(step.args["args"], ["tool.py", "--self-test"])


if __name__ == "__main__":
    unittest.main()
