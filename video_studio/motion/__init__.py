#!/usr/bin/env python3
"""Professional motion-graphics direction system.

Modules
-------
``curves``       cubic-Bezier easing, with linear explicitly rejected
``principles``   anticipation, squash/stretch, follow-through, hold windows
``palette``      tone palettes, WCAG contrast, grading
``typography``   bundled fonts, type scale, kinetic-type plans
``composition``  thirds, golden section, safe areas, negative space
``transitions``  the professional transition set and its legacy replacements
``camera``       moves, parallax, depth-of-field emulation, shake
``beat``         onset/tempo analysis and cue sheets
``direction``    brief -> direction sheet + render-ready storyboard
``compliance``   machine checks for every clause of the motion brief

The Python package is the source of truth. ``render.html`` mirrors the curve,
camera and transition tables so the visual result matches the direction sheet.
"""
from .curves import CURVES, curve, ease, is_linear_like, sample
from .palette import TONES, contrast_ratio, style_block, tone
from .transitions import PRO_TRANSITIONS, catalogue, frames_for, select, upgrade

__all__ = [
    "CURVES", "TONES", "PRO_TRANSITIONS",
    "curve", "ease", "is_linear_like", "sample",
    "tone", "style_block", "contrast_ratio",
    "catalogue", "frames_for", "select", "upgrade",
]
