#!/usr/bin/env python3
"""Fail-closed multimodal visual audit."""
import json
import hashlib
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import post_local_model

REQUIRED_CHECKS = ["visual_clarity", "composition_safe_margins", "text_readability", "contrast_color", "visual_consistency", "scene_variety_and_pacing", "artifacts_and_render_defects", "storyboard_alignment"]

def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def validate_visual_audit_report(report, video, package_root=None):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("Missing visual audit report.")
    if report.get("video_sha256") != sha256_file(video):
        raise ValueError("Visual audit does not match exact video.")
    if report.get("status") != "PASS":
        raise ValueError("Visual audit did not PASS.")
    score = report.get("overall_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or score < 8.5 or score > 10:
        raise ValueError("Visual score must be at least 8.5/10.")
    if not isinstance(report.get("model_id"), str) or not report["model_id"].strip():
        raise ValueError("Visual audit model is missing.")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ValueError("Visual checks are missing.")
    indexed = {x.get("id"): x for x in checks if isinstance(x, dict)}
    for name in REQUIRED_CHECKS:
        item = indexed.get(name)
        if not isinstance(item, dict) or str(item.get("status", "")).upper() != "PASS" or not isinstance(item.get("evidence"), str) or len(item["evidence"].strip()) < 20:
            raise ValueError("Required visual check failed: " + name)
    if not isinstance(report.get("issues"), list) or report["issues"]:
        raise ValueError("Unresolved visual issues block release.")
    frames = report.get("frames")
    if not isinstance(frames, list) or len(frames) < 6:
        raise ValueError("At least six frames must be reviewed.")
    root = Path(package_root or Path(video).parent).resolve()
    last = -1.0
    for item in frames:
        if not isinstance(item, dict):
            raise ValueError("Malformed frame record.")
        stamp = item.get("timestamp_seconds")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= last:
            raise ValueError("Frame timestamps must increase.")
        last = stamp
        if str(item.get("status", "")).upper() != "PASS" or not isinstance(item.get("observations"), str) or len(item["observations"].strip()) < 12:
            raise ValueError("Frame did not pass or lacks specific observations.")
        rel = item.get("file")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
            raise ValueError("Frame path must be package-relative.")
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Frame is missing or escapes package.")
        data = path.read_bytes()
        if len(data) < 1024 or data[:2] != bytes([255, 216]) or data[-2:] != bytes([255, 217]):
            raise ValueError("Frame is not a valid JPEG.")
        if item.get("sha256") != sha256_file(path) or item.get("size_bytes") != path.stat().st_size:
            raise ValueError("Frame evidence hash mismatch.")
    try:
        reviewed = datetime.fromisoformat(str(report.get("reviewed_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid audit timestamp.") from exc
    if reviewed.tzinfo is None or reviewed.utcoffset() is None or reviewed > datetime.now(timezone.utc):
        raise ValueError("Audit timestamp must be timezone-aware and not in the future.")
    return True
