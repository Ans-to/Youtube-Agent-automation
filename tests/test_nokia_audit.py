"""Evidence and approval boundaries for the Nokia documentary profile."""
import json
import math
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from video_studio import nokia_audit as audit, release_gate
from video_studio.quality_audit import file_sha256, parse_black_events, parse_silence_events
from video_studio.release_gate import requires_nokia_profile, validate_project_audit
from video_studio.publish_youtube import validate_approval


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sample_clock():
    return [
        {"id": "a", "scene": 1, "start": 0.0, "end": 450.0, "voStart": 0.5},
        {"id": "b", "scene": 2, "start": 450.0, "end": 900.0, "voStart": 450.3},
    ], [
        {"shot": "a", "start": 0.5, "end": 449.5, "vo": 449.0, "text": "Hello Nokia."},
        {"shot": "b", "start": 450.3, "end": 899.5, "vo": 449.2, "text": "Goodbye Nokia."},
    ]


def probe(duration=900.0, subtitles=False):
    streams = [{"codec_type": kind, "start_time": "0", "duration": str(duration)}
               for kind in ("video", "audio")]
    if subtitles:
        streams.append({"codec_type": "subtitle"})
    return {"format": {"duration": str(duration)}, "streams": streams}


def levels(voice_above_music=12.0):
    return {"active_seconds": 400, "narration_active_rms_dbfs": -15,
            "narration_sample_peak_dbfs": -4, "music_under_narration_rms_dbfs": -27,
            "music_sample_peak_dbfs": -16, "voice_above_music_db": voice_above_music}


class ClockAndCaptionTests(unittest.TestCase):
    def test_clock_requires_every_line_to_fit_its_picture(self):
        shots, timing = sample_clock()
        summary = audit.validate_clock(shots, timing, 900)
        self.assertEqual(summary["scenes"], [1, 2])
        self.assertEqual(summary["ending_tail_seconds"], 0.5)
        timing[0]["end"] = 451
        with self.assertRaisesRegex(ValueError, "does not fit"):
            audit.validate_clock(shots, timing, 900)

    def test_clock_rejects_gap_missing_line_and_short_picture(self):
        shots, timing = sample_clock()
        shots[1]["start"] += 1
        with self.assertRaisesRegex(ValueError, "gap"):
            audit.validate_clock(shots, timing, 900)
        shots, timing = sample_clock()
        with self.assertRaisesRegex(ValueError, "counts"):
            audit.validate_clock(shots, timing[:-1], 900)
        with self.assertRaisesRegex(ValueError, "does not cover"):
            audit.validate_clock(shots, timing, 910)

    def test_sidecars_must_match_words_and_timing(self):
        _, timing = sample_clock()
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "video.srt"
            good = ("1\n00:00:00,500 --> 00:07:29,500\nHello Nokia.\n\n"
                    "2\n00:07:30,300 --> 00:14:59,500\nGoodbye Nokia.\n")
            path.write_text(good, encoding="utf-8")
            self.assertEqual(audit.validate_sidecar(path, timing), 2)
            path.write_text(good.replace("Goodbye", "Hello"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                audit.validate_sidecar(path, timing)
            path.write_text(good.replace("00:07:30,300", "00:07:29,600"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                audit.validate_sidecar(path, timing)

    def test_end_of_file_and_spaced_ffmpeg_log_events_are_not_lost(self):
        self.assertEqual(parse_silence_events("silence_start: 8.000", 10)[0]["duration"], 2)
        self.assertEqual(parse_black_events("black_start: 8.000", 10)[0]["duration"], 2)
        self.assertEqual(parse_black_events("black_start:1 black_end: 1.4", 10)[0]["duration"], 0.4)

    def test_alternate_audio_tracks_are_not_silently_treated_as_audited(self):
        data = probe()
        data["streams"].append({"codec_type": "audio", "start_time": "0", "duration": "900"})
        with self.assertRaisesRegex(ValueError, "alternate audio"):
            audit._stream_coverage(data)

    def test_non_finite_values_never_pass_duration(self):
        self.assertIsNone(audit.finite(float("nan")))
        self.assertIsNone(audit.finite(float("inf")))
        with self.assertRaises(ValueError):
            audit._stream_coverage(probe(float("nan")))


class NokiaPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"representative video bytes" * 100)
        (self.root / "script.md").write_text("Hello Nokia. Goodbye Nokia.", encoding="utf-8")
        (self.root / "voice-stem.wav").write_bytes(b"voice stem")
        (self.root / "music-stem.wav").write_bytes(b"music stem")
        self.shots, self.timing = sample_clock()
        storyboard = {"scenes": [
            {"scene": s["scene"], "shots": [{"id": s["id"], "scene": s["scene"],
                "narration": t["text"], "visualCues": [{"cue": "", "visual": "name",
                    "start": s["start"], "end": s["end"]}]}]}
            for s, t in zip(self.shots, self.timing)
        ]}
        write_json(self.root / "storyboard.json", storyboard)
        write_json(self.root / "shots.json", self.shots)
        write_json(self.root / "voice-timing.json", self.timing)
        self.facts = {"coverage": "complete", "claims": [
            {"claim": "Nokia existed", "location": "scene 1", "verdict": "supported",
             "sources": [{"url": "https://example.org/history", "support": "A historical source."}]}
        ]}
        write_json(self.root / "facts.json", self.facts)
        self.qc = {"video_sha256": file_sha256(self.video), "strict": True, "passed": True,
                   "warnings": [], "audio_stream_count": 1, "duration_seconds": 900,
                   "checks": {"black_frames": {"events": [], "threshold_seconds": 0.2},
                              "audio_silence": {"events": [], "threshold_seconds": 1.5}}}
        write_json(self.root / "video.qc.json", self.qc)
        audit.init_review(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def complete_review(self, mode="none"):
        path = self.root / audit.REVIEW_FILE
        review = json.loads(path.read_text(encoding="utf-8"))
        review["reviewed_by"] = "Human reviewer"
        for entry in review["checks"].values():
            entry.update({"status": "pass", "note": "Reviewed the actual evidence and finished film."})
        review["checks"]["visual_relevance"]["scenes"] = [1, 2]
        for beat in review["checks"]["visual_relevance"]["beats"]:
            beat.update({"status": "pass", "subject": "Nokia name", "action": "name appears",
                         "relationship": "The displayed name identifies the subject of the line.",
                         "evidence": "Watched and listened to the complete interval."})
        review["checks"]["captions"]["mode"] = mode
        write_json(path, review)

    def run_audit(self, *, duration=900, lufs=-14, peak=-1.1, separation=12, subtitles=False):
        with patch.object(audit, "probe_video", return_value=probe(duration, subtitles)), \
             patch.object(audit, "measure_master", return_value=(lufs, peak)), \
             patch.object(audit, "measure_stems", return_value=levels(separation)):
            return audit.audit_package(self.root)

    def save_passing(self):
        self.complete_review()
        report = self.run_audit()
        self.assertEqual(report["status"], "PASSED", report["checks"])
        write_json(self.root / audit.REPORT_FILE, report)
        return report

    def test_blank_review_does_not_pass(self):
        report = self.run_audit()
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["checks"]["historical_accuracy"]["status"], "unverified")
        self.assertEqual(report["checks"]["captions"]["status"], "unverified")

    def test_complete_hash_bound_review_can_pass(self):
        self.save_passing()
        self.assertEqual(audit.validate_release_report(self.root)["status"], "PASSED")
        self.assertEqual(validate_project_audit(self.root)["profile"], audit.PROFILE)

    def test_28_minute_cut_failed_even_with_human_review(self):
        self.complete_review()
        report = self.run_audit(duration=1715.39)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["checks"]["duration"]["status"], "failed")

    def test_narration_music_and_master_failures_cannot_be_attested_away(self):
        self.complete_review()
        for kwargs, check in (({"separation": -1}, "music_balance"),
                              ({"peak": -0.5}, "master_audio"),
                              ({"lufs": -20}, "master_audio")):
            with self.subTest(kwargs=kwargs):
                report = self.run_audit(**kwargs)
                self.assertEqual(report["checks"][check]["status"], "failed")
                self.assertEqual(report["status"], "FAILED")

    def test_missing_meter_or_stem_is_unverified_not_pass(self):
        self.complete_review()
        with patch.object(audit, "probe_video", return_value=probe()), \
             patch.object(audit, "measure_master", side_effect=RuntimeError("meter missing")), \
             patch.object(audit, "measure_stems", side_effect=RuntimeError("numpy missing")):
            report = audit.audit_package(self.root)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["checks"]["master_audio"]["status"], "unverified")
        self.assertEqual(report["checks"]["music_balance"]["status"], "unverified")

    def test_fact_ledger_requires_coverage_and_sources(self):
        for change in ("coverage", "url", "unsupported"):
            facts = json.loads(json.dumps(self.facts))
            if change == "coverage":
                facts["coverage"] = "partial"
            elif change == "url":
                facts["claims"][0]["sources"][0]["url"] = "not a source"
            else:
                facts["claims"][0]["verdict"] = "unverified"
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit.validate_facts(facts)

    def test_no_mandatory_scene_or_caption_may_be_ignored(self):
        self.complete_review()
        path = self.root / audit.REVIEW_FILE
        review = json.loads(path.read_text())
        review["checks"]["visual_relevance"]["scenes"] = [1]
        write_json(path, review)
        report = self.run_audit(subtitles=True)
        self.assertEqual(report["checks"]["visual_relevance"]["status"], "unverified")
        self.assertEqual(report["checks"]["captions"]["status"], "failed")

    def test_old_passed_audit_without_beat_check_is_rejected_at_release(self):
        report = self.save_passing()
        del report["checks"]["visual_relevance"]["reviewed_beats"]
        write_json(self.root / audit.REPORT_FILE, report)
        with self.assertRaisesRegex(ValueError, "beat-level audit"):
            audit.validate_release_report(self.root)

    def test_scene_attestation_alone_cannot_approve_semantic_relevance(self):
        self.complete_review()
        path = self.root / audit.REVIEW_FILE
        review = json.loads(path.read_text())
        review["checks"]["visual_relevance"]["beats"].pop()
        write_json(path, review)
        report = self.run_audit()
        self.assertEqual(report["checks"]["visual_relevance"]["status"], "unverified")
        self.assertEqual(report["status"], "INCOMPLETE")

    def test_mismatched_or_changed_beat_cannot_pass(self):
        self.complete_review()
        path = self.root / audit.REVIEW_FILE
        original = json.loads(path.read_text())
        for mutation, wanted in ((lambda beat: beat.update(status="fail"), "failed"),
                                 (lambda beat: beat.update(spoken_span="Different words"), "unverified"),
                                 (lambda beat: beat.update(relationship=""), "unverified")):
            with self.subTest(wanted=wanted):
                review = json.loads(json.dumps(original))
                mutation(review["checks"]["visual_relevance"]["beats"][0])
                write_json(path, review)
                report = self.run_audit()
                self.assertEqual(report["checks"]["visual_relevance"]["status"], wanted)
                self.assertNotEqual(report["status"], "PASSED")

    def test_qc_must_have_actual_gap_measurements(self):
        self.complete_review()
        self.qc["checks"].pop("audio_silence")
        write_json(self.root / "video.qc.json", self.qc)
        # Rebind after changing the evidence; a fresh human review alone cannot fill the gap.
        audit.init_review(self.root, force=True)
        self.complete_review()
        report = self.run_audit()
        self.assertEqual(report["checks"]["gaps"]["status"], "unverified")

    def test_changed_inputs_or_added_captions_invalidate_audit(self):
        self.save_passing()
        (self.root / "music-stem.wav").write_bytes(b"changed stem")
        with self.assertRaisesRegex(ValueError, "changed"):
            audit.validate_release_report(self.root)
        (self.root / "music-stem.wav").write_bytes(b"music stem")
        (self.root / "video.srt").write_text("new caption", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            audit.validate_release_report(self.root)

    def test_upload_rechecks_profile_and_cannot_drop_it_after_approval(self):
        self.save_passing()
        metadata = {"title": "Nokia", "description": "", "tags": [],
                    "privacy": "private", "made_for_kids": "no"}
        approval = {"approved": True, "video_file": str(self.video.resolve()),
                    "video_sha256": file_sha256(self.video), "package_dir": str(self.root.resolve()),
                    "script_sha256": file_sha256(self.root / "script.md"),
                    "storyboard_sha256": file_sha256(self.root / "storyboard.json"),
                    "qc_report_sha256": file_sha256(self.root / "video.qc.json"),
                    "quality_audit_passed": True, "approved_metadata": metadata,
                    "project_audit": validate_project_audit(self.root)}
        self.assertEqual(validate_approval(approval, self.video, metadata), metadata)
        (self.root / "release-profile.json").unlink()
        with self.assertRaisesRegex(ValueError, "Project audit"):
            validate_approval(approval, self.video, metadata)

    def test_explicit_approval_binds_the_project_audit(self):
        self.save_passing()
        phrase = f"APPROVE PACKAGE {self.root.name} {file_sha256(self.video)[:12]}"
        answers = ["Nokia empire", "description", "", "private", "no", phrase]
        with patch("sys.argv", ["release_gate.py", "--package", str(self.root)]), \
             patch("builtins.input", side_effect=answers):
            release_gate.main()
        record = json.loads((self.root / "release-approval.json").read_text())
        self.assertEqual(record["project_audit"], validate_project_audit(self.root))
        self.assertFalse(record["publishing_performed"])
        self.assertEqual(validate_approval(record, self.video, record["approved_metadata"]),
                         record["approved_metadata"])

    def test_approval_blocks_if_evidence_changes_during_confirmation(self):
        self.save_passing()
        answers = iter(["Nokia empire", "description", "", "private", "no"])
        phrase = f"APPROVE PACKAGE {self.root.name} {file_sha256(self.video)[:12]}"
        def answer(prompt):
            if prompt.startswith("Type exactly"):
                (self.root / "music-stem.wav").write_bytes(b"changed during review")
                return phrase
            return next(answers)
        with patch("sys.argv", ["release_gate.py", "--package", str(self.root)]), \
             patch("builtins.input", side_effect=answer):
            with self.assertRaisesRegex(SystemExit, "evidence changed"):
                release_gate.main()
        self.assertFalse((self.root / "release-approval.json").exists())

    def test_project_identity_requires_profile_even_if_it_was_removed(self):
        (self.root / "release-profile.json").unlink()
        self.assertTrue(requires_nokia_profile(self.root))  # existing review is a project marker
        with self.assertRaisesRegex(ValueError, "profile is missing"):
            validate_project_audit(self.root, required=requires_nokia_profile(self.root))

    def test_generic_project_keeps_existing_gate(self):
        (self.root / "release-profile.json").unlink()
        (self.root / audit.REVIEW_FILE).unlink()
        self.assertFalse(requires_nokia_profile(self.root, title="A short tech explainer"))
        self.assertTrue(requires_nokia_profile(self.root, title="Nokia: The Rise and Fall"))
        self.assertIsNone(validate_project_audit(self.root))


class ActualStemMeterTests(unittest.TestCase):
    def test_active_voice_and_music_levels_are_measured(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is unavailable")
        rate = 8000
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            t = np.arange(rate * 2) / rate
            voice = np.where(t < 1, 0.25 * np.sin(2 * math.pi * 190 * t), 0)
            music = 0.035 * np.sin(2 * math.pi * 310 * t)
            for filename, data in (("voice.wav", voice), ("music.wav", music)):
                with wave.open(str(root / filename), "wb") as out:
                    out.setparams((1, 2, rate, len(data), "NONE", "not compressed"))
                    out.writeframes((data * 32767).astype("<i2").tobytes())
            result = audit.measure_stems(root / "voice.wav", root / "music.wav", 2)
            self.assertAlmostEqual(result["narration_active_rms_dbfs"], -15.05, delta=0.15)
            self.assertAlmostEqual(result["music_under_narration_rms_dbfs"], -32.13, delta=0.15)
            self.assertAlmostEqual(result["narration_sample_peak_dbfs"], -12.04, delta=0.15)
            self.assertGreater(result["voice_above_music_db"], 16)
            self.assertAlmostEqual(result["active_seconds"], 1.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
