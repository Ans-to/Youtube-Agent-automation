#!/usr/bin/env python3
"""Fail-closed MP4 validation; required audio must contain measurable, non-silent sound."""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def parse_audio_stats(stderr):
    """Parse FFmpeg volumedetect output; return dBFS peak and mean."""
    peak_match = re.search(r"max_volume:\s*(-?inf|-?[0-9.]+) dB", stderr, re.I)
    mean_match = re.search(r"mean_volume:\s*(-?inf|-?[0-9.]+) dB", stderr, re.I)
    if not peak_match or not mean_match:
        raise ValueError("Could not measure audio loudness; audio QA cannot pass on missing measurements.")
    def number(match):
        return float("-inf") if match.group(1).lower() == "-inf" else float(match.group(1))
    return {"peak_dbfs": number(peak_match), "mean_dbfs": number(mean_match)}


def inspect(path, width=None, height=None, fps=None, require_audio=False,
            minimum_mean_dbfs=-35.0, maximum_peak_dbfs=-0.1):
    video = Path(path)
    if not video.is_file() or video.stat().st_size < 1024:
        raise ValueError("Video file is missing or unexpectedly small.")
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe:
        raise ValueError("ffprobe is required; install FFmpeg with ffprobe on PATH.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,duration",
         "-of", "json", str(video)],
        check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        raise ValueError("Expected exactly one video stream, found " + str(len(video_streams)))
    stream = video_streams[0]
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Video duration is invalid.")
    if stream.get("codec_name") != "h264":
        raise ValueError("Expected H.264 output, found " + str(stream.get("codec_name")))
    if width is not None and stream.get("width") != width:
        raise ValueError("Expected width " + str(width) + ", found " + str(stream.get("width")))
    if height is not None and stream.get("height") != height:
        raise ValueError("Expected height " + str(height) + ", found " + str(stream.get("height")))
    if require_audio and not audio_streams:
        raise ValueError("Narration was requested but no audio stream exists.")
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    numerator, denominator = (int(x) for x in rate.split("/", 1))
    actual_fps = numerator / denominator if denominator else 0
    if fps is not None and abs(actual_fps - fps) > 0.15:
        raise ValueError("Expected frame rate " + str(fps) + ", found " + str(actual_fps))
    audio_report = None
    if require_audio:
        if not ffmpeg:
            raise ValueError("FFmpeg is required to measure required narration audio.")
        measured = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a:0",
             "-vn", "-af", "volumedetect", "-f", "null", "-"],
            check=False, capture_output=True, text=True, timeout=120)
        stats = parse_audio_stats(measured.stderr)
        if stats["mean_dbfs"] == float("-inf") or stats["mean_dbfs"] < minimum_mean_dbfs:
            raise ValueError("Required audio is silent or too quiet: mean " + str(stats["mean_dbfs"]) +
                             " dBFS; minimum is " + str(minimum_mean_dbfs) + " dBFS.")
        if stats["peak_dbfs"] > maximum_peak_dbfs:
            raise ValueError("Audio peak exceeds the safe ceiling: " + str(stats["peak_dbfs"]) + " dBFS.")
        audio_report = stats
    return {"valid": True, "metadata_checked": True, "duration_seconds": duration,
            "width": stream.get("width"), "height": stream.get("height"),
            "fps": round(actual_fps, 3), "has_audio": bool(audio_streams),
            "audio_loudness": audio_report,
            "video_codec": stream.get("codec_name"),
            "audio_codec": audio_streams[0].get("codec_name") if audio_streams else None,
            "size_bytes": video.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--require-audio", action="store_true",
                        help="Require an audio stream with measurable non-silent sound.")
    parser.add_argument("--minimum-mean-dbfs", type=float, default=-35.0)
    parser.add_argument("--maximum-peak-dbfs", type=float, default=-0.1)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.video, args.width, args.height, args.fps,
                                 args.require_audio, args.minimum_mean_dbfs,
                                 args.maximum_peak_dbfs), indent=2))
    except (IndexError, OSError, ValueError, subprocess.CalledProcessError,
            json.JSONDecodeError, ZeroDivisionError) as exc:
        print("VIDEO VALIDATION FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1)
