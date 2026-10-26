#!/usr/bin/env python3
"""Say what a film's acts drew, and how each one arrived.

    python tools/plan_summary.py --plan build/film/build/frames/plan.json \\
        --slug battery-twenty >> "$GITHUB_STEP_SUMMARY"

The plan already knows both halves of the picture - the template is *what* was
drawn, the entrance is *how it landed* - so a run report can say it without
decoding a single frame. That matters because the owner's test is not "did the
gates pass" but "does each film look like the script it was made from", and a
table of acts is the cheapest possible answer to that question.
"""
from __future__ import annotations

import argparse
import json
import pathlib


def rows(plan: dict) -> list[tuple[str, str, str, str]]:
    """One row per act: id, picture(s), entrance, length."""
    out = []
    seen = set()
    for shot in plan.get("shots", []):
        section = shot["section"]
        if section in seen:
            continue
        seen.add(section)
        pictures = []
        for other in plan["shots"]:
            if other["section"] != section:
                continue
            name = str(other.get("template", "?"))
            if name not in pictures:
                pictures.append(name)
        length = 0.0
        spans = [s for s in plan["shots"] if s["section"] == section]
        if spans:
            length = max(s["end"] for s in spans) - min(s["start"] for s in spans)
        out.append((section, " > ".join(pictures), str(shot.get("entrance") or "-"),
                    f"{length:.1f}s"))
    return out


def markdown(slug: str, plan: dict) -> str:
    table = "\n".join(f"| {act} | {picture} | {entrance} | {length} |"
                      for act, picture, entrance, length in rows(plan))
    duration = plan.get("duration_seconds")
    head = f"### {slug}"
    if duration:
        head += f" - {float(duration):.1f}s"
    return (f"{head}\n\n| act | picture | entrance | length |\n|---|---|---|---|\n{table}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=pathlib.Path)
    parser.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    print(markdown(args.slug, plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
