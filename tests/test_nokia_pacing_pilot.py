"""Regression checks for the opening-only pacing revision.

Frame differences and a valid cue manifest are not proof of semantic or
perceptual synchronization. The resulting video still needs a human review.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / 'video_studio/films/nokia_pacing_pilot.mjs'


def node(*args, timeout=60, binary=False):
    return subprocess.run(['node', *map(str, args)], cwd=ROOT, text=not binary,
                          capture_output=True, timeout=timeout)


@unittest.skipUnless((ROOT / 'video_studio/node_modules/@napi-rs/canvas').exists(),
                     'install the studio Node dependencies')
class NokiaPacingPilotTests(unittest.TestCase):
    def test_opening_scope_and_review_status_are_explicit(self):
        result = node(FILM, '--validate')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual((data['shots'], data['beats'], data['frames']), (6, 7, 1047))
        self.assertEqual(data['duration'], 34.9)
        self.assertEqual(data['moments'], 16)
        self.assertEqual(data['semantic_review'], 'unverified')
        self.assertIn('listening still required', data['timing'])

    def test_cues_cannot_omit_a_beat_or_claim_unrelated_narration(self):
        script = r'''
import fs from 'fs';
import {validateCues} from './video_studio/films/nokia_pacing_pilot.mjs';
const plan=JSON.parse(fs.readFileSync('./video_studio/films/nokia_semantic_pilot_plan.json'));
const voice=JSON.parse(fs.readFileSync('./docs/media/nokia/audio-repair-draft/voice-timing.json'));
const cues=JSON.parse(fs.readFileSync('./video_studio/films/nokia_pacing_pilot_cues.json'));
const edit=(fn)=>{const x=structuredClone(cues);fn(x);try{validateCues(x,plan,voice);return false}catch{return true}};
const rejects=[
  edit(x=>x.moments[0].words='words not said'),
  edit(x=>x.moments[3].words='billions'), // word belongs to the other beat
  edit(x=>x.moments[3].frame=100),        // wrong beat/order
  edit(x=>x.moments[3].frame=172.5),      // fractional frame
  edit(x=>x.moments[3].visual_action='  '),
  edit(x=>x.moments=x.moments.filter(c=>c.shot!=='s01-09')),
  edit(x=>x.moments=x.moments.filter(c=>c.frame<172||c.frame>=263)),
  edit(x=>x.fps=24),
];
if(rejects.some(x=>!x))process.exit(1);
'''
        result = node('--input-type=module', '-e', script)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gartner_values_and_elapsed_year_positions(self):
        script = r'''
import { LEADERSHIP_SHARES, NOKIA_SHARE_BY_YEAR, declineYearPosition } from './video_studio/films/nokia_pacing_pilot.mjs';
console.log(JSON.stringify({leaders:LEADERSHIP_SHARES, series:NOKIA_SHARE_BY_YEAR,
 positions:NOKIA_SHARE_BY_YEAR.map(([year])=>declineYearPosition(year))}));
'''
        result = node('--input-type=module', '-e', script)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['leaders'], [
            ['Nokia', 38.6, True], ['Samsung', 16.3, False], ['Motorola', 8.7, False],
            ['LG', 8.4, False], ['Sony Ericsson', 7.6, False], ['Others', 20.3, False]])
        self.assertEqual(data['series'], [[2008, 38.6], [2009, 36.4], [2011, 23.8],
                                          [2012, 19.1], [2013, 13.9]])
        self.assertEqual(data['positions'], [0, 0.2, 0.6, 0.8, 1])

    def test_each_subject_has_a_visible_change(self):
        # Compare the *subject* region at separated moments in each beat. This
        # catches a stopped build but does not certify motion quality or meaning.
        pairs = [
            (1.4, 4.4, (0.08, 0.20, 0.92, 0.70)),  # spreading global routes
            (6.2, 7.8, (0.33, 0.20, 0.67, 0.84)),  # phone enters the pocket
            (9.6, 13.4, (0.55, 0.20, 0.96, 0.78)),  # many phones → handset
            (14.5, 16.4, (0.05, 0.40, 0.94, 0.86)),  # comparison bars grow
            (20.5, 26.8, (0.05, 0.40, 0.95, 0.86)),  # years/decline build
            (28.0, 31.0, (0.25, 0.18, 0.75, 0.78)),  # phones fan out
            (32.2, 34.6, (0.63, 0.28, 0.78, 0.74)),  # touchscreen response
        ]
        with tempfile.TemporaryDirectory() as d:
            for index, (start, end, box) in enumerate(pairs):
                images = []
                for seconds in (start, end):
                    out = Path(d) / f'{index}-{seconds}.png'
                    result = node(FILM, '--sample', str(seconds), '--preview-scale', '.5', '--out', out)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    with Image.open(out) as image:
                        self.assertEqual(image.size, (640, 360))
                        images.append(image.convert('L').resize((192, 108)))
                bounds = (int(box[0] * 192), int(box[1] * 108),
                          int(box[2] * 192), int(box[3] * 108))
                difference = ImageChops.difference(images[0].crop(bounds), images[1].crop(bounds))
                self.assertGreater(sum(difference.histogram()[10:]), 90, (start, end))

    def test_incoming_scenes_have_visible_content_at_the_cut(self):
        # A minimal brightness guard for the dark name and chart entrances.
        # It is not a substitute for judging whether the content is right.
        with tempfile.TemporaryDirectory() as d:
            for seconds in (8.8, 19.67, 31.7):
                out = Path(d) / f'{seconds}.png'
                result = node(FILM, '--sample', seconds, '--out', out)
                self.assertEqual(result.returncode, 0, result.stderr)
                with Image.open(out).convert('L') as image:
                    self.assertGreater(sum(image.histogram()[91:]), 5000, seconds)

    @unittest.skipUnless(shutil.which('ffprobe'), 'ffprobe not installed')
    def test_delivered_mp4_has_every_frame_at_a_regular_30fps(self):
        # This is deliberately checked on the encoded file: a valid source
        # frame loop alone did not prevent a muxer from dropping an end frame.
        video = ROOT / 'docs/media/nokia/nokia-opening-pacing-pilot.mp4'
        if not video.is_file():
            self.skipTest('opening pilot MP4 not present')
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'frame=best_effort_timestamp_time',
                                 '-of', 'json', str(video)], capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = json.loads(result.stdout)['frames']
        self.assertEqual(len(frames), 1047)
        for number, frame in enumerate(frames):
            self.assertAlmostEqual(float(frame['best_effort_timestamp_time']), number / 30, places=6)

    def test_preview_pipe_range_and_invalid_requests(self):
        result = node(FILM, '--pipe', '--preview-scale', '.25', '--from', 10, '--to', 22, '--step', 3, binary=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(len(result.stdout), 4 * 320 * 180 * 4)
        self.assertNotEqual(node(FILM, '--pipe', '--step', 0).returncode, 0)
        self.assertNotEqual(node(FILM, '--pipe', '--preview-scale', 2).returncode, 0)
        self.assertNotEqual(node(FILM, '--sample', 34.9, '--out', '/tmp/unused.png').returncode, 0)

    def test_no_still_image_imports_in_revision(self):
        source = FILM.read_text()
        self.assertIn('makeShots', source)
        self.assertIn('drawMap', source)
        self.assertIn('drawHandset', source)
        self.assertNotIn('loadImage(', source)
        self.assertNotIn('drawImageFile', source)


if __name__ == '__main__':
    unittest.main()
