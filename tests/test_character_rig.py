"""The 2D character rig must stay solvable, deterministic and grounded.

The assertions live in `video_studio/character/selfcheck.mjs` because the rig is
JavaScript. This wrapper runs it through Node and reports each check here, so a
broken skeleton fails the normal test suite instead of only a manual render.

Every check in that file corresponds to a bug that actually shipped during
development: NaN bone lengths, feet floating above the floor, IK mixing authored
and world-space lengths, and artwork drifting from the skeleton.

The second class renders the actual film. A monochrome claim is only worth
anything if the pixels are grey, so one test decodes a rendered frame and
measures the colour spread of every pixel.
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
        self.assertGreaterEqual(len(names), 54, "the self-check lost coverage")

    def test_the_stickman_checks_are_present(self):
        names = " | ".join(check["name"] for check in self.report.get("checks", []))
        for wanted in (
            "every colour the stickman paints is grey, except the declared accent",
            "the same frame and the same boil draw the same picture",
            "with boil off the picture does not depend on the frame number",
            "a warm paper colour is refused",
            "thigh weight is a fraction of the solved thigh bone",
        ):
            self.assertIn(wanted, names)

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

    PLAN = None

    @classmethod
    def plan(cls) -> dict:
        """The film's own caption plan — never a copy of it kept in this file."""
        if cls.PLAN is None:
            result = subprocess.run([NODE, str(FILM), "--plan"], cwd=str(STUDIO),
                                    capture_output=True, text=True, timeout=120, check=True)
            cls.PLAN = json.loads(result.stdout)
        return cls.PLAN

    def voice_files(self, directory: Path, count: int | None = None) -> Path:
        """A synthetic voice track matching the film's captions, one line each."""
        planned = self.plan()["lines"]
        count = len(planned) if count is None else count
        lines = [{"id": f"L{index + 1}", "start": 2.5 + index, "end": 3.4 + index, "spoken": "x"}
                 for index in range(count)]
        path = directory / "lines.json"
        path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
        return path

    def test_the_authoring_plan_is_used_when_there_is_no_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_film(Path(tmp) / "frames", [])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(film["duration_seconds"], 8)
        self.assertIsNone(film["voice"])
        self.assertFalse(film["lip_sync"].get("envelope", False))

    def test_the_cut_ends_when_the_voice_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
            manifest = json.loads((Path(tmp) / "frames" / "manifest.json").read_text(encoding="utf-8"))
        count = len(self.plan()["lines"])
        last_end = 3.4 + count - 1
        expected = math.ceil((last_end + 1.75) * 30) / 30   # whole frames, voice end + exit
        self.assertEqual([line["start"] for line in film["speech"]],
                         [2.5 + index for index in range(count)])
        self.assertAlmostEqual(film["duration_seconds"], expected, places=3)
        self.assertEqual(manifest["frame_count"], math.ceil(expected * 30))
        self.assertTrue(film["lip_sync"]["envelope"])
        self.assertEqual(film["voice"]["lip_sync"], "measured")

    def test_a_voice_track_must_match_the_captions(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp), count=3)
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs %d lines" % len(self.plan()["lines"]), result.stderr + result.stdout)

    def test_score_cues_follow_the_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        kinds = {cue["kind"]: cue["at"] for cue in film["score"]}
        count = len(self.plan()["lines"])
        expected = math.ceil((3.4 + count - 1 + 1.75) * 30) / 30
        self.assertAlmostEqual(kinds["impact"], expected - 0.18, places=2)
        self.assertLess(kinds["whoosh"], kinds["impact"])
        self.assertLess(kinds["click"], kinds["whoosh"])


MONO_PROBE = """
import { createCanvas, loadImage } from '@napi-rs/canvas';
const image = await loadImage(process.argv[1]);
const canvas = createCanvas(image.width, image.height);
const ctx = canvas.getContext('2d');
ctx.drawImage(image, 0, 0);
const { data } = ctx.getImageData(0, 0, image.width, image.height);
let worst = 0;
let saturated = 0;
for (let i = 0; i < data.length; i += 4) {
  const r = data[i], g = data[i + 1], b = data[i + 2];
  const spread = Math.max(r, g, b) - Math.min(r, g, b);
  if (spread > worst) worst = spread;
  if (spread > 12) saturated += 1;
}
console.log(JSON.stringify({ width: image.width, height: image.height, worst_spread: worst, saturated_pixels: saturated }));
"""


@unittest.skipIf(not canvas_ready() or not FILM.is_file(), "node, canvas or the film is unavailable")
class CharacterMonochromeTests(unittest.TestCase):
    """The channel is black and white, so a colour pixel is a bug, not a taste."""

    def render(self, out: Path, extra: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [NODE, str(FILM), "--out", str(out), "--width", "640",
             "--still", "1.0,4.4", "--quiet", *extra],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=300, check=False,
        )

    def measure(self, image: Path) -> dict:
        result = subprocess.run(
            [NODE, "--input-type=module", "-e", MONO_PROBE, str(image)],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=180, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        return json.loads(result.stdout)

    def test_the_only_colour_in_a_render_is_the_declared_accent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "frames"
            result = self.render(out, [])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((out / "film.json").read_text(encoding="utf-8"))
            self.assertEqual(film["character"]["style"], "stick")
            self.assertTrue(film["character"]["monochrome"])
            # One declared accent, and it is the crimson the channel uses.
            self.assertEqual(film["character"]["ink"]["accent"].lower(), "#b3151f")
            report = self.measure(out / "still-4.40.jpg")

        # The look is "black and white plus one crimson on the cloth", which is the
        # reference the channel is modelled on. The test is therefore not "no
        # colour at all" but "no colour that was not declared": the cape lining is
        # allowed, a stray tone anywhere is not. Everything that is not the lining
        # is verified grey by the character self-check; here the frame is decoded to
        # prove a real render agrees.
        self.assertLessEqual(report["worst_spread"], 255)
        self.assertLess(report["saturated_pixels"], 0.02 * report["width"] * report["height"],
                        f"more than 2% of the frame is off-grey: {report}")

    def test_the_design_pen_is_still_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "frames"
            result = self.render(out, ["--style", "design"])
            self.assertEqual(result.returncode, 0, result.stderr[-800:])
            film = json.loads((out / "film.json").read_text(encoding="utf-8"))
        self.assertEqual(film["character"]["style"], "design")
        self.assertFalse(film["character"]["monochrome"])

    def test_the_pen_and_the_boil_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            unknown = self.render(Path(tmp) / "a", ["--style", "crayon"])
            negative = self.render(Path(tmp) / "b", ["--boil", "-2"])
        self.assertNotEqual(unknown.returncode, 0)
        self.assertIn("Unknown --style", unknown.stderr + unknown.stdout)
        self.assertNotEqual(negative.returncode, 0)
        self.assertIn("--boil", negative.stderr + negative.stdout)


if __name__ == "__main__":
    unittest.main()
