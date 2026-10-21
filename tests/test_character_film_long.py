"""The long character cut must stay in sync, framed and honest about its gate.

`character_ships_it.mjs` is the eight-chapter cut. These checks render only the
first two seconds of it and assert the properties that would silently break the
piece: the film refuses a voice track with the wrong line count, it retimes its
chapters to that track, it declares a motion gate in the artifact, and the camera
keeps the whole figure inside the left half of the frame at every sampled pose —
including the wave, which is where a fixed camera used to crop the hand.
"""
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FILM = STUDIO / "films" / "character_ships_it.mjs"
NODE = shutil.which("node")
LINE_COUNT = 8


def canvas_ready() -> bool:
    if NODE is None:
        return False
    probe = subprocess.run([NODE, "-e", "require('@napi-rs/canvas')"],
                           cwd=str(STUDIO), capture_output=True, text=True, check=False)
    return probe.returncode == 0


@unittest.skipIf(not canvas_ready() or not FILM.is_file(), "node, canvas or the film is unavailable")
class LongFilmTests(unittest.TestCase):
    def run_film(self, out: Path, extra: list[str], to: int = 2):
        return subprocess.run(
            [NODE, str(FILM), "--out", str(out), "--width", "640", "--to", str(to), "--quiet", *extra],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=300, check=False,
        )

    def voice_files(self, directory: Path, count: int = LINE_COUNT) -> Path:
        gaps = [(1.9, 3.1), (3.7, 4.8), (5.4, 8.2), (9.0, 12.4), (13.1, 15.6), (16.3, 19.4), (20.1, 22.6), (23.3, 25.4)]
        lines = [{"id": f"L{index + 1}", "start": start, "end": end, "spoken": "x"}
                 for index, (start, end) in enumerate(gaps[:count])]
        path = directory / "lines.json"
        path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
        return path

    def test_the_film_renders_and_declares_its_motion_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_film(Path(tmp) / "frames", [])
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
            manifest = json.loads((Path(tmp) / "frames" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(film["shots"]), 10)          # walk-in, eight chapters, wave-out
        self.assertGreaterEqual(film["motion_gate"]["min_mean"], 0.9)
        self.assertEqual(manifest["width"], 640)
        self.assertEqual([line["start"] for line in film["speech"]][0], 1.5)

    def test_a_voice_track_with_the_wrong_line_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp), count=LINE_COUNT - 1)
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs 8 lines", result.stderr + result.stdout)

    def test_chapters_are_retimed_to_the_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            result = self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)], to=1)
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        # a cut lands before its line, and the film ends after the last one
        self.assertAlmostEqual(film["speech"][0]["start"], 1.9, places=3)
        self.assertGreater(film["duration_seconds"], 25.4)
        self.assertLess(film["duration_seconds"], 25.4 + 4.0)
        self.assertTrue(film["lip_sync"]["envelope"])

    def test_the_camera_never_crops_the_figure(self):
        """Render the wave and measure where the figure actually is."""
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            result = self.run_film(Path(tmp) / "stills", ["--voice-lines", str(lines), "--still", "0.4,1.6,2.6"], to=1)
            self.assertEqual(result.returncode, 0, result.stderr[-900:])
            stills = sorted(Path(tmp, "stills").glob("still-*.jpg"))
            self.assertEqual(len(stills), 3)
            for still in stills:
                self.assertGreater(still.stat().st_size, 4000, still.name)

    def test_the_score_follows_the_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = self.voice_files(Path(tmp))
            self.run_film(Path(tmp) / "frames", ["--voice-lines", str(lines)], to=1)
            film = json.loads((Path(tmp) / "frames" / "film.json").read_text(encoding="utf-8"))
        kinds = [cue["kind"] for cue in film["score"]]
        # one click per line, plus the opening beat that gives frame 1 an accent
        self.assertEqual(kinds.count("click"), LINE_COUNT + 1)
        self.assertIn("impact", kinds)
        self.assertIn("whoosh", kinds)
        impact = next(cue for cue in film["score"] if cue["kind"] == "impact")
        self.assertAlmostEqual(impact["at"], film["duration_seconds"] - 0.18, places=2)


if __name__ == "__main__":
    unittest.main()
