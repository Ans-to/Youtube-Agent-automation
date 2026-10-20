import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

        def fake_specialist(role, instruction, context, config, runner=None):
            agent_id = role["id"]
            role_name = role.get("name", agent_id)
            if agent_id == "AGENT-08":
                return (
                    "# Final review\nThe supplied draft artifacts meet this test's acceptance criteria.\n"
                    "OVERALL QUALITY GATE: PASS",
                    0,
                )
            return (
                "# " + role_name + "\nDeterministic test deliverable for " + agent_id + ".",
                0,
            )

        with tempfile.TemporaryDirectory(dir=orchestrate.WORKSPACE) as directory:
            with patch.object(orchestrate, "run_role_with_retry", side_effect=fake_specialist):
                destination, manifest = orchestrate.run_pipeline(
                    "Prepare a concise technical outline",
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
            for stage in manifest["pipeline"]:
                self.assertTrue((destination / stage["output_file"]).is_file(), stage["output_file"])
            self.assertEqual(len(list(destination.glob("*.md"))), len(manifest["pipeline"]))
            self.assertEqual(manifest["quality_gate"], "pass")


if __name__ == "__main__":
    unittest.main()
