#!/usr/bin/env python3
"""Render the professional motion film end to end.

One command, no cloud service, no API key:

    python tools/render_motion_film.py --brief video_studio/brief.example.json \\
        --out workspace/generated/motion-film

Steps, each of which is reported with its real result:

1. direction  - compile the brief, score the film, verify the cuts against its
                own beat grid (``motion_director.py --soundtrack``);
2. frames     - rasterise every frame with the no-browser Skia renderer;
3. validate   - contiguous numbering, exact dimensions, real image headers;
4. encode     - H.264 + AAC masters with FFmpeg (4K and a delivery copy);
5. audit      - run the studio's own content/brand/legal/technical auditor on
                the encoded file and keep its verdict.

Exit codes: 0 rendered, 1 a step failed, 2 invalid input, 3 a dependency is
missing (node, the canvas module, or FFmpeg).

The script never claims more than it did. If the 4K encode is skipped, the
summary says so. If the audit is incomplete, the verdict says so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
sys.path.insert(0, str(STUDIO))

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INPUT = 2
EXIT_DEPENDENCY = 3


class DependencyMissing(RuntimeError):
    """A required external tool is not available."""


def log(message: str) -> None:
    print("[render] " + message, flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_node() -> str:
    node = shutil.which("node")
    if not node:
        raise DependencyMissing("node is not installed; the renderer needs Node.js 18 or newer")
    return node


def resolve_ffmpeg() -> tuple[str, str | None]:
    """Return (ffmpeg, ffprobe), falling back to a bundled binary if present.

    The project root goes on ``sys.path`` first: this module is imported by
    ``tools/render_authored_film.py``, which is run as a script, so ``sys.path[0]``
    is ``tools/`` and ``app`` was not importable. The documented render command
    failed on a clean checkout with ModuleNotFoundError before this.
    """
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.infrastructure.ffmpeg import find_ffmpeg, find_ffprobe

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        return ffmpeg, find_ffprobe()
    raise DependencyMissing(
        "FFmpeg is not installed. Install it (apt-get install ffmpeg) or pip install imageio-ffmpeg."
    )


def canvas_module_available() -> bool:
    """True when @napi-rs/canvas can be resolved from video_studio."""
    probe = "require.resolve('@napi-rs/canvas')"
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, resolved binary, no shell
            [resolve_node(), "-e", probe], cwd=str(STUDIO), capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def run(command: list[str], *, cwd: Path = ROOT, timeout: int = 3600) -> subprocess.CompletedProcess:
    log("$ " + " ".join(str(part) for part in command))
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, caller-controlled
        command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False,
    )


def step_direction(brief: Path, build_dir: Path, soundtrack: Path) -> dict:
    """Compile, score and verify. Returns the parsed motion report."""
    import motion_director

    build_dir.mkdir(parents=True, exist_ok=True)
    soundtrack.parent.mkdir(parents=True, exist_ok=True)
    code = motion_director.main([
        "--brief", str(brief),
        "--soundtrack", str(soundtrack),
        "--out-dir", str(build_dir),
    ])
    report_path = build_dir / "motion-report.json"
    if code not in (0, 1) or not report_path.is_file():
        raise RuntimeError("direction failed (exit %d)" % code)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["exit_code"] = code
    return report


def step_frames(storyboard: Path, frames_dir: Path, scale: float, quality: int,
                max_frames: int | None, node: str) -> dict:
    if not canvas_module_available():
        raise DependencyMissing(
            "@napi-rs/canvas is not installed. Run: cd video_studio && npm install --no-save @napi-rs/canvas"
        )
    command = [node, "render_skia.js", str(storyboard), "--out", str(frames_dir),
               "--format", "jpeg", "--quality", str(quality), "--scale", str(scale)]
    if max_frames:
        command += ["--max-frames", str(max_frames)]
    result = run(command, cwd=STUDIO, timeout=7200)
    if result.returncode != 0:
        raise RuntimeError("frame render failed: " + (result.stderr or result.stdout)[-1500:])
    manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
    return {"manifest": manifest, "stdout_tail": result.stdout.strip().splitlines()[-3:]}


def step_validate(frames_dir: Path) -> dict:
    import validate_frames

    return validate_frames.validate(frames_dir, frames_dir / "manifest.json")


def encode(frames_dir: Path, audio: Path, output: Path, ffmpeg: str, *,
           fps: int, crf: int, scale: str | None = None, preset: str = "medium",
           audio_bitrate: str = "192k", extra: list[str] | None = None) -> dict:
    """Assemble the FFmpeg argv and encode. Kept separate so it can be tested."""
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-framerate", str(fps), "-i", str(frames_dir / "frame-%06d.jpg")]
    if audio.is_file():
        command += ["-i", str(audio)]
    if scale:
        command += ["-vf", scale]
    command += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart"]
    if extra:
        command += extra
    if audio.is_file():
        command += ["-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-shortest"]
    command += ["-r", str(fps), str(output)]
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run(command, timeout=7200)
    if result.returncode != 0:
        # Report the exit code: when the OOM killer takes the encoder, stderr is
        # empty and the only surviving evidence is the signal number (137 = 128+9).
        detail = (result.stderr or result.stdout or "").strip()[-1500:] or "(no output)"
        raise RuntimeError("encode failed (exit %s): %s" % (result.returncode, detail))
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("encode produced no file: " + str(output))
    return {"path": str(output), "bytes": output.stat().st_size,
            "sha256": sha256_file(output), "command": command}


def probe(path: Path, ffprobe: str | None) -> dict:
    """Stream metadata for the finished file, when ffprobe is available."""
    if not ffprobe:
        return {"available": False, "reason": "ffprobe is not installed"}
    result = run([ffprobe, "-v", "error", "-show_entries",
                  "format=duration,size:stream=codec_name,width,height,r_frame_rate,channels,sample_rate",
                  "-of", "json", str(path)], timeout=120)
    if result.returncode != 0:
        return {"available": False, "reason": result.stderr[-300:]}
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("width")), {})
    audio = next((item for item in streams if item.get("channels")), {})
    return {
        "available": True,
        "duration_seconds": round(float(data.get("format", {}).get("duration", 0) or 0), 3),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": video.get("r_frame_rate"),
        },
        "audio": {"codec": audio.get("codec_name"), "channels": audio.get("channels"),
                  "sample_rate": audio.get("sample_rate")} if audio else None,
    }


def step_audit(video: Path, report_base: Path, ffmpeg: str) -> dict:
    """Run the studio's content auditor, allowing an honest INCOMPLETE result."""
    import audit_video as audit_cli

    # The auditor calls `ffmpeg`/`ffprobe` by name; make sure a bundled binary
    # on this machine is discoverable for that subprocess too.
    binary = Path(ffmpeg)
    if binary.is_file() and binary.name != "ffmpeg":
        shim_dir = report_base.parent / ".bin"
        shim_dir.mkdir(parents=True, exist_ok=True)
        shim = shim_dir / "ffmpeg"
        if not shim.exists():
            shim.symlink_to(binary)
        import os

        os.environ["PATH"] = str(shim_dir) + os.pathsep + os.environ.get("PATH", "")

    # Call the library rather than the CLI so one analysis pass can be written
    # in both formats: the CLI's --report accepts a single path, and its --json
    # is a boolean toggle for stdout, not a destination.
    report = audit_cli.audit_video(video)
    report["capabilities"] = audit_cli.capabilities()

    markdown_path = report_base.with_suffix(".md")
    json_path = report_base.with_suffix(".json")
    markdown_path.write_text(audit_cli.render_markdown(report), encoding="utf-8")
    json_path.write_text(audit_cli.render_json(report), encoding="utf-8")

    status = report["status"]
    # An INCOMPLETE audit is allowed here for the same reason
    # --allow-incomplete exists in the CLI: this stage fails on real
    # violations, not on rules this machine cannot check.
    code = 1 if status == audit_cli.FLAGGED else 0
    return {
        "exit_code": code,
        "status": status,
        "statement": report["statement"],
        "summary": report["summary"],
        "unverified_rule_ids": report["unverified_rule_ids"],
        "report_markdown": str(markdown_path),
        "report_json": str(json_path),
    }


def build(brief: Path, out_dir: Path, *, scale: float = 1.0, quality: int = 92,
          crf_4k: int = 20, crf_delivery: int = 21, delivery_height: int = 1080,
          max_frames: int | None = None, skip_4k: bool = False,
          skip_audit: bool = False) -> dict:
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir = out_dir / "direction"
    frames_dir = out_dir / "frames"
    soundtrack = out_dir / "soundtrack.wav"

    node = resolve_node()
    ffmpeg, ffprobe = resolve_ffmpeg()

    log("1/5 directing %s" % brief.name)
    motion = step_direction(brief, build_dir, soundtrack)
    if motion.get("status") == "failed":
        log("motion spec failed; the render will be marked non-conformant")
    storyboard_path = build_dir / "storyboard.json"
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))

    log("2/5 rendering frames at scale %.2f" % scale)
    frames = step_frames(storyboard_path, frames_dir, scale, quality, max_frames, node)

    log("3/5 validating frames")
    validation = step_validate(frames_dir)

    log("4/5 encoding")
    fps = int(storyboard.get("fps", 30))
    width = int(storyboard.get("width", 1920))
    height = int(storyboard.get("height", 1080))
    outputs = []
    if not skip_4k:
        master = out_dir / ("%s-%dx%d.mp4" % ("film", frames["manifest"]["width"], frames["manifest"]["height"]))
        outputs.append(encode(frames_dir, soundtrack, master, ffmpeg, fps=fps,
                              crf=crf_4k, scale=None, audio_bitrate="192k"))
    delivery_scale = "scale=-2:%d:flags=lanczos" % delivery_height
    delivery = out_dir / ("film-%dp.mp4" % delivery_height)
    outputs.append(encode(frames_dir, soundtrack, delivery, ffmpeg, fps=fps,
                          crf=crf_delivery, scale=delivery_scale, audio_bitrate="160k"))

    for item in outputs:
        item["probe"] = probe(Path(item["path"]), ffprobe)

    audit = None
    if not skip_audit:
        log("5/5 auditing the finished film")
        audit = step_audit(Path(outputs[-1]["path"]), out_dir / "audit", ffmpeg)

    summary = {
        "schema_version": 1,
        "title": storyboard.get("title"),
        "tone": (storyboard.get("style") or {}).get("tone"),
        "canvas": {"width": width, "height": height, "fps": fps},
        "render_scale": scale,
        "frames": {
            "count": validation["frame_count"],
            "rendered_width": frames["manifest"]["width"],
            "rendered_height": frames["manifest"]["height"],
            "format": validation["format"],
        },
        "motion_spec": {
            "status": motion.get("status"),
            "statement": motion.get("statement"),
            "summary": motion.get("summary"),
            "not_checked": [item["id"] for item in motion.get("not_checked", [])],
            "violations": [item["id"] for item in motion.get("violations", [])],
        },
        "soundtrack": {"path": str(soundtrack), "bytes": soundtrack.stat().st_size},
        "outputs": outputs,
        "audit": audit,
        "elapsed_seconds": round(time.time() - started, 1),
        "honest_notes": [
            "The soundtrack is synthesised locally; it contains no licensed music.",
            "Narration is not included unless a local voice model is configured.",
            "An INCOMPLETE audit means rules could not be verified, not that they passed.",
            "Aesthetic quality still requires human review of the encoded file.",
        ],
    }
    (out_dir / "render-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brief", default="video_studio/brief.example.json")
    parser.add_argument("--out", default="workspace/generated/motion-film")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="render scale: 1.0 is full resolution, 0.5 for a fast review copy")
    parser.add_argument("--quality", type=int, default=92, help="JPEG frame quality (1-100)")
    parser.add_argument("--crf-4k", type=int, default=20)
    parser.add_argument("--crf-delivery", type=int, default=21)
    parser.add_argument("--delivery-height", type=int, default=1080)
    parser.add_argument("--max-frames", type=int, help="cap rendered frames (smoke runs)")
    parser.add_argument("--skip-4k", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument("--json", action="store_true", help="print only the summary JSON")
    args = parser.parse_args(argv)

    brief = (ROOT / args.brief).resolve() if not Path(args.brief).is_absolute() else Path(args.brief)
    if not brief.is_file():
        print("render_motion_film: brief not found: %s" % brief, file=sys.stderr)
        return EXIT_INPUT
    if not 0.25 <= args.scale <= 1.0:
        print("render_motion_film: --scale must be between 0.25 and 1.0", file=sys.stderr)
        return EXIT_INPUT
    if not 1 <= args.quality <= 100:
        print("render_motion_film: --quality must be between 1 and 100", file=sys.stderr)
        return EXIT_INPUT

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    try:
        summary = build(brief, out_dir, scale=args.scale, quality=args.quality,
                        crf_4k=args.crf_4k, crf_delivery=args.crf_delivery,
                        delivery_height=args.delivery_height, max_frames=args.max_frames,
                        skip_4k=args.skip_4k, skip_audit=args.skip_audit)
    except DependencyMissing as exc:
        print("render_motion_film: %s" % exc, file=sys.stderr)
        return EXIT_DEPENDENCY
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("render_motion_film: %s" % exc, file=sys.stderr)
        return EXIT_FAILED

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print()
        print("FILM: %s | %dx%d @ %dfps | %d frames | %.1fs"
              % (summary["title"], summary["canvas"]["width"], summary["canvas"]["height"],
                 summary["canvas"]["fps"], summary["frames"]["count"], summary["elapsed_seconds"]))
        for item in summary["outputs"]:
            info = item.get("probe", {})
            size = item["bytes"] / 1048576
            print("  %-28s %6.1f MB  %s" % (Path(item["path"]).name, size,
                                            "%.2fs" % info["duration_seconds"]
                                            if info.get("available") else "duration unprobed"))
        print(summary["motion_spec"]["statement"])
        if summary["audit"]:
            print("CONTENT AUDIT: %s" % summary["audit"]["statement"])
        print("Summary: %s" % (out_dir / "render-summary.json"))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
