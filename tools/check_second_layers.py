#!/usr/bin/env python3
"""Ask whether two different things are moving in the same second.

The composition check asks whether the arrangement changed at all. This asks
where: a second with one thing happening fails, however large that one thing is.

    python tools/check_second_layers.py film.mp4
    python tools/check_second_layers.py film.mp4 --min-live 3 --json

Exit codes: 0 every second has at least ``--min-live`` regions changing, 1 some
second does not, 2 bad input or no FFmpeg, 3 the file was shorter than a second.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video_studio.second_layers import (  # noqa: E402 - path set up above
    MIN_LIVE_REGIONS,
    REGION_BREAK,
    SAMPLES_PER_SECOND,
    analyse_video,
    format_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", help="the file to judge")
    parser.add_argument("--min-live", type=int, default=MIN_LIVE_REGIONS,
                        help="regions that must change inside every second (default %d)"
                             % MIN_LIVE_REGIONS)
    parser.add_argument("--region-break", type=float, default=REGION_BREAK,
                        help="how different a region must get to count (default %.2f)"
                             % REGION_BREAK)
    parser.add_argument("--samples", type=int, default=SAMPLES_PER_SECOND,
                        help="frames examined per second (default %d)" % SAMPLES_PER_SECOND)
    parser.add_argument("--ffmpeg", default=None, help="FFmpeg binary to use")
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    parser.add_argument("--quiet", action="store_true", help="say nothing when it passes")
    args = parser.parse_args(argv)

    path = Path(args.video)
    if not path.is_file():
        print("no such video: %s" % path, file=sys.stderr)
        return 2
    try:
        report = analyse_video(path, ffmpeg=args.ffmpeg, samples_per_second=args.samples,
                              region_break=args.region_break)
    except RuntimeError as exc:
        print("layer check could not run: %s" % exc, file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("layer check failed: %s" % exc, file=sys.stderr)
        return 2

    report.min_live = args.min_live
    if args.json:
        payload = {
            "passed": report.passed,
            "judged_seconds": report.judged,
            "failed_seconds": len(report.failed),
            "pass_share": round(report.pass_share, 4),
            "min_live": report.min_live,
            "region_break": report.region_break,
            "seconds": [
                {"second": second.index, "live": second.live, "passed": second.passed}
                for second in report.seconds
            ],
        }
        print(json.dumps(payload, indent=2))
    elif not (args.quiet and report.passed):
        print(format_report(report))
    if not report.seconds:
        return 3
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
