#!/usr/bin/env python3
"""Fail-closed FFmpeg quality checks for rendered videos.

This catches technical defects, not artistic quality, speech correctness, or true lip-sync.
Use --strict for release candidates; tune thresholds for intentionally static/cinematic content.

The ``repeat_frames`` check answers a question the other three cannot: was the
*picture* still, not merely slightly noisy? ``freezedetect`` compares adjacent
frames with a noise tolerance, so grain, a drifting dot field or a creeping
camera makes a frozen composition look alive. See ``repeat_frames.py``. It is
reported on every file; pass ``fail_on_still=True`` (CLI: ``--fail-on-still``)
to make a hold fail the audit, which is what the film renderer does.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_tools():
    """ffmpeg and ffprobe, from the shared adapter when it can be imported."""
    try:
        from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe
    except ImportError:  # run as a script from video_studio/
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe  # type: ignore[no-redef]
    return find_ffmpeg(), find_ffprobe()


def repeat_frame_check(path, max_still_seconds):
    """Measure frozen spans, or explain why the check could not run.

    Imported here rather than at module scope so this audit keeps working on a
    machine without numpy; a check that cannot run is reported as unavailable,
    never as a pass.
    """
    try:
        import importlib.util

        try:
            from video_studio import repeat_frames as module
        except ImportError:
            spec = importlib.util.spec_from_file_location(
                "repeat_frames", Path(__file__).resolve().with_name("repeat_frames.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module.analyse_video(path, max_still_seconds=max_still_seconds)
    except ImportError as exc:
        return {"passed": False, "status": "unavailable", "spans": [],
                "longest_still_seconds": None,
                "statement": "REPEAT CHECK: NOT RUN - %s" % exc}
    except (OSError, RuntimeError, ValueError) as exc:
        return {"passed": False, "status": "unavailable", "spans": [],
                "longest_still_seconds": None,
                "statement": "REPEAT CHECK: NOT RUN - %s" % exc}


def run_filter(binary, path, video_filter=None, audio_filter=None, timeout=1800):
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


def parse_black_events(stderr, duration):
    """Keep a black interval that reaches EOF even if the filter omits its end."""
    starts = [float(x) for x in re.findall(r"black_start:\s*([0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"black_end:\s*([0-9.]+)", stderr)]
    events = [{"start": s, "end": e, "duration": round(e-s, 3)}
              for s, e in zip(starts, ends) if e >= s]
    if starts and (not ends or starts[-1] > ends[-1]):
        tail_start = starts[-1]
        if duration >= tail_start:
            events.append({"start": tail_start, "end": duration,
                           "duration": round(duration-tail_start, 3),
                           "continues_to_eof": True})
    return events


def parse_silence_events(stderr, duration):
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]
    events = [{"start": s, "end": e, "duration": round(e-s, 3)}
              for s, e in zip(starts, ends) if e >= s]
    # FFmpeg omits silence_end when silence persists to EOF.
    if starts and (not ends or starts[-1] > ends[-1]):
        tail_start = starts[-1]
        if duration >= tail_start:
            events.append({"start": tail_start, "end": duration,
                           "duration": round(duration-tail_start, 3),
                           "continues_to_eof": True})
    return events


def audit(path, strict=False, max_black_seconds=0.20, max_freeze_seconds=3.0,
          max_silence_seconds=1.5, max_still_seconds=1.0, fail_on_still=False):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("Video file missing or too small.")
    ffmpeg, ffprobe = _resolve_tools()
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
    report = {"file": str(path.resolve()), "video_sha256": file_sha256(path),
              "duration_seconds": duration, "video": videos[0],
              "audio_stream_count": len(audios), "checks": {},
              "warnings": [], "passed": True, "strict": bool(strict)}
    # The studio intentionally uses a near-black branded background (#0b0b0f).
    # A 0.10 pixel threshold mislabels this designed dark slate as a black frame.
    # Keep the duration heuristic strict but reserve detection for genuinely near-zero pixels.
    code, log = run_filter(ffmpeg, path, video_filter="blackdetect=d=0.10:pix_th=0.025")
    if code:
        raise ValueError("FFmpeg black-frame detector failed: " + log[-1000:])
    black = parse_black_events(log, duration)
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
    still = repeat_frame_check(path, max_still_seconds)
    report["checks"]["repeat_frames"] = still
    if still.get("status") == "failed":
        # Reported on every file. Only fatal when asked for: a slideshow or a
        # title-card product is legitimately static, and this audit is shared
        # with pipelines that render those. The film renderer asks for it.
        if fail_on_still:
            report["passed"] = False
        report["warnings"].append(still["statement"])
        report["warnings"].append("A held picture is a defect in a moving-graphics film: "
                                  "move the content on every spoken beat.")
    elif still.get("status") == "unavailable" and strict:
        report["warnings"].append(still["statement"])
    if audios:
        code, log = run_filter(ffmpeg, path, audio_filter="silencedetect=noise=-45dB:d=" + str(max_silence_seconds))
        if code:
            raise ValueError("FFmpeg silence detector failed: " + log[-1000:])
        silence_events = parse_silence_events(log, duration)
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
    if report["warnings"] and strict:
        report["passed"] = False
    report["scope_note"] = ("Technical heuristics only. Does not judge artistic quality, Urdu/English pronunciation or voice naturalness, "
                            "factual accuracy, subtitle-to-speech alignment, or phoneme-level lip-sync.")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--max-black-seconds", type=float, default=0.20)
    p.add_argument("--max-freeze-seconds", type=float, default=3.0)
    p.add_argument("--max-silence-seconds", type=float, default=1.5)
    p.add_argument("--max-still-seconds", type=float, default=1.0,
                   help="longest acceptable hold in the picture (repeat_frames check)")
    p.add_argument("--fail-on-still", action="store_true",
                   help="a hold longer than --max-still-seconds fails the audit")
    p.add_argument("--report", help="Optional JSON report output path.")
    args = p.parse_args()
    try:
        report = audit(args.video, args.strict, args.max_black_seconds,
                       args.max_freeze_seconds, args.max_silence_seconds,
                       args.max_still_seconds, args.fail_on_still)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        still = report["checks"].get("repeat_frames") or {}
        if still.get("statement"):
            print(still["statement"], file=sys.stderr)
        if args.report:
            Path(args.report).write_text(rendered + "\n", encoding="utf-8")
        if not report["passed"]:
            raise SystemExit(1)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("VIDEO QUALITY AUDIT FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
