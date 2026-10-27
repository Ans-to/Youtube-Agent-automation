#!/usr/bin/env python3
"""Create a local approval record bound to the exact video and upload metadata."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


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
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Quality report duration must be finite and greater than zero.")
    if audio_count < 1:
        raise ValueError("The final video must contain an audio stream.")
    if report.get("video_sha256") != sha256(video):
        raise ValueError("Quality report does not match the exact video file.")
    return True


def requires_nokia_profile(root, title=""):
    """Recognize this film when its profile was omitted, without gating unrelated videos.

    The explicit profile is the primary contract. Also fail closed when this
    project's audit/review already exists, its directory name identifies the
    film, or its first script heading / upload title identifies the Nokia empire.
    """
    root = Path(root)
    if (root / "nokia-review.json").exists() or (root / "nokia.audit.json").exists():
        return True
    def matches(text):
        value = str(text).casefold().replace("_", "-")
        return "nokia" in value and ("empire" in value or ("rise" in value and "fall" in value))
    if matches(root.name) or matches(title):
        return True
    try:
        with (root / "script.md").open(encoding="utf-8") as stream:
            for line in stream:
                if line.lstrip().startswith("# "):
                    return matches(line)
    except (OSError, UnicodeError):
        pass
    return False


def validate_project_audit(root, *, required=False):
    """Require a project-specific audit when a package declares a release profile.

    Generic packages retain their existing strict-QA gate. Nokia packages opt in
    by placing release-profile.json beside the video; once approved, both that
    profile and the matching audit remain mandatory during upload.
    """
    root = Path(root).resolve()
    profile_path = root / "release-profile.json"
    if not profile_path.exists():
        if required:
            raise ValueError("The approved project release profile is missing.")
        return None
    try:
        try:
            from .nokia_audit import PROFILE, REPORT_FILE, validate_release_report
        except ImportError:  # executed as a script from video_studio/
            from nokia_audit import PROFILE, REPORT_FILE, validate_release_report
        report = validate_release_report(root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Project-specific audit is not valid: " + str(exc)) from exc
    return {"profile": PROFILE, "profile_sha256": sha256(profile_path),
            "report_sha256": sha256(root / REPORT_FILE), "audit_status": report["status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    root = Path(args.package).resolve()
    video = root / "video.mp4"
    qc_path = root / "video.qc.json"
    for item in (root / "script.md", root / "storyboard.json", video, qc_path):
        if not item.is_file():
            raise SystemExit("Required package file missing: " + item.name)

    try:
        qc_report = json.loads(qc_path.read_text(encoding="utf-8"))
        validate_qc_report(qc_report, video)
        project_audit = validate_project_audit(root, required=requires_nokia_profile(root))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit("Release QA failed; approval is blocked: " + str(exc))

    print("Package:", root)
    print("Strict technical QA: PASS")
    if project_audit:
        print("Project-specific audit: PASS —", project_audit["profile"])
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
    if requires_nokia_profile(root, title=title):
        try:
            current = validate_project_audit(root, required=True)
            if project_audit is not None and current != project_audit:
                raise ValueError("Project audit changed during approval; start over.")
            project_audit = current
        except ValueError as exc:
            raise SystemExit("Nokia project audit is required before approval: " + str(exc))
    expected = "APPROVE PACKAGE " + root.name + " " + video_hash[:12]
    print("Metadata to be approved:")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if input("Type exactly '" + expected + "' to approve: ").strip() != expected:
        raise SystemExit("Approval cancelled.")
    if project_audit:
        # The human may spend time reviewing and typing. An audit valid before
        # the prompts must still match the exact package at confirmation time.
        try:
            if validate_project_audit(root, required=True) != project_audit:
                raise ValueError("Project audit changed during approval.")
        except ValueError as exc:
            raise SystemExit("Nokia evidence changed; approval is blocked: " + str(exc))
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
        "approved_metadata": metadata,
        "script_reviewed": True,
        "storyboard_reviewed": True,
        "publishing_performed": False,
    }
    if project_audit:
        record["project_audit"] = project_audit
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
