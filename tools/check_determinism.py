#!/usr/bin/env python3
"""Ask the renderer for the same frame twice and compare the bytes.

Why this exists
---------------
The film is not rendered in one pass. It is rendered in chunks - ``--from`` and
``--to`` - because a ten-minute film does not survive one process, and because
the owner reviews it in thirty-second pieces. That whole approach rests on one
assumption that nobody ever wrote down: **the same frame number must produce the
same pixels no matter which process draws it or what came before it.**

If that assumption is false the failure is silent and ugly. A chunk boundary
would show a seam. A re-render would not match the cut the owner approved. A
resumed render would quietly drift from the abandoned one, and every
measurement we take on the file would describe something we cannot reproduce.

Where the idea comes from
-------------------------
``howardc38/motion-fx-lab`` renders every frame twice, in two different browsers,
and compares all of them; only then does it deliver. Its rule is that a lost
context or a disagreeing process must stop publication rather than ship a blank
or a mismatched frame. We do not use their code - their recorder is a browser
recorder and ours is a local Node renderer - but the rule is worth borrowing,
because a renderer with no repeatability check is a renderer whose output cannot
be trusted to be the thing that was reviewed.

What it checks
--------------
1. **Process repeatability.** The same window is rendered twice, in two separate
   Node processes. Every frame must be byte-identical.
2. **Window independence.** The same window is rendered again with a different
   starting frame in front of it. Every frame must be byte-identical to the
   first render. This is the one that catches state carried across frames -
   an accumulator, an unseeded random, a clock - which is exactly what would
   break chunked rendering while looking fine in a single long render.

Usage
-----
    python tools/check_determinism.py
    python tools/check_determinism.py --film video_studio/films/vibe_coding.mjs --width 640 --start 330
    python tools/check_determinism.py --look dark --json

Exit codes: 0 every frame reproduced, 1 a frame did not, 2 the renderer failed,
3 the renderer produced no frames to compare.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_FILM = "video_studio/films/vibe_coding.mjs"
DEFAULT_WIDTH = 640
DEFAULT_START = 330
DEFAULT_FRAMES = 30
# How much of the film to put in front of the window in the third render. Long
# enough to expose carried state, short enough to stay cheap.
LEAD_IN = 12


def frame_digest(path: Path) -> str:
    """One frame's identity: the bytes the renderer wrote."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(film: str, out: Path, *, width: int, start: int, end: int, look: str) -> dict[int, str]:
    """Render ``start`` to ``end`` and return ``{frame number: digest}``."""
    command = [
        "node", film,
        "--out", str(out),
        "--width", str(width),
        "--from", str(start),
        "--to", str(end),
        "--look", look,
        "--quiet",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "renderer failed (%d)\n%s%s"
            % (completed.returncode, completed.stdout[-2000:], completed.stderr[-2000:])
        )
    frames = {}
    for path in sorted(out.glob("frame-*.jpg")):
        number = int(path.stem.split("-")[1])
        frames[number] = frame_digest(path)
    return frames


def compare(first: dict[int, str], second: dict[int, str], label: str) -> list[str]:
    """Every frame both renders produced, and every disagreement."""
    shared = sorted(set(first) & set(second))
    return [
        "%s: frame %06d differs (%s vs %s)" % (label, number, first[number][:12], second[number][:12])
        for number in shared
        if first[number] != second[number]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--film", default=DEFAULT_FILM, help="the film to render (default %(default)s)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                        help="render width in pixels (default %(default)d)")
    parser.add_argument("--start", type=int, default=DEFAULT_START,
                        help="first frame of the window (default %(default)d)")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                        help="frames in the window (default %(default)d)")
    parser.add_argument("--look", default="light", choices=("light", "dark"),
                        help="the look to render (default %(default)s)")
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = parser.parse_args(argv)

    if not shutil.which("node"):
        print("DETERMINISM: SKIPPED - node is not on PATH", file=sys.stderr)
        return 2
    film_path = (ROOT / args.film).resolve()
    if not film_path.exists():
        print("DETERMINISM: SKIPPED - no film at %s" % film_path, file=sys.stderr)
        return 2

    start, end = args.start, args.start + args.frames
    work = Path(tempfile.mkdtemp(prefix="determinism-"))
    try:
        first = render(args.film, work / "a", width=args.width, start=start, end=end, look=args.look)
        again = render(args.film, work / "b", width=args.width, start=start, end=end, look=args.look)
        shifted = render(args.film, work / "c", width=args.width, start=start - LEAD_IN, end=end,
                         look=args.look)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        print("DETERMINISM: FAILED - the renderer did not finish", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not first:
        print("DETERMINISM: FAILED - the renderer wrote no frames", file=sys.stderr)
        return 3

    problems = compare(first, again, "process repeatability")
    problems += compare(first, shifted, "window independence")
    shared = len(set(first) & set(again) & set(shifted))

    if args.json:
        print(json.dumps({
            "passed": not problems,
            "frames": shared,
            "window": [start, end],
            "lead_in": LEAD_IN,
            "problems": problems,
        }, indent=2))
    elif problems:
        print("DETERMINISM: FAILED - %d frame(s) did not reproduce" % len(problems))
        for problem in problems[:12]:
            print("  " + problem)
        if len(problems) > 12:
            print("  ... and %d more" % (len(problems) - 12))
    else:
        print("DETERMINISM: PASSED - %d frames identical across two processes and two chunk windows"
              % shared)
        print("  window: %06d-%06d, third render led in from %06d" % (start, end - 1, start - LEAD_IN))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
