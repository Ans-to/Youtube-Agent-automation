#!/usr/bin/env python3
"""Create a local approval record bound to the exact video and upload metadata."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    root = Path(args.package).resolve()
    video = root / "video.mp4"
    for item in (root / "script.md", root / "storyboard.json", video):
        if not item.is_file():
            raise SystemExit("Required package file missing: " + item.name)

    print("Package:", root)
    video_hash = sha256(video)
    print("Video SHA-256:", video_hash)
    print("Approval covers both the video hash and all upload metadata.")
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
        "script_sha256": sha256(root / "script.md"),
        "storyboard_sha256": sha256(root / "storyboard.json"),
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
                       "publishing_performed": False, "approved_at": record["approved_at"]})
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print("Approval record written:", root / "release-approval.json")
    print("This records approval only; it does not upload or publish.")


if __name__ == "__main__":
    main()
