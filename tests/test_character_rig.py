"""The 2D character rig must stay solvable, deterministic and grounded.

The assertions live in `video_studio/character/selfcheck.mjs` because the rig is
JavaScript. This wrapper runs it through Node and reports each check here, so a
broken skeleton fails the normal test suite instead of only a manual render.

Every check in that file corresponds to a bug that actually shipped during
development: NaN bone lengths, feet floating above the floor, IK mixing authored
and world-space lengths, and artwork drifting from the skeleton.
"""
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELFCHECK = ROOT / "video_studio" / "character" / "selfcheck.mjs"
FILM = ROOT / "video_studio" / "films" / "character_speaks.mjs"
STUDIO = ROOT / "video_studio"
NODE = shutil.which("node")


def canvas_ready() -> bool:
    if NODE is None:
        return False
    probe = subprocess.run([NODE, "-e", "require('@napi-rs/canvas')"],
                           cwd=str(STUDIO), capture_output=True, text=True, check=False)
    return probe.returncode == 0


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


@unittest.skipIf(not canvas_ready() or not FILM.is_file(), "node, canvas or the film is unavailable")
class CharacterFilmTimingTests(unittest.TestCase):
    """The picture must follow the voice, not the other way round."""

    def run_film(self, out: Path, extra: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [NODE, str(FILM), "--out", str(out), "--width", "640", "--to", "2", "--quiet", *extra],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=300, check=False,
        )

    def voice_files(self, directory: Path, count: int = 4) -> Path:
        spans = [(2.5, 3.4), (3.9, 5.1), (5.6, 6.6), (7.0, 8.1)][:count]
        lines = [{"id": f"L{index + 1}", "start": start, "end": end, "spoken": "x"}
                 for index, (start, end) in enumerate(spans)]
        path = directory / "lines.json"
        path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
        return path

    def test_the_authoring_plan_is_used_when_there_is_no_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_film(Path(tmp) / "frames", [])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        self.assertEqual(film["duration_seconds"], 12)
        self.assertIsNone(film["voice"])
        self.assertFalse(film["lip_sync"].get("envelope", False))

    def test_the_cut_ends_when_the_voice_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
            manifest = json.loads((Path(tmp) / "frames" / "manifest.json").read_text(encoding="utf-8"))
        expected = math.ceil((8.1 + 1.75) * 30) / 30   # whole frames, voice end + exit
        self.assertEqual([line["start"] for line in film["speech"]], [2.5, 3.9, 5.6, 7.0])
        self.assertAlmostEqual(film["duration_seconds"], expected, places=3)
        self.assertEqual(manifest["frame_count"], math.ceil(expected * 30))
        self.assertTrue(film["lip_sync"]["envelope"])
        self.assertEqual(film["voice"]["lip_sync"], "measured")

    def test_a_voice_track_must_match_the_captions(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp), count=3)
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs 4 lines", result.stderr + result.stdout)

    def test_score_cues_follow_the_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        kinds = {cue["kind"]: cue["at"] for cue in film["score"]}
        expected = math.ceil((8.1 + 1.75) * 30) / 30
        self.assertAlmostEqual(kinds["impact"], expected - 0.18, places=2)
        self.assertLess(kinds["whoosh"], kinds["impact"])
        self.assertLess(kinds["click"], kinds["whoosh"])


if __name__ == "__main__":
    unittest.main()
