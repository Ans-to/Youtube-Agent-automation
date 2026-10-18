#!/usr/bin/env python3
"""Validate a rendered MP4 using ffprobe when available."""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def inspect(path):
    video = Path(path)
    if not video.is_file() or video.stat().st_size < 1024:
        raise ValueError("Video file is missing or unexpectedly small.")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"valid": True, "metadata_checked": False, "reason": "ffprobe not installed", "size_bytes": video.stat().st_size}
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type,width,height",
         "-of", "json", str(video)],
        check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if not video_streams:
        raise ValueError("No video stream found.")
    stream = video_streams[0]
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Video duration is invalid.")
    if stream.get("codec_name") != "h264":
        raise ValueError("Expected H.264 output, found " + str(stream.get("codec_name")))
    return {"valid": True, "metadata_checked": True, "duration_seconds": duration,
            "width": stream.get("width"), "height": stream.get("height"),
            "video_codec": stream.get("codec_name"), "size_bytes": video.stat().st_size}


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(sys.argv[1]), indent=2))
    except (IndexError, OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("VIDEO VALIDATION FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1)
