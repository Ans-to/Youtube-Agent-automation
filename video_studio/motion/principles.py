#!/usr/bin/env python3
"""Animation principles as testable functions.

The pro brief asks for anticipation, squash and stretch, follow-through and
overlapping action, breathing room, and a camera that behaves like a physical
object. Each of those is a numeric behaviour here, not a note in a document.
"""
from __future__ import annotations

import math

from .curves import ease

# Disney's twelve principles, mapped to what this studio can actually execute.
PRINCIPLES: dict[str, str] = {
    "squash_stretch": "Volume-preserving deformation for organic subjects only; never applied to corporate geometry.",
    "anticipation": "A short counter-move before the main action so the eye can predict it.",
    "staging": "One focal point per shot, on a thirds or golden-section intersection.",
    "straight_ahead": "Frame-by-frame procedural motion for ambient layers.",
    "pose_to_pose": "Deterministic keyframes for typography and layout.",
    "follow_through": "Secondary elements keep moving after the primary element stops.",
    "overlapping_action": "Layers start and stop at staggered times, never as one block.",
    "slow_in_slow_out": "Every entrance and exit is eased; constant velocity is rejected.",
    "arcs": "Camera drift and object paths curve rather than travel in a straight line.",
    "secondary_action": "Low-amplitude parallax and grain support the main move.",
    "timing": "Fast in, hold, fast out; hold duration is computed against reading speed.",
    "exaggeration": "Overshoot is bounded by tone: playful 8%, corporate 2%.",
    "solid_drawing": "Vector geometry with a consistent stroke and corner radius.",
    "appeal": "Palette, type hierarchy and negative space are checked, not assumed.",
}


def anticipate(progress: float, lead: float = 0.18, amount: float = 0.08) -> float:
    """Counter-move offset in normalised units.

    Returns 0 at rest, dips to ``-amount`` at ``lead``, returns to 0 by
    ``2 * lead``, and stays 0 for the main movement.
    """
    if not 0.0 <= lead <= 0.5:
        raise ValueError("Anticipation lead must be between 0 and 0.5")
    if not 0.0 <= amount <= 0.25:
        raise ValueError("Anticipation amount must be between 0 and 0.25")
    p = min(1.0, max(0.0, float(progress)))
    if p <= 0.0:
        return 0.0
    if p < lead:
        return -amount * ease("entrance", p / lead)
    if p < 2.0 * lead:
        return -amount * (1.0 - ease("editorial", (p - lead) / lead))
    return 0.0


def overshoot_settle(progress: float, amount: float = 1.0) -> float:
    """Eased value that crosses 1 and settles back. ``amount`` scales the overshoot."""
    if not 0.0 <= amount <= 2.0:
        raise ValueError("Overshoot amount must be between 0 and 2")
    base = ease("settle", progress)
    return 1.0 + (base - 1.0) * amount


def follow_through(progress: float, delay: float = 0.12, curve: str = "entrance") -> float:
    """Progress for a trailing element that starts later and lands later."""
    if not 0.0 <= delay < 1.0:
        raise ValueError("Follow-through delay must be between 0 and 1")
    p = min(1.0, max(0.0, float(progress)))
    if p <= delay:
        return 0.0
    return ease(curve, (p - delay) / (1.0 - delay))


def stagger_delays(count: int, gap: float = 0.06, cap: float = 0.5) -> list[float]:
    """Evenly staggered start offsets, clamped so nothing waits too long."""
    if count < 1:
        raise ValueError("Stagger needs at least one element")
    if not 0.0 <= gap <= 0.5:
        raise ValueError("Stagger gap must be between 0 and 0.5")
    gaps = [min(cap, index * gap) for index in range(count)]
    if gaps[-1] > 0:
        span = gaps[-1]
        gaps = [round(value / span, 6) for value in gaps]
    return gaps


def stagger_delays_frames(count: int, gap_frames: int = 3, cap_frames: int = 18) -> list[int]:
    """Frame-accurate stagger used by the renderer."""
    if count < 1:
        raise ValueError("Stagger needs at least one element")
    if not 0 <= gap_frames <= 30 or not 0 <= cap_frames <= 120:
        raise ValueError("Stagger frames must be within renderer limits")
    return [min(cap_frames, index * gap_frames) for index in range(count)]


def squash_stretch(velocity: float, amount: float = 0.08, allow: bool = False) -> tuple[float, float]:
    """Volume-preserving scale pair for organic subjects.

    Corporate and rigid graphics return (1, 1) regardless of velocity: the spec
    explicitly excludes squash and stretch from that visual language.
    """
    if not allow:
        return (1.0, 1.0)
    if not 0.0 <= amount <= 0.2:
        raise ValueError("Squash amount must be between 0 and 0.2")
    v = min(1.0, max(0.0, abs(float(velocity))))
    stretch = 1.0 + amount * v
    return (stretch, 1.0 / stretch)


def hold_window(duration_seconds: float, in_fraction: float = 0.18,
                out_fraction: float = 0.18) -> dict:
    """Split a shot into fast-in / hold / fast-out, the "breathing room" pattern."""
    if not (0.0 < in_fraction < 1.0 and 0.0 < out_fraction < 1.0):
        raise ValueError("Hold fractions must be between 0 and 1")
    if in_fraction + out_fraction >= 1.0:
        raise ValueError("Entrance and exit must leave time for a hold")
    duration = float(duration_seconds)
    if duration <= 0 or not math.isfinite(duration):
        raise ValueError("Shot duration must be finite and positive")
    return {
        "seconds": duration,
        "in": duration * in_fraction,
        "hold": duration * (1.0 - in_fraction - out_fraction),
        "out": duration * out_fraction,
        "in_fraction": in_fraction,
        "out_fraction": out_fraction,
        "hold_fraction": 1.0 - in_fraction - out_fraction,
    }


def phase_at(progress: float, window: dict) -> str:
    """Which part of the breathing-room window a progress value is in."""
    p = min(1.0, max(0.0, float(progress)))
    if p < window["in_fraction"]:
        return "in"
    if p < 1.0 - window["out_fraction"]:
        return "hold"
    return "out"


def impact_shake(elapsed_seconds: float, intensity: float = 1.0,
                 decay: float = 0.18, frequency: float = 9.0) -> tuple[float, float]:
    """Decaying deterministic camera shake for an impact moment.

    Returns normalised offsets in the range -intensity..intensity. No RNG: the
    same frame always shakes the same way.
    """
    if intensity < 0 or not math.isfinite(intensity):
        raise ValueError("Shake intensity must be finite and non-negative")
    t = max(0.0, float(elapsed_seconds))
    envelope = math.exp(-t / max(1e-6, decay))
    x = math.sin(2 * math.pi * frequency * t) * envelope * intensity
    y = math.cos(2 * math.pi * frequency * 0.73 * t + 1.1) * envelope * intensity * 0.6
    return (x, y)


def parallax_rate(depth: float, base: float = 1.0) -> float:
    """Motion multiplier for a layer at a given depth (0 = far, 1 = near)."""
    if not 0.0 <= depth <= 1.0:
        raise ValueError("Parallax depth must be between 0 and 1")
    return base * (0.25 + 0.75 * depth)


def reading_time_seconds(words: int, words_per_minute: int = 220) -> float:
    """Minimum readable dwell time for on-screen copy."""
    if words < 0 or words_per_minute < 80:
        raise ValueError("Reading time needs a positive word count and a sane reading speed")
    return max(0.8, (words / words_per_minute) * 60.0 * 1.35)
