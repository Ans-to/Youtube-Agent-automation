import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import motion_director  # noqa: E402
from motion import transitions  # noqa: E402


class MotionCliTests(unittest.TestCase):
    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = motion_director.main(argv)
        return code, buffer.getvalue()

    def test_compiling_the_example_brief_writes_every_artifact_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli([
                "--brief", str(ROOT / "video_studio" / "brief.example.json"),
                "--out-dir", tmp,
            ])
            self.assertEqual(code, 0, msg=output)
            self.assertIn("MOTION SPEC: PASSED", output)
            for name in ("direction.json", "storyboard.json", "timeline.txt",
                         "motion-report.txt", "motion-report.json"):
                self.assertTrue((Path(tmp) / name).is_file(), msg=name)
            report = json.loads((Path(tmp) / "motion-report.json").read_text())
            self.assertEqual(report["violations"], [])

    def test_auditing_a_legacy_storyboard_upgrades_it_and_marks_it_a_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli([
                "--storyboard", str(ROOT / "video_studio" / "storyboard.example.json"),
                "--out-dir", tmp,
            ])
            self.assertEqual(code, 0, msg=output)
            self.assertIn("declared a preview", output)
            upgraded = json.loads((Path(tmp) / "storyboard.json").read_text())
            self.assertEqual(upgraded["style"]["master"], "preview")
            for scene in upgraded["scenes"]:
                self.assertIn(scene["transition_in"], transitions.PRO_TRANSITIONS)
                self.assertIs(scene["masked"], True)
                self.assertNotEqual(scene["easing"], "linear")

    def test_catalogue_is_printed_as_json(self):
        code, output = self.run_cli(["--catalogue"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(len(data["transitions"]["professional"]), 6)
        self.assertTrue(data["fonts"]["complete"])

    def test_beats_command_reads_a_wav(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_motion_beat import write_click_track

        with tempfile.TemporaryDirectory() as tmp:
            path = write_click_track(Path(tmp) / "track.wav", seconds=4.0)
            code, output = self.run_cli(["--beats", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("BEAT ANALYSIS", output)

    def test_invalid_input_returns_code_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json")
            code, output = self.run_cli(["--brief", str(broken), "--out-dir", tmp])
            self.assertEqual(code, 2)
            self.assertIn("Invalid JSON", output)

    def test_missing_arguments_prints_help(self):
        code, output = self.run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("usage", output.lower())


class ProductionIntegrationTests(unittest.TestCase):
    def test_the_deterministic_template_storyboard_meets_the_motion_spec(self):
        sys.path.insert(0, str(ROOT / "video_studio"))
        import production
        from motion import compliance, direction

        raw = {
            "title": "Motion smoke", "width": 1080, "height": 1920, "fps": 30,
            "scenes": production.fallback("Motion smoke")["scenes"],
        }
        upgraded = direction.upgrade_storyboard(raw, tone="corporate")
        sheet = direction.summarize_storyboard(upgraded, "corporate")
        report = compliance.audit_storyboard(upgraded, sheet)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["not_checked"][0]["id"], "MG-4.1-BEAT-SYNC")
        self.assertEqual(upgraded["style"]["tone"], "corporate")
        self.assertEqual(upgraded["style"]["master"], "preview")

    def test_production_exposes_motion_flags(self):
        source = (ROOT / "video_studio" / "production.py").read_text(encoding="utf-8")
        self.assertIn("--motion-tone", source)
        self.assertIn("--strict-motion", source)
        self.assertIn("motion_spec_status", source)
        self.assertIn("motion-report.json", source)


class ProStoryboardTests(unittest.TestCase):
    def test_the_committed_pro_storyboard_is_renderable_and_conformant(self):
        data = json.loads((ROOT / "video_studio" / "storyboard.pro.json").read_text())
        self.assertEqual((data["width"], data["height"], data["fps"]), (3840, 2160, 30))
        self.assertEqual(data["style"]["tone"], "cinematic")
        self.assertEqual(data["style"]["grade"]["vignette"], 0.3)
        self.assertEqual(len(data["scenes"]), 5)
        total = sum(scene["duration_seconds"] for scene in data["scenes"])
        self.assertLessEqual(total * data["fps"], 30000)
        for index, scene in enumerate(data["scenes"]):
            self.assertIn(scene["transition_in"], transitions.PRO_TRANSITIONS)
            if index == 0:
                self.assertEqual(scene["transition_in"], "cut")
            self.assertIn(scene["easing"], ("editorial", "entrance", "exit", "settle", "snap", "glide", "dramatic"))
            self.assertIs(scene["masked"], True)

    def test_pro_direction_sheet_matches_the_storyboard(self):
        sheet = json.loads((ROOT / "video_studio" / "direction.example.json").read_text())
        storyboard = json.loads((ROOT / "video_studio" / "storyboard.pro.json").read_text())
        self.assertEqual(sheet["title"], storyboard["title"])
        self.assertEqual(len(sheet["timeline"]), len(storyboard["scenes"]))
        self.assertEqual(sheet["timeline"][-1]["end"], 20.0)
        self.assertEqual(sheet["layers"][0]["name"], "background")


if __name__ == "__main__":
    unittest.main()
