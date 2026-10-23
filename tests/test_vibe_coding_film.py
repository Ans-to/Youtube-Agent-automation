"""The tutorial film has to stay in step with its narration.

The picture is only correct if every spoken line belongs to exactly one scene, so
these checks pin the contract rather than the numbers: the film refuses a track
with the wrong line count, it lays its 17 scenes end to end without a gap or an
overlap, it retimes itself to whatever audio it is given, and it writes the
captions and the upload package data from that same timing.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FILM = STUDIO / "films" / "vibe_coding.mjs"
SCRIPT = STUDIO / "films" / "vibe_coding.voice.json"
NODE = shutil.which("node")
LINE_COUNT = 151
SCENES = 17


def canvas_ready() -> bool:
    if NODE is None:
        return False
    probe = subprocess.run([NODE, "-e", "require('@napi-rs/canvas')"],
                           cwd=str(STUDIO), capture_output=True, text=True, check=False)
    return probe.returncode == 0


LINE_SECONDS = 4.2


def fake_voice(directory: Path, count: int = LINE_COUNT) -> Path:
    """A track that is fast to make and wrong in every way except its timing.

    Spacing it at 4.2 s puts the fake film over the ten-minute floor, which is
    the property being tested; the real track is 687 s.
    """
    lines = []
    t = 2.0
    for index in range(count):
        lines.append({"id": f"L{index + 1}", "start": round(t, 3), "end": round(t + 3.6, 3),
                      "spoken": "x"})
        t += LINE_SECONDS
    path = directory / "lines.json"
    path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
    return path


@unittest.skipIf(not canvas_ready() or not FILM.is_file() or not SCRIPT.is_file(),
                 "node, canvas or the film is unavailable")
class VibeCodingFilmTests(unittest.TestCase):
    def run_film(self, out: Path, extra: list[str], to: int | None = 1):
        command = [NODE, str(FILM), "--out", str(out), "--width", "480", "--quiet", *extra]
        if to is not None:
            command += ["--to", str(to)]
        return subprocess.run(command, cwd=str(STUDIO), capture_output=True, text=True,
                              timeout=600, check=False)

    def test_the_plan_is_long_enough_to_be_a_tutorial(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = fake_voice(Path(tmp))
            plan = subprocess.run([NODE, str(FILM), "--plan", "--voice-lines", str(lines)],
                                  cwd=str(STUDIO), capture_output=True, text=True, timeout=300, check=False)
        self.assertEqual(plan.returncode, 0, plan.stderr[-800:])
        data = json.loads(plan.stdout)
        self.assertEqual(len(data["scenes"]), SCENES)
        self.assertGreaterEqual(data["duration_seconds"], 10 * 60)
        starts = [scene["start"] for scene in data["scenes"]]
        self.assertEqual(starts, sorted(starts))

    def test_a_voice_track_with_the_wrong_line_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = fake_voice(Path(tmp), count=LINE_COUNT - 1)
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the film expects 151", result.stderr + result.stdout)

    def test_scenes_tile_the_film_without_gaps_or_overlaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = fake_voice(Path(tmp))
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        scenes = film["scenes"]
        self.assertEqual(len(scenes), SCENES)
        for earlier, later in zip(scenes, scenes[1:]):
            self.assertGreaterEqual(later["start"], earlier["end"] - 0.001)
            self.assertLessEqual(later["start"] - earlier["end"], 0.05)
        self.assertGreaterEqual(film["duration_seconds"], 10 * 60)

    def test_the_film_retimes_itself_to_the_voice_it_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = fake_voice(Path(tmp))
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        # 151 lines, 4.2 s apart, starting at 2 s: the last one ends just under 634 s
        last_end = 2.0 + (LINE_COUNT - 1) * LINE_SECONDS + 3.6
        # The picture starts at frame zero even though the voice starts at 2 s.
        # The 1.45 s lead-in of empty stage was cut: it measured as a two-second
        # freeze at the start of the film, the worst place to lose a viewer.
        self.assertAlmostEqual(film["scenes"][0]["start"], 0.0, places=2)
        self.assertGreater(film["duration_seconds"], last_end)
        self.assertLess(film["duration_seconds"], last_end + 4.0)
        self.assertEqual(film["scenes"][0]["narration_lines"], 4)

    def test_it_writes_captions_and_an_upload_package_worth_using(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = fake_voice(Path(tmp))
            out = Path(tmp) / "frames"
            result = self.run_film(out, ["--voice-lines", str(lines)])
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            srt = (out / "captions.srt").read_text(encoding="utf-8")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            timeline = (out / "timeline.txt").read_text(encoding="utf-8")
        self.assertEqual(srt.count("-->"), LINE_COUNT)
        self.assertIn("00:00:02,000 --> 00:00:05,600", srt)
        # the frame count follows the voice, not a typed constant
        self.assertGreater(manifest["frame_count"], LINE_COUNT * 120)
        self.assertEqual(manifest["fps"], 30)
        self.assertIn("vibe", timeline.lower())

    def test_nothing_in_the_film_draws_a_screenshot(self):
        """The copyright rule is structural, not a review note."""
        source = FILM.read_text(encoding="utf-8")
        # No picture is ever read from disk or fetched: grain tiles are generated
        # noise, and every interface is drawn from primitives.
        for forbidden in ("loadImage", "readFileSync(path.join(HERE, '..", "http://", "https://"):
            self.assertNotIn(forbidden, source, forbidden)


if __name__ == "__main__":
    unittest.main()
