"""The Nokia 15-minute cut is an explicit, retimeable editorial proposal."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
MODULE = STUDIO / "films" / "nokia_empire_review_cut.mjs"
MANIFEST = STUDIO / "films" / "nokia_empire_review_cut.json"
DRAFT = ROOT / "docs" / "media" / "nokia" / "nokia-15-minute-script-draft.md"

PROBE = r"""
import fs from 'fs';
import { FILM, shotStarts, totalSeconds } from './films/nokia_empire.mjs';
import { selectShots, retimeShots, reviewScript } from './films/nokia_empire_review_cut.mjs';
const manifest = JSON.parse(fs.readFileSync('./films/nokia_empire_review_cut.json'));
const original = JSON.parse(fs.readFileSync('./films/empire_narration.json'));
const cut = selectShots(manifest);
const timing = cut.map((s, i) => ({shot:s.id, text:s.text, vo:3 + i / 100}));
const actual = retimeShots(cut, timing);
function rejected(fn) { try { fn(); return false; } catch (_) { return true; } }
const dup = {...manifest, shots:[manifest.shots[0], ...manifest.shots]};
const reversed = {...manifest, shots:[...manifest.shots].reverse()};
const missing = {...manifest, shots:manifest.shots.filter(id => !id.startsWith('s13-'))};
const badTiming = timing.map((row, i) => i === 1 ? {...row, text:'changed'} : row);
const shuffled = [...timing]; [shuffled[0], shuffled[1]] = [shuffled[1], shuffled[0]];
const emptyTiming = timing.map((row, i) => i === 0 ? {...row, vo:0} : row);
console.log(JSON.stringify({
  original: FILM.map(s => ({id:s.id, scene:s.scene, text:s.text})),
  cut: cut.map(s => ({id:s.id, scene:s.scene, text:s.text})),
  estimate: totalSeconds(cut), actual: shotStarts(actual), timing,
  script: reviewScript(cut, manifest, original),
  rejection: [dup, reversed, missing].map(m => rejected(() => selectShots(m))).concat(
    [badTiming, shuffled, emptyTiming, timing.slice(1)].map(t => rejected(() => retimeShots(cut, t)))
  ),
}));
"""


@unittest.skipIf(shutil.which("node") is None, "node is unavailable")
class NokiaReviewCutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["node", "--input-type=module", "-e", PROBE],
                                cwd=STUDIO, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.data = json.loads(result.stdout.strip().splitlines()[-1])

    def test_internal_antenna_option_removes_the_external_stub(self):
        probe = r"""
import {createCanvas} from '@napi-rs/canvas';
import {drawHandset} from './motion/kit/product.mjs';
const c = createCanvas(200, 500), ctx = c.getContext('2d');
function stub(option) {
  ctx.clearRect(0, 0, 200, 500);
  drawHandset(ctx, {x:50, y:80, w:100, h:300, shadow:false, ...option});
  const pixels = ctx.getImageData(65, 72, 25, 7).data;
  let alpha = 0; for (let i = 3; i < pixels.length; i += 4) alpha += pixels[i];
  return alpha;
}
console.log(JSON.stringify([stub({}), stub({antenna:true}), stub({antenna:false})]));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", probe],
                                cwd=STUDIO, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        default, external, internal = json.loads(result.stdout)
        self.assertEqual(default, external)
        self.assertGreater(external, 0)
        self.assertEqual(internal, 0)

    def test_selected_shots_preserve_original_words_and_order(self):
        original = self.data["original"]
        selected = self.data["cut"]
        indexes = {shot["id"]: i for i, shot in enumerate(original)}
        positions = [indexes[shot["id"]] for shot in selected]
        self.assertEqual(positions, sorted(set(positions)))
        self.assertEqual(selected, [original[i] for i in positions])
        self.assertEqual(sorted({s["scene"] for s in selected}), list(range(1, 14)))
        self.assertLess(len(selected), len(original))

    def test_estimate_and_generated_script_are_explicit_draft(self):
        self.assertGreaterEqual(self.data["estimate"], 840)
        self.assertLessEqual(self.data["estimate"], 960)
        self.assertIn("not approved", self.data["script"])
        self.assertIn("unverified", self.data["script"])
        self.assertEqual(self.data["script"], DRAFT.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest["status"], "PROPOSED_FOR_AUTHOR_REVIEW")

    def test_recorded_voice_has_a_gapless_clock_and_tail(self):
        clock, timing = self.data["actual"], self.data["timing"]
        self.assertEqual(len(clock), len(timing))
        for i, (shot, line) in enumerate(zip(clock, timing)):
            self.assertEqual(shot["id"], line["shot"])
            if i:
                self.assertAlmostEqual(shot["start"], clock[i-1]["end"], places=3)
            self.assertGreaterEqual(shot["end"] + 0.001, shot["voStart"] + line["vo"] + 0.95)
        self.assertGreater(clock[-1]["end"] - clock[-1]["voStart"] - timing[-1]["vo"], 0.2)

    def test_rejects_bad_manifest_and_timing(self):
        self.assertTrue(all(self.data["rejection"]))

    def test_clock_generation_requires_explicit_timing_or_estimate(self):
        with tempfile.TemporaryDirectory() as directory:
            starts = Path(directory) / "starts.json"
            result = subprocess.run(["node", str(MODULE), "--starts", str(starts)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--timing", result.stderr)
            self.assertFalse(starts.exists())
            result = subprocess.run(["node", str(MODULE), "--estimate", "--starts", str(starts)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(starts.read_text())), len(self.data["cut"]))


if __name__ == "__main__":
    unittest.main()
