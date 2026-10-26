"""Transitions must be chosen for a reason, from a professional vocabulary.

The film used to be dealt transitions from a pool of sixteen. That is how a
documentary about a phone company cut through horizontal blinds, a luma-keyed
grid of cells and a two-panel split: the pool does not know what a cut is *for*,
so it deals novelty. `direct()` picks by role instead, and these tests hold it to
that.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / 'video_studio'
FILM = STUDIO / 'films' / 'nokia_opening.mjs'

# What an editor uses in a documentary. Anything outside this in a film cut is a
# decision that has to be argued for, not a slot that got filled.
PROFESSIONAL = {'cut', 'dissolve', 'fade', 'iris', 'wipe', 'push', 'rack'}


@unittest.skipIf(shutil.which('node') is None, 'node is not installed')
class DirectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        path = cls.dir / 'starts.json'
        subprocess.run(['node', str(FILM), '--starts', str(path)],
                       cwd=str(STUDIO), check=True, capture_output=True)
        cls.rows = json.loads(path.read_text())
        cls.joins = [r for r in cls.rows if r['transition'] not in ('-', '')]

    def test_every_join_is_a_professional_transition(self):
        for row in self.joins:
            kind = row['transition'].split('-')[0].split('@')[0]
            with self.subTest(shot=row['id'], transition=row['transition']):
                self.assertIn(kind, PROFESSIONAL,
                              f"{row['id']} is introduced with {row['transition']!r}")

    def test_no_technique_is_used_twice(self):
        kinds = [row['transition'].split('-')[0].split('@')[0] for row in self.joins]
        self.assertEqual(len(kinds), len(set(kinds)), f'repeated: {kinds}')

    def test_every_join_states_why(self):
        for row in self.joins:
            with self.subTest(shot=row['id']):
                self.assertTrue(row.get('transitionWhy'),
                                f"{row['id']} has a transition but no reason")

    def test_an_unknown_role_is_refused(self):
        """A typo in a role must not silently fall back to a cut."""
        script = (
            "import { direct } from './motion/kit/direction.mjs';"
            "try { direct([{id:'a'},{id:'b', transitionRole:'nonsense'}]);"
            "console.log('accepted'); } catch (e) { console.log('refused'); }"
        )
        out = subprocess.run(['node', '--input-type=module', '-e', script],
                             cwd=str(STUDIO), capture_output=True, text=True)
        self.assertIn('refused', out.stdout, 'an unknown role was accepted')


if __name__ == '__main__':
    unittest.main()
