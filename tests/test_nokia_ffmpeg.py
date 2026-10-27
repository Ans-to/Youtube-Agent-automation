"""Exercise the real FFmpeg filters, not just their log parsers."""
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe
from video_studio.nokia_audit import _stream_coverage, measure_master, probe_video
from video_studio.quality_audit import audit


@unittest.skipUnless(find_ffmpeg() and find_ffprobe(), "FFmpeg and FFprobe are required")
class RealMediaTests(unittest.TestCase):
    def render(self, path, *, faulty):
        filters = "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,3)'" if faulty else "null"
        audio = "sine=frequency=440:duration=1" if faulty else "sine=frequency=440:duration=4"
        args = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=15:duration=4",
                "-f", "lavfi", "-i", audio, "-vf", filters,
                "-af", "apad=pad_dur=3" if faulty else "volume=8dB", "-t", "4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
        subprocess.run(args, check=True, capture_output=True, timeout=60)

    def test_real_black_and_silence_reaching_eof_fail_strict_qc(self):
        with tempfile.TemporaryDirectory() as name:
            video = Path(name) / "faulty.mp4"
            self.render(video, faulty=True)
            report = audit(video, strict=True)
            self.assertFalse(report["passed"])
            self.assertGreater(report["checks"]["audio_silence"]["events"][0]["duration"], 2.8)
            self.assertGreater(report["checks"]["black_frames"]["events"][0]["duration"], 0.8)
            self.assertTrue(any("black" in warning.lower() for warning in report["warnings"]))
            self.assertTrue(any("silence" in warning.lower() for warning in report["warnings"]))

    def test_real_probe_and_ebu_master_meter_on_clean_fixture(self):
        with tempfile.TemporaryDirectory() as name:
            video = Path(name) / "clean.mp4"
            self.render(video, faulty=False)
            self.assertEqual(_stream_coverage(probe_video(video)), (4.0, 0))
            integrated, true_peak = measure_master(video)
            self.assertTrue(math.isfinite(integrated))
            self.assertTrue(math.isfinite(true_peak))
            report = audit(video, strict=True)
            self.assertTrue(report["passed"], report["warnings"])
            self.assertFalse(report["checks"]["audio_silence"]["events"])
            self.assertFalse(report["checks"]["black_frames"]["events"])


if __name__ == "__main__":
    unittest.main()
