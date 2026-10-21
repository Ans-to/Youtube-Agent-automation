#!/usr/bin/env python3
"""Render the hand-authored film in ``video_studio/films/`` end to end.

The film is a real authored animation script (Canvas drawing code with an
explicit timeline), not a storyboard template. This driver only wraps it:

0. voice     - optional: narrate the film's script with a local neural voice and
                hand the picture the measured line timings and mouth envelope;
1. frames    - run the film script; it rasterises 3840x2160 frames itself
                and writes ``manifest.json`` / ``film.json`` / ``timeline.txt``;
2. soundtrack- synthesise the score the film declares in ``film.json``;
2b. mix      - when there is a voice, duck the score under it and sum the two;
3. validate  - contiguous numbering, exact dimensions, real image headers;
4. encode    - H.264 + AAC 4K master and a delivery copy with FFmpeg;
5. motion    - measure real frame-to-frame change on the encoded delivery copy
                and fail if the film drifts back into static slides;
6. audit     - run the studio's content/brand/legal/technical auditor.

Everything runs locally: no cloud renderer, no API key, no third-party assets.

    python tools/render_authored_film.py --out workspace/generated/motion-film

Exit codes: 0 rendered, 1 a step failed, 2 invalid input, 3 a dependency is
missing (node, the canvas module, or FFmpeg).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import render_motion_film as base  # noqa: E402 - path set up above

DEFAULT_SCRIPT = "video_studio/films/every_frame_is_code.mjs"


# The rejected first cut measured a mean delta of 0.819 with 51.4% near-static
# frames. These gates are deliberately stricter than that baseline.
MIN_MEAN_DELTA = 1.2
MAX_STATIC_SHARE = 0.15

# Defaults for the kinetic film. A film may declare `motion_gate` in its own
# film.json and override these; the summary always records which gate was used.
DEFAULT_GATE = {"min_mean": MIN_MEAN_DELTA, "max_static": MAX_STATIC_SHARE}
STATIC_BELOW = 0.5


def log(message: str) -> None:
    base.log(message)


def step_frames(
    script: Path, frames_dir: Path, width: int, height: int, fps: int, quality: int,
    voice_lines: Path | None = None,
) -> dict:
    command = [
        base.resolve_node(),
        str(script),
        "--out",
        str(frames_dir),
        "--width",
        str(width),
        "--height",
        str(height),
        "--fps",
        str(fps),
        "--quality",
        str(quality),
    ]
    if voice_lines is not None:
        command += ["--voice-lines", str(voice_lines)]
    result = base.run(command, timeout=7200)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-2000:]
        raise RuntimeError("the film script failed:\n" + tail)
    manifest_path = frames_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("the film script did not write manifest.json")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def step_soundtrack(film_json: Path, output: Path) -> dict:
    """Synthesise exactly the cues the film declares, so picture and sound agree."""
    import audio_design

    film = json.loads(film_json.read_text(encoding="utf-8"))
    cues = film.get("score") or []
    scenes = [round(shot["end"] - shot["start"], 3) for shot in film.get("shots", [])]
    output.parent.mkdir(parents=True, exist_ok=True)
    info = audio_design.render_sound_design(
        output, float(film["duration_seconds"]), scenes, sfx_cues=cues
    )
    info["path"] = str(output)
    return info


def step_voice(script: Path, out_dir: Path, *, voice: str, allow_download: bool,
               backend: str, fps: int) -> dict:
    """Narrate the script locally; writes voiceover.wav, lines.json, envelope.json."""
    import voiceover

    out_dir.mkdir(parents=True, exist_ok=True)
    return voiceover.build(
        script, out_dir, voice=voice, allow_download=allow_download,
        backend=backend, fps=fps,
    )


def step_mix(score: Path, voice_path: Path, output: Path, depth_db: float) -> dict:
    """Duck the score under the voice and print the exact gain it applied."""
    import voice_mix

    return voice_mix.mix(score, voice_path, output, depth_db=depth_db)


def step_validate(frames_dir: Path) -> dict:
    result = base.run(
        [
            sys.executable,
            str(ROOT / "video_studio" / "validate_frames.py"),
            "--frames",
            str(frames_dir),
            "--manifest",
            str(frames_dir / "manifest.json"),
        ],
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError("frame validation failed:\n" + (result.stdout or "")[-1200:] + (result.stderr or "")[-1200:])
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


def measure_motion(video: Path, ffmpeg: str, work_dir: Path, gate: dict | None = None) -> dict:
    """Frame-to-frame luma difference, the same measure the critique was based on."""
    stats_file = work_dir / ".motion-stats.txt"
    if stats_file.exists():
        stats_file.unlink()
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf",
        f"tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={stats_file}",
        "-f", "null", "-",
    ]
    result = base.run(command, timeout=3600)
    if result.returncode != 0 or not stats_file.is_file():
        raise RuntimeError("motion measurement failed: " + (result.stderr or "")[-800:])
    values = [float(m.group(1)) for m in re.finditer(r"YAVG=([0-9.]+)", stats_file.read_text())]
    if not values:
        raise RuntimeError("motion measurement produced no samples")
    ordered = sorted(values)
    metrics = {
        "frames_measured": len(values),
        "mean_delta": round(statistics.mean(values), 3),
        "median_delta": round(statistics.median(values), 3),
        "p90_delta": round(ordered[int(len(ordered) * 0.9)], 3),
        "static_share": round(sum(1 for v in values if v < STATIC_BELOW) / len(values), 4),
        "baseline_mean_delta": 0.819,
        "baseline_static_share": 0.514,
    }
    limits = gate or DEFAULT_GATE
    min_mean = float(limits.get("min_mean", DEFAULT_GATE["min_mean"]))
    max_static = float(limits.get("max_static", DEFAULT_GATE["max_static"]))
    metrics["gate"] = {"min_mean": min_mean, "max_static": max_static}
    passed = metrics["mean_delta"] >= min_mean and metrics["static_share"] <= max_static
    metrics["status"] = "passed" if passed else "failed"
    metrics["statement"] = (
        "MOTION SPEC: %s - mean frame delta %.2f (baseline 0.82), "
        "%.1f%% near-static frames (baseline 51.4%%, limit %.0f%%)"
        % (
            "PASSED" if passed else "FAILED",
            metrics["mean_delta"],
            100 * metrics["static_share"],
            100 * max_static,
        )
    )
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", default=DEFAULT_SCRIPT, help="film script to render")
    parser.add_argument("--out", required=True, help="directory for the delivered film")
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", type=int, default=92)
    parser.add_argument("--delivery-height", type=int, default=1080)
    parser.add_argument("--skip-4k", action="store_true")
    parser.add_argument("--frames", default=None,
                        help="reuse an existing frame directory (skips rendering)")
    parser.add_argument("--voice-script", default=None,
                        help="JSON narration script; synthesise a voiceover and mix it in")
    parser.add_argument("--voice-dir", default=None,
                        help="where the voiceover lives (default: <out>/voice)")
    parser.add_argument("--voice", default="en_US-lessac-medium", help="Piper voice name")
    parser.add_argument("--voice-backend", default="auto", choices=["auto", "piper", "espeak"])
    parser.add_argument("--voice-offline", action="store_true",
                        help="never download voice weights (fail instead)")
    parser.add_argument("--duck-db", type=float, default=8.5,
                        help="how far the score drops under speech")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)

    started = time.time()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "build" / "frames"
    script = (ROOT / args.script).resolve()

    try:
        ffmpeg, ffprobe = base.resolve_ffmpeg()
    except base.DependencyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if not script.is_file():
        print("film script not found: %s" % script, file=sys.stderr)
        return 2
    if not base.canvas_module_available():
        print("the canvas module is not installed (cd video_studio && npm ci)", file=sys.stderr)
        return 3

    voice_dir = Path(args.voice_dir).resolve() if args.voice_dir else out_dir / "voice"
    step_count = 8 if (args.voice_script or (voice_dir / "voiceover.wav").is_file()) else 6
    step_no = 0

    def step(label: str) -> str:
        nonlocal step_no
        step_no += 1
        return "== %d/%d %s" % (step_no, step_count, label)

    try:
        voice_info = None
        mixed = None
        voice_wav = voice_dir / "voiceover.wav"
        voice_lines = voice_dir / "lines.json"
        if args.voice_script:
            log(step("voice"))
            voice_info = step_voice(
                (ROOT / args.voice_script).resolve(), voice_dir, voice=args.voice,
                allow_download=not args.voice_offline, backend=args.voice_backend,
                fps=args.fps,
            )
            log("   %s, %.2fs, %d lines" % (voice_info["backend"], voice_info["duration_seconds"],
                                            voice_info["line_count"]))
        elif voice_wav.is_file():
            log("   voice present: %s" % voice_wav)
            voice_info = {"path": str(voice_wav), "reused": True}
        if voice_info is not None and not voice_lines.is_file():
            raise RuntimeError("a voice track exists without lines.json; the picture cannot sync to it")

        if args.frames:
            frames_dir = Path(args.frames).resolve()
            manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
            log(step("reuse %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"])))
        else:
            log(step("render frames"))
            manifest = step_frames(script, frames_dir, args.width, args.height, args.fps, args.quality,
                                   voice_lines if voice_info else None)
            log("   %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"]))

        log(step("soundtrack"))
        soundtrack = out_dir / "soundtrack.wav"
        audio_info = step_soundtrack(frames_dir / "film.json", soundtrack)
        log("   %d sfx cues, %.1fs" % (audio_info.get("sfx_cue_count", 0), audio_info["duration_seconds"]))

        audio_track = soundtrack
        mix_info = None
        if voice_info is not None:
            log(step("mix voice over score"))
            mixed = out_dir / "mix.wav"
            mix_info = step_mix(soundtrack, voice_wav, mixed, args.duck_db)
            audio_track = mixed
            log("   duck %.1f dB, voice %.1f dB above the bed, peak %.2f"
                % (mix_info["duck_depth_db"], mix_info["voice_to_bed_db"], mix_info["peak"]))
            if voice_info.get("path") and Path(voice_info["path"]).is_file():
                # keep a copy next to the film so the mix is auditable after the fact
                target = out_dir / "voiceover.wav"
                if Path(voice_info["path"]).resolve() != target.resolve():
                    target.write_bytes(Path(voice_info["path"]).read_bytes())

        log(step("validate frames"))
        validation = step_validate(frames_dir)

        log(step("encode"))
        outputs = []
        if not args.skip_4k:
            master = out_dir / ("film-%dx%d.mp4" % (args.width, args.height))
            outputs.append(
                # 4K x264 at default thread counts needs more memory than a
                # small CI box or laptop has; these settings keep it near 1 GB.
                base.encode(frames_dir, audio_track, master, ffmpeg, fps=args.fps, crf=20,
                            preset="veryfast", audio_bitrate="192k",
                            extra=["-threads", "1",
                                   "-x264-params", "rc-lookahead=8:ref=1:bframes=2"])
            )
            log("   4K master %s (%.1f MB)" % (master.name, master.stat().st_size / 1048576))
        delivery = out_dir / ("film-%dp.mp4" % args.delivery_height)
        outputs.append(
            base.encode(frames_dir, audio_track, delivery, ffmpeg, fps=args.fps, crf=21,
                        preset="medium", audio_bitrate="160k",
                        scale="scale=-2:%d:flags=lanczos" % args.delivery_height)
        )
        log("   delivery %s (%.1f MB)" % (delivery.name, delivery.stat().st_size / 1048576))

        log(step("measure motion"))
        film_meta = json.loads((frames_dir / "film.json").read_text(encoding="utf-8"))
        gate = film_meta.get("motion_gate") or DEFAULT_GATE
        motion = measure_motion(delivery, ffmpeg, out_dir / "build", gate)
        log("   " + motion["statement"])

        log(step("content audit"))
        audit = base.step_audit(delivery, out_dir / "audit", ffmpeg)
        log("   " + audit["statement"])

        contact = out_dir / "contact-sheet.jpg"
        base.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(delivery),
             "-vf", "fps=1/2,scale=480:-2:flags=lanczos,tile=5x2:padding=6:color=0x101010",
             "-frames:v", "1", str(contact)],
            timeout=600,
        )

        film = json.loads((frames_dir / "film.json").read_text(encoding="utf-8"))
        summary = {
            "title": film["title"],
            "source": args.script,
            "canvas": {"width": args.width, "height": args.height, "fps": args.fps},
            "frames": {"count": manifest["frame_count"]},
            "elapsed_seconds": round(time.time() - started, 1),
            "motion_spec": motion,
            "audit": {key: audit[key] for key in ("status", "statement", "summary") if key in audit},
            "soundtrack": {key: audio_info[key] for key in ("duration_seconds", "sfx_cue_count", "sample_rate") if key in audio_info},
            "voice": ({key: voice_info[key] for key in ("backend", "voice", "duration_seconds", "line_count", "path", "reused") if key in voice_info}
                      if voice_info else None),
            "mix": mix_info,
            "validation": validation,
            "outputs": [
                {
                    "path": item["path"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                    "probe": base.probe(Path(item["path"]), ffprobe),
                }
                for item in outputs
            ],
            "timeline": film,
        }
        (out_dir / "render-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (frames_dir / "film.json").replace(out_dir / "film.json")
        (frames_dir / "timeline.txt").replace(out_dir / "timeline.txt")

        ok = motion["status"] == "passed" and audit.get("status") != "flagged"
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print()
            print("FILM:", summary["title"], "|", summary["frames"]["count"], "frames |",
                  summary["elapsed_seconds"], "s")
            print(motion["statement"])
            print(audit["statement"])
            for item in summary["outputs"]:
                print("OUTPUT:", Path(item["path"]).name, "%.1f MB" % (item["bytes"] / 1048576))
        return 0 if ok else 1
    except base.DependencyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print("render failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
