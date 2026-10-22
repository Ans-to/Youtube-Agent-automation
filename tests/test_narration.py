"""Narration must work on a machine with no system packages.

The film shipped silent because the only two voice backends were a neural model
that had to be downloaded and an `espeak-ng` binary that had to be installed with
a package manager. Both are things a user cannot be asked to do — the project is
local-first, and the film beside the code had a talking character with no voice.

`video_studio/espeak_lib.py` loads the synthesizer from a Python wheel instead:
no network, no system package, no administrator. These tests skip when the wheel
is absent, and otherwise prove the library really speaks and that the narration
builder uses it end to end.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover - the voice pipeline needs numpy anyway
    HAVE_NUMPY = False

try:
    import espeak_lib
    HAVE_LIB = espeak_lib.available()
    WHY = espeak_lib.why_unavailable()
except Exception as exc:  # noqa: BLE001 - report, never explode at import
    HAVE_LIB = False
    WHY = str(exc)
    espeak_lib = None

SCRIPT = ROOT / "video_studio" / "films" / "character_speaks.voice.json"


def loudness(pcm: bytes) -> float:
    """Mean absolute sample value of 16-bit little-endian PCM, 0..1."""
    if not pcm:
        return 0.0
    total = 0
    count = 0
    for index in range(0, len(pcm) - 1, 2):
        sample = int.from_bytes(pcm[index:index + 2], "little", signed=True)
        total += abs(sample)
        count += 1
    return (total / max(1, count)) / 32768.0


@unittest.skipIf(not HAVE_LIB, f"the speech wheel is not installed ({WHY})")
class SpeechLibraryTests(unittest.TestCase):
    def test_it_reports_a_sample_rate(self):
        self.assertGreater(espeak_lib.sample_rate(), 8000)

    def test_it_produces_audible_speech(self):
        pcm, rate = espeak_lib.synthesize("Every frame is drawn twice.", wpm=160)
        seconds = len(pcm) / 2 / rate
        self.assertGreater(seconds, 0.8, "the clip is too short to be a sentence")
        self.assertLess(seconds, 8.0, "the clip is far longer than the text")
        self.assertGreater(loudness(pcm), 0.01, "the clip is silent")

    def test_a_longer_sentence_takes_longer(self):
        short, rate = espeak_lib.synthesize("One.", wpm=160)
        long, _ = espeak_lib.synthesize("One. Two. Three. Four. Five.", wpm=160)
        self.assertGreater(len(long), len(short) * 2)

    def test_a_faster_rate_is_shorter(self):
        slow, rate = espeak_lib.synthesize("The quick brown fox jumps over it.", wpm=120)
        fast, _ = espeak_lib.synthesize("The quick brown fox jumps over it.", wpm=200)
        self.assertGreater(len(slow), len(fast))

    def test_pitch_changes_the_signal_without_changing_the_length_much(self):
        low, _ = espeak_lib.synthesize("A steady line of speech.", pitch=20)
        high, _ = espeak_lib.synthesize("A steady line of speech.", pitch=80)
        self.assertNotEqual(low, high)
        ratio = len(high) / max(1, len(low))
        self.assertGreater(ratio, 0.8)
        self.assertLess(ratio, 1.25)

    def test_it_writes_a_readable_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = espeak_lib.say("Written to disk.", Path(tmp) / "line.wav")
            with wave.open(str(path)) as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertGreater(handle.getnframes(), 1000)

    def test_an_unknown_voice_is_an_error_not_silence(self):
        with self.assertRaises(Exception):
            espeak_lib.synthesize("Hello.", voice="not-a-voice")


@unittest.skipIf(not (HAVE_LIB and HAVE_NUMPY), "the speech wheel or numpy is missing")
class NarrationBuilderTests(unittest.TestCase):
    """The end-to-end path a render actually takes."""

    def test_a_script_becomes_a_voice_track_without_any_download(self):
        import voiceover

        with tempfile.TemporaryDirectory() as tmp:
            info = voiceover.build(SCRIPT, Path(tmp), allow_download=False,
                                   backend="auto", fps=30)
            voiceover_path = Path(info["path"])
            self.assertTrue(voiceover_path.is_file())
            self.assertEqual(info["backend"], "espeak")
            script_data = json.loads(SCRIPT.read_text(encoding="utf-8"))
            self.assertEqual(info["line_count"], len(script_data["lines"]))
            self.assertGreater(info["duration_seconds"], 10.0)
            lines = json.loads((Path(tmp) / "lines.json").read_text(encoding="utf-8"))
            self.assertEqual(len(lines["lines"]), len(script_data["lines"]))
            envelope = json.loads((Path(tmp) / "envelope.json").read_text(encoding="utf-8"))
            self.assertTrue(envelope["lines"])
            for line in envelope["lines"]:
                self.assertTrue(line["visemes"], "no mouth shapes were measured")
                self.assertEqual(len(line["openness"]), len(line["visemes"]))

    def test_the_mouth_moves_while_the_line_is_spoken(self):
        import voiceover

        with tempfile.TemporaryDirectory() as tmp:
            info = voiceover.build(SCRIPT, Path(tmp), allow_download=False, backend="auto", fps=30)
            envelope = json.loads((Path(tmp) / "envelope.json").read_text(encoding="utf-8"))
        opened = [v["open"] for line in envelope["lines"] for v in line["visemes"]]
        self.assertTrue(opened)
        self.assertGreater(max(opened), 0.3, "the loudest mouth shape barely opens")
        self.assertLess(min(opened), 0.2, "the mouth never closes between sounds")

    def test_narration_is_offered_without_the_command_line_tool(self):
        import voiceover

        # The point of the wheel: availability must not depend on `which espeak-ng`.
        # This box has no such binary, and the backend still reports itself ready.
        self.assertTrue(voiceover.espeak_available())
        if shutil.which("espeak-ng") is None and shutil.which("espeak") is None:
            self.assertTrue(voiceover._espeak_lib_available(),
                            "there is no binary and no library, so narration would be silent")


class FilmNarrationWiringTests(unittest.TestCase):
    """A film with a `.voice.json` beside it must be rendered with a voice."""

    def test_the_render_driver_finds_the_companion_script(self):
        source = (ROOT / "tools" / "render_authored_film.py").read_text(encoding="utf-8")
        self.assertIn('with_suffix(".voice.json")', source)
        self.assertIn("narration script found beside the film", source)

    def test_the_film_has_a_companion_script(self):
        film = ROOT / "video_studio" / "films" / "character_speaks.mjs"
        companion = film.with_suffix(".voice.json")
        self.assertTrue(companion.is_file(), "the talking film has no narration script")


if __name__ == "__main__":
    unittest.main()
