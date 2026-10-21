import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from unittest.mock import patch

from video_studio.visual_audit import (
    REQUIRED_CHECKS,
    _make_contact_sheet,
    build_visual_sample_timestamps,
    scene_context_for_timestamp_range,
    run_visual_audit,
    validate_visual_audit_report,
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class VisualAuditPolicyTests(unittest.TestCase):
    def test_scene_sampling_covers_every_scene_midpoint_and_transitioned_scene(self):
        scenes = [
            {
                "duration_seconds": 2.0,
                "transition_in": "slide-left" if i % 2 else "none",
                "transition_frames": 12,
            }
            for i in range(12)
        ]
        samples = build_visual_sample_timestamps(scenes, duration=24.0, fps=30.0)
        expected_midpoints = [i * 2.0 + 1.0 for i in range(12)]
        for midpoint in expected_midpoints:
            self.assertTrue(any(abs(sample - midpoint) <= 0.001 for sample in samples), midpoint)
        self.assertGreater(len(samples), len(scenes), "Transition samples should supplement scene-midpoint coverage.")

    def test_short_video_still_has_minimum_frame_coverage(self):
        scenes = [{"duration_seconds": 1.0, "transition_in": "none"} for _ in range(4)]
        samples = build_visual_sample_timestamps(scenes, duration=4.0, fps=30.0)
        self.assertGreaterEqual(len(samples), 6)
        self.assertEqual(samples, sorted(set(samples)))

    def test_batch_prompt_context_only_includes_scenes_near_its_samples(self):
        scenes = [{"duration_seconds": 2.0} for _ in range(40)]
        summaries = [{"scene": i + 1, "headline": "scene " + str(i + 1)} for i in range(40)]
        selected = scene_context_for_timestamp_range(scenes, summaries, 80.0, 28.5, 33.5)
        self.assertGreaterEqual(len(selected), 3)
        self.assertLess(len(selected), 8)
        self.assertIn(16, [item["scene"] for item in selected])
        self.assertIn(17, [item["scene"] for item in selected])

    def test_run_visual_audit_batches_all_scene_samples_and_passes_hash_bound_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"final-encoded-video-fixture-" * 400)
            storyboard_path = root / "storyboard.json"
            scenes = [
                {"duration_seconds": 2.0, "transition_in": "slide-left" if i % 2 else "none",
                 "transition_frames": 12, "headline": "Scene " + str(i + 1), "visual_type": "hero"}
                for i in range(10)
            ]
            storyboard_path.write_text(json.dumps({
                "title": "Visual audit batch fixture", "width": 1920, "height": 1080, "fps": 30, "scenes": scenes,
            }), encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "model": {"enabled": True, "base_url": "http://127.0.0.1:8080/v1/chat/completions", "model": "unit-vision"},
                "video_studio": {},
            }), encoding="utf-8")
            fake_jpeg = bytes([255, 216]) + (b"valid-fixture-jpeg-payload-" * 100) + bytes([255, 217])

            def fake_extract(_video, package_root, timestamps, _ffmpeg, fps):
                sample_dir = package_root / "visual-audit-frames"
                sample_dir.mkdir(parents=True, exist_ok=True)
                frames = []
                seen_indices = set()
                for index, stamp in enumerate(timestamps, 1):
                    frame_index = int(round(stamp * fps))
                    if frame_index in seen_indices:
                        continue
                    seen_indices.add(frame_index)
                    actual_stamp = round(frame_index / fps, 3)
                    path = sample_dir / ("frame-%03d.jpg" % (len(frames) + 1))
                    path.write_bytes(fake_jpeg)
                    frames.append({
                        "timestamp_seconds": actual_stamp,
                        "frame_index": frame_index,
                        "file": str(path.relative_to(package_root)).replace("\\", "/"),
                        "sha256": digest(path),
                        "size_bytes": path.stat().st_size,
                    })
                return frames, sample_dir

            def fake_sheet(package_root, frames, sample_dir, _ffmpeg):
                path = sample_dir / "contact-sheet.jpg"
                path.write_bytes(fake_jpeg)
                return {
                    "file": str(path.relative_to(package_root)).replace("\\", "/"),
                    "sha256": digest(path),
                    "size_bytes": path.stat().st_size,
                    "tile_columns": 5,
                    "tile_rows": max(1, (len(frames) + 4) // 5),
                    "sample_count": len(frames),
                }

            def vision_response(request, _timeout):
                prompt = request["messages"][1]["content"][0]["text"]
                marker = "Exact detail-frame timestamps for this batch: "
                timestamps_json = prompt.split(marker, 1)[1].splitlines()[0]
                timestamps = json.loads(timestamps_json)
                verdict = {
                    "overall_score": 9.2,
                    "overall_status": "PASS",
                    "checks": [
                        {"id": check_id, "status": "PASS",
                         "evidence": "Specific measured test evidence for " + check_id + " in this batch."}
                        for check_id in REQUIRED_CHECKS
                    ],
                    "frames": [
                        {"timestamp_seconds": stamp, "status": "PASS",
                         "observations": "Typography and composition are legible in the inspected frame."}
                        for stamp in timestamps
                    ],
                    "issues": [],
                    "summary": "All supplied detail frames passed the strict fixture review.",
                }
                return {"choices": [{"message": {"content": json.dumps(verdict)}}]}

            ffprobe_output = json.dumps({
                "format": {"duration": "20.0"},
                "streams": [{
                    "codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1",
                }],
            })
            completed = subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout=ffprobe_output, stderr="")
            with patch("video_studio.visual_audit.shutil.which", side_effect=lambda name: name), \
                 patch("video_studio.visual_audit.subprocess.run", return_value=completed), \
                 patch("video_studio.visual_audit._extract_visual_frames", side_effect=fake_extract), \
                 patch("video_studio.visual_audit._make_contact_sheet", side_effect=fake_sheet), \
                 patch("video_studio.visual_audit.post_local_model", side_effect=vision_response) as mocked_vision:
                report = run_visual_audit(video, storyboard_path, root, config_path)

            self.assertEqual(report["status"], "PASS")
            self.assertGreaterEqual(report["sample_count"], len(scenes))
            self.assertEqual(report["batch_count"], mocked_vision.call_count)
            self.assertGreater(report["batch_count"], 1)
            self.assertEqual(len(report["checks"]), len(REQUIRED_CHECKS))
            self.assertTrue(validate_visual_audit_report(report, video, root))

    def make_passing_report(self, root):
        video = root / "video.mp4"
        video.write_bytes(b"video-fixture-" * 400)
        frames = []
        # The validator checks evidence integrity and JPEG markers; FFmpeg integration below
        # separately validates that the contact-sheet output can be genuinely decoded.
        jpeg_fixture = bytes([255, 216]) + (b"frame-fixture-" * 200) + bytes([255, 217])
        for index in range(6):
            path = root / ("frame-%03d.jpg" % (index + 1))
            path.write_bytes(jpeg_fixture)
            frames.append({
                "timestamp_seconds": index + 0.5,
                "file": path.name,
                "sha256": digest(path),
                "size_bytes": path.stat().st_size,
                "status": "PASS",
                "observations": "Observed clear typography and stable composition in this frame.",
            })
        contact_path = root / "contact-sheet.jpg"
        contact_path.write_bytes(jpeg_fixture)
        report = {
            "schema_version": 1,
            "status": "PASS",
            "overall_score": 9.0,
            "model_id": "test-vision-model",
            "video_sha256": digest(video),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 8.0,
            "sample_count": len(frames),
            "contact_sheet": {
                "file": contact_path.name,
                "sha256": digest(contact_path),
                "size_bytes": contact_path.stat().st_size,
                "tile_columns": 5,
                "tile_rows": 2,
                "sample_count": len(frames),
            },
            "checks": [
                {"id": check, "status": "PASS", "evidence": "Specific test evidence for this required visual category."}
                for check in REQUIRED_CHECKS
            ],
            "frames": frames,
            "issues": [],
        }
        return video, report

    def test_valid_hash_bound_visual_report_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, report = self.make_passing_report(root)
            self.assertTrue(validate_visual_audit_report(report, video, root))

    def test_low_score_cannot_pass_visual_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, report = self.make_passing_report(root)
            report["overall_score"] = 8.49
            with self.assertRaisesRegex(ValueError, "at least 8.5"):
                validate_visual_audit_report(report, video, root)

    def test_missing_or_duplicate_rubric_item_blocks_visual_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, report = self.make_passing_report(root)
            report["checks"][-1] = dict(report["checks"][0])
            with self.assertRaisesRegex(ValueError, "exactly one result|IDs are missing"):
                validate_visual_audit_report(report, video, root)

    def test_missing_sample_cannot_be_hidden_by_sample_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, report = self.make_passing_report(root)
            report["frames"].pop()
            with self.assertRaisesRegex(ValueError, "matching report record"):
                validate_visual_audit_report(report, video, root)

    def test_stale_sample_hash_blocks_visual_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, report = self.make_passing_report(root)
            (root / report["frames"][0]["file"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "JPEG|hash"):
                validate_visual_audit_report(report, video, root)


class VisualAuditFfmpegIntegrationTests(unittest.TestCase):
    def test_full_sequence_contact_sheet_is_created_by_ffmpeg(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            if os.environ.get("REQUIRE_FFMPEG_TEST") == "1":
                self.fail("Dedicated CI contact-sheet test requires FFmpeg.")
            self.skipTest("FFmpeg is installed in the dedicated later CI stage.")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample_dir = root / "visual-audit-frames"
            sample_dir.mkdir()
            prefix = sample_dir / "frame-%03d.jpg"
            subprocess.run([
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=1",
                "-frames:v", "7", "-q:v", "3", str(prefix),
            ], check=True, capture_output=True, timeout=90)
            frames = []
            for index in range(1, 8):
                path = sample_dir / ("frame-%03d.jpg" % index)
                self.assertTrue(path.is_file(), str(path))
                frames.append({
                    "timestamp_seconds": float(index),
                    "file": str(path.relative_to(root)).replace("\\", "/"),
                    "sha256": digest(path),
                    "size_bytes": path.stat().st_size,
                })
            report = _make_contact_sheet(root, frames, sample_dir, ffmpeg)
            output = root / report["file"]
            self.assertTrue(output.is_file())
            data = output.read_bytes()
            self.assertGreater(len(data), 1024)
            self.assertEqual(data[:2], bytes([255, 216]))
            self.assertEqual(data[-2:], bytes([255, 217]))
            self.assertEqual(report["sample_count"], 7)
            self.assertEqual(report["tile_rows"], 2)


if __name__ == "__main__":
    unittest.main()
