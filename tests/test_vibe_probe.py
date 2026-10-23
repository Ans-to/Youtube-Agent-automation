"""The film's motion probe must mean exactly what the delivery check means.

Why this exists
---------------
`video_studio/films/vibe_coding.mjs` grew its own `--probe` so a scene can be
measured while it is being cut, without rendering an eleven-minute film first.
That probe is only useful if it agrees with `video_studio/repeat_frames.py`,
which runs on the delivered file and fails the render. They did not agree: the
probe counted a block as changed at 1.5 grey levels and grouped blocks 24x13,
while the delivery check uses 10 grey levels on a 32x18 grid. The film passed
its own probe and froze on YouTube anyway.

This test reads both files and fails if any of the numbers drift apart again.
The numbers are parsed from the sources rather than imported so that neither
file needs the other to run.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "video_studio" / "films" / "vibe_coding.mjs"
CHECK = ROOT / "video_studio" / "repeat_frames.py"


def _film_probe():
    """The PROBE table from the film, as plain numbers."""
    source = FILM.read_text(encoding="utf-8")
    table = re.search(r"const PROBE = \{(.*?)\};", source, re.DOTALL)
    if not table:
        raise AssertionError("vibe_coding.mjs no longer declares a PROBE table")
    body = table.group(1)
    out = {}
    for name in ("blockDelta", "stillShare", "lagSeconds", "maxStillSeconds"):
        match = re.search(rf"{name}:\s*([0-9.]+)", body)
        if not match:
            raise AssertionError(f"PROBE.{name} is missing from vibe_coding.mjs")
        out[name] = float(match.group(1))
    blocks = re.search(r"blocks:\s*\[(\d+),\s*(\d+)\]", source)
    if not blocks:
        raise AssertionError("the probe no longer reports its block grid")
    out["blocks"] = (int(blocks.group(1)), int(blocks.group(2)))
    return out


def _check_numbers():
    """The constants the delivery check enforces."""
    source = CHECK.read_text(encoding="utf-8")
    out = {}
    for name in ("BLOCK_DELTA", "STILL_SHARE", "LAG_SECONDS",
                 "DEFAULT_MAX_STILL_SECONDS"):
        match = re.search(rf"^{name}\s*=\s*([0-9.]+)", source, re.MULTILINE)
        if not match:
            raise AssertionError(f"repeat_frames.py no longer defines {name}")
        out[name] = float(match.group(1))
    bx = re.search(r"^BLOCKS_X\s*=\s*(\d+)", source, re.MULTILINE)
    by = re.search(r"^BLOCKS_Y\s*=\s*(\d+)", source, re.MULTILINE)
    out["blocks"] = (int(bx.group(1)), int(by.group(1)))
    return out


class ProbeContractTests(unittest.TestCase):
    def setUp(self):
        if not FILM.exists() or not CHECK.exists():
            self.skipTest("the film and the delivery check are both required")
        self.film = _film_probe()
        self.check = _check_numbers()

    def test_the_block_magnitude_threshold_is_the_delivery_one(self):
        self.assertEqual(self.film["blockDelta"], self.check["BLOCK_DELTA"])

    def test_the_share_of_blocks_that_must_move_is_the_delivery_one(self):
        self.assertEqual(self.film["stillShare"], self.check["STILL_SHARE"])

    def test_the_comparison_lag_is_the_delivery_one(self):
        self.assertEqual(self.film["lagSeconds"], self.check["LAG_SECONDS"])

    def test_the_longest_allowed_hold_is_the_delivery_one(self):
        self.assertEqual(self.film["maxStillSeconds"],
                         self.check["DEFAULT_MAX_STILL_SECONDS"])

    def test_the_block_grid_is_the_delivery_one(self):
        self.assertEqual(self.film["blocks"], self.check["blocks"])

    def test_the_probe_reports_where_its_definition_comes_from(self):
        source = FILM.read_text(encoding="utf-8")
        self.assertIn("video_studio/repeat_frames.py", source)


if __name__ == "__main__":
    unittest.main()
