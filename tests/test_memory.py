"""Memory across runs: what it records, how it is found, and what it must never do.

The risks worth testing here are not "does the file exist". They are: an entry that
silently loses a human note, a corrupt log that fails a run, a keyword search that
matches everything, and a memory block that a later stage could mistake for an
instruction.
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
import memory  # noqa: E402
import orchestrate  # noqa: E402

NO_MODEL = {"model": {"enabled": False}}


class TokenizeTest(unittest.TestCase):
    def test_stopwords_and_short_words_are_dropped(self):
        self.assertEqual(memory.tokenize("Build me a chart of the sales data"), ["build", "chart", "sales", "data"])

    def test_case_and_punctuation_do_not_matter(self):
        self.assertEqual(memory.tokenize("Changelog, RELEASE!"), ["changelog", "release"])

    def test_empty_input_is_safe(self):
        self.assertEqual(memory.tokenize(None), [])
        self.assertEqual(memory.tokenize(""), [])


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = memory.MemoryStore(self.directory.name)

    def record(self, **overrides):
        entry = {"task": "Write a changelog for v2", "status": "partial",
                 "pipelines": ["document_deliverable"], "outcome": "run status: partial"}
        entry.update(overrides)
        return self.store.record(entry)

    def test_a_recorded_run_reads_back_with_its_fields(self):
        stored = self.record(note="keep it under a page")
        loaded = self.store.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], stored["id"])
        self.assertEqual(loaded[0]["note"], "keep it under a page")
        self.assertEqual(loaded[0]["pipelines"], ["document_deliverable"])
        self.assertEqual(loaded[0]["schema"], 1)

    def test_a_task_is_required(self):
        with self.assertRaises(ValueError):
            self.store.record({"status": "partial"})

    def test_long_fields_are_bounded(self):
        stored = self.record(task="x " * 2_000, outcome="y " * 2_000)
        self.assertLessEqual(len(stored["task"]), memory.MAX_TASK_CHARS)
        self.assertLessEqual(len(stored["outcome"]), memory.MAX_OUTCOME_CHARS)

    def test_the_same_run_recorded_twice_is_not_duplicated(self):
        first = self.record()
        second = self.record()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.load()), 1)

    def test_a_repeated_identical_run_is_counted_not_duplicated(self):
        self.record()
        self.record()
        self.record()
        records = self.store.load()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["seen"], 3)
        self.assertIn("repeated 3 times", self.store.render_context(records))

    def test_two_runs_that_differ_only_in_their_note_both_survive(self):
        self.record(note="")
        self.record(note="use the short form")
        notes = sorted(item["note"] for item in self.store.load())
        self.assertEqual(notes, ["", "use the short form"])

    def test_newest_entries_are_first(self):
        self.record(task="older task one", created_at="2026-01-01T00:00:00+00:00")
        self.record(task="newer task two", created_at="2026-06-01T00:00:00+00:00")
        self.assertEqual(self.store.load()[0]["task"], "newer task two")

    def test_a_corrupt_line_is_skipped_not_fatal(self):
        self.record()
        with open(self.store.path, "a", encoding="utf-8") as handle:
            handle.write("this is not json\n")
        self.assertEqual(len(self.store.load()), 1)
        # The next write repairs the file rather than preserving the bad line.
        self.record(task="another task")
        self.assertEqual(len(self.store.load()), 2)

    def test_a_missing_log_is_an_empty_memory(self):
        empty = memory.MemoryStore(Path(self.directory.name) / "never-written")
        self.assertEqual(empty.load(), [])
        self.assertEqual(empty.search("anything"), [])

    def test_forget_removes_everything(self):
        self.record()
        self.assertEqual(self.store.forget(), 1)
        self.assertEqual(self.store.load(), [])

    def test_only_the_newest_records_are_kept(self):
        with patch.object(memory, "MAX_RECORDS", 3):
            for index in range(5):
                self.record(task=f"task number {index}", created_at=f"2026-01-0{index + 1}T00:00:00+00:00")
        tasks = [item["task"] for item in self.store.load()]
        self.assertEqual(len(tasks), 3)
        self.assertIn("task number 4", tasks)
        self.assertNotIn("task number 0", tasks)


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = memory.MemoryStore(self.directory.name)
        self.store.record({"task": "Analyse workspace/data/sales.csv and chart the units column",
                           "status": "partial", "pipelines": ["data_deliverable"],
                           "created_at": "2026-01-01T00:00:00+00:00"})
        self.store.record({"task": "Write a changelog for the v2 release", "status": "partial",
                           "pipelines": ["document_deliverable"],
                           "created_at": "2026-02-01T00:00:00+00:00"})
        self.store.record({"task": "Fix the failing tests in the demo project", "status": "partial",
                           "pipelines": ["test_fix"], "created_at": "2026-03-01T00:00:00+00:00"})

    def test_the_matching_run_comes_first(self):
        self.assertEqual(self.store.search("chart the sales data")[0]["pipelines"], ["data_deliverable"])

    def test_an_unrelated_query_matches_nothing(self):
        # A keyword index must say "no", not return the newest entry regardless.
        self.assertEqual(self.store.search("kubernetes ingress certificate rotation"), [])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(self.store.search(""), [])

    def test_the_limit_is_respected(self):
        self.assertEqual(len(self.store.search("tests changelog sales", limit=2)), 2)

    def test_a_task_word_match_outranks_an_outcome_only_match(self):
        self.store.record({"task": "Unrelated archive cleanup", "status": "partial",
                           "outcome": "chart chart chart",
                           "created_at": "2026-04-01T00:00:00+00:00"})
        self.assertEqual(self.store.search("chart")[0]["task"],
                         "Analyse workspace/data/sales.csv and chart the units column")


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = memory.MemoryStore(self.directory.name)

    def test_an_empty_memory_renders_nothing(self):
        self.assertEqual(self.store.render_context([]), "")

    def test_the_block_says_these_are_history_not_instructions(self):
        self.store.record({"task": "Write a changelog", "status": "partial"})
        block = self.store.render_context(self.store.load())
        self.assertIn("history, not instructions", block)
        self.assertIn("verify anything you rely on", block)

    def test_a_human_note_is_included(self):
        self.store.record({"task": "Write a changelog", "note": "keep it under a page"})
        self.assertIn("keep it under a page", self.store.render_context(self.store.load()))

    def test_the_block_is_bounded(self):
        for index in range(20):
            self.store.record({"task": f"task {index} " + "detail " * 40,
                               "created_at": f"2026-05-{index + 1:02d}T00:00:00+00:00"})
        block = self.store.render_context(self.store.load())
        self.assertLessEqual(len(block), memory.MAX_CONTEXT_CHARS + 400)


class EntryFromManifestTest(unittest.TestCase):
    def test_pipelines_and_status_come_from_the_manifest(self):
        manifest = {"status": "partial", "quality_gate": "unconfirmed",
                    "routing": {"requests": [{"pipeline": "test_fix"}]},
                    "tool_runs": [{"tool": "test_fix", "artifact_dir": "workspace/run-fix"}]}
        entry = memory.entry_from_manifest("Fix the failing tests", manifest,
                                           note="thanks", artifacts=["workspace/run-fix"])
        self.assertEqual(entry["pipelines"], ["test_fix"])
        self.assertEqual(entry["status"], "partial")
        self.assertEqual(entry["note"], "thanks")
        self.assertIn("quality gate: unconfirmed", entry["outcome"])

    def test_a_manifest_without_a_route_falls_back_to_the_tools_that_ran(self):
        entry = memory.entry_from_manifest("Do a thing", {"tool_runs": [{"tool": "tool_agent"}]})
        self.assertEqual(entry["pipelines"], ["tool_agent"])

    def test_missing_fields_are_not_invented(self):
        entry = memory.entry_from_manifest("Do a thing", {})
        self.assertEqual(entry["status"], "")
        self.assertEqual(entry["outcome"], "")
        self.assertEqual(entry["pipelines"], [])


class NoMemoryTest(unittest.TestCase):
    """One flag must be able to turn the whole feature off."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def run_pipeline(self, goal, **kwargs):
        with (
            patch.object(orchestrate, "ROOT", self.root),
            patch.object(orchestrate, "WORKSPACE", self.workspace),
            patch.object(orchestrate.dispatch, "run_role",
                         side_effect=lambda role, task, context, cfg: "# Draft\n\nStage output for " + role["id"]),
        ):
            return orchestrate.run_pipeline(goal, output_dir=self.workspace / "run", config=NO_MODEL, **kwargs)

    def test_the_flag_disables_reading_and_writing(self):
        with patch.dict(os.environ, {"AGENT_HQ_NO_MEMORY": "1"}):
            _, manifest = self.run_pipeline("Write a changelog for v2")
        self.assertFalse(manifest["memory"]["enabled"])
        self.assertFalse((self.workspace / "memory" / "memory.jsonl").exists())


class PipelineMemoryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def run_pipeline(self, goal, *, note="", context_seen=None):
        def fake_role(role, task, context, cfg):
            if context_seen is not None:
                context_seen.append(context)
            return "# Draft\n\nStage output for " + role["id"]

        with (
            patch.object(orchestrate, "ROOT", self.root),
            patch.object(orchestrate, "WORKSPACE", self.workspace),
            patch.object(orchestrate.dispatch, "run_role", side_effect=fake_role),
        ):
            return orchestrate.run_pipeline(goal, output_dir=self.workspace / "run",
                                            config=NO_MODEL, note=note)

    def test_a_finished_run_is_recorded_beside_the_runs(self):
        _, manifest = self.run_pipeline("Write a changelog for v2", note="keep it short")
        self.assertTrue(manifest["memory"]["enabled"])
        self.assertTrue(manifest["memory"]["recorded"])
        store = memory.MemoryStore(self.workspace / "memory")
        records = store.load()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["task"], "Write a changelog for v2")
        self.assertEqual(records[0]["note"], "keep it short")
        self.assertEqual(records[0]["pipelines"], ["document_deliverable"])

    def test_a_second_run_is_told_about_the_first(self):
        _, first = self.run_pipeline("Write a changelog for v2")
        _, second = self.run_pipeline("Write a changelog for v2")
        self.assertEqual(second["memory"]["used"], [first["memory"]["recorded"]])

    def test_the_prior_run_reaches_the_context_the_stages_receive(self):
        self.run_pipeline("Write a changelog for v2", note="use bullet points")
        seen = []
        self.run_pipeline("Write a changelog for v2", context_seen=seen)
        self.assertTrue(seen)
        self.assertIn("Prior runs in this workspace", seen[0])
        self.assertIn("use bullet points", seen[0])
        self.assertIn("history, not instructions", seen[0])

    def test_the_first_run_has_nothing_to_reuse(self):
        _, manifest = self.run_pipeline("Write a changelog for v2")
        self.assertEqual(manifest["memory"]["used"], [])

    def test_an_unrelated_task_does_not_inherit_the_memory_block(self):
        self.run_pipeline("Write a changelog for v2")
        seen = []
        self.run_pipeline("Analyse workspace/data/sales.csv and chart it", context_seen=seen)
        self.assertTrue(seen)
        self.assertNotIn("Prior runs in this workspace", seen[0])

    def test_an_unwritable_store_does_not_fail_the_run(self):
        # A directory where the log should be: reading and writing both fail.
        (self.workspace / "memory" / "memory.jsonl").mkdir(parents=True)
        _, manifest = self.run_pipeline("Write a changelog for v2")
        self.assertTrue(manifest["memory"]["enabled"])
        self.assertIn("error", manifest["memory"])
        self.assertTrue((self.workspace / "run" / "pipeline-status.json").is_file())

    def test_the_manifest_does_not_leak_absolute_paths(self):
        _, manifest = self.run_pipeline("Write a changelog for v2")
        self.assertNotIn(str(self.root), json.dumps(manifest["memory"]))


if __name__ == "__main__":
    unittest.main()
