"""The 2D character rig must stay solvable, deterministic and grounded.

The assertions live in `video_studio/character/selfcheck.mjs` because the rig is
JavaScript. This wrapper runs it through Node and reports each check here, so a
broken skeleton fails the normal test suite instead of only a manual render.

Every check in that file corresponds to a bug that actually shipped during
development: NaN bone lengths, feet floating above the floor, IK mixing authored
and world-space lengths, and artwork drifting from the skeleton.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELFCHECK = ROOT / "video_studio" / "character" / "selfcheck.mjs"
NODE = shutil.which("node")


@unittest.skipIf(NODE is None or not SELFCHECK.is_file(), "node or the character rig is unavailable")
class CharacterRigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [NODE, str(SELFCHECK)],
            cwd=str(ROOT / "video_studio"),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        cls.result = result
        try:
            cls.report = json.loads(result.stdout)
        except json.JSONDecodeError:
            cls.report = {"ok": False, "checks": [], "failures": [result.stderr[-500:]]}

    def test_selfcheck_reports_every_check(self):
        names = [check["name"] for check in self.report.get("checks", [])]
        self.assertTrue(names, "the rig self-check produced no checks")
        self.assertGreaterEqual(len(names), 10, "the self-check lost coverage")

    def test_no_check_failed(self):
        failures = self.report.get("failures") or []
        self.assertEqual(failures, [], "character rig failures: " + "; ".join(failures))

    def test_each_check_reports_a_success_value(self):
        for check in self.report.get("checks", []):
            self.assertIn("ok", check, check.get("name"))
            self.assertIn("detail", check, check.get("name"))

    def test_process_exit_code_matches_the_verdict(self):
        expected = 0 if self.report.get("ok") else 1
        self.assertEqual(self.result.returncode, expected)


if __name__ == "__main__":
    unittest.main()
