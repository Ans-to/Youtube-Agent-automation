"""Regression tests for the content pipeline's research-first policy."""
import unittest

from video_studio.production import should_collect_research


class ResearchPolicyTests(unittest.TestCase):
    def test_model_generated_content_researches_by_default(self):
        self.assertTrue(should_collect_research(research_requested=False, model_enabled=True, render_template=False))

    def test_offline_template_smoke_stays_network_free_by_default(self):
        self.assertFalse(should_collect_research(research_requested=False, model_enabled=False, render_template=True))

    def test_explicit_research_is_honored_for_any_mode(self):
        self.assertTrue(should_collect_research(research_requested=True, model_enabled=False, render_template=True))


if __name__ == "__main__":
    unittest.main()
