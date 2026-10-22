"""Every write is shown as a change, not a dump.

The properties that matter: a diff is taken from the real files, it is bounded, a
binary file is named rather than rendered, and the manifest carries counts and
paths without smuggling file bodies back in — the manifest is a record, not a copy
of the artifact.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))
import orchestrate  # noqa: E402
import review  # noqa: E402
import test_fix  # noqa: E402
import tool_agent  # noqa: E402

NO_MODEL = {"model": {"enabled": False}}


class ChangeRecordTest(unittest.TestCase):
    def test_a_modified_file_carries_the_lines_that_changed(self):
        record = review.change_record("app.js", "const a = 1;\n", "const a = 1;\nconst b = 2;\n")
        self.assertEqual(record["kind"], "modified")
        self.assertEqual(record["added"], 1)
        self.assertEqual(record["removed"], 0)
        self.assertIn("+const b = 2;", record["diff"])
        self.assertIn("--- a/app.js", record["diff"])

    def test_a_created_file_is_marked_created(self):
        record = review.change_record("notes.md", None, "hello\n")
        self.assertEqual(record["kind"], "created")
        self.assertEqual(record["added"], 1)
        self.assertIn("+hello", record["diff"])

    def test_an_unchanged_file_produces_no_diff(self):
        record = review.change_record("notes.md", "same\n", "same\n")
        self.assertEqual(record["kind"], "unchanged")
        self.assertEqual(record["diff"], [])

    def test_an_empty_file_that_did_not_exist_is_still_a_change(self):
        record = review.change_record("blank.txt", None, "")
        self.assertEqual(record["kind"], "created")

    def test_a_deleted_file_is_counted(self):
        record = review.change_record("gone.txt", "a\nb\n", None)
        self.assertEqual(record["kind"], "deleted")
        self.assertEqual(record["removed"], 2)

    def test_a_binary_file_is_named_not_rendered(self):
        record = review.change_record("image.bin", "\x00abc", "\x00def")
        self.assertEqual(record["kind"], "binary")
        self.assertTrue(record["binary"])
        self.assertEqual(record["diff"], [])

    def test_a_large_diff_is_truncated_and_flagged(self):
        before = "".join(f"line {index}\n" for index in range(500))
        after = "".join(f"changed {index}\n" for index in range(500))
        record = review.change_record("big.txt", before, after)
        self.assertTrue(record["truncated"])
        self.assertLessEqual(len(record["diff"]), review.MAX_DIFF_LINES + 1)
        self.assertIn("diff truncated", record["diff"][-1])


class BuildChangesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def build(self, baseline):
        return review.build_changes(self.root, baseline)

    def test_only_the_baseline_files_are_considered(self):
        (self.root / "touched.txt").write_text("new\n")
        (self.root / "untouched.txt").write_text("other\n")
        changes = self.build({"touched.txt": None})
        self.assertEqual([item["path"] for item in changes["files"]], ["touched.txt"])

    def test_the_summary_matches_the_file_list(self):
        (self.root / "a.txt").write_text("a\n")
        (self.root / "b.txt").write_text("b\n")
        changes = self.build({"a.txt": None, "b.txt": "old\n"})
        self.assertEqual(changes["summary"]["files_changed"], len(changes["files"]))
        self.assertEqual(changes["summary"]["created"], 1)
        self.assertEqual(changes["summary"]["modified"], 1)

    def test_an_unchanged_file_is_listed_separately(self):
        (self.root / "same.txt").write_text("x\n")
        changes = self.build({"same.txt": "x\n"})
        self.assertEqual(changes["files"], [])
        self.assertEqual(changes["unchanged"], ["same.txt"])

    def test_the_report_names_no_absolute_paths(self):
        (self.root / "a.txt").write_text("a\n")
        text = json.dumps(self.build({"a.txt": None}))
        self.assertNotIn(str(self.root), text)

    def test_rendering_an_empty_change_set_says_so(self):
        page = review.render_markdown(self.build({}))
        self.assertIn("No files were written or changed", page)


class RenderTest(unittest.TestCase):
    def test_the_page_shows_a_fenced_diff_and_its_limits(self):
        changes = review.build_changes  # noqa: F841 - keeps the reader oriented
        record = review.change_record("a.txt", "old\n", "new\n")
        page = review.render_markdown({
            "files": [record],
            "summary": {"files_changed": 1, "created": 0, "modified": 1, "deleted": 0,
                        "binary": 0, "added_lines": 1, "removed_lines": 1},
            "limits": ["Diffs are capped."],
        })
        self.assertTrue(page.startswith("# "))
        self.assertIn("```diff", page)
        self.assertIn("-old", page)
        self.assertIn("+new", page)
        self.assertIn("## Limits", page)

    def test_the_manifest_entry_carries_no_file_bodies(self):
        record = review.change_record("a.txt", None, "secret content here\n")
        entry = review.manifest_entry({"files": [record], "summary": {"files_changed": 1}})
        self.assertEqual(entry["files"], ["a.txt"])
        self.assertNotIn("secret content here", json.dumps(entry))

    def test_the_aggregate_page_points_at_each_builder(self):
        page = review.render_aggregate([
            {"tool": "tool_agent", "artifact_dir": "workspace/run/projects/run-web",
             "files": ["index.html"], "summary": {"files_changed": 1, "created": 1,
                                                  "modified": 0, "deleted": 0,
                                                  "added_lines": 10, "removed_lines": 0},
             "review": "changes.md"},
        ])
        self.assertIn("tool_agent", page)
        self.assertIn("workspace/run/projects/run-web/changes.md", page)
        self.assertIn("`index.html`", page)

    def test_the_aggregate_page_handles_a_run_that_wrote_nothing(self):
        self.assertIn("No builder wrote files", review.render_aggregate([]))


class ToolAgentChangeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name) / "workspace"

    def test_a_build_writes_a_change_report_beside_its_artifacts(self):
        result = tool_agent.run_tool_agent("Build a website for a bakery", self.workspace, "TASK-1")
        sandbox = self.workspace / "projects" / "task-1"
        self.assertTrue((sandbox / "changes.json").is_file())
        self.assertTrue((sandbox / "changes.md").is_file())
        self.assertIn("changes.json", result["files"])
        report = json.loads((sandbox / "changes.json").read_text())
        self.assertEqual(report["schema"], 1)
        self.assertEqual(sorted(item["path"] for item in report["files"]),
                         sorted(result["artifacts"]))

    def test_the_manifest_keeps_counts_not_bodies(self):
        result = tool_agent.run_tool_agent("Build a website for a bakery", self.workspace, "TASK-2")
        serialized = json.dumps(result["changes"])
        self.assertIn("index.html", serialized)
        self.assertNotIn("Offline project scaffold", serialized)
        self.assertNotIn("localStorage.setItem", serialized)

    def test_a_second_run_over_changed_files_reports_modifications(self):
        tool_agent.run_tool_agent("Build a site", self.workspace, "TASK-3")
        page = self.workspace / "projects" / "task-3" / "index.html"
        page.write_text("<p>hand edited</p>\n", encoding="utf-8")
        result = tool_agent.run_tool_agent("Build a site", self.workspace, "TASK-3")
        report = json.loads((self.workspace / "projects" / "task-3" / "changes.json").read_text())
        index = next(item for item in report["files"] if item["path"] == "index.html")
        self.assertEqual(index["kind"], "modified")
        self.assertIn("-<p>hand edited</p>", index["diff"])
        self.assertEqual(result["status"], "partial")

    def test_a_single_file_plan_records_exactly_that_file(self):
        def model(prompt, max_tokens):
            return json.dumps({
                "steps": [{"tool": "write_file", "args": {"path": "notes.md",
                                                           "content": "# Notes\n"}}],
                "verify": [{"path": "notes.md", "contains": "# Notes"}],
            })

        result = tool_agent.run_tool_agent("Write notes", self.workspace, "TASK-4", model_call=model)
        report = json.loads((self.workspace / "projects" / "task-4" / "changes.json").read_text())
        self.assertEqual([item["path"] for item in report["files"]], ["notes.md"])
        self.assertEqual(result["changes"]["summary"]["files_changed"], 1)


class VerificationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.destination = self.workspace / "run"
        self.destination.mkdir()
        patcher = patch.object(orchestrate, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = patch.dict(os.environ, {"AGENT_HQ_NO_MEMORY": "1"})
        env.start()
        self.addCleanup(env.stop)

    def build(self, goal="Write a changelog for the v2 release"):
        sink = {}
        runs = orchestrate.run_builtin_tools(goal, self.destination, NO_MODEL, route_sink=sink)
        return runs, sink["route"]

    def test_a_real_run_passes_and_records_the_review(self):
        runs, _ = self.build()
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "passed", checks[0]["errors"])
        self.assertIn("change_report_matches_the_writes", checks[0]["checks"])

    def test_a_missing_change_report_fails_verification(self):
        runs, _ = self.build()
        for name in ("changes.json", "changes.md"):
            (self.root / runs[0]["artifact_dir"] / name).unlink()
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("changes.json" in error for error in checks[0]["errors"]))

    def test_a_change_without_a_diff_fails_verification(self):
        runs, _ = self.build()
        path = self.root / runs[0]["artifact_dir"] / "changes.json"
        report = json.loads(path.read_text())
        report["files"][0]["diff"] = []
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("no diff" in error for error in checks[0]["errors"]))

    def test_a_summary_that_does_not_match_the_files_fails_verification(self):
        runs, _ = self.build()
        path = self.root / runs[0]["artifact_dir"] / "changes.json"
        report = json.loads(path.read_text())
        report["summary"]["files_changed"] = 99
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("does not match its file list" in error for error in checks[0]["errors"]))

    def test_a_path_escaping_the_artifact_fails_verification(self):
        runs, _ = self.build()
        path = self.root / runs[0]["artifact_dir"] / "changes.json"
        report = json.loads(path.read_text())
        report["files"][0]["path"] = "../outside.txt"
        path.write_text(json.dumps(report))
        checks = orchestrate.verify_artifact_tool_runs(runs, project_root=self.root)
        self.assertEqual(checks[0]["status"], "failed")
        self.assertTrue(any("outside the artifact" in error for error in checks[0]["errors"]))

    def test_the_run_level_index_counts_what_was_written(self):
        runs, _ = self.build()
        summary = orchestrate._write_change_review("Write a changelog", self.destination, runs)
        self.assertEqual(summary["builders"], 1)
        self.assertEqual(summary["files_changed"], 2)
        self.assertIn("review/changes.md", summary["path"])

    def test_the_run_level_index_ignores_builders_that_wrote_nothing(self):
        summary = orchestrate._write_change_review("Do nothing", self.destination, [])
        self.assertEqual(summary["builders"], 0)
        page = (self.destination / "review" / "changes.md").read_text()
        self.assertIn("No builder wrote files", page)


class RunReviewTest(unittest.TestCase):
    """The whole pipeline leaves one index pointing at every builder's diff."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        env = patch.dict(os.environ, {"AGENT_HQ_NO_MEMORY": "1"})
        env.start()
        self.addCleanup(env.stop)

    def test_a_pipeline_run_writes_a_review_index(self):
        with (
            patch.object(orchestrate, "ROOT", self.root),
            patch.object(orchestrate, "WORKSPACE", self.workspace),
            patch.object(orchestrate.dispatch, "run_role",
                         side_effect=lambda role, task, context, cfg: "# Draft\n\nOutput."),
        ):
            destination, manifest = orchestrate.run_pipeline(
                "Write a changelog for the v2 release",
                output_dir=self.workspace / "run", config=NO_MODEL, agent_ids=["AGENT-09"])
        review_page = destination / "review" / "changes.md"
        self.assertTrue(review_page.is_file())
        self.assertIn("tool_agent", review_page.read_text())
        self.assertIn("deliverable.md", review_page.read_text())
        self.assertEqual(manifest["change_review"]["files_changed"], 2)
        # The index must not sit among the stage notes.
        top_level = sorted(path.name for path in destination.glob("*.md"))
        self.assertNotIn("changes.md", top_level)


class TestFixDiffTest(unittest.TestCase):
    """A repair is a change too, so it gets the same treatment."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        (self.project / "calc.py").write_text("def average(v):\n    return sum(v) / (len(v) - 1)\n")
        (self.project / "tests").mkdir()
        (self.project / "tests" / "__init__.py").write_text("")
        (self.project / "tests" / "test_calc.py").write_text(
            "import unittest\nfrom calc import average\n\n\n"
            "class T(unittest.TestCase):\n    def test_it(self):\n"
            "        self.assertEqual(average([2, 4]), 3)\n", encoding="utf-8")

    def propose(self, content):
        return lambda run: {"path": "calc.py", "content": content, "why": "denominator"}

    def test_a_verified_repair_carries_its_diff(self):
        report = test_fix.diagnose(
            self.project, propose=self.propose("def average(v):\n    return sum(v) / len(v)\n"))
        self.assertTrue(report["verified_fix"])
        diff = report["repairs"][0]["diff"]
        self.assertIn("-    return sum(v) / (len(v) - 1)", diff)
        self.assertIn("+    return sum(v) / len(v)", diff)
        self.assertIn("```diff", test_fix.render_markdown(report))

    def test_a_reverted_repair_keeps_the_diff_as_evidence(self):
        report = test_fix.diagnose(
            self.project, propose=self.propose("def average(v):\n    return 0\n"))
        self.assertFalse(report["verified_fix"])
        self.assertTrue(report["repairs"][0]["reverted"])
        # The diff documents what was tried, even though the file is back as it was.
        self.assertIn("+    return 0", report["repairs"][0]["diff"])
        self.assertIn("(len(v) - 1)", (self.project / "calc.py").read_text())


if __name__ == "__main__":
    unittest.main()
