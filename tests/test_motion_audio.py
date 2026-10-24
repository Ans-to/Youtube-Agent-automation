import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import audio_design  # noqa: E402

CUES = [
    {"at": 0.5, "kind": "whoosh", "gain": 0.4, "length": 0.32},
    {"at": 1.2, "kind": "impact", "gain": 0.3, "length": 0.40},
    {"at": 1.8, "kind": "click", "gain": 0.2, "length": 0.09},
]


class MotionAudioTests(unittest.TestCase):
    def test_sfx_render_is_deterministic_and_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.wav"
            second = Path(tmp) / "b.wav"
            report = audio_design.render_motion_sfx(first, 3.0, CUES, sample_rate=16000)
            audio_design.render_motion_sfx(second, 3.0, CUES, sample_rate=16000)
            self.assertEqual(report["cue_count"], 3)
            self.assertEqual(report["duration_seconds"], 3.0)
            self.assertLessEqual(report["peak"], 1.0)
            self.assertGreater(report["peak"], 0.0)
            with wave.open(str(first), "rb") as a, wave.open(str(second), "rb") as b:
                self.assertEqual(a.getnchannels(), 1)
                self.assertEqual(a.getsampwidth(), 2)
                self.assertEqual(a.getframerate(), 16000)
                self.assertEqual(a.getnframes(), 48000)
                self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))

    def test_every_declared_sfx_kind_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _index, kind in enumerate(audio_design.SFX_KINDS):
                path = Path(tmp) / ("cue-%s.wav" % kind)
                report = audio_design.render_motion_sfx(
                    path, 1.0, [{"at": 0.1, "kind": kind, "gain": 0.4, "length": 0.3}],
                    sample_rate=8000,
                )
                self.assertEqual(report["cue_count"], 1)
                self.assertGreater(report["peak"], 0.0, msg=kind)

    def test_unknown_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown kind"):
                audio_design.render_motion_sfx(Path(tmp) / "x.wav", 1.0,
                                               [{"at": 0.1, "kind": "airhorn", "length": 0.2}])

    def test_gain_and_length_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "gain"):
                audio_design.render_motion_sfx(Path(tmp) / "x.wav", 1.0,
                                               [{"at": 0.1, "kind": "click", "gain": 2.0, "length": 0.2}])
            with self.assertRaisesRegex(ValueError, "length"):
                audio_design.render_motion_sfx(Path(tmp) / "x.wav", 1.0,
                                               [{"at": 0.1, "kind": "click", "gain": 0.2, "length": 9.0}])

    def test_cues_outside_the_timeline_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audio_design.render_motion_sfx(
                Path(tmp) / "x.wav", 1.0, [{"at": 5.0, "kind": "click", "gain": 0.2, "length": 0.1}])
            self.assertEqual(report["cue_count"], 0)
            self.assertEqual(report["peak"], 0.0)

    def test_sfx_mix_joins_the_procedural_bed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audio_design.render_sound_design(
                Path(tmp) / "mix.wav", 2.0, [1.0, 1.0], sample_rate=8000,
                sfx_cues=[{"at": 1.0, "kind": "whoosh", "gain": 0.3, "length": 0.32}],
            )
            self.assertEqual(report["sfx_cue_count"], 1)
            self.assertEqual(report["scene_cue_count"], 1)
            with wave.open(report["path"], "rb") as stream:
                self.assertEqual(stream.getnframes(), 16000)

    def test_invalid_durations_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                audio_design.render_motion_sfx(Path(tmp) / "x.wav", 0, [])
            with self.assertRaisesRegex(ValueError, "Cues must be a list"):
                audio_design.render_motion_sfx(Path(tmp) / "x.wav", 1.0, {"at": 0})


if __name__ == "__main__":
    unittest.main()


class NoCueIsAHeldNote(unittest.TestCase):
    """A cue may be loud, sharp, or long. It may not be a note.

    The owner heard a "veeee" in the render test and could not say where it came
    from, which is what a tone under a noise sounds like: the ears find the pitch
    and the brain cannot place it. Two cues were doing it. The whoosh mixed noise
    with a sine sweeping to 1.6 kHz - and its phase was not integrated, so it
    burbled as well as whistled - and the swell was a pair of pure sines at
    140-200 Hz held for a second and a quarter.

    Both are now noise through a moving bandpass. These tests hold them there: a
    tone puts most of a window's energy in one bin, and air does not.
    """

    RATE = 24000
    WINDOW = 0.08

    def _share_of_one_bin(self, kind, length, limit):
        import math

        import numpy as np

        samples = np.array(audio_design._synth_cue(kind, length, self.RATE, seed=7919))
        size = int(self.WINDOW * self.RATE)
        worst, at = 0.0, 0.0
        for start in range(0, max(1, len(samples) - size), size // 2):
            segment = samples[start:start + size] * np.hanning(size)
            energy = np.abs(np.fft.rfft(segment, 4096)) ** 2
            share = float(energy.max() / energy.sum())
            if share > worst:
                worst, at = share, start / self.RATE
        self.assertLess(worst, limit,
                        msg="%s is %.0f%% one bin at %.2fs - that is a note, not air"
                            % (kind, worst * 100, at))
        return worst

    def test_whoosh_is_air_and_not_a_whistle(self):
        self._share_of_one_bin("whoosh", 0.7, 0.10)
        self._share_of_one_bin("whoosh", 0.45, 0.10)

    def test_swell_is_air_and_not_a_held_note(self):
        self._share_of_one_bin("swell", 1.2, 0.10)
        self._share_of_one_bin("swell", 0.9, 0.10)

    def test_the_band_actually_moves(self):
        """A bandpass that never sweeps is just a quieter hiss."""
        import numpy as np

        samples = np.array(audio_design._synth_cue("whoosh", 0.7, self.RATE, seed=7919))

        def centroid(segment):
            spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
            freqs = np.fft.rfftfreq(len(segment), 1 / self.RATE)
            return float((spectrum * freqs).sum() / max(spectrum.sum(), 1e-9))

        size = int(0.08 * self.RATE)
        early = centroid(samples[:size])
        late = centroid(samples[-size:])
        self.assertGreater(late, early * 1.5,
                           "the whoosh opens from %.0f Hz to %.0f Hz only" % (early, late))

    def test_impact_stays_in_hearing(self):
        """It used to sweep to about ten hertz, which nobody can hear."""
        import numpy as np

        samples = np.array(audio_design._synth_cue("impact", 0.5, self.RATE, seed=7919))
        segment = samples[-int(0.2 * self.RATE):]
        spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
        freqs = np.fft.rfftfreq(len(segment), 1 / self.RATE)
        peak = float(freqs[int(np.argmax(spectrum[3:])) + 3])
        self.assertGreater(peak, 35.0, "the hit ends at %.0f Hz" % peak)
