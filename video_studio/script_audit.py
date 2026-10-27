#!/usr/bin/env python3
"""Fail-closed, topic-independent release audit for script-first motion films.

The automated checks establish file/clock provenance and technical measurements.
They do not establish meaning, speech accuracy, visual synchronization,
intelligibility, factual truth, accessibility or artistic quality. A named human
must watch/listen to the encoded video and assess every visual beat.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_studio import nokia_audit as shared, script_director as director  # noqa: E402
from video_studio.quality_audit import file_sha256  # noqa: E402
from video_studio.semantic_review import blank_beat_reviews, validate_beat_reviews, SemanticMismatch  # noqa: E402

PROFILE = 'script-motion-v1'
REPORT_FILE = 'script.audit.json'
REVIEW_FILE = 'script-review.json'
REQUIRED_INPUTS = (
    'release-profile.json', 'video.mp4', 'script.txt', 'script.md', 'script-plan.json',
    'render-plan.json', 'storyboard.json', 'shots.json', 'voice-timing.json', 'music-plan.json',
    'frame-timing.json', 'video.qc.json', 'voice-stem.wav', 'music-stem.wav',
)
MANUAL = ('narration_sync', 'narration_delivery', 'visual_relevance', 'pacing_motion',
          'music_balance', 'captions', 'clean_ending', 'factual_review')
AUTO = ('profile', 'script_coverage', 'technical_quality', 'frame_cadence', 'stream_coverage',
        'master_audio', 'stem_measurements')


def _file(root: Path, name: str) -> Path:
    return shared._file(root, name)


def manifest(root: Path, *, review: bool = False) -> dict:
    names = set(REQUIRED_INPUTS)
    names.update(p.name for p in root.iterdir() if p.suffix.lower() in {'.srt', '.vtt'}
                 and (p.is_file() or p.is_symlink()))
    if (root / 'effects-stem.wav').exists():
        names.add('effects-stem.wav')
    if review:
        names.add(REVIEW_FILE)
    return {name: file_sha256(path) for name in sorted(names)
            if (path := _file(root, name)).is_file()}


def _json(root: Path, name: str):
    return json.loads(_file(root, name).read_text(encoding='utf-8'))


def _result(status, detail, **extra):
    return {'status': status, 'detail': detail, **extra}


def validate_structure(root: Path, duration: float) -> dict:
    """Cross-check exact text, plan, picture clock, voice clock and review cues."""
    raw = _file(root, 'script.txt').read_bytes()
    if raw != _file(root, 'script.md').read_bytes():
        raise ValueError('script.md differs from the supplied narration')
    script = raw.decode('utf-8')
    plan = director.validate_plan(script, _json(root, 'script-plan.json'))
    render, shots, timing, storyboard = (_json(root, name) for name in
        ('render-plan.json', 'shots.json', 'voice-timing.json', 'storyboard.json'))
    if not isinstance(render, dict) or render.get('profile') != PROFILE or render.get('fps') != 30:
        raise ValueError('render plan profile or frame rate is invalid')
    frames, rows = render.get('frames'), render.get('beats')
    if (type(frames) is not int or frames <= 0 or not isinstance(rows, list)
            or len(rows) != len(plan['beats']) or len(shots) != len(rows) or len(timing) != len(rows)
            or render.get('script_sha256') != plan['script_sha256']):
        raise ValueError('render plan does not cover the exact script')
    clock = shared.validate_clock(shots, timing, duration)
    if abs(frames / 30 - duration) > .25 or clock['ending_tail_seconds'] < .20:
        raise ValueError('encoded duration or final narration tail does not fit the frame clock')
    expected_start = 0
    for beat, row, shot, line in zip(plan['beats'], rows, shots, timing):
        if not isinstance(row, dict) or row.get('id') != beat['id'] or line.get('text') != beat['text']:
            raise ValueError(f"{beat['id']}: picture or narration text differs from the exact source")
        sf, ef, vf = row.get('start_frame'), row.get('end_frame'), row.get('voice_start_frame')
        if (type(sf) is not int or type(ef) is not int or type(vf) is not int or sf != expected_start
                or ef <= sf or vf < sf or vf >= ef or row.get('visual') != beat['visual']):
            raise ValueError(f"{beat['id']}: frame/visual plan changed or contains a gap")
        if (abs(shot['start'] - sf / 30) > .002 or abs(shot['end'] - ef / 30) > .002
                or abs(line['start'] - vf / 30) > .002
                or abs(float(row.get('voice_end', -1)) - line['end']) > .002):
            raise ValueError(f"{beat['id']}: rendered frame clock differs from measured narration")
        expected_start = ef
    if expected_start != frames:
        raise ValueError('render frame clock does not cover the final frame')
    # Enumerating these checks structural coverage, not whether pictures mean
    # what they claim, nor whether the audio actually says the supplied words.
    beats = blank_beat_reviews(storyboard, shots, timing)
    return {'plan': plan, 'render': render, 'shots': shots, 'timing': timing,
            'storyboard': storyboard, 'clock': clock, 'beats': beats}


def init_review(root: Path, *, force: bool = False) -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('Package directory does not exist.')
    missing = [name for name in REQUIRED_INPUTS if not _file(root, name).is_file()]
    if missing:
        raise ValueError('Cannot initialize review without: ' + ', '.join(missing))
    if _json(root, 'release-profile.json') != {'profile': PROFILE}:
        raise ValueError('The script-first release profile is missing or invalid.')
    target = _file(root, REVIEW_FILE)
    if target.exists() and not force:
        raise ValueError(f'{REVIEW_FILE} already exists; use --force to replace it.')
    frames = _json(root, 'render-plan.json')['frames']
    evidence = validate_structure(root, frames / 30)
    checks = {name: {'status': 'unverified', 'note': ''} for name in MANUAL}
    checks['visual_relevance']['beats'] = evidence['beats']
    checks['captions']['mode'] = 'unverified'
    review = {'schema_version': 1, 'reviewed_by': '', 'reviewed_inputs': manifest(root), 'checks': checks,
              'instructions': 'Watch and listen to the entire encoded video. Describe actual evidence; '
                              'assess subject, action, relationship, qualifiers and timing for each beat.'}
    target.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target


def _review(review, binding: dict, key: str):
    if (not isinstance(review, dict) or review.get('schema_version') != 1
            or not isinstance(review.get('reviewed_by'), str) or not review['reviewed_by'].strip()
            or review.get('reviewed_inputs') != binding):
        return 'unverified', 'A named human review bound to these exact files is required.', {}
    checks = review.get('checks')
    item = checks.get(key) if isinstance(checks, dict) else None
    if not isinstance(item, dict):
        return 'unverified', 'Human check is missing.', {}
    if item.get('status') == 'fail':
        return 'failed', f"Reviewer reported a defect: {item.get('note', '')}", item
    if item.get('status') != 'pass' or not isinstance(item.get('note'), str) or len(item['note'].strip()) < 10:
        return 'unverified', 'A named reviewer must describe the evidence and pass this check.', item
    return 'attested', f"Reviewed by {review['reviewed_by']}: {item['note'].strip()}", item


def _technical(qc, video: Path):
    from video_studio.release_gate import validate_qc_report
    validate_qc_report(qc, video)
    checks = qc.get('checks') if isinstance(qc, dict) else None
    if not isinstance(checks, dict):
        raise ValueError('technical report lacks measured checks')
    for name, maximum in (('black_frames', .20), ('audio_silence', 1.5)):
        part = checks.get(name)
        threshold = shared.finite(part.get('threshold_seconds')) if isinstance(part, dict) else None
        if threshold is None or not 0 < threshold <= maximum or not isinstance(part.get('events'), list):
            raise ValueError(f'{name} was not checked at the required threshold')
        for event in part['events']:
            duration = shared.finite(event.get('duration')) if isinstance(event, dict) else None
            if duration is None or duration >= threshold:
                raise ValueError(f'{name} contains an unverified or failing interval')
    freeze = checks.get('freezes')
    threshold = shared.finite(freeze.get('threshold_seconds')) if isinstance(freeze, dict) else None
    if threshold is None or not 0 < threshold <= 3.0 or not isinstance(freeze.get('events'), list):
        raise ValueError('freeze detection was not measured at the required threshold')
    if freeze['events']:
        raise ValueError('freeze detection reported an interval needing correction')
    repeat = checks.get('repeat_frames')
    if not isinstance(repeat, dict) or repeat.get('status') != 'passed' or repeat.get('passed') is not True:
        raise ValueError('content-based held-picture check did not pass')
    threshold = shared.finite(repeat.get('limit_seconds'))
    longest = shared.finite(repeat.get('longest_still_seconds'))
    if threshold is None or not 0 < threshold <= 1.0 or longest is None or longest > 1.0:
        raise ValueError('held-picture check exceeded the one-second limit')
    return True


def audit_package(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('Package directory does not exist.')
    initial = manifest(root, review=True)
    binding = {k: v for k, v in initial.items() if k != REVIEW_FILE}
    missing = [name for name in REQUIRED_INPUTS if name not in initial]
    checks = {}
    try:
        if missing or _json(root, 'release-profile.json') != {'profile': PROFILE}:
            raise ValueError('Missing or invalid inputs: ' + ', '.join(missing))
        checks['profile'] = _result('passed', 'Script-first profile and required evidence are present.')
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks['profile'] = _result('unverified', str(exc))
    review = None
    try:
        review = _json(root, REVIEW_FILE)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    video = _file(root, 'video.mp4')
    duration, subtitle_streams = None, None
    try:
        probe = shared.probe_video(video)
        duration, subtitle_streams = shared._stream_coverage(probe)
        if subtitle_streams:
            raise ValueError('embedded subtitle tracks are not verified by this profile; use a reviewed sidecar')
        checks['stream_coverage'] = _result('passed', f'One video and one audio stream cover {duration:.3f}s.')
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        checks['stream_coverage'] = _result('unverified', str(exc))
    data = None
    try:
        if duration is None:
            raise ValueError('encoded video duration is unavailable')
        data = validate_structure(root, duration)
        checks['script_coverage'] = _result('passed', f"{len(data['beats'])} exact source spans on a contiguous measured clip clock.",
            limitation='Clip boundaries do not verify the actual spoken words or word-level sync.')
    except (OSError, TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        checks['script_coverage'] = _result('failed', str(exc))
    try:
        _technical(_json(root, 'video.qc.json'), video)
        checks['technical_quality'] = _result('passed', 'Strict black, silence, freeze and held-picture checks passed.')
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks['technical_quality'] = _result('failed', str(exc))
    try:
        from video_studio.script_production import encoded_cadence
        if data is None:
            raise ValueError('valid frame plan is unavailable')
        saved = _json(root, 'frame-timing.json')
        actual = encoded_cadence(video, data['render']['frames'])
        if saved != actual or actual.get('passed') is not True:
            raise ValueError('encoded frame timestamps/count differ from the frame plan or saved report')
        checks['frame_cadence'] = _result('passed', f"{actual['decoded_frames']} regular 30 fps timestamps.")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        checks['frame_cadence'] = _result('unverified', str(exc))
    master, levels = None, None
    try:
        lufs, peak = shared.measure_master(video)
        master = {'integrated_lufs': lufs, 'true_peak_dbtp': peak}
        if abs(lufs + 14) > 1.5 or peak > -1:
            checks['master_audio'] = _result('failed', f'{lufs:.1f} LUFS, {peak:.1f} dBTP; target -14 ±1.5 LUFS and ≤-1 dBTP.')
        else:
            checks['master_audio'] = _result('passed', f'{lufs:.1f} LUFS, {peak:.1f} dBTP.')
    except (OSError, RuntimeError, ValueError) as exc:
        checks['master_audio'] = _result('unverified', str(exc))
    recommendations = []
    try:
        if duration is None:
            raise ValueError('encoded video duration is unavailable')
        levels = shared.measure_stems(_file(root, 'voice-stem.wav'), _file(root, 'music-stem.wav'), duration)
        separation = shared.finite(levels.get('voice_above_music_db'))
        active = shared.finite(levels.get('active_seconds'))
        voice_level = shared.finite(levels.get('narration_active_rms_dbfs'))
        music_level = shared.finite(levels.get('music_under_narration_rms_dbfs'))
        if active is None or active <= 0 or voice_level is None or music_level is None or separation is None:
            checks['stem_measurements'] = _result('unverified', 'Speech-active narration and music levels could not both be measured.')
        elif separation <= 0:
            checks['stem_measurements'] = _result('failed', 'Music meets or exceeds narration during speech-active windows.')
        else:
            checks['stem_measurements'] = _result('passed', 'Aligned stem levels measured; intelligibility requires listening.')
        for key, label, low, high in (
            ('narration_active_rms_dbfs', 'Narration active RMS', -18, -12),
            ('narration_sample_peak_dbfs', 'Narration sample peak', -6, -3),
            ('music_under_narration_rms_dbfs', 'Music under narration', -30, -24),
        ):
            number = shared.finite(levels.get(key))
            if number is None:
                recommendations.append(f'{label} was not measurable.')
            elif not low <= number <= high:
                recommendations.append(f'{label} {number:.2f} dBFS is outside the recommended {low} to {high} dBFS range.')
        if (root / 'effects-stem.wav').exists():
            effects = shared.measure_effects(_file(root, 'effects-stem.wav'), duration)
            checks['stem_measurements']['effects'] = effects
            value = shared.finite(effects.get('active_rms_dbfs'))
            if value is None or not -18 <= value <= -10:
                recommendations.append('Effects level is unavailable or outside the recommended -18 to -10 dBFS range.')
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        checks['stem_measurements'] = _result('unverified', str(exc))
    for key in MANUAL:
        state, detail, item = _review(review, binding, key)
        if key == 'visual_relevance' and state == 'attested':
            if data is None:
                state, detail = 'unverified', 'A valid source/clock is needed for beat review.'
            else:
                try:
                    count = validate_beat_reviews(data['storyboard'], data['shots'], data['timing'], item.get('beats'))
                except SemanticMismatch as exc:
                    state, detail = 'failed', str(exc)
                except (ValueError, TypeError) as exc:
                    state, detail = 'unverified', str(exc)
                else:
                    detail += f' {count} visual beats reviewed.'
        if key == 'captions' and state == 'attested':
            sidecars = sorted(n for n in binding if Path(n).suffix.lower() in {'.srt', '.vtt'})
            mode = item.get('mode')
            try:
                if subtitle_streams is None or data is None:
                    raise ValueError('caption streams or timing could not be inspected')
                if mode == 'none':
                    if sidecars or subtitle_streams:
                        raise ValueError('captions exist despite a no-captions attestation')
                elif mode == 'sidecar':
                    if not sidecars or subtitle_streams:
                        raise ValueError('caption mode does not match the delivered tracks')
                    for name in sidecars:
                        shared.validate_sidecar(_file(root, name), data['timing'])
                else:
                    raise ValueError('caption mode must be none or sidecar')
            except (OSError, ValueError) as exc:
                state, detail = 'unverified', str(exc)
        checks[key] = _result(state, detail)
    final = manifest(root, review=True)
    if initial != final:
        checks['profile'] = _result('failed', 'Inputs changed while the audit was running; audit again.')
    states = {item['status'] for item in checks.values()}
    status = 'FAILED' if 'failed' in states else 'INCOMPLETE' if 'unverified' in states else 'PASSED'
    return {'schema_version': 1, 'profile': PROFILE, 'status': status, 'video_sha256': final.get('video.mp4'),
            'inputs': final, 'missing_inputs': missing, 'duration_seconds': duration, 'master': master,
            'stem_levels': levels, 'recommendations': recommendations, 'checks': checks,
            'scope_note': 'Technical/structural checks do not prove semantic meaning, actual speech, '
                          'perceptual motion, mix intelligibility or factual accuracy.'}


def validate_release_report(root: Path) -> dict:
    root = root.resolve()
    if _json(root, 'release-profile.json') != {'profile': PROFILE}:
        raise ValueError('Script-first release profile is missing or invalid.')
    report = _json(root, REPORT_FILE)
    if not isinstance(report, dict) or report.get('schema_version') != 1 or report.get('profile') != PROFILE or report.get('status') != 'PASSED':
        raise ValueError('Script-first audit is missing or not passed.')
    current = manifest(root, review=True)
    if any(name not in current for name in (*REQUIRED_INPUTS, REVIEW_FILE)) or current != report.get('inputs'):
        raise ValueError('Script-first audit inputs changed or are missing; review and audit again.')
    if report.get('video_sha256') != current['video.mp4']:
        raise ValueError('Script-first audit belongs to another video.')
    checks = report.get('checks')
    if not isinstance(checks, dict) or set(checks) != set(AUTO + MANUAL):
        raise ValueError('Script-first audit is missing required checks.')
    for key in AUTO + MANUAL:
        expected = 'attested' if key in MANUAL else 'passed'
        if not isinstance(checks.get(key), dict) or checks[key].get('status') != expected:
            raise ValueError(f'Script-first audit check {key} is not {expected}.')
    duration = shared.finite(report.get('duration_seconds'))
    if duration is None or duration <= 0:
        raise ValueError('Encoded duration is missing.')
    data = validate_structure(root, duration)
    _technical(_json(root, 'video.qc.json'), _file(root, 'video.mp4'))
    review = _json(root, REVIEW_FILE)
    binding = {k: v for k, v in current.items() if k != REVIEW_FILE}
    for key in MANUAL:
        if _review(review, binding, key)[0] != 'attested':
            raise ValueError(f'Script-first human review {key} is missing or stale.')
    validate_beat_reviews(data['storyboard'], data['shots'], data['timing'],
                          review['checks']['visual_relevance'].get('beats'))
    sidecars = sorted(n for n in binding if Path(n).suffix.lower() in {'.srt', '.vtt'})
    mode = review['checks']['captions'].get('mode')
    if mode == 'none' and sidecars:
        raise ValueError('Caption sidecars were not reviewed.')
    if mode == 'sidecar' and sidecars:
        for name in sidecars:
            shared.validate_sidecar(_file(root, name), data['timing'])
    elif mode != 'none':
        raise ValueError('Caption review mode does not match the package.')
    cadence = _json(root, 'frame-timing.json')
    if (not isinstance(cadence, dict) or cadence.get('passed') is not True
            or cadence.get('video_sha256') != current['video.mp4']
            or cadence.get('expected_frames') != data['render']['frames']
            or cadence.get('decoded_frames') != data['render']['frames']):
        raise ValueError('Encoded frame timing is missing or stale.')
    levels = report.get('stem_levels')
    if not isinstance(levels, dict) or any(shared.finite(levels.get(key)) is None for key in
            ('active_seconds', 'narration_active_rms_dbfs', 'music_under_narration_rms_dbfs', 'voice_above_music_db')):
        raise ValueError('Aligned speech-active narration/music measurements are missing.')
    if shared.finite(levels['active_seconds']) <= 0 or shared.finite(levels['voice_above_music_db']) <= 0:
        raise ValueError('Music is not measurably below active narration.')
    master = report.get('master')
    lufs = shared.finite(master.get('integrated_lufs')) if isinstance(master, dict) else None
    peak = shared.finite(master.get('true_peak_dbtp')) if isinstance(master, dict) else None
    if lufs is None or peak is None or abs(lufs + 14) > 1.5 or peak > -1:
        raise ValueError('Master loudness/true peak are missing or outside target.')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--init-review', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.package)
    try:
        if args.init_review:
            path = init_review(root, force=args.force)
            print(f'Blank, unverified human review created: {path}')
            return 0
        report = audit_package(root)
        _file(root.resolve(), REPORT_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return {'PASSED': 0, 'FAILED': 1, 'INCOMPLETE': 2}[report['status']]
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f'SCRIPT AUDIT COULD NOT RUN: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
