#!/usr/bin/env python3
"""Voice production: the step between a text-to-speech model and a narration.

A neural model reads what it is given, in one breath. Hand it a twelve-word
sentence and it delivers one long, flat contour: every clause at the same speed,
no pause where the commas are, the same pitch fall whether the sentence is
ending or continuing. That is heard as "robotic" even when the voice itself is
good, and it is the reason a plain `piper` render sounds like a machine reading
a spreadsheet rather than a person explaining something.

This module does what a voice director would do to a raw take:

* **phrase it** - the line is split where a speaker would breathe, at sentence
  ends, commas, colons, semicolons and dashes, and each clause is synthesised on
  its own so the model gives it its own contour;
* **space it** - pauses go where the punctuation is, longer at the end of a
  sentence than inside one, and scaled to the length of the clause in front of
  them rather than to a fixed number;
* **shape the rate** - the last clause of a sentence lands slightly slower than
  the ones before it, which is the audible difference between a list and an
  argument;
* **rejoin it** - the pieces are faded, joined and trimmed so no click or hole
  is left between them.

Everything here is a pure function of the text and the model, so a film renders
the same audio every time. No network, no second model, no sampling.
"""
from __future__ import annotations

import re

import numpy as np

SAMPLE_RATE = 24000

# A speaker does not pause to the millisecond; these are the lengths that read
# as speech rather than as a machine waiting. They scale with the clause before
# them, because a long clause earns a longer breath than a two-word one.
PAUSE_SECONDS = {
    "sentence": 0.30,
    "colon": 0.19,
    "semicolon": 0.17,
    "dash": 0.16,
    "comma": 0.12,
}
PAUSE_SCALE_MAX = 1.45   # a long clause may stretch its pause by up to this
# The final clause of a sentence slows down a little. Below about 4% it is not
# audible; above about 10% it sounds like a different speaker.
FINAL_CLAUSE_RATE = 0.93
MID_CLAUSE_RATE = 0.985

SPLIT_AFTER = {
    ".": "sentence", "!": "sentence", "?": "sentence", "…": "sentence",
    ":": "colon", ";": "semicolon", "—": "dash", "–": "dash", ",": "comma",
}


def split_clauses(text: str) -> list[tuple[str, str]]:
    """Split a line into (clause, pause kind) pairs, keeping the punctuation.

    The punctuation stays on the clause: Piper's phonemiser uses it to decide the
    fall or rise of the phrase, so stripping it would flatten exactly the contour
    this module exists to create.
    """
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return []
    clauses: list[tuple[str, str]] = []
    buffer: list[str] = []
    for index, char in enumerate(cleaned):
        buffer.append(char)
        kind = SPLIT_AFTER.get(char)
        if not kind:
            continue
        # A decimal point (3.5) or an abbreviation (e.g.) is not a pause.
        previous = cleaned[index - 1] if index else ""
        following = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        if char == "." and (previous.isdigit() and following.isdigit()):
            continue
        if char == "." and following and following.isalpha() and previous.isalpha() and index:
            # "e.g." / "U.S." - a dot wedged between letters is not a stop.
            continue
        clause = "".join(buffer).strip()
        if clause:
            clauses.append((clause, kind))
        buffer = []
    tail = "".join(buffer).strip()
    if tail:
        clauses.append((tail, "sentence" if not clauses else ""))
    return clauses


def pause_for(kind: str, clause: str) -> float:
    """The silence after a clause: its punctuation, stretched for a long clause."""
    base = PAUSE_SECONDS.get(kind, 0.0)
    if base <= 0:
        return 0.0
    words = max(1, len(clause.split()))
    stretch = min(PAUSE_SCALE_MAX, 0.85 + words / 24.0)
    return base * stretch


def rate_for(index: int, total: int) -> float:
    """Per-clause pace. The last clause of a line lands rather than trails."""
    if total <= 1:
        return 1.0
    if index == total - 1:
        return FINAL_CLAUSE_RATE
    if index == 0:
        return 1.0
    return MID_CLAUSE_RATE


def _trim(signal: np.ndarray, rate: int, floor: float = 0.004, handle: float = 0.006):
    """Drop leading and trailing near-silence, keeping a short handle.

    The handle is deliberately short. It exists so the fade that follows has
    somewhere to start without shaving the first consonant, but a long handle
    puts the fade entirely inside silence, which is the same as having none.
    """
    if signal.size == 0:
        return signal
    envelope = np.abs(signal)
    audible = np.flatnonzero(envelope > floor)
    if audible.size == 0:
        return signal[:0]
    start = max(0, audible[0] - int(rate * handle))
    stop = min(signal.size, audible[-1] + int(rate * handle))
    return signal[start:stop]


def _fade(signal: np.ndarray, rate: int, ms: float = 8.0) -> np.ndarray:
    n = min(int(rate * ms / 1000), signal.size // 2)
    if n <= 0:
        return signal
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out = signal.copy()
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def assemble(clauses: list[tuple[str, str]], synth_clause, rate: int = SAMPLE_RATE) -> np.ndarray:
    """Synthesise each clause and join them with the pauses the punctuation asks for.

    `synth_clause(text, rate_multiplier)` returns a float32 mono buffer at `rate`.
    It is passed in rather than imported so this module stays testable without a
    model on the machine.
    """
    pieces: list[np.ndarray] = []
    total = len(clauses)
    for index, (clause, kind) in enumerate(clauses):
        audio = synth_clause(clause, rate_for(index, total))
        if audio is None or audio.size == 0:
            continue
        audio = _fade(_trim(np.asarray(audio, dtype=np.float32), rate), rate)
        if audio.size == 0:
            continue
        pieces.append(audio)
        gap = pause_for(kind, clause)
        if gap > 0 and index < total - 1:
            pieces.append(np.zeros(int(rate * gap), dtype=np.float32))
    if not pieces:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(pieces)


def synthesise_line(text: str, synth_clause, rate: int = SAMPLE_RATE) -> np.ndarray:
    """The whole production path for one narration line."""
    return assemble(split_clauses(text), synth_clause, rate=rate)
