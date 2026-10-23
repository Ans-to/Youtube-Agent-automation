"""The structure checker must fail on the problems it claims to catch.

A checker that always passes is decoration. Each test builds a tiny repository
that contains exactly one violation and asserts the matching rule fires - and
that a clean tree produces nothing.

The rules are the ones that rot silently: an import in the wrong direction, a
run flag creeping back into a module, a helper copied instead of shared, a new
script dropped in the repository root.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools import check_structure


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def clean_tree(root: Path) -> None:
    write(root, "app/services/thing.py", "def build(x):\n    return x + 1\n")
    write(root, "ui/views/page.py", "from app.services.thing import build\n\nVALUE = build(1)\n")
    write(root, "tools/helper.py", "def add(a, b):\n    return a + b\n")


def rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


class StructureRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        clean_tree(self.root)

    def test_a_clean_tree_has_no_findings(self):
        self.assertEqual(check_structure.run_checks(self.root), [])

    def test_a_windows_style_path_is_still_checked(self):
        # The layer rule used to compare with ``startswith("app/")``, so on
        # Windows a real violation arrived as ``app\\services\\bad.py`` and
        # passed. The rule must not depend on the separator it was handed.
        import ast

        tree = ast.parse("from ui.views.page import VALUE\n")
        findings = check_structure.check_layer("app\\services\\bad.py", tree)
        self.assertEqual([f.rule for f in findings], ["S1"])
        self.assertEqual(findings[0].path, "app/services/bad.py")

    def test_reported_paths_use_forward_slashes_on_every_platform(self):
        write(self.root, "app/services/bad.py", "from ui.views.page import VALUE\n")
        findings = check_structure.run_checks(self.root)
        self.assertTrue(findings)
        for finding in findings:
            with self.subTest(path=finding.path):
                self.assertNotIn("\\", finding.path)

    def test_layer_violation_app_importing_the_ui(self):
        write(self.root, "app/services/bad.py", "from ui.views.page import VALUE\n")
        findings = check_structure.run_checks(self.root)
        self.assertIn("S1", rules(findings))
        self.assertEqual([f.path for f in findings if f.rule == "S1"], ["app/services/bad.py"])

    def test_ui_importing_app_is_allowed(self):
        write(self.root, "ui/views/other.py", "from app.services.thing import build\n")
        self.assertNotIn("S1", rules(check_structure.run_checks(self.root)))

    def test_run_flags_at_module_scope_are_caught(self):
        write(self.root, "ui/views/flags.py", "RUNNING = False\nVIDEO_RUNNING = False\n")
        findings = [f for f in check_structure.run_checks(self.root) if f.rule == "S2"]
        self.assertEqual(len(findings), 2)

    def test_a_constant_named_like_a_flag_is_not_a_flag(self):
        write(self.root, "app/services/limits.py", "MAX_CYCLES = 100\n")
        self.assertNotIn("S2", rules(check_structure.run_checks(self.root)))

    def test_copied_function_bodies_are_reported(self):
        body = "".join("    value_%d = %d\n" % (n, n) for n in range(9)) + "    return value_0\n"
        write(self.root, "tools/one.py", "def compute(a):\n" + body)
        write(self.root, "tools/two.py", "def compute(a):\n" + body)
        findings = [f for f in check_structure.run_checks(self.root) if f.rule == "S3"]
        self.assertEqual(len(findings), 1)
        # Reported with forward slashes on every platform, so the message can be
        # pasted into a link or a review comment without translation.
        self.assertEqual(findings[0].path, "tools/two.py")
        self.assertIn("tools/one.py", findings[0].message)

    def test_a_short_repeated_helper_is_not_reported(self):
        write(self.root, "tools/three.py", "def small(a):\n    return a\n")
        write(self.root, "tools/four.py", "def small(a):\n    return a\n")
        self.assertNotIn("S3", rules(check_structure.run_checks(self.root)))

    def test_naming_violations(self):
        write(self.root, "app/services/BadName.py", (
            "class bad_class:\n"
            "    pass\n"
            "\n"
            "def ComputeThing(a):\n"
            "    return a\n"
        ))
        findings = [f.message for f in check_structure.run_checks(self.root) if f.rule == "S4"]
        self.assertTrue(any("not snake_case" in message for message in findings))
        self.assertTrue(any("not PascalCase" in message for message in findings))

    def test_a_private_helper_name_is_allowed(self):
        write(self.root, "app/services/priv.py", "def _build(a):\n    return a\n")
        self.assertNotIn("S4", rules(check_structure.run_checks(self.root)))

    def test_a_new_root_level_script_is_reported(self):
        write(self.root, "scratch.py", "print('hi')\n")
        findings = [f for f in check_structure.run_checks(self.root) if f.rule == "S5"]
        self.assertEqual([f.path for f in findings], ["scratch.py"])

    def test_an_entry_point_over_budget_is_reported(self):
        write(self.root, "dashboard.py", "\n".join("x = %d" % n for n in range(320)) + "\n")
        findings = [f for f in check_structure.run_checks(self.root) if f.rule == "S6"]
        self.assertEqual(len(findings), 1)
        self.assertIn("320 lines", findings[0].message)

    def test_the_real_repository_passes(self):
        root = Path(__file__).resolve().parents[1]
        findings = check_structure.run_checks(root)
        self.assertEqual(findings, [], "\n".join(str(f) for f in findings))

    def test_cli_returns_nonzero_and_json_on_findings(self):
        write(self.root, "scratch.py", "print('hi')\n")
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = check_structure.main(["--json", "--root", str(self.root)])
        self.assertEqual(code, 1)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["passed"])
        self.assertGreaterEqual(payload["count"], 1)


if __name__ == "__main__":
    unittest.main()
