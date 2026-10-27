"""Source fidelity, directional tripwires and review gates for script-first films."""
import copy
import json
import math
import shutil
import subprocess
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from video_studio import quality_audit, script_director as director, script_production as production, script_audit as audit
from video_studio.release_gate import validate_project_audit, requires_script_profile, require_nokia_audit_if_applicable

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'video_studio' / 'examples' / 'script_motion'


def example(name):
    script = (EXAMPLES / f'{name}.txt').read_text(encoding='utf-8')
    visuals = json.loads((EXAMPLES / f'{name}.visuals.json').read_text(encoding='utf-8'))['visuals']
    return script, visuals


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def tone(path, seconds=.7, rate=48000):
    frames = round(seconds * rate)
    data = b''.join(struct.pack('<h', round(3000 * math.sin(2 * math.pi * 400 * i / rate))) for i in range(frames))
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(data)


class ExactScriptTests(unittest.TestCase):
    def test_spans_preserve_every_character_and_numeric_punctuation(self):
        script = '  Mr. Bell paid 5.44 units.\r\n\r\nThen 1,000 users replied!  آخر؟\n'
        beats = director.split_script(script)
        self.assertEqual(''.join(script[b['source_start']:b['source_end']] for b in beats), script)
        self.assertEqual([b['text'] for b in beats], [
            'Mr. Bell paid 5.44 units.', 'Then 1,000 users replied!', 'آخر؟'])
        self.assertEqual(director.DIGIT.findall(script), ['5.44', '1,000'])

    def test_long_unpunctuated_script_is_rejected_not_arbitrarily_split(self):
        with self.assertRaisesRegex(director.PlanError, 'too long'):
            director.split_script('word ' * 100)

    def test_previous_plan_is_bound_to_exact_script_and_offsets(self):
        script, visuals = example('systems')
        plan = director.make_plan(script, visuals)
        self.assertEqual(director.validate_plan(script, plan)['beats'], plan['beats'])
        with self.assertRaisesRegex(director.PlanError, 'different script'):
            director.validate_plan(script.replace('server', 'router', 1), plan)
        plan['beats'][0]['text'] = 'Model wrote a different sentence.'
        with self.assertRaisesRegex(director.PlanError, 'changed'):
            director.validate_plan(script, plan)

    def test_all_three_unrelated_examples_plan_without_topic_research(self):
        for name in ('systems', 'nature', 'numbers'):
            with self.subTest(name=name):
                script, visuals = example(name)
                plan = director.make_plan(script, visuals)
                self.assertEqual(plan['semantic_status'], 'unverified')
                self.assertEqual([b['text'] for b in plan['beats']], [b['text'] for b in director.split_script(script)])

    def test_plan_only_cli_path_preserves_bytes_and_never_researches(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'workspace').mkdir()
            script = root / 'source.txt'; original = b'A server sends a message to a laptop.\r\nThe laptop does not send a message to the server.\r\n'
            script.write_bytes(original)
            args = Namespace(out='workspace/out', script=str(script), plan=str(EXAMPLES / 'systems.visuals.json'),
                             render=False, language='en', voice='bm_george', voice_dir=None,
                             captions=False, scale=.5, crf=18)
            with patch.object(production, 'ROOT', root), patch.object(production, 'load_config', return_value={}):
                self.assertEqual(production.run(args), 0)
            output = root / 'workspace' / 'out'
            self.assertEqual((output / 'script.txt').read_bytes(), original)
            self.assertEqual((output / 'script.md').read_bytes(), original)
            status = json.loads((output / 'package-status.json').read_text())
            self.assertFalse(status['topic_research_performed'])
            self.assertFalse(status['publishable'])

    def test_local_model_http_protocol_with_a_stub_not_a_real_model(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from threading import Thread
        script = (EXAMPLES / 'systems.txt').read_text(encoding='utf-8')
        choices = json.loads((EXAMPLES / 'systems.visuals.json').read_text(encoding='utf-8'))['visuals']
        requests = []
        class Stub(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(request)
                body = json.dumps({'choices': [{'message': {'content': json.dumps({'visuals': choices})}}]}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Stub)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            cfg = {'model': {'enabled': True, 'base_url': f'http://127.0.0.1:{server.server_port}/v1/chat/completions',
                             'model': 'test-stub'}}
            plan = director.model_plan(script, cfg)
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertEqual([row['text'] for row in plan['beats']], [beat['text'] for beat in director.split_script(script)])
        self.assertEqual(len(requests), 1)
        payload = json.loads(requests[0]['messages'][1]['content'])
        self.assertEqual([b['id'] for b in payload['beats']], ['b0001', 'b0002'])
        self.assertIn('not a writer or researcher', requests[0]['messages'][0]['content'])

    def test_bom_is_not_silently_read_as_a_spoken_word(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'script.txt'
            path.write_bytes(b'\xef\xbb\xbfHello.')
            with self.assertRaisesRegex(ValueError, 'BOM'):
                production.read_exact_script(path)


class SemanticTripwireTests(unittest.TestCase):
    def test_negation_cannot_be_rendered_as_a_completed_transfer(self):
        script, visuals = example('systems')
        visuals[1]['graphic']['type'] = 'transfer'
        with self.assertRaisesRegex(director.PlanError, 'negated narration'):
            director.make_plan(script, visuals)

    def test_blocked_visual_needs_an_actual_negated_action(self):
        script, visuals = example('systems')
        visuals[0]['graphic']['type'] = 'blocked'
        with self.assertRaisesRegex(director.PlanError, 'needs a narrated negation'):
            director.make_plan(script, visuals)

    def test_unicode_negation_is_not_shown_as_completed(self):
        script = 'سرور پیغام نہیں بھیجتا۔'
        visual = {'id': 'b0001', 'subject': 'سرور', 'action': 'نہیں بھیجتا', 'object': 'پیغام',
                  'qualifiers': 'منفی', 'focus_quote': 'پیغام نہیں بھیجتا', 'mood': 'tense',
                  'graphic': {'type': 'transfer', 'from': {'icon': 'server', 'label': 'سرور'},
                              'to': {'icon': 'laptop', 'label': 'لیپ ٹاپ'},
                              'item': {'icon': 'message', 'label': 'پیغام'}, 'relation': 'بھیجتا'}}
        with self.assertRaisesRegex(director.PlanError, 'negated narration'):
            director.make_plan(script, [visual])

    def test_negated_action_label_must_keep_the_negation(self):
        script, visuals = example('systems')
        visuals[1]['graphic']['relation'] = 'send'
        with self.assertRaisesRegex(director.PlanError, 'retain the negation'):
            director.make_plan(script, visuals)

    def test_reversed_relationship_is_detected(self):
        script, visuals = example('systems')
        graph = visuals[0]['graphic']
        graph['from'], graph['to'] = graph['to'], graph['from']
        with self.assertRaisesRegex(director.PlanError, 'direction is reversed'):
            director.make_plan(script, visuals)

    def test_receives_from_relationship_is_detected(self):
        script = 'The laptop receives a message from the server.'
        _, visuals = example('systems')
        item = copy.deepcopy(visuals[0])
        item['focus_quote'] = 'laptop receives a message'
        item['graphic']['relation'] = 'receives'
        item['graphic']['from'], item['graphic']['to'] = item['graphic']['to'], item['graphic']['from']
        with self.assertRaisesRegex(director.PlanError, 'direction is reversed'):
            director.make_plan(script, [item])

    def test_invented_chart_value_and_numeric_substring_are_rejected(self):
        script, visuals = example('numbers')
        visuals[0]['graphic']['bars'][1].update({'value': '30', 'source': '30'})
        with self.assertRaises(director.PlanError):
            director.make_plan(script, visuals)
        script, visuals = example('numbers')
        script = script.replace('10 liters', '100 liters')
        with self.assertRaisesRegex(director.PlanError, 'occur exactly'):
            visuals[0]['focus_quote'] = 'Water usage fell from 20 to 100 liters'
            director.make_plan(script, visuals)

    def test_invented_number_attached_to_a_unit_is_rejected(self):
        script, visuals = example('systems')
        visuals[0]['graphic']['item']['label'] = '3.2x message'
        with self.assertRaisesRegex(director.PlanError, 'displayed number'):
            director.make_plan(script, visuals)

    def test_chart_hides_final_value_while_its_bar_is_still_growing(self):
        if not shutil.which('node'):
            self.skipTest('Node is required for the drawing primitive')
        program = ("import {chartBarState} from './video_studio/motion/chart.mjs';"
                   "console.log(JSON.stringify([chartBarState(10,20,.5),chartBarState(10,20,1)]));")
        result = subprocess.run(['node', '--input-type=module', '-e', program], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        halfway, complete = json.loads(result.stdout)
        self.assertEqual(halfway['relativeHeight'], .25)
        self.assertFalse(halfway['labelVisible'])
        self.assertEqual(complete['relativeHeight'], .5)
        self.assertTrue(complete['labelVisible'])

    def test_chart_cannot_reverse_the_narrated_value_order(self):
        script, visuals = example('numbers')
        visuals[0]['graphic']['bars'].reverse()
        with self.assertRaisesRegex(director.PlanError, 'narrated order'):
            director.make_plan(script, visuals)

    def test_no_unsupported_or_unrelated_icon_fallback(self):
        script, visuals = example('systems')
        visuals[0]['graphic']['from']['icon'] = 'generic_stock_photo'
        with self.assertRaisesRegex(director.PlanError, 'unsupported icon'):
            director.make_plan(script, visuals)
        visuals[0]['graphic'] = {'type': 'unsupported'}
        with self.assertRaisesRegex(director.PlanError, 'unsupported visual'):
            director.make_plan(script, visuals)

    def test_unrelated_but_supported_icon_label_does_not_fill_a_gap(self):
        script, visuals = example('systems')
        visuals[0]['graphic']['from'] = {'icon': 'building', 'label': 'factory'}
        with self.assertRaisesRegex(director.PlanError, 'not present'):
            director.make_plan(script, visuals)

    def test_missing_or_changed_quote_is_not_a_caption(self):
        script, visuals = example('systems')
        visuals[0]['focus_quote'] = 'The server invented a result'
        with self.assertRaisesRegex(director.PlanError, 'not a literal quote'):
            director.make_plan(script, visuals)

    def test_growth_direction_and_comparison_order(self):
        script = 'Sales fell.'
        visual = {'id': 'b0001', 'subject': 'sales', 'action': 'fell', 'object': 'none',
                  'qualifiers': 'none', 'focus_quote': 'Sales fell', 'mood': 'sparse',
                  'graphic': {'type': 'focus', 'node': {'icon': 'abstract', 'label': 'Sales'}, 'effect': 'grow'}}
        with self.assertRaisesRegex(director.PlanError, 'contradicts'):
            director.make_plan(script, [visual])
        script = 'A is smaller than B.'
        visual.update({'focus_quote': 'A is smaller than B', 'graphic': {'type': 'compare',
                       'left': {'icon': 'abstract', 'label': 'B'}, 'right': {'icon': 'abstract', 'label': 'A'},
                       'relation': 'smaller than'}})
        with self.assertRaisesRegex(director.PlanError, 'reverses'):
            director.make_plan(script, [visual])


class LocalPlannerTests(unittest.TestCase):
    def test_model_only_supplies_visuals_source_text_remains_unchanged(self):
        script, visuals = example('systems')
        calls = []
        def post(url, body, timeout):
            calls.append((url, body, timeout))
            altered = copy.deepcopy(visuals)
            altered[0]['narration'] = 'This is invented text and must be ignored.'
            return {'choices': [{'message': {'content': json.dumps({'visuals': altered})}}]}
        cfg = {'model': {'enabled': True, 'base_url': 'http://127.0.0.1:8080/v1/chat/completions'}}
        plan = director.model_plan(script, cfg, post=post)
        self.assertEqual([b['text'] for b in plan['beats']], [b['text'] for b in director.split_script(script)])
        self.assertIn('not a writer or researcher', calls[0][1]['messages'][0]['content'])
        self.assertEqual(calls[0][1]['max_tokens'], 1200)
        self.assertEqual(plan['semantic_status'], 'unverified')

    def test_model_batch_limits_are_explicit_and_fail_closed(self):
        script, _ = example('systems')
        for setting in ({'visual_batch_size': 0}, {'visual_max_output_tokens': 499},
                        {'visual_batch_size': 'not-a-number'}):
            with self.subTest(setting=setting), self.assertRaises(director.PlanError):
                director.model_plan(script, {'model': {'enabled': True, **setting}}, post=lambda *a, **kw: None)

    def test_unavailable_model_does_not_fall_back_to_stock_visuals(self):
        script, _ = example('systems')
        with self.assertRaisesRegex(director.PlanError, 'No stock visual'):
            director.model_plan(script, {})

    def test_malformed_or_missing_beats_fail(self):
        script, _ = example('systems')
        cfg = {'model': {'enabled': True}}
        with self.assertRaisesRegex(director.PlanError, 'invalid JSON'):
            director.model_plan(script, cfg, post=lambda *a, **kw: {'choices': [{'message': {'content': 'bad'}}]})
        with self.assertRaisesRegex(director.PlanError, 'every beat'):
            director.model_plan(script, cfg, post=lambda *a, **kw: {'choices': [{'message': {'content': '{"visuals":[]}'}}]})


class MeasuredClockTests(unittest.TestCase):
    def test_recorded_clips_drive_contiguous_picture_clock_and_tail(self):
        script, visuals = example('systems'); plan = director.make_plan(script, visuals)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            tone(directory / 'b0001.wav', .77); tone(directory / 'b0002.wav', 1.31)
            render, shots, timing, storyboard = production.measured_clock(plan, directory)
            self.assertEqual(render['frames'], shots[-1]['end'] * 30)
            self.assertEqual(shots[0]['end'], shots[1]['start'])
            self.assertAlmostEqual(timing[0]['vo'], .77)
            self.assertAlmostEqual(timing[1]['vo'], 1.31)
            self.assertGreater(shots[-1]['end'] - timing[-1]['end'], .2)
            self.assertEqual(storyboard['scenes'][0]['shots'][0]['narration'], plan['beats'][0]['text'])
            self.assertIn('unverified', render['timing_note'])

    def test_missing_silent_and_wrong_format_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaises((FileNotFoundError, ValueError)):
                production.pcm_info(directory / 'missing.wav')
            path = directory / 'silence.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(b'\0\0' * 5000)
            with self.assertRaisesRegex(ValueError, 'silent'):
                production.pcm_info(path)
            tone(directory / 'wrong.wav', .7, 22050)
            with self.assertRaisesRegex(ValueError, '48 kHz'):
                production.pcm_info(directory / 'wrong.wav')

    def test_decoder_failure_with_stderr_never_becomes_a_pass(self):
        import io
        from video_studio import repeat_frames
        class BrokenDecoder:
            def __init__(self):
                self.stdout = io.BytesIO(b'')
                self.stderr = io.BytesIO(b'corrupt input')
                self.returncode = 1
            def wait(self, timeout):
                return 1
        with patch.object(repeat_frames.subprocess, 'Popen', return_value=BrokenDecoder()):
            with self.assertRaisesRegex(RuntimeError, 'corrupt input'):
                list(repeat_frames.iter_video_frames(Path('bad.mp4'), fps=10, width=2, height=2, ffmpeg='ffmpeg'))

    def test_freeze_at_eof_is_not_discarded(self):
        events = quality_audit.parse_freeze_events('freeze_start: 2.0', 10)
        self.assertEqual(events[0]['duration'], 8)
        self.assertTrue(events[0]['continues_to_eof'])
        events = quality_audit.parse_freeze_events('freeze_start: 1 freeze_duration: 3 freeze_end: 4\nfreeze_start: 7', 10)
        self.assertEqual([event['duration'] for event in events], [3, 3])


class GeneralReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        script, visuals = example('systems'); self.plan = director.make_plan(script, visuals)
        self.root.joinpath('script.txt').write_bytes(script.encode()); self.root.joinpath('script.md').write_bytes(script.encode())
        write_json(self.root / 'script-plan.json', self.plan); write_json(self.root / 'release-profile.json', {'profile': audit.PROFILE})
        voice = self.root / 'voice'; voice.mkdir()
        tone(voice / 'b0001.wav'); tone(voice / 'b0002.wav')
        render, shots, timing, storyboard = production.measured_clock(self.plan, voice)
        self.duration = render['frames'] / 30
        for name, value in (('render-plan.json', render), ('shots.json', shots), ('voice-timing.json', timing), ('storyboard.json', storyboard), ('music-plan.json', {})):
            write_json(self.root / name, value)
        self.video = self.root / 'video.mp4'; self.video.write_bytes(b'fake test bytes' * 100)
        (self.root / 'voice-stem.wav').write_bytes(b'voice'); (self.root / 'music-stem.wav').write_bytes(b'music')
        from video_studio.quality_audit import file_sha256
        self.cadence = {'video_sha256': file_sha256(self.video), 'fps': 30, 'expected_frames': render['frames'],
                        'decoded_frames': render['frames'], 'max_timestamp_error_seconds': 0, 'passed': True,
                        'scope': 'Encoded frame timestamps only; not perceptual smoothness.'}
        write_json(self.root / 'frame-timing.json', self.cadence)
        self.qc = {'video_sha256': file_sha256(self.video), 'strict': True, 'passed': True, 'warnings': [],
                   'duration_seconds': self.duration, 'audio_stream_count': 1,
                   'checks': {'black_frames': {'threshold_seconds': .2, 'events': []},
                              'audio_silence': {'threshold_seconds': 1.5, 'events': []},
                              'freezes': {'threshold_seconds': 3.0, 'events': []},
                              'repeat_frames': {'status': 'passed', 'passed': True, 'limit_seconds': 1.0, 'longest_still_seconds': .5}}}
        write_json(self.root / 'video.qc.json', self.qc)
        audit.init_review(self.root)
        self.probe = {'format': {'duration': str(self.duration)}, 'streams': [
            {'codec_type': 'video', 'start_time': '0', 'duration': str(self.duration)},
            {'codec_type': 'audio', 'start_time': '0', 'duration': str(self.duration)}]}
        self.levels = {'active_seconds': 1.4, 'narration_active_rms_dbfs': -15, 'narration_sample_peak_dbfs': -4,
                       'music_under_narration_rms_dbfs': -27, 'voice_above_music_db': 12}

    def tearDown(self):
        self.temp.cleanup()

    def complete_review(self):
        path = self.root / audit.REVIEW_FILE; review = json.loads(path.read_text())
        review['reviewed_by'] = 'A real reviewer'
        for item in review['checks'].values():
            item.update(status='pass', note='Watched and listened to the encoded evidence.')
        review['checks']['captions']['mode'] = 'none'
        for beat in review['checks']['visual_relevance']['beats']:
            beat.update(status='pass', subject='server or laptop', action='sends or is blocked',
                        relationship='source and destination match speech', evidence='Watched and listened to this interval')
        write_json(path, review)

    def run_audit(self):
        with patch.object(audit.shared, 'probe_video', return_value=self.probe), \
             patch.object(audit.shared, 'measure_master', return_value=(-14, -1.5)), \
             patch.object(audit.shared, 'measure_stems', return_value=self.levels), \
             patch.object(production, 'encoded_cadence', return_value=self.cadence):
            return audit.audit_package(self.root)

    def test_technical_success_alone_cannot_approve(self):
        report = self.run_audit()
        self.assertEqual(report['status'], 'INCOMPLETE', report['checks'])
        self.assertEqual(report['checks']['visual_relevance']['status'], 'unverified')
        self.assertEqual(report['checks']['narration_sync']['status'], 'unverified')

    def test_full_named_review_is_hash_bound_and_rechecked(self):
        self.complete_review(); report = self.run_audit()
        self.assertEqual(report['status'], 'PASSED', report['checks'])
        write_json(self.root / audit.REPORT_FILE, report)
        self.assertEqual(validate_project_audit(self.root)['profile'], audit.PROFILE)
        (self.root / 'script.md').write_text('Different narration.')
        with self.assertRaisesRegex(ValueError, 'changed'):
            validate_project_audit(self.root)

    def test_each_beat_must_be_reviewed_and_failed_beats_block(self):
        self.complete_review(); path = self.root / audit.REVIEW_FILE; review = json.loads(path.read_text())
        review['checks']['visual_relevance']['beats'][1]['status'] = 'fail'; write_json(path, review)
        report = self.run_audit()
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['checks']['visual_relevance']['status'], 'failed')

    def test_missing_profile_or_loose_repeat_limit_cannot_bypass_review(self):
        self.assertTrue(requires_script_profile(self.root))
        (self.root / 'release-profile.json').unlink()
        with self.assertRaisesRegex(ValueError, 'profile is missing'):
            validate_project_audit(self.root)
        self.qc['checks']['repeat_frames']['limit_seconds'] = 3
        with self.assertRaisesRegex(ValueError, 'one-second'):
            audit._technical(self.qc, self.video)

    def test_nokia_film_cannot_use_generic_profile_instead_of_nokia_audit(self):
        with self.assertRaisesRegex(ValueError, 'Nokia 15-minute'):
            require_nokia_audit_if_applicable(self.root, {'profile': audit.PROFILE}, title='Nokia Rise and Fall')


if __name__ == '__main__':
    unittest.main()
