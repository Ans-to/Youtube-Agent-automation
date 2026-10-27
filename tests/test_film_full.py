"""Guards for the eight-minute cut.

Two bugs in the full film were found by looking at stills, and both were the
same shape: a property that existed on one object and was read from another.

1.  Each new shot was stored as ``{id, text, shot}`` - the picture one level
    down. The assembler spread the *entry*, so every new shot arrived with no
    ``layers`` and rendered as its own background: fifty backgrounds in a row,
    and the log said the film was fifty-three shots long.
2.  Each new shot carried its join on the entry rather than on the picture.
    The assembler read the picture, found nothing, and every join in the film
    became a hard cut - including the four that were written as a fade, a wipe
    and a push.

Neither throws. Both are only visible in the output, so they are asserted here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
FILM = STUDIO / "films" / "nokia_full.mjs"

PROBE = """
import { FILM } from './films/nokia_full.mjs';
console.log(JSON.stringify(FILM.map((s) => ({
  id: s.id,
  dur: s.dur,
  layers: (s.layers || []).length,
  kind: (s.transition && s.transition.kind) || null,
  label: (s.transition && s.transition.label) || null,
  text: s.text || '',
}))));
"""

KINDS = {'cut', 'fade', 'dissolve', 'rack', 'iris', 'wipe', 'push'}


@unittest.skipIf(shutil.which('node') is None or not FILM.is_file(), 'node or the full film is unavailable')
class FullFilmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(
            ['node', '--input-type=module', '-e', PROBE],
            cwd=STUDIO, capture_output=True, text=True, timeout=180,
        )
        if out.returncode != 0:
            raise AssertionError(out.stderr[:2000])
        cls.shots = json.loads(out.stdout.strip().splitlines()[-1])

    def test_the_film_is_a_long_form_film(self):
        total = sum(s['dur'] for s in self.shots)
        self.assertGreaterEqual(len(self.shots), 45, 'a full film, not a trailer')
        self.assertGreaterEqual(total, 7 * 60, f'{total:.1f}s is under seven minutes')
        self.assertLessEqual(total, 9 * 60 + 1, f'{total:.1f}s is over nine minutes')

    def test_every_shot_has_a_picture(self):
        empty = [s['id'] for s in self.shots if s['layers'] < 2]
        self.assertEqual(empty, [], f'shots with no layers render as a bare background: {empty}')

    def test_every_shot_is_narrated(self):
        silent = [s['id'] for s in self.shots if not s['text'].strip()]
        self.assertEqual(silent, [], f'shots with no narration: {silent}')

    def test_no_shot_is_a_flash_frame(self):
        short = [(s['id'], s['dur']) for s in self.shots if s['dur'] < 3.5]
        self.assertEqual(short, [], f'shots under 3.5s: {short}')

    def test_every_join_resolves_to_a_transition(self):
        missing = [s['id'] for s in self.shots if s['kind'] not in KINDS]
        self.assertEqual(missing, [], f'joins that would fall back to a cut: {missing}')

    def test_the_joins_are_punctuated_not_uniform(self):
        kinds = Counter(s['kind'] for s in self.shots[1:])
        self.assertGreaterEqual(sum(v for k, v in kinds.items() if k != 'cut'), 8,
                                f'only {kinds} - a film that cuts every time has no punctuation')
        self.assertGreater(kinds['cut'], sum(kinds.values()) * 0.5,
                           f'{kinds} - the accents have become the grammar')


if __name__ == '__main__':
    unittest.main()
