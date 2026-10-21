import json
import tempfile
import unittest
from pathlib import Path

from video_studio.audit import detectors, vision
from video_studio.audit.auditor import audit_signals
from video_studio.audit.signals import MediaSignals, TranscriptCue


def observation(start, end, kind, label, confidence=0.8, box=None):
    return vision.Observation(start=start, end=end, kind=kind, label=label,
                              confidence=confidence, box=box)


def document(items, provider="test-detector"):
    return {"schema_version": 1, "provider": provider, "observations": items}


class ObservationParsingTests(unittest.TestCase):
    def test_valid_document_round_trips(self):
        observations, provider = vision.parse_observations(document([
            {"start": 1.0, "end": 3.0, "kind": "object", "label": "knife", "confidence": 0.8},
            {"start": 0.0, "end": 5.0, "kind": "face", "label": "face", "confidence": 0.9,
             "box": [0.3, 0.1, 0.2, 0.3]},
        ]))
        self.assertEqual(provider, "test-detector")
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].label, "knife")
        self.assertEqual(observations[1].box, (0.3, 0.1, 0.2, 0.3))
        self.assertAlmostEqual(observations[0].duration, 2.0)

    def test_invalid_documents_are_rejected_with_clear_errors(self):
        cases = [
            ([], "must contain a JSON object"),
            ({"observations": "nope"}, "'observations' array"),
            ({"observations": ["x"]}, "must be an object"),
            ({"observations": [{"start": 0, "end": 1, "kind": "alien", "label": "x"}]}, "unsupported kind"),
            ({"observations": [{"start": 0, "end": 1, "kind": "object", "label": ""}]}, "needs a label"),
            ({"observations": [{"start": 2, "end": 1, "kind": "object", "label": "x"}]}, "invalid time range"),
            ({"observations": [{"start": 0, "end": 1, "kind": "object", "label": "x", "confidence": 2}]}, "confidence"),
            ({"observations": [{"start": 0, "end": 1, "kind": "face", "label": "f", "box": [0, 0, 2, 1]}]}, "normalized"),
            ({"observations": [{"start": 0, "end": 1, "kind": "face", "label": "f", "box": [0, 0, 1]}]}, "box must be"),
        ]
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as caught:
                    vision.parse_observations(payload)
                self.assertIn(message, str(caught.exception))

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs.json"
            path.write_text(json.dumps(document([
                {"start": 0, "end": 2, "kind": "scene", "label": "kitchen", "confidence": 0.7}
            ])), encoding="utf-8")
            observations, provider = vision.load_observations(path)
        self.assertEqual(observations[0].label, "kitchen")
        self.assertEqual(provider, "test-detector")

    def test_bad_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obs.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                vision.load_observations(path)


class TemporalEventTests(unittest.TestCase):
    def test_consecutive_observations_merge_into_one_event(self):
        events = vision.build_events([
            observation(0.0, 1.0, "object", "knife"),
            observation(1.2, 2.0, "object", "knife"),
            observation(2.4, 4.0, "object", "Knife"),
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].label, "knife")
        self.assertAlmostEqual(events[0].start, 0.0)
        self.assertAlmostEqual(events[0].end, 4.0)
        self.assertEqual(events[0].observations, 3)

    def test_distant_observations_stay_separate(self):
        events = vision.build_events([
            observation(0.0, 1.0, "object", "gun"),
            observation(20.0, 21.0, "object", "gun"),
        ])
        self.assertEqual(len(events), 2)

    def test_scene_labels_attach_to_events(self):
        events = vision.build_events([
            observation(0.0, 10.0, "scene", "kitchen"),
            observation(2.0, 4.0, "object", "knife"),
        ])
        knife = next(event for event in events if event.label == "knife")
        self.assertIn("kitchen", knife.scenes)

    def test_faces_are_excluded_from_content_events(self):
        events = vision.build_events([observation(0.0, 5.0, "face", "face", box=(0.1, 0.1, 0.2, 0.2))])
        self.assertEqual(events, [])


class VisualDetectorTests(unittest.TestCase):
    def test_weapon_in_a_kitchen_is_downgraded_not_flagged_as_violence(self):
        findings = detectors.detect_visual_content([
            observation(0.0, 10.0, "scene", "kitchen"),
            observation(0.0, 10.0, "action", "cooking", 0.8),
            observation(1.0, 6.0, "object", "knife", 0.9),
        ])
        weapon = [item for item in findings if item.rule_id == "CS-WEAPONS"]
        self.assertEqual(len(weapon), 1)
        self.assertLess(weapon[0].confidence, 30)
        self.assertIn("tool or prop", weapon[0].description)
        self.assertFalse([item for item in findings if item.rule_id == "CS-VIOLENCE"])

    def test_weapon_without_benign_context_is_confident(self):
        findings = detectors.detect_visual_content([observation(1.0, 5.0, "object", "gun", 0.95)])
        self.assertEqual(len(findings), 1)
        self.assertGreater(findings[0].confidence, 40)

    def test_fighting_action_is_violence(self):
        findings = detectors.detect_visual_content([observation(3.0, 6.0, "action", "punching", 0.9)])
        self.assertTrue(findings)
        self.assertEqual(findings[0].rule_id, "CS-VIOLENCE")
        self.assertGreater(findings[0].confidence, 50)

    def test_blood_maps_to_violence(self):
        findings = detectors.detect_visual_content([observation(0.0, 2.0, "object", "blood", 0.8)])
        self.assertEqual(findings[0].rule_id, "CS-VIOLENCE")

    def test_adult_and_contraband_labels_map_to_their_rules(self):
        findings = detectors.detect_visual_content([
            observation(0.0, 2.0, "object", "nudity", 0.9),
            observation(3.0, 5.0, "object", "syringe", 0.7),
        ])
        rules = {item.rule_id for item in findings}
        self.assertIn("CS-ADULT", rules)
        self.assertIn("CS-CONTRABAND", rules)

    def test_brief_detection_has_lower_confidence_than_a_long_one(self):
        brief = detectors.detect_visual_content([observation(0.0, 0.3, "object", "gun", 0.9)])
        long = detectors.detect_visual_content([observation(0.0, 6.0, "object", "gun", 0.9)])
        self.assertLess(brief[0].confidence, long[0].confidence)

    def test_unknown_labels_produce_nothing(self):
        self.assertEqual(detectors.detect_visual_content([
            observation(0.0, 2.0, "object", "chair", 0.9),
            observation(0.0, 2.0, "action", "sitting", 0.9),
        ]), [])

    def test_logo_matches_a_competitor(self):
        findings = detectors.detect_visual_competitors(
            [observation(4.0, 7.0, "logo", "Acme Corp", 0.88)], ["Acme"]
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "BS-COMPETITOR")

    def test_unrelated_logo_does_not_match(self):
        self.assertEqual(detectors.detect_visual_competitors(
            [observation(4.0, 7.0, "logo", "Northwind", 0.9)], ["Acme"]
        ), [])


class MouthMotionTests(unittest.TestCase):
    def test_mouth_series_samples_only_inside_the_face_box(self):
        # 3x3 grid over the frame; a face at y=0.2..0.5 puts the mouth in the
        # middle row, so motion is placed in the middle-centre cell (index 4).
        grid = [(index * 0.1, tuple(0.5 if cell == 4 else 0.0 for cell in range(9)))
                for index in range(20)]
        faces = [observation(0.0, 2.0, "face", "face", box=(0.4, 0.2, 0.2, 0.3))]
        series = vision.mouth_motion_series(grid, faces)
        self.assertTrue(series)
        self.assertTrue(all(value > 0 for _, value in series))

    def test_no_faces_means_no_series(self):
        grid = [(0.0, tuple([0.1] * 9))]
        self.assertEqual(vision.mouth_motion_series(grid, []), [])


class AuditorVisualIntegrationTests(unittest.TestCase):
    def test_visual_evidence_alone_satisfies_content_rules(self):
        signals = MediaSignals(duration=10.0)
        signals.observations = [observation(2.0, 5.0, "object", "gun", 0.95)]
        report = audit_signals(signals, video_name="x.mp4")
        weapons = next(item for item in report["rules"] if item["id"] == "CS-WEAPONS")
        self.assertEqual(weapons["status"], "flagged")
        finding = next(item for item in report["findings"] if item["rule_id"] == "CS-WEAPONS")
        self.assertRegex(finding["timestamp_display"], r"^\[00:00:02 - 00:00:05\]$")
        self.assertGreater(finding["confidence"], 40)

    def test_text_and_vision_are_combined(self):
        signals = MediaSignals(duration=10.0)
        signals.transcript = [TranscriptCue(0, 3, "he had a gun")]
        signals.observations = [observation(6.0, 8.0, "action", "punching", 0.9)]
        report = audit_signals(signals, video_name="x.mp4")
        weapon_rules = [item for item in report["findings"] if item["rule_id"] == "CS-WEAPONS"]
        violence = [item for item in report["findings"] if item["rule_id"] == "CS-VIOLENCE"]
        self.assertTrue(weapon_rules)
        self.assertTrue(violence)

    def test_competitor_logo_is_flaggable(self):
        signals = MediaSignals(duration=10.0, competitor_terms=["Acme"])
        signals.observations = [observation(1.0, 4.0, "logo", "Acme", 0.9)]
        report = audit_signals(signals, video_name="x.mp4")
        self.assertIn("BS-COMPETITOR", [item["rule_id"] for item in report["findings"]])

    def test_without_vision_rules_remain_unverified(self):
        report = audit_signals(MediaSignals(duration=10.0), video_name="x.mp4")
        for rule_id in ("CS-VIOLENCE", "CS-WEAPONS", "CS-ADULT"):
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id, report["unverified_rule_ids"])


if __name__ == "__main__":
    unittest.main()
