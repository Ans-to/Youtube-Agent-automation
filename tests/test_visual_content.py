"""Legacy graphics must not fabricate missing chart, quote or process content."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from video_studio.production import require_authored_visual_content

ROOT = Path(__file__).resolve().parents[1]


class LegacyGraphicContentTests(unittest.TestCase):
    def test_incomplete_visual_metadata_is_rejected_before_voice_work(self):
        for kind in ('stat', 'diagram', 'timeline', 'comparison', 'quote', 'code'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'requires explicit visual content'):
                require_authored_visual_content({'visual_type': kind}, 1)
        for scene in (
            {'visual_type': 'stat', 'stat_value': '20', 'stat_label': 'liters'},
            {'visual_type': 'diagram', 'visual_nodes': ['source', 'receiver']},
            {'visual_type': 'timeline', 'timeline_events': ['first', 'second']},
            {'visual_type': 'comparison', 'comparison_left_title': 'A', 'comparison_right_title': 'B',
             'comparison_left': ['one'], 'comparison_right': ['two']},
            {'visual_type': 'quote', 'quote': 'Explicit words.'},
            {'visual_type': 'code', 'code_lines': ['print(1)']},
        ):
            require_authored_visual_content(scene, 1)

    def test_node_validator_refuses_missing_values_in_both_renderers(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is unavailable')
        cases = [
            {'visual_type': 'stat'}, {'visual_type': 'quote'}, {'visual_type': 'diagram'},
            {'visual_type': 'timeline'}, {'visual_type': 'code'}, {'visual_type': 'comparison'},
            {'visual_type': 'bar-chart', 'chart_values': [4, 7], 'chart_labels': ['A', '']},
        ]
        script = ("const v=require('./video_studio/visual_content.cjs');"
                  "const rows=JSON.parse(process.argv[1]);"
                  "process.stdout.write(JSON.stringify(rows.map(x=>v.contentProblem(x,x.visual_type))));")
        result = subprocess.run([node, '-e', script, json.dumps(cases)], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertTrue(all(json.loads(result.stdout)))
        for name in ('render.js', 'render_skia.js'):
            self.assertIn('contentProblem(scene', (ROOT / 'video_studio' / name).read_text())

    def test_render_html_contains_no_claim_or_number_defaults(self):
        source = (ROOT / 'video_studio' / 'render.html').read_text(encoding='utf-8')
        for invented in ('The clearest idea wins.', 'MEASURED IMPACT', '[4,7,5,9]',
                         '["Manual","Slow","Scattered"]', '"3.2×"'):
            self.assertNotIn(invented, source)


if __name__ == '__main__':
    unittest.main()
