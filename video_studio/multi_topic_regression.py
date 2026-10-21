#!/usr/bin/env python3
"""Render and audit ten distinct voiced scripts across unrelated YouTube niches.

Requires the local English Piper CLI/model installed by CI (or an equivalent local setup).
Each MP4 is rendered by the production Canvas2D/FFmpeg path, then independently audited.
This is synthetic regression material, not researched publication-ready content.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
CORPUS = BASE / "multi_topic_regression.json"
FPS = 30
WIDTH = 1920
HEIGHT = 1080
MAX_SILENCE_SECONDS = 0.45


def run(command, timeout=1800):
    return subprocess.run(
        [str(part) for part in command],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def validate_corpus(corpus):
    topics = corpus.get("topics")
    if not isinstance(topics, list) or len(topics) != 10:
        raise ValueError("The regression corpus must contain exactly ten scripts.")
    ids = [str(topic.get("id", "")) for topic in topics]
    niches = [str(topic.get("niche", "")).strip().casefold() for topic in topics]
    titles = [str(topic.get("title", "")).strip().casefold() for topic in topics]
    if any(not value for value in ids + niches + titles):
        raise ValueError("Every regression script needs an ID, niche, and title.")
    if len(set(ids)) != 10 or len(set(niches)) != 10 or len(set(titles)) != 10:
        raise ValueError("All ten scripts must have distinct IDs, niches, and titles.")
    narration_lines = []
    for topic in topics:
        scenes = topic.get("scenes")
        if not isinstance(scenes, list) or len(scenes) != 3:
            raise ValueError(topic["id"] + " must have three scenes.")
        for scene in scenes:
            narration = str(scene.get("narration", "")).strip()
            if len(narration.split()) < 5 or not narration.endswith("."):
                raise ValueError(topic["id"] + " contains a short or malformed narration line.")
            narration_lines.append(narration.casefold())
    if len(narration_lines) != len(set(narration_lines)):
        raise ValueError("The corpus contains duplicate narration lines; scripts must differ.")
    return topics


def write_package(topic, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    storyboard = {
        "title": topic["title"],
        "description": topic["description"],
        "niche": topic["niche"],
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "narration_language": "en",
        "scenes": topic["scenes"],
    }
    storyboard_path = output_dir / "storyboard.json"
    storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    script_lines = [
        "# " + topic["title"],
        "",
        "**Niche:** " + topic["niche"],
        "",
        topic["description"],
        "",
    ]
    for index, scene in enumerate(topic["scenes"], 1):
        script_lines.extend([
            "## Scene " + str(index) + " — " + scene["headline"],
            "",
            scene["narration"],
            "",
        ])
    script_lines.extend([
        "---",
        "",
        "Regression-only synthetic copy. Claims and framing still require source verification before publication.",
        "",
    ])
    (output_dir / "script.md").write_text("\n".join(script_lines), encoding="utf-8")
    (output_dir / "topic.json").write_text(
        json.dumps({
            "id": topic["id"],
            "niche": topic["niche"],
            "title": topic["title"],
            "description": topic["description"],
            "scene_count": len(topic["scenes"]),
            "visual_types": [scene["visual_type"] for scene in topic["scenes"]],
            "narration_lines": [scene["narration"] for scene in topic["scenes"]],
            "synthetic_regression_only": True,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return storyboard_path


def audit_one(topic, output_dir):
    entry = {
        "id": topic["id"],
        "niche": topic["niche"],
        "title": topic["title"],
        "status": "failed",
        "output_dir": output_dir.name,
        "failure_reasons": [],
    }
    try:
        storyboard_path = write_package(topic, output_dir)
        video_path = output_dir / "video.mp4"
        render_log = output_dir / "render.log"
        command = [
            sys.executable,
            str(BASE / "studio.py"),
            "--storyboard", str(storyboard_path.resolve()),
            "--output", str(video_path.resolve()),
            "--language", "en",
            "--with-voice",
        ]
        rendered = run(command, timeout=1800)
        render_log.write_text(
            "$ " + " ".join(command) + "\n\n"
            + (rendered.stdout or "")
            + "\n--- STDERR ---\n"
            + (rendered.stderr or ""),
            encoding="utf-8",
        )
        if rendered.returncode != 0:
            raise RuntimeError(
                "Real TTS-to-MP4 render failed with exit code "
                + str(rendered.returncode) + ". See render.log."
            )
        if not video_path.is_file() or video_path.stat().st_size < 1024:
            raise RuntimeError("Renderer returned success without a valid MP4.")

        qc_path = output_dir / "video.qc.json"
        qc_command = [
            sys.executable,
            str(BASE / "quality_audit.py"),
            str(video_path.resolve()),
            "--strict",
            "--max-silence-seconds", str(MAX_SILENCE_SECONDS),
            "--report", str(qc_path.resolve()),
        ]
        audited = run(qc_command, timeout=900)
        (output_dir / "quality-audit.log").write_text(
            "$ " + " ".join(qc_command) + "\n\n"
            + (audited.stdout or "")
            + "\n--- STDERR ---\n"
            + (audited.stderr or ""),
            encoding="utf-8",
        )
        if not qc_path.is_file():
            raise RuntimeError("Strict quality audit did not write video.qc.json.")
        qc = json.loads(qc_path.read_text(encoding="utf-8"))
        silence = qc.get("checks", {}).get("audio_silence", {})
        silence_events = silence.get("events", [])
        loudness = qc.get("checks", {}).get("audio_loudness", {})
        delivery = qc.get("checks", {}).get("delivery_spec", {})
        if audited.returncode != 0 or qc.get("passed") is not True:
            entry["qc_warnings"] = qc.get("warnings", [])
            raise RuntimeError(
                "Strict technical/audio QA failed. See video.qc.json and quality-audit.log."
            )
        if silence_events:
            entry["silence_events"] = silence_events
            raise RuntimeError("Strict QA reported silence intervals over the configured limit.")
        storyboard_copy = video_path.with_suffix(".storyboard.json")
        if not storyboard_copy.is_file():
            raise RuntimeError("Rendered storyboard with measured speech timing is missing.")
        aligned_storyboard = json.loads(storyboard_copy.read_text(encoding="utf-8"))
        scenes = aligned_storyboard.get("scenes", [])
        pacing = []
        for index, scene in enumerate(scenes, 1):
            try:
                padding = float(scene["narration_padding_seconds"])
                spoken = float(scene["narration_duration_seconds"])
                duration = float(scene["duration_seconds"])
                coverage = float(scene["voice_coverage_ratio"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Scene " + str(index) + " has incomplete measured speech-pacing metadata."
                ) from exc
            if not all(math.isfinite(value) for value in (padding, spoken, duration, coverage)):
                raise RuntimeError("Scene " + str(index) + " has non-finite speech-pacing metadata.")
            if padding > 0.24 or padding < 0 or coverage < 0.88:
                raise RuntimeError(
                    "Scene " + str(index) + " did not meet speech-coverage limits: "
                    + json.dumps({"padding": padding, "coverage": coverage})
                )
            pacing.append({
                "scene": index,
                "headline": scene.get("headline", ""),
                "spoken_seconds": round(spoken, 3),
                "scene_seconds": round(duration, 3),
                "tail_padding_seconds": round(padding, 3),
                "voice_coverage_ratio": round(coverage, 3),
            })
        entry.update({
            "status": "passed",
            "video": video_path.name,
            "video_bytes": video_path.stat().st_size,
            "duration_seconds": round(float(qc["duration_seconds"]), 3),
            "resolution": str(delivery.get("width")) + "x" + str(delivery.get("height")),
            "video_bitrate_bps": delivery.get("container_bitrate_bps"),
            "video_codec": qc.get("video", {}).get("codec_name"),
            "audio_codec": "aac" if qc.get("audio_stream_count") == 1 else None,
            "audio_stream_count": qc.get("audio_stream_count"),
            "integrated_loudness_lufs": loudness.get("integrated_lufs"),
            "true_peak_dbfs": loudness.get("true_peak_dbfs"),
            "silence_event_count": len(silence_events),
            "silence_threshold_seconds": MAX_SILENCE_SECONDS,
            "pacing": pacing,
            "visual_types": [scene.get("visual_type") for scene in aligned_storyboard.get("scenes", [])],
            "qc_file": qc_path.name,
            "storyboard_file": storyboard_path.name,
            "script_file": "script.md",
        })
        print(
            "PASS",
            topic["id"],
            "|",
            topic["niche"],
            "| duration",
            entry["duration_seconds"],
            "s | silence events",
            len(silence_events),
            flush=True,
        )
    except Exception as exc:
        entry["failure_reasons"].append(str(exc))
        entry["error_type"] = type(exc).__name__
        print("FAIL", topic["id"], "|", topic["niche"], "|", str(exc), flush=True)
        traceback.print_exc()
    return entry


def create_contact_sheet(entries, output_root):
    ffmpeg = shutil.which("ffmpeg")
    frames = []
    for entry in entries:
        if entry.get("status") == "passed":
            candidate = output_root / entry["output_dir"] / "style-frame.png"
            if candidate.is_file() and candidate.stat().st_size > 64:
                frames.append(candidate)
    if not ffmpeg or not frames:
        return None, "No FFmpeg or no successfully rendered style frames."
    cell_w, cell_h, columns = 480, 270, 4
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for frame in frames:
        command.extend(["-i", str(frame)])
    filters = []
    labels = []
    for index in range(len(frames)):
        label = "v" + str(index)
        filters.append(
            "[" + str(index) + ":v]scale=" + str(cell_w) + ":" + str(cell_h)
            + ":force_original_aspect_ratio=decrease,pad=" + str(cell_w) + ":" + str(cell_h)
            + ":(ow-iw)/2:(oh-ih)/2,setsar=1[" + label + "]"
        )
        labels.append("[" + label + "]")
    layout = "|".join(
        str((index % columns) * cell_w) + "_" + str((index // columns) * cell_h)
        for index in range(len(frames))
    )
    filters.append(
        "".join(labels) + "xstack=inputs=" + str(len(frames))
        + ":layout=" + layout + ":fill=0x080d18[out]"
    )
    contact = output_root / "ten-niche-contact-sheet.jpg"
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[out]", "-frames:v", "1", "-q:v", "2", str(contact),
    ])
    result = run(command, timeout=300)
    if result.returncode != 0 or not contact.is_file() or contact.stat().st_size < 1024:
        return None, "FFmpeg contact-sheet creation failed: " + (result.stderr or result.stdout)[-1200:]
    return contact.name, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default="workspace/multi-topic-regression")
    args = parser.parse_args()
    try:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        topics = validate_corpus(corpus)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("REGRESSION CORPUS INVALID:", str(exc), file=sys.stderr)
        return 2
    model = os.environ.get("PIPER_MODEL", "").strip()
    if not model or not Path(model).is_file() or not shutil.which("piper"):
        print("PIPER_MODEL and the local piper CLI are required for real voiced regression renders.", file=sys.stderr)
        return 2
    output_arg = Path(args.output_root).expanduser()
    output_root = output_arg.resolve() if output_arg.is_absolute() else (ROOT / output_arg).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "README.txt").write_text(
        "TEN-NICHE VOICED MP4 REGRESSION\n\n"
        "Each folder contains a real local-TTS MP4 produced by video_studio/studio.py, "
        "its script, storyboard, subtitles, render metadata, and strict video.qc.json report. "
        "The scripts are intentionally synthetic regression content, not researched or publication-approved videos. "
        "All ten must pass strict QA for this workflow to pass.\n",
        encoding="utf-8",
    )
    entries = []
    for topic in topics:
        output_dir = output_root / (topic["id"] + "-" + topic["niche"].lower().replace(" ", "-"))
        entries.append(audit_one(topic, output_dir))
        summary = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "all_passed": len(entries) == len(topics) and all(e["status"] == "passed" for e in entries),
            "requested_count": len(topics),
            "completed_count": len(entries),
            "passed_count": sum(e["status"] == "passed" for e in entries),
            "failed_count": sum(e["status"] != "passed" for e in entries),
            "silence_threshold_seconds": MAX_SILENCE_SECONDS,
            "entries": entries,
        }
        (output_root / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    contact_sheet, sheet_error = create_contact_sheet(entries, output_root)
    summary["contact_sheet"] = contact_sheet
    if sheet_error:
        summary["contact_sheet_error"] = sheet_error
        summary["all_passed"] = False
        summary["failed_count"] += 1
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps({
            "all_passed": summary["all_passed"],
            "requested_count": summary["requested_count"],
            "passed_count": summary["passed_count"],
            "failed_count": summary["failed_count"],
            "contact_sheet": summary.get("contact_sheet"),
            "videos": [
                {
                    "id": entry["id"],
                    "niche": entry["niche"],
                    "status": entry["status"],
                    "duration_seconds": entry.get("duration_seconds"),
                    "failure_reasons": entry.get("failure_reasons", []),
                }
                for entry in entries
            ],
        }, ensure_ascii=False, indent=2),
        flush=True,
    )
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
