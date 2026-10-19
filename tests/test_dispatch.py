import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import dispatch


class AgentDispatcherTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.research_patch = patch.object(dispatch, "collect_web_research", None)
        self.research_patch.start()
        self.addCleanup(self.research_patch.stop)

    def test_research_topic_extracts_user_goal_and_specialist_focus(self):
        task = (
            "OVERALL USER GOAL:\nBuild a textile dyeing reconciliation tool for factories.\n\n"
            "YOUR CEO-ASSIGNED SUBTASK:\nResearch authoritative textile traceability sources and current compliance risks.\n\n"
            "Pipeline stage 1 of 4. Work on your assigned responsibility."
        )
        topic = dispatch.research_topic_from_task(task)
        self.assertIn("textile dyeing reconciliation tool", topic)
        self.assertIn("textile traceability sources", topic)
        self.assertNotIn("OVERALL USER GOAL", topic)
        self.assertNotIn("Pipeline stage", topic)

    def test_ceo_research_topic_extracts_goal_not_delegation_boilerplate(self):
        task = (
            "Act as the CEO of Agent HQ.\nReturn ONLY valid JSON.\n\n"
            "USER GOAL:\nFind current free tools for making professional motion graphics.\n\n"
            "AVAILABLE SPECIALISTS:\n" + ("AGENT roster " * 50)
        )
        topic = dispatch.research_topic_from_task(task)
        self.assertIn("free tools for making professional motion graphics", topic)
        self.assertNotIn("AVAILABLE SPECIALISTS", topic)

    def test_finds_specialist_role(self):
        role = dispatch.find_role("AGENT-09")
        self.assertIsNotNone(role)
        self.assertEqual(role["name"], "Script Architect")

    def test_motion_roles_receive_implemented_visual_system_reference(self):
        for agent_id in ("AGENT-51", "AGENT-52"):
            with self.subTest(agent_id=agent_id):
                role = dispatch.find_role(agent_id)
                output = dispatch.run_role(role, "Design a practice output", "", {"model": {"enabled": False}})
                self.assertIn("IMPLEMENTED MOTION DESIGN SYSTEM", output)
                self.assertIn("transition_in", output)

    def test_finds_skillbook_for_each_new_motion_role(self):
        for agent_id in ("AGENT-51", "AGENT-52"):
            with self.subTest(agent_id=agent_id):
                profile = dispatch.find_skill(agent_id)
                self.assertIsNotNone(profile)
                self.assertGreaterEqual(len(profile["workflow"]), 3)
                self.assertGreaterEqual(len(profile["quality_gates"]), 3)

    def test_human_approval_role_cannot_be_run_automatically(self):
        role = dispatch.find_role("AGENT-50")
        with self.assertRaisesRegex(ValueError, "human approval boundary"):
            dispatch.run_role(role, "Approve this upload", "", {"model": {"enabled": False}})

    def test_unknown_role_returns_none(self):
        self.assertIsNone(dispatch.find_role("AGENT-99"))

    def test_disabled_model_is_explicit_template_mode(self):
        role = dispatch.find_role("AGENT-08")
        output = dispatch.run_role(role, "Review this claim", "No sources", {"model": {"enabled": False}})
        self.assertIn("Template mode only", output)
        self.assertIn("Fact Checker", output)
        self.assertIn("Field mastery playbook", output)
        self.assertIn("QUALITY GATES", output)

    def test_slug_removes_path_separators(self):
        self.assertNotIn("/", dispatch.safe_slug("../danger/task"))



    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    dispatch.post_local_model(url, {}, 1)

if __name__ == "__main__":
    unittest.main()
