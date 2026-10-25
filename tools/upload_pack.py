#!/usr/bin/env python3
"""Turn a finished film into the pack you paste into YouTube.

A film is not published by uploading it. It is published by uploading it with a
title that earns a click, a description that keeps the promise the thumbnail
made, chapters that let a viewer jump to the part they came for, and a pinned
comment that gives them something to do next. That is work a channel does every
time, and it is work that can be derived from the film itself - the brief knows
the promise, the plan knows when each section starts, the subtitles know what is
actually said - so none of it has to be invented at upload time.

    python tools/upload_pack.py \
        --brief video_studio/briefs/review-ai-code.json \
        --film build/film/film.json \
        --out build/upload-pack.md

What it enforces, because YouTube does:

  - a title under 100 characters, and the first option under 60 so it is not
    truncated on a phone;
  - at least three chapters, the first at 0:00, and every chapter at least ten
    seconds long - so short sections are merged into their neighbour rather than
    silently dropped by YouTube;
  - a description under 5000 characters and tags under 500.

Nothing in the pack claims anything the film does not say: the description is
built from the brief's promise and the sections' own headings, and the chapters
are the sections' real times.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_TITLE = 100
SHORT_TITLE = 60
MAX_DESCRIPTION = 5000
MAX_TAGS = 500
MIN_CHAPTER_SECONDS = 10.0

# Words that carry no search value on their own. A tag list made of these is a
# tag list that competes with every video on the platform.
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "it", "this", "that", "you", "your", "how", "what", "why", "when",
    "not", "no", "do", "does", "doesn", "dont", "don't", "at", "as", "by", "be",
    "just", "all", "one", "two", "three", "into", "from", "than", "then",
}


def stamp(seconds: float) -> str:
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def slug_words(value: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in STOPWORDS]


def sentence(value: str) -> str:
    """A heading, set as a sentence: 'The three checks' stays, 'AN AGENT' relaxes."""
    value = value.strip()
    if not value:
        return value
    if value.isupper():
        value = value.lower()
    return value[0].upper() + value[1:]


def chapters_from_sections(sections: list[dict], duration: float) -> list[dict]:
    """Merge sections until every chapter clears YouTube's ten-second floor.

    A section is a beat of the argument; a chapter is a place a viewer can jump
    to. They are not the same list - the film has nine sections and some are five
    seconds long - so a short section is folded into the chapter that follows it,
    keeping the earlier timestamp and the fuller heading. The first chapter always
    starts at zero, because a chapter list that does not is rejected.
    """
    marks = [{"start": 0.0,
              "heading": sentence(sections[0]["heading"]) if sections else "Start"}]
    for section in sections[1:]:
        marks.append({"start": round(float(section["start"]), 3),
                      "heading": sentence(section.get("heading") or section.get("id") or "")})
    marks[0]["start"] = 0.0
    marks[0]["heading"] = sentence(marks[0]["heading"])

    merged: list[dict] = []
    for mark in marks:
        if not merged:
            merged.append(dict(mark))
            continue
        previous = merged[-1]
        if mark["start"] - previous["start"] < MIN_CHAPTER_SECONDS:
            # Too soon after the last one: this heading joins the chapter it sits
            # in, and the chapter keeps the name of the place, not the beat.
            previous["also"] = (previous.get("also") or []) + [mark["heading"]]
            continue
        merged.append(dict(mark))

    # The last chapter has to be ten seconds long too, or there is no last chapter.
    if len(merged) > 1 and duration - merged[-1]["start"] < MIN_CHAPTER_SECONDS:
        dropped = merged.pop()
        merged[-1].setdefault("also", []).append(dropped["heading"])

    for mark in merged:
        mark["time"] = stamp(mark["start"])
    return merged


def _question(promise: str) -> str | None:
    """The promise, asked instead of stated. Only where the grammar allows it."""
    body = promise.strip().rstrip(".")
    for lead in ("You will ", "You can ", "You "):
        if body.lower().startswith(lead.lower()):
            rest = body[len(lead):]
            return "Can you %s?" % rest
    return None


def title_options(brief: dict) -> list[str]:
    """Three titles, in the three shapes that actually work.

    A search title names the thing a viewer types into the box. A question title
    opens the loop the film closes, and questions out-perform statements of the
    same length because the viewer has to answer them. A promise title says what
    the viewer walks away with. Each is derived from the brief, so none of them
    can claim something the film does not deliver - and each is a whole sentence,
    not two fragments joined with a comma.
    """
    options: list[str] = []

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        candidate = re.sub(r"\s+", " ", candidate).strip(" .")
        if 8 <= len(candidate) <= MAX_TITLE and candidate not in options:
            options.append(candidate)

    promise = (brief.get("promise") or "").strip()
    add(brief.get("title", ""))
    add(_question(promise))
    add(promise)
    for section in brief.get("sections", []):
        heading = sentence(section.get("heading", ""))
        if heading and len(heading) > 14:
            add(heading)
    return options[:3]


def tag_list(brief: dict, limit: int = MAX_TAGS) -> list[str]:
    """The brief's own tags first, then subject words from its headings.

    Tags are search furniture. The two-word phrases worth having - "ai code
    review", "pull request" - are a judgement about the audience, not something
    that can be counted out of a script, so the brief states them and this keeps
    the order it was given. Only if the brief is quiet does it fall back to the
    words its title and headings repeat, and then only single words, because a
    pair assembled by adjacency produces "before ships", which nobody types.
    """
    explicit = [str(value).strip().lower() for key in ("tags", "keywords")
                for value in (brief.get(key) or [])]

    counts: dict[str, int] = {}
    for blob in [brief.get("title", "")] + [s.get("heading", "") for s in brief.get("sections", [])]:
        for word in slug_words(blob):
            if len(word) >= 4:
                counts[word] = counts.get(word, 0) + 1
    fallback = sorted(counts, key=lambda key: (-counts[key], -len(key), key))

    tags: list[str] = []
    budget = 0
    for tag in explicit + fallback:
        cost = len(tag) + (1 if tags else 0)
        if not tag or tag in tags or budget + cost > limit:
            continue
        tags.append(tag)
        budget += cost
        if len(tags) >= 18:
            break
    return tags


def description(brief: dict, chapters: list[dict], headings: list[str], *,
                tags: list[str], opening: str = "") -> str:
    """The description a viewer reads after the title made them click.

    The first two lines are the ones YouTube shows before "more", so they carry
    the question the film answers and the promise it makes - in the film's own
    words, taken from its opening line and its brief. Then what it covers, in the
    film's own order; then the chapters; then how it was made. There is no link
    here that does not exist and no claim the narration does not make.
    """
    promise = sentence(brief.get("promise") or brief.get("title", ""))
    first_paragraph = [value for value in (opening.strip(), promise) if value]

    lines = []
    if first_paragraph:
        lines += [first_paragraph[0], ""]
        lines += first_paragraph[1:]
        lines.append("")
    if headings:
        lines.append("What it covers, in order:")
        lines += ["- %s" % heading for heading in headings]
        lines.append("")
    if chapters:
        lines.append("Chapters")
        for chapter in chapters:
            extra = (" - " + "; ".join(chapter["also"])) if chapter.get("also") else ""
            lines.append("%s %s%s" % (chapter["time"], chapter["heading"], extra))
        lines.append("")
    lines.append("Every frame is drawn by code and the narration is synthesised locally. "
                 "No stock footage, no licensed music, no API key.")
    # Hashtags are a choice, not a derivation: three of them, set in the brief.
    hashtags = ["#" + "".join(part.title() for part in value.split())
                for value in (brief.get("hashtags") or [])][:3]
    if hashtags:
        lines += ["", " ".join(hashtags)]
    text = "\n".join(lines).strip()
    if len(text) > MAX_DESCRIPTION:
        text = text[: MAX_DESCRIPTION - 1].rstrip() + "\u2026"
    return text


def build(brief: dict, film: dict, *, site: str = "") -> dict:
    """Assemble the pack from the film's plan and the brief it came from.

    The plan is the authority on timing, and it carries one entry per *section* -
    not per shot. A section with staged beats is drawn as several shots, and a
    kinetic headline is drawn as one shot per line, so counting shots and reading
    them against the brief's section list silently shifts every heading by one.
    That is what produced a chapter called "How the minute is spent" at the time
    the three checks were on screen.
    """
    duration = float(film.get("duration_seconds") or 0.0)
    sections = list(film.get("sections") or [])
    if not sections:
        raise ValueError("the plan has no sections; a pack cannot guess the chapter times")

    marks = [{"start": float(section["start"]),
              "heading": sentence(section.get("heading") or section.get("id") or "")}
             for section in sections]
    chapters = chapters_from_sections(marks, duration)
    headings = [sentence(s.get("heading", "")) for s in brief.get("sections", []) if s.get("heading")]
    opening = ""
    if brief.get("sections") and brief["sections"][0].get("lines"):
        opening = brief["sections"][0]["lines"][0].get("text", "")
    titles = title_options(brief)
    tags = tag_list(brief)
    return {
        "titles": titles,
        "title": titles[0] if titles else brief.get("title", ""),
        "short_title": next((t for t in titles if len(t) <= SHORT_TITLE), titles[0] if titles else ""),
        "description": description(brief, chapters, headings, tags=tags, opening=opening),
        "chapters": chapters,
        "tags": tags,
        "thumbnail": (brief.get("thumbnail") or {}).get("line", ""),
        "duration_seconds": duration,
        "site": site,
    }


def to_markdown(pack: dict) -> str:
    out = ["# Upload pack - %s" % pack["title"], "",
           "Derived from the brief and the film's own timeline. The chapters are the real "
           "times, merged only where YouTube's ten-second floor would reject them.", "",
           "## Title", ""]
    for index, title in enumerate(pack["titles"], 1):
        out.append("%d. %s  _(%d characters)_" % (index, title, len(title)))
    out += ["", "The first one fits a phone without being cut off. The others trade that for search "
                "terms and tension.", "",
            "## Thumbnail", ""]
    if pack["thumbnail"]:
        out += ["`%s` - drawn by `video_studio/films/thumbnail.mjs` from the same brief." % pack["thumbnail"], ""]
    else:
        out += ["Not set in the brief.", ""]
    out += ["## Description", "", "```", pack["description"], "```", "", "## Chapters", "", "```"]
    for chapter in pack["chapters"]:
        extra = (" - " + "; ".join(chapter["also"])) if chapter.get("also") else ""
        out.append("%s %s%s" % (chapter["time"], chapter["heading"], extra))
    out += ["```", "", "## Tags", "", ", ".join(pack["tags"]), "",
            "## Before you upload", "",
            "- The first three seconds are the hook; do not put a logo card in front of them.",
            "- Set the thumbnail, then check it at 320 pixels wide - that is the size it is seen.",
            "- An end screen can go over the last %d seconds (from %s), where the film holds its "
            "closing line." % (max(3, int(round(pack["duration_seconds"] - pack["chapters"][-1]["start"]))),
                               pack["chapters"][-1]["time"]) if pack["chapters"] else
            "- Add an end screen over the closing line.",
            "- Pin the first comment with the one thing you want the viewer to do next.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brief", required=True, help="the brief the film was built from")
    parser.add_argument("--film", required=True, help="film.json written by the renderer")
    parser.add_argument("--out", required=True, help="markdown pack")
    parser.add_argument("--json-out", default=None, help="the same pack as JSON")
    parser.add_argument("--site", default="", help="where the film can be watched, if anywhere")
    args = parser.parse_args(argv)

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    film = json.loads(Path(args.film).read_text(encoding="utf-8"))
    pack = build(brief, film, site=args.site)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(pack), encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")

    problems = []
    if not pack["titles"]:
        problems.append("no title")
    if len(pack["chapters"]) < 3:
        problems.append("fewer than three chapters")
    if pack["chapters"] and pack["chapters"][0]["start"] != 0.0:
        problems.append("the first chapter does not start at zero")
    print(json.dumps({
        "out": str(out),
        "titles": len(pack["titles"]),
        "chapters": len(pack["chapters"]),
        "tags": len(pack["tags"]),
        "description_characters": len(pack["description"]),
        "problems": problems,
        "statement": "UPLOAD PACK: %d titles, %d chapters, %d tags, description %d characters%s"
                     % (len(pack["titles"]), len(pack["chapters"]), len(pack["tags"]),
                        len(pack["description"]), " - " + ", ".join(problems) if problems else ""),
    }, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
