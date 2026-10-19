import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'video_studio'))
from captions import build_subtitles, validate_subtitle_text

class SubtitleParityTests(unittest.TestCase):
    def setUp(self):
        self.srt, self.vtt = build_subtitles({'scenes': [{'narration': 'Research the topic carefully.', 'duration_seconds': 4}, {'narration': 'Explain the evidence clearly.', 'duration_seconds': 4}]})
    def test_generated_sidecars_match(self):
        self.assertGreater(validate_subtitle_text(self.srt, self.vtt)['cue_count'], 0)
    def test_rejects_text_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'text differs'):
            validate_subtitle_text(self.srt, self.vtt.replace('Research the topic carefully.', 'Research the topic incorrectly.'))
    def test_rejects_timing_mismatch(self):
        changed = self.vtt.replace('00:00:00.000 --> 00:00:04.000', '00:00:00.100 --> 00:00:04.000', 1)
        with self.assertRaisesRegex(ValueError, 'timings differ'):
            validate_subtitle_text(self.srt, changed)
    def test_rejects_missing_cue(self):
        blocks = self.vtt.split('\n\n')
        with self.assertRaisesRegex(ValueError, 'cue counts'):
            validate_subtitle_text(self.srt, '\n\n'.join(blocks[:-1]) + '\n')

if __name__ == '__main__':
    unittest.main()
