#!/usr/bin/env python3
"""Build the upload package for a rendered film from the film's own scene table.

A long film needs a title, a description, chapter timestamps and tags before it
can be published. Typing those by hand is how a chapter timestamp ends up half a
minute out of place, so they are read from ``film.json`` — the same file the
renderer wrote, with the times it actually drew.

    python3 tools/youtube_package.py --film workspace/generated/vibe-coding/film.json \\
        --title "Vibe Coding on Arena, through GitHub" --out workspace/generated/vibe-coding/youtube.json

The description is assembled from the film's scenes, so the chapter list can
never disagree with the picture. Nothing here uploads anything: it writes a file
a person reviews and pastes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# YouTube will not show chapters unless the first one starts at 00:00 and there
# are at least three of them, each at least ten seconds long.
MIN_CHAPTER_SECONDS = 10


def stamp(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def chapters(scenes: list[dict], duration: float) -> list[dict]:
    """Chapter list from the scenes, merged until every chapter is long enough."""
    picked: list[dict] = []
    for scene in sorted(scenes, key=lambda s: float(s["start"])):
        start = float(scene["start"])
        label = str(scene.get("chapter") or scene.get("label") or scene.get("id") or "Scene")
        label = label.strip()
        if not label:
            continue
        if not picked and start > 1:
            # The first chapter must start at zero or YouTube ignores all of them.
            picked.append({"at": 0.0, "label": "Intro"})
        if picked and start - picked[-1]["at"] < MIN_CHAPTER_SECONDS:
            continue
        if picked and picked[-1]["label"] == label:
            continue
        picked.append({"at": round(start, 1), "label": label})
    if picked and picked[0]["at"] > 0.5:
        picked.insert(0, {"at": 0.0, "label": "Intro"})
    # A chapter needs to be the last thing in the list to be shown; trim one that
    # starts too near the end to be useful.
    while len(picked) > 1 and duration - picked[-1]["at"] < MIN_CHAPTER_SECONDS:
        picked.pop()
    return picked


def build(film: dict, *, title: str, description: str, tags: list[str] | None,
          site: str | None) -> dict:
    duration = float(film.get("duration_seconds") or 0)
    scenes = film.get("scenes") or film.get("shots") or []
    if duration <= 0:
        raise ValueError("the film has no duration; it was probably not rendered")
    if not scenes:
        raise ValueError("the film has no scene table to build chapters from")

    marks = chapters(scenes, duration)
    if len(marks) < 3:
        raise ValueError("fewer than three chapters: YouTube will not show a chapter list")

    body = [description.strip(), ""]
    body.append("CHAPTERS")
    for mark in marks:
        body.append(f"{stamp(mark['at'])}  {mark['label']}")
    body.append("")
    if site:
        body.append(f"Code and films: {site}")
    body.append("")
    body.append("Everything in this video was drawn in code. No screenshots, no stock "
                "footage, no music library. The narration is synthesised on the machine.")

    return {
        "title": title,
        "duration_seconds": duration,
        "duration_human": stamp(duration),
        "description": "\n".join(body),
        "chapters": marks,
        "tags": tags or [],
        "category": "Education",
        "made_for_kids": False,
        "chapters_ok": len(marks) >= 3 and marks[0]["at"] == 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--film", required=True, help="film.json written by the renderer")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="", help="comma separated")
    parser.add_argument("--site", default="")
    parser.add_argument("--out", default=None, help="default: youtube.json beside the film")
    args = parser.parse_args(argv)

    film_path = Path(args.film)
    if not film_path.is_file():
        print("no such film.json: %s" % film_path, file=sys.stderr)
        return 2
    film = json.loads(film_path.read_text(encoding="utf-8"))
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    try:
        package = build(film, title=args.title, description=args.description,
                        tags=tags, site=args.site or None)
    except ValueError as exc:
        print("cannot package this film: %s" % exc, file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else film_path.with_name("youtube.json")
    out.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    print("YOUTUBE: %s (%s, %d chapters) -> %s"
          % (package["title"], package["duration_human"], len(package["chapters"]), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
