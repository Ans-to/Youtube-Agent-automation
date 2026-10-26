"""The voice chain has to be measurable, or it is just an opinion.

What went wrong before is that a filter went unstable and produced NaN, and the
only thing that noticed was a loudness reading of -70 LUFS printed to a console
nobody read. These tests are the ones that would have failed.
"""
import unittest

import numpy as np

from video_studio import voice as V


class FilterTest(unittest.TestCase):
    def test_every_filter_stays_finite(self):
        """A biquad with one coefficient mis-normalised made the whole chain NaN."""
        noise = np.random.default_rng(0).normal(0, 0.1, V.SR).astype(np.float32)
        for name, fn in [
            ('highpass', lambda x: V.highpass(x, 88)),
            ('lowpass', lambda x: V.lowpass(x, 6000)),
            ('peaking', lambda x: V.peaking(x, 320, 0.9, -2.5)),
            ('low_shelf', lambda x: V.low_shelf(x, 160, 1.2)),
            ('high_shelf', lambda x: V.high_shelf(x, 9500, -2.0)),
            ('master', V.master),
        ]:
            with self.subTest(filter=name):
                out = fn(noise)
                self.assertTrue(np.all(np.isfinite(out)), f'{name} produced non-finite samples')
                self.assertGreater(float(np.max(np.abs(out))), 0.0, f'{name} silenced the signal')

    def test_highpass_removes_rumble(self):
        t = np.arange(V.SR) / V.SR
        rumble = np.sin(2 * np.pi * 30 * t).astype(np.float32)
        out = V.highpass(rumble, 88.0)
        self.assertLess(float(np.sqrt(np.mean(out ** 2))), 0.05, 'rumble survived the high-pass')

    def test_de_ess_targets_sibilance(self):
        """7 kHz should drop, 1 kHz should not."""
        t = np.arange(V.SR) / V.SR
        def band(freq):
            return V.peaking(np.sin(2 * np.pi * freq * t).astype(np.float32), 5500, 1.2, -3.0)
        sib = float(np.sqrt(np.mean(band(7000) ** 2)))
        mid = float(np.sqrt(np.mean(band(1000) ** 2)))
        self.assertLess(sib, mid, 'the de-esser took more mid than sibilance')


class LoudnessTest(unittest.TestCase):
    def test_lufs_matches_a_known_tone(self):
        """A 1 kHz sine at -20 dBFS is about -20 LUFS; K-weighting is near 0 there."""
        t = np.arange(V.SR * 3) / V.SR
        tone = (0.1 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        self.assertAlmostEqual(V.lufs(tone), -23.0, delta=1.5)

    def test_normalise_reaches_the_target_and_respects_ceiling(self):
        t = np.arange(V.SR * 2) / V.SR
        quiet = (0.01 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        out = V.normalise(quiet, target=-16.0, ceiling_db=-1.5)
        self.assertAlmostEqual(V.lufs(out), -16.0, delta=1.0)
        self.assertLessEqual(float(np.max(np.abs(out))), 10 ** (-1.5 / 20) + 1e-3)


class PhrasingTest(unittest.TestCase):
    def test_comma_and_stop_are_cut_where_a_speaker_breathes(self):
        cuts = V.phrases('One company, four industries. Then the ground moved.')
        self.assertEqual([c[1] for c in cuts], ['comma', 'stop', 'none'])
        self.assertEqual(cuts[0][0], 'One company')

    def test_a_sentence_ends_slower_than_it_starts(self):
        """The drama profile decelerates into a full stop; the calm one does not.

        This used to assert 0.97 / 1.02 / 0.94 outright, which pinned one
        performance as the only performance. The read was then rejected as too
        dramatic and the constant had to move - the property worth testing is
        that the shaping *follows the profile*, not which profile is in favour.
        """
        was = V.PROFILE
        try:
            V.set_profile('dramatic')
            self.assertEqual(V.shape_rate(0, 3), 0.97)
            self.assertEqual(V.shape_rate(2, 3), 0.94)
            self.assertEqual(V.shape_rate(1, 3), 1.02)

            V.set_profile('calm')
            self.assertEqual(V.shape_rate(0, 3), 1.0)
            self.assertLess(V.shape_rate(2, 3), 1.0)
            self.assertGreater(V.shape_rate(2, 3), 0.98)
        finally:
            V.set_profile(was)

    def test_calm_pauses_are_shorter_than_dramatic_ones(self):
        """A 420 ms full stop is a trailer beat; a narrator breathes for less."""
        was = V.PROFILE
        try:
            V.set_profile('dramatic')
            dramatic = V.PAUSE['stop'] * V.PERFORMANCE['dramatic']['pause']
            V.set_profile('calm')
            calm = V.PAUSE['stop'] * V.PERFORMANCE['calm']['pause']
        finally:
            V.set_profile(was)
        self.assertLess(calm, dramatic * 0.8)

    def test_an_unknown_profile_is_refused(self):
        with self.assertRaises(SystemExit):
            V.set_profile('shouty')

    def test_engines_declare_themselves(self):
        """An unavailable engine must say why, not disappear."""
        for engine in V.ENGINES:
            if not engine.available:
                self.assertTrue(engine.reason, f'{engine.name} is unavailable with no reason given')


if __name__ == '__main__':
    unittest.main()
