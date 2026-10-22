#!/usr/bin/env python3
"""Validate a rendered frame sequence before FFmpeg encodes it.

Both renderer paths are supported: ``render.js`` writes PNG, and the
no-browser ``render_skia.js`` writes JPEG by default.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
FRAME_PATTERN = re.compile(r"frame-(\d{6})\.(png|jpg|jpeg)$")
JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(path):
    """Width and height from a JPEG's start-of-frame marker."""
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ValueError("Frame is not a valid JPEG: " + path.name)
        while True:
            marker = stream.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                raise ValueError("JPEG has no start-of-frame marker: " + path.name)
            kind = marker[1]
            if kind in (0xD8, 0xD9) or 0xD0 <= kind <= 0xD7:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) < 2:
                raise ValueError("Truncated JPEG: " + path.name)
            length = int.from_bytes(length_bytes, "big")
            if kind in JPEG_SOF_MARKERS:
                data = stream.read(5)
                if len(data) < 5:
                    raise ValueError("Truncated JPEG frame header: " + path.name)
                height = int.from_bytes(data[1:3], "big")
                width = int.from_bytes(data[3:5], "big")
                return width, height
            stream.seek(max(0, length - 2), 1)


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
        if path.suffix.lower() == ".png":
            with path.open("rb") as stream:
                header = stream.read(24)
            if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
                raise ValueError("Frame is not a valid PNG header: " + path.name)
            actual_width, actual_height = struct.unpack(">II", header[16:24])
        else:
            with path.open("rb") as stream:
                if stream.read(3) != JPEG_SIGNATURE:
                    raise ValueError("Frame is not a valid JPEG: " + path.name)
            actual_width, actual_height = jpeg_size(path)
        if (actual_width, actual_height) != (width, height):
            raise ValueError("Wrong frame dimensions in " + path.name + ": " +
                             str(actual_width) + "x" + str(actual_height) +
                             ", expected " + str(width) + "x" + str(height) + ".")
        if path.stat().st_size < 100:
            raise ValueError("Frame is unexpectedly small: " + path.name)
    return {"valid": True, "frame_count": expected, "width": width, "height": height,
            "format": found[0][1].suffix.lower().lstrip(".")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.frames, args.manifest), indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("FRAME VALIDATION FAILED:", str(exc), file=sys.stderr)
        raise SystemExit(1) from None
