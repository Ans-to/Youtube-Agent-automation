#!/usr/bin/env python3
"""Validate the rendered PNG frame sequence before FFmpeg encodes it."""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FRAME_PATTERN = re.compile(r"frame-(\d{6})\.png$")


def validate(frames_dir, manifest_path):
    frames_dir = Path(frames_dir)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    width, height, expected = int(manifest["width"]), int(manifest["height"]), int(manifest["frame_count"])
    if expected < 1 or expected > 30000:
        raise ValueError("Manifest frame count is outside the supported 1..30000 range.")
    found = []
    for path in frames_dir.iterdir():
        match = FRAME_PATTERN.fullmatch(path.name)
        if match and path.is_file():
            found.append((int(match.group(1)), path))
    found.sort(key=lambda item: item[0])
    if len(found) != expected:
        raise ValueError("Expected " + str(expected) + " frames, found " + str(len(found)) + ".")
    for index, (number, path) in enumerate(found):
        if number != index:
            raise ValueError("Frame sequence has a gap at index " + str(index) + ".")
        with path.open("rb") as stream:
            header = stream.read(24)
        if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
            raise ValueError("Frame is not a valid PNG header: " + path.name)
        actual_width, actual_height = struct.unpack(">II", header[16:24])
        if (actual_width, actual_height) != (width, height):
            raise ValueError("Wrong frame dimensions in " + path.name + ": " +
                             str(actual_width) + "x" + str(actual_height) +
                             ", expected " + str(width) + "x" + str(height) + ".")
        if path.stat().st_size < 100:
            raise ValueError("Frame is unexpectedly small: " + path.name)
    return {"valid": True, "frame_count": expected, "width": width, "height": height}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.frames, args.manifest), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("FRAME VALIDATION FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1)
