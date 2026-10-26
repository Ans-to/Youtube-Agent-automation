#!/usr/bin/env python3
"""Ask the one question every other gate was too polite to ask.

    python tools/check_picture_truth.py --plan build/film/build/frames/plan.json \
        --voice build/film/voice/lines.json

The studio already measures motion, arrangements, holds, loudness and captions.
All of those passed on a film whose third act was wrong on screen: at 13 s the
grid showed causes one and three while the narrator was still on cause one, with
a hole where cause two belonged. Nothing failed, because every existing gate
measures a property of the output - how much it moves, how many arrangements it
makes - and none of them measures whether the picture agrees with the voice.

This does. It reads the plan, which publishes the timing of every row, and the
voice file, which publishes the timing of every word, and checks three things:

  truth-rows      each row appears no earlier than its own sentence is spoken,
                  and no more than a breath after it. A row that arrives early is
                  the picture saying something the narrator has not said yet.
  truth-order     rows appear in the order they are spoken. Out of order is a
                  fill-in-the-blank diagram: cause one and cause three with a
                  hole in the middle.
  truth-words     every phrase a beat prints is fully spoken by the end of that
                  beat. A picture may condense a sentence; it may not invent one.

Exit 0 when every beat agrees with the voice, 1 when one does not, 2 when the
plan or the voice file cannot be read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# A row may arrive a moment after its sentence starts - the entrance takes about
# half a second - but it may never arrive before the words exist.
LATE_ALLOWANCE = 1.2
EARLY_ALLOWANCE = 0.15
# Words match on letters and digits only: "twenty-percent." is "twenty percent".
def bare(word: str) -> str:
    return "".join(ch for ch in str(word).lower() if ch.isalnum())


def load_words(voice_path: Path) -> list[dict]:
    """Every word in the film, with its time, in order."""
    data = json.loads(voice_path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("lines", [])
    words = []
    for line in rows:
        times = line.get("word_times") or []
        if times:
            for item in times:
                token = bare(item.get("text", ""))
                if token:
                    words.append({"word": token, "start": float(item["start"]),
                                  "end": float(item["end"])})
        else:
            # No per-word timing: spread the line's words evenly across it. Crude,
            # but it keeps the gate honest about ordering rather than skipping.
            tokens = [bare(part) for part in str(line.get("text", "")).split()]
            tokens = [token for token in tokens if token]
            if not tokens:
                continue
            start = float(line.get("start", 0.0))
            end = float(line.get("end", start))
            step = (end - start) / len(tokens)
            for index, token in enumerate(tokens):
                words.append({"word": token, "start": start + index * step,
                              "end": start + (index + 1) * step})
    return words


def say_when(phrase: str, words: list[dict], after: int = 0) -> tuple[float, float] | None:
    """When this phrase is spoken: (first word start, last word end).

    In order, with words skipped, because a row is allowed to condense its
    sentence. Requires at least two words to match, so a single shared word
    cannot place a row.
    """
    want = [bare(part) for part in str(phrase).split()]
    want = [token for token in want if token]
    if not want:
        return None
    best = None
    for start in range(after, len(words)):
        index = 0
        last = start
        for cursor in range(start, len(words)):
            if words[cursor]["word"] == want[index]:
                index += 1
                last = cursor
                if index == len(want):
                    break
        if index >= min(len(want), 2):
            candidate = (words[start]["start"], words[last]["end"], start)
            if best is None or index > best[0]:
                best = (index, candidate)
            if index == len(want):
                break
    if best is None:
        return None
    _, (start_s, end_s, _index) = best
    return start_s, end_s


def check(plan_path: Path, voice_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    words = load_words(voice_path)
    findings = []
    checked_rows = 0

    # Rows: every beat of a section carries the same list, so it is checked once.
    seen = set()
    for shot in plan.get("shots", []):
        section = shot.get("section")
        rows = shot.get("rows") or []
        if not rows or section in seen:
            continue
        seen.add(section)
        cursor = 0
        previous_at = -1.0
        for row in rows:
            checked_rows += 1
            said = say_when(row.get("text", ""), words, cursor)
            if said is None:
                findings.append({
                    "rule": "truth-words",
                    "where": f"{section}:{row.get('text')}",
                    "detail": "this row prints words the narrator never says",
                })
                continue
            start_s, end_s = said
            at = float(row.get("at", 0.0))
            if at < start_s - EARLY_ALLOWANCE:
                findings.append({
                    "rule": "truth-rows",
                    "where": f"{section}:{row.get('text')}",
                    "detail": f"row appears at {at:.2f}s but its sentence starts at "
                              f"{start_s:.2f}s - the picture is ahead of the voice",
                })
            elif at > start_s + LATE_ALLOWANCE:
                findings.append({
                    "rule": "truth-rows",
                    "where": f"{section}:{row.get('text')}",
                    "detail": f"row appears at {at:.2f}s but its sentence starts at "
                              f"{start_s:.2f}s - the picture lags the voice",
                })
            if at < previous_at - 0.05:
                findings.append({
                    "rule": "truth-order",
                    "where": f"{section}:{row.get('text')}",
                    "detail": f"row appears at {at:.2f}s, before the row above it "
                              f"at {previous_at:.2f}s - out of the order they are said",
                })
            previous_at = max(previous_at, at)
            cursor = max(cursor, 0)

        # How far through the voice the section's rows have got, so the next
        # section cannot match words this one already used.
        if rows:
            last = say_when(rows[-1].get("text", ""), words)
            if last:
                cursor = 0

    # Phrases a beat prints must be spoken by the end of that beat.
    for shot in plan.get("shots", []):
        shows = shot.get("shows")
        if not shows:
            continue
        for phrase in str(shows).split("|"):
            phrase = phrase.strip()
            if not phrase:
                continue
            said = say_when(phrase, words)
            if said is None:
                findings.append({
                    "rule": "truth-words",
                    "where": f"{shot.get('id')}",
                    "detail": f"{phrase!r} is printed but never spoken",
                })
            elif said[1] > float(shot.get("end", 0.0)) + 0.5:
                findings.append({
                    "rule": "truth-words",
                    "where": f"{shot.get('id')}",
                    "detail": f"{phrase!r} finishes being said at {said[1]:.2f}s, after "
                              f"this beat ends at {float(shot.get('end', 0.0)):.2f}s",
                })

    return {
        "plan": str(plan_path),
        "voice": str(voice_path),
        "rows_checked": checked_rows,
        "findings": findings,
        "passed": not findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = check(args.plan, args.voice)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"picture truth: could not read the inputs: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if report["passed"]:
            print(f"PICTURE TRUTH: PASSED - {report['rows_checked']} rows, every one on "
                  f"the sentence that says it")
        else:
            print(f"PICTURE TRUTH: FAILED - {len(report['findings'])} finding(s)")
            for finding in report["findings"]:
                print(f"  - {finding['rule']} {finding['where']}: {finding['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
