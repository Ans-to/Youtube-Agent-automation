"""Nokia's score follows scene boundaries, not a guessed 15-minute clock."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from video_studio.nokia_music import PROFILE, build_plan

ROOT = Path(__file__).resolve().parents[1]


def clock():
    return [{"id": f"s{n:02}", "scene": n, "start": (n - 1) * 10.0, "end": n * 10.0}
            for n in range(1, 14)]


class NokiaMusicPlanTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(PROFILE.read_text(encoding="utf-8"))

    def test_five_requested_styles_follow_scene_clock(self):
        plan = build_plan(clock(), self.profile)
        self.assertEqual([s["id"] for s in plan["sections"]],
                         ["opening", "rise", "disruption", "decline", "lesson"])
        self.assertEqual([s["style"] for s in plan["sections"]], [
            "Suspenseful, cinematic", "Inspiring, energetic", "Tense, modern electronic",
            "Emotional, restrained", "Reflective, cinematic"])
        self.assertEqual([(s["start"], s["end"]) for s in plan["sections"]],
                         [(0, 10), (10, 50), (50, 80), (80, 110), (110, 130)])
        self.assertEqual(plan["audio_targets"]["master_max_true_peak_dbtp"], -1)

    def test_missing_or_reordered_scene_is_rejected(self):
        rows = clock()
        rows[3]["scene"] = 2
        with self.assertRaises(ValueError):
            build_plan(rows, self.profile)

    def test_gap_overlap_and_duplicate_ids_are_rejected(self):
        for mutation in ("gap", "overlap", "duplicate"):
            rows = clock()
            if mutation == "gap":
                rows[4]["start"] += 1
            elif mutation == "overlap":
                rows[4]["start"] -= 1
            else:
                rows[4]["id"] = rows[3]["id"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_plan(rows, self.profile)

    def test_overlapping_profile_ranges_are_rejected(self):
        profile = json.loads(json.dumps(self.profile))
        profile["sections"][1]["scenes"] = [1, 5]
        with self.assertRaisesRegex(ValueError, "exactly once"):
            build_plan(clock(), profile)

    def test_long_motifs_reuse_deterministic_plucks(self):
        try:
            from video_studio import score
        except ModuleNotFoundError:
            self.skipTest("numpy is unavailable")
        with patch.object(score, "pluck", wraps=score.pluck) as synth:
            audio = score.build(8, [("build", 0, 8)])
        # Twelve-plus notes repeat just three pitches and one octave accent.
        self.assertLessEqual(synth.call_count, 6)
        self.assertEqual(len(audio), 8 * score.SR)
        self.assertGreater(float(abs(audio).max()), 0)

    @unittest.skipUnless(shutil.which("node"), "node unavailable")
    def test_current_film_clock_is_explicitly_not_15_minutes(self):
        probe = ("import {shotStarts} from './films/nokia_empire.mjs'; "
                 "console.log(JSON.stringify(shotStarts()));")
        result = subprocess.run(["node", "--input-type=module", "-e", probe],
                                cwd=ROOT / "video_studio", text=True, capture_output=True)
        if result.returncode and "ERR_MODULE_NOT_FOUND" in result.stderr:
            self.skipTest("video_studio npm dependencies are not installed")
        self.assertEqual(result.returncode, 0, result.stderr)
        starts = json.loads(result.stdout.strip().splitlines()[-1])
        plan = build_plan(starts, self.profile)
        self.assertGreater(plan["duration_seconds"], 960)
        self.assertEqual(plan["sections"][-1]["end"], plan["duration_seconds"])


if __name__ == "__main__":
    unittest.main()
