import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import beat  # noqa: E402


def write_click_track(path, bpm=120, seconds=6.0, sample_rate=22050):
    period = 60.0 / bpm
    count = int(seconds * sample_rate)
    samples = array("h")
    for index in range(count):
        t = index / sample_rate
        phase = t % period
        value = 0.02 * math.sin(2 * math.pi * 110.0 * t)
        if phase < 0.03:
            value += 0.8 * math.exp(-phase * 120.0) * math.sin(2 * math.pi * 1800.0 * phase)
        samples.append(int(max(-1.0, min(1.0, value)) * 32767))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())
    return path


class BeatTests(unittest.TestCase):
    def test_wav_reader_returns_mono_samples_at_native_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_click_track(Path(tmp) / "track.wav", seconds=2.0)
            samples, rate = beat.read_wav(path)
            self.assertEqual(rate, 22050)
            self.assertEqual(len(samples), 44100)
            self.assertLessEqual(max(abs(value) for value in samples), 1.0)

    def test_spectral_flux_tracks_the_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_click_track(Path(tmp) / "track.wav", seconds=2.0)
            samples, rate = beat.read_wav(path)
            flux = beat.spectral_flux(samples, rate)
            self.assertGreater(len(flux["flux"]), 10)
            self.assertEqual(len(flux["flux"]), len(flux["times"]))
            self.assertGreater(max(flux["flux"]), 0)

    def test_onsets_and_tempo_recover_a_120_bpm_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_click_track(Path(tmp) / "track.wav", bpm=120, seconds=6.0)
            analysis = beat.analyze(path)
            self.assertGreaterEqual(len(analysis["onsets"]), 8)
            self.assertIsNotNone(analysis["tempo"]["bpm"])
            self.assertAlmostEqual(analysis["tempo"]["bpm"], 120.0, delta=6.0)
            self.assertGreater(analysis["beat_count"], 8)

    def test_silence_produces_no_onsets_or_tempo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silence.wav"
            samples = array("h", [0] * 22050)
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(22050)
                stream.writeframes(samples.tobytes())
            analysis = beat.analyze(path)
            self.assertEqual(analysis["onsets"], [])
            self.assertIsNone(analysis["tempo"]["bpm"])
            self.assertEqual(analysis["beats"], [])

    def test_snap_only_moves_cues_that_are_close(self):
        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
        result = beat.snap_to_beats([0.51, 1.02, 2.30], beats, tolerance=0.12)
        self.assertEqual(result["times"], [0.5, 1.0, 2.30])
        self.assertEqual(result["moved"], 2)
        self.assertEqual(result["unsnapped"], 1)

    def test_nearest_beat_returns_the_signed_distance(self):
        self.assertEqual(beat.nearest_beat(0.44, [0.0, 0.5]), (0.5, 0.06))
        self.assertEqual(beat.nearest_beat(3.0, []), (3.0, 0.0))

    def test_beat_grid_is_evenly_spaced(self):
        grid = beat.beat_grid({"bpm": 120.0}, 2.0)
        self.assertEqual(grid, [0.0, 0.5, 1.0, 1.5, 2.0])
        self.assertEqual(beat.beat_grid({"bpm": None}, 2.0), [])

    def test_tempo_needs_enough_onsets(self):
        result = beat.estimate_tempo([{"time": 0.0}, {"time": 0.5}])
        self.assertIsNone(result["bpm"])
        self.assertIn("too few", result["reason"])

    def test_cue_sheet_attaches_sound_to_edits_only(self):
        timeline = [
            {"start": 0.0, "transition_in": "cut"},
            {"start": 2.0, "transition_in": "whip-pan"},
            {"start": 4.0, "transition_in": "glitch", "impact": True},
        ]
        sheet = beat.cue_sheet(timeline, beats=[0.0, 2.0, 4.0, 4.5])
        kinds = [cue["kind"] for cue in sheet["cues"]]
        self.assertEqual(kinds, ["whoosh", "glitch", "impact"])
        self.assertEqual([cue["at"] for cue in sheet["cues"]], [2.0, 4.0, 4.12])
        self.assertLessEqual(sheet["max_gain"], 0.42)

    def test_unknown_wav_and_bad_rates_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                beat.read_wav(Path(tmp) / "missing.wav")
        with self.assertRaisesRegex(ValueError, "Beat grid"):
            beat.beat_grid({"bpm": 120.0}, 0)

    def test_report_is_human_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_click_track(Path(tmp) / "track.wav", seconds=4.0)
            text = beat.report(path)
            self.assertIn("BEAT ANALYSIS", text)
            self.assertIn("BPM", text)


if __name__ == "__main__":
    unittest.main()
