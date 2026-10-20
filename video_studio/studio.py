#!/usr/bin/env python3
"""Render a storyboard to H.264 MP4, with optional scene-aligned local Piper narration."""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from captions import build_subtitles, validate_english_text, validate_english_voice_model, validate_subtitle_text
from capabilities import profile_device


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


def prepare_voice(data, piper, model, ffmpeg, ffprobe, fps):
    validate_english_voice_model(model)
    voice_dir = BASE / "voice_segments"
    shutil.rmtree(voice_dir, ignore_errors=True)
    voice_dir.mkdir(parents=True)
    segments = []
    for index, scene in enumerate(data["scenes"]):
        narration = validate_english_text(scene.get("narration", ""), "Scene " + str(index + 1) + " narration")
        scene["caption"] = narration
        raw = voice_dir / ("raw-%03d.wav" % index)
        if narration:
            run([piper, "--model", model, "--output_file", str(raw)],
                input=(narration + "\n").encode("utf-8"), timeout=300)
            spoken_duration = probe_duration(ffprobe, raw)
            scene["narration_duration_seconds"] = spoken_duration
        else:
            original = float(scene["duration_seconds"])
            run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", str(original), "-c:a", "pcm_s16le", str(raw)])
            spoken_duration = 0.0
            scene["narration_duration_seconds"] = float(scene["duration_seconds"])
        target_seconds = max(float(scene["duration_seconds"]), spoken_duration + 0.45)
        target_frames = max(1, math.ceil(target_seconds * fps))
        aligned_seconds = target_frames / fps
        scene["duration_seconds"] = aligned_seconds
        normalized = voice_dir / ("segment-%03d.wav" % index)
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", default="storyboard.example.json")
    parser.add_argument("--output", default="outputs/offline-agent-hq-demo.mp4")
    parser.add_argument("--with-voice", action="store_true", help="Use local Piper CLI and PIPER_MODEL path")
    parser.add_argument("--keep-frames", action="store_true", help="Keep PNG frames after a successful MP4 render")
    parser.add_argument("--print-capabilities", action="store_true", help="Print detected device profile and exit")
    args = parser.parse_args()
    profile = profile_device(BASE)
    if args.print_capabilities:
        print(json.dumps(profile, indent=2))
        return
    print("Device profile:", json.dumps({key: profile[key] for key in ("tier", "ram_gib", "render_threads", "max_parallel_heavy_jobs", "reason")}, ensure_ascii=False))
    print("Quality policy: requested dimensions and frame rate are preserved; the renderer will not silently downgrade output quality.")
    node, ffmpeg, ffprobe = shutil.which("node"), shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not node:
        raise SystemExit("Node.js was not found. Install Node.js LTS first.")
    if not ffmpeg or not ffprobe:
        raise SystemExit("FFmpeg and ffprobe are required and must be available on PATH.")
    piper, model = shutil.which("piper"), os.environ.get("PIPER_MODEL", "").strip()
    if args.with_voice and (not piper or not model or not Path(model).is_file()):
        raise SystemExit("Voice requested, but Piper or a valid PIPER_MODEL file is missing.")

    storyboard = Path(args.storyboard).expanduser().resolve()
    if not storyboard.is_file():
        storyboard = (BASE / args.storyboard).resolve()
    if not storyboard.is_file():
        raise SystemExit("Storyboard not found: " + str(storyboard))
    data = json.loads(storyboard.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list) or not data["scenes"]:
        raise SystemExit("Storyboard must contain at least one scene.")
    for index, scene in enumerate(data["scenes"], 1):
        scene["narration"] = validate_english_text(scene.get("narration", ""), "Scene " + str(index) + " narration")
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
        generated_storyboard, voice_dir, segments = prepare_voice(data, piper, model, ffmpeg, ffprobe, fps)
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
    srt_text, vtt_text = build_subtitles(data)
    subtitle_report = validate_subtitle_text(srt_text, vtt_text)
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
    if not args.keep_frames:
        shutil.rmtree(BASE / "frames", ignore_errors=True)
    if voice_dir:
        shutil.rmtree(voice_dir, ignore_errors=True)
    if generated_storyboard:
        generated_storyboard.unlink(missing_ok=True)
    print("SUCCESS:", output)
    print("English subtitles (SRT):", srt_path)
    print("English subtitles (WebVTT):", vtt_path)
    print("Duration:", manifest["duration_seconds"], "seconds")
    print("Frames:", manifest["frame_count"])
    print("Local MP4 only: this pipeline does not upload or publish content.")


if __name__ == "__main__":
    main()
