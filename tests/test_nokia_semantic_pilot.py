"""Traceability and house-style checks for the opening-only semantic pilot.

These tests cannot determine whether a picture means what a narrator says.
Listening and viewing remain mandatory before approval.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / 'video_studio/films/nokia_semantic_pilot.mjs'
PLAN = ROOT / 'video_studio/films/nokia_semantic_pilot_plan.json'


def node(*args, timeout=60):
    return subprocess.run(['node', *map(str, args)], cwd=ROOT, text=True,
                          capture_output=True, timeout=timeout)


@unittest.skipUnless((ROOT / 'video_studio/node_modules/@napi-rs/canvas').exists(),
                     'install the studio Node dependencies')
class NokiaSemanticPilotTests(unittest.TestCase):
    def test_pilot_covers_its_six_opening_shots(self):
        result = node(FILM, '--validate')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual((data['shots'], data['beats'], data['frames']), (6, 7, 1047))
        self.assertEqual(data['semantic_review'], 'unverified')
        self.assertIn('human listening', data['timing'])

    def test_wrong_or_missing_narration_and_gaps_are_rejected(self):
        script = r'''
import fs from 'fs';
import {validatePlan} from './video_studio/films/nokia_semantic_pilot.mjs';
const plan=JSON.parse(fs.readFileSync('./video_studio/films/nokia_semantic_pilot_plan.json'));
const voice=JSON.parse(fs.readFileSync('./docs/media/nokia/nokia-15-minute-review-voice-timing.json'));
const shots=JSON.parse(fs.readFileSync('./docs/media/nokia/nokia-15-minute-review-shots.json'));
const edit=(fn)=>{const x=structuredClone(plan);fn(x);try{validatePlan(x,voice,shots);return false}catch{return true}};
const rejects=[
  edit(x=>x.rows[0].spoken_span='Different words'),
  edit(x=>x.rows[1].char_start++),
  edit(x=>x.rows[1].start_frame++),
  edit(x=>x.rows[0].visual='unrelated'),
  edit(x=>x.rows[0].intent=''),
  edit(x=>x.rows[1].end_frame=x.rows[1].start_frame),
  edit(x=>x.rows.pop()),
];
if(rejects.some(x=>!x))process.exit(1);
'''
        result = node('--input-type=module', '-e', script)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_peak_example_uses_2008_all_phone_share(self):
        # Gartner reported 38.6% in 2008 versus 37.8% in 2007. The visual
        # accompanying 'at its peak' must not label 2007 as the peak year.
        source = FILM.read_text()
        self.assertIn('ALL PHONES SOLD · GARTNER · 2008', source)
        self.assertIn('38.6% of worldwide mobile-phone sales', source)
        self.assertIn("{ label: '2008', value: 38.6", source)
        self.assertNotIn('ALL PHONES SOLD · GARTNER · 2007', source)

    def test_cuts_do_not_start_on_an_almost_empty_entrance(self):
        # A brightness guard catches the specific dark entrance found on the
        # first render. It cannot tell whether the visible subject is correct.
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            for t in ('5.87', '20.10', '31.90'):
                out = Path(d) / (t + '.png')
                result = node(FILM, '--sample', t, '--out', out)
                self.assertEqual(result.returncode, 0, result.stderr)
                with Image.open(out).convert('L') as image:
                    self.assertGreater(sum(image.histogram()[91:]), 10_000, t)

    def test_native_hd_frames_use_existing_house_builders_and_change(self):
        from PIL import Image, ImageChops
        source = FILM.read_text()
        self.assertIn("from './nokia_full.mjs'", source)
        self.assertIn('drawHandset', source)
        self.assertNotIn('loadImage(', source)
        self.assertNotIn('nokia_motion_review.mjs', source)
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.png', Path(d) / 'b.png'
            first = node(FILM, '--sample', '6.1', '--out', a)
            second = node(FILM, '--sample', '7.2', '--out', b)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            with Image.open(a) as one, Image.open(b) as two:
                self.assertEqual(one.size, (1920, 1080))
                self.assertIsNotNone(ImageChops.difference(one.convert('RGB'), two.convert('RGB')).getbbox())


if __name__ == '__main__':
    unittest.main()
