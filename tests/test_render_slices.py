"""The frame driver has to survive a long film on a small machine.

A canvas renderer allocates native pixel buffers that the V8 heap never sees, so
a 20,000-frame film climbs to several gigabytes and then stops making frames.
The driver answers that by running the film in slices, one process each; these
tests pin the command it builds so a later edit cannot quietly turn slicing back
off, or slice in a way that writes the wrong frame indices.
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import render_authored_film  # noqa: E402


class SliceCommandTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._run = render_authored_film.base.run
        self._node = render_authored_film.base.resolve_node

        def fake_run(command, timeout=0, **kwargs):
            self.calls.append(list(command))

            class Result:
                returncode = 0
                stdout = '{"frames": 10}'
                stderr = ""

            return Result()

        render_authored_film.base.run = fake_run
        render_authored_film.base.resolve_node = lambda: "node"

    def tearDown(self):
        render_authored_film.base.run = self._run
        render_authored_film.base.resolve_node = self._node

    def _slice(self, frames, tmp=Path("/tmp/frames")):
        return render_authored_film.step_frames(
            Path("/tmp/film.mjs"), tmp, 1920, 1080, 30, 92, slice_frames=frames)

    def test_no_slicing_is_one_command(self):
        with self.assertRaises(RuntimeError):
            # no manifest is written by the fake, which is fine: the command list
            # is what is being checked here.
            self._slice(0)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("--from", self.calls[0])

    def test_slicing_asks_the_film_for_its_plan_first(self):
        with self.assertRaises(RuntimeError):
            self._slice(4)
        self.assertIn("--plan", self.calls[0])
        self.assertEqual(len(self.calls), 4)  # plan + 3 slices for 10 frames

    def test_every_slice_but_the_last_is_full_length(self):
        with self.assertRaises(RuntimeError):
            self._slice(4)
        slices = self.calls[1:]
        spans = []
        for command in slices:
            start = int(command[command.index("--from") + 1])
            stop = int(command[command.index("--to") + 1])
            spans.append((start, stop))
        self.assertEqual(spans, [(0, 4), (4, 8), (8, 10)])

    def test_the_slices_cover_the_film_exactly_once(self):
        with self.assertRaises(RuntimeError):
            self._slice(4)
        covered = []
        for command in self.calls[1:]:
            start = int(command[command.index("--from") + 1])
            stop = int(command[command.index("--to") + 1])
            covered.extend(range(start, stop))
        self.assertEqual(covered, list(range(10)))

    def test_a_zero_slice_size_would_loop_for_ever(self):
        """Guard the guard: slicing must be used with a positive size."""
        source = (ROOT / "tools" / "render_authored_film.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn("if not slice_frames:", source)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "step_frames"
                            for node in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()
