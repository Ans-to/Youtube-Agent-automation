"""Fail-closed tests for technical QA and the YouTube release gate."""
import json
import base64
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from video_studio.quality_audit import file_sha256
from video_studio.release_gate import validate_qc_report
from video_studio.release_evidence import (REQUIRED_CREATIVE_CHECKS, validate_release_evidence)
from video_studio.publish_youtube import validate_approval


class ReleaseQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"test video bytes " * 256)
        self.script = self.root / "script.md"
        self.script.write_text("# Reviewed script\n", encoding="utf-8")
        self.storyboard = self.root / "storyboard.json"
        self.storyboard.write_text('{"scenes": []}\n', encoding="utf-8")
        self.qc_path = self.root / "video.qc.json"
        self.report = {
            "file": str(self.video),
            "video_sha256": file_sha256(self.video),
            "duration_seconds": 12.5,
            "audio_stream_count": 1,
            "warnings": [],
            "passed": True,
            "strict": True,
        }
        self.manifest_path = self.root / "render-manifest.json"
        self.manifest = {"width":1920,"height":1080,"fps":30,"frame_count":375,"duration_seconds":12.5,
            "video_sha256":file_sha256(self.video),
            "impact_pixel_smoke":{"passed":True,"changed_pixels":{"flash":100,"invert":100,"burst":100,"speed-lines":100,"shockwave":100}},
            "impact_events":[{"id":"hit-1","scene":1,"type":"shockwave","frame":15,"timestamp_seconds":.5,"duration_frames":2,"duration_seconds":2/30,"pixel_smoke_test_passed":True}],
            "transitions":[{"scene":1,"type":"none","frames":0}]}
        self.manifest_path.write_text(json.dumps(self.manifest,indent=2),encoding="utf-8")
        image_dir=self.root/"impact-frame-evidence"; image_dir.mkdir()
        self.evidence_image=image_dir/"event-001-shockwave.png"
        self.evidence_image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cBfkAAAAASUVORK5CYII="))
        self.impact_evidence_path=self.root/"impact-frame-evidence.json"
        self.impact_evidence={"schema_version":1,"video_file":self.video.name,"video_sha256":file_sha256(self.video),
            "render_manifest_sha256":file_sha256(self.manifest_path),
            "events":[{"id":"hit-1","type":"shockwave","frame":15,"timestamp_seconds":.5,
                "file":"impact-frame-evidence/event-001-shockwave.png","sha256":file_sha256(self.evidence_image),"size_bytes":self.evidence_image.stat().st_size}]}
        self.impact_evidence_path.write_text(json.dumps(self.impact_evidence,indent=2),encoding="utf-8")
        self.report["video"]={"codec_type":"video","width":1920,"height":1080,"avg_frame_rate":"30/1"}
        self.report["audited_at"]=datetime.now(timezone.utc).isoformat()
        self.report["render_manifest_sha256"]=file_sha256(self.manifest_path)
        self.report["impact_frame_evidence_sha256"]=file_sha256(self.impact_evidence_path)
        self.report["checks"] = {
            "delivery_spec": {"passed": True, "codec": "h264", "width": 1920, "height": 1080,
                "pixel_format": "yuv420p", "field_order": "progressive", "container_bitrate_bps": 4000000},
            "black_frames": {"count": 0, "events": []},
            "freezes": {"count": 0, "events": []},
            "audio_timing": {"verified": True},
            "audio_loudness": {"available": True, "integrated_lufs": -18.0, "true_peak_dbfs": -2.0, "min_loudness_lufs": -24.0, "max_true_peak_dbfs": -1.0},
            "audio_silence": {"count": 0},
            "render_manifest": {"present": True},
            "impact_frame_evidence": {"present": True},
        }
        frame_dir = self.root / "visual-audit-frames"
        frame_dir.mkdir()
        frame_records = []
        fixture_jpeg = bytes([255, 216]) + (b"fixture-frame-" * 100) + bytes([255, 217])
        for index in range(6):
            frame_path = frame_dir / ("frame-%03d.jpg" % (index + 1))
            frame_path.write_bytes(fixture_jpeg)
            frame_records.append({
                "timestamp_seconds": float(index + 1), "file": str(frame_path.relative_to(self.root)).replace("\\", "/"),
                "sha256": file_sha256(frame_path), "size_bytes": frame_path.stat().st_size,
                "status": "PASS", "observations": "Sampled frame has adequate layout and readable visible elements.",
            })
        from video_studio.visual_audit import REQUIRED_CHECKS as REQUIRED_VISUAL_CHECKS
        self.visual_path = self.root / "visual-audit.json"
        visual_report = {
            "schema_version": 1, "status": "PASS", "overall_score": 9.0, "model_id": "unit-test-vision",
            "video_sha256": file_sha256(self.video), "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 12.5, "sample_count": 6,
            "checks": [{"id": name, "status": "PASS", "evidence": "Specific unit-test evidence for this visual rubric check."}
                       for name in REQUIRED_VISUAL_CHECKS],
            "frames": frame_records, "issues": [], "summary": "All fixture frame checks passed.",
        }
        self.visual_path.write_text(json.dumps(visual_report, indent=2), encoding="utf-8")
        self.report["visual_audit_sha256"] = file_sha256(self.visual_path)
        self.report["checks"]["visual_audit"] = {
            "status": "PASS", "score": 9.0, "model_id": "unit-test-vision",
            "sample_count": 6, "sha256": self.report["visual_audit_sha256"],
        }
        self.write_report()
        self.review_path=self.root/"creative-review.json"
        self.review={"schema_version":1,"reviewer":"Local reviewer","reviewed_at":datetime.now(timezone.utc).isoformat(),
            "video_sha256":file_sha256(self.video),"render_manifest_sha256":file_sha256(self.manifest_path),"qc_report_sha256":file_sha256(self.qc_path),
            "reviewed_segments":[{"timestamp_seconds":.5,"notes":"reviewed hit-1 impact visibility and title legibility"}],
            "checks":{check:{"status":"pass","evidence":["Reviewed against exact render."]} for check in REQUIRED_CREATIVE_CHECKS}}
        self.review_path.write_text(json.dumps(self.review,indent=2),encoding="utf-8")
        self.provenance_path=self.root/"asset-provenance.json"
        self.provenance={"schema_version":1,"approved":True,"reviewer":"Local reviewer","reviewed_at":datetime.now(timezone.utc).isoformat(),
            "asset_strategy":"procedural_original","assets":[]}
        self.provenance_path.write_text(json.dumps(self.provenance,indent=2),encoding="utf-8")
        self.style_frame=self.root/"style-frame.png"; self.style_frame.write_bytes(b"style frame fixture")
        self.style_approval_path=self.root/"style-frame-approval.json"
        self.style_approval={"schema_version":1,"approved":True,"reviewer":"Local reviewer",
            "reviewed_at":datetime.now(timezone.utc).isoformat(),"style_frame_sha256":file_sha256(self.style_frame)}
        self.style_approval_path.write_text(json.dumps(self.style_approval,indent=2),encoding="utf-8")
        self.metadata = {
            "title": "Test title",
            "description": "Test description",
            "tags": ["test"],
            "privacy": "private",
            "made_for_kids": "no",
        }
        self.approval = {
            "approved": True,
            "video_file": str(self.video),
            "video_sha256": file_sha256(self.video),
            "package_dir": str(self.root),
            "script_sha256": file_sha256(self.script),
            "storyboard_sha256": file_sha256(self.storyboard),
            "approved_metadata": self.metadata,
            "quality_audit_passed": True,
            "qc_report_sha256": file_sha256(self.qc_path),
            "render_manifest_sha256": file_sha256(self.manifest_path),
            "impact_frame_evidence_sha256": file_sha256(self.impact_evidence_path),
            "creative_review_sha256": file_sha256(self.review_path),
            "asset_provenance_sha256": file_sha256(self.provenance_path),
            "style_frame_sha256": file_sha256(self.style_frame),
            "style_frame_approval_sha256": file_sha256(self.style_approval_path),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_report(self):
        self.qc_path.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")

    def test_strict_passing_report_is_accepted(self):
        self.assertTrue(validate_qc_report(self.report, self.video))

    def test_non_strict_report_is_rejected(self):
        report = dict(self.report, strict=False)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_failed_report_is_rejected(self):
        report = dict(self.report, passed=False)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_report_for_different_video_is_rejected(self):
        report = dict(self.report, video_sha256="0" * 64)
        with self.assertRaises(ValueError):
            validate_qc_report(report, self.video)

    def test_report_with_warnings_or_no_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_qc_report(dict(self.report, warnings=["black frame"]), self.video)
        with self.assertRaises(ValueError):
            validate_qc_report(dict(self.report, audio_stream_count=0), self.video)

    def test_upload_requires_unchanged_passing_audit(self):
        approved = validate_approval(self.approval, self.video, self.metadata)
        self.assertEqual(approved, self.metadata)
        self.qc_path.write_text(json.dumps(dict(self.report, passed=False)), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_approval(self.approval, self.video, self.metadata)

    def test_upload_rejects_approval_without_qc_binding(self):
        approval = dict(self.approval)
        approval.pop("qc_report_sha256")
        with self.assertRaises(ValueError):
            validate_approval(approval, self.video, self.metadata)

    def test_release_evidence_requires_timestamped_event_review(self):
        self.assertTrue(validate_release_evidence(self.root,self.video,self.report))
        review=dict(self.review)
        review["reviewed_segments"]=[{"timestamp_seconds":1.0,"notes":"Reviewed an unrelated scene"}]
        self.review_path.write_text(json.dumps(review),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"timestamped review note"):
            validate_release_evidence(self.root,self.video,self.report)

    def test_manifest_hash_mismatch_fails_closed(self):
        from video_studio.release_evidence import validate_render_manifest
        with self.assertRaisesRegex(ValueError,"exact video SHA-256"):
            validate_render_manifest(dict(self.manifest,video_sha256="0"*64),self.video)


if __name__ == "__main__":
    unittest.main()
