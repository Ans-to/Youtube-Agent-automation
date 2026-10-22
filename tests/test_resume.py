"""Resuming an unfinished run: skip what is done, redo only what is missing.

The failure this guards against is subtle: a resumed run that quietly redoes
everything looks like it worked, and a resumed run that mixes two different tasks'
outputs produces a manifest describing a job that never existed. Both are tested
here, along with the ordinary case of getting the same files back.
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

NO_MODEL = {"model": {"enabled": False}}
STAGES = ["AGENT-09", "AGENT-20", "AGENT-08"]


class ResumeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.destination = self.workspace / "run"
        self.calls = []
        patcher = patch.dict(os.environ, {"AGENT_HQ_NO_MEMORY": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers ------------------------------------------------------------
    def fake_role(self, role, task, context, cfg):
        self.calls.append(role["id"])
        if role["id"] == "AGENT-08":
            return "# Review\n\nLooks fine.\n\nOVERALL QUALITY GATE: PASS"
        return "# " + role["name"] + "\n\nDeterministic output for " + role["id"] + "."

    def pipeline(self, task="Prepare a concise technical outline", *, resume=False, role=None, agent_ids=None):
        with (
            patch.object(orchestrate, "ROOT", self.root),
            patch.object(orchestrate, "WORKSPACE", self.workspace),
            patch.object(orchestrate.dispatch, "run_role", side_effect=role or self.fake_role),
        ):
            return orchestrate.run_pipeline(task, output_dir=self.destination, config=NO_MODEL,
                                            agent_ids=agent_ids or STAGES, resume=resume)

    def stage_files(self):
        return sorted(path.name for path in self.destination.glob("[0-9][0-9]-*.md"))

    def first_run(self):
        _, manifest = self.pipeline()
        self.calls.clear()
        return manifest

    # -- the ordinary case ---------------------------------------------------
    def test_a_finished_run_is_reused_without_calling_the_model(self):
        self.first_run()
        _, manifest = self.pipeline(resume=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(manifest["resume"]["stages_reused"], len(STAGES))
        self.assertEqual(manifest["resume"]["stages_run"], 0)
        self.assertTrue(all(stage["status"] == "reused_from_previous_run" for stage in manifest["pipeline"]))

    def test_reused_files_are_not_rewritten(self):
        self.first_run()
        before = {path.name: (path.read_text(), path.stat().st_mtime_ns)
                  for path in self.destination.glob("[0-9][0-9]-*.md")}
        self.pipeline(resume=True)
        after = {path.name: (path.read_text(), path.stat().st_mtime_ns)
                 for path in self.destination.glob("[0-9][0-9]-*.md")}
        self.assertEqual(before, after)

    def test_the_quality_gate_is_recovered_from_the_reused_reviewer(self):
        self.first_run()
        _, manifest = self.pipeline(resume=True)
        self.assertEqual(manifest["quality_gate"], "pass")
        reviewer = next(stage for stage in manifest["pipeline"] if stage["agent_id"] == "AGENT-08")
        self.assertEqual(reviewer["quality_gate"], "pass")
        self.assertTrue(reviewer.get("resumed"))

    # -- the interrupted case ------------------------------------------------
    def test_only_the_missing_stage_runs_again(self):
        self.first_run()
        missing = self.stage_files()[1]
        (self.destination / missing).unlink()
        _, manifest = self.pipeline(resume=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(manifest["resume"]["stages_reused"], len(STAGES) - 1)
        self.assertEqual(manifest["resume"]["stages_run"], 1)
        self.assertEqual(len(self.stage_files()), len(STAGES))

    def test_resuming_does_not_duplicate_artifacts(self):
        self.first_run()
        before = self.stage_files()
        (self.destination / before[2]).unlink()
        self.pipeline(resume=True)
        self.assertEqual(self.stage_files(), before)

    def test_an_empty_stage_file_counts_as_unfinished(self):
        self.first_run()
        empty = self.destination / self.stage_files()[0]
        empty.write_text("")
        _, manifest = self.pipeline(resume=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(manifest["resume"]["stages_run"], 1)

    def test_a_reused_stage_does_not_claim_to_have_researched(self):
        self.first_run()
        _, manifest = self.pipeline(resume=True)
        stage = manifest["pipeline"][0]
        self.assertEqual(stage["research_status"], "not_rerun")
        self.assertEqual(stage["research_reports"], [])
        self.assertEqual(stage["retry_count"], 0)

    # -- refusals ------------------------------------------------------------
    def test_a_different_task_is_not_resumed(self):
        self.first_run()
        _, manifest = self.pipeline(task="Prepare a totally different outline", resume=True)
        self.assertFalse(manifest["resume"]["enabled"])
        self.assertIn("different task", manifest["resume"]["reason"])
        self.assertEqual(len(self.calls), len(STAGES))

    def test_a_different_stage_set_is_not_resumed(self):
        self.first_run()
        _, manifest = self.pipeline(resume=True, agent_ids=["AGENT-09", "AGENT-08"])
        self.assertFalse(manifest["resume"]["enabled"])
        self.assertIn("different stages", manifest["resume"]["reason"])

    def test_nothing_to_resume_is_not_an_error(self):
        _, manifest = self.pipeline(resume=True)
        self.assertFalse(manifest["resume"]["enabled"])
        self.assertIn("no previous run", manifest["resume"]["reason"])
        self.assertEqual(len(self.calls), len(STAGES))

    def test_a_corrupt_delegation_file_is_not_trusted(self):
        self.first_run()
        (self.destination / "00-ceo-delegation.json").write_text("{not json")
        _, manifest = self.pipeline(resume=True)
        self.assertFalse(manifest["resume"]["enabled"])
        self.assertIn("no previous run", manifest["resume"]["reason"])

    def test_resume_not_requested_is_recorded_as_such(self):
        _, manifest = self.pipeline()
        self.assertFalse(manifest["resume"]["enabled"])
        self.assertIn("not requested", manifest["resume"]["reason"])

    # -- the record ----------------------------------------------------------
    def test_the_resume_decision_is_in_the_manifest_and_on_disk(self):
        self.first_run()
        destination, manifest = self.pipeline(resume=True)
        on_disk = json.loads((destination / "pipeline-status.json").read_text())
        self.assertTrue(on_disk["resume"]["enabled"])
        self.assertEqual(on_disk["resume"]["stages_reused"], len(STAGES))

    def test_the_resume_record_is_json_safe_and_leaks_no_paths(self):
        self.first_run()
        _, manifest = self.pipeline(resume=True)
        self.assertNotIn(str(self.root), json.dumps(manifest["resume"]))


if __name__ == "__main__":
    unittest.main()
