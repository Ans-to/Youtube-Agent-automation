import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import orchestrate


class OrchestrationTests(unittest.TestCase):
    def test_human_approval_role_cannot_be_auto_orchestrated(self):
        with self.assertRaises(ValueError):
            orchestrate.run_pipeline("Prepare a draft", agent_ids=["AGENT-50"], config={"model": {"enabled": False}})

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            orchestrate.run_pipeline("Prepare a draft", agent_ids=["AGENT-99"], config={"model": {"enabled": False}})

    def test_sequential_pipeline_writes_manifest_and_draft_outputs(self):
        orchestrate.WORKSPACE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=orchestrate.WORKSPACE) as directory:
            destination, manifest = orchestrate.run_pipeline(
                "Create a small technical video outline",
                context="Supplied local source note.",
                agent_ids=["AGENT-09", "AGENT-20"],
                output_dir=Path(directory) / "pipeline",
                config={"model": {"enabled": False}},
            )
            self.assertEqual(len(manifest["pipeline"]), 3)
            self.assertEqual(manifest["pipeline"][-1]["agent_id"], "AGENT-08")
            self.assertEqual(manifest["research_performed"], "attempted_for_each_specialist_stage")
            self.assertTrue(manifest["human_review_required"])
            self.assertTrue((destination / "pipeline-status.json").is_file())
            self.assertEqual(len(list(destination.glob("*.md"))), 4)


if __name__ == "__main__":
    unittest.main()
