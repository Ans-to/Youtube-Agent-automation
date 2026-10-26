import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import dispatch


class AgentDispatcherTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root_patch = patch.object(dispatch, "ROOT", Path(self.tempdir.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
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

    def test_specialist_research_uses_five_complementary_queries_and_pages(self):
        from unittest.mock import patch
        role = dispatch.find_role("AGENT-02")
        metadata = {"topic": "task topic", "pages_attempted": 5, "pages_fetched": 5}
        sources = [{"url": "https://example.com/" + str(i)} for i in range(5)]
        response = {"choices": [{"message": {"content": "Research-backed specialist draft."}}]}
        with patch.object(dispatch, "collect_web_research", return_value=(metadata, sources)) as research_call, \
             patch.object(dispatch, "post_local_model", return_value=response):
            dispatch.run_role(
                role,
                "OVERALL USER GOAL:\\nBuild a useful AI video workflow.\\n\\n"
                "YOUR CEO-ASSIGNED SUBTASK:\\nResearch reliable implementation approaches.",
                "",
                {"model": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1/chat/completions",
                    "model": "llama3.2:3b",
                    "max_output_tokens": 900,
                    "timeout_seconds": 120,
                }},
            )
        kwargs = research_call.call_args.kwargs
        self.assertEqual(len(kwargs["queries"]), 5)
        self.assertIn("official documentation", kwargs["queries"][1])
        self.assertIn("independent research", kwargs["queries"][2])
        self.assertIn("limitations risks", kwargs["queries"][3])
        self.assertIn("recent updates", kwargs["queries"][4])
        self.assertEqual(kwargs["max_results"], 5)
        self.assertEqual(kwargs["max_pages"], 5)

    def test_research_report_saves_markdown_and_structured_status(self):
        import json
        metadata = {"topic": "test topic", "pages_attempted": 1, "pages_fetched": 1}
        markdown = "# Research report\n\nSource evidence."
        md_path, json_path = dispatch.save_research_report("AGENT-02", markdown, metadata, [{"url": "https://example.com"}])
        root = Path(self.tempdir.name)
        self.assertTrue((root / md_path).is_file())
        self.assertTrue((root / json_path).is_file())
        saved = json.loads((root / json_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["metadata"]["pages_fetched"], 1)
        self.assertEqual(saved["results"][0]["url"], "https://example.com")

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



    def test_ceo_planning_skips_research_and_uses_cpu_friendly_budget(self):
        from unittest.mock import patch
        role = dispatch.find_role("AGENT-01")
        response = {"choices": [{"message": {"content": '{"assignments":[{"agent_id":"AGENT-02","task":"Research"}]}'}}]}
        with patch.object(dispatch, "post_local_model", return_value=response) as post_model:
            result = dispatch.run_role(
                role,
                "Plan the specialist delegation",
                "",
                {"model": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1/chat/completions",
                    "model": "llama3.2:3b",
                    "max_output_tokens": 2200,
                    "timeout_seconds": 120,
                }},
                perform_research=False,
            )
        self.assertIn('"assignments"', result)
        self.assertEqual(post_model.call_args.args[2], 240)
        self.assertLessEqual(post_model.call_args.args[1]["max_tokens"], 500)

    def test_specialist_output_tokens_are_capped_for_small_local_models(self):
        from unittest.mock import patch
        role = dispatch.find_role("AGENT-09")
        response = {"choices": [{"message": {"content": "# Script\\n\\nDraft"}}]}
        with patch.object(dispatch, "post_local_model", return_value=response) as post_model:
            dispatch.run_role(
                role,
                "Write a script",
                "Earlier notes. " * 4000,
                {"model": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1/chat/completions",
                    "model": "llama3.2:3b",
                    "max_output_tokens": 2200,
                    "timeout_seconds": 120,
                }},
                perform_research=False,
            )
        body = post_model.call_args.args[1]
        self.assertLessEqual(body["max_tokens"], 1700)
        self.assertEqual(post_model.call_args.args[2], 240)
        self.assertLess(len(body["messages"][1]["content"]), 11000)

    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    dispatch.post_local_model(url, {}, 1)

class RosterTreeTests(unittest.TestCase):
    """The roster is a tree; these tests are what stop it drifting back into a list."""

    def test_every_child_has_a_parent_that_exists(self):
        roles = dispatch.roster_roles()
        by_id = {role["id"]: role for role in roles}
        children = [role for role in roles if role.get("parent")]
        self.assertTrue(children)
        for role in children:
            with self.subTest(role=role["id"]):
                self.assertIn(role["parent"], by_id)

    def test_subtree_returns_descendants_and_not_siblings(self):
        picture = dispatch.subtree({"AGENT-51"})
        self.assertIn("AGENT-23", picture)
        self.assertIn("AGENT-52", picture)
        self.assertNotIn("AGENT-09", picture)
        self.assertNotIn("AGENT-31", picture)

    def test_motion_roles_are_derived_from_the_tree(self):
        self.assertEqual(
            set(dispatch.MOTION_ROLES),
            set(dispatch.subtree(("AGENT-51", "AGENT-31"))),
        )
        self.assertIn("AGENT-21", dispatch.MOTION_ROLES)
        self.assertIn("AGENT-23", dispatch.MOTION_ROLES)

    def test_parents_get_their_sub_agents_in_the_brief(self):
        brief = dispatch.sub_agent_brief("AGENT-51")
        self.assertIn("YOUR SUB-AGENTS", brief)
        self.assertIn("AGENT-23", brief)
        self.assertIn("Kinetic Typography", brief)
        self.assertEqual(dispatch.sub_agent_brief("AGENT-26"), "")

    def test_the_brief_reaches_the_template_playbook(self):
        role = dispatch.find_role("AGENT-51")
        text = dispatch.run_role(role, "Plan the shots", "", {"model": {"enabled": False}}, perform_research=False)
        self.assertIn("YOUR SUB-AGENTS", text)
        self.assertIn("AGENT-52", text)

    def test_deleted_roles_are_gone_from_both_files(self):
        for agent_id in ("AGENT-04", "AGENT-05", "AGENT-06", "AGENT-30", "AGENT-34",
                         "AGENT-35", "AGENT-44", "AGENT-45", "AGENT-46", "AGENT-47",
                         "AGENT-48", "AGENT-49"):
            with self.subTest(role=agent_id):
                self.assertIsNone(dispatch.find_role(agent_id))
                self.assertIsNone(dispatch.find_skill(agent_id))

    def test_the_human_gate_is_a_parent_that_directs_nobody(self):
        self.assertEqual(dispatch.children_of("AGENT-50"), [])
        with self.assertRaises(ValueError):
            dispatch.ensure_executable_role(dispatch.find_role("AGENT-50"))


if __name__ == "__main__":
    unittest.main()
