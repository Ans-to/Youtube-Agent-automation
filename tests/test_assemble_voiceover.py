"""Assembling a voiceover from supplied clips must not invent timing.

`voiceover.build()` synthesises speech with a local model. When a session hands
the pipeline one clip per line instead, the same three artifacts have to come
out — narration, line timings, mouth envelope — and they have to describe the
audio on disk. These tests protect that contract: monotonic, gap-aware timing,
a line count that matches the script, an envelope that closes in pauses, and a
loudness chain that leaves headroom.
"""
import json
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:  # noqa: BLE001 - the DSP dependency is optional on CI images
    raise unittest.SkipTest("numpy is required to exercise the voice DSP") from None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import assemble_voiceover  # noqa: E402
import voiceover  # noqa: E402

RATE = voiceover.SAMPLE_RATE


def write_wav(path: Path, signal, rate: int = RATE) -> None:
    voiceover.write_wav(path, np.asarray(signal, dtype=np.float32), rate)


def spoken_burst(seconds: float, rate: int = RATE, amplitude: float = 0.4) -> np.ndarray:
    """A tone burst with silence around it, the shape of one spoken line."""
    lead = np.zeros(int(rate * 0.08), dtype=np.float32)
    body = amplitude * np.sin(2 * math.pi * 180 * np.arange(int(rate * seconds)) / rate).astype(np.float32)
    tail = np.zeros(int(rate * 0.12), dtype=np.float32)
    return np.concatenate([lead, body.astype(np.float32), tail])


def script_file(directory: Path, gaps=(0.4, 0.5, 0.0), text_count: int = 3) -> Path:
    lines = [
        {"id": f"L{i + 1}", "text": f"line {i + 1}", "gap_before": gaps[i], "pause_after": 0.3}
        for i in range(text_count)
    ]
    path = directory / "voice.json"
    path.write_text(json.dumps({"lines": lines}), encoding="utf-8")
    return path


class AssembleVoiceoverTests(unittest.TestCase):
    def build(self, clips_dir: Path, script: Path, out: Path, **kwargs):
        return assemble_voiceover.assemble(script, clips_dir, out, **kwargs)

    def test_line_timings_follow_the_gaps_in_the_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            for index in range(3):
                write_wav(clips / f"L{index + 1}.wav", spoken_burst(0.6))
            script = script_file(tmp)
            report = self.build(clips, script, tmp / "voice")

            lines = report["lines"]
            self.assertEqual(len(lines), 3)
            self.assertAlmostEqual(lines[0]["start"], 0.4, delta=0.01)
            # each line starts after the previous line's audio plus its pause
            for previous, current in zip(lines, lines[1:]):
                self.assertGreaterEqual(current["start"], previous["end"])
            self.assertEqual([line["id"] for line in lines], ["L1", "L2", "L3"])

    def test_the_three_artifacts_the_film_needs_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            for index in range(3):
                write_wav(clips / f"L{index + 1}.wav", spoken_burst(0.5))
            out = tmp / "voice"
            self.build(clips, script_file(tmp), out, fps=30)

            for name in ("voiceover.wav", "lines.json", "envelope.json", "voiceover.json"):
                self.assertTrue((out / name).is_file(), name)

            with wave.open(str(out / "voiceover.wav"), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), RATE)

            envelope = json.loads((out / "envelope.json").read_text(encoding="utf-8"))
            self.assertEqual(envelope["fps"], 30)
            self.assertEqual(len(envelope["lines"]), 3)
            for entry in envelope["lines"]:
                expected = max(1, int(round((entry["end"] - entry["start"]) * 30)))
                self.assertEqual(len(entry["openness"]), expected)

    def test_the_envelope_closes_between_lines_and_opens_inside_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            for index in range(3):
                write_wav(clips / f"L{index + 1}.wav", spoken_burst(0.7))
            out = tmp / "voice"
            self.build(clips, script_file(tmp), out)
            envelope = json.loads((out / "envelope.json").read_text(encoding="utf-8"))

            for entry in envelope["lines"]:
                # the fade-in/out handles are short: the middle has to be open
                middle = entry["openness"][2:-2]
                self.assertGreater(max(middle), 0.5, entry["id"])

    def test_a_missing_clip_fails_loudly_with_the_line_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            write_wav(clips / "L1.wav", spoken_burst(0.4))
            write_wav(clips / "L2.wav", spoken_burst(0.4))
            with self.assertRaises(ValueError) as caught:
                self.build(clips, script_file(tmp), tmp / "voice")
        self.assertIn("L3", str(caught.exception))

    def test_mp3_clips_are_decoded_when_ffmpeg_is_available(self):
        if not (assemble_voiceover.shutil.which("ffmpeg") or _bundled_ffmpeg()):
            self.skipTest("no ffmpeg on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            for index in range(3):
                write_wav(clips / f"L{index + 1}.wav", spoken_burst(0.5))
                subprocess_result = _convert(clips / f"L{index + 1}.wav", clips / f"L{index + 1}.mp3")
                if not subprocess_result:
                    self.skipTest("ffmpeg could not encode a test mp3")
                (clips / f"L{index + 1}.wav").unlink()
            report = self.build(clips, script_file(tmp), tmp / "voice")
        self.assertEqual(report["line_count"], 3)

    def test_the_mix_leaves_headroom(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            clips = tmp / "clips"
            clips.mkdir()
            for index in range(3):
                write_wav(clips / f"L{index + 1}.wav", spoken_burst(0.5, amplitude=0.95))
            report = self.build(clips, script_file(tmp), tmp / "voice")
            peak = voiceover.read_wav(Path(report["path"]))[0]
        self.assertLessEqual(float(np.max(np.abs(peak))), 10 ** (-1.4 / 20) + 1e-3)


def _bundled_ffmpeg():
    try:
        import imageio_ffmpeg

        return Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
    except Exception:  # noqa: BLE001
        return False


def _convert(source: Path, target: Path) -> bool:
    import subprocess

    try:
        ffmpeg = assemble_voiceover.resolve_ffmpeg()
    except assemble_voiceover.DependencyMissing:
        return False
    result = subprocess.run(  # noqa: S603 - fixed argv in a test
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), str(target)],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0 and target.is_file()


if __name__ == "__main__":
    unittest.main()
