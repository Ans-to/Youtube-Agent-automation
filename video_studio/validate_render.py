#!/usr/bin/env python3
"""Validate MP4 codec, duration, dimensions, frame rate, and optional audio."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def inspect(path, width=None, height=None, fps=None, require_audio=False):
    video = Path(path)
    if not video.is_file() or video.stat().st_size < 1024:
        raise ValueError("Video file is missing or unexpectedly small.")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe is required; install FFmpeg with ffprobe on PATH.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate",
         "-of", "json", str(video)],
        check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise ValueError("No video stream found.")
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
    return {"valid": True, "metadata_checked": True, "duration_seconds": duration,
            "width": stream.get("width"), "height": stream.get("height"),
            "fps": round(actual_fps, 3), "has_audio": bool(audio_streams),
            "video_codec": stream.get("codec_name"), "audio_codec": audio_streams[0].get("codec_name") if audio_streams else None,
            "size_bytes": video.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--require-audio", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.video, args.width, args.height, args.fps, args.require_audio), indent=2))
    except (IndexError, OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError, ZeroDivisionError) as exc:
        print("VIDEO VALIDATION FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1)
