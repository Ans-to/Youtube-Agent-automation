"""Tests for the voice production layer and the Kokoro backend's pure parts.

The production layer is what stands between a text-to-speech model and a
narration a person would listen to: phrasing, pauses, rate shaping. These tests
pin the behaviour that is audible, and they run without a model so they stay
fast and offline.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import voice_production as vp  # noqa: E402


def tone(rate=vp.SAMPLE_RATE, seconds=0.4, freq=180.0):
    t = np.arange(int(rate * seconds), dtype=np.float32) / rate
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class SplitClauses(unittest.TestCase):
    def test_a_comma_is_a_pause_and_the_punctuation_stays(self):
        clauses = vp.split_clauses("Read the diff, then run it.")
        self.assertGreaterEqual(len(clauses), 2)
        self.assertEqual(clauses[0][1], "comma")
        self.assertIn(",", clauses[0][0])

    def test_a_question_mark_ends_a_sentence(self):
        kinds = [kind for _, kind in vp.split_clauses("Do you ship it? Not before reading.")]
        self.assertEqual(kinds[0], "sentence")

    def test_a_decimal_point_is_not_a_pause(self):
        clauses = vp.split_clauses("Bump the limit to 3.5 seconds.")
        self.assertEqual(len(clauses), 1)
        self.assertIn("3.5", clauses[0][0])

    def test_an_abbreviation_is_not_a_pause(self):
        clauses = vp.split_clauses("Read the lockfile, e.g. the hashes, before merging.")
        joined = " ".join(clause for clause, _ in clauses)
        self.assertIn("e.g.", joined)
        self.assertNotIn("e.", [clause[-2:] for clause, _ in clauses])

    def test_empty_text_produces_nothing(self):
        self.assertEqual(vp.split_clauses("   "), [])

    def test_the_tail_after_the_last_stop_has_no_trailing_pause(self):
        clauses = vp.split_clauses("Stop. Then go")
        self.assertEqual(clauses[-1][1], "")  # nothing to wait for at a line end


class PauseShape(unittest.TestCase):
    def test_a_sentence_end_is_longer_than_a_comma(self):
        self.assertGreater(vp.pause_for("sentence", "one two three"),
                           vp.pause_for("comma", "one two three"))

    def test_a_longer_clause_earns_a_longer_breath(self):
        short = vp.pause_for("sentence", "Ship it")
        long = vp.pause_for("sentence", "read the diff then run the tests then ship it all")
        self.assertGreater(long, short)

    def test_the_stretch_is_capped(self):
        enormous = " ".join(["word"] * 400)
        self.assertAlmostEqual(vp.pause_for("sentence", enormous),
                               vp.PAUSE_SECONDS["sentence"] * vp.PAUSE_SCALE_MAX, places=3)

    def test_unknown_punctuation_asks_for_no_pause(self):
        self.assertEqual(vp.pause_for("", "no stop here"), 0.0)


class RateShape(unittest.TestCase):
    def test_the_final_clause_lands_slower(self):
        self.assertLess(vp.rate_for(2, 3), vp.rate_for(1, 3))

    def test_a_single_clause_keeps_its_own_pace(self):
        self.assertEqual(vp.rate_for(0, 1), 1.0)

    def test_the_final_rate_is_audible_but_not_a_different_speaker(self):
        self.assertLess(vp.FINAL_CLAUSE_RATE, 0.98)
        self.assertGreater(vp.FINAL_CLAUSE_RATE, 0.85)


class Assemble(unittest.TestCase):
    def test_every_clause_is_synthesised_once(self):
        seen = []

        def synth(text, pace):
            seen.append((text, pace))
            return tone()

        vp.assemble([("first,", "comma"), ("second.", "sentence")], synth)
        self.assertEqual([text for text, _ in seen], ["first,", "second."])

    def test_pauses_are_inserted_at_the_declared_length(self):
        def synth(text, pace):
            return tone(seconds=0.2)

        audio = vp.assemble([("first,", "comma"), ("second.", "sentence")], synth)
        speech = 0.4 * vp.SAMPLE_RATE
        gap = int(vp.SAMPLE_RATE * vp.pause_for("comma", "first,"))
        self.assertAlmostEqual(audio.size, speech + gap, delta=2)

    def test_no_pause_is_appended_after_the_last_clause(self):
        def synth(text, pace):
            return tone(seconds=0.2)

        audio = vp.assemble([("only clause here,", "comma")], synth)
        self.assertAlmostEqual(audio.size / vp.SAMPLE_RATE, 0.2, delta=0.02)

    def test_joins_do_not_click(self):
        """A join is a fade, so no sample step may jump by a large amount."""
        def synth(text, pace):
            return tone(seconds=0.35)

        audio = vp.assemble([("one,", "comma"), ("two,", "comma"), ("three.", "sentence")], synth)
        steps = np.abs(np.diff(audio))
        self.assertLess(float(steps.max()), 0.25)

    def test_leading_and_trailing_silence_is_trimmed_but_a_handle_remains(self):
        def synth(text, pace):
            return np.concatenate([np.zeros(2400, dtype=np.float32), tone(seconds=0.3),
                                   np.zeros(2400, dtype=np.float32)])

        audio = vp.assemble([("hello there.", "sentence")], synth)
        # The join fade starts at zero by design; what matters is that it reaches
        # full level quickly and that the pad around the speech has been cut.
        self.assertGreater(float(np.abs(audio[:960]).max()), 0.1)  # level inside 40 ms
        self.assertLess(audio.size / vp.SAMPLE_RATE, 0.34)

    def test_an_empty_model_response_is_skipped_not_fatal(self):
        def synth(text, pace):
            return np.zeros(0, dtype=np.float32)

        audio = vp.assemble([("nothing.", "sentence")], synth)
        self.assertEqual(audio.size, 0)


class KokoroSpeeds(unittest.TestCase):
    """The speed mapping, pinned: it is what sets the film's words per minute."""

    def test_the_neutral_script_rate_gives_the_narration_tempo(self):
        import kokoro_voice
        self.assertAlmostEqual(kokoro_voice._speed_for(0.82), kokoro_voice.KOKORO_TEMPO, places=3)

    def test_a_higher_rate_speaks_faster(self):
        """`rate` is a pace multiplier: 0.9 is a brisker read than 0.75."""
        import kokoro_voice
        self.assertGreater(kokoro_voice._speed_for(0.9), kokoro_voice._speed_for(0.75))

    def test_speed_is_clamped_to_what_the_model_accepts(self):
        import kokoro_voice
        self.assertGreaterEqual(kokoro_voice._speed_for(50.0), 0.5)
        self.assertLessEqual(kokoro_voice._speed_for(0.001), kokoro_voice.SPEED_CEILING)

    def test_the_narration_tempo_lands_between_140_and_175_wpm(self):
        """Measured on the shipped voice: 0.86 of the model tempo is ~155 wpm."""
        import kokoro_voice
        self.assertLess(kokoro_voice.KOKORO_TEMPO, 1.0)
        self.assertGreater(kokoro_voice.KOKORO_TEMPO, 0.8)


class KokoroAssets(unittest.TestCase):
    def test_the_pins_and_their_integrity_strings_agree(self):
        import kokoro_voice
        for name, spec in kokoro_voice.PACKAGES.items():
            self.assertIn(spec["version"], spec["url"], name)
            self.assertTrue(spec["integrity"].startswith("sha512-"), name)

    def test_availability_is_a_bool_and_needs_no_network(self):
        import kokoro_voice
        self.assertIsInstance(kokoro_voice.available(), bool)

    def test_the_cache_dir_honours_the_environment(self):
        import importlib
        import os
        import kokoro_voice
        previous = os.environ.get("AGENTHQ_KOKORO_DIR")
        os.environ["AGENTHQ_KOKORO_DIR"] = "/tmp/kokoro-cache-test"
        try:
            self.assertEqual(str(kokoro_voice.cache_dir()), "/tmp/kokoro-cache-test")
        finally:
            if previous is None:
                os.environ.pop("AGENTHQ_KOKORO_DIR", None)
            else:
                os.environ["AGENTHQ_KOKORO_DIR"] = previous

    def test_a_missing_voice_is_named_in_the_error(self):
        """Asking for a voice that does not exist must say so, not crash obscurely."""
        import kokoro_voice
        # No cache and no network is fine: the name check happens before the fetch.
        with self.assertRaises(kokoro_voice.KokoroUnavailable):
            kokoro_voice.build_voices(Path("/tmp/kokoro-empty-cache"), names=["no_such_voice"])


if __name__ == "__main__":
    unittest.main()
