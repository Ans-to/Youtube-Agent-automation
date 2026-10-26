#!/usr/bin/env python3
"""Write docs/ten-films.md from what the repository actually holds.

    python tools/ten_films_doc.py            # write the page
    python tools/ten_films_doc.py --check    # fail if the page is stale

Everything on the page comes from a file that is committed:

  video_studio/briefs/*.json          what each film was asked to argue
  docs/media/demos/<slug>.mp4         the 720p copy, and its size
  docs/media/demos/plans/<slug>.json  what each act drew and how it arrived
  docs/media/demos/plans/<slug>-craft.json   the eighteen craft rules

The page used to be assembled by a script kept outside the repository, which
meant it could not be regenerated from the repository alone - and after a machine
reset it could not be regenerated at all. If the page and the films disagree now,
`--check` says so.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "video_studio" / "briefs"
DEMOS = ROOT / "docs" / "media" / "demos"
PLANS = DEMOS / "plans"
PAGE = ROOT / "docs" / "ten-films.md"

# What each picture is for, in one clause. Kept here because the catalogue's own
# sentence is written for the chooser, not for a reader.
WHAT = {
    "kinetic-headline": "one spoken sentence, set as type that performs itself",
    "count-up": "a figure the script claims, counted out under its label",
    "list-build": "rows arriving one at a time, in reading order",
    "compare-pair": "two states held against each other, with a divider",
    "code-typing": "the line itself, typed with a caret",
    "bar-compare": "bars grown to their values, for a share of a whole",
    "sweep-rule": "a rule crossing the frame - punctuation, not information",
    "stack-push": "slabs stacking up, each arrival pushing the last",
    "fork-paths": "one thing splitting into two outcomes",
    "matrix-grid": "tiles that fill in the order they are spoken",
    "ring-gauge": "a dial sweeping to a claimed number",
    "budget-rail": "one span divided into the parts it is spent on",
    "stamp-lockup": "the closing phrase impressed on the frame",
    "command-console": "a window that types a command and shows it finish",
    "dot-gauge": "a proportion as countable dots, the lit ones being the part",
    "timeline-rail": "a sequence on one axis, each stop arriving with its words",
    "overlap-pair": "two things and the middle they share, hatched",
    "exploded-stack": "a whole taken apart into the layers it is made of",
}

ENTRANCE = {
    "draw-on": "drafted in from one side, a pen line at the edge",
    "wipe": "a hard horizontal reveal",
    "iris": "a circle opening on the subject",
    "scan": "a scanner band passes and the figure lands behind it",
    "highlighter": "a marker stroke behind a line of type",
    "slit-scan": "vertical strips snapping into place in waves",
    "whip": "sliding in with a short motion trail",
    "squash": "landing with squash and stretch",
    "stamp": "pressed on, overshooting then settling",
    "assembly": "two halves arriving from opposite sides and meeting",
}


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def films() -> list[dict]:
    out = []
    for path in sorted(BRIEFS.glob("*.json")):
        brief = load(path)
        slug = str(brief.get("slug") or path.stem)
        plan_path = PLANS / f"{slug}.json"
        craft_path = PLANS / f"{slug}-craft.json"
        mp4 = DEMOS / f"{slug}.mp4"
        out.append({
            "slug": slug,
            "brief": brief,
            "plan": load(plan_path) if plan_path.is_file() else None,
            "craft": load(craft_path) if craft_path.is_file() else None,
            "mb": round(mp4.stat().st_size / 1048576, 1) if mp4.is_file() else 0.0,
            "built": mp4.is_file(),
        })
    return out


def acts(plan: dict | None) -> list[dict]:
    """One row per act, in order: id, pictures, entrance, length."""
    if not plan:
        return []
    out, seen = [], set()
    for shot in plan.get("shots", []):
        section = shot["section"]
        if section in seen:
            continue
        seen.add(section)
        shots = [s for s in plan["shots"] if s["section"] == section]
        pictures, entrances = [], []
        for other in shots:
            name = str(other.get("template", "?"))
            if name not in pictures:
                pictures.append(name)
            kind = str(other.get("entrance") or "-")
            if kind not in entrances:
                entrances.append(kind)
        length = max(s["end"] for s in shots) - min(s["start"] for s in shots)
        out.append({
            "id": section,
            "pictures": pictures,
            "entrance": entrances[0] if entrances else "-",
            "seconds": round(length, 1),
        })
    return out


def sequence(film: dict) -> tuple[str, ...]:
    return tuple(str(section.get("template")) for section in film["brief"].get("sections", [])
                 if section.get("template"))


def table(films_: list[dict]) -> str:
    head = ("| film | length | acts | craft | review copy |\n|---|---|---|---|---|\n")
    rows = []
    for film in films_:
        brief = film["brief"]
        plan = film["plan"] or {}
        seconds = plan.get("duration_seconds")
        length = f"{float(seconds):.1f} s" if seconds else "-"
        n = len(acts(film["plan"]))
        craft = film["craft"] or {}
        rules = craft.get("rules") or []
        passed = sum(1 for rule in rules if rule.get("ok"))
        craft_cell = f"{passed}/{len(rules)}" if rules else "-"
        if film["built"]:
            copy = f"[mp4](media/demos/{film['slug']}.mp4) - {film['mb']} MB"
        else:
            copy = "not rendered yet"
        rows.append(f"| [{brief['title']}](media/demos/{film['slug']}.mp4) "
                    f"| {length} | {n} | {craft_cell} | {copy} |")
    return head + "\n".join(rows)


def vocabulary(films_: list[dict]) -> str:
    used: dict[str, list[str]] = {}
    for film in films_:
        for act in acts(film["plan"]):
            for picture in act["pictures"]:
                used.setdefault(picture, []).append(film["slug"])
    entrances: dict[str, list[str]] = {}
    for film in films_:
        for act in acts(film["plan"]):
            if act["entrance"] != "-":
                entrances.setdefault(act["entrance"], []).append(film["slug"])
    rows = []
    for name, slugs in sorted(used.items(), key=lambda kv: (-len(set(kv[1])), kv[0])):
        unique = list(dict.fromkeys(slugs))
        rows.append(f"| `{name}` | {WHAT.get(name, '')} | {len(unique)} | {', '.join(unique)} |")
    entrance_rows = []
    for name, slugs in sorted(entrances.items(), key=lambda kv: (-len(set(kv[1])), kv[0])):
        unique = list(dict.fromkeys(slugs))
        entrance_rows.append(f"| `{name}` | {ENTRANCE.get(name, '')} | {len(unique)} |")
    return ("| picture | what it draws | films | which |\n|---|---|---|---|\n"
            + "\n".join(rows)
            + "\n\n| entrance | how the picture lands | films |\n|---|---|---|\n"
            + "\n".join(entrance_rows))


def per_film(film: dict) -> str:
    brief = film["brief"]
    rows = acts(film["plan"])
    if rows:
        table_rows = "\n".join(
            f"| {act['id']} | {' > '.join(f'`{p}`' for p in act['pictures'])} "
            f"| `{act['entrance']}` | {act['seconds']} s |"
            for act in rows)
        schedule = ("| act | picture | entrance | length |\n|---|---|---|---|\n" + table_rows)
    else:
        schedule = "*This film has not been rendered, so there is no schedule yet.*"
    craft = film["craft"] or {}
    failing = [rule for rule in craft.get("rules") or [] if not rule.get("ok")]
    craft_note = ""
    if failing:
        craft_note = ("\n**Craft rules failing:** "
                      + "; ".join(f"{rule.get('id')}: {rule.get('detail')}" for rule in failing)
                      + "\n")
    links = [f"[watch](media/demos/{film['slug']}.mp4)",
             f"[captions](media/demos/{film['slug']}.srt)",
             f"[contact sheet](media/demos/{film['slug']}-contact-sheet.jpg)",
             f"brief `video_studio/briefs/{film['slug']}.json`"]
    return (f"### {brief['title']}\n\n*{brief.get('promise', '')}*\n\n"
            f"{' - '.join(links)}\n\n{schedule}\n{craft_note}")


def build() -> str:
    films_ = films()
    built = [film for film in films_ if film["built"]]
    sequences = {sequence(film) for film in films_ if sequence(film)}
    shared = len(films_) - len(sequences)

    opening = f"""# Ten one-minute films, each built for its own script

Ten scripts, ten renders, ten different structures. The point of the page is not
that the studio can make ten films - it can - but that each film argues the way
its own script argues.

The first batch passed every gate and was still wrong: **"you are using the same
template for every video... every video is should have the template which is
compatible with the script, not copy paste one template on every video."** That
was accurate. Ten scripts had been poured into one skeleton, and every gate
passed, because a gate measures a film against the rules and a film can follow
every rule while looking like the last one.

So the acts were rebuilt from each argument. This page is generated from the
briefs, the plans and the renders that sit in this repository -
`python tools/ten_films_doc.py` - so it cannot drift from them. Of the
{len(films_)} films here, {len(sequences)} have their own act sequence
({shared} share one with another film).

## The ten

{table(films_)}

Every film is 1280x720, 30 fps, H.264 High with AAC at 48 kHz, `+faststart`, and
loudness-normalised for YouTube. *Craft* is how many of the eighteen rules in
`video_studio/craft.py` pass; a dash means the report has not been published yet.

## The vocabulary

Two things make a picture: what is drawn, and how it lands. The studio has both,
and each is chosen by the beat, not by habit.

{vocabulary(films_)}

The entrances are ports of motion basics from
[howardc38/motion-fx-lab](https://github.com/howardc38/motion-fx-lab) (0BSD):
stroke reveals, clip wipes, iris openings, slit-scan strips, press and squash,
exploded assembly. `FITS` in `video_studio/motion/fxlab.mjs` records which
entrance each picture can carry, so a highlighter band is never drawn across a
dial, and an act never lands the same way as the act before it.

## How these were rendered

On GitHub, by a standard `ubuntu-24.04` runner, for nothing:
`.github/workflows/ten-films.yml` renders every brief in `video_studio/briefs` as
its own matrix job, runs the preflight and the craft gate on each, and then a
publish job commits the 720p copies, the captions and the contact sheets into
`docs/media/demos`. The renders are committed because a render that only exists
in a temporary directory is not a deliverable - that mistake cost a full batch.

To re-render one film, either run that workflow with `films` set to the slug, or
do it locally:

```bash
python tools/preflight_brief.py --brief video_studio/briefs/<slug>.json
python tools/brief_to_voice.py --brief video_studio/briefs/<slug>.json --out build/voice.json
python tools/render_authored_film.py \\
  --script video_studio/films/from_brief.mjs \\
  --script-args "--brief video_studio/briefs/<slug>.json" \\
  --voice-script build/voice.json --voice-backend kokoro --voice am_michael \\
  --out build/<slug> --width 1920 --height 1080 --delivery-height 720 --skip-4k
```

## The films, one by one

"""
    return opening + "\n".join(per_film(film) for film in films_)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed page differs from what is built")
    args = parser.parse_args(argv)
    page = build()
    if args.check:
        current = PAGE.read_text(encoding="utf-8") if PAGE.is_file() else ""
        if current.strip() != page.strip():
            print("docs/ten-films.md is stale: run python tools/ten_films_doc.py",
                  file=sys.stderr)
            return 1
        print("docs/ten-films.md is up to date")
        return 0
    PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {PAGE.relative_to(ROOT)} ({len(page.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
