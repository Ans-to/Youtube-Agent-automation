import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_studio.audit import media


SRT = """1
00:00:01,000 --> 00:00:04,500
Hello and welcome.

2
00:00:05,000 --> 00:00:08,250
Today we build <i>something</i> real.
"""

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.500
Hello and welcome.

00:00:05.000 --> 00:00:08.250
<v Host>Today we build something real.</v>
"""


class SubtitleParsingTests(unittest.TestCase):
    def test_srt_is_parsed(self):
        cues = media.parse_subtitles(SRT)
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0].start, 1.0, places=3)
        self.assertAlmostEqual(cues[0].end, 4.5, places=3)
        self.assertEqual(cues[0].text, "Hello and welcome.")
        self.assertEqual(cues[0].source, "subtitles")

    def test_vtt_is_parsed_and_tags_are_stripped(self):
        cues = media.parse_subtitles(VTT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[1].text, "Today we build something real.")
        self.assertAlmostEqual(cues[1].start, 5.0, places=3)

    def test_garbage_is_ignored(self):
        self.assertEqual(media.parse_subtitles("no timestamps here"), [])
        self.assertEqual(media.parse_subtitles(""), [])

    def test_millisecond_padding_is_handled(self):
        # A one-digit fraction means tenths of a second, not milliseconds.
        cues = media.parse_subtitles("1\n00:00:01,5 --> 00:00:02,25\nshort stamps\n")
        self.assertAlmostEqual(cues[0].start, 1.5, places=3)
        self.assertAlmostEqual(cues[0].end, 2.25, places=3)


class CapabilityTests(unittest.TestCase):
    def test_capabilities_report_booleans_for_every_key(self):
        caps = media.capabilities()
        self.assertEqual(
            set(caps),
            {"ffmpeg", "ffprobe", "ocr", "ocr_engine", "asr", "audio_analysis",
             "vision_observations", "local_model"},
        )
        self.assertTrue(all(isinstance(value, bool) for value in caps.values()))

    def test_missing_tools_are_reported_as_false(self):
        with patch.object(media.shutil, "which", return_value=None), \
             patch.object(media, "_module_available", return_value=False):
            caps = media.capabilities()
        self.assertFalse(caps["ffmpeg"])
        self.assertFalse(caps["ocr"])
        self.assertFalse(caps["asr"])


class DegradationTests(unittest.TestCase):
    def test_collect_without_ffmpeg_returns_empty_signals_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "v.mp4"
            video.write_bytes(b"\x00" * 4096)
            with patch.object(media.shutil, "which", return_value=None):
                signals = media.collect(video)
        self.assertEqual(signals.luminance, [])
        self.assertEqual(signals.audio_rms, [])
        self.assertEqual(signals.transcript, [])
        self.assertFalse(signals.has("luminance"))
        self.assertFalse(signals.has("transcript"))

    def test_subtitles_are_used_when_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "v.mp4"
            video.write_bytes(b"\x00" * 4096)
            subs = Path(directory) / "v.srt"
            subs.write_text(SRT, encoding="utf-8")
            with patch.object(media.shutil, "which", return_value=None):
                signals = media.collect(video, subtitle_path=subs)
        self.assertEqual(len(signals.transcript), 2)
        self.assertIn("subtitles", signals.sources["transcript"])
        self.assertTrue(signals.has("transcript"))

    def test_asr_is_not_attempted_without_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "v.mp4"
            video.write_bytes(b"\x00" * 4096)
            with patch.object(media.shutil, "which", return_value=None):
                signals = media.collect(video, whisper_model="base")
        self.assertEqual(signals.transcript, [])

    def test_ocr_is_skipped_when_tesseract_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "v.mp4"
            video.write_bytes(b"\x00" * 4096)
            with patch.object(media.shutil, "which", return_value=None):
                self.assertEqual(media.read_on_screen_text(video, duration=10.0), [])

    def test_probe_returns_empty_without_ffprobe(self):
        with patch.object(media.shutil, "which", return_value=None):
            self.assertEqual(media.probe(Path("whatever.mp4")), {})


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required to generate a real media fixture")
class RealMediaTests(unittest.TestCase):
    """Runs only where FFmpeg exists, so the adapters are exercised for real."""

    def test_clip_with_a_black_gap_and_a_tone(self):
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "clip.mp4"
            subprocess.run(  # noqa: S603 - fixed argv for a test fixture
                [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=white:s=160x90:d=1",
                 "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                 "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                 "-map", "[v]", "-map", "2:a", "-shortest", str(video)],
                check=False, capture_output=True,
            )
            if not video.is_file():
                self.skipTest("FFmpeg could not synthesize the fixture")
            signals = media.collect(video, sample_fps=5.0)
            self.assertTrue(signals.luminance)
            self.assertTrue(signals.audio_rms)
            self.assertGreater(signals.duration, 0)
            dark = [value for _, value in signals.luminance]
            self.assertLess(min(dark), 0.2)


if __name__ == "__main__":
    unittest.main()
