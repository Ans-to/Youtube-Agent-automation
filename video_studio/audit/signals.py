"""Signal containers and small time-series helpers.

The auditor never touches video directly. It reasons over a :class:`MediaSignals`
value, which makes every detector a pure function over numbers and text — fast to
test, deterministic, and independent of whether FFmpeg, OCR, or ASR are installed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Interval:
    """A half-open time range in seconds."""

    start: float
    end: float
    label: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
        }


@dataclass(frozen=True)
class TranscriptCue:
    """One span of spoken (or subtitle) text."""

    start: float
    end: float
    text: str
    confidence: float | None = None
    source: str = "provided"


@dataclass(frozen=True)
class TextBlock:
    """One span of on-screen text detected by OCR."""

    start: float
    end: float
    text: str
    confidence: float = 1.0
    height_ratio: float = 0.0
    contrast: float | None = None


@dataclass
class MediaSignals:
    """Everything the detectors are allowed to know about a video."""

    duration: float = 0.0
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    luminance: list[tuple[float, float]] = field(default_factory=list)
    peak_luminance: list[tuple[float, float]] = field(default_factory=list)
    motion: list[tuple[float, float]] = field(default_factory=list)
    red_level: list[tuple[float, float]] = field(default_factory=list)
    audio_rms: list[tuple[float, float]] = field(default_factory=list)
    audio_window: float = 0.1
    silence: list[Interval] = field(default_factory=list)
    transcript: list[TranscriptCue] = field(default_factory=list)
    ocr: list[TextBlock] = field(default_factory=list)
    competitor_terms: list[str] = field(default_factory=list)
    music_detected: bool | None = None
    music_confidence: float = 0.0
    audio_profile: object | None = None
    observations: list = field(default_factory=list)
    mouth_motion: list[tuple[float, float]] = field(default_factory=list)
    grid_motion: list[tuple[float, tuple[float, ...]]] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # -- evidence availability -------------------------------------------
    def has(self, signal: str) -> bool:
        """True when at least one usable sample exists for the named signal."""
        if signal == "luminance":
            return len(self.luminance) >= 2
        if signal == "motion":
            return len(self.motion) >= 2
        if signal == "red_level":
            return len(self.red_level) >= 2
        if signal == "audio_rms":
            return len(self.audio_rms) >= 2
        if signal == "silence":
            return bool(self.silence) or self.has("audio_rms")
        if signal == "transcript":
            return any(cue.text.strip() for cue in self.transcript)
        if signal in {"ocr", "disclosure_text"}:
            return bool(self.ocr)
        if signal == "competitor_terms":
            return bool(self.competitor_terms)
        if signal == "music":
            return self.music_detected is not None
        if signal == "audio_profile":
            return bool(self.audio_profile is not None and getattr(self.audio_profile, "frames", None))
        if signal == "vision":
            return bool(self.observations)
        if signal == "faces":
            return any(getattr(item, "kind", "") == "face" and getattr(item, "box", None) for item in self.observations)
        if signal == "mouth_motion":
            return len(self.mouth_motion) >= 5
        return False

    def missing(self, required: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(name for name in required if not self.has(name))

    def transcript_text(self) -> str:
        return " ".join(cue.text for cue in self.transcript)

    def ocr_text(self) -> str:
        return " ".join(block.text for block in self.ocr)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS, clamping negatives to zero."""
    total = int(max(0.0, math.floor(float(seconds) + 1e-6)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_interval(start: float, end: float) -> str:
    return f"[{format_timestamp(start)} - {format_timestamp(max(start, end))}]"


def merge_intervals(intervals: list[Interval], gap: float = 0.0) -> list[Interval]:
    """Merge overlapping or near-adjacent intervals, preserving the first label."""
    ordered = sorted((item for item in intervals if item.end > item.start), key=lambda item: item.start)
    merged: list[Interval] = []
    for item in ordered:
        if merged and item.start <= merged[-1].end + gap:
            previous = merged[-1]
            merged[-1] = Interval(previous.start, max(previous.end, item.end), previous.label or item.label)
        else:
            merged.append(item)
    return merged


def interval_covering(start: float, end: float) -> Interval:
    return Interval(max(0.0, start), max(start, end))


# ---------------------------------------------------------------------------
# Series helpers (deliberately dependency-free: no numpy in the base install)
# ---------------------------------------------------------------------------

def resample(series: list[tuple[float, float]], step: float, duration: float) -> list[float]:
    """Nearest-neighbour resample a (time, value) series onto a uniform grid."""
    if step <= 0:
        raise ValueError("step must be positive")
    count = max(1, int(math.floor(duration / step)))
    if not series:
        return [0.0] * count
    ordered = sorted(series, key=lambda item: item[0])
    values = [0.0] * count
    index = 0
    for position in range(count):
        target = position * step
        while index + 1 < len(ordered) and ordered[index + 1][0] <= target:
            index += 1
        values[position] = float(ordered[index][1])
    return values


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def normalize(values: list[float]) -> list[float]:
    """Scale to 0..1; a flat series becomes all zeros rather than dividing by zero."""
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return [0.0] * len(values)
    return [(value - low) / (high - low) for value in values]


def correlation(left: list[float], right: list[float]) -> float:
    """Pearson correlation of two equal-length series; 0.0 when either is flat."""
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    a, b = left[:size], right[:size]
    mean_a, mean_b = mean(a), mean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=False))
    denom_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    denom_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if denom_a < 1e-9 or denom_b < 1e-9:
        return 0.0
    return numerator / (denom_a * denom_b)


def shift(values: list[float], offset: int) -> list[float]:
    """Shift a series by ``offset`` samples, padding with zeros."""
    if offset == 0:
        return list(values)
    if offset > 0:
        return [0.0] * min(offset, len(values)) + list(values)[: max(0, len(values) - offset)]
    return list(values)[-offset:] + [0.0] * min(-offset, len(values))


def best_lag(
    reference: list[float],
    target: list[float],
    step: float,
    max_seconds: float = 0.5,
) -> tuple[float, float]:
    """Return (lag_seconds, correlation) for the best alignment of target to reference.

    A positive lag means the target tracks the reference *late*, i.e. the picture
    lags the sound.
    """
    if not reference or not target:
        return 0.0, 0.0
    max_samples = max(1, int(round(max_seconds / step)))
    best_offset, best_score = 0, -2.0
    for offset in range(-max_samples, max_samples + 1):
        score = correlation(reference, shift(target, offset))
        if score > best_score + 1e-12:
            best_offset, best_score = offset, score
    # ``shift`` delays the target, so a positive offset that aligns them means the
    # target was originally early. Report the target's lateness with a positive sign.
    return -best_offset * step, best_score
