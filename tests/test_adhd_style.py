import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import adhd_style


class ADHDStyleIntegrationTests(unittest.TestCase):
    def test_canonical_upstream_skill_is_bundled(self):
        self.assertTrue(adhd_style.canonical_skill_exists())
        text = adhd_style.SKILL_PATH.read_text(encoding="utf-8")
        for marker in ("Lead with the next action", "Number multi-step tasks", "Matter-of-fact tone for errors"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_runtime_rules_are_compact_and_actionable(self):
        rules = adhd_style.runtime_instructions()
        self.assertIn("Lead with the answer or the next concrete action", rules)
        self.assertIn("confirm before destructive actions", rules)
        self.assertIn("Preserve the requested artifact's format", rules)
        self.assertLess(len(rules), 2500)


if __name__ == "__main__":
    unittest.main()
