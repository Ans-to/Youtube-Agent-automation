"""Tests for the house timing table.

The table exists because every effect used to carry its own duration, written
where it was used, so the only way to answer "how long is a mark" was to grep for
it. A table is only better than that if it is true: if it lists a timing nothing
reads, it is documentation pretending to be a rule. These tests keep it true.

The table is JavaScript, so it is read through ``timings_cli.mjs`` rather than
copied here. A copy would be the second source of truth the table exists to
remove.
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
CLI = STUDIO / "motion" / "timings_cli.mjs"

NODE = shutil.which("node")


def read_table() -> dict:
    completed = subprocess.run(
        [NODE, str(CLI)], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    if completed.returncode != 0:
        raise AssertionError("timings_cli.mjs failed: " + completed.stderr[-1500:])
    return json.loads(completed.stdout)


@unittest.skipUnless(NODE, "node is not installed; the JavaScript table cannot be read")
class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = read_table()

    def test_every_entry_respects_its_own_ceiling(self):
        self.assertEqual(self.table["problems"], [], "a house timing breaks its ceiling")

    def test_arrival_ceiling_is_the_researched_one(self):
        # Material 3: 400 ms to enter, 200 ms to exit, 300 ms to change, and never
        # longer than 700 ms.
        self.assertAlmostEqual(self.table["arrivalMax"], 0.7)

    def test_light_ceiling_is_longer_than_arrival(self):
        self.assertGreater(self.table["lightMax"], self.table["arrivalMax"])

    def test_every_entry_describes_itself(self):
        for name, entry in self.table["entries"].items():
            with self.subTest(timing=name):
                self.assertGreater(entry["seconds"], 0)
                self.assertIn(entry["kind"], ("arrival", "light", "cycle"))
                self.assertTrue(entry["what"].strip())

    def test_every_entry_is_actually_read_by_the_renderer(self):
        # This is the test that keeps the table honest. Every name has to appear
        # as seconds('name') or houseSeconds('name') somewhere in the renderer; an
        # entry nobody reads is a duration that lies about where timing comes from.
        sources = [
            path.read_text(encoding="utf-8", errors="ignore")
            for path in STUDIO.rglob("*.mjs")
            if "node_modules" not in str(path) and path != CLI
        ]
        haystack = "\n".join(sources)
        unused = [
            name for name in self.table["entries"]
            if not re.search(r"(?:houseSeconds|seconds)\(\s*['\"]%s['\"]" % re.escape(name), haystack)
        ]
        self.assertEqual(unused, [], "house timings defined but never read")

    def test_audit_catches_an_overlong_arrival(self):
        # A positive control on the rule itself: the audit must reject a timing
        # over its ceiling, or the ceiling is decoration.
        script = (
            "import { DURATIONS, audit } from './video_studio/motion/timings.mjs';"
            "DURATIONS.transition.seconds = 1.9;"
            "process.stdout.write(JSON.stringify(audit()));"
        )
        completed = subprocess.run(
            [NODE, "--input-type=module", "-e", script],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-1500:])
        problems = json.loads(completed.stdout)
        self.assertTrue(problems, "a 1.9 s arrival was accepted")
        self.assertIn("transition", problems[0])


if __name__ == "__main__":
    unittest.main()
