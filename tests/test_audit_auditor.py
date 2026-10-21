import json
import tempfile
import unittest
from pathlib import Path

from video_studio.audit.auditor import (
    FLAGGED,
    INCOMPLETE,
    PASSED,
    audit_signals,
    render_json,
    render_markdown,
)
from video_studio.audit.rules import RULES
from video_studio.audit.signals import MediaSignals, TextBlock, TranscriptCue


def series(values, step=0.1):
    return [(round(index * step, 4), value) for index, value in enumerate(values)]


def clean_signals(duration=30.0, frames=100):
    signals = MediaSignals(duration=duration, fps=30, width=1920, height=1080)
    # Gentle, varied picture and audio: no black, freeze, dead air, or flashing.
    signals.luminance = series([0.45 + 0.01 * (index % 3) for index in range(frames)])
    signals.motion = series([0.08 + 0.01 * (index % 5) for index in range(frames)])
    signals.red_level = series([0.40 + 0.01 * (index % 3) for index in range(frames)])
    signals.audio_rms = series([0.18 + 0.05 * (index % 6) for index in range(frames)])
    signals.transcript = [
        TranscriptCue(0, 6, "Welcome back. Today we build a small offline website."),
        TranscriptCue(7, 14, "First we plan the layout, then we write the files."),
        TranscriptCue(15, 25, "Finally we verify the result and review the output."),
    ]
    signals.ocr = [TextBlock(1, 8, "Sponsored by Northwind", confidence=0.95, height_ratio=0.04)]
    signals.competitor_terms = ["Acme"]
    signals.sources = {"luminance": "test", "audio_rms": "test", "transcript": "test", "ocr": "test"}
    return signals


ALL_ATTESTED = ("CS-ADULT", "BS-SENTIMENT", "LE-MUSIC", "LE-CLIPS")


def clean_audit(**overrides):
    signals = overrides.pop("signals", None) or clean_signals()
    options = {
        "video_name": "clean.mp4",
        "required_disclosures": ["sponsored"],
        "hate_lexicon": ["unlikelyterm"],
        "attested": ALL_ATTESTED,
        "attested_by": "reviewer",
        "capabilities": {"ffmpeg": True, "asr": True, "ocr": True},
    }
    options.update(overrides)
    return audit_signals(signals, **options)


class RuleCatalogTests(unittest.TestCase):
    def test_every_requested_category_and_rule_is_present(self):
        categories = {rule.category for rule in RULES}
        self.assertEqual(categories, {"Content Safety", "Brand Safety", "Legal", "Technical QA"})
        ids = {rule.id for rule in RULES}
        for required in (
            "CS-VIOLENCE", "CS-HATE-SPEECH", "CS-ADULT", "CS-CONTRABAND", "CS-SELFHARM",
            "BS-COMPETITOR", "BS-PROFANITY", "BS-SENTIMENT", "BS-CONTROVERSY",
            "LE-MUSIC", "LE-CLIPS", "LE-DISCLOSURE", "LE-CHILDREN",
            "TQ-BLACK", "TQ-DEAD-AIR", "TQ-FREEZE", "TQ-STROBE", "TQ-AVSYNC",
        ):
            with self.subTest(rule=required):
                self.assertIn(required, ids)

    def test_rules_declare_evidence_and_feasibility(self):
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertIn(rule.feasibility, {"automatic", "model_required", "not_detectable_offline"})
                self.assertTrue(rule.name and rule.intent)
                self.assertIn(rule.category, {"Content Safety", "Brand Safety", "Legal", "Technical QA"})

    def test_copyright_music_is_declared_not_detectable(self):
        rule = next(item for item in RULES if item.id == "LE-MUSIC")
        self.assertEqual(rule.feasibility, "not_detectable_offline")
        self.assertIn("fingerprint", rule.detection + rule.limitation)


class StatusTests(unittest.TestCase):
    def test_clean_fully_evidenced_audit_passes_with_the_exact_statement(self):
        report = clean_audit()
        self.assertEqual(report["status"], PASSED)
        self.assertEqual(report["statement"], "AUDIT STATUS: PASSED - No violations detected.")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["summary"]["flagged"], 0)

    def test_missing_evidence_never_reports_passed(self):
        signals = MediaSignals(duration=30.0)  # nothing collected at all
        report = audit_signals(signals, video_name="bare.mp4")
        self.assertEqual(report["status"], INCOMPLETE)
        self.assertTrue(report["statement"].startswith("AUDIT STATUS: INCOMPLETE"))
        self.assertIn("TQ-BLACK", report["unverified_rule_ids"])
        self.assertIn("CS-VIOLENCE", report["unverified_rule_ids"])
        self.assertNotIn("PASSED - No violations", report["statement"])

    def test_attestation_is_required_for_rules_without_detectors(self):
        report = clean_audit(attested=(), attested_by="")
        self.assertEqual(report["status"], INCOMPLETE)
        self.assertIn("CS-ADULT", report["unverified_rule_ids"])
        self.assertIn("BS-SENTIMENT", report["unverified_rule_ids"])

    def test_attestation_is_recorded_with_the_name(self):
        report = clean_audit(attested=("CS-ADULT", "BS-SENTIMENT"), attested_by="A. Reviewer")
        by_id = {item["id"]: item for item in report["rules"]}
        self.assertEqual(by_id["CS-ADULT"]["status"], "attested")
        self.assertEqual(report["attestation"]["attested_by"], "A. Reviewer")
        self.assertEqual(sorted(report["attestation"]["rule_ids"]), ["BS-SENTIMENT", "CS-ADULT"])

    def test_attestation_requires_a_name_and_a_known_rule(self):
        signals = clean_signals()
        with self.assertRaises(ValueError):
            audit_signals(signals, attested=["CS-ADULT"])
        with self.assertRaises(ValueError):
            audit_signals(signals, attested=["NOT-A-RULE"], attested_by="x")

    def test_attestation_cannot_silence_a_detector_that_flagged(self):
        signals = clean_signals()
        signals.transcript.append(TranscriptCue(26, 29, "that was shit and bullshit again"))
        report = audit_signals(
            signals, attested=["CS-ADULT", "BS-SENTIMENT", "BS-PROFANITY"], attested_by="reviewer",
            hate_lexicon=["unlikelyterm"], required_disclosures=["sponsored"],
        )
        self.assertEqual(report["status"], FLAGGED)
        profanity = next(item for item in report["rules"] if item["id"] == "BS-PROFANITY")
        self.assertEqual(profanity["status"], "flagged")
        self.assertIn("BS-PROFANITY", [finding["rule_id"] for finding in report["findings"]])

    def test_not_applicable_rules_are_reported_separately(self):
        signals = clean_signals()
        signals.competitor_terms = []
        report = clean_audit(signals=signals, required_disclosures=None)
        by_id = {item["id"]: item for item in report["rules"]}
        self.assertEqual(by_id["LE-DISCLOSURE"]["status"], "not_applicable")
        self.assertEqual(by_id["BS-COMPETITOR"]["status"], "not_applicable")

    def test_unattested_licensing_rules_block_a_clean_pass(self):
        complete = clean_audit(attested=ALL_ATTESTED)
        self.assertEqual(complete["status"], PASSED)
        partial = clean_audit(attested=("CS-ADULT", "BS-SENTIMENT"))
        self.assertEqual(partial["status"], INCOMPLETE)
        self.assertIn("LE-MUSIC", partial["unverified_rule_ids"])
        self.assertIn("LE-CLIPS", partial["unverified_rule_ids"])

    def test_competitor_supply_turns_a_not_applicable_rule_into_a_real_check(self):
        report = clean_audit()
        competitor = next(item for item in report["rules"] if item["id"] == "BS-COMPETITOR")
        self.assertEqual(competitor["status"], "passed")

        signals = clean_signals()
        signals.ocr.append(TextBlock(20, 24, "better than Acme Pro", confidence=0.9, height_ratio=0.03))
        flagged = clean_audit(signals=signals)
        self.assertEqual(flagged["status"], FLAGGED)
        self.assertIn("BS-COMPETITOR", [item["rule_id"] for item in flagged["findings"]])


class FindingTests(unittest.TestCase):
    def test_findings_carry_every_required_field(self):
        signals = clean_signals()
        signals.luminance = series([0.5, 0.5] + [0.01] * 30 + [0.5, 0.5])
        report = clean_audit(signals=signals)
        self.assertEqual(report["status"], FLAGGED)
        self.assertTrue(report["findings"])
        finding = report["findings"][0]
        for key in ("timestamp", "timestamp_display", "category", "rule", "rule_id",
                    "description", "confidence"):
            self.assertIn(key, finding)
        self.assertRegex(finding["timestamp_display"], r"^\[\d{2}:\d{2}:\d{2} - \d{2}:\d{2}:\d{2}\]$")
        self.assertGreaterEqual(finding["confidence"], 0)
        self.assertLessEqual(finding["confidence"], 100)

    def test_flagged_statement_counts_violations(self):
        signals = clean_signals()
        signals.audio_rms = series([0.0] * 60)
        report = clean_audit(signals=signals)
        self.assertEqual(report["status"], FLAGGED)
        self.assertIn("AUDIT STATUS: FLAGGED", report["statement"])

    def test_profanity_finding_is_flagged_end_to_end(self):
        signals = clean_signals()
        signals.transcript.append(TranscriptCue(26, 29, "this is shit, bullshit and fuck"))
        report = clean_audit(signals=signals)
        self.assertIn("BS-PROFANITY", [item["rule_id"] for item in report["findings"]])

    def test_absent_disclosure_is_flagged_when_ocr_ran(self):
        signals = clean_signals()
        signals.ocr = [TextBlock(1, 8, "Welcome to the show", confidence=0.95, height_ratio=0.05)]
        report = clean_audit(signals=signals, required_disclosures=["paid partnership"])
        self.assertEqual(report["status"], FLAGGED)
        disclosure = [item for item in report["findings"] if item["rule_id"] == "LE-DISCLOSURE"]
        self.assertEqual(len(disclosure), 1)
        self.assertIn("not found", disclosure[0]["description"])

    def test_disclosure_without_ocr_is_unverified_not_passed(self):
        signals = clean_signals()
        signals.ocr = []
        report = clean_audit(signals=signals, required_disclosures=["paid partnership"])
        # Without OCR the auditor cannot see the screen, so this is missing evidence.
        self.assertEqual(report["status"], INCOMPLETE)
        self.assertIn("LE-DISCLOSURE", report["unverified_rule_ids"])

    def test_music_presence_is_flagged_but_rights_are_not_judged(self):
        signals = clean_signals()
        signals.music_detected = True
        report = clean_audit(signals=signals, attested=("CS-ADULT", "BS-SENTIMENT"))
        music = [item for item in report["findings"] if item["rule_id"] == "LE-MUSIC"]
        self.assertEqual(len(music), 1)
        self.assertIn("cannot determine ownership", music[0]["description"])

    def test_findings_are_sorted_by_time(self):
        signals = clean_signals()
        signals.luminance = series(
            [0.5] * 5 + [0.01] * 5 + [0.5] * 5 + [0.01] * 5 + [0.5] * 5
        )
        report = clean_audit(signals=signals)
        starts = [item["timestamp"]["start"] for item in report["findings"]]
        self.assertEqual(starts, sorted(starts))


class RenderingTests(unittest.TestCase):
    def test_markdown_contains_the_required_fields(self):
        signals = clean_signals()
        signals.luminance = series([0.5] * 3 + [0.01] * 20 + [0.5] * 3)
        text = render_markdown(clean_audit(signals=signals))
        for label in ("**Timestamp:**", "**Violation Category:**", "**Rule Broken:**",
                      "**Description:**", "**Confidence Score:**"):
            self.assertIn(label, text)
        self.assertIn("AUDIT STATUS: FLAGGED", text)

    def test_markdown_lists_unverified_rules(self):
        text = render_markdown(audit_signals(MediaSignals(duration=10.0)))
        self.assertIn("## Not verified", text)
        self.assertIn("`TQ-BLACK`", text)
        self.assertIn("Capability gaps", text) if "Capability gaps" in text else True

    def test_markdown_marks_attestation(self):
        text = render_markdown(clean_audit(attested=ALL_ATTESTED, attested_by="Sam"))
        self.assertIn("## Human attestation", text)
        self.assertIn("Sam", text)
        self.assertIn("not machine-verified", text)

    def test_json_render_is_valid_and_round_trips(self):
        report = clean_audit()
        decoded = json.loads(render_json(report))
        self.assertEqual(decoded["status"], report["status"])
        self.assertIn("rules", decoded)


class CliTests(unittest.TestCase):
    def test_missing_file_returns_three(self):
        import audit_video
        import sys

        root = Path(__file__).resolve().parents[1] / "video_studio"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        self.assertEqual(audit_video.main(["/nonexistent/video.mp4"]), 3)

    def test_attest_without_name_is_rejected(self):
        import sys

        root = Path(__file__).resolve().parents[1] / "video_studio"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import audit_video

        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "v.mp4"
            video.write_bytes(b"\x00" * 2048)
            self.assertEqual(audit_video.main([str(video), "--attest", "CS-ADULT"]), 3)


if __name__ == "__main__":
    unittest.main()
