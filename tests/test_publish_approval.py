import json
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

from video_studio.publish_youtube import sha256, validate_approval
from video_studio.release_evidence import REQUIRED_CREATIVE_CHECKS


class PublishApprovalTests(unittest.TestCase):
    def make_package(self, directory):
        root=Path(directory)
        video=root/"video.mp4"; video.write_bytes(b"fake video bytes for approval hashing")
        script=root/"script.md"; script.write_text("approved narration",encoding="utf-8")
        storyboard=root/"storyboard.json"; storyboard.write_text('{"scenes": []}',encoding="utf-8")
        manifest_path=root/"render-manifest.json"
        manifest={"width":1920,"height":1080,"fps":30,"frame_count":375,"duration_seconds":12.5,"video_sha256":sha256(video),
            "impact_pixel_smoke":{"passed":True,"changed_pixels":{"flash":100,"invert":100,"burst":100,"speed-lines":100,"shockwave":100}},
            "impact_events":[{"id":"hit-1","scene":1,"type":"shockwave","frame":15,"timestamp_seconds":.5,"duration_frames":2,"duration_seconds":2/30,"pixel_smoke_test_passed":True}],
            "transitions":[{"scene":1,"type":"none","frames":0}]}
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        evidence_dir=root/"impact-frame-evidence"; evidence_dir.mkdir()
        image=evidence_dir/"event-001-shockwave.png"
        import base64
        image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cBfkAAAAASUVORK5CYII="))
        evidence_path=root/"impact-frame-evidence.json"
        evidence={"schema_version":1,"video_file":video.name,"video_sha256":sha256(video),"render_manifest_sha256":sha256(manifest_path),
            "events":[{"id":"hit-1","type":"shockwave","frame":15,"timestamp_seconds":.5,"file":"impact-frame-evidence/event-001-shockwave.png","sha256":sha256(image),"size_bytes":image.stat().st_size}]}
        evidence_path.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        from video_studio.visual_audit import REQUIRED_CHECKS as REQUIRED_VISUAL_CHECKS
        frame_dir=root/"visual-audit-frames"; frame_dir.mkdir()
        frame_records=[]
        fixture_jpeg=bytes([255,216])+(b"fixture-frame-"*100)+bytes([255,217])
        for index in range(6):
            frame_path=frame_dir/("frame-%03d.jpg"%(index+1)); frame_path.write_bytes(fixture_jpeg)
            frame_records.append({"timestamp_seconds":float(index+1),
                "file":str(frame_path.relative_to(root)).replace("\\","/"),
                "sha256":sha256(frame_path),"size_bytes":frame_path.stat().st_size,
                "status":"PASS","observations":"Frame fixture has readable layout and clear visual structure."})
        visual_path=root/"visual-audit.json"
        visual={"schema_version":1,"status":"PASS","overall_score":9.0,"model_id":"unit-test-vision",
            "video_sha256":sha256(video),"reviewed_at":datetime.now(timezone.utc).isoformat(),
            "duration_seconds":12.5,"sample_count":6,
            "checks":[{"id":name,"status":"PASS","evidence":"Specific test evidence for this visual rubric check."}
                for name in REQUIRED_VISUAL_CHECKS],
            "frames":frame_records,"issues":[],"summary":"Unit-test visual evidence."}
        visual_path.write_text(json.dumps(visual,indent=2),encoding="utf-8")
        qc_path=root/"video.qc.json"
        qc={"file":str(video.resolve()),"video_sha256":sha256(video),"duration_seconds":12.5,
            "video":{"codec_type":"video","width":1920,"height":1080,"avg_frame_rate":"30/1"},"audio_stream_count":1,
            "checks":{
                "delivery_spec":{"passed":True,"codec":"h264","width":1920,"height":1080,"pixel_format":"yuv420p","field_order":"progressive","container_bitrate_bps":4000000},
                "black_frames":{"count":0,"events":[]},"freezes":{"count":0,"events":[]},
                "audio_timing":{"verified":True},"audio_loudness":{"available":True,"integrated_lufs":-18.0,"true_peak_dbfs":-2.0},
                "audio_silence":{"count":0},"render_manifest":{"present":True},"impact_frame_evidence":{"present":True},
                "visual_audit":{"status":"PASS","score":9.0,"model_id":"unit-test-vision","sample_count":6,"sha256":sha256(visual_path)}},
            "visual_audit_sha256":sha256(visual_path),"warnings":[],"passed":True,"strict":True,
            "audited_at":datetime.now(timezone.utc).isoformat(),
            "render_manifest_sha256":sha256(manifest_path),"impact_frame_evidence_sha256":sha256(evidence_path)}
        qc_path.write_text(json.dumps(qc),encoding="utf-8")
        review_path=root/"creative-review.json"
        review={"schema_version":1,"reviewer":"Local reviewer","reviewed_at":datetime.now(timezone.utc).isoformat(),
            "video_sha256":sha256(video),"render_manifest_sha256":sha256(manifest_path),"qc_report_sha256":sha256(qc_path),
            "reviewed_segments":[{"timestamp_seconds":.5,"notes":"reviewed hit-1 impact visibility"}],
            "checks":{c:{"status":"pass","evidence":["Reviewed against exact render."]} for c in REQUIRED_CREATIVE_CHECKS}}
        review_path.write_text(json.dumps(review),encoding="utf-8")
        provenance_path=root/"asset-provenance.json"
        provenance={"schema_version":1,"approved":True,"reviewer":"Local reviewer","reviewed_at":datetime.now(timezone.utc).isoformat(),"asset_strategy":"procedural_original","assets":[]}
        provenance_path.write_text(json.dumps(provenance),encoding="utf-8")
        style_frame=root/"style-frame.png"; style_frame.write_bytes(b"style frame fixture")
        style_approval_path=root/"style-frame-approval.json"
        style_approval={"schema_version":1,"approved":True,"reviewer":"Local reviewer","reviewed_at":datetime.now(timezone.utc).isoformat(),"style_frame_sha256":sha256(style_frame)}
        style_approval_path.write_text(json.dumps(style_approval),encoding="utf-8")
        metadata={"title":"Approved title","description":"Approved description","tags":["AI","Technology"],"privacy":"private","made_for_kids":"no"}
        approval={"approved":True,"package_dir":str(root.resolve()),"video_file":str(video.resolve()),"video_sha256":sha256(video),
            "script_sha256":sha256(script),"storyboard_sha256":sha256(storyboard),"quality_audit_passed":True,"qc_report_sha256":sha256(qc_path),
            "render_manifest_sha256":sha256(manifest_path),"impact_frame_evidence_sha256":sha256(evidence_path),
            "creative_review_sha256":sha256(review_path),"asset_provenance_sha256":sha256(provenance_path),
            "style_frame_sha256":sha256(style_frame),"style_frame_approval_sha256":sha256(style_approval_path),
            "approved_metadata":{**metadata,"tags":list(metadata["tags"])}}
        return video,metadata,approval

    def test_accepts_exact_video_and_metadata_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            self.assertEqual(validate_approval(approval, video.resolve(), metadata), metadata)

    def test_rejects_changed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            metadata["privacy"] = "public"
            with self.assertRaisesRegex(ValueError, "differs from the approved record"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_modified_video_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            video.write_bytes(b"changed after approval")
            with self.assertRaisesRegex(ValueError, "Video changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_script_changed_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            (Path(directory) / "script.md").write_text("changed narration", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Script changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_storyboard_changed_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            (Path(directory) / "storyboard.json").write_text("{\"scenes\": [\"changed\"]}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Storyboard changed after approval"):
                validate_approval(approval, video.resolve(), metadata)

    def test_rejects_wrong_package_path(self):
        with tempfile.TemporaryDirectory() as directory:
            video, metadata, approval = self.make_package(directory)
            approval["package_dir"] = str(Path(directory).parent.resolve())
            with self.assertRaisesRegex(ValueError, "parent directory"):
                validate_approval(approval, video.resolve(), metadata)


if __name__ == "__main__":
    unittest.main()
