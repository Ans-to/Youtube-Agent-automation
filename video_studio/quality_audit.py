#!/usr/bin/env python3
"""Fail-closed FFmpeg quality checks for rendered videos.

This catches technical defects, not artistic quality, speech correctness, or true lip-sync.
Use --strict for release candidates; tune thresholds for intentionally static/cinematic content.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .release_evidence import validate_render_manifest, validate_impact_frame_evidence
except ImportError:
    from release_evidence import validate_render_manifest, validate_impact_frame_evidence


# Viewer-retention pacing contract: long unscored gaps are a release defect.
MAX_ALLOWED_SILENCE_SECONDS = 0.30


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def parse_silence_events(stderr, duration):
    starts = [float(x) for x in re.findall(r"silence_start:([0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:([0-9.]+)", stderr)]
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
          max_silence_seconds=MAX_ALLOWED_SILENCE_SECONDS, min_loudness_lufs=-24.0, max_true_peak_dbfs=-1.0):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("Video file missing or too small.")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("Both ffmpeg and ffprobe must be installed.")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration,bit_rate:stream=codec_type,codec_name,profile,pix_fmt,field_order,width,height,avg_frame_rate,duration,sample_rate,channels,start_time,bit_rate",
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
              "warnings": [], "passed": True, "strict": bool(strict),
              "audited_at": datetime.now(timezone.utc).isoformat()}
    # Strict delivery envelope: verify the encoded stream itself, not just the requested storyboard.
    video_stream = videos[0]
    try:
        width, height = int(video_stream.get("width", 0)), int(video_stream.get("height", 0))
        probed_bitrate = int(data.get("format", {}).get("bit_rate", 0) or 0)
    except (TypeError, ValueError):
        width, height, probed_bitrate = 0, 0, 0
    # Some containers report bit_rate as N/A. Derive the aggregate bitrate from
    # actual delivered file size and duration in that case.
    measured_bitrate = probed_bitrate if probed_bitrate > 0 else int(path.stat().st_size * 8 / duration)
    try:
        fps_num, fps_den = str(video_stream.get("avg_frame_rate", "0/1")).split("/", 1)
        measured_fps = float(fps_num) / float(fps_den)
    except (TypeError, ValueError, ZeroDivisionError):
        measured_fps = 0.0
    if measured_fps <= 0:
        measured_fps = 0.0
    # YouTube's published bitrates are recommendations, not universal minimums.
    # Use them as review context, not as a stand-alone rejection for flat graphics.
    if height >= 2160:
        recommended_bitrate = 45_000_000 if measured_fps > 30 else 35_000_000
    elif height >= 1440:
        recommended_bitrate = 24_000_000 if measured_fps > 30 else 16_000_000
    elif height >= 1080:
        recommended_bitrate = 12_000_000 if measured_fps > 30 else 8_000_000
    elif height >= 720:
        recommended_bitrate = 7_500_000 if measured_fps > 30 else 5_000_000
    elif height >= 480:
        recommended_bitrate = 4_000_000 if measured_fps > 30 else 2_500_000
    else:
        recommended_bitrate = 1_500_000 if measured_fps > 30 else 1_000_000
    delivery = {
        "codec": video_stream.get("codec_name"), "width": width, "height": height,
        "pixel_format": video_stream.get("pix_fmt"), "field_order": video_stream.get("field_order"),
        "container_bitrate_bps": measured_bitrate, "probed_container_bitrate_bps": probed_bitrate or None,
        "recommended_sdr_bitrate_bps": recommended_bitrate,
        "below_recommended_bitrate": measured_bitrate < recommended_bitrate,
        "bitrate_is_advisory_not_a_pass_fail_rule": True,
        "passed": True, "requirements": [],
    }
    requirements = [
        (width >= 1 and height >= 1 and min(width, height) >= 1080, "Output must be at least 1080 pixels on its short edge."),
        (video_stream.get("codec_name") == "h264", "Release video must use H.264."),
        (video_stream.get("pix_fmt") == "yuv420p", "Release video must use yuv420p for broad platform compatibility."),
        (video_stream.get("field_order") == "progressive", "Progressive scan could not be confirmed."),
    ]
    for requirement_passed, reason in requirements:
        if not requirement_passed:
            delivery["passed"] = False
            delivery["requirements"].append({"passed": False, "reason": reason})
            if strict:
                report["passed"] = False
                report["warnings"].append(reason)
        else:
            delivery["requirements"].append({"passed": True})
    report["checks"]["delivery_spec"] = delivery
    manifest_path = path.with_name("render-manifest.json")
    evidence_path = path.with_name("impact-frame-evidence.json")
    if manifest_path.is_file():
        report["render_manifest_sha256"] = file_sha256(manifest_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_render_manifest(manifest, path, report)
            report["checks"]["render_manifest"] = {"present": True, "sha256": report["render_manifest_sha256"],
                "video_sha256_matches": True, "impact_event_count": len(manifest["impact_events"]),
                "impact_pixel_smoke_passed": True}
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            report["passed"] = False
            report["warnings"].append("Render manifest failed validation: " + str(exc))
            manifest = {}
        if evidence_path.is_file() and manifest:
            report["impact_frame_evidence_sha256"] = file_sha256(evidence_path)
            try:
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                validate_impact_frame_evidence(evidence, evidence_path, path, manifest_path, manifest)
                report["checks"]["impact_frame_evidence"] = {"present": True, "sha256": report["impact_frame_evidence_sha256"],
                    "video_sha256_matches": True, "manifest_sha256_matches": True,
                    "event_count_matches": len(evidence["events"]) == len(manifest["impact_events"])}
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                report["passed"] = False
                report["warnings"].append("Extracted impact-frame evidence failed validation: " + str(exc))
        else:
            report["impact_frame_evidence_sha256"] = None
            report["checks"]["impact_frame_evidence"] = {"present": False}
            if strict:
                report["passed"] = False
                report["warnings"].append("Extracted impact-frame evidence is missing from the strict release package.")
    else:
        report["render_manifest_sha256"] = None
        report["impact_frame_evidence_sha256"] = None
        report["checks"]["render_manifest"] = {"present": False}
        report["checks"]["impact_frame_evidence"] = {"present": False}
        if strict:
            report["passed"] = False
            report["warnings"].append("Render manifest is missing from the strict release package.")
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
        stream_durations = []
        for stream in audios:
            try:
                value = float(stream.get("duration", 0) or 0)
                stream_durations.append(value if value > 0 else None)
            except (TypeError, ValueError):
                stream_durations.append(None)
        try:
            n, d = str(videos[0].get("avg_frame_rate", "0/1")).split("/", 1)
            video_fps = float(n) / float(d)
        except (ValueError, ZeroDivisionError):
            video_fps = 0.0
        audio_timing = {"video_duration_seconds": duration, "stream_durations_seconds": stream_durations,
                        "max_delta_seconds": max(.25, 1.0/video_fps) if video_fps > 0 else .25, "verified": True}
        for stream_duration in stream_durations:
            if stream_duration is None:
                audio_timing["verified"] = False
                report["warnings"].append("Audio stream duration is unavailable; audio/video duration parity was not verified.")
            elif abs(stream_duration-duration) > audio_timing["max_delta_seconds"]:
                audio_timing["verified"] = False
                report["warnings"].append("Audio/video duration mismatch exceeds configured tolerance.")
        report["checks"]["audio_timing"] = audio_timing
        loud_code, loud_log = run_filter(ffmpeg, path, audio_filter="ebur128=peak=true")
        integrated = re.findall(r"\bI:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*LUFS", loud_log)
        peaks = re.findall(r"\bPeak:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*dBFS", loud_log)
        if loud_code == 0 and integrated and peaks:
            loudness, peak = float(integrated[-1]), float(peaks[-1])
            report["checks"]["audio_loudness"] = {"available": True, "integrated_lufs": loudness,
                "true_peak_dbfs": peak, "min_loudness_lufs": min_loudness_lufs, "max_true_peak_dbfs": max_true_peak_dbfs}
            if loudness < min_loudness_lufs:
                report["passed"] = False
                report["warnings"].append("Integrated audio loudness is below the configured minimum.")
            if peak > max_true_peak_dbfs:
                report["passed"] = False
                report["warnings"].append("Audio true peak exceeds the configured ceiling.")
        else:
            report["checks"]["audio_loudness"] = {"available": False, "note": "FFmpeg ebur128 metrics are unavailable or not parseable."}
            if strict:
                report["passed"] = False
                report["warnings"].append("Strict audio loudness and true-peak measurement is unavailable; release cannot pass without it.")
        if strict:
            for audio in audios:
                if audio.get("codec_name") != "aac":
                    report["passed"] = False
                    report["warnings"].append("Strict delivery requires AAC audio.")
                if str(audio.get("sample_rate", "")) != "48000":
                    report["passed"] = False
                    report["warnings"].append("Strict delivery requires 48 kHz audio.")
                if int(audio.get("channels", 0) or 0) != 2:
                    report["passed"] = False
                    report["warnings"].append("Strict delivery requires stereo audio.")
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
    p.add_argument("--max-silence-seconds", type=float, default=MAX_ALLOWED_SILENCE_SECONDS)
    p.add_argument("--min-loudness-lufs", type=float, default=-24.0)
    p.add_argument("--max-true-peak-dbfs", type=float, default=-1.0)
    p.add_argument("--report", help="Optional JSON report output path.")
    args = p.parse_args()
    try:
        if not (-70.0 <= args.min_loudness_lufs <= 0.0):
            raise ValueError("--min-loudness-lufs must be between -70 and 0.")
        if not (-20.0 <= args.max_true_peak_dbfs <= 0.0):
            raise ValueError("--max-true-peak-dbfs must be between -20 and 0.")
        report = audit(args.video, args.strict, args.max_black_seconds,
                       args.max_freeze_seconds, args.max_silence_seconds,
                       args.min_loudness_lufs, args.max_true_peak_dbfs)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.report:
            report_path = Path(args.report)
            report_path.write_text(rendered + "\n", encoding="utf-8")
            review_template_path = report_path.with_name("creative-review.template.json")
            if review_template_path.is_file():
                review_template = json.loads(review_template_path.read_text(encoding="utf-8"))
                review_template["qc_report_sha256"] = file_sha256(report_path)
                review_template_path.write_text(json.dumps(review_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not report["passed"]:
            raise SystemExit(1)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("VIDEO QUALITY AUDIT FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
