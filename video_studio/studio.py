#!/usr/bin/env python3
"""Render a storyboard to H.264 MP4, with optional scene-aligned local Piper narration."""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))
from captions import build_subtitles, normalize_narration_language, validate_narration_text, validate_english_voice_model, validate_subtitle_text
from capabilities import profile_device
from voice_backends import get_urdu_tts_command, load_project_config, resolve_urdu_tts_command, require_urdu_voice_human_approval
from render_lock import render_lock
from release_evidence import REQUIRED_CREATIVE_CHECKS


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, cwd=BASE, timeout=1800, **kwargs):
    print("+", " ".join(str(item) for item in command), flush=True)
    return subprocess.run(command, cwd=str(cwd), check=True, timeout=timeout, **kwargs)


def probe_duration(ffprobe, path):
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=60)
    duration = float(json.loads(result.stdout).get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Could not determine audio duration for " + str(path))
    return duration

def paced_scene_duration(planned_seconds, narration_seconds, fps, minimum_gap=0.06, maximum_gap=0.22):
    """Keep the visual hold close to spoken audio; never pad a short line to a stale scene target."""
    try:
        planned = float(planned_seconds)
        narration = float(narration_seconds)
        rate = int(fps)
        min_gap = float(minimum_gap)
        max_gap = float(maximum_gap)
    except (TypeError, ValueError) as exc:
        raise ValueError("Scene pacing requires numeric durations and a valid frame rate.") from exc
    if (not all(math.isfinite(value) for value in (planned, narration, min_gap, max_gap))
            or planned <= 0 or narration <= 0 or rate < 1 or rate > 60
            or min_gap < 0 or max_gap < min_gap):
        raise ValueError("Scene pacing requires finite positive durations, fps 1–60, and ordered non-negative gap limits.")
    # Work in whole frames without rounding the requested maximum tail upward.
    # Rounding duration up can add an extra frame (33 ms at 30 fps), which violates
    # the declared cap. First calculate the frame ceiling that will not clip speech,
    # then select a scene length inside the exact maximum-padded frame budget.
    audio_frames = math.ceil(narration * rate - 1e-9)
    minimum_frames = math.ceil((narration + min_gap) * rate - 1e-9)
    maximum_frames = math.floor((narration + max_gap) * rate + 1e-9)
    if maximum_frames < audio_frames:
        raise ValueError(
            "Frame rate cannot fit the narration inside the maximum scene-tail padding."
        )
    planned_frames = math.floor(planned * rate + 1e-9)
    target_frames = min(
        maximum_frames,
        max(audio_frames, minimum_frames, min(planned_frames, maximum_frames)),
    )
    return target_frames / rate


def build_audio_gated_visemes(text, audio_path, scene_duration_seconds, window_seconds=0.08):
    """Create approximate mouth-shape cues from real audio energy and grapheme classes.

    This is an offline fallback when a forced phoneme/viseme aligner is not configured.
    It is intentionally labelled as an approximation: energy does not reveal phonemes,
    and grapheme-to-mouth-shape mapping cannot guarantee phoneme-accurate lip-sync.
    """
    try:
        scene_duration = float(scene_duration_seconds)
        window_seconds = float(window_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("Viseme timing requires numeric scene and window durations.") from exc
    if not math.isfinite(scene_duration) or scene_duration <= 0:
        raise ValueError("Viseme timing requires a finite positive scene duration.")
    if not math.isfinite(window_seconds) or not 0.02 <= window_seconds <= 0.25:
        raise ValueError("Viseme analysis window must be between 0.02 and 0.25 seconds.")

    try:
        with wave.open(str(audio_path), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frame_count = stream.getnframes()
            if channels not in (1, 2) or sample_width != 2 or sample_rate < 8000 or sample_rate > 192000:
                raise ValueError("Viseme analysis expects mono/stereo PCM16 WAV at 8–192 kHz.")
            raw = stream.readframes(frame_count)
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError("Could not read narration WAV for approximate viseme timing: " + str(exc)) from exc

    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    actual_frames = len(samples) // channels
    if actual_frames <= 0:
        raise ValueError("Narration WAV contains no audio frames.")
    if len(samples) % channels:
        raise ValueError("Narration WAV has an incomplete interleaved audio frame.")

    audio_seconds = actual_frames / sample_rate
    analysis_seconds = min(scene_duration, audio_seconds)
    window_frames = max(1, int(round(sample_rate * window_seconds)))
    levels = []
    starts = []
    cursor = 0
    while cursor < int(math.ceil(analysis_seconds * sample_rate)):
        end = min(actual_frames, cursor + window_frames)
        if end <= cursor:
            break
        sample_start, sample_end = cursor * channels, end * channels
        segment = samples[sample_start:sample_end]
        if segment:
            mean_square = sum(int(value) * int(value) for value in segment) / len(segment)
            rms = math.sqrt(mean_square)
        else:
            rms = 0.0
        levels.append(rms)
        starts.append(cursor / sample_rate)
        cursor = end
    peak_rms = max(levels, default=0.0)
    # PCM16 units avoid classifying codec quantization noise as speech.
    threshold = max(35.0, peak_rms * 0.14)

    # This mapping is a visual heuristic, not a claim of phonetic alignment.
    # It covers frequent English and Urdu letter classes; unknown letters use open.
    closed_letters = set("mbpمبپ")
    round_letters = set("ouwqوؤ")
    wide_letters = set("eiyےیئ")
    open_letters = set("aآااہ")
    def shape_for_grapheme(char):
        token = char.lower()
        if token in closed_letters:
            return "closed"
        if token in round_letters:
            return "round"
        if token in wide_letters:
            return "wide"
        if token in open_letters:
            return "open"
        return "open"

    graphemes = [char for char in str(text or "") if char.isalpha()]
    mapped = [shape_for_grapheme(char) for char in graphemes] or ["open"]
    cues = []
    char_index = 0
    last_shape = None

    def add_cue(time_seconds, shape):
        ratio = max(0.0, min(1.0, float(time_seconds) / scene_duration))
        timestamp = round(ratio, 8)
        if cues and timestamp < cues[-1]["t"]:
            timestamp = cues[-1]["t"]
        if cues and timestamp == cues[-1]["t"]:
            cues[-1]["shape"] = shape
        elif not cues or cues[-1]["shape"] != shape:
            cues.append({"t": timestamp, "shape": shape})

    for start, rms in zip(starts, levels):
        if rms > threshold:
            shape = mapped[char_index % len(mapped)]
            char_index += 1
        else:
            shape = "closed"
        if shape != last_shape:
            add_cue(start, shape)
            last_shape = shape

    # Explicitly close the mouth when the unpadded narration ends and at scene end.
    add_cue(min(scene_duration, audio_seconds), "closed")
    add_cue(scene_duration, "closed")
    if not cues:
        return [{"t": 0.0, "shape": "closed"}, {"t": 1.0, "shape": "closed"}]
    if cues[0]["t"] > 0.0:
        cues.insert(0, {"t": 0.0, "shape": "closed"})
    if cues[-1]["t"] < 1.0:
        cues.append({"t": 1.0, "shape": "closed"})
    # Normalize same-timestamp updates and ensure a stable sorted track.
    normalized = []
    for cue in sorted(cues, key=lambda item: item["t"]):
        if normalized and cue["t"] == normalized[-1]["t"]:
            normalized[-1] = cue
        elif not normalized or normalized[-1]["shape"] != cue["shape"]:
            normalized.append(cue)
    if not normalized:
        normalized = [{"t": 0.0, "shape": "closed"}]
    if normalized[0]["t"] > 0:
        normalized.insert(0, {"t": 0.0, "shape": "closed"})
    if normalized[-1]["t"] < 1.0:
        normalized.append({"t": 1.0, "shape": "closed"})
    elif normalized[-1]["t"] == 1.0:
        normalized[-1]["shape"] = "closed"
    return normalized


def prepare_voice(data, piper, model, ffmpeg, ffprobe, fps, language="en", config=None):
    profile = normalize_narration_language(language)
    config = config or {}
    command_template = get_urdu_tts_command(config) if profile == "ur-en" else None
    if profile == "en":
        validate_english_voice_model(model)
    elif not command_template:
        raise ValueError("Urdu-English narration requires a valid local voice adapter.")
    voice_dir = BASE / "voice_segments"
    shutil.rmtree(voice_dir, ignore_errors=True)
    voice_dir.mkdir(parents=True)
    segments = []
    voice_items = []
    for index, scene in enumerate(data["scenes"]):
        narration = validate_narration_text(scene.get("narration", ""), profile, "Scene " + str(index + 1) + " narration")
        scene["narration_language"] = profile
        scene["caption"] = narration
        raw = voice_dir / ("raw-%03d.wav" % index)
        if profile == "en":
            run([piper, "--model", model, "--output_file", str(raw)],
                input=(narration + "\n").encode("utf-8"), timeout=300)
        else:
            text_file = voice_dir / ("narration-%03d.txt" % index)
            text_file.write_text(narration + "\n", encoding="utf-8")
            voice_items.append({"text_file": text_file, "output_file": raw, "scene_index": index + 1})

    if profile == "ur-en":
        manifest = voice_dir / "urdu-tts-manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "items": [{"text_file": str(item["text_file"].resolve()),
                       "output_file": str(item["output_file"].resolve())}
                      for item in voice_items],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # The bundled Piper adapter accepts a manifest, loads the small CPU ONNX voice
        # once per video, and synthesizes scenes sequentially. Custom per-scene adapters
        # remain supported. The legacy Kani/NeMo adapter is an explicit advanced option.
        if any("{manifest_file}" in part for part in command_template):
            command = resolve_urdu_tts_command(command_template, manifest_file=manifest)
            timeout = max(900, min(7200, len(voice_items) * 120))
            print("+", " ".join(command), flush=True)
            adapter_env = os.environ.copy()
            if any(Path(part).name == "urdu_tts_adapter.py" for part in command_template):
                prefix = configured_kani_speaker_prefix(config)
                if prefix is not None:
                    adapter_env["AGENTHQ_KANI_SPEAKER_PREFIX"] = prefix
            result = subprocess.run(
                command, cwd=str(ROOT), capture_output=True, text=True,
                timeout=timeout, check=False, env=adapter_env,
            )
            if result.stdout:
                print(result.stdout.rstrip(), flush=True)
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr, flush=True)
            if result.returncode != 0:
                raise RuntimeError("Batched Urdu TTS adapter failed with exit code " + str(result.returncode) + ".")
        else:
            for item in voice_items:
                command = resolve_urdu_tts_command(
                    command_template, text_file=item["text_file"], output_file=item["output_file"]
                )
                print("+", " ".join(command), flush=True)
                result = subprocess.run(
                    command, cwd=str(ROOT), capture_output=True, text=True,
                    timeout=600, check=False,
                )
                if result.stdout:
                    print(result.stdout.rstrip(), flush=True)
                if result.stderr:
                    print(result.stderr.rstrip(), file=sys.stderr, flush=True)
                if result.returncode != 0:
                    raise RuntimeError("Urdu TTS adapter failed for scene " + str(item["scene_index"])
                                       + " with exit code " + str(result.returncode) + ".")
        missing = [str(item["scene_index"]) for item in voice_items
                   if not item["output_file"].is_file() or item["output_file"].stat().st_size == 0]
        if missing:
            raise RuntimeError("Urdu TTS adapter did not create non-empty WAV output for scene(s): "
                               + ", ".join(missing) + ". Refusing an incomplete or silent render.")

    for index, scene in enumerate(data["scenes"]):
        raw = voice_dir / ("raw-%03d.wav" % index)
        if not raw.is_file() or raw.stat().st_size == 0:
            raise RuntimeError("Voice backend did not create a non-empty WAV for scene " + str(index + 1) + ".")
        # Trim only leading/trailing quiet tails; preserve natural pauses inside the sentence.
        # Reversing the clip lets the start-trim filter safely target its trailing edge.
        trimmed = voice_dir / ("trimmed-%03d.wav" % index)
        trim_filter = (
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:start_silence=0.03,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:start_silence=0.05,"
            "areverse"
        )
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
             "-af", trim_filter, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(trimmed)])
        if not trimmed.is_file() or trimmed.stat().st_size < 1024:
            raise RuntimeError("Voice backend produced no usable speech after silence trimming for scene " + str(index + 1) + ".")
        spoken_duration = probe_duration(ffprobe, trimmed)
        if spoken_duration < 0.20:
            raise RuntimeError("Narration for scene " + str(index + 1) + " is too short to pace as a real scene.")
        scene["narration_duration_seconds"] = round(spoken_duration, 6)
        target_frames = max(1, int(round(paced_scene_duration(
            scene["duration_seconds"], spoken_duration, fps
        ) * fps)))
        aligned_seconds = target_frames / fps
        scene["duration_seconds"] = aligned_seconds
        scene["narration_padding_seconds"] = round(max(0.0, aligned_seconds - spoken_duration), 6)
        scene["voice_coverage_ratio"] = round(min(1.0, spoken_duration / aligned_seconds), 4)
        character = scene.get("character")
        if isinstance(character, dict) and character.get("enabled") is True:
            if not character.get("visemes"):
                character["visemes"] = build_audio_gated_visemes(
                    scene.get("narration", ""), trimmed, aligned_seconds
                )
                character["viseme_alignment"] = (
                    "audio-energy-gated grapheme approximation; not forced phoneme alignment"
                )
                character["speaking"] = True
            else:
                # Never trust model/user-provided metadata to claim audio alignment.
                # Existing cues are retained for visuals but are explicitly unverified.
                character["viseme_alignment"] = (
                    "preauthored/model-supplied cues not validated against final audio; not forced phoneme alignment"
                )
            scene["viseme_alignment"] = character["viseme_alignment"]
        normalized = voice_dir / ("segment-%03d.wav" % index)
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(trimmed),
             "-af", "apad,atrim=duration=" + ("%.6f" % aligned_seconds),
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(normalized)])
        segments.append(normalized)
    storyboard = BASE / "voice-storyboard.generated.json"
    storyboard.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return storyboard, voice_dir, segments



def combine_voice(segments, ffmpeg, output):
    if not segments:
        raise ValueError("No audio segments were generated.")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning"]
    labels = []
    for index, path in enumerate(segments):
        command.extend(["-i", str(path)])
        labels.append("[" + str(index) + ":a]")
    filter_graph = "".join(labels) + "concat=n=" + str(len(segments)) + ":v=0:a=1[outa]"
    command.extend(["-filter_complex", filter_graph, "-map", "[outa]",
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output)])
    run(command, timeout=900)


def configured_kani_speaker_prefix(config):
    """Return the explicit local Kani speaker prefix, or None when unspecified."""
    video_config = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(video_config, dict):
        raise ValueError("config.json video_studio settings must be an object.")
    if "kani_speaker_prefix" not in video_config:
        return None
    prefix = video_config.get("kani_speaker_prefix")
    if not isinstance(prefix, str):
        raise ValueError("config.json video_studio.kani_speaker_prefix must be text.")
    return prefix.strip()


def resolve_narration_language(explicit_language, storyboard, config):
    """Resolve explicit CLI override, then storyboard profile, then configured channel default."""
    video_config = config.get("video_studio", {}) if isinstance(config, dict) else {}
    if not isinstance(video_config, dict):
        video_config = {}
    storyboard_language = storyboard.get("narration_language") if isinstance(storyboard, dict) else None
    configured_language = video_config.get("narration_language", "ur-en")
    return normalize_narration_language(explicit_language or storyboard_language or configured_language)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", default="storyboard.example.json")
    parser.add_argument("--output", default="outputs/offline-agent-hq-demo.mp4")
    parser.add_argument("--with-voice", action="store_true", help="Synthesize the storyboard's declared language using the configured local backend")
    parser.add_argument("--language", choices=["en", "ur-en"], help="Override narration language; defaults to storyboard then config.json video_studio.narration_language (ur-en when unset)")
    parser.add_argument("--keep-frames", action="store_true", help="Keep PNG frames after a successful MP4 render")
    parser.add_argument("--print-capabilities", action="store_true", help="Print detected device profile and exit")
    args = parser.parse_args()
    profile = profile_device(BASE)
    try:
        config = load_project_config(ROOT)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.print_capabilities:
        print(json.dumps(profile, indent=2))
        return
    with render_lock(BASE / ".render.lock"):
        print("Device profile:", json.dumps({key: profile[key] for key in ("tier", "ram_gib", "render_threads", "max_parallel_heavy_jobs", "reason")}, ensure_ascii=False))
        print("Quality policy: requested dimensions and frame rate are preserved; the renderer will not silently downgrade output quality.")
        node, ffmpeg, ffprobe = shutil.which("node"), shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not node:
            raise SystemExit("Node.js was not found. Install Node.js LTS first.")
        if not ffmpeg or not ffprobe:
            raise SystemExit("FFmpeg and ffprobe are required and must be available on PATH.")
        piper, model = shutil.which("piper"), os.environ.get("PIPER_MODEL", "").strip()

        storyboard = Path(args.storyboard).expanduser().resolve()
        if not storyboard.is_file():
            storyboard = (BASE / args.storyboard).resolve()
        if not storyboard.is_file():
            raise SystemExit("Storyboard not found: " + str(storyboard))
        data = json.loads(storyboard.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("scenes"), list) or not data["scenes"]:
            raise SystemExit("Storyboard must contain at least one scene.")
        try:
            language = resolve_narration_language(args.language, data, config)
            urdu_tts_command = get_urdu_tts_command(config)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if language == "ur-en" and not args.with_voice:
            raise SystemExit("Urdu-English video output cannot be rendered silently; configure a suitable local Urdu TTS adapter and pass --with-voice.")
        if args.with_voice and language == "en" and (not piper or not model or not Path(model).is_file()):
            raise SystemExit("English voice requested, but Piper or a valid PIPER_MODEL file is missing.")
        if args.with_voice and language == "ur-en" and not urdu_tts_command:
            raise SystemExit("No Urdu-English voice adapter command was resolved. The default empty setting should select Piper; install it with powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup_urdu_tts_windows.ps1 and inspect config.json if a custom adapter was intended.")
        if args.with_voice and language == "ur-en":
            try:
                require_urdu_voice_human_approval(config)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
        data["narration_language"] = language
        for index, scene in enumerate(data["scenes"], 1):
            scene["narration_language"] = language
            scene["narration"] = validate_narration_text(scene.get("narration", ""), language, "Scene " + str(index) + " narration")
            scene["caption"] = scene["narration"]
        fps = int(data.get("fps", 30))
        if not 1 <= fps <= 60:
            raise SystemExit("Storyboard fps must be from 1 to 60.")
        if not isinstance(data.get("scenes"), list) or not data["scenes"]:
            raise SystemExit("Storyboard must contain at least one scene.")

        voice_dir, segments, generated_storyboard = None, [], None
        render_storyboard = storyboard
        if args.with_voice:
            if not any(str(scene.get("narration", "")).strip() for scene in data["scenes"]):
                raise SystemExit("No narration text exists in the storyboard.")
            generated_storyboard, voice_dir, segments = prepare_voice(data, piper, model, ffmpeg, ffprobe, fps, language, config)
            render_storyboard = generated_storyboard

        run([node, "render.js", str(render_storyboard)], timeout=3600)
        manifest_path = BASE / "render-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame_check = subprocess.run(
            [sys.executable, str(BASE / "validate_frames.py"), "--frames", str(BASE / "frames"),
             "--manifest", str(manifest_path)],
            cwd=str(BASE), check=True, capture_output=True, text=True, timeout=300)
        print(frame_check.stdout.strip())

        output_arg = Path(args.output).expanduser()
        output = output_arg.resolve() if output_arg.is_absolute() else (BASE / output_arg).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        profile_path = output.with_suffix(".capabilities.json")
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        silent = output.with_name(output.stem + ".silent.mp4")
        srt_path, vtt_path = output.with_suffix(".srt"), output.with_suffix(".vtt")
        srt_text, vtt_text = build_subtitles(data, language=language)
        subtitle_report = validate_subtitle_text(srt_text, vtt_text, language=language)
        srt_path.write_text(srt_text, encoding="utf-8")
        vtt_path.write_text(vtt_text, encoding="utf-8")
        print("Subtitle validation:", json.dumps(subtitle_report))
        frames = BASE / "frames" / "frame-%06d.png"
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-framerate", str(fps),
             "-i", str(frames), "-frames:v", str(manifest["frame_count"]),
             "-c:v", "libx264", "-threads", str(profile["render_threads"]), "-pix_fmt", "yuv420p", "-crf", "20",
             "-movflags", "+faststart", str(silent)])
        if args.with_voice:
            combined = voice_dir / "combined.wav"
            combine_voice(segments, ffmpeg, combined)
            run([ffmpeg, "-y", "-hide_banner", "-loglevel", "warning", "-i", str(silent),
                 "-i", str(combined), "-map", "0:v:0", "-map", "1:a:0",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                 "-movflags", "+faststart", str(output)])
            silent.unlink(missing_ok=True)
        else:
            silent.replace(output)
            print("No voice synthesized. Add --with-voice after installing Piper and setting PIPER_MODEL.")

        validation_args = [sys.executable, str(BASE / "validate_render.py"), str(output),
                           "--width", str(int(manifest["width"])), "--height", str(int(manifest["height"])),
                           "--fps", str(fps)]
        if args.with_voice:
            validation_args.append("--require-audio")
        validation = subprocess.run(validation_args, cwd=str(BASE), check=True,
                                    capture_output=True, text=True, timeout=120)
        print(validation.stdout.strip())
        if generated_storyboard:
            aligned_copy = output.with_suffix(".storyboard.json")
            shutil.copy2(generated_storyboard, aligned_copy)
            print("Aligned storyboard:", aligned_copy)
        packaged_manifest = dict(manifest)
        packaged_manifest["video_file"] = output.name
        packaged_manifest["video_sha256"] = file_sha256(output)
        manifest_output = output.with_name("render-manifest.json")
        manifest_output.write_text(json.dumps(packaged_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        impact_dir = output.with_name("impact-frame-evidence")
        impact_dir.mkdir(parents=True, exist_ok=True)
        impact_evidence = {"schema_version": 1, "video_file": output.name,
            "video_sha256": packaged_manifest["video_sha256"],
            "render_manifest_sha256": file_sha256(manifest_output), "events": []}
        for event_index, event in enumerate(packaged_manifest.get("impact_events", []), 1):
            timestamp = float(event["timestamp_seconds"])
            frame_path = impact_dir / ("event-%03d-%s.png" % (event_index, event["type"]))
            run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", ("%.6f" % timestamp),
                 "-i", str(output), "-frames:v", "1", "-update", "1", str(frame_path)], timeout=120)
            if not frame_path.is_file() or frame_path.stat().st_size < 64 or frame_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("Could not extract a valid PNG from the final MP4 at impact event " + str(event["id"]))
            impact_evidence["events"].append({"id": event["id"], "type": event["type"], "frame": event["frame"],
                "timestamp_seconds": timestamp, "file": frame_path.relative_to(output.parent).as_posix(),
                "sha256": file_sha256(frame_path), "size_bytes": frame_path.stat().st_size})
        impact_evidence_path = output.with_name("impact-frame-evidence.json")
        impact_evidence_path.write_text(json.dumps(impact_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        style_time = min(1.5, max(0.0, float(manifest["duration_seconds"]) - 1.0 / float(manifest["fps"])))
        style_frame = output.with_name("style-frame.png")
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", ("%.6f" % style_time),
             "-i", str(output), "-frames:v", "1", "-update", "1", str(style_frame)], timeout=120)
        if not style_frame.is_file() or style_frame.stat().st_size < 64 or style_frame.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Could not extract a valid style-frame PNG from the final MP4.")
        review_template = {"schema_version": 1, "reviewer": "", "reviewed_at": "",
            "video_sha256": packaged_manifest["video_sha256"], "render_manifest_sha256": file_sha256(manifest_output),
            "qc_report_sha256": None, "reviewed_segments": [],
            "checks": {check: {"status": "pending", "evidence": []} for check in REQUIRED_CREATIVE_CHECKS},
            "instructions": "Only copy to creative-review.json after a real review. Complete each check with observed evidence and timestamped notes for every impact event. Never mark unchecked items as pass."}
        review_template_path = output.with_name("creative-review.template.json")
        if not review_template_path.exists():
            review_template_path.write_text(json.dumps(review_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        provenance_template = {"schema_version": 1, "approved": False, "reviewer": "", "reviewed_at": "",
            "asset_strategy": "procedural_original", "assets": [],
            "instructions": "Confirm original procedural graphics, or switch to listed_assets and enumerate each imported asset with SHA-256, source, license and rights basis."}
        provenance_path = output.with_name("asset-provenance.template.json")
        if not provenance_path.exists():
            provenance_path.write_text(json.dumps(provenance_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        style_template = {"schema_version": 1, "approved": False, "reviewer": "", "reviewed_at": "",
            "style_frame_file": style_frame.name, "style_frame_sha256": file_sha256(style_frame),
            "instructions": "Review style-frame.png and set approved=true only after explicitly accepting the visual direction."}
        style_template_path = output.with_name("style-frame-approval.template.json")
        if not style_template_path.exists():
            style_template_path.write_text(json.dumps(style_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Render manifest:", manifest_output)
        print("Encoded-MP4 impact evidence:", impact_evidence_path)
        print("Style frame:", style_frame)
        print("Release evidence templates written as pending/unapproved.")
        if not args.keep_frames:
            shutil.rmtree(BASE / "frames", ignore_errors=True)
        if voice_dir:
            shutil.rmtree(voice_dir, ignore_errors=True)
        if generated_storyboard:
            generated_storyboard.unlink(missing_ok=True)
        print("SUCCESS:", output)
        print(language + " subtitles (SRT):", srt_path)
        print(language + " subtitles (WebVTT):", vtt_path)
        print("Duration:", manifest["duration_seconds"], "seconds")
        print("Frames:", manifest["frame_count"])
        print("Local MP4 only: this pipeline does not upload or publish content.")


if __name__ == "__main__":
    main()
