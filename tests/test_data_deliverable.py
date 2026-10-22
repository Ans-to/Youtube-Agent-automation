"""The data pipeline is the first one that reads a file the user named.

That makes it the first place where a task can point at arbitrary disk content, so
the confinement tests matter as much as the statistics ones. Every refusal below
is asserted to leave *no* measured numbers behind: an artifact that half-reads a
forbidden file would be worse than one that declines.
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
import tool_agent  # noqa: E402

NO_MODEL = {"model": {"enabled": False}}
CSV = "region,units,price\nNorth,10,2.5\nSouth,4,\nEast,7,3.25\n"


class DeterministicDataFilesTest(unittest.TestCase):
    def test_measured_numbers_land_in_the_artifacts(self):
        files = tool_agent.deterministic_data_files("Analyse it", data_text=CSV, data_name="sales.csv")
        summary = json.loads(files["summary.json"])
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["source"], "sales.csv")
        self.assertEqual(summary["numeric_columns"], ["units", "price"])
        self.assertIn("8", files["analysis.md"])          # a measured value is reported
        self.assertIn("<svg", files["chart.svg"])
        self.assertIn("def main", files["analyze.py"])
        # The report must say how to reproduce itself, since that is the claim
        # that makes a measured artifact trustworthy.
        self.assertIn("python analyze.py", files["analysis.md"])

    def test_no_dataset_produces_an_explicit_refusal_not_fake_numbers(self):
        files = tool_agent.deterministic_data_files("Analyse a dataset")
        summary = json.loads(files["summary.json"])
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["columns"], [])
        self.assertIn("nothing to measure", summary["no_data_reason"])
        self.assertIn("Nothing was measured", files["analysis.md"])

    def test_unreadable_dataset_is_reported_with_the_reason(self):
        files = tool_agent.deterministic_data_files("Analyse it", data_text="", data_name="",
                                                    reason="dataset file was not found")
        self.assertIn("dataset file was not found", json.loads(files["summary.json"])["no_data_reason"])

    def test_malformed_input_is_explained_not_crashed(self):
        files = tool_agent.deterministic_data_files("Analyse it", data_text="   \n\n",
                                                    data_name="empty.csv")
        summary = json.loads(files["summary.json"])
        self.assertEqual(summary["rows"], 0)
        self.assertIn("could not be read", summary["no_data_reason"])


class DataRunTest(unittest.TestCase):
    def test_run_verifies_all_four_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = tool_agent.run_tool_agent("Analyse sales", directory, "T-data",
                                               deliverable="data", data_text=CSV,
                                               data_name="sales.csv")
            root = Path(directory) / "projects" / "t-data"
            self.assertEqual(result["deliverable"], "data")
            self.assertEqual(result["status"], "partial")   # verified scaffold, not model work
            for name in ("summary.json", "analysis.md", "chart.svg", "analyze.py"):
                self.assertTrue((root / name).is_file(), name)
            self.assertTrue(all(check["status"] == "passed" for check in result["verification"]))

    def test_prompt_states_the_no_interpretation_rule(self):
        prompt = tool_agent.build_plan_prompt("Analyse a dataset", "[]", allow_exec=False,
                                              deliverable="data")
        self.assertIn("DELIVERABLE KIND: data", prompt)
        self.assertIn("Never state a trend, correlation, or causal", prompt)


class DatasetReadConfinementTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "workspace" / "data").mkdir(parents=True)
        (self.root / "workspace" / "data" / "ok.csv").write_text(CSV, encoding="utf-8")
        (self.root / "outside.csv").write_text(CSV, encoding="utf-8")
        (self.root / "workspace" / "data" / "notes.txt").write_text("x", encoding="utf-8")

    def read(self, reference):
        return orchestrate._read_dataset(reference, project_root=self.root)

    def test_a_relative_file_inside_the_project_is_read(self):
        text, name, error = self.read("workspace/data/ok.csv")
        self.assertEqual(error, "")
        self.assertEqual(name, "ok.csv")
        self.assertIn("North", text)

    def test_refuses_paths_that_escape_the_project(self):
        for reference in ("../outside.csv", "../../etc/passwd.csv", "workspace/../../outside.csv"):
            with self.subTest(reference=reference):
                text, _, error = self.read(reference)
                self.assertEqual(text, "")
                self.assertIn("relative path", error)

    def test_refuses_dot_directories_and_dotfiles(self):
        # A named dataset must not become a way to reach .git or a dotfile.
        for reference in (".git/config.csv", ".git/data.csv", "workspace/.hidden.csv"):
            with self.subTest(reference=reference):
                text, _, error = self.read(reference)
                self.assertEqual(text, "")
                self.assertIn("dot-directories", error)

    def test_refuses_absolute_paths_and_drive_letters(self):
        for reference in ("/etc/passwd.csv", "C:/Windows/data.csv", r"C:\data.csv"):
            with self.subTest(reference=reference):
                text, _, error = self.read(reference)
                self.assertEqual(text, "")
                self.assertIn("relative path", error)

    def test_refuses_other_file_types(self):
        text, _, error = self.read("workspace/data/notes.txt")
        self.assertEqual(text, "")
        self.assertIn(".csv", error)

    def test_refuses_a_missing_file(self):
        text, _, error = self.read("workspace/data/nope.csv")
        self.assertEqual(text, "")
        self.assertIn("not found", error)

    def test_refuses_an_oversized_file_before_reading_it(self):
        big = self.root / "workspace" / "data" / "big.csv"
        big.write_text("a\n" + "1\n" * (orchestrate.MAX_DATASET_BYTES // 2 + 10), encoding="utf-8")
        text, _, error = self.read("workspace/data/big.csv")
        self.assertEqual(text, "")
        self.assertIn("limit", error)

    def test_empty_reference_is_explained(self):
        text, _, error = self.read("")
        self.assertEqual(text, "")
        self.assertIn("no dataset file", error)


class OrchestrationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "data").mkdir(parents=True)
        (self.workspace / "data" / "sales.csv").write_text(CSV, encoding="utf-8")
        self.destination = self.workspace / "run-1"
        self.destination.mkdir(parents=True)
        patcher = patch.object(orchestrate, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tools(self, goal):
        sink = {}
        runs = orchestrate.run_builtin_tools(goal, self.destination, NO_MODEL, route_sink=sink)
        return runs, sink["route"]

    def test_csv_request_builds_and_verifies_a_measured_report(self):
        runs, route = self.run_tools("Analyse workspace/data/sales.csv and chart the units column")
        self.assertEqual(route.pipelines, ["data_deliverable"])
        self.assertEqual(runs[0]["deliverable"], "data")
        self.assertEqual(runs[0]["selected_by"], "data_deliverable")
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        self.assertIn("data_summary_report_chart_and_analyzer", checks[0]["checks"])
        summary = json.loads((self.root / runs[0]["artifact_dir"] / "summary.json").read_text())
        self.assertEqual(summary["rows"], 3)

    def test_a_failed_read_still_produces_an_honest_artifact(self):
        runs, _ = self.run_tools("Analyse workspace/data/missing.csv")
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        summary = json.loads((self.root / runs[0]["artifact_dir"] / "summary.json").read_text())
        self.assertEqual(summary["rows"], 0)
        self.assertIn("not found", summary["no_data_reason"])

    def test_a_dataset_outside_the_project_is_never_read(self):
        # Two layers refuse this: the router will not carry an escaping path into
        # the arguments at all, and the reader would refuse it if it did.
        (self.root.parent / "outside.csv").write_text(CSV, encoding="utf-8")
        runs, route = self.run_tools("Analyse ../outside.csv and chart it")
        self.assertNotIn("source", route.requests[0].args)
        summary = json.loads((self.root / runs[0]["artifact_dir"] / "summary.json").read_text())
        self.assertEqual(summary["rows"], 0)
        self.assertIn("no dataset file was named", summary["no_data_reason"])


class DataContractTest(unittest.TestCase):
    """A claim in the summary must match what is on disk."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.destination = self.root / "workspace" / "run-1"
        self.destination.mkdir(parents=True)

    def build(self):
        with patch.object(orchestrate, "ROOT", self.root):
            return orchestrate.run_builtin_tools("Analyse sales.csv", self.destination, NO_MODEL)[0]

    def test_interpretation_claim_fails_verification(self):
        result = self.build()
        path = self.root / result["artifact_dir"] / "summary.json"
        summary = json.loads(path.read_text())
        summary["interpretation_performed"] = True
        path.write_text(json.dumps(summary))
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("interpretation" in error for error in checks[0]["errors"]))

    def test_rows_without_a_profile_fail_verification(self):
        result = self.build()
        path = self.root / result["artifact_dir"] / "summary.json"
        summary = json.loads(path.read_text())
        summary["rows"] = 10
        summary["columns_detail"] = {}
        path.write_text(json.dumps(summary))
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")

    def test_a_chart_with_a_script_fails_verification(self):
        result = self.build()
        path = self.root / result["artifact_dir"] / "chart.svg"
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>')
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("script element" in error for error in checks[0]["errors"]))

    def test_a_report_without_limits_fails_verification(self):
        result = self.build()
        path = self.root / result["artifact_dir"] / "analysis.md"
        path.write_text("# Report\n\n## Findings\n\nNothing.\n")
        checks = orchestrate.verify_artifact_tool_runs([result], project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
