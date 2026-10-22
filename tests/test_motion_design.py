import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import composition, palette, typography  # noqa: E402


class PaletteTests(unittest.TestCase):
    def test_every_tone_passes_its_contrast_floor(self):
        report = palette.validate_palettes()
        for name, data in report.items():
            self.assertEqual(data["issues"], [], msg=name)
            self.assertGreaterEqual(data["report"]["fg_on_bg"], 7.0, msg=name)
            self.assertGreaterEqual(data["report"]["accent_on_bg"], 4.5, msg=name)

    def test_contrast_ratio_matches_wcag_extremes(self):
        self.assertEqual(palette.contrast_ratio("#000000", "#ffffff"), 21.0)
        self.assertEqual(palette.contrast_ratio("#ffffff", "#ffffff"), 1.0)

    def test_invalid_hex_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid hex"):
            palette.contrast_ratio("#12", "#ffffff")
        self.assertFalse(palette.is_hex("ketchup"))
        self.assertTrue(palette.is_hex("#0A1628"))

    def test_tone_aliases_are_normalised(self):
        self.assertEqual(palette.normalize_tone("energetic"), "edgy")
        self.assertEqual(palette.normalize_tone("premium"), "cinematic")
        self.assertEqual(palette.normalize_tone("clean"), "minimalist")
        with self.assertRaisesRegex(ValueError, "Unknown tone"):
            palette.normalize_tone("corporate-ish")

    def test_each_tone_has_a_complete_style_block(self):
        for name in palette.TONES:
            block = palette.style_block(name)
            self.assertEqual(block["tone"], name)
            self.assertEqual(block["palette"]["name"], name)
            self.assertTrue(block["typography"]["display_stack"].startswith('"Space Grotesk"'))
            self.assertTrue(0 <= block["grade"]["grain"] <= 0.08)
            for role in ("primary", "entrance", "exit", "accent"):
                self.assertIn(block["easing"][role], (
                    "editorial", "entrance", "exit", "settle", "snap", "glide", "dramatic"))

    def test_light_tone_is_marked_as_light(self):
        self.assertTrue(palette.TONES["minimalist"].palette.light)
        self.assertFalse(palette.TONES["cinematic"].palette.light)


class TypographyTests(unittest.TestCase):
    def test_bundled_fonts_are_present(self):
        inventory = typography.available_fonts()
        self.assertTrue(inventory["complete"], msg=str(inventory["missing"]))
        self.assertEqual(len(inventory["families"]["Inter"]["weights"]), 5)
        self.assertEqual(len(inventory["families"]["Space Grotesk"]["weights"]), 4)
        self.assertGreater(inventory["total_bytes"], 100_000)

    def test_font_face_css_covers_every_file(self):
        css = typography.font_face_css()
        self.assertEqual(css.count("@font-face"), 9)
        self.assertIn("inter-latin-700-normal.woff2", css)
        self.assertIn("space-grotesk-latin-600-normal.woff2", css)

    def test_stacks_start_with_designed_faces(self):
        self.assertEqual(typography.stack_issues(typography.DISPLAY_STACK), [])
        self.assertEqual(typography.stack_issues(typography.TEXT_STACK), [])

    def test_default_stack_and_comic_sans_are_rejected(self):
        self.assertTrue(typography.stack_issues("Arial, sans-serif"))
        self.assertTrue(typography.stack_issues("Comic Sans MS, cursive"))
        self.assertTrue(typography.stack_issues(""))

    def test_type_scale_doubles_from_1080p_to_4k(self):
        hd = typography.type_scale(1920)
        uhd = typography.type_scale(3840)
        self.assertEqual(hd["headline"].size_px, 88)
        self.assertEqual(uhd["headline"].size_px, 176)
        self.assertEqual(hd["caption"].size_px, 30)
        self.assertEqual(uhd["caption"].size_px, 60)
        self.assertEqual(uhd["caption"].size_px, hd["caption"].size_px * 2)

    def test_hierarchy_is_distinct_and_measured(self):
        self.assertEqual(typography.hierarchy_issues(1920), [])
        report = typography.hierarchy_report(3840)
        self.assertTrue(report["distinct"])
        self.assertGreaterEqual(report["headline_over_subhead"], 1.4)
        self.assertGreaterEqual(report["subhead_over_caption"], 1.2)

    def test_invalid_widths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "canvas width"):
            typography.type_scale(100)

    def test_kinetic_plan_staggers_and_masks_every_word(self):
        plan = typography.kinetic_plan("Every frame is code", fps=60)
        self.assertEqual(len(plan["words"]), 4)
        self.assertEqual(plan["words"][0]["start_frame"], 0)
        self.assertGreater(plan["words"][1]["start_frame"], 0)
        self.assertTrue(all(word["mask"] for word in plan["words"]))
        self.assertEqual(typography.kinetic_issues(plan), [])
        self.assertGreater(plan["reading_seconds"], 0)

    def test_kinetic_plan_rejects_empty_text_and_bad_fps(self):
        with self.assertRaisesRegex(ValueError, "at least one word"):
            typography.kinetic_plan("   ")
        with self.assertRaisesRegex(ValueError, "fps"):
            typography.kinetic_plan("Words", fps=90)


class CompositionTests(unittest.TestCase):
    def test_all_shipped_aspect_ratios_pass_the_layout_audit(self):
        for ratio, shots in composition.audit_aspect_ratios().items():
            for kind, report in shots.items():
                self.assertEqual(report["issues"], [], msg="%s %s" % (ratio, kind))
                self.assertGreaterEqual(report["negative_space"], 0.40, msg="%s %s" % (ratio, kind))

    def test_hero_text_stays_clear_of_its_graphic(self):
        layout = composition.layout_for(3840, 2160, "hero")
        self.assertFalse(composition.overlap(layout.text, layout.graphic))

    def test_content_cards_start_on_the_golden_section(self):
        layout = composition.layout_for(3840, 2160, "diagram")
        self.assertAlmostEqual(layout.graphic.x / 3840, 0.618, delta=0.02)

    def test_title_and_action_safe_areas(self):
        safe = composition.safe_box(1920, 1080, composition.TITLE_SAFE)
        self.assertAlmostEqual(safe.x, 96.0, places=3)
        self.assertAlmostEqual(safe.width, 1728.0, places=3)
        action = composition.safe_box(1920, 1080, composition.ACTION_SAFE)
        self.assertGreater(action.width, safe.width)

    def test_boxes_inside_and_overlap(self):
        outer = composition.Box(0, 0, 100, 100)
        inner = composition.Box(10, 10, 20, 20)
        self.assertTrue(composition.contains(outer, inner))
        self.assertFalse(composition.contains(inner, outer))
        self.assertTrue(composition.overlap(outer, inner))
        self.assertEqual(composition.overlap_area(inner, outer), 400)

    def test_focus_points_include_thirds_and_golden(self):
        points = composition.focus_points(1920, 1080)
        self.assertEqual(len(points), 8)
        self.assertEqual({point["system"] for point in points}, {"thirds", "golden"})
        nearest = composition.nearest_focus(1920, 1080, 640, 360)
        self.assertLess(nearest["distance_px"], 5)

    def test_kinetic_type_owns_the_content_lane_and_has_no_card(self):
        layout = composition.layout_for(3840, 2160, "kinetic-type")
        self.assertAlmostEqual(layout.text.width, 0.844 * 3840, places=3)
        self.assertEqual(layout.graphic.width, 0.0)
        self.assertFalse(composition.overlap(layout.text, layout.graphic))

    def test_portrait_layout_is_composed_for_portrait(self):
        portrait = composition.layout_for(1080, 1920, "bar-chart")
        self.assertTrue(portrait.portrait)
        self.assertFalse(composition.overlap(portrait.text, portrait.graphic))
        self.assertLessEqual(portrait.graphic.bottom, portrait.caption.y)


if __name__ == "__main__":
    unittest.main()
