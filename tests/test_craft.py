"""Tests for the craft gate.

Each test pins one rule to the number in `docs/youtube-craft.md`, because a gate
whose thresholds drift silently is worse than no gate: it reports "passed" for a
film that breaks the rule it was written for.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video_studio"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import craft  # noqa: E402
import brief_to_voice  # noqa: E402


def cues(*rows):
    return [{"start": s, "end": e, "text": t, "lines": [t]} for s, e, t in rows]


def script(*texts):
    return {"lines": [{"id": f"L{i + 1:03d}", "scene": "s1", "text": t}
                      for i, t in enumerate(texts)]}


class MergeCuesTests(unittest.TestCase):
    def test_touching_cues_are_one_spoken_line(self):
        merged = craft.merge_cues(cues((0.0, 2.0, "An agent wrote"), (2.0, 4.0, "this code")))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "An agent wrote this code")

    def test_a_real_pause_keeps_two_lines(self):
        merged = craft.merge_cues(cues((0.0, 2.0, "first"), (2.6, 4.0, "second")))
        self.assertEqual(len(merged), 2)


class BindLinesTests(unittest.TestCase):
    def test_bind_refuses_captions_from_another_script(self):
        with self.assertRaises(ValueError):
            craft.bind_lines(script("one two three"), cues((0.0, 1.0, "completely different")))

    def test_bind_assigns_real_times(self):
        bound = craft.bind_lines(script("An agent wrote this code"), cues((3.0, 6.0, "An agent wrote this code")))
        self.assertEqual((bound[0]["start"], bound[0]["end"]), (3.0, 6.0))


class HookTests(unittest.TestCase):
    def test_a_late_first_claim_fails_the_hook_window(self):
        report = craft.analyse(script("A sentence that arrives far too late"),
                               cues((7.5, 10.0, "A sentence that arrives far too late")))
        rule = {r.id: r for r in report.rules}["hook-window"]
        self.assertFalse(rule.ok)

    def test_a_short_early_claim_passes(self):
        report = craft.analyse(script("Ship it or stop it"),
                               cues((0.4, 2.4, "Ship it or stop it")))
        self.assertTrue({r.id: r for r in report.rules}["hook-window"].ok)


class CaptionTests(unittest.TestCase):
    def test_a_cue_shown_too_briefly_fails_reading(self):
        long_line = "x" * 60
        report = craft.analyse(script(long_line), cues((0.0, 1.0, long_line)))
        self.assertFalse({r.id: r for r in report.rules}["caption-read"].ok)

    def test_a_phonetic_respelling_fails_the_clean_rule(self):
        report = craft.analyse(script("You say vee coder"), cues((0.0, 3.0, "You say vee coder")))
        self.assertFalse({r.id: r for r in report.rules}["caption-clean"].ok)


class ShortFormTests(unittest.TestCase):
    def test_a_short_film_is_judged_on_section_length_not_density(self):
        rows = [(i * 6.0, i * 6.0 + 5.0, "one two three four five")
                for i in range(8)]
        report = craft.analyse(script(*["one two three four five"] * 8), cues(*rows))
        ids = {r.id for r in report.rules}
        self.assertIn("section-length", ids)
        self.assertNotIn("interrupt-density", ids)


class BriefToVoiceTests(unittest.TestCase):
    BRIEF = {
        "title": "T",
        "sections": [
            {"id": "a", "lines": [{"text": "first line"}]},
            {"id": "b", "lines": [{"text": "second line"}, {"text": "third line"}]},
        ],
    }

    def test_ids_are_sequential_in_reading_order(self):
        out = brief_to_voice.build(self.BRIEF)
        self.assertEqual([line["id"] for line in out["lines"]], ["L001", "L002", "L003"])

    def test_section_boundaries_get_the_longer_gap(self):
        out = brief_to_voice.build(self.BRIEF)
        self.assertEqual(out["lines"][0]["gap_before"], brief_to_voice.LEAD_IN)
        # Line 2 opens the next section, so it gets the longer gap; line 3 is
        # the second line inside that section and gets the breath.
        self.assertEqual(out["lines"][1]["gap_before"], brief_to_voice.GAP_BETWEEN_SECTIONS)
        self.assertEqual(out["lines"][2]["gap_before"], brief_to_voice.GAP_IN_SECTION)

    def test_the_read_is_slower_than_piper_default(self):
        out = brief_to_voice.build(self.BRIEF)
        self.assertLess(out["lines"][0]["rate"], 1.0)

    def test_an_empty_section_is_an_error(self):
        with self.assertRaises(ValueError):
            brief_to_voice.build({"sections": [{"id": "a", "lines": []}]})


if __name__ == "__main__":
    unittest.main()
