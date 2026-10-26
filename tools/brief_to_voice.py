#!/usr/bin/env python3
"""Turn a video brief into the narration script the voiceover reads.

A brief holds the narration inside its sections, because that is where a person
writes it: one sentence per idea, next to the picture it belongs to. The
synthesiser wants the other shape - a flat list of lines with ids, a gap before
each one and a pause after - and it wants ids that are stable across edits,
because the picture is retimed to those ids.

So this tool is the adapter. It flattens, assigns ids in reading order, and sets
the two silences that matter: a short breath inside a section, a longer one
between sections. It writes nothing else and changes nothing; running it twice
on the same brief gives the same file.

    python tools/brief_to_voice.py --brief video_studio/briefs/review-ai-code.json \\
        --out build/review/voice-script.json

Exit codes: 0 written, 2 the brief is unusable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Silence, in seconds. Between sections is longer than inside one, and the film
# opens with a beat of air before the first claim so the frame is not talking
# before the viewer has looked at it.
# The gap before the first word. It used to be 1.15 seconds, which spent the
# opening of the hook - and, because the picture is cut from this timeline, the
# first twenty-six frames of the film - on a blank field.
LEAD_IN = 0.12
GAP_IN_SECTION = 0.42
GAP_BETWEEN_SECTIONS = 0.85
PAUSE_AFTER = 0.32
# Piper's mid-length read lands near 197 words per minute at rate 1.0, which is
# past the point a viewer starts skipping. 0.86 puts it in the 160-170 band the
# listening gate is calibrated for.
LINE_RATE = 0.82


def build(brief: dict) -> dict:
    sections = brief.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("the brief has no sections")
    lines = []
    counter = 0
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValueError(f"section {index + 1} is not an object")
        section_id = str(section.get("id") or f"section-{index + 1}")
        spoken = section.get("lines") or []
        if not spoken:
            raise ValueError(f"section {section_id} has no narration lines")
        for line_index, line in enumerate(spoken):
            text = str((line or {}).get("text") or "").strip()
            if not text:
                raise ValueError(f"section {section_id} line {line_index + 1} has no text")
            counter += 1
            line_id = str((line or {}).get("id") or f"L{counter:03d}")
            if index == 0 and line_index == 0:
                gap = LEAD_IN
            elif line_index == 0:
                gap = GAP_BETWEEN_SECTIONS
            else:
                gap = GAP_IN_SECTION
            lines.append({
                "id": line_id,
                "scene": section_id,
                "text": text,
                "gap_before": gap,
                "pause_after": PAUSE_AFTER,
                "rate": LINE_RATE,
            })
    return {
        "title": brief.get("title") or "Untitled",
        "promise": brief.get("promise"),
        "source": "tools/brief_to_voice.py",
        "lines": lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Brief -> narration script")
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        brief = json.loads(args.brief.read_text(encoding="utf-8"))
        script = build(brief)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"brief_to_voice: {error}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(script, indent=2) + "\n", encoding="utf-8")
    words = sum(len(str(line["text"]).split()) for line in script["lines"])
    seconds = words / 2.6
    print(f"{len(script['lines'])} lines, {words} words (~{seconds:.0f}s spoken) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
