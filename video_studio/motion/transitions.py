#!/usr/bin/env python3
"""Editorial transitions: the professional set, and the ones it replaces.

The brief forbids PowerPoint-style Push, Wipe and Dissolve. Those names are
still accepted by the renderer so old storyboards do not break, but the
direction compiler upgrades them to a designed transition and the compliance
report names any that survive.

Every professional transition here has a physical idea behind it: a camera
whip, a matte with an edge, a shared object, a signal fault, or a match cut.
"""
from __future__ import annotations

from dataclasses import dataclass

from .palette import normalize_tone


@dataclass(frozen=True)
class Transition:
    name: str
    family: str
    default_seconds: float
    min_seconds: float
    max_seconds: float
    description: str
    physical_idea: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "family": self.family,
            "default_seconds": self.default_seconds,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "description": self.description,
            "physical_idea": self.physical_idea,
        }


PRO_TRANSITIONS: dict[str, Transition] = {
    "cut": Transition(
        "cut", "edit", 0.0, 0.0, 0.0,
        "Deliberate hard cut on a change of idea.",
        "An edit, not an effect. The strongest transition when the shot itself changes.",
    ),
    "whip-pan": Transition(
        "whip-pan", "camera", 0.30, 0.16, 0.45,
        "Fast horizontal camera whip with directional blur and a settled landing.",
        "A camera head turning so quickly the frame smears.",
    ),
    "masked-reveal": Transition(
        "masked-reveal", "matte", 0.55, 0.30, 0.80,
        "A shaped matte with a soft edge grows from the focal point and reveals the new shot.",
        "A physical card or iris opening over the lens.",
    ),
    "morph": Transition(
        "morph", "shape", 0.50, 0.30, 0.70,
        "Outgoing frame recedes and defocuses while the incoming frame resolves into place.",
        "One object becoming another through mass and focus, not a cross-fade.",
    ),
    "glitch": Transition(
        "glitch", "texture", 0.20, 0.10, 0.33,
        "RGB separation, slice displacement and a brief scanline tear.",
        "A digital signal fault at the cut.",
    ),
    "match-cut": Transition(
        "match-cut", "continuity", 0.45, 0.24, 0.70,
        "The shared graphic anchor carries across the cut while both frames scale through it.",
        "The eye holds one shape while the world changes around it.",
    ),
}

# Legacy aliases kept for backwards compatibility with existing storyboards.
LEGACY_TRANSITIONS = {
    "fade": "morph",
    "wipe-left": "masked-reveal",
    "wipe-right": "masked-reveal",
    "slide-left": "whip-pan",
    "slide-right": "whip-pan",
    "zoom": "match-cut",
    "push": "masked-reveal",
    "dissolve": "morph",
}

# Explicitly named in the negative constraints.
FORBIDDEN_TRANSITIONS = frozenset({"push", "wipe-left", "wipe-right", "dissolve"})
LEGACY_NAMES = frozenset(LEGACY_TRANSITIONS)

ALL_RENDERABLE = frozenset(PRO_TRANSITIONS) | LEGACY_NAMES


def normalize(name: str) -> str:
    key = str(name or "cut").strip().lower()
    if key not in ALL_RENDERABLE:
        raise ValueError(
            "Unknown transition %r. Professional set: %s"
            % (name, ", ".join(sorted(PRO_TRANSITIONS)))
        )
    return key


def upgrade(name: str, tone: str | None = None) -> str:
    """Map a legacy transition to its designed replacement."""
    key = normalize(name)
    if key in PRO_TRANSITIONS:
        return key
    replacement = LEGACY_TRANSITIONS[key]
    # Edgy and playful prefer the faster, harder option when both exist.
    if key in ("fade", "dissolve") and normalize_tone(tone) in ("edgy", "playful"):
        return "glitch"
    if key in ("slide-left", "slide-right"):
        return "whip-pan"
    return replacement


def select(index: int, tone: str | None = None, previous: str | None = None,
           purpose: str | None = None) -> str:
    """Deterministic editorial choice: varied, but never random and never repeated."""
    profile = {
        "corporate": ("masked-reveal", "match-cut", "cut", "morph"),
        "edgy": ("whip-pan", "glitch", "cut", "masked-reveal"),
        "minimalist": ("cut", "morph", "match-cut", "masked-reveal"),
        "cinematic": ("masked-reveal", "match-cut", "morph", "cut"),
        "playful": ("whip-pan", "masked-reveal", "morph", "glitch"),
    }[normalize_tone(tone)]
    if purpose in ("hard-reset", "aside"):
        return "cut"
    if purpose in ("impact", "reveal") and normalize_tone(tone) in ("edgy", "playful"):
        return "glitch"
    choice = profile[index % len(profile)]
    if previous and choice == previous:
        choice = profile[(index + 1) % len(profile)]
    return choice


def frames_for(name: str, fps: int, seconds: float | None = None) -> int:
    """Frame count for a transition, clamped to its designed range."""
    key = normalize(name)
    if not isinstance(fps, int) or not 1 <= fps <= 60:
        raise ValueError("Transition timing needs an fps between 1 and 60")
    if key == "cut":
        return 0
    item = PRO_TRANSITIONS.get(key)
    seconds = item.default_seconds if seconds is None else float(seconds)
    if item is not None:
        seconds = min(item.max_seconds, max(item.min_seconds, seconds))
    elif seconds <= 0:
        seconds = 0.35
    return max(1, min(60, int(round(seconds * fps))))


def plan_issues(transitions: list[str], *, allow_legacy: bool = False) -> list[str]:
    """Editorial checks for a whole transition plan."""
    issues = []
    names = [str(value).lower() for value in transitions]
    for index, name in enumerate(names):
        if name not in ALL_RENDERABLE:
            issues.append("Scene %d uses an unknown transition %r" % (index + 1, name))
        elif name in FORBIDDEN_TRANSITIONS and not allow_legacy:
            issues.append("Scene %d uses the forbidden template transition %r" % (index + 1, name))
    for index in range(2, len(names)):
        if names[index] == names[index - 1] == names[index - 2] and names[index] != "cut":
            issues.append("Transition %r repeats three times in a row" % names[index])
    if len(set(names)) == 1 and len(names) > 1:
        issues.append("Every scene uses the same transition; variation is required")
    return issues


def catalogue() -> dict:
    return {
        "professional": {name: item.as_dict() for name, item in PRO_TRANSITIONS.items()},
        "legacy": dict(LEGACY_TRANSITIONS),
        "forbidden": sorted(FORBIDDEN_TRANSITIONS),
    }
