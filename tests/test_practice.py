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

    def test_model_output_requires_human_review_before_feedback_is_reused(self):
        practice.WORKSPACE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            root = Path(directory)
            with patch.object(practice.dispatch, "run_role", return_value="# Test draft\nA model-generated mock artifact."):
                attempt_dir, report = practice.create_attempt(
                    "AGENT-51",
                    task="Create a motion art-direction brief.",
                    config={"model": {"enabled": True}},
                    run_root=root / "runs",
                )
            self.assertEqual(report["status"], "pending_human_assessment")
            self.assertEqual(report["mode"], "local_model")
            scores = {
                item["gate"]: {"score": 2, "evidence": "Observed requirement met in draft"}
                for item in report["quality_gates"]
            }
            saved = practice.record_human_assessment(
                attempt_dir / "assessment.json",
                scores,
                "Keep this reviewed lesson.",
                root / "feedback",
            )
            self.assertEqual(saved["status"], "human_reviewed_pass")
            self.assertTrue(saved["model_output_reviewed"])
            with patch.object(dispatch, "FEEDBACK_DIR", root / "feedback"):
                lessons = dispatch.load_human_lessons("AGENT-51")
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0]["improvement_notes"], "Keep this reviewed lesson.")

    def test_template_review_feedback_is_not_reused_as_model_learning(self):
        practice.WORKSPACE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            root = Path(directory)
            attempt_dir, report = practice.create_attempt(
                "AGENT-52",
                task="Create a compositing practice checklist.",
                config={"model": {"enabled": False}},
                run_root=root / "runs",
            )
            scores = {
                item["gate"]: {"score": 2, "evidence": "Observed checklist matches the rubric"}
                for item in report["quality_gates"]
            }
            saved = practice.record_human_assessment(
                attempt_dir / "assessment.json", scores, "Template feedback only.", root / "feedback"
            )
            self.assertEqual(saved["status"], "template_reviewed_only")
            with patch.object(dispatch, "FEEDBACK_DIR", root / "feedback"):
                self.assertEqual(dispatch.load_human_lessons("AGENT-52"), [])

    def test_feedback_loader_uses_only_human_reviewed_lessons(self):
        with tempfile.TemporaryDirectory(dir=practice.WORKSPACE) as directory:
            feedback = Path(directory) / "AGENT-51.jsonl"
            feedback.write_text(
                json.dumps({"human_reviewed": False, "model_output_reviewed": True, "improvement_notes": "unreviewed; ignore"}) + "\\n" +
                json.dumps({"human_reviewed": True, "model_output_reviewed": False, "improvement_notes": "template feedback; ignore"}) + "\\n" +
                json.dumps({"human_reviewed": True, "model_output_reviewed": True, "improvement_notes": "Use cleaner hierarchy.", "scores": {"layout": 1}}) + "\\n",
                encoding="utf-8")
            with patch.object(dispatch, "FEEDBACK_DIR", Path(directory)):
                lessons = dispatch.load_human_lessons("AGENT-51")
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0]["improvement_notes"], "Use cleaner hierarchy.")
            self.assertIn("layout", lessons[0]["gates_to_improve"])

    def test_batch_practice_lists_all_specialists_but_no_approval_roles(self):
        roles = practice.executable_roles()
        self.assertEqual(len(roles), 51)
        self.assertTrue(all(not role.get("approval_required") for role in roles))
        self.assertNotIn("AGENT-50", {role["id"] for role in roles})
        self.assertIn("AGENT-51", {role["id"] for role in roles})
        self.assertIn("AGENT-52", {role["id"] for role in roles})

    def test_human_approval_profile_cannot_be_practiced_automatically(self):
        with self.assertRaisesRegex(ValueError, "human approval boundary"):
            practice.create_attempt("AGENT-50", task="Approve a release", config={"model": {"enabled": False}})


if __name__ == "__main__":
    unittest.main()
