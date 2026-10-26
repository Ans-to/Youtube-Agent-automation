#!/usr/bin/env python3
"""List the briefs in the studio, for a workflow that renders a set of them.

    python tools/brief_slugs.py                 # one slug per line, in order
    python tools/brief_slugs.py --matrix        # {"include": [{"slug": ...}]}
    python tools/brief_slugs.py --matrix --films all
    python tools/brief_slugs.py --matrix --films battery-twenty,ten-minutes

The matrix shape is what `strategy.matrix` wants, so the list of films is kept in
one place - the brief folder - instead of being copied into a workflow file where
it would quietly go stale the first time somebody added a script.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "video_studio" / "briefs"


def slugs_from_folder() -> list[str]:
    out = []
    for path in sorted(BRIEFS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(str(data.get("slug") or path.stem))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--films", default="all",
                        help='comma-separated slugs, or "all" (the default)')
    parser.add_argument("--matrix", action="store_true",
                        help="print the GitHub Actions matrix JSON instead of a list")
    args = parser.parse_args(argv)

    known = slugs_from_folder()
    if not known:
        print("no briefs found", file=sys.stderr)
        return 1
    if args.films.strip().lower() in {"all", ""}:
        chosen = known
    else:
        asked = [part.strip() for part in args.films.split(",") if part.strip()]
        missing = [slug for slug in asked if slug not in known]
        if missing:
            print(f"no such brief: {', '.join(missing)}", file=sys.stderr)
            return 1
        chosen = asked

    if args.matrix:
        print(json.dumps({"include": [{"slug": slug} for slug in chosen]}))
    else:
        print("\n".join(chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
