#!/usr/bin/env python3
"""Ask a video how often it actually changes the picture.

The freeze checks ask "did anything move?" and are beaten by grain or a ticking
caption. This asks "is this a new arrangement?", which decoration cannot fake.

    python tools/check_composition.py docs/media/vibe-coding-preview.mp4
    python tools/check_composition.py film.mp4 --json --max-hold 8

Exit codes: 0 the picture keeps changing, 1 it is a slideshow, 2 bad input or
no FFmpeg, 3 the file was too short to judge.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video_studio.composition import (  # noqa: E402 - path set up above
    MAX_HOLD_SECONDS,
    SAMPLE_FPS,
    analyse_video,
    format_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", help="the file to judge")
    parser.add_argument("--max-hold", type=float, default=MAX_HOLD_SECONDS,
                        help="longest a single arrangement may stay (default %.0f s)"
                             % MAX_HOLD_SECONDS)
    parser.add_argument("--ffmpeg", default=None, help="FFmpeg binary to use")
    parser.add_argument("--sample-fps", type=float, default=None,
                        help="frames a second to judge (default %.1f). Probing one scene "
                             "wants a finer rate than the whole film; the verdict was "
                             "checked to be the same at 1, 2 and 4 frames a second"
                             % SAMPLE_FPS)
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    parser.add_argument("--quiet", action="store_true", help="say nothing when it passes")
    args = parser.parse_args(argv)

    path = Path(args.video)
    if not path.is_file():
        print("no such video: %s" % path, file=sys.stderr)
        return 2
    try:
        kwargs = {}
        if args.sample_fps:
            kwargs["sample_fps"] = args.sample_fps
        verdict = analyse_video(path, max_hold_seconds=args.max_hold,
                                ffmpeg=args.ffmpeg, **kwargs)
    except RuntimeError as exc:
        print("composition check could not run: %s" % exc, file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("composition check failed: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2))
    elif not (args.quiet and verdict.get("passed")):
        print(format_report(verdict))
    if verdict["status"] == "not_run":
        return 3
    return 0 if verdict.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
