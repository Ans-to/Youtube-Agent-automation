#!/usr/bin/env python3
"""Create a local approval record bound to the exact video and upload metadata."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from .release_evidence import parse_timestamp, validate_release_evidence
    from .visual_audit import validate_visual_audit_report
except ImportError:
    from release_evidence import parse_timestamp, validate_release_evidence
    from visual_audit import validate_visual_audit_report


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()



def validate_qc_report(report, video):
    """Reject missing, non-strict, warning-bearing, or mismatched QA reports."""
    if not isinstance(report, dict):
        raise ValueError("Quality report must be a JSON object.")
    if report.get("strict") is not True:
        raise ValueError("A strict quality-audit report is required.")
    if report.get("passed") is not True:
        raise ValueError("The quality audit did not pass.")
    warnings = report.get("warnings")
    if not isinstance(warnings, list) or warnings:
        raise ValueError("Quality report contains warnings or has an invalid warnings field.")
    try:
        duration = float(report.get("duration_seconds", 0))
        audio_count = int(report.get("audio_stream_count", 0))
    except (TypeError, ValueError):
        raise ValueError("Quality report has invalid duration/audio metadata.")
    if duration <= 0:
        raise ValueError("Quality report duration must be greater than zero.")
    if audio_count < 1:
        raise ValueError("The final video must contain an audio stream.")
    if report.get("video_sha256") != sha256(video):
        raise ValueError("Quality report does not match the exact video file.")

    # A self-declared passed=True flag is never sufficient: every release-critical
    # automated check and the separate vision-model verdict must exist and pass.
    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("Quality report is missing its structured checks.")
    required_checks = (
        "delivery_spec", "black_frames", "freezes", "audio_timing",
        "audio_loudness", "audio_silence", "render_manifest", "impact_frame_evidence",
    )
    for name in required_checks:
        if not isinstance(checks.get(name), dict):
            raise ValueError("Quality report is missing required check: " + name)
    delivery = checks["delivery_spec"]
    if delivery.get("passed") is not True or delivery.get("codec") != "h264" or delivery.get("pixel_format") != "yuv420p":
        raise ValueError("Encoded video delivery-specification check did not pass.")
    if min(int(delivery.get("width", 0) or 0), int(delivery.get("height", 0) or 0)) < 1080:
        raise ValueError("Release video must be at least 1080 pixels on its short edge.")
    if delivery.get("field_order") != "progressive":
        raise ValueError("Progressive scan could not be confirmed.")
    try:
        measured_bitrate = int(delivery.get("container_bitrate_bps", 0) or 0)
        recommended_bitrate = int(delivery.get("recommended_sdr_bitrate_bps", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Encoded bitrate measurement is invalid.") from exc
    if measured_bitrate <= 0 or recommended_bitrate <= 0:
        raise ValueError("Encoded bitrate or platform reference could not be measured.")
    if checks["audio_timing"].get("verified") is not True:
        raise ValueError("Audio/video duration parity was not verified.")
    if checks["audio_loudness"].get("available") is not True:
        raise ValueError("Audio loudness and true peak were not measured.")
    loudness = checks["audio_loudness"]
    try:
        integrated_lufs = float(loudness["integrated_lufs"])
        true_peak_dbfs = float(loudness["true_peak_dbfs"])
        minimum_lufs = float(loudness["min_loudness_lufs"])
        maximum_peak = float(loudness["max_true_peak_dbfs"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Audio loudness report lacks numeric measured values and thresholds.") from exc
    import math
    if not all(math.isfinite(value) for value in (integrated_lufs, true_peak_dbfs, minimum_lufs, maximum_peak)):
        raise ValueError("Audio loudness report contains non-finite values.")
    if integrated_lufs < minimum_lufs or true_peak_dbfs > maximum_peak:
        raise ValueError("Measured audio loudness or true peak is outside the strict release range.")
    if checks["audio_silence"].get("count") != 0:
        raise ValueError("Unexpected or unreviewed long audio silence blocks release.")
    if checks["freezes"].get("count") != 0:
        raise ValueError("Freeze detection reported static intervals; release is blocked.")
    if checks["render_manifest"].get("present") is not True or checks["impact_frame_evidence"].get("present") is not True:
        raise ValueError("Render manifest and encoded impact-frame evidence are mandatory.")

    visual_path = video.with_name("visual-audit.json")
    if not visual_path.is_file():
        raise ValueError("Independent multimodal visual audit is missing; release is blocked.")
    try:
        visual_report = json.loads(visual_path.read_text(encoding="utf-8"))
        validate_visual_audit_report(visual_report, video, video.parent)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Independent visual audit failed validation: " + str(exc)) from exc
    actual_visual_sha = sha256(visual_path)
    if report.get("visual_audit_sha256") != actual_visual_sha:
        raise ValueError("Quality report has a missing or stale visual-audit hash.")
    visual_check = checks.get("visual_audit")
    if not isinstance(visual_check, dict) or visual_check.get("status") != "PASS" or visual_check.get("sha256") != actual_visual_sha:
        raise ValueError("Quality report does not bind a passing visual-audit result.")
    if visual_check.get("score", 0) < 8.5 or visual_check.get("sample_count", 0) < 6:
        raise ValueError("Visual audit score or sample coverage is below release thresholds.")
    manifest_path = video.with_name("render-manifest.json")
    evidence_path = video.with_name("impact-frame-evidence.json")
    if not manifest_path.is_file() or not evidence_path.is_file():
        raise ValueError("Strict release requires the render manifest and extracted impact-frame evidence.")
    if report.get("render_manifest_sha256") != sha256(manifest_path):
        raise ValueError("Quality report has a missing or stale render-manifest binding.")
    if report.get("impact_frame_evidence_sha256") != sha256(evidence_path):
        raise ValueError("Quality report has a missing or stale impact-frame evidence binding.")
    audited_at = parse_timestamp(report.get("audited_at"), "Quality report audited_at")
    newest = max(video.stat().st_mtime, manifest_path.stat().st_mtime, evidence_path.stat().st_mtime)
    if audited_at.timestamp() + 2 < newest:
        raise ValueError("Quality report predates the current video or renderer evidence.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    root = Path(args.package).resolve()
    video = root / "video.mp4"
    qc_path = root / "video.qc.json"
    manifest_path = root / "render-manifest.json"
    impact_evidence_path = root / "impact-frame-evidence.json"
    review_path = root / "creative-review.json"
    provenance_path = root / "asset-provenance.json"
    style_frame = root / "style-frame.png"
    style_approval_path = root / "style-frame-approval.json"
    for item in (root / "script.md", root / "storyboard.json", video, qc_path, manifest_path,
                 impact_evidence_path, review_path, provenance_path, style_frame, style_approval_path):
        if not item.is_file():
            raise SystemExit("Required release evidence missing; approval is blocked: " + item.name)

    try:
        qc_report = json.loads(qc_path.read_text(encoding="utf-8"))
        validate_qc_report(qc_report, video)
        validate_release_evidence(root, video, qc_report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit("Strict technical QA failed; approval is blocked: " + str(exc))

    print("Package:", root)
    print("Strict technical QA: PASS")
    video_hash = sha256(video)
    script_path = root / "script.md"
    storyboard_path = root / "storyboard.json"
    script_hash = sha256(script_path)
    storyboard_hash = sha256(storyboard_path)
    print("Video SHA-256:", video_hash)
    print("Script SHA-256:", script_hash)
    print("Storyboard SHA-256:", storyboard_hash)
    print("Approval is tied to the exact video, script, storyboard, and upload metadata.")
    title = input("Exact YouTube title (max 100 characters): ").strip()
    description = input("Exact YouTube description (max 5000 characters): ").strip()
    tags = [tag.strip() for tag in input("Comma-separated tags (optional): ").split(",") if tag.strip()]
    privacy = input("Visibility (private/unlisted/public): ").strip().lower()
    kids = input("Is this video made for kids? (yes/no): ").strip().lower()
    if not title or len(title) > 100 or len(description) > 5000 or len(tags) > 500 or any(len(tag) > 100 for tag in tags):
        raise SystemExit("Invalid metadata length or tag count; approval not created.")
    if privacy not in {"private", "unlisted", "public"} or kids not in {"yes", "no"}:
        raise SystemExit("Visibility must be private/unlisted/public and made-for-kids must be yes/no.")
    metadata = {"title": title, "description": description, "tags": tags,
                "privacy": privacy, "made_for_kids": kids}
    expected = "APPROVE PACKAGE " + root.name + " " + video_hash[:12]
    print("Metadata to be approved:")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if input("Type exactly '" + expected + "' to approve: ").strip() != expected:
        raise SystemExit("Approval cancelled.")
    record = {
        "approved": True,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "package_dir": str(root),
        "video_file": str(video),
        "video_sha256": video_hash,
        "script_sha256": script_hash,
        "storyboard_sha256": storyboard_hash,
        "quality_audit_passed": True,
        "qc_report_sha256": sha256(qc_path),
        "render_manifest_sha256": sha256(manifest_path),
        "impact_frame_evidence_sha256": sha256(impact_evidence_path),
        "creative_review_sha256": sha256(review_path),
        "asset_provenance_sha256": sha256(provenance_path),
        "style_frame_sha256": sha256(style_frame),
        "style_frame_approval_sha256": sha256(style_approval_path),
        "approved_metadata": metadata,
        "script_reviewed": True,
        "storyboard_reviewed": True,
        "publishing_performed": False,
    }
    (root / "release-approval.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    status_path = root / "package-status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({"status": "approved_for_upload", "human_review_required": False,
                       "quality_audit_passed": True, "qc_report_sha256": record["qc_report_sha256"],
                       "publishing_performed": False, "approved_at": record["approved_at"]})
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print("Approval record written:", root / "release-approval.json")
    print("This records approval only; it does not upload or publish.")


if __name__ == "__main__":
    main()
