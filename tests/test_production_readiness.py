"""Production readiness must not be inferred from a technical FFmpeg pass."""
import unittest

from video_studio.production_readiness import evaluate_production_readiness


class ProductionReadinessTests(unittest.TestCase):
    def package(self):
        scenes = [{
            "narration": "A fully narrated scene with a presenter.",
            "visual_type": ("hero", "diagram", "timeline")[index],
            "character": {
                "enabled": True,
                "pose": ("explain", "point", "think")[index],
                "expression": ("curious", "confident", "focused")[index],
            },
        } for index in range(3)]
        return (
            {
                "generated_by": "local_model_multi_pass",
                "duration_target_met": True,
                "narration_words": 1500,
                "target_minutes": 15,
                "subtitle_files": ["video.srt", "video.vtt"],
                "character_animation": {"phoneme_aligned": True},
            },
            {"fetched_page_count": 3, "independent_domain_count": 3},
            {"scenes": scenes},
        )

    def test_deterministic_template_is_not_production_ready(self):
        status, research, storyboard = self.package()
        status["generated_by"] = "deterministic_template"
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertIn("not a researched model-generated episode", " ".join(result["blockers"]))

    def test_short_narration_is_not_production_ready_even_if_technical_qa_passes(self):
        status, research, storyboard = self.package()
        status["narration_words"] = 64
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("too short" in item for item in result["blockers"]))

    def test_missing_independent_sources_blocks_readiness(self):
        status, research, storyboard = self.package()
        research["independent_domain_count"] = 1
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("independent domains" in item for item in result["blockers"]))

    def test_approximate_lip_sync_does_not_pass_production_readiness(self):
        status, research, storyboard = self.package()
        status["character_animation"]["phoneme_aligned"] = False
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("phoneme-aligned" in item for item in result["blockers"]))

    def test_all_explicit_requirements_can_pass(self):
        status, research, storyboard = self.package()
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertTrue(result["passed"])
        self.assertEqual(result["blockers"], [])

    def test_reused_frozen_presenter_pose_blocks_readiness(self):
        status, research, storyboard = self.package()
        for scene in storyboard["scenes"]:
            scene["character"]["pose"] = "explain"
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("pose variation" in item for item in result["blockers"]))

    def test_reused_expression_blocks_readiness(self):
        status, research, storyboard = self.package()
        for scene in storyboard["scenes"]:
            scene["character"]["expression"] = "confident"
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("expressive variation" in item for item in result["blockers"]))

    def test_single_visual_composition_reuse_blocks_readiness(self):
        status, research, storyboard = self.package()
        for scene in storyboard["scenes"]:
            scene["visual_type"] = "hero"
        result = evaluate_production_readiness(status, research, storyboard)
        self.assertFalse(result["passed"])
        self.assertTrue(any("composition variety" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
