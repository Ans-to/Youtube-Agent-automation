"""A 4K master has to survive a small machine.

Encoding 3840x2160 in one x264 pass is killed on a 4 GB box: the driver sees exit
137 with an empty stderr, so it cannot tell "out of memory" from "bad argument".
The segmented path exists for that case. These tests pin the planner (no frame is
lost or duplicated) and the chunked encode itself against FFmpeg when it is
installed, so the fallback cannot rot silently.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import render_authored_film as driver  # noqa: E402
import render_motion_film as base  # noqa: E402


class SegmentPlanTests(unittest.TestCase):
    def test_every_frame_is_covered_once_and_in_order(self):
        for total, segments in ((954, 6), (954, 1), (100, 3), (7, 7), (5, 9)):
            plan = driver.segment_plan(total, segments)
            covered = []
            for start, count in plan:
                self.assertGreater(count, 0)
                covered.extend(range(start, start + count))
            self.assertEqual(covered, list(range(total)), (total, segments))

    def test_the_plan_never_asks_for_more_parts_than_frames(self):
        self.assertEqual(len(driver.segment_plan(3, 99)), 3)
        self.assertEqual(driver.segment_plan(3, 1), [(0, 3)])

    def test_the_contact_sheet_is_filled_whatever_the_length(self):
        # 10 tiles over the duration: short films get a higher rate, long ones a
        # lower one, and the frame count always matches the tile count.
        for duration, tiles in ((12.0, 10), (60.0, 10), (500.0, 10)):
            fps = driver.contact_sheet_fps(duration)
            self.assertAlmostEqual(fps * duration, tiles, delta=0.001)
        self.assertGreater(driver.contact_sheet_fps(3.0), driver.contact_sheet_fps(60.0))
        # Very long films hit the floor; the tile filter then takes the first ten
        # frames of the sampled stream, so over-sampling is harmless.
        self.assertEqual(driver.contact_sheet_fps(1e6), 0.02)

    def test_an_empty_film_is_an_error(self):
        with self.assertRaises(ValueError):
            driver.segment_plan(0, 4)


class SegmentPlanFfmpegTests(unittest.TestCase):
    """Really encode two chunks and concat them, to prove the argv is valid."""

    def setUp(self):
        try:
            self.ffmpeg, _ = base.resolve_ffmpeg()
        except base.DependencyMissing:
            self.skipTest("ffmpeg is not installed")
        if shutil.which("node") is None:
            self.skipTest("node is not installed")
        if not base.canvas_module_available():
            self.skipTest("the canvas module is not installed")

    def test_a_chunked_encode_matches_the_frame_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            frames = tmp / "frames"
            result = subprocess.run(
                [base.resolve_node(), str(ROOT / "video_studio" / "films" / "character_ships_it.mjs"),
                 "--out", str(frames), "--width", "320", "--to", "36", "--quiet"],
                cwd=str(ROOT / "video_studio"), capture_output=True, text=True, check=False, timeout=300,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-600:])
            manifest = json.loads((frames / "manifest.json").read_text(encoding="utf-8"))
            rendered = len(list(frames.glob("frame-*.jpg")))
            self.assertEqual(rendered, 36)
            audio = tmp / "silence.wav"
            subprocess.run(  # a real audio track, so the mux path is exercised
                [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "anullsrc=r=48000:cl=mono", "-t", "1.2", str(audio)],
                capture_output=True, text=True, check=False,
            )
            output = tmp / "cut.mp4"
            info = driver.encode_segmented(
                frames, audio, output, self.ffmpeg, fps=manifest["fps"], crf=30,
                preset="ultrafast", audio_bitrate="96k", total_frames=rendered,
                segments=3, work_dir=tmp / "segments",
                extra=["-threads", "1"],
            )
            self.assertTrue(output.is_file())
            self.assertEqual(info["mode"], "segmented")
            self.assertEqual(info["segments"], 3)
            self.assertGreater(info["bytes"], 0)
            # the parts are cleaned up after a successful concat
            self.assertEqual(list((tmp / "segments").glob("part-*.mp4")), [])

            _, ffprobe = base.resolve_ffmpeg()
            if not ffprobe:
                return
            probe = subprocess.run(  # noqa: S603 - fixed argv in a test
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)],
                capture_output=True, text=True, check=False,
            )
            duration = float(json.loads(probe.stdout)["format"]["duration"])
            self.assertAlmostEqual(duration, 36 / manifest["fps"], delta=0.25)


if __name__ == "__main__":
    unittest.main()
