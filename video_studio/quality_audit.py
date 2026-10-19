#!/usr/bin/env python3
"""Fail-closed FFmpeg quality checks for rendered videos.

This catches technical defects, not artistic quality, speech correctness, or true lip-sync.
Use --strict for release candidates; tune thresholds for intentionally static/cinematic content.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run_filter(binary, path, video_filter=None, audio_filter=None, timeout=300):
    command = [binary, "-hide_banner", "-nostats", "-i", str(path)]
    if video_filter:
        command += ["-vf", video_filter, "-an"]
    elif audio_filter:
        command += ["-vn", "-af", audio_filter]
    command += ["-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stderr


def intervals(stderr, start_pattern, end_pattern=None):
    starts = [float(x) for x in re.findall(start_pattern, stderr)]
    if not end_pattern:
        return starts
    ends = [float(x) for x in re.findall(end_pattern, stderr)]
    return [{"start": s, "end": e, "duration": round(e-s, 3)}
            for s, e in zip(starts, ends) if e >= s]


def audit(path, strict=False, max_black_seconds=0.20, max_freeze_seconds=3.0,
          max_silence_seconds=1.5):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("Video file missing or too small.")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("Both ffmpeg and ffprobe must be installed.")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
         "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60)
    data = json.loads(probe.stdout)
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise ValueError("Expected exactly one video stream.")
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Invalid duration.")
    report = {"file": str(path), "duration_seconds": duration,
              "video": videos[0], "audio_stream_count": len(audios),
              "checks": {}, "warnings": [], "passed": True}
    code, log = run_filter(ffmpeg, path, video_filter="blackdetect=d=0.10:pix_th=0.10")
    if code:
        raise ValueError("FFmpeg black-frame detector failed: " + log[-1000:])
    black = intervals(log, r"black_start:([0-9.]+)", r"black_end:([0-9.]+)")
    report["checks"]["black_frames"] = {"count": len(black), "events": black,
                                         "threshold_seconds": max_black_seconds}
    if any(e["duration"] >= max_black_seconds for e in black):
        report["passed"] = False
        report["warnings"].append("Unexpected black frame interval detected; inspect timestamps.")
    code, log = run_filter(ffmpeg, path, video_filter="freezedetect=n=-50dB:d=" + str(max_freeze_seconds))
    if code:
        raise ValueError("FFmpeg freeze detector failed: " + log[-1000:])
    freezes = intervals(log, r"freeze_start:([0-9.]+)", r"freeze_end:([0-9.]+)")
    # Some FFmpeg versions report freeze_start and freeze_duration instead of freeze_end.
    if not freezes:
        starts = [float(x) for x in re.findall(r"freeze_start:([0-9.]+)", log)]
        durations = [float(x) for x in re.findall(r"freeze_duration:([0-9.]+)", log)]
        freezes = [{"start": s, "end": round(s+d, 3), "duration": d}
                   for s, d in zip(starts, durations)]
    report["checks"]["freezes"] = {"count": len(freezes), "events": freezes,
                                    "threshold_seconds": max_freeze_seconds}
    if freezes:
        report["warnings"].append("Long static intervals found; may be intentional slides or visual dead air.")
        if strict:
            report["passed"] = False
    if audios:
        code, log = run_filter(ffmpeg, path, audio_filter="silencedetect=noise=-45dB:d=" + str(max_silence_seconds))
        if code:
            raise ValueError("FFmpeg silence detector failed: " + log[-1000:])
        starts = [float(x) for x in re.findall(r"silence_start:([0-9.]+)", log)]
        ends = [float(x) for x in re.findall(r"silence_end:([0-9.]+)", log)]
        # A silence continuing to EOF may have no silence_end marker.
        silence_events = [{"start": s, "end": e, "duration": round(e-s, 3)}
                          for s, e in zip(starts, ends) if e >= s]
        report["checks"]["audio_silence"] = {"count": len(silence_events),
            "events": silence_events, "threshold_seconds": max_silence_seconds}
        if silence_events:
            report["warnings"].append("Long audio silence found; intentional pauses need review.")
            if strict:
                report["passed"] = False
    else:
        report["checks"]["audio_silence"] = {"count": None, "events": [],
                                               "note": "No audio stream; narration not verified."}
        if strict:
            report["passed"] = False
            report["warnings"].append("Strict audit requires an audio stream.")
    report["scope_note"] = ("Technical heuristics only. Does not judge artistic quality, Urdu pronunciation, "
                            "factual accuracy, subtitle-to-speech alignment, or phoneme-level lip-sync.")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--max-black-seconds", type=float, default=0.20)
    p.add_argument("--max-freeze-seconds", type=float, default=3.0)
    p.add_argument("--max-silence-seconds", type=float, default=1.5)
    p.add_argument("--report", help="Optional JSON report output path.")
    args = p.parse_args()
    try:
        report = audit(args.video, args.strict, args.max_black_seconds,
                       args.max_freeze_seconds, args.max_silence_seconds)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.report:
            Path(args.report).write_text(rendered + "\n", encoding="utf-8")
        if not report["passed"]:
            raise SystemExit(1)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("VIDEO QUALITY AUDIT FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
