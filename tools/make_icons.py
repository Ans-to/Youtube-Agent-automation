#!/usr/bin/env python3
"""Draw the app icons as PNG, with no image library and no network.

Chrome, Edge and Android will only offer a real "install" for an app that ships
bitmap icons at 192 and 512 pixels. An SVG-only manifest gets you a bookmark,
not an app, which is why `web/icons/` exists and why this script exists: the
icons are generated from the same geometry as `web/icon.svg` instead of being
copied from somewhere, so they can be regenerated and reviewed.

Everything here is standard library. Coverage is computed by supersampling each
shape inside its own bounding box, then composited in painter's order. It is not
fast — a second or two per icon — but it is deterministic, offline, and runs once.

    python tools/make_icons.py            # writes web/icons/*.png
    python tools/make_icons.py --check    # verifies the committed files match
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "web" / "icons"

#: icon.png           192 and 512, full-bleed art, the sizes a browser asks for
#: icon-maskable.png  512, same art pulled into the inner 80% safe circle
SIZES = (192, 512)
MASKABLE_SIZE = 512

BG = (0x08, 0x07, 0x0B)
_RING_FILL = (0x17, 0x0D, 0x15)
_ORANGE = (0xFF, 0x8A, 0x32)
_RED = (0xFF, 0x3B, 0x2F)
_GOLD = (0xFF, 0xC5, 0x6C)
_CREAM = (0xFF, 0xF0, 0xD8)

#: Design space is the 512-unit viewBox from web/icon.svg.
STAR = [(256, 95), (301, 180), (397, 194), (327, 261), (344, 357),
        (256, 312), (168, 357), (185, 261), (115, 194), (211, 180)]
SPOKES = [((256, 220), (256, 292)), ((220, 256), (292, 256)),
          ((231, 231), (281, 281)), ((281, 231), (231, 281))]

_SS = 4  # supersampling factor per axis


def _blank(size):
    return bytearray(size * size * 4)


def _blend(buffer, size, x, y, colour, alpha):
    if alpha <= 0:
        return
    index = (y * size + x) * 4
    r, g, b = colour
    existing = buffer[index + 3] / 255.0
    out_a = alpha + existing * (1 - alpha)
    if out_a <= 0:
        return
    for offset, value in enumerate((r, g, b)):
        old = buffer[index + offset]
        buffer[index + offset] = int(round(
            (value * alpha + old * existing * (1 - alpha)) / out_a))
    buffer[index + 3] = int(round(out_a * 255))


def _shape_mask(size, scale, offset, bounds, inside):
    """Coverage mask (0..1 per pixel) for a shape, sampled inside its bounds."""
    x0, y0, x1, y1 = bounds
    x0 = max(0, int(math.floor(x0 * scale + offset[0])))
    y0 = max(0, int(math.floor(y0 * scale + offset[1])))
    x1 = min(size - 1, int(math.ceil(x1 * scale + offset[0])))
    y1 = min(size - 1, int(math.ceil(y1 * scale + offset[1])))
    total = _SS * _SS
    mask = {}
    for py in range(y0, y1 + 1):
        row = []
        for px in range(x0, x1 + 1):
            hits = 0
            for sy in range(_SS):
                for sx in range(_SS):
                    dx = (px + (sx + 0.5) / _SS - offset[0]) / scale
                    dy = (py + (sy + 0.5) / _SS - offset[1]) / scale
                    if inside(dx, dy):
                        hits += 1
            row.append(hits / total)
        mask[py] = (x0, row)
    return mask


def _paint(buffer, size, mask, colour, opacity=1.0):
    for py, (x0, row) in mask.items():
        for index, coverage in enumerate(row):
            coverage *= opacity
            if coverage > 0.002:
                _blend(buffer, size, x0 + index, py, colour, coverage)


def _circle(cx, cy, radius):
    r2 = radius * radius
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r2


def _ring(cx, cy, radius, width):
    outer = (radius + width / 2) ** 2
    inner = (radius - width / 2) ** 2
    def inside(x, y):
        d = (x - cx) ** 2 + (y - cy) ** 2
        return inner <= d <= outer
    return inside


def _polygon(points):
    def inside(x, y):
        result = False
        count = len(points)
        for index in range(count):
            x1, y1 = points[index]
            x2, y2 = points[(index + 1) % count]
            if (y1 > y) != (y2 > y):
                if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    result = not result
        return result
    return inside


def _segment(p1, p2, width):
    (x1, y1), (x2, y2) = p1, p2
    half = (width / 2) ** 2
    def inside(x, y):
        dx, dy = x2 - x1, y2 - y1
        length = dx * dx + dy * dy
        if length == 0:
            return (x - x1) ** 2 + (y - y1) ** 2 <= half
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length))
        px, py = x1 + t * dx, y1 + t * dy
        return (x - px) ** 2 + (y - py) ** 2 <= half
    return inside


def _rounded_rect(width, height, radius):
    def inside(x, y):
        cx = min(max(x, radius), width - radius)
        cy = min(max(y, radius), height - radius)
        return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
    return inside


def render(size, *, padding=0.0, maskable=False):
    """Draw the icon at `size` pixels.

    `padding` shrinks the *art* into the centre. `maskable` makes the background
    a full-bleed square instead of a rounded tile: Android crops a maskable icon
    to its own shape, and a rounded background would leave transparent corners
    inside that crop.
    """
    buffer = _blank(size)
    scale = size / 512.0 * (1.0 - padding)
    offset = (size / 2.0 - 256 * scale, size / 2.0 - 256 * scale)

    if maskable:
        background = _rounded_rect(512, 512, 0)
    else:
        background = _rounded_rect(512, 512, 112)
    mask = _shape_mask(size, 1.0, (0, 0), (0, 0, size, size), background)
    _paint(buffer, size, mask, BG)

    def draw(inside, bounds, colour, opacity=1.0):
        mask = _shape_mask(size, scale, offset, bounds, inside)
        _paint(buffer, size, mask, colour, opacity)

    draw(_circle(256, 256, 172), (84, 84, 428, 428), _RING_FILL)
    draw(_ring(256, 256, 172, 8), (80, 80, 432, 432), _ORANGE)
    draw(_ring(256, 256, 118, 5), (136, 136, 376, 376), _RED, 0.8)
    draw(_polygon(STAR), (110, 90, 400, 362), _ORANGE, 0.14)
    draw(_ring_polygon(STAR, 7), (110, 90, 400, 362), _GOLD)
    draw(_circle(256, 256, 43), (209, 209, 303, 303), _RED)
    draw(_ring(256, 256, 43, 7), (209, 209, 303, 303), _GOLD)
    for start, end in SPOKES:
        low = (min(start[0], end[0]) - 8, min(start[1], end[1]) - 8)
        high = (max(start[0], end[0]) + 8, max(start[1], end[1]) + 8)
        draw(_segment(start, end, 8), (low[0], low[1], high[0], high[1]), _CREAM)
    return buffer


def _ring_polygon(points, width):
    """Stroke a closed polygon as a set of round-capped segments."""
    segments = []
    count = len(points)
    for index in range(count):
        segments.append(_segment(points[index], points[(index + 1) % count], width))
    def inside(x, y):
        return any(segment(x, y) for segment in segments)
    return inside


def write_png(path, buffer, size):
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # no per-row filter: keeps the encoder small and exact
        rows.extend(buffer[y * size * 4:(y + 1) * size * 4])
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    return png


def expected_icons():
    """The exact bytes each committed icon should contain."""
    icons = {}
    for size in SIZES:
        icons[f"icon-{size}.png"] = (size, render(size))
    icons[f"icon-maskable-{MASKABLE_SIZE}.png"] = (
        MASKABLE_SIZE, render(MASKABLE_SIZE, padding=0.20, maskable=True))
    return icons


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the installable app icons.")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed PNGs match what this script would write")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    drift = []
    for name, (size, buffer) in sorted(expected_icons().items()):
        path = out_dir / name
        if args.check:
            try:
                existing = path.read_bytes()
            except OSError:
                drift.append(f"{name}: missing")
                continue
            # Compare the pixels, not the file. The PNG body is zlib output and
            # zlib may compress identical pixels differently on another platform
            # or version; comparing bytes would report drift that is invisible
            # and would tempt someone to commit platform-specific binaries.
            if _committed_rows(existing) != _png_rows(buffer, size):
                drift.append(f"{name}: differs from the committed icon")
            continue
        write_png(path, buffer, size)
        print(f"wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} ({size}x{size})")
    if args.check:
        if drift:
            for line in drift:
                print("DRIFT:", line)
            print("Run: python tools/make_icons.py")
            return 1
        print("Icons: OK (committed PNGs match the generator)")
    return 0


def _png_rows(buffer, size):
    """The uncompressed, filtered scanlines this generator writes for an icon."""
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter type 0 (none) on every row
        rows.extend(buffer[y * size * 4:(y + 1) * size * 4])
    return bytes(rows)


def _committed_rows(data):
    """Decode a committed PNG back to the same scanlines, or return None.

    Returns ``None`` for a file that is not an 8-bit RGBA PNG this tool could
    have written, so the caller reports drift instead of raising.
    """
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    position, idat = 8, bytearray()
    while position + 8 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        tag = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        if tag == b"IDAT":
            idat.extend(payload)
        elif tag == b"IEND":
            break
        position += 12 + length
    if not idat:
        return None
    try:
        return zlib.decompress(bytes(idat))
    except zlib.error:
        return None


def _png_bytes(buffer, size):
    import io
    temp = io.BytesIO()
    rows = _png_rows(buffer, size)
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    temp.write(b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
               + chunk(b"IEND", b""))
    return temp.getvalue()


if __name__ == "__main__":
    sys.exit(main())
