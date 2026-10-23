#!/usr/bin/env python3
"""Ask a finished film one question: did the picture ever stop moving?

    python tools/check_repeat_frames.py workspace/generated/vibe-coding/film-1080p.mp4

Exit status is 0 when nothing held longer than the limit, 1 when something did,
and 2 when the check could not run at all. The check is described in
``video_studio/repeat_frames.py``; the short version is that it compares each
frame with the frame half a second earlier, on pooled blocks, with a magnitude
threshold - so grain, a drifting dot field, a progress bar or a creeping camera
do not count as movement.

The render driver runs the same check on the delivered file and fails the
render, so this command exists for looking at a file that has already been
built, or for a file built somewhere else.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_studio.repeat_frames import (  # noqa: E402
    DEFAULT_MAX_STILL_SECONDS,
    analyse_video,
    format_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", help="file to check")
    parser.add_argument("--max-still-seconds", type=float, default=DEFAULT_MAX_STILL_SECONDS,
                        help="longest hold that is still acceptable (default %.1f s)"
                             % DEFAULT_MAX_STILL_SECONDS)
    parser.add_argument("--report", help="write the full JSON report here")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a report")
    args = parser.parse_args(argv)

    try:
        report = analyse_video(args.video, max_still_seconds=args.max_still_seconds)
    except (OSError, RuntimeError, ValueError) as exc:
        print("REPEAT CHECK: COULD NOT RUN - %s" % exc, file=sys.stderr)
        return 2

    rendered = json.dumps(report, indent=2)
    if args.report:
        Path(args.report).write_text(rendered + "\n", encoding="utf-8")
    print(rendered if args.json else format_report(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
