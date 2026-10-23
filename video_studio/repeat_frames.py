#!/usr/bin/env python3
"""Detect a picture that has stopped moving, whatever is painted on top of it.

Why this exists
---------------
Three freeze checks already lived in this repository, and all three were beaten
by the same trick: they compare *adjacent* frames. Film grain, sensor noise, a
drifting background dot field or a creeping gradient changes every pixel a
little, every frame, so "did anything change since the last frame?" always
answers yes even when the composition on screen has not changed at all.

This check asks the question a viewer actually asks: **is this the same picture
as half a second ago?**

How it is made immune to the noise
----------------------------------
1. Frames are decoded at 192x108. That averages 55 source pixels of a 1080p
   frame into one, so per-pixel grain is gone before any comparison happens.
2. Those frames are pooled into 32x18 blocks of 6x6 pixels (576 blocks), so a
   block has to move as a *shape* before it counts. The grid is fine enough
   that a line of text arriving is several blocks - at a 16x9 grid one letter
   fell inside a single block and the check called typing "frozen".
3. Each frame is compared against the frame `lag_seconds` in the past, not the
   one before it. A slow drift that moves a fraction of a pixel per frame is
   invisible to a person, and it is invisible here too.
4. A block counts as changed only if its average moved by more than
   `block_delta` grey levels (default 10 of 255). That threshold is the whole
   trick: decoration moves every block a little, content moves a few blocks a
   lot. Measured on a film with a 20 s frozen card, decoration sat at 6-8 levels
   and real content at 20-180.

A span is reported when the share of changed blocks stays below `still_share`
(2% of 576 blocks, i.e. fewer than twelve) for longer than `min_span` seconds.
   A caption ticking over does not make a film "moving", which is the point.
Subtitles ticking does not make a film "moving"; this is deliberate.

Used by
-------
* ``tools/check_repeat_frames.py`` - run it on any file, by hand.
* ``tools/render_authored_film.py`` - runs it on the delivered file and **fails
  the render** if any span is longer than the limit.

This is the check that should have caught the 21-second title card.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np

# Defaults. Changing any of these changes what "moving" means, so they are
# named, documented and reported in every result rather than buried in a call.
SAMPLE_FPS = 10.0
LAG_SECONDS = 0.5
FRAME_WIDTH = 192
FRAME_HEIGHT = 108
BLOCKS_X = 32
BLOCKS_Y = 18
# Calibrated on two real files rather than guessed. In the film that shipped
# with a 20-second frozen title card, decoration (grain, drifting dots, a moving
# sheen) moves blocks by 6-8 grey levels; on the same film, a typed line or a
# panel landing moves blocks by 20-180. Ten levels sits in the gap and separates
# them by a factor of about seventeen.
BLOCK_DELTA = 10.0
STILL_SHARE = 0.02
MIN_SPAN_SECONDS = 0.5
DEFAULT_MAX_STILL_SECONDS = 1.0


def resolve_ffmpeg(ffmpeg: str | None = None) -> str | None:
    """Prefer a system ffmpeg, fall back to the bundled imageio binary."""
    if ffmpeg:
        return ffmpeg
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # pragma: no cover - depends on the local install
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def pool(frame: np.ndarray, blocks_x: int = BLOCKS_X, blocks_y: int = BLOCKS_Y) -> np.ndarray:
    """Average a greyscale frame into blocks. Returns a (blocks_y, blocks_x) float array."""
    height, width = frame.shape[:2]
    # Trim to a whole number of blocks instead of resampling: a partial block at
    # the right edge would carry a different amount of detail and bias the test.
    usable_h = (height // blocks_y) * blocks_y
    usable_w = (width // blocks_x) * blocks_x
    if usable_h < blocks_y or usable_w < blocks_x:
        raise ValueError(
            "frame %dx%d is too small to pool into %dx%d blocks"
            % (width, height, blocks_x, blocks_y)
        )
    grid = frame[:usable_h, :usable_w].astype(np.float32)
    cell_h = usable_h // blocks_y
    cell_w = usable_w // blocks_x
    return grid.reshape(blocks_y, cell_h, blocks_x, cell_w).mean(axis=(1, 3))


def analyse_frames(
    frames,
    *,
    fps: float,
    lag_seconds: float = LAG_SECONDS,
    blocks_x: int = BLOCKS_X,
    blocks_y: int = BLOCKS_Y,
    block_delta: float = BLOCK_DELTA,
    still_share: float = STILL_SHARE,
    min_span_seconds: float = MIN_SPAN_SECONDS,
) -> dict:
    """Measure frozen spans in a sequence of greyscale frames.

    ``frames`` is any iterable of 2-D arrays of the same size, already captured
    at ``fps``. Keeping this function independent of ffmpeg is what makes the
    behaviour testable with synthetic frames - including the case that matters
    most: a still picture with heavy per-pixel noise on top of it.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")

    lag = max(1, int(round(lag_seconds * fps)))
    history: list[np.ndarray] = []
    still_flags: list[bool] = []
    shares: list[float] = []
    judged = 0

    for index, frame in enumerate(frames):
        pooled = pool(frame, blocks_x, blocks_y)
        history.append(pooled)
        if len(history) > lag + 1:
            history.pop(0)
        if index < lag:
            still_flags.append(False)
            shares.append(1.0)
            continue
        previous = history[0]
        changed = float(np.mean(np.abs(pooled - previous) > block_delta))
        shares.append(changed)
        still_flags.append(changed < still_share)
        judged += 1

    spans = _group(still_flags, fps, min_span_seconds)
    longest = max((span["seconds"] for span in spans), default=0.0)
    return {
        "sampled_frames": len(still_flags),
        "judged_frames": judged,
        "lag_seconds": lag / fps,
        "lag_frames": lag,
        "longest_still_seconds": round(longest, 2),
        "still_share_of_frames": round(
            sum(1 for flag in still_flags if flag) / len(still_flags), 4
        ) if still_flags else 0.0,
        "mean_changed_share": round(float(np.mean(shares)) if shares else 0.0, 4),
        "spans": spans,
        "thresholds": {
            "sample_fps": fps,
            "lag_seconds": lag / fps,
            "blocks": [blocks_x, blocks_y],
            "block_delta": block_delta,
            "still_share": still_share,
            "min_span_seconds": min_span_seconds,
        },
    }


def _group(flags: list[bool], fps: float, min_span_seconds: float) -> list[dict]:
    """Turn per-frame still flags into timed spans, longest first."""
    spans: list[list[float]] = []
    run_start = None
    for index, flag in enumerate(flags):
        if flag and run_start is None:
            run_start = index
        elif not flag and run_start is not None:
            spans.append([run_start / fps, index / fps])
            run_start = None
    if run_start is not None:
        spans.append([run_start / fps, len(flags) / fps])

    out = []
    for start, end in spans:
        seconds = end - start
        if seconds + 1e-9 < min_span_seconds:
            continue
        out.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "seconds": round(seconds, 2),
        })
    out.sort(key=lambda span: -span["seconds"])
    return out


def iter_video_frames(path: Path, *, fps: float, width: int, height: int, ffmpeg: str):
    """Stream greyscale frames out of a video without loading it into memory."""
    command = [
        ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(path),
        "-an", "-vf", f"fps={fps},scale={width}:{height}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    frame_bytes = width * height
    try:
        while True:
            chunk = process.stdout.read(frame_bytes)
            if not chunk or len(chunk) < frame_bytes:
                break
            yield np.frombuffer(chunk, dtype=np.uint8).reshape(height, width)
    finally:
        process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", "replace")
        process.stderr.close()
        process.wait(timeout=60)
        if process.returncode not in (0, None) and not stderr.strip():
            raise RuntimeError("ffmpeg failed while decoding %s" % path)


def analyse_video(
    path: Path | str,
    *,
    sample_fps: float = SAMPLE_FPS,
    lag_seconds: float = LAG_SECONDS,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
    blocks_x: int = BLOCKS_X,
    blocks_y: int = BLOCKS_Y,
    block_delta: float = BLOCK_DELTA,
    still_share: float = STILL_SHARE,
    min_span_seconds: float = MIN_SPAN_SECONDS,
    max_still_seconds: float = DEFAULT_MAX_STILL_SECONDS,
    ffmpeg: str | None = None,
) -> dict:
    """Run the check on a video file and decide pass or fail."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    binary = resolve_ffmpeg(ffmpeg)
    if not binary:
        raise RuntimeError("ffmpeg is required for the repeat-frame check")

    frames = iter_video_frames(path, fps=sample_fps, width=width, height=height, ffmpeg=binary)
    report = analyse_frames(
        frames, fps=sample_fps, lag_seconds=lag_seconds,
        blocks_x=blocks_x, blocks_y=blocks_y, block_delta=block_delta,
        still_share=still_share, min_span_seconds=min_span_seconds,
    )
    report["file"] = str(path.resolve())
    return decide(report, max_still_seconds)


def decide(report: dict, max_still_seconds: float = DEFAULT_MAX_STILL_SECONDS) -> dict:
    """Turn measurements into a pass/fail verdict, in place.

    Separate from decoding so the verdict itself is testable without a video.
    A check that could not run is not a check that passed, so a file too short
    to judge fails rather than passing by default.
    """
    report["limit_seconds"] = max_still_seconds
    if report["judged_frames"] == 0:
        report["passed"] = False
        report["status"] = "too_short"
        report["statement"] = (
            "REPEAT CHECK: NOT RUN - the file is shorter than the %.1f s window "
            "needed to judge it" % report["lag_seconds"]
        )
        return report

    over = [span for span in report["spans"] if span["seconds"] > max_still_seconds]
    report["passed"] = not over
    report["status"] = "passed" if report["passed"] else "failed"
    longest = report["longest_still_seconds"]
    if over:
        worst = over[0]
        report["statement"] = (
            "REPEAT CHECK: FAILED - the picture is unchanged for %.1f s at %s "
            "(limit %.1f s); %d frozen span(s)"
            % (worst["seconds"], timecode(worst["start"]), max_still_seconds, len(over))
        )
        report["fix_hint"] = (
            "Nothing on screen may hold for more than %.1f s. Move the content on "
            "every spoken beat, or cut the span out. Grain, drift, a progress bar "
            "or a moving highlight do not count: they are removed by this check."
            % max_still_seconds
        )
    else:
        report["statement"] = (
            "REPEAT CHECK: PASSED - no span longer than %.1f s (longest %.1f s)"
            % (max_still_seconds, longest)
        )
    return report


def timecode(seconds: float) -> str:
    total = max(0, int(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def format_report(report: dict, *, limit: int = 10) -> str:
    """A short, human report, the way a person reads it in a terminal."""
    lines = [
        "REPEAT CHECK  %s" % Path(report.get("file", "?")).name,
        "  %s" % report["statement"],
        "  sampled %d frames at %.0f fps, comparing each to %.1f s earlier"
        % (report["sampled_frames"], report["thresholds"]["sample_fps"], report["lag_seconds"]),
    ]
    if report.get("spans"):
        lines.append("  frozen spans (longest first):")
        for span in report["spans"][:limit]:
            lines.append("    %s -> %s   %5.2f s"
                         % (timecode(span["start"]), timecode(span["end"]), span["seconds"]))
        if len(report["spans"]) > limit:
            lines.append("    ... and %d more" % (len(report["spans"]) - limit))
    if report.get("fix_hint"):
        lines.append("  fix: " + report["fix_hint"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI wrapper
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video")
    parser.add_argument("--max-still-seconds", type=float, default=DEFAULT_MAX_STILL_SECONDS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = analyse_video(args.video, max_still_seconds=args.max_still_seconds)
    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return 0 if report["passed"] else 1
