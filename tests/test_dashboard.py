import unittest

import dashboard


class DashboardWorkflowTests(unittest.TestCase):
    def tearDown(self):
        active = dashboard.ACTIVE_WORKFLOW
        if active:
            dashboard.release_workflow(active)

    def test_workflow_gate_allows_only_one_active_workflow(self):
        claimed, active = dashboard.try_claim_workflow("test workflow")
        self.assertTrue(claimed)
        self.assertEqual(active, "")
        claimed_again, current = dashboard.try_claim_workflow("another workflow")
        self.assertFalse(claimed_again)
        self.assertEqual(current, "test workflow")
        dashboard.release_workflow("test workflow")
        claimed_after_release, _ = dashboard.try_claim_workflow("another workflow")
        self.assertTrue(claimed_after_release)

    def test_dashboard_exposes_video_product_and_specialist_forms(self):
        for action in ('action="/generate-video"', 'action="/build-product"', 'action="/run-pipeline"'):
            with self.subTest(action=action):
                self.assertIn(action, dashboard.HTML_PAGE)

    def test_video_and_product_outputs_are_reported_in_state(self):
        state = dashboard.task_state()
        self.assertIn("video_running", state)
        self.assertIn("video_output", state)
        self.assertIn("product_running", state)
        self.assertIn("product_output", state)


if __name__ == "__main__":
    unittest.main()
