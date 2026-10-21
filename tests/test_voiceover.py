"""The voiceover pipeline must produce a timeline the picture can trust.

These tests never need a real speech model: the synthesiser is stubbed with a
tone so the timing math, the loudness chain and the envelope export are all
exercised on any machine. What the real voice sounds like is a render-time
question; what this file protects is that the numbers handed to the film are
correct, monotonic and derived from the audio instead of guessed.
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
    # The runtime voice chain needs numpy, but the project checks job installs no
    # third-party packages. Skip the module there instead of failing discovery:
    # an import error inside a test module used to turn the whole suite red.
    raise unittest.SkipTest("numpy is required to exercise the voice DSP") from None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import voiceover  # noqa: E402


def write_tone(path: Path, seconds: float, rate: int = 24000, amplitude: float = 0.5) -> None:
    samples = np.arange(int(rate * seconds)) / rate
    signal = amplitude * np.sin(2 * math.pi * 170 * samples)
    voiceover.write_wav(path, signal, rate)


class ScriptParsingTests(unittest.TestCase):
    def test_plain_strings_become_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"lines": ["one", "two"]}), encoding="utf-8")
            lines = voiceover.load_script(path)
        self.assertEqual([line.text for line in lines], ["one", "two"])
        self.assertEqual([line.id for line in lines], ["L1", "L2"])

    def test_objects_keep_their_pacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"lines": [
                {"id": "A", "text": "first", "gap_before": 2.5, "pause_after": 0.4, "rate": 0.9},
            ]}), encoding="utf-8")
            line = voiceover.load_script(path)[0]
        self.assertEqual(line.id, "A")
        self.assertEqual(line.gap_before, 2.5)
        self.assertEqual(line.pause_after, 0.4)
        self.assertEqual(line.rate, 0.9)

    def test_empty_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"lines": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                voiceover.load_script(path)

    def test_a_line_without_text_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"lines": [{"id": "A", "text": "  "}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                voiceover.load_script(path)

    def test_emphasis_markup_is_not_spoken(self):
        self.assertEqual(voiceover.spoken_text("once in *bones*"), "once in bones")
        self.assertEqual(voiceover.emphasis_words("once in *bones*, not CODE"),
                         ["bones", "code"])

    def test_punctuation_drives_prosody(self):
        cases = {"Is it?": "rising", "Do it!": "urgent", "and then,": "continuing", "Done.": "settling"}
        for text, expected in cases.items():
            self.assertEqual(voiceover.prosody_note(voiceover.Line(text=text)), expected)


class EnvelopeTests(unittest.TestCase):
    def test_silence_reads_as_a_closed_mouth(self):
        values = voiceover.openness_envelope(np.zeros(24000, dtype=np.float32), 24000, fps=30)
        self.assertEqual(len(values), 30)
        self.assertEqual(max(values), 0.0)

    def test_a_burst_is_near_one_and_a_pause_is_zero(self):
        signal = np.zeros(24000, dtype=np.float32)
        signal[3000:9000] = 0.6 * np.sin(np.arange(6000) / 10.0)
        values = voiceover.openness_envelope(signal, 24000, fps=30)
        loud = values[6:10]
        quiet = values[20:25]
        self.assertGreater(min(loud), 0.8)
        self.assertLess(max(quiet), 0.05)

    def test_values_stay_in_range(self):
        signal = (np.random.RandomState(0).randn(24000) * 0.4).astype(np.float32)
        values = voiceover.openness_envelope(signal, 24000, fps=30)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in values))


class AssemblyTests(unittest.TestCase):
    """Drive build() with a stubbed voice and check the timeline it publishes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.script = self.dir / "script.json"
        self.script.write_text(json.dumps({"lines": [
            {"id": "L1", "text": "Every frame,", "gap_before": 1.0, "pause_after": 0.25},
            {"id": "L2", "text": "is drawn twice.", "pause_after": 0.5},
            {"id": "L3", "text": "Once in *bones*.", "pause_after": 0.5},
            {"id": "L4", "text": "Once in code.", "pause_after": 0.25},
        ]}), encoding="utf-8")
        self.originals = (voiceover.piper_available, voiceover.piper_model_path,
                          voiceover.synth_piper_line)

        def fake_synth(line, model, out_path):
            write_tone(Path(out_path), 0.8 + 0.15 * len(line.text.split()))

        voiceover.piper_available = lambda: True
        voiceover.piper_model_path = lambda *args, **kwargs: Path("stub.onnx")
        voiceover.synth_piper_line = fake_synth

    def tearDown(self):
        (voiceover.piper_available, voiceover.piper_model_path,
         voiceover.synth_piper_line) = self.originals
        self.tmp.cleanup()

    def test_timeline_is_contiguous_and_ordered(self):
        report = voiceover.build(self.script, self.dir / "voice", fps=30)
        lines = report["lines"]
        self.assertEqual(len(lines), 4)
        for previous, current in zip(lines, lines[1:]):
            self.assertLessEqual(previous["end"], current["start"] + 1e-6)
        self.assertEqual(lines[0]["start"], 1.0)   # gap_before is honoured
        self.assertAlmostEqual(report["duration_seconds"], lines[-1]["end"] + 0.25, places=2)

    def test_line_durations_come_from_the_audio(self):
        report = voiceover.build(self.script, self.dir / "voice", fps=30)
        for line in report["lines"]:
            expected = 0.8 + 0.15 * len(line["spoken"].split())
            self.assertAlmostEqual(line["duration"], expected, delta=0.02)

    def test_envelope_file_matches_the_lines(self):
        voiceover.build(self.script, self.dir / "voice", fps=30)
        envelope = json.loads((self.dir / "voice" / "envelope.json").read_text(encoding="utf-8"))
        self.assertEqual(envelope["fps"], 30)
        self.assertEqual([item["id"] for item in envelope["lines"]], ["L1", "L2", "L3", "L4"])
        for item in envelope["lines"]:
            self.assertEqual(len(item["openness"]), int(round((item["end"] - item["start"]) * 30)))
            self.assertTrue(all(0.0 <= value <= 1.0 for value in item["openness"]))

    def test_the_written_voiceover_is_loud_and_not_clipped(self):
        voiceover.build(self.script, self.dir / "voice", fps=30)
        with wave.open(str(self.dir / "voice" / "voiceover.wav"), "rb") as handle:
            self.assertEqual(handle.getframerate(), voiceover.SAMPLE_RATE)
            self.assertEqual(handle.getnchannels(), 1)
            data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2") / 32768.0
        self.assertGreater(float(np.sqrt(np.mean(data ** 2))), 0.02)
        self.assertLessEqual(float(np.max(np.abs(data))), 1.0)

    def test_missing_backend_explains_what_to_install(self):
        voiceover.piper_available = lambda: False
        voiceover.espeak_available = lambda: False
        with self.assertRaises(voiceover.VoiceBackendMissing) as caught:
            voiceover.build(self.script, self.dir / "voice", fps=30)
        message = str(caught.exception)
        self.assertIn("piper", message)
        self.assertIn("espeak", message)

    def test_lines_json_is_the_picture_contract(self):
        voiceover.build(self.script, self.dir / "voice", fps=30)
        payload = json.loads((self.dir / "voice" / "lines.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"lines"})
        self.assertEqual([line["id"] for line in payload["lines"]], ["L1", "L2", "L3", "L4"])


if __name__ == "__main__":
    unittest.main()
