#!/usr/bin/env python3
"""The craft gate: does this film hold an audience, by the numbers?

`docs/youtube-craft.md` collects what the platform data says about hooks,
pacing, interrupts, captions and packaging. This module measures a film against
those rules. It reads only artifacts the pipeline already produces - the
narration script, the caption file and the film's own metadata - so it can run
before a frame is encoded and in CI without a browser.

Two design decisions worth stating:

* Every rule reports the number it measured, not just a verdict. A failing gate
  that says "pacing wrong" is an argument; one that says "mean beat 1.9s, sd
  0.31s, need sd >= 0.35 x mean" is a fix.
* Thresholds live in one dict, `LIMITS`, next to the craft note. Changing what
  the studio accepts is a visible edit with a source, not a magic number buried
  in a comparison.

Exit-code convention is the repo's: 0 clean, 1 a rule failed, 2 bad input.
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- thresholds -----------------------------------------------------------
# Each entry carries its unit and the section of docs/youtube-craft.md it comes
# from, so a reader can argue with the source rather than the code.
LIMITS = {
    # craft note s2 - the first three seconds are where the decision is made
    "hook_start_max_s": 3.0,          # first spoken claim
    "hook_words_max": 18,             # a hook is a sentence, not a paragraph
    "hook_seconds_max": 7.0,
    # craft note s2 - Studio's Intro key moment
    "intro_window_s": 30.0,
    "intro_words_min": 45,            # no slow throat-clearing in the window
    "intro_words_max": 105,           # and no auctioneer
    # craft note s3 - pacing
    "beat_max_s": 12.0,               # matches the composition gate
    "beat_mean_max_s": 6.0,
    # Proxy, not the rule: line starts only. The composition gate measures
    # the real cap (no composition held > 12 s); this catches a *spoken* lull.
    "beat_cadence_max_s": 8.0,
    "pause_max_s": 1.6,               # inside a section
    "section_pause_max_s": 3.0,       # between sections
    "variation_min_ratio": 0.35,      # sd / mean of beat length
    # craft note s3 - structural interrupts
    "interrupts_per_10min_min": 6,
    "interrupts_per_10min_max": 18,
    "interrupts_first_minute_min": 2,
    # craft note s6 - captions
    # 42 characters is the broadcast/Netflix caption line limit.
    "caption_chars_per_line_max": 42,
    "caption_lines_max": 2,
    "caption_read_cps": 18.0,         # adult captions: 17-20 cps (Netflix/BBC)
    "caption_min_s": 0.8,
    # craft note s5 - packaging
    "title_chars_max": 60,
    "title_promise_chars_max": 40,
    "thumb_words_min": 2,
    "thumb_words_max": 5,
    # craft note s8 - chapters
    "chapter_count_min": 4,
    "chapter_seconds_min": 10.0,
    # A short film is not a scaled-down long film: nine sections in under a
    # minute is dense by the per-ten-minutes measure and perfectly paced in the
    # edit, and nine chapters cannot each last ten seconds inside 52 of them.
    # Below this length the density rules are replaced by absolute ones.
    "short_form_seconds": 240.0,
    "short_chapter_seconds_min": 2.5,
    "short_chapter_count_max": 12,
    "short_interrupts_per_10min_max": 60,
}

# Spelling hacks a formant synthesiser invites and a viewer would read. Kept
# deliberately short: a long blocklist starts banning real words.
RESPELLING_HACKS = {
    "vee", "doubleyou", "double-you", "aitch", "jay", "kew", "eye-oh",
    "en-eye", "em-el", "ex-eye", "bee-eye", "tee-em", "arr-ess", "you-arr",
    "ess-cue-el", "jason", "sequel",
}
LETTER_SPELLOUT = re.compile(r"\b(?:[A-Za-z][-–/]){2,}[A-Za-z]\b")


@dataclass
class Rule:
    """One measured rule. `ok` is the verdict, `detail` is why."""

    id: str
    ok: bool
    detail: str
    value: float | int | str | None = None
    limit: float | int | str | None = None
    section: str = ""


@dataclass
class Report:
    rules: list[Rule] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def failures(self) -> list[Rule]:
        return [rule for rule in self.rules if not rule.ok]

    @property
    def passed(self) -> bool:
        return not self.failures

    def statement(self) -> str:
        lines = [f"craft gate: {'PASSED' if self.passed else 'FAILED'} "
                 f"({len(self.rules) - len(self.failures)}/{len(self.rules)} rules)"]
        for rule in self.rules:
            mark = "ok  " if rule.ok else "FAIL"
            lines.append(f"  {mark} {rule.id:<24} {rule.detail}")
        return "\n".join(lines)


# --- input ----------------------------------------------------------------

def load_script(path: Path) -> dict:
    """The narration script: {title?, promise?, lines:[{id, text, scene}]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"lines": data}
    if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
        raise ValueError(f"{path}: expected an object with a lines array")
    return data


def parse_timestamp(stamp: str) -> float:
    match = re.match(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})", stamp.strip())
    if not match:
        raise ValueError(f"bad timestamp {stamp!r}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def parse_srt(text: str) -> list[dict]:
    """Cues as [{start, end, text, lines}], whitespace-normalised."""
    cues: list[dict] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        rows = [row for row in block.split("\n") if row.strip()]
        if len(rows) < 2:
            continue
        if "-->" not in rows[1]:
            if len(rows) < 3 or "-->" not in rows[2]:
                continue
            rows = rows[1:]
        start_text, end_text = (part.strip() for part in rows[1].split("-->")[:2])
        body = [row.strip() for row in rows[2:] if row.strip()]
        if not body:
            continue
        cues.append({
            "start": parse_timestamp(start_text),
            "end": parse_timestamp(end_text),
            "lines": body,
            "text": " ".join(body),
        })
    return cues


def read_srt(path: Path) -> list[dict]:
    return parse_srt(Path(path).read_text(encoding="utf-8"))


# --- measurement ----------------------------------------------------------

def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def merge_cues(cues: list[dict], tolerance: float = 0.02) -> list[dict]:
    """Rejoin cues the caption writer split out of one spoken line.

    A long sentence becomes two or three caption cues that run back to back. For
    pacing we want the *line* the voice spoke, not the caption widget, so cues
    that touch (next start within `tolerance` of this end) are one beat.
    """
    merged: list[dict] = []
    for cue in sorted(cues, key=lambda item: item["start"]):
        if merged and cue["start"] - merged[-1]["end"] <= tolerance:
            merged[-1]["end"] = max(merged[-1]["end"], cue["end"])
            merged[-1]["text"] = (merged[-1]["text"] + " " + cue["text"]).strip()
            merged[-1]["lines"] = merged[-1]["lines"] + cue["lines"]
        else:
            merged.append({**cue, "lines": list(cue["lines"])})
    return merged


def _fingerprint(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())[:24]


def bind_lines(script: dict, cues: list[dict]) -> list[dict]:
    """Give every narration line its real start and end, from the captions.

    The script holds text and scene; the caption file holds time. They are bound
    by order after merging split cues, and the bind is *checked* against the
    words - a silent misalignment would make every pacing number wrong, so a
    mismatch raises instead of returning plausible nonsense.
    """
    lines = script.get("lines") or []
    if not lines:
        return []
    if all(line.get("end") for line in lines):
        return [dict(line) for line in lines]
    merged = merge_cues(cues)
    if len(merged) != len(lines):
        raise ValueError(
            f"cannot bind {len(lines)} narration lines to {len(merged)} caption beats; "
            "regenerate the captions from this script")
    bound = []
    for line, cue in zip(lines, merged):
        expected, got = _fingerprint(str(line.get("text") or "")), _fingerprint(cue["text"])
        if expected and got and expected[:12] != got[:12]:
            raise ValueError(
                f"line {line.get('id')} reads {expected[:12]!r} but its caption reads "
                f"{got[:12]!r}; the captions are from a different script")
        bound.append({**line, "start": cue["start"], "end": cue["end"]})
    return bound


def scene_chapters(lines: list[dict]) -> list[dict]:
    """Chapter marks from the narration: one per scene, at its first line.

    Returns [{scene, start}] in film order. A scene the script never spells out
    (no `scene` key) collapses into a single chapter rather than inventing one.
    """
    chapters: list[dict] = []
    seen: set[str] = set()
    for line in lines:
        scene = str(line.get("scene") or "film")
        if scene in seen:
            continue
        seen.add(scene)
        chapters.append({"scene": scene, "start": float(line.get("start") or 0.0)})
    return chapters


def analyse(script: dict, cues: list[dict], *, duration: float | None = None,
            title: str | None = None, thumbnail_text: str | None = None,
            promise: str | None = None) -> Report:
    """Measure a film's narration and captions against LIMITS."""
    lines = script.get("lines") or []
    caption_cues = sorted(cues, key=lambda cue: cue["start"])
    if not caption_cues and not any(line.get("end") for line in lines):
        raise ValueError("nothing to measure: no cues and no timed lines")

    # Beats are spoken lines; captions are the widgets that show them.
    timed = bind_lines(script, caption_cues) if lines else []
    beats = ([{"start": float(line["start"]), "end": float(line["end"]),
               "text": str(line.get("text") or "")} for line in timed]
             if timed else
             [{"start": cue["start"], "end": cue["end"], "text": cue["text"]}
              for cue in caption_cues])
    if not caption_cues:
        caption_cues = [{"start": beat["start"], "end": beat["end"], "text": beat["text"],
                         "lines": [beat["text"]]} for beat in beats]
    end_of_film = duration or max(beat["end"] for beat in beats)
    report = Report()

    # ---- hook
    first = beats[0]
    first_words = _words(first["text"])
    first_seconds = first["end"] - first["start"]
    report.rules.append(Rule(
        "hook-window", first["start"] <= LIMITS["hook_start_max_s"],
        f"first claim at {first['start']:.2f}s (max {LIMITS['hook_start_max_s']}s)",
        first["start"], LIMITS["hook_start_max_s"], "s2"))
    report.rules.append(Rule(
        "hook-length",
        first_words <= LIMITS["hook_words_max"] and first_seconds <= LIMITS["hook_seconds_max"],
        f"{first_words} words, {first_seconds:.2f}s "
        f"(max {LIMITS['hook_words_max']} / {LIMITS['hook_seconds_max']}s)",
        first_words, LIMITS["hook_words_max"], "s2"))

    # ---- Intro window: dense enough to promise, calm enough to follow
    window = LIMITS["intro_window_s"]
    intro_words = sum(_words(beat["text"]) for beat in beats if beat["start"] < window)
    report.rules.append(Rule(
        "intro-density",
        LIMITS["intro_words_min"] <= intro_words <= LIMITS["intro_words_max"],
        f"{intro_words} words in the first {window:.0f}s "
        f"(want {LIMITS['intro_words_min']}-{LIMITS['intro_words_max']})",
        intro_words, f"{LIMITS['intro_words_min']}-{LIMITS['intro_words_max']}", "s2"))

    # ---- pacing: beats and pauses
    gaps = []
    for previous, cue in zip(beats, beats[1:]):
        gap = cue["start"] - previous["end"]
        if gap > 0:
            gaps.append(gap)
    beat_lengths = [beat["end"] - beat["start"] for beat in beats]
    mean_beat = sum(beat_lengths) / len(beat_lengths)
    spread = _stdev(beat_lengths) / mean_beat if mean_beat else 0.0
    report.metrics.update({
        "cues": len(beats),
        "duration_s": round(end_of_film, 3),
        "first_claim_s": round(first["start"], 3),
        "intro_words": intro_words,
        "mean_beat_s": round(mean_beat, 3),
        "beat_sd_ratio": round(spread, 3),
        "longest_beat_s": round(max(beat_lengths), 3),
        "longest_gap_s": round(max(gaps), 3) if gaps else 0.0,
        "words_per_minute": round(
            sum(_words(beat["text"]) for beat in beats) / max(end_of_film, 1e-6) * 60.0, 1),
    })
    report.rules.append(Rule(
        "beat-max", max(beat_lengths) <= LIMITS["beat_max_s"],
        f"longest beat {max(beat_lengths):.2f}s (max {LIMITS['beat_max_s']})",
        round(max(beat_lengths), 2), LIMITS["beat_max_s"], "s3"))
    report.rules.append(Rule(
        "beat-mean", mean_beat <= LIMITS["beat_mean_max_s"],
        f"mean beat {mean_beat:.2f}s (max {LIMITS['beat_mean_max_s']})",
        round(mean_beat, 2), LIMITS["beat_mean_max_s"], "s3"))
    report.rules.append(Rule(
        "pacing-variation", spread >= LIMITS["variation_min_ratio"],
        f"sd/mean {spread:.2f} (min {LIMITS['variation_min_ratio']})",
        round(spread, 2), LIMITS["variation_min_ratio"], "s3"))
    longest_gap = max(gaps) if gaps else 0.0
    report.rules.append(Rule(
        "no-dead-air", longest_gap <= LIMITS["section_pause_max_s"],
        f"longest silence {longest_gap:.2f}s (max {LIMITS['section_pause_max_s']})",
        round(longest_gap, 2), LIMITS["section_pause_max_s"], "s3"))

    # Cue-to-cue cadence: a viewer must never wait more than N seconds for the
    # picture or the words to change.
    cadence = [cue["start"] - previous["start"] for previous, cue in zip(beats, beats[1:])]
    worst_cadence = max(cadence) if cadence else 0.0
    report.rules.append(Rule(
        "beat-cadence", worst_cadence <= LIMITS["beat_cadence_max_s"],
        f"slowest change every {worst_cadence:.2f}s (max {LIMITS['beat_cadence_max_s']})",
        round(worst_cadence, 2), LIMITS["beat_cadence_max_s"], "s3"))

    # ---- structural interrupts: scene changes
    chapters = scene_chapters(timed) if timed else []
    within = [chapter["start"] for chapter in chapters if chapter["start"] < end_of_film]
    per_ten_min = len(within) / max(end_of_film, 1e-6) * 600.0
    first_minute = len([start for start in within if start < 60.0])
    report.metrics.update({
        "interrupts": len(within),
        "interrupts_per_10min": round(per_ten_min, 2),
        "interrupts_first_minute": first_minute,
        "chapters": [{"scene": chapter["scene"], "start": round(chapter["start"], 3)}
                     for chapter in chapters],
    })
    short_form = end_of_film < LIMITS["short_form_seconds"]
    if chapters:
        if short_form:
            # A per-ten-minutes density has no meaning for a one-minute film: it
            # asks nine chapters in 51 seconds to be sparse. What matters here is
            # that no chapter outstays its welcome.
            section_lengths = [b["start"] - a["start"] for a, b in zip(chapters, chapters[1:])]
            section_lengths.append(end_of_film - chapters[-1]["start"])
            mean_section = sum(section_lengths) / len(section_lengths)
            report.metrics["mean_section_s"] = round(mean_section, 2)
            report.rules.append(Rule(
                "section-length", 3.0 <= mean_section <= 12.0,
                f"mean section {mean_section:.1f}s (want 3-12s for a short film)",
                round(mean_section, 1), "3-12", "s3"))
        else:
            report.rules.append(Rule(
                "interrupt-density",
                LIMITS["interrupts_per_10min_min"] <= per_ten_min <= LIMITS["interrupts_per_10min_max"],
                f"{per_ten_min:.1f} scene changes per 10 min "
                f"(want {LIMITS['interrupts_per_10min_min']}-{LIMITS['interrupts_per_10min_max']})",
                round(per_ten_min, 1),
                f"{LIMITS['interrupts_per_10min_min']}-{LIMITS['interrupts_per_10min_max']}", "s3"))
        report.rules.append(Rule(
            "interrupt-first-minute", first_minute >= LIMITS["interrupts_first_minute_min"],
            f"{first_minute} scene changes in the first minute "
            f"(min {LIMITS['interrupts_first_minute_min']})",
            first_minute, LIMITS["interrupts_first_minute_min"], "s3"))

        # ---- chapters, as YouTube will read them
        lengths = [b["start"] - a["start"] for a, b in zip(chapters, chapters[1:])]
        lengths.append(end_of_film - chapters[-1]["start"])
        report.rules.append(Rule(
            "chapter-count", len(chapters) >= LIMITS["chapter_count_min"],
            f"{len(chapters)} chapters (min {LIMITS['chapter_count_min']})",
            len(chapters), LIMITS["chapter_count_min"], "s8"))
        shortest = LIMITS["short_chapter_seconds_min"] if short_form else LIMITS["chapter_seconds_min"]
        report.rules.append(Rule(
            "chapter-length", min(lengths) >= shortest,
            f"shortest chapter {min(lengths):.1f}s (min {shortest})",
            round(min(lengths), 1), shortest, "s8"))
        report.rules.append(Rule(
            "chapters-from-zero", chapters[0]["start"] <= 3.5,
            f"first scene at {chapters[0]['start']:.2f}s (publishes as 00:00; max 3.5s)",
            round(chapters[0]["start"], 2), 3.5, "s8"))

    # ---- captions
    too_long = []
    too_short = []
    dirty = []
    for cue in caption_cues:
        for row in cue["lines"]:
            if len(row) > LIMITS["caption_chars_per_line_max"]:
                too_long.append(row)
        if len(cue["lines"]) > LIMITS["caption_lines_max"]:
            too_long.append(f"{len(cue['lines'])} lines: {cue['text'][:40]}")
        need = len(cue["text"]) / LIMITS["caption_read_cps"]
        if cue["end"] - cue["start"] < max(need, LIMITS["caption_min_s"]):
            too_short.append(cue["text"][:40])
        for word in re.findall(r"[A-Za-z][A-Za-z'-]*", cue["text"]):
            if word.lower() in RESPELLING_HACKS or LETTER_SPELLOUT.search(word):
                dirty.append(word)
    report.metrics["caption_problems"] = {
        "too_long": len(too_long), "too_short": len(too_short),
        "respellings": sorted(set(dirty))[:10],
    }
    report.rules.append(Rule(
        "caption-chars", not too_long,
        f"{len(too_long)} captions over {LIMITS['caption_chars_per_line_max']} chars/line"
        if too_long else f"all captions within {LIMITS['caption_chars_per_line_max']} chars/line",
        len(too_long), 0, "s6"))
    report.rules.append(Rule(
        "caption-read", not too_short,
        f"{len(too_short)} captions too fast to read" if too_short
        else f"all captions hold {LIMITS['caption_read_cps']:.0f} chars/s or slower",
        len(too_short), 0, "s6"))
    report.rules.append(Rule(
        "caption-clean", not dirty,
        f"spelling hacks in captions: {sorted(set(dirty))[:5]}" if dirty
        else "no phonetic respellings in captions",
        len(dirty), 0, "s6"))

    # ---- packaging
    resolved_title = title or script.get("title") or ""
    if resolved_title:
        report.rules.append(Rule(
            "title-length", len(resolved_title) <= LIMITS["title_chars_max"],
            f"title {len(resolved_title)} chars (max {LIMITS['title_chars_max']})",
            len(resolved_title), LIMITS["title_chars_max"], "s5"))
    resolved_thumb = thumbnail_text if thumbnail_text is not None else (script.get("thumbnail") or {}).get("line")
    if resolved_thumb:
        thumb_words = _words(resolved_thumb)
        report.rules.append(Rule(
            "thumb-words",
            LIMITS["thumb_words_min"] <= thumb_words <= LIMITS["thumb_words_max"],
            f"thumbnail says {thumb_words} words "
            f"(want {LIMITS['thumb_words_min']}-{LIMITS['thumb_words_max']})",
            thumb_words, f"{LIMITS['thumb_words_min']}-{LIMITS['thumb_words_max']}", "s5"))
    if promise and resolved_title:
        overlap = _promise_overlap(promise, resolved_title)
        report.rules.append(Rule(
            "title-promise", bool(overlap),
            f"title shares {overlap or 'no'} concrete words with the promise",
            ",".join(overlap), "s5"))

    return report


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "your",
    "you", "it", "is", "are", "be", "will", "this", "that", "how", "what", "no",
}


def _promise_overlap(promise: str, title: str) -> list[str]:
    """Concrete nouns both the promise and the title use - the promise kept."""
    words = {word.lower() for word in re.findall(r"[A-Za-z]{4,}", promise)}
    return sorted(word for word in words
                  if word not in STOPWORDS and word in title.lower())


def verify(script_path: Path, srt_path: Path | None = None, *, title: str | None = None,
           thumbnail_text: str | None = None, duration: float | None = None) -> Report:
    """Convenience wrapper: load the two files a film already has, measure them."""
    script = load_script(script_path)
    cues = read_srt(srt_path) if srt_path else []
    return analyse(script, cues, duration=duration, title=title or script.get("title"),
                   thumbnail_text=thumbnail_text, promise=script.get("promise"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Measure a film against the craft rules")
    parser.add_argument("--script", required=True, type=Path, help="narration script JSON")
    parser.add_argument("--srt", type=Path, help="caption file for the same film")
    parser.add_argument("--title", help="override the title to check")
    parser.add_argument("--thumbnail-text", help="words burned into the thumbnail")
    parser.add_argument("--duration", type=float, help="film length in seconds")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    try:
        report = verify(args.script, args.srt, title=args.title,
                        thumbnail_text=args.thumbnail_text, duration=args.duration)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"craft gate: bad input: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "passed": report.passed,
            "metrics": report.metrics,
            "rules": [{"id": rule.id, "ok": rule.ok, "detail": rule.detail,
                       "value": rule.value, "limit": rule.limit,
                       "section": rule.section} for rule in report.rules],
        }, indent=2))
    else:
        print(report.statement())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
