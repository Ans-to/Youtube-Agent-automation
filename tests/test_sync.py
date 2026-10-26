"""The film and the narration have to be on the same clock.

They were not. The picture added up `vo + PAD` shot by shot; the voice track added
up its own 0.30 s lead and 0.35 s gaps. Two sums, one film - by 33 s the picture
had cut to the trades while the previous line was still being spoken, and the
drift swung from -0.73 s to +1.05 s across eight shots.

These tests read the film's own starts file and the voice's own timings, so they
fail if either side ever starts keeping a private clock again.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / 'video_studio'
FILM = STUDIO / 'films' / 'nokia_opening.mjs'
TIMING = STUDIO / 'films' / 'vo-timing.json'

LEAD = 0.30
LEAD_FIRST = 0.55


@unittest.skipIf(shutil.which('node') is None, 'node is not installed')
class SyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.starts_path = cls.dir / 'starts.json'
        subprocess.run(
            ['node', str(FILM), '--starts', str(cls.starts_path)],
            cwd=str(STUDIO), check=True, capture_output=True,
        )
        cls.starts = json.loads(cls.starts_path.read_text())
        cls.timing = json.loads(TIMING.read_text())

    def test_the_film_and_the_voice_name_the_same_shots(self):
        film_ids = [row['id'] for row in self.starts]
        voice_ids = [row['shot'] for row in self.timing]
        self.assertEqual(film_ids, voice_ids)

    def test_every_line_starts_a_beat_after_its_own_cut(self):
        for i, (shot, line) in enumerate(zip(self.starts, self.timing)):
            with self.subTest(shot=shot['id']):
                expected = shot['start'] + (LEAD_FIRST if i == 0 else LEAD)
                self.assertAlmostEqual(
                    shot['voStart'], expected, delta=0.01,
                    msg=f"{shot['id']}: the film says the voice starts at "
                        f"{shot['voStart']}s, but the cut is at {shot['start']}s")

    def test_no_line_runs_past_its_own_cut(self):
        """A line that outlives its shot is a cut in the middle of a word."""
        for shot, line in zip(self.starts, self.timing):
            with self.subTest(shot=shot['id']):
                spoken_end = shot['voStart'] + line['vo']
                self.assertLess(
                    spoken_end, shot['end'] + 0.001,
                    f"{shot['id']}: the line ends at {spoken_end:.2f}s but the shot "
                    f"ends at {shot['end']:.2f}s")

    def test_drift_does_not_accumulate(self):
        """The bug was cumulative. The gap before a line may vary; it may not grow."""
        gaps = []
        for i, (shot, line) in enumerate(zip(self.starts, self.timing)):
            gaps.append(round(shot['voStart'] - shot['start'], 3))
        self.assertEqual(len(set(gaps[1:])), 1, f'the lead varies per shot: {gaps}')
        self.assertLess(gaps[0], 1.0)


class PlacementTest(unittest.TestCase):
    def test_placement_uses_the_films_vo_start(self):
        """The mixer must read voStart, not recompute a lead of its own."""
        from video_studio import narrate

        timing = [{'shot': 'a', 'vo': 2.0}, {'shot': 'b', 'vo': 1.5}]
        starts = [
            {'id': 'a', 'start': 0.0, 'end': 3.0, 'voStart': 0.55},
            {'id': 'b', 'start': 3.0, 'end': 5.0, 'voStart': 3.30},
        ]
        placed = narrate.place_in_film(timing, starts)
        self.assertAlmostEqual(placed[0]['start'], 0.55, delta=0.001)
        self.assertAlmostEqual(placed[1]['start'], 3.30, delta=0.001)
        self.assertAlmostEqual(placed[1]['end'], 4.80, delta=0.001)

    def test_a_line_that_overruns_its_shot_is_refused(self):
        from video_studio import narrate

        timing = [{'shot': 'a', 'vo': 5.0}]
        starts = [{'id': 'a', 'start': 0.0, 'end': 3.0, 'voStart': 0.30}]
        with self.assertRaises(SystemExit):
            narrate.place_in_film(timing, starts)


if __name__ == '__main__':
    unittest.main()
