#!/usr/bin/env python3
"""Render the hand-authored film in ``video_studio/films/`` end to end.

The film is a real authored animation script (Canvas drawing code with an
explicit timeline), not a storyboard template. This driver only wraps it:

1. frames    - run the film script; it rasterises 3840x2160 frames itself
                and writes ``manifest.json`` / ``film.json`` / ``timeline.txt``;
2. soundtrack- synthesise the score the film declares in ``film.json``;
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
STATIC_BELOW = 0.5


def log(message: str) -> None:
    base.log(message)


def step_frames(
    script: Path, frames_dir: Path, width: int, height: int, fps: int, quality: int
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


def measure_motion(video: Path, ffmpeg: str, work_dir: Path) -> dict:
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
    passed = metrics["mean_delta"] >= MIN_MEAN_DELTA and metrics["static_share"] <= MAX_STATIC_SHARE
    metrics["status"] = "passed" if passed else "failed"
    metrics["statement"] = (
        "MOTION SPEC: %s - mean frame delta %.2f (baseline 0.82), "
        "%.1f%% near-static frames (baseline 51.4%%, limit %.0f%%)"
        % (
            "PASSED" if passed else "FAILED",
            metrics["mean_delta"],
            100 * metrics["static_share"],
            100 * MAX_STATIC_SHARE,
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

    try:
        if args.frames:
            frames_dir = Path(args.frames).resolve()
            manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
            log("== 1/6 reuse %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"]))
        else:
            log("== 1/6 render frames")
            manifest = step_frames(script, frames_dir, args.width, args.height, args.fps, args.quality)
            log("   %d frames at %dx%d" % (manifest["frame_count"], manifest["width"], manifest["height"]))

        log("== 2/6 soundtrack")
        soundtrack = out_dir / "soundtrack.wav"
        audio_info = step_soundtrack(frames_dir / "film.json", soundtrack)
        log("   %d sfx cues, %.1fs" % (audio_info.get("sfx_cue_count", 0), audio_info["duration_seconds"]))

        log("== 3/6 validate frames")
        validation = step_validate(frames_dir)

        log("== 4/6 encode")
        outputs = []
        if not args.skip_4k:
            master = out_dir / ("film-%dx%d.mp4" % (args.width, args.height))
            outputs.append(
                # 4K x264 at default thread counts needs more memory than a
                # small CI box or laptop has; these settings keep it near 1 GB.
                base.encode(frames_dir, soundtrack, master, ffmpeg, fps=args.fps, crf=20,
                            preset="veryfast", audio_bitrate="192k",
                            extra=["-threads", "1",
                                   "-x264-params", "rc-lookahead=8:ref=1:bframes=2"])
            )
            log("   4K master %s (%.1f MB)" % (master.name, master.stat().st_size / 1048576))
        delivery = out_dir / ("film-%dp.mp4" % args.delivery_height)
        outputs.append(
            base.encode(frames_dir, soundtrack, delivery, ffmpeg, fps=args.fps, crf=21,
                        preset="medium", audio_bitrate="160k",
                        scale="scale=-2:%d:flags=lanczos" % args.delivery_height)
        )
        log("   delivery %s (%.1f MB)" % (delivery.name, delivery.stat().st_size / 1048576))

        log("== 5/6 measure motion")
        motion = measure_motion(delivery, ffmpeg, out_dir / "build")
        log("   " + motion["statement"])

        log("== 6/6 content audit")
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
