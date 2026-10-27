"""Regression checks for the motion-only Nokia review (not a human approval)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'video_studio/films/nokia_motion_review.mjs'
PLAN = ROOT / 'video_studio/films/nokia_motion_review_plan.json'
PHRASES = ROOT / 'video_studio/films/nokia_motion_review_phrase_timing.json'


def run_node(*args, check=True):
    return subprocess.run(['node', *map(str, args)], cwd=ROOT, text=True,
                          capture_output=True, check=check, timeout=90)


@unittest.skipUnless((ROOT / 'video_studio/node_modules/@napi-rs/canvas').exists(),
                     'install the studio Node dependencies')
class MotionReviewTests(unittest.TestCase):
    def test_plan_has_a_valid_contiguous_timeline(self):
        args = [SCRIPT, '--validate'] + ([] if PHRASES.exists() else ['--estimate'])
        result = json.loads(run_node(*args).stdout)
        self.assertEqual(result['shots'], 72)
        self.assertGreaterEqual(result['beats'], 180)
        self.assertEqual(result['fps'], 30)
        self.assertAlmostEqual(result['duration'], 28069 / 30)
        self.assertLess(result['longestBeat'], 10)
        self.assertGreater(len(result['visuals']), 30)
        self.assertIn('human review required', result['timing'])

    def test_every_planned_graphic_draws(self):
        args = [SCRIPT, '--render-check'] + ([] if PHRASES.exists() else ['--estimate'])
        output = run_node(*args).stdout
        self.assertIn('planned graphics at 1920x1080', output)
        self.assertIn('human review', output)

    def test_sample_is_real_full_hd_and_changes_over_time(self):
        # The tree-to-pulp wheel is genuinely animated, not a static image or
        # an interpolated frame from the old 12 fps film.
        from PIL import Image, ImageChops
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / 'a.png', Path(directory) / 'b.png'
            extra = [] if PHRASES.exists() else ['--estimate']
            run_node(SCRIPT, '--sample', '57', '--out', a, *extra)
            run_node(SCRIPT, '--sample', '57.3', '--out', b, *extra)
            with Image.open(a) as one, Image.open(b) as two:
                self.assertEqual(one.size, (1920, 1080))
                self.assertIsNotNone(ImageChops.difference(one.convert('RGB'), two.convert('RGB')).getbbox())

    def test_cue_validation_and_phrase_boundaries_fail_closed(self):
        js = r'''
          import {buildTimeline} from './video_studio/films/nokia_motion_review.mjs';
          const plan={schema_version:1,shots:{s:[{cue:'',visual:'mill',headline:'H',detail:'D'},
            {cue:'world',visual:'tower',headline:'W',detail:'D'}]}};
          const shots=[{id:'s',scene:1,start:0,end:5}];
          const voice=[{shot:'s',start:1,end:4,vo:3,text:'Hello world'}];
          const timing={schema_version:1,shots:[{shot:'s',sample_rate:48000,samples:144000,
            phrases:[{text:'Hello world',char_start:0,char_end:11,start_sample:0,end_sample:144000,pause_samples:0}]}]};
          const out=buildTimeline(plan,shots,voice,30,timing);
          if(out.length!==2||out[0].startFrame!==0||out[1].endFrame!==150||out[0].endFrame!==out[1].startFrame) process.exit(1);
          let rejected=0;
          plan.shots.s[1].cue='missing';try{buildTimeline(plan,shots,voice,30,timing)}catch{rejected++}
          plan.shots.s[1].cue='world';timing.shots[0].samples=143000;
          try{buildTimeline(plan,shots,voice,30,timing)}catch{rejected++}
          if(rejected!==2)process.exit(2);
        '''
        result = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_and_renderer_use_no_image_or_photograph_assets(self):
        plan = json.loads(PLAN.read_text())
        self.assertIn('not photographs', plan['notes'][0])
        source = SCRIPT.read_text()
        self.assertNotIn('loadImage(', source)
        self.assertNotIn('image-search/', source)
        self.assertNotIn('nokia_review_v2/', source)


if __name__ == '__main__':
    unittest.main()
