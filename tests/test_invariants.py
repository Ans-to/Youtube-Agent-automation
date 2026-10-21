import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.check_invariants import (
    RULE_TO_INVARIANT,
    Finding,
    main,
    run_checks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_fixture(root: Path) -> None:
    """Create a minimal clean repository that satisfies every enforced rule."""
    rules = "\n".join(f"- {rule}" for rule in RULE_TO_INVARIANT)
    write(root, "docs/NORTH_STAR.md", "# Rules\n\nP1 P2 P3 P4 P5 P6 P7 P8\n\n" + rules + "\n")
    write(root, "config.example.json", json.dumps({
        "model": {
            "enabled": False,
            "base_url": "http://127.0.0.1:8080/v1/chat/completions",
        }
    }, indent=2))
    write(root, "agents/orchestrate.py", (
        "# generation_mode and deterministic_template labelling live here.\n"
        "MODE = 'explicit_template_demo'\n"
    ))
    write(root, "video_studio/production.py", (
        "# --render-template exists for the offline demo.\n"
        "REFUSAL = 'No local model is enabled'\n"
    ))
    write(root, "tools/tool_runtime.py", (
        "from path_utils import safe_relative_path, is_within\n"
        "allow_exec = False\n"
    ))


def violations(findings: list[Finding], rule: str) -> list[Finding]:
    return [finding for finding in findings if finding.rule == rule]


class InvariantFixtureTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        build_fixture(self.root)

    def tearDown(self):
        self._directory.cleanup()

    def test_clean_fixture_passes(self):
        self.assertEqual(run_checks(self.root), [])

    def test_hosted_ai_import_is_rejected(self):
        write(self.root, "app.py", "import openai\n")
        findings = violations(run_checks(self.root), "NO_PAID_SDK")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "app.py")
        self.assertEqual(findings[0].line, 1)

    def test_hosted_ai_requirement_and_package_are_rejected(self):
        write(self.root, "requirements.txt", "requests\nopenai>=1.0\n")
        write(self.root, "package.json", json.dumps({"dependencies": {"@anthropic-ai/sdk": "^1"}}))
        findings = violations(run_checks(self.root), "NO_PAID_SDK")
        self.assertEqual({finding.path for finding in findings}, {"requirements.txt", "package.json"})

    def test_billable_endpoint_literal_is_rejected(self):
        write(self.root, "client.py", 'URL = "https://api.openai.com/v1/chat/completions"\n')
        findings = violations(run_checks(self.root), "NO_BILLABLE_ENDPOINT")
        self.assertEqual([finding.path for finding in findings], ["client.py"])
        self.assertIn("api.openai.com", findings[0].message)

    def test_credential_literals_are_rejected_unless_suppressed(self):
        write(self.root, "leak.py", 'KEY = "sk-' + "a" * 32 + '"\n')
        findings = violations(run_checks(self.root), "NO_SECRET_LITERAL")
        self.assertEqual(len(findings), 1)
        self.assertNotIn("a" * 32, findings[0].message)

        write(self.root, "leak.py", 'KEY = "sk-' + "a" * 32 + '"  # invariant-allow: NO_SECRET_LITERAL test fixture\n')
        self.assertEqual(violations(run_checks(self.root), "NO_SECRET_LITERAL"), [])

    def test_non_loopback_or_enabled_model_config_is_rejected(self):
        write(self.root, "config.example.json", json.dumps({
            "model": {"enabled": False, "base_url": "https://api.example.com/v1"}
        }))
        self.assertTrue(violations(run_checks(self.root), "LOOPBACK_MODEL_ONLY"))

        write(self.root, "config.example.json", json.dumps({
            "model": {"enabled": True, "base_url": "http://127.0.0.1:8080/v1"}
        }))
        findings = violations(run_checks(self.root), "LOOPBACK_MODEL_ONLY")
        self.assertEqual(len(findings), 1)
        self.assertIn("model.enabled", findings[0].message)

    def test_shell_string_execution_is_rejected(self):
        write(self.root, "runner.py", "import subprocess\nsubprocess.run('ls', shell=True)\n")
        findings = violations(run_checks(self.root), "SAFE_SUBPROCESS")
        self.assertEqual([finding.line for finding in findings], [2])

    def test_missing_safety_artifacts_are_reported(self):
        (self.root / "tools" / "tool_runtime.py").unlink()
        write(self.root, "agents/orchestrate.py", "MODE = 'unknown'\n")
        (self.root / "docs" / "NORTH_STAR.md").unlink()

        rules = {finding.rule for finding in run_checks(self.root)}
        self.assertIn("TOOL_SANDBOX_PRESENT", rules)
        self.assertIn("HONEST_DEGRADATION", rules)
        self.assertIn("INVARIANT_REGISTRY", rules)

    def test_undocumented_invariant_is_reported(self):
        write(self.root, "docs/NORTH_STAR.md", "P1 P2 P3 P4 P6 P7 P8\n" + "\n".join(RULE_TO_INVARIANT))
        findings = violations(run_checks(self.root), "INVARIANT_REGISTRY")
        self.assertEqual(len(findings), 1)
        self.assertIn("P5", findings[0].message)

    def test_cli_reports_status_and_exit_code(self):
        clean_output = io.StringIO()
        with contextlib.redirect_stdout(clean_output):
            self.assertEqual(main(["--root", str(self.root)]), 0)
        self.assertIn("PASS", clean_output.getvalue())

        write(self.root, "bad.py", "import anthropic\n")
        failing_output = io.StringIO()
        with contextlib.redirect_stdout(failing_output):
            self.assertEqual(main(["--root", str(self.root), "--json"]), 1)
        report = json.loads(failing_output.getvalue())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["violations"][0]["rule"], "NO_PAID_SDK")
        self.assertEqual(report["violations"][0]["invariant"], "P1")


class RepositoryInvariantTests(unittest.TestCase):
    def test_this_repository_satisfies_its_own_rules(self):
        findings = run_checks(REPO_ROOT)
        self.assertEqual(
            findings, [],
            "North Star violations:\n" + "\n".join(
                f"{finding.rule} {finding.path}:{finding.line} {finding.message}" for finding in findings
            ),
        )


if __name__ == "__main__":
    unittest.main()
