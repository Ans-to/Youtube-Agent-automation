#!/usr/bin/env python3
"""Evidence-normalizing core for the YouTube multimodal content auditor.

Detector adapters (vision/OCR, ASR/audio, temporal context, copyright reference
matching, and lip-sync analysis) supply timestamped observations. This module
validates and normalizes that evidence; it does not pretend to run those models.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RULES = {
    "violence_gore": ("Content Safety", "Violence & Gore"),
    "weapons_self_harm": ("Content Safety", "Weapons & Self-Harm"),
    "hate_harassment": ("Content Safety", "Hate Speech & Harassment"),
    "adult_content": ("Content Safety", "Adult Content"),
    "contraband": ("Content Safety", "Restricted Contraband"),
    "competitor_presence": ("Brand Safety", "Competitor Presence"),
    "profanity": ("Brand Safety", "Profanity Frequency"),
    "aggressive_tone": ("Brand Safety", "Aggressive Tone"),
    "controversial_theme": ("Brand Safety", "Controversial Themes"),
    "copyright_music": ("Legal", "Copyrighted Music Match"),
    "unlicensed_visual": ("Legal", "Unlicensed Visual Match"),
    "missing_disclosure": ("Legal", "Required Disclosure Missing"),
    "unreadable_disclosure": ("Legal", "Required Disclosure Unreadable"),
    "child_safety_privacy": ("Legal", "Children's Privacy & Suitability"),
    "dead_air": ("Technical QA", "Dead Air"),
    "black_screen": ("Technical QA", "Black Screen / Dropped Signal"),
    "frozen_frame": ("Technical QA", "Frozen Frame / Dropped Signal"),
    "audio_levels": ("Technical QA", "Audio Level / Clipping"),
    "photosensitivity": ("Technical QA", "Rapid Flashing / Photosensitivity"),
    "av_sync": ("Technical QA", "Audio-Video / Lip Sync"),
    "ocr_text": ("Content Safety", "Unsafe On-Screen Text"),
    "other": ("Review Required", "Unclassified Finding"),
}
REQUIRED_CAPABILITIES = {
    "object_action_detection", "face_scene_analysis", "ocr",
    "asr_transcription", "text_policy_classification", "audio_event_music_analysis", "temporal_context",
    "brand_logo_matching", "copyright_reference_matching",
    "disclosure_ocr_readability", "children_safety_context",
    "dead_air_black_screen", "photosensitivity", "av_sync",
}
TIMESTAMP_RE = re.compile(r"^\d{2,}:\d{2}:\d{2}(?:\.\d{1,3})?$")


def timestamp(seconds):
    """Format non-negative seconds as HH:MM:SS, preserving hours above 99."""
    total = max(0, int(float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 0:
            raise ValueError("timestamps must be non-negative")
        return float(value)
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"invalid timestamp: {value!r}")
    parts = value.split(":")
    hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"invalid timestamp: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def normalize_finding(item, duration):
    if not isinstance(item, dict):
        raise ValueError("each finding must be a JSON object")
    rule = str(item.get("rule", "other")).strip().lower()
    if rule not in RULES:
        rule = "other"
    start = parse_timestamp(item.get("start_seconds", item.get("start", 0)))
    end = parse_timestamp(item.get("end_seconds", item.get("end", start)))
    if end < start:
        raise ValueError("finding end timestamp precedes its start")
    if duration is not None and end > duration + 1:
        raise ValueError("finding timestamp exceeds video duration")
    confidence = item.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be a number from 0.0 to 1.0")
    description = item.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("finding description must be a non-empty string")
    category, rule_name = RULES[rule]
    return {
        "start": start,
        "end": end,
        "Timestamp": f"{timestamp(start)} - {timestamp(end)}",
        "Violation Category": category,
        "Rule Broken": str(item.get("rule_name") or rule_name),
        "Description": description.strip(),
        "Confidence Score": f"{round(float(confidence) * 100)}%",
        "_rule_id": rule,
        "_evidence": item.get("evidence"),
        "_source": item.get("source", "detector"),
    }


def technical_findings(qc_report):
    """Convert the existing FFmpeg QC checks into timestamped audit findings."""
    findings = []
    duration = float(qc_report.get("duration_seconds", 0) or 0)
    checks = qc_report.get("checks", {})

    for event in checks.get("black_frames", {}).get("events", []):
        if float(event.get("duration", 0)) >= float(checks.get("black_frames", {}).get("threshold_seconds", 0.2)):
            findings.append({
                "start_seconds": event["start"], "end_seconds": event["end"],
                "rule": "black_screen",
                "description": f"Black frame interval lasts {float(event['duration']):.2f} seconds.",
                "confidence": 0.99, "source": "ffmpeg-blackdetect",
            })

    for event in checks.get("freezes", {}).get("events", []):
        findings.append({
            "start_seconds": event.get("start", 0), "end_seconds": event.get("end", event.get("start", 0)),
            "rule": "frozen_frame",
            "description": f"Frame content remained static for {float(event.get('duration', 0)):.2f} seconds; confirm whether intentional.",
            "confidence": 0.80, "source": "ffmpeg-freezedetect",
        })

    silence = checks.get("audio_silence", {})
    threshold = float(silence.get("threshold_seconds", 1.5))
    for event in silence.get("events", []):
        if float(event.get("duration", 0)) >= threshold:
            findings.append({
                "start_seconds": event["start"], "end_seconds": event["end"],
                "rule": "dead_air",
                "description": f"Audio silence lasts {float(event['duration']):.2f} seconds; verify whether this pause is intentional.",
                "confidence": 0.98, "source": "ffmpeg-silencedetect",
            })

    if int(qc_report.get("audio_stream_count", 0) or 0) < 1 and duration > 0:
        findings.append({
            "start_seconds": 0, "end_seconds": duration, "rule": "dead_air",
            "description": "The video contains no audio stream.",
            "confidence": 1.0, "source": "ffprobe",
        })

    photosensitivity = checks.get("photosensitivity", {})
    for event in photosensitivity.get("events", []):
        findings.append({
            "start_seconds": event.get("start", 0),
            "end_seconds": event.get("end", event.get("start", 0)),
            "rule": "photosensitivity",
            "description": (
                f"Potential rapid high-contrast flashing: {event.get('transition_count', 0)} "
                f"large average-luminance transitions within about {event.get('window_seconds', 1.0)} second(s). "
                "This heuristic is not a formal photosensitivity compliance test."
            ),
            "confidence": 0.70, "source": "ffmpeg-signalstats-screening",
        })

    timing = checks.get("audio_timing", {})
    if timing and timing.get("verified") is False:
        findings.append({
            "start_seconds": 0, "end_seconds": duration, "rule": "av_sync",
            "description": "Audio/video stream durations exceed the configured parity tolerance; this is not phoneme-level lip-sync verification.",
            "confidence": 0.99, "source": "ffprobe-duration-parity",
        })

    loudness = checks.get("audio_loudness", {})
    if loudness.get("available"):
        if float(loudness.get("integrated_lufs", 0)) < float(loudness.get("min_loudness_lufs", -24)):
            findings.append({
                "start_seconds": 0, "end_seconds": duration, "rule": "audio_levels",
                "description": f"Integrated loudness {loudness['integrated_lufs']} LUFS is below the configured minimum.",
                "confidence": 0.98, "source": "ffmpeg-ebur128",
            })
        if float(loudness.get("true_peak_dbfs", 0)) > float(loudness.get("max_true_peak_dbfs", -1)):
            findings.append({
                "start_seconds": 0, "end_seconds": duration, "rule": "audio_levels",
                "description": f"True peak {loudness['true_peak_dbfs']} dBFS exceeds the configured ceiling.",
                "confidence": 0.98, "source": "ffmpeg-ebur128",
            })
    return findings


def build_report(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("evidence root must be a JSON object")
    duration = evidence.get("duration_seconds")
    if duration is not None:
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            raise ValueError("duration_seconds must be positive")
        duration = float(duration)

    coverage = evidence.get("coverage", {})
    if not isinstance(coverage, dict):
        raise ValueError("coverage must be a JSON object")
    completed = set()
    failed = {}
    for name, status in coverage.items():
        if status in (True, "complete", "passed"):
            completed.add(name)
        elif status in ("failed", "error", "timeout"):
            failed[name] = str(status)
        elif status not in (False, "not_configured", "skipped", None):
            failed[name] = str(status)
        elif status is False:
            failed[name] = "failed"
    missing = sorted(REQUIRED_CAPABILITIES - completed)
    raw_findings = evidence.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("findings must be a list")
    findings = [normalize_finding(x, duration) for x in raw_findings]
    findings.sort(key=lambda x: (x["start"], x["end"], x["Violation Category"], x["Rule Broken"]))

    public_findings = [{k: v for k, v in finding.items() if not k.startswith("_")} for finding in findings]
    if missing or failed:
        status = "INCOMPLETE"
        summary = "AUDIT STATUS: INCOMPLETE - Required detector coverage is missing or failed."
    elif public_findings:
        status = "FLAGGED"
        summary = "AUDIT STATUS: FLAGGED - Findings detected."
    else:
        status = "PASSED"
        summary = "AUDIT STATUS: PASSED - No violations detected."

    return {
        "audit_status": status,
        "summary": summary,
        "video": evidence.get("video"),
        "duration_seconds": duration,
        "findings": public_findings,
        "coverage": {
            "required_capabilities": sorted(REQUIRED_CAPABILITIES),
            "completed_capabilities": sorted(completed),
            "missing_capabilities": missing,
            "failed_capabilities": failed,
        },
        "limitations": [
            "This core validates detector evidence; it does not itself run vision, OCR, ASR, music fingerprinting, or lip-sync models.",
            "A logo detection is not proof of competitor status without a configured brand reference list.",
            "A music/visual similarity result is not a legal determination of copyright ownership or license status.",
            "Context-sensitive classifications must include temporal evidence; a weapon/tool by itself is not enough to infer violence.",
            "Confidence values are supplied by detector adapters and must be calibrated on representative evaluation data.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", help="JSON evidence bundle emitted by configured detector adapters")
    parser.add_argument("--video", help="Optional MP4 path; runs existing FFmpeg/ffprobe technical checks")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    try:
        if not args.evidence and not args.video:
            parser.error("provide --evidence and/or --video")
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")) if args.evidence else {}
        if args.video:
            try:
                from .quality_audit import audit as run_technical_audit
            except ImportError:
                from quality_audit import audit as run_technical_audit
            qc = run_technical_audit(Path(args.video), strict=False)
            evidence["video"] = str(Path(args.video))
            evidence["duration_seconds"] = qc["duration_seconds"]
            coverage = evidence.setdefault("coverage", {})
            findings = evidence.setdefault("findings", [])
            if not isinstance(coverage, dict) or not isinstance(findings, list):
                raise ValueError("coverage must be an object and findings must be a list")
            coverage["dead_air_black_screen"] = "complete"
            coverage["photosensitivity"] = (
                "complete" if qc.get("checks", {}).get("photosensitivity", {}).get("available") else "failed"
            )
            findings.extend(technical_findings(qc))
            try:
                root_config = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                root_config = {}
            from auditor_adapters import run_optional_detectors
            detector_result = run_optional_detectors(args.video, root_config, technical_coverage=coverage)
            coverage.update(detector_result["coverage"])
            findings.extend(detector_result["findings"])
        report = build_report(evidence)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        return 0 if report["audit_status"] == "PASSED" else 1
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print("AUDIT ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
