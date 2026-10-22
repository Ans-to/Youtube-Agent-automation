#!/usr/bin/env python3
"""Render long videos in slices, so a 20-minute film does not need 200 GB of disk.

The single-pass renderer writes every frame to disk as a PNG and only then starts
FFmpeg. That is fine for a 30-second clip and impossible for a 20-minute one:
1,200 seconds at 30 fps is 36,000 PNGs, several hundred gigabytes, and a render
that dies near the end loses all of it.

This module renders the film as a sequence of slices instead:

1. Plan the slice boundaries from the storyboard's own scene lengths.
2. For each slice, ask `video_studio/render.js` for exactly that frame range
   (it can start mid-film, because a frame is a pure function of its index).
3. Encode the slice to its own MP4 part with FFmpeg, then delete that slice's
   frames before the next one starts.
4. Concatenate the parts without re-encoding, and mux the audio once.

Consequences that matter:

- **Disk stays flat.** At most one slice of PNGs exists at a time, whatever the
  length of the film.
- **A crash costs one slice, not the film.** Finished parts are kept and reused
  on the next run with `--resume`.
- **A long render is visible while it happens**: per-slice progress and a rate
  measured from real slices, not a guess.

Nothing here is clever about codecs or quality: the requested resolution, frame
rate and CRF are passed through untouched, because a smaller machine or a longer
film is never a reason to quietly change what was asked for.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = 1

#: One slice of one minute keeps a 1080p slice's PNGs to roughly 2 GB at the
#: worst, and keeps a failed slice cheap to repeat. Longer slices need less
#: overhead but more transient disk; shorter ones add encode/concat passes.
DEFAULT_SEGMENT_SECONDS = 60
#: A requested slice size is honoured, right down to one frame. Silently rounding
#: it up would mean rendering something other than what was asked for, which is
#: the exact failure this project refuses elsewhere. Very small slices do add
#: encode and concat overhead, and `render` says so rather than "fixing" it.
MIN_SEGMENT_FRAMES = 1

#: The renderer's own per-call ceiling. A slice may not exceed it.
MAX_FRAMES_PER_CALL = 30_000


def frames_for_scenes(storyboard):
    """Frame counts per scene, computed exactly as render.js computes them."""
    fps = int(storyboard.get("fps") or 30)
    counts = []
    for index, scene in enumerate(storyboard.get("scenes") or [], start=1):
        try:
            seconds = float(scene.get("duration_seconds"))
        except (TypeError, ValueError):
            raise ValueError(f"Scene {index} has no valid duration_seconds.")
        if not seconds > 0 or seconds > 600:
            raise ValueError(f"Scene {index} duration must be >0 and <=600 seconds.")
        counts.append(max(1, round(seconds * fps)))
    if not counts:
        raise ValueError("Storyboard contains no scenes.")
    return counts


def plan_segments(total_frames, *, segment_frames):
    """Split a frame count into contiguous slices, last one short."""
    if total_frames < 1:
        raise ValueError("total_frames must be positive.")
    segment_frames = max(MIN_SEGMENT_FRAMES, min(int(segment_frames), MAX_FRAMES_PER_CALL))
    plan = []
    start = 0
    while start < total_frames:
        count = min(segment_frames, total_frames - start)
        plan.append({"index": len(plan), "start": start, "count": count})
        start += count
    return plan


def describe_plan(storyboard, plan, *, fps):
    """What this job will do, in the numbers a user needs before waiting."""
    total = sum(item["count"] for item in plan)
    return {
        "duration_seconds": round(total / fps, 2),
        "total_frames": total,
        "segments": len(plan),
        "fps": fps,
        "resolution": [int(storyboard.get("width") or 1920), int(storyboard.get("height") or 1080)],
        "largest_slice_frames": max(item["count"] for item in plan),
    }


def _default_run(command, *, timeout):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _tail(result, limit=600):
    text = (getattr(result, "stderr", "") or "") + (getattr(result, "stdout", "") or "")
    return text.strip()[-limit:]


def render(storyboard_path, output_path, *, fps=None, segment_seconds=None,
           work_dir=None, audio=None, crf=20, preset="veryfast", threads=None,
           extra_filters=None, keep_frames=False, resume=True, node=None,
           ffmpeg=None, run=None, log=print, validate_slice=None):
    """Render a storyboard of any length to one MP4. Returns a job record."""
    storyboard_path = Path(storyboard_path)
    output_path = Path(output_path)
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    fps = int(fps or storyboard.get("fps") or 30)
    if not 1 <= fps <= 60:
        raise ValueError("fps must be 1..60.")

    counts = frames_for_scenes(storyboard)
    total_frames = sum(counts)
    segment_frames = (segment_seconds or DEFAULT_SEGMENT_SECONDS) and int(
        round((segment_seconds or DEFAULT_SEGMENT_SECONDS) * fps))
    plan = plan_segments(total_frames, segment_frames=segment_frames)

    node = node or shutil.which("node")
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not node:
        raise RuntimeError("Node.js was not found; the renderer cannot run.")
    if not ffmpeg:
        raise RuntimeError("FFmpeg was not found; the slices cannot be encoded.")
    run = run or _default_run

    work_dir = Path(work_dir) if work_dir else output_path.parent / (output_path.stem + ".long-form")
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = describe_plan(storyboard, plan, fps=fps)
    record = {
        "schema": SCHEMA,
        "storyboard": str(storyboard_path),
        "output": str(output_path),
        "plan": summary,
        "slices": [],
        "resumed_slices": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "quality": {"crf": crf, "preset": preset, "note":
                    "resolution, frame rate and CRF are exactly what was requested"},
    }
    log("Long-form render: %.1f min, %d frames, %d slice(s) of %d frames"
        % (summary["duration_seconds"] / 60, total_frames, len(plan), plan[0]["count"]))
    if len(plan) > 60:
        log("  note: %d slices is a lot of encode and concat overhead; a larger"
            " --segment-seconds is faster with the same output" % len(plan))

    started = time.monotonic()
    parts = []
    for item in plan:
        part = work_dir / ("part-%03d.mp4" % item["index"])
        part_record_path = work_dir / ("part-%03d.json" % item["index"])
        slice_dir = work_dir / ("frames-%03d" % item["index"])
        slice_manifest = work_dir / ("manifest-%03d.json" % item["index"])

        if resume and _part_is_complete(part, part_record_path, item):
            record["resumed_slices"] += 1
            record["slices"].append(json.loads(part_record_path.read_text(encoding="utf-8")))
            parts.append(part)
            log("  slice %d/%d already done (%d frames), reusing it"
                % (item["index"] + 1, len(plan), item["count"]))
            continue

        slice_started = time.monotonic()
        _render_slice(node, storyboard_path, slice_dir, slice_manifest, item, run=run)
        _check_slice(slice_manifest, item)
        if validate_slice is not None:
            # Checking each slice beats checking once at the end: a bad slice is
            # caught while its frames are still on disk and can be re-rendered,
            # instead of after the whole film has been encoded.
            try:
                validate_slice(slice_dir, slice_manifest, item)
            except Exception as exc:  # noqa: BLE001 - any validator failure is fatal here
                raise RuntimeError("slice at frame %d failed validation: %s"
                                   % (item["start"], exc)) from exc
        _encode_slice(ffmpeg, slice_dir, part, item, fps=fps, crf=crf,
                      preset=preset, threads=threads, extra_filters=extra_filters, run=run)
        slice_seconds = round(time.monotonic() - slice_started, 1)

        slice_record = {
            "index": item["index"], "start": item["start"], "count": item["count"],
            "seconds": slice_seconds,
            "bytes": part.stat().st_size,
        }
        part_record_path.write_text(json.dumps(slice_record, indent=2) + "\n", encoding="utf-8")
        record["slices"].append(slice_record)
        parts.append(part)

        if not keep_frames:
            shutil.rmtree(slice_dir, ignore_errors=True)
            slice_manifest.unlink(missing_ok=True)

        done = sum(entry["count"] for entry in record["slices"])
        rate = done / max(0.001, time.monotonic() - started)
        left = max(0, total_frames - done)
        log("  slice %d/%d done in %ss (%d/%d frames, %.2f fps, ~%s left)"
            % (item["index"] + 1, len(plan), _pretty(slice_seconds), done, total_frames,
               rate, _pretty(left / max(rate, 0.01))))

    _concat(ffmpeg, work_dir, parts, output_path, audio=audio, run=run)

    record["elapsed_seconds"] = round(time.monotonic() - started, 1)
    record["bytes"] = output_path.stat().st_size if output_path.is_file() else 0
    record["duration_seconds"] = round(total_frames / fps, 2)
    record["complete"] = all(entry["count"] for entry in record["slices"]) and len(parts) == len(plan)
    record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (work_dir / "long-form.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    log("Rendered %.1f min in %s -> %s"
        % (record["duration_seconds"] / 60, _pretty(record["elapsed_seconds"]), output_path))
    return record


def _part_is_complete(part, record_path, item):
    """A part counts as done only if the file is non-empty and its record agrees."""
    if not part.is_file() or part.stat().st_size == 0 or not record_path.is_file():
        return False
    try:
        saved = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return saved.get("start") == item["start"] and saved.get("count") == item["count"]


def _render_slice(node, storyboard_path, slice_dir, manifest, item, *, run):
    command = [
        node, str(ROOT / "video_studio" / "render.js"), str(storyboard_path),
        "--from-frame=%d" % item["start"],
        "--frame-count=%d" % item["count"],
        "--out-dir=%s" % slice_dir,
        "--manifest=%s" % manifest,
    ]
    # A slice is bounded by the renderer's own 30,000-frame cap; the timeout is
    # scaled from that so a slow CPU gets time instead of a spurious failure.
    timeout = max(1800, item["count"] * 4)
    result = run(command, timeout=timeout)
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError("slice render failed at frame %d: %s"
                           % (item["start"], _tail(result)))
    if not manifest.is_file():
        raise RuntimeError("slice render wrote no manifest for frame %d" % item["start"])


def _check_slice(manifest, item):
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    written = int(data.get("frame_count") or 0)
    if written != item["count"]:
        raise RuntimeError("slice at frame %d produced %d of %d frames"
                           % (item["start"], written, item["count"]))
    if int(data.get("first_frame", -1)) != item["start"]:
        raise RuntimeError("slice manifest disagrees about its first frame")


def _encode_slice(ffmpeg, slice_dir, part, item, *, fps, crf, preset, threads,
                  extra_filters, run):
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps),
        "-start_number", str(item["start"]),
        "-i", str(Path(slice_dir) / "frame-%06d.png"),
        "-frames:v", str(item["count"]),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
    ]
    if threads:
        command += ["-threads", str(threads)]
    if extra_filters:
        command += list(extra_filters)
    command += [str(part)]
    timeout = max(1800, item["count"] * 2)
    result = run(command, timeout=timeout)
    if getattr(result, "returncode", 1) != 0 or not Path(part).is_file() or Path(part).stat().st_size == 0:
        raise RuntimeError("slice encode failed at frame %d: %s" % (item["start"], _tail(result)))


def _concat(ffmpeg, work_dir, parts, output_path, *, audio, run):
    if not parts:
        raise RuntimeError("nothing to concatenate")
    listing = Path(work_dir) / "concat.txt"
    listing.write_text("".join("file '%s'\n" % Path(part).resolve() for part in parts),
                       encoding="utf-8")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", str(listing)]
    audio_path = Path(audio) if audio else None
    if audio_path and audio_path.is_file():
        command += ["-i", str(audio_path)]
    command += ["-c:v", "copy"]
    if audio_path and audio_path.is_file():
        command += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"]
    command += ["-movflags", "+faststart", str(output_path)]
    result = run(command, timeout=3600)
    if getattr(result, "returncode", 1) != 0 or not Path(output_path).is_file():
        raise RuntimeError("concatenation failed: " + _tail(result))


def _pretty(seconds):
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return "%ds" % seconds
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return "%dm %02ds" % (minutes, rest)
    hours, minutes = divmod(minutes, 60)
    return "%dh %02dm" % (hours, minutes)


def frame_validator():
    """Validate a slice with the project's own frame checker.

    Imported lazily so this module stays usable (and testable) without the video
    studio on the path.
    """
    sys.path.insert(0, str(ROOT / "video_studio"))
    import validate_frames

    def check(frames_dir, manifest_path, item):
        return validate_frames.validate(frames_dir, manifest_path,
                                        start_number=item["start"])
    return check


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render long videos in slices.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--segment-seconds", type=int, default=DEFAULT_SEGMENT_SECONDS,
                        help="length of one slice (default 60s; fewer, larger slices are faster)")
    parser.add_argument("--audio", default=None, help="narration or mix to mux once at the end")
    parser.add_argument("--crf", type=int, default=20)
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-validate", action="store_true",
                        help="skip the per-slice frame validation (not recommended)")
    parser.add_argument("--plan-only", action="store_true", help="print the slice plan and exit")
    args = parser.parse_args(argv)

    storyboard = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    fps = int(storyboard.get("fps") or 30)
    counts = frames_for_scenes(storyboard)
    plan = plan_segments(sum(counts),
                         segment_frames=int(round(args.segment_seconds * fps)))
    print(json.dumps(describe_plan(storyboard, plan, fps=fps), indent=2))
    if args.plan_only:
        return 0
    try:
        render(args.storyboard, args.output, segment_seconds=args.segment_seconds,
               audio=args.audio, crf=args.crf, preset=args.preset, threads=args.threads,
               keep_frames=args.keep_frames, resume=not args.no_resume,
               validate_slice=None if args.no_validate else frame_validator())
    except (RuntimeError, ValueError, OSError) as exc:
        print("LONG-FORM RENDER FAILED:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
