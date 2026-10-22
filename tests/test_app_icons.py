"""Tests for the app icon generator.

The icons are committed binaries, so the tests check two things that matter: the
committed files really are valid PNGs at the sizes the manifest advertises, and
the generator would reproduce exactly those bytes if run again.
"""
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_icons


def _read_chunks(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    position = 8
    chunks = []
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        tag = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        chunks.append((tag, payload))
        position += 12 + length
    return chunks


def _decode(data):
    """Minimal PNG decode of our own output: RGBA, filter 0 on every row."""
    chunks = dict(_read_chunks(data))
    width, height, depth, colour, _, _, _ = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    assert (depth, colour) == (8, 6), "expected 8-bit RGBA"
    raw = zlib.decompress(chunks[b"IDAT"])
    rows = []
    stride = width * 4
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 0, "unexpected filter byte"
        rows.append(raw[start + 1:start + 1 + stride])
    return width, height, rows


class CommittedIconTests(unittest.TestCase):
    def test_every_manifest_icon_exists(self):
        import json
        manifest = json.loads((ROOT / "web" / "manifest.webmanifest").read_text())
        for icon in manifest["icons"]:
            if not icon["src"].endswith(".png"):
                continue
            with self.subTest(icon=icon["src"]):
                path = ROOT / "web" / "icons" / Path(icon["src"]).name
                self.assertTrue(path.is_file(), f"{path} is missing")
                width, height, _ = _decode(path.read_bytes())
                self.assertEqual(f"{width}x{height}", icon["sizes"])

    def test_the_rounded_icons_are_square_with_see_through_corners(self):
        for name in ("icon-192.png", "icon-512.png"):
            with self.subTest(name=name):
                width, height, rows = _decode((ROOT / "web" / "icons" / name).read_bytes())
                self.assertEqual(width, height)
                # Rounded corners: the very first pixel must be see-through, or a
                # dark square appears behind every launcher icon.
                self.assertEqual(rows[0][3], 0)
                # ...and the centre must be opaque, or the icon is empty.
                self.assertEqual(rows[height // 2][(width // 2) * 4 + 3], 255)

    def test_the_maskable_icon_is_full_bleed(self):
        # Android crops this one to its own shape. Transparent corners would show
        # through the crop, so the background has to reach every edge.
        width, height, rows = _decode((ROOT / "web" / "icons" / "icon-maskable-512.png").read_bytes())
        for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            with self.subTest(corner=(x, y)):
                self.assertEqual(rows[y][x * 4 + 3], 255)

    def test_the_maskable_icon_keeps_its_art_inside_the_safe_circle(self):
        width, _, rows = _decode((ROOT / "web" / "icons" / "icon-maskable-512.png").read_bytes())
        middle = rows[width // 2]
        # Android may crop a maskable icon to a circle of ~80% width, so nothing
        # important may sit in the outer 10%. The outer ring is the widest art.
        for ratio in (0.02, 0.05, 0.09):
            x = int(width * ratio) * 4
            self.assertEqual(tuple(middle[x:x + 3]), (8, 7, 11),
                             f"art reaches {ratio:.0%} of the width, inside the crop margin")
        # The ring itself, drawn at 172/512 radius, must be inside the safe circle.
        padded_edge = width // 2 - int(172 * 0.8)
        self.assertGreater(padded_edge, width // 10)

    def test_the_generator_reproduces_a_committed_icon(self):
        # This is the check that keeps the binaries honest: they are not artwork
        # somebody dropped in, they are the output of this script. The smallest
        # icon is enough to prove the pipeline, and costs a fraction of the 512
        # render, so the suite stays fast.
        reproduced = make_icons._png_bytes(make_icons.render(192), 192)
        self.assertEqual(reproduced, (ROOT / "web" / "icons" / "icon-192.png").read_bytes())

    def test_check_mode_reports_drift_rather_than_passing(self):
        tiny = {"icon-192.png": (2, bytearray(2 * 2 * 4))}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(make_icons, "expected_icons", return_value=tiny):
            self.assertEqual(make_icons.main(["--check", "--out-dir", directory]), 1)
            make_icons.main(["--out-dir", directory])
            self.assertEqual(make_icons.main(["--check", "--out-dir", directory]), 0)


class EncoderTests(unittest.TestCase):
    def test_a_tiny_buffer_encodes_to_a_valid_png(self):
        buffer = bytearray(2 * 2 * 4)
        for index in range(4):
            buffer[index * 4:index * 4 + 4] = bytes((10, 20, 30, 255))
        data = make_icons._png_bytes(buffer, 2)
        width, height, rows = _decode(data)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rows[0][:4], bytes((10, 20, 30, 255)))

    def test_a_rounded_rectangle_has_rounded_corners(self):
        shape = make_icons._rounded_rect(100, 100, 20)
        self.assertFalse(shape(0, 0))
        self.assertFalse(shape(2, 2))
        self.assertTrue(shape(50, 50))
        self.assertTrue(shape(10, 50))

    def test_a_polygon_contains_its_centre_and_not_its_far_corner(self):
        star = make_icons._polygon(make_icons.STAR)
        self.assertTrue(star(256, 250))
        self.assertFalse(star(5, 5))

    def test_a_segment_is_thick_enough_to_be_visible(self):
        segment = make_icons._segment((0, 0), (10, 0), 4)
        self.assertTrue(segment(5, 0))
        self.assertTrue(segment(5, 1.5))
        self.assertFalse(segment(5, 5))


if __name__ == "__main__":
    unittest.main()
