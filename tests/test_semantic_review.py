"""Semantic coverage is evidence structure, never a machine judgment of meaning."""
import copy
import unittest

from video_studio.semantic_review import (
    SemanticMismatch, blank_beat_reviews, expected_beats, validate_beat_reviews,
)


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.shots = [{'id': 's1', 'scene': 1, 'start': 0.0, 'end': 8.0, 'voStart': 0.2}]
        self.timing = [{'shot': 's1', 'text': 'A company grew. Its share then fell.',
                        'start': 0.2, 'end': 7.5, 'vo': 7.3}]
        self.storyboard = {'scenes': [{'scene': 1, 'shots': [{
            'id': 's1', 'scene': 1, 'narration': self.timing[0]['text'],
            'visualCues': [{'cue': '', 'visual': 'growth', 'start': 0.0, 'end': 4.0},
                           {'cue': 'Its share', 'visual': 'decline', 'start': 4.0, 'end': 8.0}],
        }]}]}

    def blank(self):
        return blank_beat_reviews(self.storyboard, self.shots, self.timing)

    def reviewed(self):
        rows = self.blank()
        for row in rows:
            row.update(status='pass', subject='the company', action='its market share changes',
                       relationship='the bars show the same change as the narration',
                       evidence='the named reviewer watched the encoded video with audio')
        return rows

    def test_splits_exact_words_and_leaves_everything_unverified(self):
        rows = self.blank()
        self.assertEqual(''.join(x['spoken_span'] for x in rows), self.timing[0]['text'])
        self.assertEqual([x['spoken_span'] for x in rows], ['A company grew. ', 'Its share then fell.'])
        self.assertTrue(all(x['status'] == 'unverified' for x in rows))
        with self.assertRaisesRegex(ValueError, 'unverified'):
            validate_beat_reviews(self.storyboard, self.shots, self.timing, rows)
        self.assertEqual(validate_beat_reviews(self.storyboard, self.shots, self.timing, self.reviewed()), 2)

    def test_unicode_case_matching_keeps_original_character_positions(self):
        text = 'Straße grew. Then it fell.'
        self.timing[0]['text'] = text
        shot = self.storyboard['scenes'][0]['shots'][0]
        shot['narration'] = text
        shot['visualCues'][1]['cue'] = 'then'
        rows = self.blank()
        self.assertEqual([x['spoken_span'] for x in rows], ['Straße grew. ', 'Then it fell.'])

    def test_rejects_uncovered_changed_and_failed_review_rows(self):
        rows = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'every visual cue'):
            validate_beat_reviews(self.storyboard, self.shots, self.timing, rows[:1])
        rows[0]['spoken_span'] = 'A different thing.'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            validate_beat_reviews(self.storyboard, self.shots, self.timing, rows)
        rows = self.reviewed()
        rows[1]['status'] = 'fail'
        with self.assertRaises(SemanticMismatch):
            validate_beat_reviews(self.storyboard, self.shots, self.timing, rows)

    def test_storyboard_must_cover_narration_and_picture_in_order(self):
        for edit in (
            lambda x: x['scenes'][0]['shots'][0].update(narration='changed words'),
            lambda x: x['scenes'][0]['shots'][0]['visualCues'][1].update(cue='missing words'),
            lambda x: x['scenes'][0]['shots'][0]['visualCues'][1].update(start=4.1),
            lambda x: x['scenes'][0]['shots'][0]['visualCues'][1].update(end=float('nan')),
            lambda x: x['scenes'][0]['shots'][0].update(visualCues=[]),
        ):
            story = copy.deepcopy(self.storyboard)
            edit(story)
            with self.subTest(story=story), self.assertRaises(ValueError):
                expected_beats(story, self.shots, self.timing)


if __name__ == '__main__':
    unittest.main()
