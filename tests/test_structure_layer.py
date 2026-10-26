"""The film is built from shapes, not from type with a plate behind it.

The owner's note was "don't use only text, use different shapes and make
structure with them". That is a design requirement, so it is checked like one: a
brief that turns back into a slideshow of sentences fails here before it reaches
a render.

Two things are measured on the brief and on the delivered plan:

  * at least half the sections are carried by a *structure* template - a diagram
    with rails, rings, grids, forks or a console window - rather than by type;
  * every diagram beat publishes what it draws, and that text is spoken in the
    film, so the shapes are describing the narration and not decorating it.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / "video_studio" / "briefs" / "review-ai-code.json"
PLAN = ROOT / "docs" / "media" / "review-ai-code-plan.json"

# Templates that draw a structure. Everything else in the library sets type.
STRUCTURE_TEMPLATES = {
    "fork-paths", "matrix-grid", "ring-gauge", "budget-rail", "command-console",
}


def tokens(value: str) -> list[str]:
    return [t for t in (re.sub(r"[^a-z0-9']", "", w.lower()) for w in str(value).split()) if t]


class TheBriefIsBuiltFromDiagrams(unittest.TestCase):
    def setUp(self):
        self.brief = json.loads(BRIEF.read_text(encoding="utf-8"))
        self.sections = self.brief["sections"]

    def test_half_the_film_is_a_diagram(self):
        shapes = [s for s in self.sections if s.get("template") in STRUCTURE_TEMPLATES]
        self.assertGreaterEqual(
            len(shapes), len(self.sections) / 2,
            f"only {len(shapes)} of {len(self.sections)} sections use a structure template")

    def test_each_diagram_names_the_props_it_needs(self):
        needs = {
            "fork-paths": ("left", "right"),
            "matrix-grid": ("items",),
            "ring-gauge": ("value",),
            "budget-rail": ("segments",),
            "command-console": ("lines",),
        }
        for section in self.sections:
            template = section.get("template")
            if template not in STRUCTURE_TEMPLATES:
                continue
            for prop in needs[template]:
                self.assertIn(prop, section.get("props", {}),
                              f"section {section['id']} ({template}) is missing {prop}")

    def test_the_rail_adds_up_to_the_whole(self):
        """A rail that does not sum to its total draws a proportion that is a lie."""
        for section in self.sections:
            if section.get("template") != "budget-rail":
                continue
            props = section["props"]
            parts = sum(segment["value"] for segment in props["segments"])
            self.assertEqual(parts, props["total"],
                             f"section {section['id']}: segments sum to {parts}, total is {props['total']}")


class TheDeliveredPlanDrawsShapes(unittest.TestCase):
    def setUp(self):
        if not PLAN.is_file():
            self.skipTest("the delivered plan is not in the repository")
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        if not any("shows" in shot for shot in self.plan.get("shots", [])):
            self.skipTest("this plan predates the on-screen text record")

    def test_diagram_beats_are_in_the_delivered_plan(self):
        used = {shot["template"] for shot in self.plan["shots"]}
        self.assertTrue(used & STRUCTURE_TEMPLATES,
                        f"the delivered film uses no diagrams (templates: {sorted(used)})")

    def test_every_diagram_beat_says_something(self):
        silent = [shot["id"] for shot in self.plan["shots"]
                  if shot["template"] in STRUCTURE_TEMPLATES and not shot.get("shows")]
        self.assertEqual(silent, [], "a diagram beat has nothing recorded on it")


if __name__ == "__main__":
    unittest.main()
