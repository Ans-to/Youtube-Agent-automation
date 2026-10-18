import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents import practice
from agents import dispatch


class PracticeLoopTests(unittest.TestCase):
    def test_practice_run_creates_artifact_and_assessment_template(self):
        practice.WORKSPACE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            run_root = Path(directory) / "runs"
            attempt_dir, report = practice.create_attempt(
                "AGENT-51",
                task="Produce a short art-direction practice brief.",
                context="Only supplied practice context.",
                config={"model": {"enabled": False}},
                run_root=run_root,
            )
            self.assertEqual(report["status"], "template_only_not_assessed")
            self.assertFalse(report["model_weight_training_performed"])
            self.assertTrue((attempt_dir / "artifact.md").is_file())
            self.assertTrue((attempt_dir / "assessment.json").is_file())
            self.assertIn("no ai generation occurred", report["notes"].lower())

    def test_human_assessment_requires_evidence_and_records_feedback(self):
        practice.WORKSPACE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            root = Path(directory)
            attempt_dir, report = practice.create_attempt(
                "AGENT-52",
                task="Design a short compositing checklist.",
                config={"model": {"enabled": False}},
                run_root=root / "runs",
            )
            report_path = attempt_dir / "assessment.json"
            gates = report["quality_gates"]
            scores = {item["gate"]: {"score": 2, "evidence": "Checked artifact section"} for item in gates}
            first_name = gates[0]["gate"]
            bad_scores = dict(scores)
            bad_scores[first_name] = {"score": 2, "evidence": ""}
            with self.assertRaisesRegex(ValueError, "concrete evidence"):
                practice.record_human_assessment(report_path, bad_scores, "Improve diagram hierarchy", root / "feedback")
            result = practice.record_human_assessment(report_path, scores, "Improve diagram hierarchy", root / "feedback")
            self.assertEqual(result["status"], "human_reviewed_pass")
            self.assertEqual(result["score_percent"], 100.0)
            feedback = root / "feedback" / "AGENT-52.jsonl"
            self.assertTrue(feedback.is_file())
            saved = json.loads(feedback.read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(saved["human_reviewed"])
            self.assertIn("Improve diagram hierarchy", saved["improvement_notes"])

    def test_feedback_loader_uses_only_human_reviewed_lessons(self):
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            feedback = Path(directory) / "AGENT-51.jsonl"
            feedback.write_text(
                json.dumps({"human_reviewed": False, "improvement_notes": "ignore"}) + "\n" +
                json.dumps({"human_reviewed": True, "improvement_notes": "Use cleaner hierarchy.", "scores": {"layout": 1}}) + "\n",
                encoding="utf-8")
            with patch.object(dispatch, "FEEDBACK_DIR", Path(directory)):
                lessons = dispatch.load_human_lessons("AGENT-51")
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0]["improvement_notes"], "Use cleaner hierarchy.")
            self.assertIn("layout", lessons[0]["gates_to_improve"])

    def test_human_approval_profile_cannot_be_practiced_automatically(self):
        with self.assertRaisesRegex(ValueError, "human approval boundary"):
            practice.create_attempt("AGENT-50", task="Approve a release", config={"model": {"enabled": False}})


if __name__ == "__main__":
    unittest.main()
