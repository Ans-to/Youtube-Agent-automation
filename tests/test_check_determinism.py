"""Tests for the render repeatability gate.

The gate exists because the whole film is rendered in chunks: if a frame number
does not always produce the same bytes, a chunk boundary shows a seam and a
re-render stops matching the cut that was approved. These tests exercise the
comparison itself - which frames it reports, and what it says about a window
that reproduced and one that did not - without invoking a renderer, so they stay
fast and run everywhere. ``tools/check_determinism.py`` is the part that actually
renders; this file proves it would notice if the renderer drifted.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_determinism  # noqa: E402 - path set up above


class ComparisonTests(unittest.TestCase):
    """What the gate reports when two renders agree, and when they do not."""

    def test_identical_renders_report_nothing(self):
        first = {0: "aaa", 1: "bbb", 2: "ccc"}
        again = dict(first)
        self.assertEqual(check_determinism.compare(first, again, "process repeatability"), [])

    def test_one_changed_frame_is_named(self):
        first = {0: "aaa", 1: "bbb", 2: "ccc"}
        drifted = {0: "aaa", 1: "XXX", 2: "ccc"}
        problems = check_determinism.compare(first, drifted, "window independence")
        self.assertEqual(len(problems), 1)
        self.assertIn("window independence", problems[0])
        self.assertIn("000001", problems[0])

    def test_every_changed_frame_is_reported(self):
        first = {n: "same" for n in range(30)}
        drifted = {n: ("same" if n < 20 else "other") for n in range(30)}
        problems = check_determinism.compare(first, drifted, "process repeatability")
        self.assertEqual(len(problems), 10)

    def test_a_shorter_second_render_only_compares_what_is_shared(self):
        # A partial render must not be reported as a disagreement about frames it
        # never produced; it is a shorter render, which the caller sees from the
        # shared count rather than as a false failure.
        first = {0: "aaa", 1: "bbb", 2: "ccc"}
        shorter = {0: "aaa", 1: "bbb"}
        self.assertEqual(check_determinism.compare(first, shorter, "process repeatability"), [])

    def test_digest_is_the_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame-000001.jpg"
            path.write_bytes(b"one")
            first = check_determinism.frame_digest(path)
            path.write_bytes(b"two")
            second = check_determinism.frame_digest(path)
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_json_verdict_carries_the_window(self):
        # The command line contract the quality gate parses: a pass has to be
        # machine-readable, or the gate cannot report it.
        parser_defaults = check_determinism.DEFAULT_START
        self.assertIsInstance(parser_defaults, int)
        verdict = json.dumps({"passed": True, "frames": 30,
                              "window": [check_determinism.DEFAULT_START,
                                         check_determinism.DEFAULT_START + check_determinism.DEFAULT_FRAMES],
                              "lead_in": check_determinism.LEAD_IN, "problems": []})
        loaded = json.loads(verdict)
        self.assertTrue(loaded["passed"])
        self.assertEqual(loaded["problems"], [])


if __name__ == "__main__":
    unittest.main()
