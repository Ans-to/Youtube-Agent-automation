"""The motion template library must choose by situation and stay in its box.

These tests exist because the library makes promises that are easy to state and
easy to break: every template declares which situations it serves, where in the
frame it may draw, and how long a beat it can carry. If any of that stops being
true, a film draws something plausible and wrong - which is exactly the failure
the owner has rejected twice.

The heavy checks run the JavaScript, because the library is JavaScript and the
only honest way to know a template stays inside its region is to render it and
measure the ink. They skip when node or the canvas package is unavailable, like
the other film tests in this suite.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
CLI = STUDIO / "motion" / "library_cli.mjs"
AGENT_MAP = ROOT / "agents" / "motion_templates.json"
CHECKER = ROOT / "tools" / "check_motion_library.py"
NODE = shutil.which("node")


def canvas_ready() -> bool:
    if NODE is None or not CLI.is_file():
        return False
    probe = subprocess.run([NODE, "-e", "require('@napi-rs/canvas')"],
                           cwd=str(STUDIO), capture_output=True, text=True, check=False)
    return probe.returncode == 0


def node_json(source: str) -> dict:
    """Run a module snippet against the library and read its JSON output."""
    script = (
        "import { TEMPLATES, REGIONS, RESERVED, regionRect, drawTemplate } from './motion/library.mjs';\n"
        "import { SITUATIONS, rankTemplates, chooseTemplate } from './motion/choose.mjs';\n"
        f"{source}"
    )
    probe = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        cwd=str(STUDIO), capture_output=True, text=True, timeout=120, check=False,
    )
    if probe.returncode != 0:
        raise AssertionError(probe.stderr.strip()[:800])
    return json.loads(probe.stdout)


class CatalogueTests(unittest.TestCase):
    """The published map must be the code's own output."""

    def test_the_agent_map_is_generated_from_the_code(self):
        published = json.loads(AGENT_MAP.read_text(encoding="utf-8"))
        self.assertEqual(published["version"], 1)
        self.assertIn("--write-agent-map", published["generated_by"])
        ids = [template["id"] for template in published["templates"]]
        self.assertEqual(len(ids), len(set(ids)), "template ids must be unique")
        self.assertGreaterEqual(len(ids), 6)
        for template in published["templates"]:
            self.assertTrue(template["purpose"].strip(), template["id"])
            self.assertTrue(template["when"], template["id"])
            self.assertTrue(template["avoid"], template["id"])
            self.assertLess(template["minSeconds"], template["maxSeconds"], template["id"])
            for need in template["needs"]:
                self.assertIn(need, template["sample"], f"{template['id']} needs {need}")

    def test_every_situation_points_at_real_templates(self):
        published = json.loads(AGENT_MAP.read_text(encoding="utf-8"))
        ids = {template["id"] for template in published["templates"]}
        for name, spec in published["situations"].items():
            self.assertTrue(spec["wants"], name)
            for wanted in spec["wants"]:
                self.assertIn(wanted, ids, f"{name} wants {wanted}")

    def test_no_region_touches_the_live_column_or_the_caption_band(self):
        published = json.loads(AGENT_MAP.read_text(encoding="utf-8"))
        reserved = published["reserved"]

        def overlap(a, b):
            return not (
                a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]
            )

        for name, box in published["regions"].items():
            self.assertGreaterEqual(box["x"], 0, name)
            self.assertGreaterEqual(box["y"], 0, name)
            self.assertLessEqual(box["x"] + box["w"], 1.0001, name)
            self.assertLessEqual(box["y"] + box["h"], 1.0001, name)
            for reserved_name, keep_out in reserved.items():
                self.assertFalse(overlap(box, keep_out), f"{name} overlaps {reserved_name}")

    def test_the_python_checker_passes(self):
        probe = subprocess.run(
            ["python3", str(CHECKER), "--skip-selfcheck"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120, check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)


@unittest.skipIf(not canvas_ready(), "node, canvas or the library is unavailable")
class RenderTests(unittest.TestCase):
    """The promises that can only be kept by drawing."""

    def test_every_template_renders_inside_its_region_and_moves(self):
        probe = subprocess.run([NODE, str(CLI), "--selfcheck"],
                               cwd=str(STUDIO), capture_output=True, text=True, timeout=300, check=False)
        self.assertEqual(probe.returncode, 0, probe.stdout[-1500:] + probe.stderr[-800:])
        report = json.loads(probe.stdout)
        self.assertGreaterEqual(report["cases"], 10)
        self.assertEqual(report["failures"], [])

    def test_a_template_refuses_a_region_it_does_not_own(self):
        result = node_json("""
const canvas = (await import('@napi-rs/canvas')).createCanvas(320, 180);
const ctx = canvas.getContext('2d');
let message = 'no error';
try {
  drawTemplate(ctx, 'sweep-rule', { w: 320, h: 180, region: 'title', seconds: 0.8, local: 0.2, label: 'X' });
} catch (error) { message = error.message; }
console.log(JSON.stringify({ message }));
""")
        self.assertIn("cannot draw in region", result["message"])

    def test_a_template_refuses_a_beat_it_cannot_carry(self):
        result = node_json("""
const canvas = (await import('@napi-rs/canvas')).createCanvas(320, 180);
const ctx = canvas.getContext('2d');
let message = 'no error';
try {
  drawTemplate(ctx, 'sweep-rule', { w: 320, h: 180, region: 'band', seconds: 4.0, local: 0.2, label: 'X' });
} catch (error) { message = error.message; }
console.log(JSON.stringify({ message }));
""")
        self.assertIn("built for beats of", result["message"])

    def test_a_missing_prop_is_an_error_not_a_default(self):
        result = node_json("""
const canvas = (await import('@napi-rs/canvas')).createCanvas(320, 180);
const ctx = canvas.getContext('2d');
let message = 'no error';
try {
  drawTemplate(ctx, 'list-build', { w: 320, h: 180, region: 'stage', seconds: 2, local: 0.5 });
} catch (error) { message = error.message; }
console.log(JSON.stringify({ message }));
""")
        self.assertIn('needs the prop "items"', result["message"])


class ChooserTests(unittest.TestCase):
    """The decision layer: right template for the situation, with reasons."""

    @unittest.skipIf(NODE is None or not CLI.is_file(), "node is unavailable")
    def choose(self, situation: str, seconds: float, region: str) -> dict:
        probe = subprocess.run(
            [NODE, str(CLI), "--choose", "--situation", situation,
             "--seconds", str(seconds), "--region", region],
            cwd=str(STUDIO), capture_output=True, text=True, timeout=120, check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        return json.loads(probe.stdout)

    @unittest.skipIf(NODE is None or not CLI.is_file(), "node is unavailable")
    def test_each_situation_picks_a_template_that_belongs_to_it(self):
        cases = [
            ("opening-claim", 2.4, "title", "kinetic-headline"),
            ("explain-a-number", 2.0, "stage", "count-up"),
            ("show-a-sequence", 3.0, "ledger", "list-build"),
            ("recap", 3.0, "stage", "list-build"),
            ("make-a-comparison", 3.0, "split", "compare-pair"),
            ("show-the-mechanism", 3.0, "stage", "code-typing"),
            ("hold-a-beat", 0.8, "band", "sweep-rule"),
            ("build-an-argument", 3.0, "stage", "stack-push"),
        ]
        for situation, seconds, region, expected in cases:
            payload = self.choose(situation, seconds, region)
            best = payload["ranked"][0]
            self.assertEqual(best["id"], expected, f"{situation}: {payload['assuming_props']}")
            self.assertNotIn("rejected", best)
            self.assertTrue(best["reasons"], situation)

    @unittest.skipIf(NODE is None or not CLI.is_file(), "node is unavailable")
    def test_a_region_the_template_does_not_own_is_refused_with_a_reason(self):
        payload = self.choose("opening-claim", 2.4, "title")
        refused = {entry["id"]: entry.get("rejected", "") for entry in payload["ranked"][1:]}
        self.assertIn("is not one of its regions", refused["sweep-rule"])

    @unittest.skipIf(NODE is None or not CLI.is_file(), "node is unavailable")
    def test_repeating_the_previous_template_is_penalised(self):
        result = node_json("""
const alone = rankTemplates({ situation: 'recap', seconds: 3.0, region: 'stage',
  have: { items: true }, previous: null });
const after = rankTemplates({ situation: 'recap', seconds: 3.0, region: 'stage',
  have: { items: true }, previous: 'list-build' });
const score = (rows, id) => rows.find((row) => row.id === id).score;
console.log(JSON.stringify({ alone: score(alone, 'list-build'), after: score(after, 'list-build') }));
""")
        self.assertLess(result["after"], result["alone"])

    @unittest.skipIf(NODE is None or not CLI.is_file(), "node is unavailable")
    def test_impossible_beat_explains_itself_instead_of_crashing(self):
        result = node_json("""
let message = 'no error';
try {
  chooseTemplate({ situation: 'hold-a-beat', seconds: 9.0, region: 'band', have: {} });
} catch (error) { message = error.message; }
console.log(JSON.stringify({ message }));
""")
        self.assertIn("No template can fill this beat", result["message"])
        self.assertIn("sweep-rule", result["message"])


if __name__ == "__main__":
    unittest.main()
