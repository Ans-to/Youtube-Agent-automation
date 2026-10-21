"""Visual scene understanding: observations, temporal events, and vocabulary.

No model ships with this repository, and none may be downloaded from a paid API
(the North Star forbids it). Instead, local vision output enters through a small,
validated contract: an **observations JSON** file produced by whatever runs on
the operator's machine — a YOLO/ONNX detector, an InsightFace pass, a Tesseract
sweep, or a hand annotated review.

That keeps the auditor honest in both directions: it never pretends to see, and
it never refuses real evidence because it came from a tool this project does not
bundle.

Example::

    {
      "schema_version": 1,
      "provider": "yolo11n.onnx (local, CPU)",
      "observations": [
        {"start": 1.2, "end": 3.4, "kind": "object", "label": "knife", "confidence": 0.82},
        {"start": 1.0, "end": 4.0, "kind": "face", "label": "face", "confidence": 0.91,
         "box": [0.32, 0.12, 0.22, 0.28]},
        {"start": 2.0, "end": 5.0, "kind": "action", "label": "cooking", "confidence": 0.7},
        {"start": 0.0, "end": 9.0, "kind": "scene", "label": "kitchen", "confidence": 0.8}
      ]
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("object", "face", "action", "scene", "logo", "text")
MAX_OBSERVATIONS = 20_000
MAX_LABEL_LENGTH = 80

# Vocabulary used to map model labels onto audit rules.
WEAPON_LABELS = {
    "knife", "gun", "rifle", "pistol", "handgun", "shotgun", "sword", "blade",
    "weapon", "firearm", "grenade", "machete", "axe", "bow", "crossbow", "bomb",
}
VIOLENCE_ACTIONS = {
    "fight", "fighting", "punch", "punching", "kick", "kicking", "stabbing",
    "shooting", "strangle", "choking", "assault", "beating", "wrestling",
    "hitting", "slap", "slapping",
}
GORE_LABELS = {"blood", "gore", "corpse", "dead body", "injury", "wound", "burn"}
ADULT_LABELS = {
    "nudity", "nude", "explicit", "porn", "pornography", "sexual", "genitalia",
    "underwear", "lingerie", "topless",
}
CONTRABAND_LABELS = {
    "syringe", "cocaine", "heroin", "methamphetamine", "marijuana", "cannabis",
    "drugs", "pill", "bong", "vape", "pipe",
}
# Environments that make an otherwise alarming label mundane.
BENIGN_SCENES = {
    "kitchen", "restaurant", "cooking", "studio", "workshop", "classroom",
    "laboratory", "sports", "gym", "playground", "farm", "museum", "stage",
    "theatre", "theater", "set", "backstage", "tutorial", "interview",
}
# Labels describing benign handling of a cutting tool.
SAFE_TOOL_ACTIONS = {"cooking", "chopping", "slicing", "cutting food", "preparing food", "dicing"}


@dataclass(frozen=True)
class Observation:
    """One detector statement about one span of the video."""

    start: float
    end: float
    kind: str
    label: str
    confidence: float
    box: tuple[float, float, float, float] | None = None
    provider: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict:
        payload = {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "kind": self.kind,
            "label": self.label,
            "confidence": round(self.confidence, 3),
        }
        if self.box is not None:
            payload["box"] = [round(value, 4) for value in self.box]
        if self.provider:
            payload["provider"] = self.provider
        return payload


@dataclass
class TemporalEvent:
    """Consecutive observations of the same label, merged into one event."""

    kind: str
    label: str
    start: float
    end: float
    confidence: float
    observations: int = 1
    scenes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "confidence": round(self.confidence, 3),
            "observations": self.observations,
            "scenes": list(self.scenes),
        }


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"observation field '{name}' must be a number")
    return float(value)


def parse_observations(payload: object) -> tuple[list[Observation], str]:
    """Validate an observations document, returning (observations, provider)."""
    if not isinstance(payload, dict):
        raise ValueError("observations file must contain a JSON object")
    items = payload.get("observations")
    if not isinstance(items, list):
        raise ValueError("observations file must contain an 'observations' array")
    if len(items) > MAX_OBSERVATIONS:
        raise ValueError(f"observations file exceeds the {MAX_OBSERVATIONS}-entry limit")
    provider = str(payload.get("provider", ""))[:120]
    parsed: list[Observation] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"observation {index} must be an object")
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in KINDS:
            raise ValueError(f"observation {index} has unsupported kind '{kind}'")
        label = str(item.get("label", "")).strip()
        if not label or len(label) > MAX_LABEL_LENGTH:
            raise ValueError(f"observation {index} needs a label of 1-{MAX_LABEL_LENGTH} characters")
        start = _number(item.get("start"), "start")
        end = _number(item.get("end"), "end")
        if start < 0 or end < start:
            raise ValueError(f"observation {index} has an invalid time range")
        confidence = _number(item.get("confidence", 1.0), "confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"observation {index} confidence must be between 0 and 1")
        box_raw = item.get("box")
        box = None
        if box_raw is not None:
            if not isinstance(box_raw, list) or len(box_raw) != 4:
                raise ValueError(f"observation {index} box must be [x, y, width, height]")
            values = tuple(_number(value, "box") for value in box_raw)
            if any(value < 0 or value > 1 for value in values):
                raise ValueError(f"observation {index} box values must be normalized to 0..1")
            box = values  # type: ignore[assignment]
        parsed.append(Observation(
            start=start, end=end, kind=kind, label=label, confidence=confidence,
            box=box, provider=provider,
        ))
    return parsed, provider


def load_observations(path: str | Path) -> tuple[list[Observation], str]:
    """Read and validate an observations JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"observations file is not valid JSON: {exc.msg}") from exc
    return parse_observations(payload)


def build_events(observations: list[Observation], *, gap: float = 0.5) -> list[TemporalEvent]:
    """Merge consecutive same-label observations into events.

    This is the temporal layer: a single frame labelled ``knife`` is weak
    evidence, a knife present for four seconds while an action reads
    ``chopping`` is a different claim entirely.
    """
    grouped: dict[tuple[str, str], list[Observation]] = {}
    for observation in observations:
        if observation.kind == "face":
            continue
        grouped.setdefault((observation.kind, observation.label.lower()), []).append(observation)

    scenes = [
        (observation.start, observation.end, observation.label.lower())
        for observation in observations if observation.kind == "scene"
    ]
    events: list[TemporalEvent] = []
    for (kind, label), items in grouped.items():
        ordered = sorted(items, key=lambda item: item.start)
        run: list[Observation] = []
        for item in ordered:
            if run and item.start <= run[-1].end + gap:
                run.append(item)
            else:
                if run:
                    events.append(_event_from_run(kind, label, run, scenes))
                run = [item]
        if run:
            events.append(_event_from_run(kind, label, run, scenes))
    return sorted(events, key=lambda event: (event.start, event.kind, event.label))


def _event_from_run(kind: str, label: str, run: list[Observation], scenes) -> TemporalEvent:
    start = min(item.start for item in run)
    end = max(item.end for item in run)
    confidence = sum(item.confidence for item in run) / len(run)
    overlapping = sorted({
        scene_label for scene_start, scene_end, scene_label in scenes
        if scene_start < end and scene_end > start
    })
    return TemporalEvent(
        kind=kind, label=label, start=start, end=end,
        confidence=confidence, observations=len(run), scenes=tuple(overlapping),
    )


def scene_context(events: list[TemporalEvent], start: float, end: float) -> set[str]:
    """Scene labels overlapping a time span."""
    labels: set[str] = set()
    for event in events:
        if event.kind == "scene" and event.start < end and event.end > start:
            labels.add(event.label)
    return labels


def face_observations(observations: list[Observation]) -> list[Observation]:
    return [item for item in observations if item.kind == "face" and item.box is not None]


def mouth_motion_series(
    grid_motion: list[tuple[float, tuple[float, ...]]],
    faces: list[Observation],
    *,
    grid: int = 3,
) -> list[tuple[float, float]]:
    """Average motion inside the lower face box, per frame.

    The lower third of a face box is a mouth/jaw proxy: it moves when someone
    speaks and stays quiet when they do not. It is **not** viseme alignment, and
    the rule that consumes it says so.
    """
    if not grid_motion or not faces:
        return []
    series: list[tuple[float, float]] = []
    for time, cells in grid_motion:
        active = [
            face for face in faces
            if face.start <= time <= face.end and face.box is not None
        ]
        if not active:
            continue
        values: list[float] = []
        for face in active:
            x, y, width, height = face.box  # type: ignore[misc]
            mouth_top = y + height * 0.6
            for row in range(grid):
                for column in range(grid):
                    cell_x0, cell_x1 = column / grid, (column + 1) / grid
                    cell_y0, cell_y1 = row / grid, (row + 1) / grid
                    if cell_x1 <= x or cell_x0 >= x + width:
                        continue
                    if cell_y1 <= mouth_top or cell_y0 >= y + height:
                        continue
                    index = row * grid + column
                    if index < len(cells):
                        values.append(cells[index])
        if values:
            series.append((time, sum(values) / len(values)))
    return series
