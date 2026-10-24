#!/usr/bin/env python3
"""Write the subtitle track for a rendered film from the lines it was voiced from.

YouTube wants a subtitle file before a film goes up, and the cues have to agree
with what is on screen and with what the voice says. Both come from
``lines.json`` - the same file the voice stage used - so the track cannot drift
away from the read.

    python3 tools/film_subtitles.py /home/user/build/yt-film/voice/lines.json \\
        --srt film.srt --vtt film.vtt

A long line is split into short cues at word boundaries and timed by character
count inside the line's own start and end, because a 90-character cue is not
readable at 720p however long it stays on screen.

Exit codes: 0 both tracks written and validated, 1 the file cannot produce a
legal track (overlap, empty text, a synthesiser spelling), 2 bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from video_studio.captions import _stamp, _wrap_words, validate_subtitle_text  # noqa: E402
from check_narration import caption_hacks  # noqa: E402

MAX_CHARS = 42
MAX_LINES = 2
# Two characters per frame at 30 fps is about as fast as a cue can be replaced
# and still read; below this a cue is a flicker rather than a word.
MIN_CUE_SECONDS = 0.5


def load_lines(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(lines, list) or not lines:
        raise ValueError(f"{path} has no 'lines' array")
    return [line for line in lines if isinstance(line, dict)]


def _fits(words: list[str]) -> bool:
    return len(_wrap_words(" ".join(words), MAX_CHARS)) <= MAX_LINES


def _atoms(text: str) -> list[list[str]]:
    """Whole sentences where they fit, word by word where they do not.

    A cue that ends on a comma because the character budget ran out is a cue the
    reader has to re-read twice. Sentences are the natural break, so they are
    honoured first and only a sentence too long for two lines is broken by words.
    """
    atoms: list[list[str]] = []
    for sentence in re.split(r"(?<=[.!?;:])\s+", text):
        words = sentence.split()
        while words:
            if _fits(words):
                atoms.append(words)
                break
            cut = len(words) - 1
            while cut > 1 and not _fits(words[:cut]):
                cut -= 1
            atoms.append(words[:cut])
            words = words[cut:]
    for atom in atoms:
        for word in atom:
            if not _fits([word]):
                raise ValueError(f"the word {word!r} does not fit on screen in {MAX_LINES} lines")
    return atoms


def split_cue(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    """Break one spoken line into readable cues, timed by character count."""
    atoms = _atoms(" ".join(str(text).split()))
    if not atoms:
        return []
    # Join neighbouring sentences while both still fit, so a short line does not
    # turn into three flickering cues.
    chunks: list[list[str]] = [atoms[0]]
    for atom in atoms[1:]:
        if _fits(chunks[-1] + atom):
            chunks[-1] = chunks[-1] + atom
        else:
            chunks.append(atom)
    weights = [max(1, len(" ".join(chunk))) for chunk in chunks]
    total = sum(weights)
    cues = []
    elapsed = 0.0
    span = max(0.0, end - start)
    for chunk, weight in zip(chunks, weights):
        chunk_start = start + span * elapsed / total
        elapsed += weight
        chunk_end = start + span * elapsed / total
        if chunk_end - chunk_start < MIN_CUE_SECONDS and cues:
            # Too short to read: let it borrow the time from the cue before it.
            chunk_start = cues[-1][1]
        cues.append((chunk_start, chunk_end, " ".join(chunk)))
    return cues


def build_cues(lines: list[dict]) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for line in lines:
        text = " ".join(str(line.get("text") or "").split())
        if not text:
            continue
        try:
            start = float(line["start"])
            end = float(line["end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"line {line.get('id')!r} has no numeric start/end") from None
        if end <= start:
            raise ValueError(f"line {line.get('id')!r} ends before it starts")
        for chunk_start, chunk_end, chunk in split_cue(text, start, end):
            # Never let a cue run into the next one; an overlap is the one thing
            # a player cannot fix by itself.
            if cues and chunk_start < cues[-1][1]:
                chunk_start = cues[-1][1]
            if chunk_end - chunk_start < 0.05:
                continue
            cues.append((chunk_start, chunk_end, chunk))
    if not cues:
        raise ValueError("no cues: every line was empty")
    return cues


def wrap(text: str) -> str:
    lines = _wrap_words(text, MAX_CHARS)
    if len(lines) > MAX_LINES:
        raise ValueError(f"a cue of {len(text)} characters needs {len(lines)} lines")
    return "\n".join(lines)


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    parts = []
    for number, (start, end, text) in enumerate(cues, 1):
        parts.append(f"{number}\n{_stamp(start)} --> {_stamp(end)}\n{wrap(text)}\n")
    return "\n".join(parts).rstrip() + "\n"


def to_vtt(cues: list[tuple[float, float, str]]) -> str:
    parts = ["WEBVTT", ""]
    for start, end, text in cues:
        parts.append(f"{_stamp(start, '.')} --> {_stamp(end, '.')}\n{wrap(text)}\n")
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lines", help="the lines.json the voice stage used")
    parser.add_argument("--srt", default=None, help="where to write the SRT")
    parser.add_argument("--vtt", default=None, help="where to write the WebVTT")
    parser.add_argument("--language", default="en")
    args = parser.parse_args(argv)

    lines_path = Path(args.lines)
    if not lines_path.is_file():
        print(f"no such file: {lines_path}", file=sys.stderr)
        return 2

    hacks = caption_hacks(lines_path)
    if hacks:
        print("SUBTITLES: FAIL - the text still spells for a synthesiser:", file=sys.stderr)
        for hack in hacks:
            print(f"  {hack['id']}: {hack['text']!r} -> {hack['should_be']!r}", file=sys.stderr)
        return 1

    try:
        cues = build_cues(load_lines(lines_path))
    except ValueError as exc:
        print(f"SUBTITLES: FAIL - {exc}", file=sys.stderr)
        return 1

    try:
        srt, vtt = to_srt(cues), to_vtt(cues)
        validate_subtitle_text(srt, vtt, args.language)
    except ValueError as exc:
        print(f"SUBTITLES: FAIL - {exc}", file=sys.stderr)
        return 1

    srt_path = Path(args.srt) if args.srt else lines_path.with_suffix(".srt")
    vtt_path = Path(args.vtt) if args.vtt else lines_path.with_suffix(".vtt")
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    vtt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(srt, encoding="utf-8")
    vtt_path.write_text(vtt, encoding="utf-8")
    longest = max(len(text) for _, _, text in cues)
    print(f"SUBTITLES: PASS - {len(cues)} cues, longest {longest} characters")
    print(f"  {srt_path}")
    print(f"  {vtt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
