"""Tests for the one pipeline that edits code the user already has.

The properties asserted here are the ones that make a "fixed" claim meaningful:
the suite must go green afterwards, the edit must be reverted when it does not,
test files must never be touched, and nothing may be reported as repaired when
no run happened at all.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))
import orchestrate  # noqa: E402
import test_fix  # noqa: E402

BROKEN_SOURCE = "def average(values):\n    return sum(values) / (len(values) - 1)\n"
FIXED_SOURCE = "def average(values):\n    return sum(values) / len(values)\n"
TEST_FILE = """import unittest
from calc import average


class AverageTests(unittest.TestCase):
    def test_average_of_three(self):
        self.assertEqual(average([2, 4, 6]), 4)
"""

FAIL_OUTPUT = """test_average_of_three (tests.test_calc.AverageTests.test_average_of_three) ... FAIL

======================================================================
FAIL: test_average_of_three (tests.test_calc.AverageTests.test_average_of_three)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/app/tests/test_calc.py", line 7, in test_average_of_three
    self.assertEqual(average([2, 4, 6]), 4)
AssertionError: 6.0 != 4

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)
"""

PASS_OUTPUT = """test_average_of_three (tests.test_calc.AverageTests.test_average_of_three) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.001s

OK
"""


def make_project(directory, *, source=BROKEN_SOURCE, test=TEST_FILE, tests_dir="tests"):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    (root / "calc.py").write_text(source, encoding="utf-8")
    target = root / tests_dir
    target.mkdir(parents=True, exist_ok=True)
    (target / "test_calc.py").write_text(test, encoding="utf-8")
    return root


class ParsingTest(unittest.TestCase):
    def test_reads_the_failing_test_its_location_and_message(self):
        parsed = test_fix.parse_failures(FAIL_OUTPUT)
        self.assertEqual(parsed["tests_ran"], 1)
        self.assertEqual(parsed["summary"], "FAILED (failures=1)")
        failure = parsed["failures"][0]
        self.assertEqual(failure["test"], "tests.test_calc.AverageTests.test_average_of_three")
        self.assertEqual(failure["message"], "AssertionError: 6.0 != 4")
        self.assertEqual(failure["frames"][-1]["line"], 7)
        self.assertEqual(failure["frames"][-1]["file"], "/tmp/app/tests/test_calc.py")

    def test_a_passing_run_reports_no_failures(self):
        parsed = test_fix.parse_failures(PASS_OUTPUT)
        self.assertEqual(parsed["tests_ran"], 1)
        self.assertEqual(parsed["failures"], [])
        self.assertEqual(parsed["summary"], "OK")

    def test_unrecognised_output_is_not_mistaken_for_a_pass(self):
        parsed = test_fix.parse_failures("something entirely unexpected")
        self.assertEqual(parsed["tests_ran"], 0)
        self.assertEqual(parsed["failures"], [])

    def test_error_blocks_are_distinguished_from_failures(self):
        text = ("======================================================================\n"
                "ERROR: test_one (tests.test_a.TestA.test_one)\n"
                "----------------------------------------------------------------------\n"
                "Traceback (most recent call last):\n"
                '  File "/tmp/a/src.py", line 3, in f\n'
                "    raise ValueError('no')\n"
                "ValueError: no\n\n"
                "----------------------------------------------------------------------\n"
                "Ran 1 test in 0.001s\n\nFAILED (errors=1)\n")
        failure = test_fix.parse_failures(text)["failures"][0]
        self.assertEqual(failure["kind"], "error")
        self.assertEqual(failure["message"], "ValueError: no")


class CommandDetectionTest(unittest.TestCase):
    def test_a_tests_directory_gets_a_discovery_command(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(directory)
            argv, framework, reason = test_fix.detect_command(project)
            self.assertEqual(framework, "unittest")
            self.assertEqual(reason, "")
            self.assertIn("unittest", argv)
            self.assertIn("tests", argv)

    def test_a_node_project_is_diagnosed_rather_than_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"scripts": {"test": "node test.js"}}')
            argv, framework, reason = test_fix.detect_command(root)
            self.assertEqual(argv, [])
            self.assertEqual(framework, "node")
            self.assertIn("allowlist", reason)

    def test_a_directory_without_tests_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            argv, _, reason = test_fix.detect_command(Path(directory))
            self.assertEqual(argv, [])
            self.assertIn("no Python test files", reason)


class RepairLoopTest(unittest.TestCase):
    """The loop is driven with injected runs and proposals: no subprocess, no model."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = make_project(self.directory.name)

    def fake_runs(self, project, passes_after):
        """A run function that fails until the project content changes."""
        def run(_root, argv, _timeout):
            content = (self.project / "calc.py").read_text()
            green = content == FIXED_SOURCE if passes_after else False
            output = PASS_OUTPUT if green else FAIL_OUTPUT
            return {
                "command": list(argv), "exit_code": 0 if green else 1, "output": output,
                "green": green, "timed_out": False, "error": "", "duration_seconds": 0.01,
                **test_fix.parse_failures(output),
            }
        return run

    def test_a_repair_that_turns_the_suite_green_is_kept_and_marked_verified(self):
        propose = lambda run: {"path": "calc.py", "content": FIXED_SOURCE, "why": "off by one"}
        report = test_fix.diagnose(self.project, run=self.fake_runs(self.project, True), propose=propose)
        self.assertTrue(report["verified_fix"])
        self.assertTrue(report["green"])
        self.assertEqual(report["repairs"][0]["kind"], "model_patch")
        self.assertTrue(report["repairs"][0]["verified"])
        self.assertEqual((self.project / "calc.py").read_text(), FIXED_SOURCE)
        self.assertFalse(report["test_files_modified"])

    def test_a_repair_that_does_not_work_is_reverted(self):
        broken = "def average(values):\n    return 0\n"
        propose = lambda run: {"path": "calc.py", "content": broken, "why": "guess"}
        report = test_fix.diagnose(self.project, run=self.fake_runs(self.project, False), propose=propose)
        self.assertFalse(report["verified_fix"])
        self.assertTrue(report["repairs"][0]["reverted"])
        # The tree is exactly as it was found.
        self.assertEqual((self.project / "calc.py").read_text(), BROKEN_SOURCE)

    def test_no_proposal_means_a_diagnosis_not_an_edit(self):
        report = test_fix.diagnose(self.project, run=self.fake_runs(self.project, True))
        self.assertEqual(report["repairs"], [])
        self.assertFalse(report["verified_fix"])
        self.assertEqual((self.project / "calc.py").read_text(), BROKEN_SOURCE)

    def test_a_proposal_cannot_edit_a_test_file(self):
        propose = lambda run: {"path": "tests/test_calc.py", "content": "import unittest\n"}
        report = test_fix.diagnose(self.project, run=self.fake_runs(self.project, True), propose=propose)
        self.assertFalse(report["verified_fix"])
        record = report["repairs"][0]
        self.assertIn("test file", record["why"])
        self.assertIn("assertEqual", (self.project / "tests" / "test_calc.py").read_text())

    def test_a_proposal_cannot_escape_the_project(self):
        propose = lambda run: {"path": "../outside.py", "content": "x = 1\n"}
        report = test_fix.diagnose(self.project, run=self.fake_runs(self.project, True), propose=propose)
        self.assertFalse(report["verified_fix"])
        self.assertFalse((Path(self.directory.name).parent / "outside.py").exists())

    def test_attempts_are_bounded(self):
        calls = []

        def run(_root, argv, _timeout):
            calls.append(1)
            return {
                "command": list(argv), "exit_code": 1, "output": FAIL_OUTPUT,
                "green": False, "timed_out": False, "error": "", "duration_seconds": 0.01,
                **test_fix.parse_failures(FAIL_OUTPUT),
            }

        propose = lambda run: {"path": "calc.py", "content": BROKEN_SOURCE + "# nope\n"}
        report = test_fix.diagnose(self.project, run=run, propose=propose, max_attempts=2)
        self.assertEqual(len(calls), 3)          # first run plus two attempts
        self.assertEqual(len(report["repairs"]), 2)
        self.assertEqual((self.project / "calc.py").read_text(), BROKEN_SOURCE)

    def test_an_edit_to_a_test_file_is_reported_as_tampering(self):
        def run(_root, argv, _timeout):
            # Something outside the loop edited the test while it ran.
            (self.project / "tests" / "test_calc.py").write_text("import unittest\n")
            return {
                "command": list(argv), "exit_code": 0, "output": PASS_OUTPUT,
                "green": True, "timed_out": False, "error": "", "duration_seconds": 0.01,
                **test_fix.parse_failures(PASS_OUTPUT),
            }

        report = test_fix.diagnose(self.project, run=run)
        self.assertTrue(report["test_files_modified"])
        self.assertFalse(report["verified_fix"])
        self.assertIn("tests/test_calc.py", report["changed_test_files"])


class StructuralRepairTest(unittest.TestCase):
    def test_a_missed_discovery_pattern_is_corrected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "math_test.py").write_text(TEST_FILE.replace("test_calc", "math_test"), encoding="utf-8")
            (root / "calc.py").write_text(FIXED_SOURCE, encoding="utf-8")
            calls = []

            def run(_root, argv, _timeout):
                calls.append(list(argv))
                collected = "-p" in argv
                output = PASS_OUTPUT if collected else "----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n"
                parsed = test_fix.parse_failures(output)
                return {
                    "command": list(argv), "exit_code": 0, "output": output,
                    "green": bool(parsed["tests_ran"]) and collected, "timed_out": False,
                    "error": "", "duration_seconds": 0.01, **parsed,
                }

            report = test_fix.diagnose(root, run=run)
            self.assertEqual(report["repairs"][0]["kind"], "discovery_pattern")
            self.assertTrue(report["repairs"][0]["verified"])
            self.assertEqual(calls[1][-2:], ["-p", "*_test.py"])

    def test_an_unimportable_tests_package_gets_a_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_project(directory)
            (root / "tests" / "__init__.py").unlink(missing_ok=True)
            error_output = ('ERROR: tests (unittest.loader._FailedTest)\n'
                            "ImportError: Failed to import test module: tests\n"
                            "ModuleNotFoundError: No module named 'tests'\n")
            state = {"marked": False}

            def run(_root, argv, _timeout):
                marked = (root / "tests" / "__init__.py").is_file()
                state["marked"] = state["marked"] or marked
                output = PASS_OUTPUT if marked else error_output
                parsed = test_fix.parse_failures(output)
                parsed["tests_ran"] = parsed["tests_ran"] or (1 if marked else 0)
                return {
                    "command": list(argv), "exit_code": 0 if marked else 1, "output": output,
                    "green": marked, "timed_out": False, "error": "", "duration_seconds": 0.01,
                    **parsed,
                }

            report = test_fix.diagnose(root, run=run)
            self.assertEqual(report["repairs"][0]["kind"], "package_marker")
            self.assertTrue((root / "tests" / "__init__.py").is_file())
            self.assertTrue(report["verified_fix"])


class DiagnosisWithoutRunningTest(unittest.TestCase):
    def test_execution_disabled_still_produces_an_honest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(directory)
            report = test_fix.diagnose(project, allow_exec=False)
            self.assertEqual(report["runs"], [])
            self.assertIn("execution is disabled", report["no_run_reason"])
            self.assertFalse(report["verified_fix"])
            self.assertIn("No repair was attempted", test_fix.render_markdown(report))

    def test_a_missing_project_is_reported_not_invented(self):
        report = test_fix.diagnose(Path(tempfile.gettempdir()) / "definitely-not-here-12345")
        self.assertEqual(report["runs"], [])
        self.assertIn("does not exist", report["no_run_reason"])


class ProposalValidationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = make_project(self.directory.name)
        self.allowed = {"calc.py"}

    def validate(self, proposal):
        return test_fix.validate_proposal(self.project, proposal, set(self.allowed))

    def test_a_complete_valid_file_is_accepted(self):
        proposal, problem = self.validate({"path": "calc.py", "content": FIXED_SOURCE, "why": "fix"})
        self.assertEqual(problem, "")
        self.assertEqual(proposal["path"], "calc.py")

    def test_files_the_failure_did_not_name_are_refused(self):
        _, problem = self.validate({"path": "other.py", "content": "x = 1\n"})
        self.assertIn("did not name", problem)

    def test_test_files_are_refused_even_when_listed(self):
        self.allowed = {"tests/test_calc.py"}
        _, problem = self.validate({"path": "tests/test_calc.py", "content": "x = 1\n"})
        self.assertIn("test file", problem)

    def test_invalid_python_is_refused(self):
        _, problem = self.validate({"path": "calc.py", "content": "def average(:\n"})
        self.assertIn("valid Python", problem)

    def test_an_edit_outside_the_project_is_refused(self):
        _, problem = self.validate({"path": "../evil.py", "content": "x = 1\n"})
        self.assertNotEqual(problem, "")

    def test_a_give_up_reply_is_not_a_repair(self):
        _, problem = self.validate({"give_up": True})
        self.assertIn("declined", problem)

    def test_non_python_files_are_refused(self):
        self.allowed = {"notes.md"}
        _, problem = self.validate({"path": "notes.md", "content": "x"})
        self.assertIn("non-Python", problem)


class ModelProposerTest(unittest.TestCase):
    def test_a_broken_model_reply_degrades_to_no_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(directory)
            proposer = test_fix.model_proposer(lambda prompt, tokens: "not json", project)
            self.assertIsNone(proposer({"output": FAIL_OUTPUT, "failures": test_fix.parse_failures(FAIL_OUTPUT)["failures"]}))

    def test_a_raising_model_degrades_to_no_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            project = make_project(directory)

            def call(prompt, tokens):
                raise OSError("model unreachable")

            proposer = test_fix.model_proposer(call, project)
            self.assertIsNone(proposer({"output": FAIL_OUTPUT,
                                        "failures": test_fix.parse_failures(FAIL_OUTPUT)["failures"]}))

    def test_a_repair_prompt_names_the_rule_and_the_file(self):
        prompt = test_fix.build_repair_prompt("AssertionError: 6.0 != 4", {"calc.py": BROKEN_SOURCE})
        self.assertIn("JSON only", prompt)
        self.assertIn("never edit a test file", prompt)
        self.assertIn("FILE calc.py", prompt)


class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "orchestration" / "run").mkdir(parents=True)
        self.destination = self.workspace / "orchestration" / "run"
        self.project = make_project(self.workspace / "demo")
        patcher = patch.object(orchestrate, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tools(self, goal, env="1"):
        sink = {}
        with patch.dict("os.environ", {"AGENT_HQ_ALLOW_EXEC": env}):
            runs = orchestrate.run_builtin_tools(goal, self.destination, {"model": {"enabled": False}},
                                                 route_sink=sink)
        return runs, sink["route"]

    def test_the_request_routes_and_verifies(self):
        runs, route = self.run_tools("Fix the failing tests in workspace/demo")
        self.assertEqual(route.pipelines, ["test_fix"])
        self.assertEqual(route.requests[0].args["project"], "workspace/demo")
        self.assertEqual(runs[0]["tool"], "test_fix")
        self.assertEqual(runs[0]["status"], "partial")     # diagnosed, not repaired
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        self.assertIn("test_report_diagnosis_and_verified_repair", checks[0]["checks"])
        report = json.loads((self.destination / "projects" / "run-fix" / "test-report.json").read_text())
        self.assertEqual(report["tests_ran"], 1)
        self.assertEqual(report["failures"][0]["test"],
                         "tests.test_calc.AverageTests.test_average_of_three")

    def test_the_repair_is_kept_when_a_model_proposes_a_working_fix(self):
        def fake_model(prompt, tokens):
            return json.dumps({"path": "calc.py", "content": FIXED_SOURCE, "why": "off-by-one"})

        with patch.object(orchestrate, "tool_model_call", return_value=fake_model):
            runs, _ = self.run_tools("Fix the failing tests in workspace/demo")
        self.assertEqual(runs[0]["status"], "completed")
        self.assertTrue(runs[0]["verified_fix"])
        self.assertEqual((self.project / "calc.py").read_text(), FIXED_SOURCE)
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])

    def test_a_wrong_model_fix_is_reverted_and_the_run_is_not_completed(self):
        def fake_model(prompt, tokens):
            return json.dumps({"path": "calc.py", "content": "def average(values):\n    return 0\n"})

        with patch.object(orchestrate, "tool_model_call", return_value=fake_model):
            runs, _ = self.run_tools("Fix the failing tests in workspace/demo")
        self.assertEqual(runs[0]["status"], "partial")
        self.assertFalse(runs[0]["verified_fix"])
        self.assertEqual((self.project / "calc.py").read_text(), BROKEN_SOURCE)
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])

    def test_execution_disabled_reports_why_nothing_ran(self):
        runs, _ = self.run_tools("Fix the failing tests in workspace/demo", env="")
        self.assertEqual(runs[0]["status"], "partial")
        self.assertIn("execution is disabled", runs[0]["no_run_reason"])
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])

    def test_a_project_outside_the_workspace_is_never_read(self):
        (Path(self.directory.name).parent / "outside-project").mkdir(exist_ok=True)
        runs, route = self.run_tools("Fix the failing tests in ../outside-project")
        self.assertNotIn("project", route.requests[0].args)
        self.assertEqual(runs[0]["status"], "partial")
        self.assertIn("no project directory", runs[0]["no_run_reason"])

    def test_verification_rejects_a_claim_of_a_fix_that_did_not_pass(self):
        runs, _ = self.run_tools("Fix the failing tests in workspace/demo")
        path = self.destination / "projects" / "run-fix" / "test-report.json"
        report = json.loads(path.read_text())
        report["verified_fix"] = True
        report["repairs"] = [{"attempt": 1, "kind": "model_patch", "path": "calc.py",
                              "why": "made up", "verified": True, "reverted": False}]
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("without a passing run" in error for error in checks[0]["errors"]))

    def test_verification_rejects_a_report_with_no_run_and_no_reason(self):
        runs, _ = self.run_tools("Fix the failing tests in workspace/demo")
        path = self.destination / "projects" / "run-fix" / "test-report.json"
        report = json.loads(path.read_text())
        report["runs"] = []
        report["no_run_reason"] = ""
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")

    def test_verification_rejects_an_edited_test_file(self):
        runs, _ = self.run_tools("Fix the failing tests in workspace/demo")
        path = self.destination / "projects" / "run-fix" / "test-report.json"
        report = json.loads(path.read_text())
        report["test_files_modified"] = True
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("test file was modified" in error for error in checks[0]["errors"]))


class RoutingTest(unittest.TestCase):
    def route(self, task):
        from agents import routing
        return routing.route_task(task, {"model": {"enabled": False}})

    def test_a_failing_suite_with_a_repair_verb_routes_to_the_repair_pipeline(self):
        for task in ("Fix the failing tests in workspace/demo",
                     "Make the failing test suite pass in workspace/calculator",
                     "Debug the broken test in workspace/app"):
            with self.subTest(task=task):
                self.assertEqual(self.route(task).pipelines, ["test_fix"])

    def test_the_named_project_is_carried_but_an_escaping_path_is_not(self):
        self.assertEqual(self.route("Fix the failing tests in workspace/demo").requests[0].args["project"],
                         "workspace/demo")
        for task in ("Fix the failing tests in /etc/passwd",
                     "Fix the failing tests in ../../secrets",
                     "Fix the failing tests under C:/Users/me/project"):
            with self.subTest(task=task):
                self.assertNotIn("project", self.route(task).requests[0].args)

    def test_a_question_about_a_failing_test_is_advice(self):
        route = self.route("Explain how to fix a failing test")
        self.assertEqual(route.pipelines, [])
        self.assertTrue(route.advisory)

    def test_writing_new_tests_is_not_a_repair_request(self):
        self.assertNotIn("test_fix", self.route("Write some unit tests for my calculator").pipelines)

    def test_other_builds_still_route(self):
        self.assertEqual(self.route("Write a changelog for v2").pipelines, ["document_deliverable"])
        self.assertEqual(self.route("Build a CLI that dedupes photos").pipelines, ["cli_tool"])


if __name__ == "__main__":
    unittest.main()
