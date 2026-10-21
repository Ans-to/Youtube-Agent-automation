"""The renderer must match the direction engine, not merely resemble it.

``render.html`` is JavaScript and cannot import the Python package, so its
curve, camera and transition tables are duplicated. These tests parse the
duplicate tables and fail when they drift. Without this, the direction sheet
would be a description of a renderer that no longer exists.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

from motion import camera, curves, palette, transitions, typography  # noqa: E402

RENDER_HTML = ROOT / "video_studio" / "render.html"
RENDER_JS = ROOT / "video_studio" / "render.js"


def html():
    return RENDER_HTML.read_text(encoding="utf-8")


class RendererTableTests(unittest.TestCase):
    def test_curve_table_matches_the_python_curves(self):
        match = re.search(r"const CURVES=\{([^}]*)\};", html())
        self.assertIsNotNone(match, "CURVES table not found in render.html")
        found = {}
        for entry in match.group(1).split("],"):
            entry = entry.strip().rstrip("]")
            if not entry:
                continue
            name, _, values = entry.partition(":")
            found[name.strip()] = [float(value) for value in values.strip(" []").split(",")]
        self.assertEqual(set(found), set(curves.CURVES) - curves.FORBIDDEN_CURVES)
        for name, control_points in found.items():
            python_curve = curves.CURVES[name]
            self.assertEqual(
                control_points,
                [python_curve.x1, python_curve.y1, python_curve.x2, python_curve.y2],
                msg=name,
            )

    def test_linear_is_absent_from_the_renderer(self):
        match = re.search(r"const CURVES=\{([^}]*)\};", html())
        self.assertNotIn("linear", match.group(1))

    def test_camera_moves_match_python(self):
        source = html()
        block = source[source.index("function cameraTransformFor"):]
        block = block[: block.index("return {scale,offsetX,offsetY,rotation")]
        implemented = set(re.findall(r'mode==="([a-z-]+)"', block))
        implemented.discard("static")
        self.assertEqual(implemented, set(camera.MOVES) - {"static"})

    def test_transition_capability_list_matches_python(self):
        match = re.search(r"transitions:\[([^\]]*)\]", html())
        self.assertIsNotNone(match)
        listed = {item.strip().strip('"') for item in match.group(1).split(",")}
        self.assertEqual(listed, set(transitions.PRO_TRANSITIONS) | transitions.LEGACY_NAMES)

    def test_render_js_accepts_exactly_the_same_transitions(self):
        source = RENDER_JS.read_text(encoding="utf-8")
        match = re.search(r"const transitionTypes=new Set\(\[([^\]]*)\]\);", source)
        self.assertIsNotNone(match)
        listed = {item.strip().strip('"') for item in match.group(1).split(",")}
        # "none" is a storyboard value meaning "no transition", not a renderable edit.
        self.assertEqual(listed - {"none"}, set(transitions.ALL_RENDERABLE))

    def test_render_js_accepts_the_python_easing_names(self):
        source = RENDER_JS.read_text(encoding="utf-8")
        match = re.search(r"const easingTypes=new Set\(\[([^\]]*)\]\);", source)
        self.assertIsNotNone(match)
        listed = {item.strip().strip('"') for item in match.group(1).split(",")}
        self.assertEqual(listed, set(curves.CURVES) - curves.FORBIDDEN_CURVES)

    def test_render_js_accepts_every_python_tone(self):
        source = RENDER_JS.read_text(encoding="utf-8")
        match = re.search(r"const toneTypes=new Set\(\[([^\]]*)\]\);", source)
        self.assertIsNotNone(match)
        listed = {item.strip().strip('"') for item in match.group(1).split(",")}
        self.assertEqual(listed, set(palette.TONES))


class RendererAssetTests(unittest.TestCase):
    def test_every_declared_font_face_file_exists(self):
        faces = re.findall(r"src:url\('fonts/([^']+)'\)", html())
        self.assertEqual(len(faces), 9)
        for filename in faces:
            path = ROOT / "video_studio" / "fonts" / filename
            self.assertTrue(path.is_file(), msg=filename)
            self.assertGreater(path.stat().st_size, 5000, msg=filename)

    def test_font_face_declarations_cover_the_python_inventory(self):
        faces = set(re.findall(r"src:url\('fonts/([^']+)'\)", html()))
        expected = {filename for weights in typography.BUNDLED_FONTS.values()
                    for filename in weights.values()}
        self.assertEqual(faces, expected)

    def test_no_forbidden_typeface_is_referenced(self):
        source = html().lower()
        for forbidden in typography.FORBIDDEN_FONTS:
            self.assertNotIn(forbidden, source, msg=forbidden)

    def test_no_system_default_font_leads_a_stack(self):
        source = html()
        self.assertNotIn('px Arial"', source)
        self.assertNotIn("px Arial,", source)


class RendererBehaviourTests(unittest.TestCase):
    def test_text_is_masked_and_eased_rather_than_drawn_immediately(self):
        source = html()
        self.assertIn("anticipationOffset(", source)
        self.assertIn("ease(\"settle\",raw)", source)
        self.assertIn("ease(\"entrance\",raw)", source)
        self.assertIn("ctx.clip()", source)

    def test_grade_pass_exists_and_is_bounded(self):
        source = html()
        self.assertIn("GRADE.vignette", source)
        self.assertIn("GRADE.grain", source)
        self.assertIn("GRADE.bloom", source)
        self.assertIn("Math.min(.4,Number(grade.vignette))", source)

    def test_canvas_accepts_four_k_portrait(self):
        source = html()
        self.assertIn("height>3840", source)
        self.assertIn("window.setCanvasSize", source)
        self.assertIn("h<180||h>3840", RENDER_JS.read_text(encoding="utf-8"))

    def test_style_block_is_validated_before_rendering(self):
        source = RENDER_JS.read_text(encoding="utf-8")
        self.assertIn("style must be an object", source)
        self.assertIn("must be a 6-digit hex colour", source)
        self.assertIn("style.grade.", source)

    def test_bundled_fonts_are_awaited_before_the_first_frame(self):
        source = RENDER_JS.read_text(encoding="utf-8")
        self.assertIn("document.fonts.ready", source)
        self.assertIn("document.fonts.check", source)
        self.assertIn("Bundled font regression", source)

    def test_renderer_no_longer_draws_a_second_kinetic_card(self):
        source = html()
        block = source[source.index('if(type==="kinetic-type")'):]
        block = block[: block.index("else if(type===")]
        self.assertNotIn("rounded(", block)

    def test_renderer_no_longer_duplicates_the_hero_orbit(self):
        self.assertNotIn('String(scene.visual_type||"hero")==="hero"){\n    ctx.strokeStyle=p.accent', html())


if __name__ == "__main__":
    unittest.main()
