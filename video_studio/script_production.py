#!/usr/bin/env python3
"""Produce a motion-graphics draft from an exact supplied narration script.

No topic research, script writing, stock imagery or invented filler graphics.
A local model can propose a declarative beat plan; an authored plan can be used
instead. The plan is validated before audio/rendering. A rendered file is a
DRAFT until technical, beat-level semantic and listening reviews are complete.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import textwrap
import wave
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
for directory in (str(ROOT), str(BASE)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe  # noqa: E402
from video_studio import script_director as director  # noqa: E402

FPS = 30
SR = 48_000
PROFILE = 'script-motion-v1'


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_exact_script(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('Script must be an existing UTF-8 file of at most 2 MB.')
    raw = path.read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError('Remove the UTF-8 BOM; it is not part of the spoken script.')
    return raw.decode('utf-8')


def workspace_output(path: str) -> Path:
    workspace = (ROOT / 'workspace').resolve()
    output = Path(path).expanduser()
    output = (ROOT / output).resolve() if not output.is_absolute() else output.resolve()
    if output == workspace or workspace not in output.parents:
        raise ValueError('Output must be a subdirectory of the project workspace.')
    return output


def load_config() -> dict:
    path = ROOT / 'config.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('config.json must contain an object.')
    return data


def authored_or_model_plan(script: str, plan_file: Path | None, config: dict) -> dict:
    if plan_file is None:
        return director.model_plan(script, config)
    value = json.loads(plan_file.read_text(encoding='utf-8'))
    if isinstance(value, dict) and 'visuals' in value:
        return director.make_plan(script, value['visuals'], origin='authored; semantic meaning unverified')
    return director.validate_plan(script, value)


def pcm_info(path: Path) -> tuple[int, int]:
    """Check format, length and some actual nonzero audio, not speech accuracy."""
    try:
        with wave.open(str(path), 'rb') as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SR:
                raise ValueError(f'{path.name}: narration must be mono 48 kHz PCM16')
            frames = wav.getnframes()
            if frames < SR // 20:
                raise ValueError(f'{path.name}: narration clip is missing or too short')
            audible = False
            while chunk := wav.readframes(65536):
                # PCM16 zero is two zero bytes; not a speech/intelligibility test.
                if chunk.strip(b'\x00'):
                    audible = True
                    break
            if not audible:
                raise ValueError(f'{path.name}: narration clip is silent')
    except (wave.Error, EOFError) as exc:
        raise ValueError(f'{path.name}: invalid PCM WAV') from exc
    return frames, SR


def synthesize(plan: dict, directory: Path, *, language: str, voice: str,
               external_dir: Path | None, config: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    beats = plan['beats']
    if external_dir is not None:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError('FFmpeg is required to normalize supplied narration clips.')
        for beat in beats:
            source = external_dir / f"{beat['id']}.wav"
            if not source.is_file():
                raise ValueError(f'Missing supplied narration clip {source.name}.')
            target = directory / source.name
            if source.resolve() == target.resolve():
                raise ValueError('The external voice directory must differ from the output voice directory.')
            subprocess.run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source),
                            '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', str(target)],
                           check=True, timeout=300)
            pcm_info(target)
        return
    if language == 'en':
        from video_studio import voice as V
        V.require_engine('kokoro')
        V.set_profile('calm')
        for beat in beats:
            # Only surrounding source whitespace is removed. No model-generated
            # text is accepted as narration.
            audio = V.synth(beat['text'], voice, base_rate=.95)
            target = directory / f"{beat['id']}.wav"
            V.write_wav(target, audio)
            pcm_info(target)
            print(f"Narration {beat['id']}: {beat['text'][:75]}", flush=True)
        return
    if language == 'ur-en':
        from video_studio.voice_backends import get_urdu_tts_command, resolve_urdu_tts_command
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError('FFmpeg is required for the configured Urdu voice.')
        template = get_urdu_tts_command(config)
        raw_dir = directory / 'raw'
        raw_dir.mkdir(exist_ok=True)
        items = []
        for beat in beats:
            text_path = raw_dir / f"{beat['id']}.txt"
            audio_path = raw_dir / f"{beat['id']}.wav"
            text_path.write_text(beat['text'], encoding='utf-8')
            items.append({'text_file': str(text_path.resolve()), 'output_file': str(audio_path.resolve())})
        if any('{manifest_file}' in item for item in template):
            manifest = raw_dir / 'manifest.json'
            write_json(manifest, {'schema_version': 1, 'items': items})
            subprocess.run(resolve_urdu_tts_command(template, manifest_file=manifest), cwd=ROOT,
                           check=True, timeout=max(900, min(7200, len(items) * 120)))
        else:
            for item in items:
                subprocess.run(resolve_urdu_tts_command(template, text_file=item['text_file'],
                                                       output_file=item['output_file']),
                               cwd=ROOT, check=True, timeout=600)
        for beat, item in zip(beats, items):
            raw = Path(item['output_file'])
            if not raw.is_file() or raw.stat().st_size == 0:
                raise ValueError(f"Urdu adapter did not create {beat['id']}.wav")
            target = directory / f"{beat['id']}.wav"
            subprocess.run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-i', str(raw),
                            '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', str(target)],
                           check=True, timeout=300)
            pcm_info(target)
        return
    raise ValueError('Unsupported narration language.')


def measured_clock(plan: dict, voice_dir: Path) -> tuple[dict, list[dict], list[dict], dict]:
    """Derive a single contiguous frame/sample clock from the actual WAVs."""
    frame = 0
    rendered, shots, timing, scenes = [], [], [], []
    beats = plan.get('beats', [])
    if not beats:
        raise ValueError('A complete plan is required before timing.')
    for index, beat in enumerate(beats):
        samples, rate = pcm_info(voice_dir / f"{beat['id']}.wav")
        lead = 8 if index == 0 else 5
        tail = 20 if index == len(beats) - 1 else 6
        voiced_frames = math.ceil(samples * FPS / rate)
        end_frame = frame + lead + voiced_frames + tail
        start, end = frame / FPS, end_frame / FPS
        vo_start = (frame + lead) / FPS
        vo_end = vo_start + samples / rate
        shot = {'id': beat['id'], 'scene': index + 1, 'start': start, 'end': end, 'voStart': vo_start}
        line = {'shot': beat['id'], 'file': f"{beat['id']}.wav", 'start': vo_start, 'end': vo_end,
                'vo': samples / rate, 'samples': samples, 'sample_rate': rate, 'text': beat['text']}
        visual = beat['visual']
        description = f"{visual['graphic']['type']}: {visual['subject']} / {visual['action']} / {visual['object']}"
        storyboard_shot = {'id': beat['id'], 'scene': index + 1, 'narration': beat['text'],
                           'visualCues': [{'cue': '', 'visual': description, 'start': start, 'end': end}]}
        scenes.append({'scene': index + 1, 'shots': [storyboard_shot]})
        rendered.append({'id': beat['id'], 'start_frame': frame, 'end_frame': end_frame,
                         'voice_start_frame': frame + lead, 'voice_end': vo_end, 'visual': visual})
        shots.append(shot); timing.append(line); frame = end_frame
    render_plan = {'schema_version': 1, 'profile': PROFILE, 'fps': FPS, 'frames': frame,
                   'script_sha256': plan['script_sha256'], 'beats': rendered,
                   'timing_note': 'PCM clip boundaries measured; within-clip word alignment is unverified.'}
    return render_plan, shots, timing, {'schema_version': 1, 'scenes': scenes}


def score_sections(plan: dict, shots: list[dict]) -> list[tuple[str, float, float]]:
    sections = []
    for beat, shot in zip(plan['beats'], shots):
        mood = beat['visual']['mood']
        if sections and sections[-1][0] == mood:
            sections[-1] = (mood, sections[-1][1], shot['end'])
        else:
            sections.append((mood, shot['start'], shot['end']))
    return sections


def make_audio(plan: dict, root: Path, shots: list[dict], timing: list[dict]) -> None:
    from video_studio import narrate, score
    voice_dir = root / 'voice'
    write_json(voice_dir / 'timing.json', timing)
    sections = score_sections(plan, shots)
    write_json(root / 'music-plan.json', {'sections': [
        {'mood': mood, 'start': start, 'end': end} for mood, start, end in sections],
        'note': 'Procedural score is a draft; encoded mix and intelligibility require listening.'})
    music = score.build(shots[-1]['end'], sections, stereo=False)
    score.write_wav(root / 'score.wav', music)
    del music
    narrate.mix(voice_dir, root / 'score.wav', root / 'master.wav', starts_path=root / 'shots.json',
                duck=.32, score_gain=.55, target_lufs=-14, ceiling_dbfs=-2.0,
                voice_peak_limit_dbfs=-3.3, timing_out=root / 'voice-timing.json', stems_dir=root)


def encode(root: Path, *, scale: float = 1.5, crf: int = 18) -> None:
    ffmpeg = find_ffmpeg()
    node = shutil.which('node')
    if not ffmpeg or not node:
        raise RuntimeError('Node.js and FFmpeg are required for rendering.')
    width, height = round(1280 * scale), round(720 * scale)
    if width % 2 or height % 2:
        raise ValueError('Render dimensions must both be even.')
    target = root / 'video.mp4'
    temporary = root / 'video.rendering.mp4'
    node_cmd = [node, str(BASE / 'films' / 'script_motion.mjs'), '--plan', str(root / 'render-plan.json'),
                '--scale', str(scale), '--pipe']
    encoder_cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
                   '-pix_fmt', 'rgba', '-s', f'{width}x{height}', '-r', str(FPS), '-i', 'pipe:0',
                   '-i', str(root / 'master.wav'), '-map', '0:v:0', '-map', '1:a:0',
                   '-c:v', 'libx264', '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p',
                   '-fps_mode', 'passthrough', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                   str(temporary)]
    # Stderr goes to temporary files: neither process can block on a full log
    # pipe while FFmpeg consumes frames. Never use -shortest (it lost a frame).
    with (root / 'render-node.log').open('wb') as nlog, (root / 'render-ffmpeg.log').open('wb') as flog:
        producer = subprocess.Popen(node_cmd, stdout=subprocess.PIPE, stderr=nlog, cwd=ROOT)
        try:
            encoder = subprocess.Popen(encoder_cmd, stdin=producer.stdout, stdout=subprocess.DEVNULL,
                                       stderr=flog, cwd=ROOT)
            producer.stdout.close()
            ecode = encoder.wait(timeout=7200)
            pcode = producer.wait(timeout=120)
        except BaseException:
            producer.kill()
            if 'encoder' in locals():
                encoder.kill()
                encoder.wait()
            producer.wait()
            raise
    if pcode or ecode or not temporary.is_file() or temporary.stat().st_size < 1024:
        raise RuntimeError(f'Render failed (graphics {pcode}, FFmpeg {ecode}); inspect render logs.')
    temporary.replace(target)


def encoded_cadence(video: Path, expected_frames: int) -> dict:
    """Inspect every encoded frame timestamp; a nominal fps field is not enough."""
    from video_studio.quality_audit import file_sha256
    ffprobe = find_ffprobe()
    if not ffprobe:
        raise RuntimeError('ffprobe is required for frame cadence verification.')
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                             'frame=best_effort_timestamp_time', '-of', 'csv=p=0', str(video)],
                            capture_output=True, text=True, check=True, timeout=1800)
    timestamps = []
    for line in result.stdout.splitlines():
        field = line.strip().split(',')[0]
        if not field:
            continue
        try:
            value = float(field)
        except ValueError as exc:
            raise ValueError('Could not parse every encoded video frame timestamp.') from exc
        if not math.isfinite(value):
            raise ValueError('Encoded video has a non-finite frame timestamp.')
        timestamps.append(value)
    max_error = max((abs(t - i / FPS) for i, t in enumerate(timestamps)), default=math.inf)
    passed = len(timestamps) == expected_frames and max_error < .001
    return {'video_sha256': file_sha256(video), 'fps': FPS, 'expected_frames': expected_frames,
            'decoded_frames': len(timestamps), 'max_timestamp_error_seconds': max_error if math.isfinite(max_error) else None,
            'passed': passed, 'scope': 'Encoded frame timestamps only; not perceptual smoothness.'}


def _srt_time(value: float) -> str:
    ms = max(0, round(value * 1000)); h, ms = divmod(ms, 3_600_000); m, ms = divmod(ms, 60_000); s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def write_captions(path: Path, timing: list[dict]) -> None:
    blocks = []
    for i, line in enumerate(timing, 1):
        content = '\n'.join(textwrap.wrap(line['text'], width=42, break_long_words=False,
                                         break_on_hyphens=False, replace_whitespace=True))
        blocks.append(f"{i}\n{_srt_time(line['start'])} --> {_srt_time(line['end'])}\n{content}")
    path.write_text('\n\n'.join(blocks) + '\n', encoding='utf-8')


def run(args) -> int:
    from video_studio import quality_audit
    root = workspace_output(args.out)
    if (root / 'video.mp4').exists() or (root / 'release-approval.json').exists():
        raise ValueError('This package already contains a video or approval; choose a new output directory '
                         'so a failed rerender cannot leave a stale deliverable.')
    script = read_exact_script(Path(args.script).expanduser().resolve())
    config = load_config()
    from video_studio.captions import normalize_narration_language, validate_narration_text
    settings = config.get('video_studio', {})
    if not isinstance(settings, dict):
        raise ValueError('config.json video_studio settings must be an object.')
    language = normalize_narration_language(args.language or settings.get('narration_language', 'ur-en'))
    validate_narration_text(script, language, 'Supplied narration')
    plan = authored_or_model_plan(script, Path(args.plan).expanduser().resolve() if args.plan else None, config)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'script.txt').write_bytes(script.encode('utf-8'))
    # release_gate's existing package interface expects script.md; preserve it
    # exactly, with no heading, summary, extra narration or rewritten words.
    (root / 'script.md').write_bytes(script.encode('utf-8'))
    write_json(root / 'script-plan.json', plan)
    write_json(root / 'release-profile.json', {'profile': PROFILE})
    status = {'profile': PROFILE, 'status': 'draft', 'publishable': False,
              'narration_language': language,
              'human_review_required': True, 'script_preserved': True,
              'topic_research_performed': False, 'semantic_status': 'unverified',
              'timing_status': 'not_rendered', 'quality_status': 'not_run'}
    write_json(root / 'package-status.json', status)
    print(f"Plan: {len(plan['beats'])} source-linked beats -> {root / 'script-plan.json'}")
    if not args.render:
        print('No video rendered. Visual meaning and pacing remain unverified.')
        return 0
    voices = root / 'voice'
    synthesize(plan, voices, language=language, voice=args.voice,
               external_dir=Path(args.voice_dir).expanduser().resolve() if args.voice_dir else None, config=config)
    render_plan, shots, timing, storyboard = measured_clock(plan, voices)
    write_json(root / 'render-plan.json', render_plan)
    write_json(root / 'shots.json', shots)
    write_json(root / 'voice-timing.json', timing)
    write_json(root / 'storyboard.json', storyboard)
    make_audio(plan, root, shots, timing)
    if args.captions:
        write_captions(root / 'video.srt', timing)
    encode(root, scale=args.scale, crf=args.crf)
    cadence = encoded_cadence(root / 'video.mp4', render_plan['frames'])
    write_json(root / 'frame-timing.json', cadence)
    report = quality_audit.audit(root / 'video.mp4', strict=True, fail_on_still=True)
    write_json(root / 'video.qc.json', report)
    status.update({'timing_status': 'clip_boundaries_measured; word_alignment_unverified',
                   'frame_cadence_passed': cadence['passed'], 'quality_status': 'passed' if report['passed'] else 'failed',
                   'captions': 'sidecar_unverified' if args.captions else 'none',
                   'rendered_frames': render_plan['frames'], 'duration_seconds': render_plan['frames'] / FPS})
    write_json(root / 'package-status.json', status)
    print(f"Rendered DRAFT: {root / 'video.mp4'}")
    print('No semantic, speech, mix, caption, factual or perceptual approval was inferred from the technical checks.')
    if not cadence['passed'] or not report['passed']:
        print('Technical checks failed; inspect frame-timing.json and video.qc.json.', file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', required=True, help='UTF-8 plain text: the exact words to narrate')
    parser.add_argument('--out', required=True, help='package directory inside workspace/')
    parser.add_argument('--plan', help='authored visuals JSON or previously generated script-plan.json')
    parser.add_argument('--render', action='store_true', help='synthesize, render, meter and create a draft')
    parser.add_argument('--language', choices=('en', 'ur-en'), default=None,
                        help='defaults to config, or ur-en; English must be selected explicitly')
    parser.add_argument('--voice', default='bm_george', help='local Kokoro English voice')
    parser.add_argument('--voice-dir', help='alternative pre-recorded WAVs named b0001.wav, b0002.wav, ...')
    parser.add_argument('--captions', action='store_true', help='include draft, line-timed SRT; human review required')
    parser.add_argument('--scale', type=float, default=1.5, help='1.5 = 1920x1080; lower values are review previews')
    parser.add_argument('--crf', type=int, default=18, help='H.264 quality (lower is higher; 0–30)')
    args = parser.parse_args(argv)
    if not .25 <= args.scale <= 1.5 or not 0 <= args.crf <= 30:
        parser.error('--scale must be .25–1.5 and --crf must be 0–30')
    try:
        return run(args)
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f'SCRIPT PRODUCTION FAILED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
