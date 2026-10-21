"""Fail-closed validation for render and creative-release evidence."""
import hashlib
import json
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

REQUIRED_CREATIVE_CHECKS = ['PKG-COMPLETE','VIDEO-VALID','DELIVERY-SPECS','AV-INTEGRITY','AUDIO-PLAN','BLACK-FREEZE','IMPACT-FRAMES','TRANSITIONS','MOTION-CONTINUITY','TEXT-READABILITY','SUBTITLES','SCRIPT-STORYBOARD','ASSET-PROVENANCE','STYLE-FRAME-APPROVAL','CREATIVE-REVIEW','VIDEO-HASH','QC-FRESHNESS','NO-MANDATORY-WARNINGS']


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + " must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(label + " must include a timezone.")
    if parsed > datetime.now(timezone.utc):
        raise ValueError(label + " cannot be in the future.")
    return parsed


def read_json(path, label):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(label + " is missing or invalid JSON: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError(label + " must be a JSON object.")
    return value


def validate_render_manifest(manifest, video, qc_report=None):
    if not isinstance(manifest, dict):
        raise ValueError("Render manifest must be a JSON object.")
    if manifest.get("video_sha256") != sha256_file(video):
        raise ValueError("Render manifest does not match the exact video SHA-256.")
    for field in ("width", "height", "fps", "frame_count"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Render manifest has invalid " + field + ".")
    duration = manifest.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not isfinite(duration) or duration <= 0:
        raise ValueError("Render manifest duration_seconds must be positive.")
    if abs(manifest["frame_count"] / manifest["fps"] - duration) > 1e-6:
        raise ValueError("Render manifest duration does not match frame count and FPS.")
    smoke = manifest.get("impact_pixel_smoke")
    if not isinstance(smoke, dict) or smoke.get("passed") is not True:
        raise ValueError("Renderer impact-frame pixel-smoke evidence is missing or failed.")
    counts = smoke.get("changed_pixels")
    types = ("flash", "invert", "burst", "speed-lines", "shockwave")
    if not isinstance(counts, dict) or any(isinstance(counts.get(name), bool) or not isinstance(counts.get(name), int) or counts[name] < 20 for name in types):
        raise ValueError("Impact-frame pixel-smoke evidence is incomplete or invalid.")
    events = manifest.get("impact_events")
    if not isinstance(events, list):
        raise ValueError("Render manifest impact_events must be a list.")
    seen = set()
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            raise ValueError("Impact event " + str(index) + " must be an object.")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id or event_id in seen:
            raise ValueError("Impact event IDs must be unique and non-empty.")
        seen.add(event_id)
        if event.get("type") not in types:
            raise ValueError("Render manifest contains an unsupported impact effect.")
        frame, length = event.get("frame"), event.get("duration_frames")
        stamp, seconds = event.get("timestamp_seconds"), event.get("duration_seconds")
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame < manifest["frame_count"]:
            raise ValueError("Impact event frame is outside the rendered timeline.")
        if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= 6 or frame + length > manifest["frame_count"]:
            raise ValueError("Impact event frame duration is invalid.")
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not isfinite(stamp) or abs(stamp - frame / manifest["fps"]) > 1e-6:
            raise ValueError("Impact event timestamp does not match frame and FPS.")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not isfinite(seconds) or abs(seconds - length / manifest["fps"]) > 1e-6:
            raise ValueError("Impact event duration does not match frame count and FPS.")
        if event.get("pixel_smoke_test_passed") is not True:
            raise ValueError("Impact event is missing pixel-smoke evidence.")
    if not isinstance(manifest.get("transitions"), list):
        raise ValueError("Render manifest transitions must be a list.")
    if qc_report is not None:
        actual = qc_report.get("video") if isinstance(qc_report, dict) else None
        if not isinstance(actual, dict):
            raise ValueError("Quality report is missing video stream metadata.")
        for field in ("width", "height"):
            if int(actual.get(field, 0) or 0) != manifest[field]:
                raise ValueError("Render manifest " + field + " does not match the rendered MP4.")
        try:
            n, d = str(actual.get("avg_frame_rate", "0/1")).split("/", 1)
            actual_fps = float(n) / float(d)
        except (ValueError, ZeroDivisionError):
            actual_fps = 0
        if actual_fps <= 0 or abs(actual_fps - manifest["fps"]) > .02:
            raise ValueError("Render manifest FPS does not match the rendered MP4.")
        actual_duration = float(qc_report.get("duration_seconds", 0) or 0)
        if actual_duration <= 0 or abs(actual_duration - duration) > max(.08, 1 / manifest["fps"] + .01):
            raise ValueError("Render manifest duration does not match the rendered MP4.")
    return True


def validate_impact_frame_evidence(evidence, evidence_path, video, manifest_path, manifest):
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        raise ValueError("Impact-frame evidence must use schema_version 1.")
    if evidence.get("video_sha256") != sha256_file(video):
        raise ValueError("Impact-frame evidence does not match the exact video SHA-256.")
    if evidence.get("render_manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("Impact-frame evidence does not match the exact render manifest.")
    items, events = evidence.get("events"), manifest.get("impact_events")
    if not isinstance(items, list) or not isinstance(events, list) or len(items) != len(events):
        raise ValueError("Impact-frame evidence must provide exactly one extracted frame per event.")
    root = Path(evidence_path).parent.resolve()
    for index, (item, event) in enumerate(zip(items, events), 1):
        if not isinstance(item, dict):
            raise ValueError("Impact-frame evidence item " + str(index) + " must be an object.")
        for key in ("id", "type", "frame"):
            if item.get(key) != event.get(key):
                raise ValueError("Impact-frame evidence item does not match manifest " + key + ".")
        stamp = item.get("timestamp_seconds")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not isfinite(stamp) or abs(stamp - event["timestamp_seconds"]) > 1e-6:
            raise ValueError("Impact-frame evidence timestamp does not match event timeline.")
        relative = item.get("file")
        if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
            raise ValueError("Impact-frame evidence path must be package-relative.")
        image_path = (root / relative).resolve()
        if not image_path.is_relative_to(root) or not image_path.is_file():
            raise ValueError("Impact-frame evidence image is missing or escapes the package.")
        payload = image_path.read_bytes()
        if len(payload) < 64 or payload[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Impact-frame evidence image is not a valid PNG.")
        if item.get("sha256") != sha256_file(image_path):
            raise ValueError("Impact-frame evidence PNG SHA-256 mismatch.")
        if item.get("size_bytes") != image_path.stat().st_size:
            raise ValueError("Impact-frame evidence PNG size mismatch.")
    return True


def validate_creative_review(review, video, manifest_path, qc_path):
    if not isinstance(review, dict) or review.get("schema_version") != 1:
        raise ValueError("Creative review must use schema_version 1.")
    if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
        raise ValueError("Creative review requires a named reviewer.")
    parse_timestamp(review.get("reviewed_at"), "Creative review reviewed_at")
    for key, path in (("video_sha256", video), ("render_manifest_sha256", manifest_path), ("qc_report_sha256", qc_path)):
        if review.get(key) != sha256_file(path):
            raise ValueError("Creative review does not match the exact " + key.replace("_sha256", "") + ".")
    manifest = read_json(manifest_path, "Render manifest")
    qc = read_json(qc_path, "QC report")
    if qc.get("video_sha256") != sha256_file(video) or qc.get("passed") is not True or qc.get("strict") is not True or qc.get("warnings") != []:
        raise ValueError("Creative review cannot bind a non-passing strict QC report.")
    duration, fps = float(manifest["duration_seconds"]), float(manifest["fps"])
    segments = review.get("reviewed_segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Creative review requires timestamped reviewed_segments.")
    normalized = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Reviewed segment must be an object.")
        stamp, notes = segment.get("timestamp_seconds"), segment.get("notes")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not isfinite(stamp) or stamp < 0 or stamp >= duration:
            raise ValueError("Reviewed segment timestamp must be inside the rendered video.")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("Every reviewed segment requires observed notes.")
        normalized.append((float(stamp), notes.lower()))
    checks = review.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("Creative review checks must be an object.")
    for check_id in REQUIRED_CREATIVE_CHECKS:
        check = checks.get(check_id)
        evidence = check.get("evidence") if isinstance(check, dict) else None
        if not isinstance(check, dict) or check.get("status") != "pass":
            raise ValueError("Creative review check " + check_id + " is missing or not PASS.")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
            raise ValueError("Creative review check " + check_id + " requires explicit evidence.")
    for event in manifest.get("impact_events", []):
        event_id, stamp = str(event["id"]).lower(), float(event["timestamp_seconds"])
        if not any(abs(t - stamp) <= max(1 / fps, .04) and event_id in notes for t, notes in normalized):
            raise ValueError("Impact event " + event_id + " lacks a timestamped review note at its rendered timestamp.")
    return True


def validate_asset_provenance(provenance):
    if not isinstance(provenance, dict) or provenance.get("schema_version") != 1 or provenance.get("approved") is not True:
        raise ValueError("Asset provenance has not been explicitly approved.")
    if not isinstance(provenance.get("reviewer"), str) or not provenance["reviewer"].strip():
        raise ValueError("Asset provenance requires a named reviewer.")
    parse_timestamp(provenance.get("reviewed_at"), "Asset provenance reviewed_at")
    assets, strategy = provenance.get("assets"), provenance.get("asset_strategy")
    if not isinstance(assets, list):
        raise ValueError("Asset provenance assets must be a list.")
    if strategy == "procedural_original" and not assets:
        return True
    if strategy != "listed_assets" or not assets:
        raise ValueError("Asset provenance must record original graphics or list imported assets.")
    for index, asset in enumerate(assets, 1):
        if not isinstance(asset, dict):
            raise ValueError("Asset provenance item " + str(index) + " must be an object.")
        for key in ("name", "sha256", "source", "license", "rights_basis"):
            if not isinstance(asset.get(key), str) or not asset[key].strip():
                raise ValueError("Asset provenance item " + str(index) + " is missing " + key + ".")
        if len(asset["sha256"]) != 64 or any(c not in "0123456789abcdefABCDEF" for c in asset["sha256"]):
            raise ValueError("Asset provenance SHA-256 is invalid.")
    return True


def validate_style_frame_approval(approval, style_frame):
    if not isinstance(approval, dict) or approval.get("schema_version") != 1 or approval.get("approved") is not True:
        raise ValueError("Style frame has not been explicitly approved.")
    if not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip():
        raise ValueError("Style-frame approval requires a named reviewer.")
    parse_timestamp(approval.get("reviewed_at"), "Style-frame reviewed_at")
    if approval.get("style_frame_sha256") != sha256_file(style_frame):
        raise ValueError("Style-frame approval does not match the exact style-frame image.")
    return True


def validate_release_evidence(package_root, video, qc_report):
    root, video = Path(package_root).resolve(), Path(video).resolve()
    files = {
        "manifest": root / "render-manifest.json",
        "impact_evidence": root / "impact-frame-evidence.json",
        "review": root / "creative-review.json",
        "provenance": root / "asset-provenance.json",
        "style_frame": root / "style-frame.png",
        "style_approval": root / "style-frame-approval.json",
        "qc": root / "video.qc.json",
    }
    for path in files.values():
        if not path.is_file():
            raise ValueError("Required release evidence is missing: " + path.name)
    manifest = read_json(files["manifest"], "Render manifest")
    evidence = read_json(files["impact_evidence"], "Impact-frame evidence")
    review = read_json(files["review"], "Creative review")
    provenance = read_json(files["provenance"], "Asset provenance")
    style = read_json(files["style_approval"], "Style-frame approval")
    validate_render_manifest(manifest, video, qc_report)
    validate_impact_frame_evidence(evidence, files["impact_evidence"], video, files["manifest"], manifest)
    if qc_report.get("render_manifest_sha256") != sha256_file(files["manifest"]):
        raise ValueError("QC report has a missing or stale render-manifest binding.")
    if qc_report.get("impact_frame_evidence_sha256") != sha256_file(files["impact_evidence"]):
        raise ValueError("QC report has a missing or stale impact-frame evidence binding.")
    audited = parse_timestamp(qc_report.get("audited_at"), "Quality report audited_at")
    newest = max(video.stat().st_mtime, files["manifest"].stat().st_mtime, files["impact_evidence"].stat().st_mtime)
    if audited.timestamp() + 2 < newest:
        raise ValueError("Quality report predates the current video or renderer evidence.")
    validate_creative_review(review, video, files["manifest"], files["qc"])
    validate_asset_provenance(provenance)
    validate_style_frame_approval(style, files["style_frame"])
    return True
