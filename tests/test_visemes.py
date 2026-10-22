"""Mouth shapes must follow articulation, not volume.

The renderer used to open the character's mouth in proportion to how loud each
frame was, so /p/ and /a/ looked identical whenever they were equally loud and a
quiet passage produced a closed mouth even while the speaker was saying a vowel.
`video_studio.visemes` replaces that with measurements of *which* sounds are
being made: formants for vowels, turbulent high-frequency energy for fricatives,
and a voicing estimate plus energy collapse for closures.

These tests pin down the three things that went wrong while building it, because
each one produced a plausible-looking but wrong envelope rather than an error:

* frame extraction advanced one sample per frame, so every frame was nearly the
  same audio;
* the autocorrelation normaliser punished long lags, so low-pitched real speech
  scored as unvoiced;
* formants were read without pre-emphasis and without anatomical limits, so the
  linear predictor locked onto pitch harmonics and reported F1 up to 1800 Hz.

The vowel table below is synthesised with a full source-filter-radiation model
(glottal tilt, two formant resonators, lip radiation). An earlier table omitted
the radiation stage and made pre-emphasis look harmful, which sent the estimator
in the wrong direction.
"""
import sys
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError:  # noqa: BLE001 - the DSP dependency is optional on CI images
    raise unittest.SkipTest("numpy is required to exercise the viseme estimator") from None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import visemes  # noqa: E402

FS = 22050


def _resonator(signal, frequency, bandwidth, rate):
    """Two-pole resonator, the standard building block of a formant filter."""
    radius = np.exp(-np.pi * bandwidth / rate)
    theta = 2.0 * np.pi * frequency / rate
    a1 = -2.0 * radius * np.cos(theta)
    a2 = radius * radius
    y1 = y2 = 0.0
    out = np.empty_like(signal)
    for index, value in enumerate(signal):
        result = value - a1 * y1 - a2 * y2
        y2 = y1
        y1 = result
        out[index] = result
    return out


def synth_vowel(f1, f2, rate=FS, duration=0.5, f0=110.0, amplitude=0.3):
    """A voiced vowel with the spectral tilt real speech actually carries.

    Impulse train -> glottal two-pole (-12 dB/oct) -> F1 -> F2 -> first
    difference (lip radiation, +6 dB/oct). The net -6 dB/oct is what
    pre-emphasis in the estimator is there to cancel.
    """
    count = int(rate * duration)
    source = np.zeros(count)
    source[::int(rate / f0)] = 1.0
    tilt = 0.98
    glottal = np.zeros(count)
    for index in range(2, count):
        glottal[index] = 2 * tilt * glottal[index - 1] - tilt * tilt * glottal[index - 2] + source[index]
    radiated = np.append(glottal[0], np.diff(glottal))
    shaped = _resonator(_resonator(radiated, f1, 80.0, rate), f2, 110.0, rate)
    return amplitude * shaped / 10.0


def synth_closure(rate=FS, duration=0.5, amplitude=0.3, f0=110.0):
    """A /p/: the vocal tract is shut, so almost nothing gets out."""
    count = int(rate * duration)
    return amplitude * 0.02 * np.random.default_rng(7).standard_normal(count)


VOWELS = {"a": (730, 1090), "i": (270, 2290), "u": (300, 870),
          "e": (530, 1840), "o": (570, 840)}


class FrameExtractionTest(unittest.TestCase):
    """Every frame must be a different slice of audio."""

    def test_frames_advance_by_the_hop_size(self):
        signal = np.arange(4000, dtype=np.float64)
        frames, hop = visemes._frame_signal(signal, 16000, fps=30, window_ms=40.0)
        self.assertEqual(hop, round(16000 / 30))
        # The regression: frames advanced one sample apart, so frame 0 and
        # frame 1 shared 959 of their first 960 samples.
        self.assertEqual(frames[0][0], 0.0)
        self.assertEqual(frames[1][0], float(hop))
        self.assertNotEqual(float(frames[0][10]), float(frames[1][10]))

    def test_consecutive_frames_are_not_near_identical(self):
        # 175 Hz is deliberately not a whole number of cycles per 1/30 s hop;
        # a divisor of the hop would make adjacent frames genuinely identical.
        signal = np.sin(2 * np.pi * 175 * np.arange(24000) / 24000)
        frames, hop = visemes._frame_signal(signal, 24000, fps=30, window_ms=40.0)
        difference = np.abs(frames[3] - frames[4]).mean()
        self.assertGreater(difference, 0.1, "frames are sliding one sample at a time")


class VoicingTest(unittest.TestCase):
    """Periodicity must not depend on the pitch being high."""

    def test_low_pitched_tone_is_voiced(self):
        rate = 24000
        for f0 in (100, 120, 200):
            tone = np.sin(2 * np.pi * f0 * np.arange(rate) / rate)
            frame = tone[:int(rate * 0.04)]
            self.assertGreater(visemes._voicing(frame, rate), 0.6,
                               f"{f0} Hz should read as voiced")

    def test_voicing_does_not_fall_with_lag(self):
        # 100 Hz sits at lag 240 of a 960 sample window, which overlaps 75% of
        # the frame; the old normaliser charged it 25% and it scored ~0.2.
        rate = 24000
        window = int(rate * 0.04)
        scores = []
        for f0 in (100, 240):
            tone = np.sin(2 * np.pi * f0 * np.arange(window) / rate)
            scores.append(visemes._voicing(tone, rate))
        self.assertAlmostEqual(scores[0], scores[1], delta=0.15)

    def test_noise_is_not_voiced(self):
        frame = np.random.default_rng(3).standard_normal(960)
        self.assertLess(visemes._voicing(frame, 24000), 0.5)


class FormantTest(unittest.TestCase):
    """Formants must land where the vocal tract put them."""

    def test_vowel_table(self):
        for name, (f1, f2) in VOWELS.items():
            with self.subTest(vowel=name):
                frames = visemes.estimate_visemes(synth_vowel(f1, f2), FS, fps=30)
                measured = frames[len(frames) // 2]
                self.assertLess(abs(measured["f1"] - f1), 120,
                                f"/{name}/ F1 {measured['f1']:.0f} vs {f1}")
                self.assertLess(abs(measured["f2"] - f2), 200,
                                f"/{name}/ F2 {measured['f2']:.0f} vs {f2}")
                self.assertEqual(measured["class"], "vowel")

    def test_f1_stays_inside_its_anatomical_range(self):
        for name, (f1, f2) in VOWELS.items():
            with self.subTest(vowel=name):
                frames = visemes.estimate_visemes(synth_vowel(f1, f2), FS, fps=30)
                for frame in frames:
                    self.assertLessEqual(frame["f1"], visemes.F1_MAX_HZ)
                    if frame["f2"]:
                        self.assertGreater(frame["f2"], frame["f1"])


class MouthShapeTest(unittest.TestCase):
    """The channels the renderer consumes have to describe the phoneme."""

    def test_vowels_have_distinct_mouths(self):
        shapes = {}
        for name, (f1, f2) in VOWELS.items():
            frames = visemes.estimate_visemes(synth_vowel(f1, f2), FS, fps=30)
            shapes[name] = frames[len(frames) // 2]
        # /a/ is wide open, /u/ and /i/ are nearly shut.
        self.assertGreater(shapes["a"]["open"], 0.6)
        self.assertLess(shapes["i"]["open"], 0.35)
        # /i/ spreads and /u/ rounds; the two must not be the same shape.
        self.assertGreater(shapes["i"]["wide"], 0.75)
        self.assertLess(shapes["u"]["wide"], 0.40)
        self.assertGreater(shapes["u"]["round"], 0.70)
        self.assertLess(shapes["i"]["round"], 0.25)

    def test_open_a_sits_between_front_and_back(self):
        # /a/ is central: it must not be as spread as /i/ nor as pursed as /u/.
        # An unguarded linear map put it at one extreme.
        def shape(name):
            frames = visemes.estimate_visemes(synth_vowel(*VOWELS[name]), FS, fps=30)
            return frames[len(frames) // 2]

        a, i, u = shape("a"), shape("i"), shape("u")
        self.assertLess(a["round"], u["round"])
        self.assertGreater(a["round"], i["round"])
        self.assertGreater(a["wide"], u["wide"])

    def test_silence_closes_the_mouth(self):
        frames = visemes.estimate_visemes(np.zeros(FS // 2), FS, fps=30)
        self.assertLess(frames[0]["open"], 0.1)
        self.assertGreater(frames[0]["press"], 0.8)
        self.assertEqual(frames[0]["class"], "silence")

    def test_noise_is_turbulent_not_voiced(self):
        noise = np.diff(np.random.default_rng(11).standard_normal(FS // 2)) * 0.3
        frames = visemes.estimate_visemes(noise, FS, fps=30)
        middle = frames[len(frames) // 2]
        self.assertEqual(middle["class"], "fricative")
        self.assertGreater(middle["teeth"], 0.5)
        self.assertLess(middle["press"], 0.4)


class EqualLoudnessTest(unittest.TestCase):
    """The complaint that started this: volume was the only input.

    Under the old loudness ramp, two frames of equal loudness always produced
    the same mouth, and a quiet passage always produced a closed mouth.
    """

    def test_equal_loudness_vowels_have_different_mouths(self):
        # /a/ and /i/ at the same amplitude are equally loud and must not look
        # the same: one hangs open, the other is nearly shut and spread.
        frames_a = visemes.estimate_visemes(synth_vowel(*VOWELS["a"]), FS, fps=30)
        frames_i = visemes.estimate_visemes(synth_vowel(*VOWELS["i"]), FS, fps=30)
        a, i = frames_a[10], frames_i[10]

        self.assertAlmostEqual(a["loudness"], i["loudness"], delta=0.15)
        self.assertGreater(a["open"] - i["open"], 0.4,
                           "equally loud vowels must open the jaw by different amounts")
        self.assertGreater(i["wide"] - a["wide"], 0.3,
                           "equally loud vowels must spread the lips by different amounts")

    def test_a_stop_reads_as_a_closure(self):
        """A /p/ is a shut vocal tract between two vowels, not a quiet vowel."""
        gap = int(FS * 0.18)
        silence = np.zeros(gap)
        utterance = np.concatenate([
            synth_vowel(*VOWELS["a"], duration=0.35),
            silence,
            synth_vowel(*VOWELS["a"], duration=0.35),
        ])
        frames = visemes.estimate_visemes(utterance, FS, fps=30)
        # The analysis window is 40 ms and the smoothing pass lets shapes lead
        # and lag, so pick the frame at the centre of the gap.
        centre = int((0.35 + 0.09) * 30)
        closed = frames[centre]
        vowel_frame = frames[3]

        self.assertGreater(vowel_frame["open"], 0.6)
        self.assertLess(closed["open"], 0.25)
        self.assertGreater(closed["press"], vowel_frame["press"] + 0.4,
                           "a stop closure must press the lips far harder than a vowel")

    def test_shape_follows_phoneme_across_loudness(self):
        # A quiet vowel must still open the mouth; the same vowel amplified
        # must not change shape, only be equally recognisable.
        quiet = synth_vowel(*VOWELS["a"], amplitude=0.05)
        loud = synth_vowel(*VOWELS["a"], amplitude=0.60)
        quiet_frame = visemes.estimate_visemes(quiet, FS, fps=30)[10]
        loud_frame = visemes.estimate_visemes(loud, FS, fps=30)[10]
        self.assertAlmostEqual(quiet_frame["open"], loud_frame["open"], delta=0.25)
        self.assertAlmostEqual(quiet_frame["round"], loud_frame["round"], delta=0.25)


class ChannelContractTest(unittest.TestCase):
    """The renderer reads these keys; the envelope writer drops what it cannot."""

    def test_every_frame_carries_the_renderer_channels(self):
        frames = visemes.estimate_visemes(synth_vowel(*VOWELS["a"]), FS, fps=30)
        for frame in frames:
            for channel in ("open", "wide", "round", "teeth", "press"):
                self.assertIn(channel, frame)
                self.assertGreaterEqual(frame[channel], 0.0)
                self.assertLessEqual(frame[channel], 1.0)

    def test_renderer_channels_strip_diagnostics(self):
        frames = visemes.estimate_visemes(synth_vowel(*VOWELS["a"]), FS, fps=30)
        channels = visemes.as_renderer_channels(frames)
        self.assertEqual(len(channels), len(frames))
        self.assertEqual(set(channels[0]), {"open", "wide", "round", "teeth", "press"})

    def test_empty_signal_still_returns_one_frame(self):
        frames = visemes.estimate_visemes(np.zeros(0), FS, fps=30)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["class"], "silence")

    def test_frame_count_matches_video_length(self):
        frames = visemes.estimate_visemes(np.zeros(FS * 2), FS, fps=30)
        self.assertAlmostEqual(len(frames), 60, delta=1)


class OrderTest(unittest.TestCase):
    """The LPC order has to scale with the sample rate."""

    def test_order_scales_with_rate(self):
        self.assertEqual(visemes.lpc_order_for(8000), 12)
        self.assertNotEqual(visemes.lpc_order_for(16000), visemes.lpc_order_for(44100))
        self.assertGreater(visemes.lpc_order_for(44100), visemes.lpc_order_for(22050))

    def test_rate_does_not_change_the_answer(self):
        # The same vowel measured at two sample rates has to describe the same
        # mouth; a fixed order of 12 is tuned for 8 kHz and merges F1 with F2
        # above it.
        low = synth_vowel(*VOWELS["u"], rate=16000)
        high = synth_vowel(*VOWELS["u"], rate=44100)
        low_frame = visemes.estimate_visemes(low, 16000, fps=30)[10]
        high_frame = visemes.estimate_visemes(high, 44100, fps=30)[10]
        self.assertAlmostEqual(low_frame["round"], high_frame["round"], delta=0.25)


if __name__ == "__main__":
    unittest.main()
