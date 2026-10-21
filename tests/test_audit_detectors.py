import unittest

from video_studio.audit import detectors
from video_studio.audit.signals import (
    TextBlock,
    TranscriptCue,
    best_lag,
    format_interval,
    format_timestamp,
    merge_intervals,
    Interval,
)


def series(values, step=0.1):
    return [(round(index * step, 4), value) for index, value in enumerate(values)]


class TimestampTests(unittest.TestCase):
    def test_format_and_interval(self):
        self.assertEqual(format_timestamp(0), "00:00:00")
        self.assertEqual(format_timestamp(3661.9), "01:01:01")
        self.assertEqual(format_timestamp(-5), "00:00:00")
        self.assertEqual(format_interval(12, 14), "[00:00:12 - 00:00:14]")

    def test_merge_intervals_joins_overlaps_and_gaps(self):
        merged = merge_intervals([Interval(0, 2), Interval(1.5, 3), Interval(5, 6)], gap=0.5)
        self.assertEqual([(item.start, item.end) for item in merged], [(0, 3), (5, 6)])

    def test_best_lag_detects_a_shifted_series(self):
        reference = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        lag, score = best_lag(reference, [0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0], 0.1)
        self.assertAlmostEqual(lag, 0.1, places=6)
        self.assertGreater(score, 0.85)


class BlackFreezeDeadAirTests(unittest.TestCase):
    def test_black_run_is_reported_with_timestamps(self):
        values = [0.5, 0.5, 0.02, 0.01, 0.02, 0.01, 0.02, 0.4]
        findings = detectors.detect_black(series(values, 0.25), min_seconds=0.5)
        self.assertEqual(len(findings), 1)
        self.assertAlmostEqual(findings[0].start, 0.5, places=3)
        self.assertGreaterEqual(findings[0].end, 1.5)
        self.assertEqual(findings[0].rule_id, "TQ-BLACK")
        self.assertGreater(findings[0].confidence, 90)

    def test_brief_black_frames_are_not_flagged(self):
        findings = detectors.detect_black(series([0.5, 0.01, 0.5], 0.1), min_seconds=0.5)
        self.assertEqual(findings, [])

    def test_dead_air_respects_minimum_duration(self):
        quiet = [0.0] * 30
        values = [0.2] * 5 + quiet + [0.2] * 5
        findings = detectors.detect_dead_air(series(values, 0.1), window=0.1, min_seconds=2.0)
        self.assertEqual(len(findings), 1)
        self.assertAlmostEqual(findings[0].start, 0.5, places=2)
        self.assertAlmostEqual(findings[0].end, 3.5, places=2)

    def test_short_gap_is_not_dead_air(self):
        values = [0.2] * 5 + [0.0] * 5 + [0.2] * 5
        self.assertEqual(detectors.detect_dead_air(series(values, 0.1), min_seconds=2.0), [])

    def test_freeze_detection(self):
        values = [0.3, 0.2] + [0.0] * 40 + [0.2]
        findings = detectors.detect_freeze(series(values, 0.1), min_seconds=3.0)
        self.assertEqual(len(findings), 1)
        self.assertIn("static", findings[0].description)

    def test_freeze_ignores_normal_motion(self):
        values = [0.3 + 0.05 * (index % 3) for index in range(60)]
        self.assertEqual(detectors.detect_freeze(series(values, 0.1), min_seconds=3.0), [])


class StrobeTests(unittest.TestCase):
    def test_rapid_alternation_is_flagged(self):
        values = [0.05 if index % 2 else 0.95 for index in range(40)]
        findings = detectors.detect_strobe(series(values, 0.1))
        self.assertTrue(findings)
        self.assertEqual(findings[0].rule_id, "TQ-STROBE")
        self.assertIn("flashes per second", findings[0].description)

    def test_slow_fade_is_not_a_strobe(self):
        values = [0.5 + 0.01 * (index % 5) for index in range(60)]
        self.assertEqual(detectors.detect_strobe(series(values, 0.1)), [])

    def test_red_flashes_are_counted_separately(self):
        red = [0.1 if index % 2 else 0.8 for index in range(40)]
        findings = detectors.detect_strobe(series([0.4] * 40, 0.1), series(red, 0.1))
        self.assertTrue(any("red" in finding.description.lower() for finding in findings))


class AvSyncTests(unittest.TestCase):
    def test_aligned_envelopes_pass(self):
        pattern = [0.0, 0.8, 0.0, 0.6] * 20
        findings = detectors.detect_av_sync(series(pattern, 0.1), series(pattern, 0.1))
        self.assertEqual(findings, [])

    def test_lagging_picture_is_flagged(self):
        # Impulse every second in audio; the picture reacts 0.3 s late.
        audio = [1.0 if index % 10 == 0 else 0.0 for index in range(100)]
        visual = [1.0 if index % 10 == 3 else 0.0 for index in range(100)]
        findings = detectors.detect_av_sync(series(audio, 0.1), series(visual, 0.1))
        self.assertEqual(len(findings), 1)
        self.assertIn("lags", findings[0].description)
        self.assertAlmostEqual(findings[0].evidence["lag_seconds"], 0.3, places=2)

    def test_leading_picture_is_flagged_in_the_other_direction(self):
        audio = [1.0 if index % 10 == 3 else 0.0 for index in range(100)]
        visual = [1.0 if index % 10 == 0 else 0.0 for index in range(100)]
        findings = detectors.detect_av_sync(series(audio, 0.1), series(visual, 0.1))
        self.assertEqual(len(findings), 1)
        self.assertIn("leads", findings[0].description)


class ProfanityTests(unittest.TestCase):
    def test_rate_above_threshold_flags(self):
        text = "that was shit and fucking bullshit, damn"
        findings = detectors.detect_profanity(text, duration=30.0, max_per_minute=2.0)
        self.assertEqual(len(findings), 1)
        self.assertIn("per minute", findings[0].description)

    def test_low_rate_pass_and_clean_text_pass(self):
        self.assertEqual(detectors.detect_profanity("one shit", duration=600.0), [])
        self.assertEqual(detectors.detect_profanity("a perfectly clean sentence", duration=10.0), [])

    def test_obfuscation_is_normalized(self):
        findings = detectors.detect_profanity("sh*t sh1t f*ck", duration=30.0, max_per_minute=1.0)
        self.assertTrue(findings)

    def test_scunthorpe_problem_does_not_trigger(self):
        text = "we visited Scunthorpe and discussed the assistant class"
        self.assertEqual(detectors.detect_profanity(text, duration=30.0, max_per_minute=1.0), [])


class ContentTermTests(unittest.TestCase):
    def test_weapon_in_benign_context_gets_low_confidence(self):
        cues = [
            TranscriptCue(0, 4, "Today the chef sharpens the knife before cooking"),
            TranscriptCue(5, 9, "the kitchen is ready for the recipe"),
        ]
        findings = detectors.detect_content_terms(cues, [])
        self.assertTrue(findings)
        weapons = [item for item in findings if item.rule_id == "CS-WEAPONS"]
        self.assertTrue(weapons)
        self.assertLessEqual(weapons[0].confidence, 20)
        self.assertIn("benign context", weapons[0].description)

    def test_weapon_without_context_is_higher_confidence_but_not_certain(self):
        cues = [TranscriptCue(0, 3, "he pulled a gun on the crowd")]
        findings = [item for item in detectors.detect_content_terms(cues, []) if item.rule_id == "CS-WEAPONS"]
        self.assertTrue(findings)
        self.assertGreater(findings[0].confidence, 30)
        self.assertLess(findings[0].confidence, 60)

    def test_self_harm_and_contraband_map_to_their_rules(self):
        cues = [TranscriptCue(0, 3, "talk of suicide and cocaine")]
        ids = {item.rule_id for item in detectors.detect_content_terms(cues, [])}
        self.assertIn("CS-SELFHARM", ids)
        self.assertIn("CS-CONTRABAND", ids)

    def test_ocr_blocks_are_scanned_too(self):
        blocks = [TextBlock(0, 2, "blood everywhere", confidence=0.9, height_ratio=0.03)]
        findings = detectors.detect_content_terms([], blocks)
        self.assertTrue(any(item.rule_id == "CS-VIOLENCE" for item in findings))

    def test_clean_text_produces_nothing(self):
        cues = [TranscriptCue(0, 3, "welcome back to the channel, today we build a website")]
        self.assertEqual(detectors.detect_content_terms(cues, []), [])


class BrandAndLegalTests(unittest.TestCase):
    def test_competitor_terms_are_matched_in_text(self):
        findings = detectors.detect_competitors("we compared it with Acme Tools", ["Acme"], duration=60)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "BS-COMPETITOR")

    def test_competitor_absent(self):
        self.assertEqual(detectors.detect_competitors("nothing here", ["Acme"], duration=60), [])

    def test_controversy_themes_are_grouped(self):
        findings = detectors.detect_controversy("the election and the earthquake aftermath", duration=60)
        self.assertEqual(len(findings), 1)
        self.assertIn("politics", findings[0].description)

    def test_missing_disclosure_is_flagged(self):
        findings = detectors.detect_disclosures([], ["sponsored"], duration=30)
        self.assertEqual(len(findings), 1)
        self.assertIn("not found", findings[0].description)
        self.assertEqual(findings[0].confidence, 90.0)

    def test_legible_disclosure_passes(self):
        blocks = [TextBlock(1, 6, "Sponsored by Acme", confidence=0.9, height_ratio=0.04)]
        self.assertEqual(detectors.detect_disclosures(blocks, ["sponsored"], duration=30), [])

    def test_illegible_disclosure_is_flagged(self):
        blocks = [TextBlock(1, 6, "Sponsored", confidence=0.9, height_ratio=0.005)]
        findings = detectors.detect_disclosures(blocks, ["sponsored"], duration=30)
        self.assertEqual(len(findings), 1)
        self.assertIn("illegible", findings[0].description)

    def test_brief_disclosure_is_flagged(self):
        blocks = [TextBlock(1, 1.4, "Sponsored", confidence=0.9, height_ratio=0.04)]
        findings = detectors.detect_disclosures(blocks, ["sponsored"], duration=30, min_display_seconds=1.5)
        self.assertEqual(len(findings), 1)
        self.assertIn("below the", findings[0].description)

    def test_children_and_data_cues_together_flag(self):
        findings = detectors.detect_children_context("fun toys for kids, enter your email to win", duration=60)
        self.assertEqual(len(findings), 1)
        self.assertIn("screening heuristic", findings[0].description)

    def test_children_cues_alone_do_not_flag(self):
        self.assertEqual(detectors.detect_children_context("fun toys for kids", duration=60), [])


if __name__ == "__main__":
    unittest.main()
