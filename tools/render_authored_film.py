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

# The contact sheet is a 5x2 tile: this many frames spans the whole film.
CONTACT_TILES = 10


def contact_sheet_fps(duration_seconds: float) -> float:
    """Sampling rate that fills the contact sheet exactly once, whatever the length.

    A fixed cap truncates short films: 0.5 fps over a 12 s cut gives six frames
    for a ten-tile sheet, so four tiles were black. Too low a floor truncates long
    ones, which is why the rate is derived from the duration rather than chosen.
    """
    return max(0.02, CONTACT_TILES / max(0.1, float(duration_seconds)))


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


def segment_plan(total_frames: int, segments: int) -> list[tuple[int, int]]:
    """Split a frame range into contiguous [start, count) runs for one-pass-each.

    Encoding a 3840x2160 film in a single x264 process needs far more memory than
    a 4 GB laptop or a small CI box has; the process is killed part-way through
    and the driver sees only an empty error. Chunking bounds the encoder's frame
    pools, and concat joins the parts losslessly afterwards.
    """
    if total_frames <= 0:
        raise ValueError("a film needs at least one frame")
    segments = max(1, min(int(segments), total_frames))
    base = total_frames // segments
    extra = total_frames % segments
    plan = []
    cursor = 0
    for index in range(segments):
        count = base + (1 if index < extra else 0)
        plan.append((cursor, count))
        cursor += count
    return plan


def encode_segmented(frames_dir: Path, audio: Path, output: Path, ffmpeg: str, *,
                     fps: int, crf: int, preset: str, audio_bitrate: str,
                     total_frames: int, segments: int, work_dir: Path,
                     extra: list[str] | None = None) -> dict:
    """Encode in chunks, concat them, then mux the audio. Same result, less RAM."""
    work_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, (start, count) in enumerate(segment_plan(total_frames, segments)):
        part = work_dir / ("part-%03d.mp4" % index)
        command = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-start_number", str(start),
            "-i", str(frames_dir / "frame-%06d.jpg"),
            "-frames:v", str(count),
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]
        if extra:
            command += extra
        command += [str(part)]
        result = base.run(command, timeout=7200)
        if result.returncode != 0 or not part.is_file() or part.stat().st_size == 0:
            raise RuntimeError("segmented encode failed at part %d: %s"
                               % (index, (result.stderr or result.stdout or "")[-800:]))
        parts.append(part)
        log("   part %d/%d: frames %d-%d" % (index + 1, len(parts) if False else segments,
                                             start, start + count - 1))

    listing = work_dir / "concat.txt"
    listing.write_text("".join("file '%s'\n" % part.resolve() for part in parts), encoding="utf-8")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(listing),
    ]
    if audio.is_file():
        command += ["-i", str(audio)]
    command += ["-c:v", "copy"]
    if audio.is_file():
        command += ["-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-shortest"]
    command += ["-movflags", "+faststart", str(output)]
    result = base.run(command, timeout=3600)
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("concat failed: " + (result.stderr or result.stdout or "")[-1200:])
    for part in parts:
        part.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    return {
        "path": str(output),
        "bytes": output.stat().st_size,
        "sha256": base.sha256_file(output),
        "command": command,
        "mode": "segmented",
        "segments": len(parts),
    }


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
    parser.add_argument("--encode-segments", type=int, default=0,
                        help="encode the master in N chunks (0 = one pass, fall back "
                             "to 6 chunks if the single pass is killed)")
    parser.add_argument("--master-crf", type=int, default=20, help="CRF for the master")
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
            # A pre-rendered narration (a hosted model, a human read) is assembled
            # by tools/assemble_voiceover.py; read its report so the summary says
            # what the picture was actually cut to, not just that a file existed.
            voice_info = {"path": str(voice_wav), "reused": True}
            report_path = voice_dir / "voiceover.json"
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                for key in ("backend", "voice", "duration_seconds", "line_count", "model"):
                    if report.get(key) is not None:
                        voice_info[key] = report[key]
            elif voice_lines.is_file():
                voice_info["line_count"] = len(
                    json.loads(voice_lines.read_text(encoding="utf-8")).get("lines", []))
            log("   voice present: %s%s" % (
                voice_wav.name,
                " (%s, %.2fs, %d lines)" % (voice_info.get("backend", "pre-rendered"),
                                            voice_info["duration_seconds"],
                                            voice_info["line_count"])
                if voice_info.get("duration_seconds") and voice_info.get("line_count") else ""))
        if voice_info is not None and not voice_lines.is_file():
            raise RuntimeError("a voice track exists without lines.json; the picture cannot sync to it")

        if args.frames:
            frames_dir = Path(args.frames).resolve()
            manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
            # A previous pass moves film.json / timeline.txt out to the delivery
            # folder, so a *second* pass over the same frames must read them there.
            if not (frames_dir / "film.json").is_file() and (out_dir / "film.json").is_file():
                log("   using %s from the previous pass" % (out_dir / "film.json").name)
                film_json = out_dir / "film.json"
            else:
                film_json = frames_dir / "film.json"
            log(step("reuse %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"])))
        else:
            log(step("render frames"))
            manifest = step_frames(script, frames_dir, args.width, args.height, args.fps, args.quality,
                                   voice_lines if voice_info else None)
            log("   %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"]))
            film_json = frames_dir / "film.json"

        log(step("soundtrack"))
        soundtrack = out_dir / "soundtrack.wav"
        audio_info = step_soundtrack(film_json, soundtrack)
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
        # A 4K x264 pass needs more memory than a small laptop or CI box has. The
        # single pass is tried first because it is fastest when it fits; if the
        # encoder is killed (exit 137, empty stderr) the chunked path takes over
        # and produces the same file.
        segment_mode = args.encode_segments or 0

        def encode_master(path: Path) -> dict:
            nonlocal segment_mode
            if segment_mode:
                log("   encoding %d segments" % segment_mode)
                return encode_segmented(
                    frames_dir, audio_track, path, ffmpeg, fps=args.fps, crf=args.master_crf,
                    preset="veryfast", audio_bitrate="192k",
                    total_frames=manifest["frame_count"], segments=segment_mode,
                    work_dir=out_dir / "build" / "segments",
                    extra=["-threads", "2", "-x264-params", "rc-lookahead=4:ref=1:bframes=0"])
            try:
                return base.encode(frames_dir, audio_track, path, ffmpeg, fps=args.fps,
                                   crf=args.master_crf, preset="veryfast", audio_bitrate="192k",
                                   extra=["-threads", "1",
                                          "-x264-params", "rc-lookahead=8:ref=1:bframes=2"])
            except RuntimeError as exc:
                message = str(exc)
                out_of_memory = any(token in message for token in ("137", "Killed", "killed")) \
                    or message.rstrip().endswith("(no output)")
                if not out_of_memory:
                    raise  # a real encode error, not an out-of-memory kill
                log("   single-pass encode was killed; retrying in 6 segments")
                segment_mode = 6
                path.unlink(missing_ok=True)
                return encode_master(path)

        if not args.skip_4k:
            master = out_dir / ("film-%dx%d.mp4" % (args.width, args.height))
            info = encode_master(master)
            info.setdefault("mode", "single-pass")
            outputs.append(info)
            log("   master %s (%.1f MB, %s)" % (master.name, info["bytes"] / 1048576, info["mode"]))
        delivery = out_dir / ("film-%dp.mp4" % args.delivery_height)
        outputs.append(
            base.encode(frames_dir, audio_track, delivery, ffmpeg, fps=args.fps, crf=21,
                        preset="medium", audio_bitrate="160k",
                        scale="scale=-2:%d:flags=lanczos" % args.delivery_height)
        )
        log("   delivery %s (%.1f MB)" % (delivery.name, delivery.stat().st_size / 1048576))

        log(step("measure motion"))
        film_meta = json.loads(film_json.read_text(encoding="utf-8"))
        gate = film_meta.get("motion_gate") or DEFAULT_GATE
        motion = measure_motion(delivery, ffmpeg, out_dir / "build", gate)
        log("   " + motion["statement"])

        probed = base.probe(delivery, ffprobe)
        film_duration = float(probed.get("duration_seconds") or 0) or float(
            manifest["frame_count"] / args.fps)

        log(step("content audit"))
        audit = base.step_audit(delivery, out_dir / "audit", ffmpeg)
        log("   " + audit["statement"])

        contact = out_dir / "contact-sheet.jpg"
        # The sheet has to show the *whole* film, not the first ten beats of it: a
        # fixed 1 frame every 2 s silently truncated anything longer than 20 s, so
        # the sampling rate is derived from the delivered duration instead. The
        # old upper cap of 0.5 fps also truncated short films: a 12 s cut sampled
        # at 0.5 fps yields six frames for a 5x2 tile, so four tiles came out black.
        sheet_fps = contact_sheet_fps(film_duration)
        base.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(delivery),
             "-vf", "fps=%.4f,scale=480:-2:flags=lanczos,tile=5x2:padding=6:color=0x101010"
                    % sheet_fps,
             "-frames:v", "1", str(contact)],
            timeout=600,
        )

        film = json.loads(film_json.read_text(encoding="utf-8"))
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
        for name in ("film.json", "timeline.txt"):
            source = frames_dir / name
            if source.is_file() and source.resolve() != (out_dir / name).resolve():
                source.replace(out_dir / name)

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
