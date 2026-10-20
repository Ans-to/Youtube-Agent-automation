import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import adhd_style
import dispatch


class ADHDStyleIntegrationTests(unittest.TestCase):
    def test_canonical_upstream_skill_is_bundled(self):
        self.assertTrue(adhd_style.canonical_skill_exists())
        text = adhd_style.SKILL_PATH.read_text(encoding="utf-8")
        for marker in ("Lead with the next action", "Number multi-step tasks", "Matter-of-fact tone for errors"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_specialist_model_prompt_receives_runtime_rules(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(dispatch, "ROOT", Path(tempdir)), \\
                 patch.object(dispatch, "collect_web_research", None), \\
                 patch.object(dispatch, "post_local_model", return_value={"choices": [{"message": {"content": "ok"}}]}) as call:
                result = dispatch.run_role(
                    {"id": "AGENT-02", "name": "Test specialist", "mission": "Test mission"},
                    "Give a concise task status.", "",
                    {"model": {"enabled": True, "base_url": "http://127.0.0.1:8080/v1/chat/completions", "model": "test", "max_output_tokens": 500}},
                )
                self.assertEqual(result, "ok")
                system_prompt = call.call_args.args[1]["messages"][0]["content"]
                self.assertIn("ADHD-FRIENDLY OUTPUT STYLE", system_prompt)
                self.assertIn("Lead with the answer or the next concrete action", system_prompt)

    def test_runtime_rules_are_compact_and_actionable(self):
        rules = adhd_style.runtime_instructions()
        self.assertIn("Lead with the answer or the next concrete action", rules)
        self.assertIn("confirm before destructive actions", rules)
        self.assertIn("Preserve the requested artifact's format", rules)
        self.assertLess(len(rules), 2500)


if __name__ == "__main__":
    unittest.main()
