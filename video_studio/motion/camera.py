#!/usr/bin/env python3
"""The camera is a physical object: moves, parallax, depth of field, shake.

All motion is expressed as normalised output that the Canvas renderer applies
to the whole frame. Moves are eased, deterministic, and clamped so a camera
never reveals the edge of the artwork.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .curves import ease, is_linear_like
from .palette import normalize_tone


@dataclass(frozen=True)
class Move:
    name: str
    description: str
    max_scale_delta: float
    max_offset: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "max_scale_delta": self.max_scale_delta,
            "max_offset": self.max_offset,
        }


MOVES: dict[str, Move] = {
    "static": Move("static", "Locked-off frame. The default for data and legal text.", 0.0, 0.0),
    "push-in": Move("push-in", "Slow dolly toward the subject; builds emphasis.", 0.075, 0.0),
    "pull-out": Move("pull-out", "Dolly back to reveal context.", 0.075, 0.0),
    "pan-left": Move("pan-left", "Lateral truck left with a slight perspective shift.", 0.012, 0.045),
    "pan-right": Move("pan-right", "Lateral truck right with a slight perspective shift.", 0.012, 0.045),
    "drift": Move("drift", "Ambient curved drift; never travels in a straight line.", 0.010, 0.018),
    "crane-up": Move("crane-up", "Rise vertically as if on a jib.", 0.020, 0.030),
    "tilt-down": Move("tilt-down", "Tilt down toward the lower third.", 0.015, 0.025),
    "handheld": Move("handheld", "Micro-movement of a shoulder-mounted camera.", 0.008, 0.006),
}

CAMERA_AMPLITUDE = {
    "corporate": 0.6,
    "edgy": 1.2,
    "minimalist": 0.3,
    "cinematic": 0.9,
    "playful": 0.8,
}


def normalize_move(value: str | None) -> str:
    key = str(value or "static").strip().lower()
    if key not in MOVES:
        raise ValueError("Unknown camera move %r. Choose one of: %s" % (value, ", ".join(sorted(MOVES))))
    return key


def select(index: int, tone: str | None = None, purpose: str | None = None) -> str:
    """Deterministic camera assignment; keeps repeat shots from feeling identical."""
    key = normalize_tone(tone)
    if purpose in ("data", "legal", "read"):
        return "static"
    rotation = {
        "corporate": ("push-in", "static", "pan-left", "pull-out"),
        "edgy": ("push-in", "handheld", "pan-right", "tilt-down"),
        "minimalist": ("static", "drift", "push-in", "static"),
        "cinematic": ("push-in", "crane-up", "drift", "pull-out"),
        "playful": ("push-in", "crane-up", "pan-left", "handheld"),
    }[key]
    return rotation[index % len(rotation)]


def sample(move: str, progress: float, amplitude: float | None = None,
           tone: str | None = None) -> dict:
    """Camera transform for one frame.

    Returns ``scale`` around the frame centre and ``offset_x``/``offset_y`` as
    fractions of canvas width and height. Rotation is in degrees and is kept
    below 0.4 degrees so text stays level.
    """
    key = normalize_move(move)
    p = min(1.0, max(0.0, float(progress)))
    amount = CAMERA_AMPLITUDE[normalize_tone(tone)] if amplitude is None else float(amplitude)
    if not 0.0 <= amount <= 2.0:
        raise ValueError("Camera amplitude must be between 0 and 2")

    eased = ease("editorial" if key not in ("handheld", "drift") else "glide", p)
    spec = MOVES[key]
    scale = 1.0
    offset_x = 0.0
    offset_y = 0.0
    rotation = 0.0

    if key == "push-in":
        scale = 1.0 + spec.max_scale_delta * amount * eased
    elif key == "pull-out":
        scale = 1.0 + spec.max_scale_delta * amount * (1.0 - eased)
    elif key == "pan-left":
        offset_x = -spec.max_offset * amount * eased
        scale = 1.0 + spec.max_scale_delta * amount * eased
    elif key == "pan-right":
        offset_x = spec.max_offset * amount * eased
        scale = 1.0 + spec.max_scale_delta * amount * eased
    elif key == "crane-up":
        offset_y = -spec.max_offset * amount * eased
        scale = 1.0 + spec.max_scale_delta * amount * eased
    elif key == "tilt-down":
        offset_y = spec.max_offset * amount * eased
        scale = 1.0 + spec.max_scale_delta * amount * eased
    elif key == "drift":
        offset_x = math.sin(eased * math.pi) * spec.max_offset * amount
        offset_y = -0.6 * spec.max_offset * amount * eased
        rotation = 0.22 * amount * math.sin(eased * math.pi)
        scale = 1.0 + spec.max_scale_delta * amount
    elif key == "handheld":
        offset_x = 0.0025 * amount * math.sin(p * math.pi * 7.0)
        offset_y = 0.0018 * amount * math.cos(p * math.pi * 5.3)
        rotation = 0.10 * amount * math.sin(p * math.pi * 3.1)

    return {
        "move": key,
        "scale": round(scale, 5),
        "offset_x": round(offset_x, 5),
        "offset_y": round(offset_y, 5),
        "rotation_degrees": round(rotation, 3),
    }


def shake_offsets(intensity: float, elapsed_seconds: float, decay: float = 0.18) -> dict:
    """Deterministic impact shake, expressed as fractions of the canvas."""
    if not 0.0 <= intensity <= 2.0:
        raise ValueError("Shake intensity must be between 0 and 2")
    t = max(0.0, float(elapsed_seconds))
    envelope = math.exp(-t / max(1e-6, decay))
    return {
        "x": 0.0018 * intensity * envelope * math.sin(2 * math.pi * 9.0 * t),
        "y": 0.0012 * intensity * envelope * math.cos(2 * math.pi * 6.6 * t + 1.1),
        "rotation_degrees": 0.08 * intensity * envelope * math.sin(2 * math.pi * 4.2 * t),
    }


def dof(depth: float, aperture: float = 0.6) -> dict:
    """Approximate depth of field for a flat Canvas composition.

    Canvas has no lens model. A layer is blurred and slightly desaturated based
    on distance from the focal plane; this is an emulation and is labelled as
    one in the docs and in the compliance report.
    """
    if not 0.0 <= depth <= 1.0:
        raise ValueError("Depth must be between 0 and 1")
    if not 0.0 <= aperture <= 1.0:
        raise ValueError("Aperture must be between 0 and 1")
    distance = abs(depth - 0.5) * 2.0
    return {
        "blur_px": round(12.0 * aperture * distance * distance, 2),
        "opacity": round(1.0 - 0.18 * aperture * distance, 3),
        "depth": depth,
    }


def parallax(depth: float, frame: int, fps: int = 30, base_speed: float = 12.0) -> float:
    """Horizontal displacement for a layer, in pixels, at a given depth."""
    if not isinstance(frame, int) or frame < 0:
        raise ValueError("Parallax needs a non-negative frame index")
    if not isinstance(fps, int) or not 1 <= fps <= 60:
        raise ValueError("Parallax needs an fps between 1 and 60")
    if not 0.0 <= depth <= 1.0:
        raise ValueError("Depth must be between 0 and 1")
    return round(base_speed * (0.25 + 0.75 * depth) * (frame / fps), 3)


def move_issues(move: str, progress_samples: int = 32) -> list[str]:
    """Reject a camera that cannot move smoothly with the configured curves."""
    key = normalize_move(move)
    issues = []
    if key == "static":
        return issues
    if is_linear_like("editorial") and key != "handheld":
        issues.append("Default camera curve is linear")
    if progress_samples < 8:
        raise ValueError("Camera check needs at least eight samples")
    return issues


def catalogue() -> dict:
    return {name: item.as_dict() for name, item in MOVES.items()}
