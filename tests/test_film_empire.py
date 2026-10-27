"""The second film: somebody else's script, kept verbatim.

`films/empire_narration.json` is the author's narration, unedited. The picture
file splits it at sentence boundaries so each beat can have its own frame, which
means the script only survives if every fragment lands in the film, in order,
with nothing dropped and nothing quietly rewritten to fit a shot.

That is the one property worth asserting: this film's words are not the agent's.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FILM = STUDIO / "films" / "nokia_empire.mjs"
SCRIPT = STUDIO / "films" / "empire_narration.json"

PROBE = """
import { FILM, totalSeconds } from './films/nokia_empire.mjs';
console.log(JSON.stringify({
  total: totalSeconds(),
  shots: FILM.map((s) => ({
    id: s.id,
    scene: s.scene,
    dur: s.dur,
    layers: (s.layers || []).length,
    kind: (s.transition && s.transition.kind) || 'cut',
    text: s.text,
  })),
}));
"""

KINDS = {'cut', 'fade', 'dissolve', 'rack', 'iris', 'wipe', 'push'}


def norm(text: str) -> str:
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'\s+', ' ', text).strip()


@unittest.skipIf(shutil.which('node') is None or not FILM.is_file(), 'node or the film is unavailable')
class EmpireFilmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(
            ['node', '--input-type=module', '-e', PROBE],
            cwd=STUDIO, capture_output=True, text=True, timeout=180,
        )
        if out.returncode != 0:
            raise AssertionError(out.stderr[:2000])
        cls.probe = json.loads(out.stdout.strip().splitlines()[-1])
        cls.script = json.loads(SCRIPT.read_text())

    def test_every_scene_of_the_script_is_in_the_film(self):
        spoken = {}
        for shot in self.probe['shots']:
            spoken.setdefault(shot['scene'], []).append(shot['text'])
        self.assertEqual(sorted(spoken), sorted(s['n'] for s in self.script['scenes']))
        for scene in self.script['scenes']:
            with self.subTest(scene=scene['n']):
                self.assertEqual(
                    norm(' '.join(spoken[scene['n']])), norm(scene['text']),
                    f"scene {scene['n']} is not the script's scene {scene['n']}",
                )

    def test_every_shot_has_a_picture(self):
        empty = [s['id'] for s in self.probe['shots'] if s['layers'] < 2]
        self.assertEqual(empty, [], f'shots that would render as a bare background: {empty}')

    def test_every_join_resolves(self):
        bad = [s['id'] for s in self.probe['shots'] if s['kind'] not in KINDS]
        self.assertEqual(bad, [], f'joins that would fall back to a cut: {bad}')

    def test_it_is_a_feature_length_documentary(self):
        # 3,116 words of narration does not fit in fifteen minutes at a calm
        # read; the film is as long as its script is.
        self.assertGreater(self.probe['total'], 1400)
        self.assertLess(self.probe['total'], 2000)

    def test_the_joins_are_punctuated(self):
        kinds = Counter(s['kind'] for s in self.probe['shots'][1:])
        self.assertGreaterEqual(sum(v for k, v in kinds.items() if k != 'cut'), 15, str(kinds))
        self.assertGreater(kinds['cut'], sum(kinds.values()) * 0.5, str(kinds))

    def test_no_shot_is_a_flash_frame(self):
        short = [(s['id'], s['dur']) for s in self.probe['shots'] if s['dur'] < 2.5]
        self.assertEqual(short, [], f'shots under 2.5s: {short}')


if __name__ == '__main__':
    unittest.main()
