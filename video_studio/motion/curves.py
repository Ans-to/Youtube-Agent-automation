#!/usr/bin/env python3
"""Cubic-Bezier motion curves: the only legal way an element may move.

The spec forbids linear interpolation. This module makes that mechanical rather
than aspirational: every named curve is a cubic Bezier with a documented
character, ``linear`` exists only so the validator can recognise and reject it,
and ``is_linear_like`` measures how close any sampled motion is to constant
velocity.

The JavaScript renderer mirrors this table in ``render.html``; the Python side
is the source of truth and is what the tests and the compliance report check.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Curve:
    """A cubic Bezier easing curve with control points in (x, y) pairs."""

    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    character: str

    def at(self, progress: float) -> float:
        return bezier_y_at_x(progress, self.x1, self.y1, self.x2, self.y2)


# Control points are CSS cubic-bezier values. Values outside 0..1 on the y axis
# are intentional: they are what produce overshoot and settle.
CURVES: dict[str, Curve] = {
    "editorial": Curve(
        "editorial", 0.65, 0.00, 0.35, 1.00,
        "Weighted ease-in-out. Default for graphic movement: accelerates late, "
        "decelerates long, never feels mechanical.",
    ),
    "entrance": Curve(
        "entrance", 0.16, 1.00, 0.30, 1.00,
        "Expo-style entrance. Very fast departure, long soft landing.",
    ),
    "exit": Curve(
        "exit", 0.70, 0.00, 0.84, 0.00,
        "Ease-in departure. Slow release, fast exit; the mirror of entrance.",
    ),
    "settle": Curve(
        "settle", 0.22, 1.35, 0.36, 1.00,
        "Back-out settle. Crosses the target, returns once, then holds. "
        "Used for accent marks and logo locks, never for body copy.",
    ),
    "snap": Curve(
        "snap", 0.40, 0.00, 0.20, 1.00,
        "UI snap. Near-instant response with a short decelerating tail.",
    ),
    "glide": Curve(
        "glide", 0.45, 0.05, 0.55, 0.95,
        "Slow, even-feeling drift for ambient background motion. Gentle "
        "acceleration and deceleration; still not linear.",
    ),
    "dramatic": Curve(
        "dramatic", 0.83, 0.00, 0.17, 1.00,
        "Very slow-in, very slow-out. For cinematic reveals and long holds.",
    ),
    # Present so the validator and the report can name what is forbidden.
    "linear": Curve(
        "linear", 0.00, 0.00, 1.00, 1.00,
        "Constant velocity. FORBIDDEN for element movement by the pro spec.",
    ),
}

FORBIDDEN_CURVES = frozenset({"linear"})
DEFAULT_CURVE = "editorial"

# Character-to-curve assignments. The direction compiler picks from this table;
# it never invents a curve at render time.
CURVE_ROLES: dict[str, str] = {
    "primary": "editorial",   # headline blocks, layout moves
    "entrance": "entrance",   # elements arriving
    "exit": "exit",           # elements leaving
    "accent": "settle",       # small marks that need character
    "ui": "snap",             # labels, counters, chips
    "ambient": "glide",       # background/parallax drift
    "cinematic": "dramatic",  # titles and hero statements
}


def _bezier_axis(t: float, a1: float, a2: float) -> float:
    """One axis of a cubic Bezier with endpoints fixed at 0 and 1."""
    u = 1.0 - t
    return 3.0 * u * u * t * a1 + 3.0 * u * t * t * a2 + t * t * t


def _bezier_slope(t: float, a1: float, a2: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * a1 + 6.0 * u * t * (a2 - a1) + 3.0 * t * t * (1.0 - a2)


def bezier_y_at_x(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Solve y for a given x on a cubic Bezier easing curve.

    Newton-Raphson with a bisection safeguard. The x axis is monotonic for
    control points with 0 <= x1, x2 <= 1, which every shipped curve satisfies.
    """
    if not (0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0):
        raise ValueError("Bezier x control points must be between 0 and 1")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    guess = x
    for _ in range(6):
        error = _bezier_axis(guess, x1, x2) - x
        if abs(error) < 1e-9:
            return _bezier_axis(guess, y1, y2)
        slope = _bezier_slope(guess, x1, x2)
        if abs(slope) < 1e-7:
            break
        guess -= error / slope
        if not 0.0 < guess < 1.0:
            guess = x
            break
    low, high = 0.0, 1.0
    for _ in range(48):
        mid = (low + high) * 0.5
        if _bezier_axis(mid, x1, x2) < x:
            low = mid
        else:
            high = mid
    t = (low + high) * 0.5
    return _bezier_axis(t, y1, y2)


def curve(name: str = DEFAULT_CURVE) -> Curve:
    key = str(name or "").strip().lower()
    if key not in CURVES:
        raise ValueError(
            "Unknown easing curve %r. Available: %s" % (name, ", ".join(sorted(CURVES)))
        )
    return CURVES[key]


def ease(name: str, progress: float) -> float:
    """Evaluate a named curve, clamped to its full range."""
    value = float(progress)
    if not math.isfinite(value):
        raise ValueError("Easing progress must be finite")
    return curve(name).at(min(1.0, max(0.0, value)))


def sample(name: str, count: int = 24) -> list[float]:
    """Sample a curve at ``count`` evenly spaced progress points, endpoints included."""
    if count < 2:
        raise ValueError("A curve sample needs at least two points")
    last = count - 1
    return [ease(name, index / last) for index in range(count)]


def velocity_profile(name: str, count: int = 48) -> list[float]:
    """Per-step velocity of a curve. Used to prove acceleration exists."""
    values = sample(name, count)
    return [values[i + 1] - values[i] for i in range(len(values) - 1)]


def is_linear_like(name: str, tolerance: float = 0.02, count: int = 64) -> bool:
    """True when the curve is constant velocity (within ``tolerance``).

    A pure linear curve deviates by 0. A curve that merely starts or ends fast
    still deviates from the straight line in the middle, so this is not a
    rounding-error test - it is a design test.
    """
    values = sample(name, count)
    last = count - 1
    deviation = max(abs(y - index / last) for index, y in enumerate(values))
    return deviation <= tolerance


def peak_overshoot(name: str, count: int = 256) -> float:
    """Maximum amount by which the curve passes beyond its target."""
    return max(0.0, max(sample(name, count)) - 1.0)


def is_monotonic(name: str, count: int = 256) -> bool:
    values = sample(name, count)
    return all(values[i + 1] >= values[i] - 1e-9 for i in range(len(values) - 1))


def describe(name: str) -> dict:
    """Machine-readable description used in direction sheets and reports."""
    item = curve(name)
    return {
        "name": item.name,
        "control_points": [item.x1, item.y1, item.x2, item.y2],
        "character": item.character,
        "linear": is_linear_like(item.name),
        "monotonic": is_monotonic(item.name),
        "peak_overshoot": round(peak_overshoot(item.name), 4),
    }
