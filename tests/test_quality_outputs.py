import unittest
from quality_outputs import youtube_package, structured_plan, structured_draft, structured_review


class QualityOutputTests(unittest.TestCase):
    def test_youtube_package_is_detailed_and_evidence_safe(self):
        result = youtube_package("AI safety explainer", "How do local AI agents work?")
        for expected in ("Scene 01", "Motion-graphics direction", "Research register",
                         "Shorts cutdown", "Release QA", "[VERIFY]", "No sources were consulted"):
            self.assertIn(expected, result)
        self.assertIn("How do local AI agents work?", result)

    def test_plan_has_acceptance_evidence_and_risk_controls(self):
        result = structured_plan("Demo", "Build a mobile-friendly dashboard")
        self.assertIn("Definition of done", result)
        self.assertIn("Acceptance evidence", result)
        self.assertIn("human approval", result.lower())

    def test_draft_is_honest_about_template_mode(self):
        result = structured_draft("Draft", "Write a launch post")
        self.assertIn("structured drafting scaffold only", result.lower())

    def test_review_does_not_claim_checks_passed(self):
        result = structured_review("Review", "file excerpt")
        self.assertIn("NOT VERIFIED", result)
        self.assertIn("no semantic review or tests were performed", result.lower())


if __name__ == "__main__":
    unittest.main()
