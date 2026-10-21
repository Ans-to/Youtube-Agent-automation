#!/usr/bin/env python3
"""Typography system: bundled professional faces, a real scale, kinetic type.

The brief says to use modern typefaces and never let text simply appear. This
module owns three things:

* which font files ship with the studio and under what licence;
* a per-resolution type scale with distinct primary/secondary/tertiary roles;
* the kinetic-type plan (stagger, mask reveal, anticipation, overshoot) that
  the renderer executes frame by frame.

Fonts are bundled as WOFF2 under ``video_studio/fonts`` so the renderer never
depends on whatever happens to be installed on the host.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

# family -> weight -> filename. These are the only faces the studio ships.
BUNDLED_FONTS: dict[str, dict[int, str]] = {
    "Inter": {
        400: "inter-latin-400-normal.woff2",
        500: "inter-latin-500-normal.woff2",
        600: "inter-latin-600-normal.woff2",
        700: "inter-latin-700-normal.woff2",
        800: "inter-latin-800-normal.woff2",
    },
    "Space Grotesk": {
        400: "space-grotesk-latin-400-normal.woff2",
        500: "space-grotesk-latin-500-normal.woff2",
        600: "space-grotesk-latin-600-normal.woff2",
        700: "space-grotesk-latin-700-normal.woff2",
    },
}

FONT_LICENSES = {
    "Inter": "SIL Open Font License 1.1",
    "Space Grotesk": "SIL Open Font License 1.1",
}

DISPLAY_STACK = '"Space Grotesk","Inter","Helvetica Neue",Arial,sans-serif'
TEXT_STACK = '"Inter","Helvetica Neue",Arial,sans-serif'
RTL_STACK = '"Noto Naskh Arabic","Noto Nastaliq Urdu","Nirmala UI",' + TEXT_STACK

# Never allowed anywhere in a compliant stack.
FORBIDDEN_FONTS = frozenset({"comic sans ms", "comic sans", "papyrus", "jokerman", "curlz mt"})

# Allowed as fallbacks only; a compliant stack must begin with a designed face.
DEFAULT_FONTS = frozenset({"arial", "helvetica", "times new roman", "calibri", "verdana"})

# Reference resolution for the scale. Everything is expressed relative to 1920 px
# of width so 4K doubles exactly instead of silently staying small.
REFERENCE_WIDTH = 1920

SCALE_RATIOS = {
    "display": 0.0688,
    "headline": 0.0458333,
    "subhead": 0.0230,
    "eyebrow": 0.0130,
    "body": 0.0180,
    "caption": 0.015625,
    "legal": 0.0100,
    "footer": 0.0105,
}

TRACKING_EM = {
    "display": -0.030,
    "headline": -0.020,
    "subhead": 0.000,
    "eyebrow": 0.140,
    "body": 0.005,
    "caption": 0.006,
    "legal": 0.010,
    "footer": 0.080,
}

LINE_HEIGHT = {
    "display": 1.02,
    "headline": 1.14,
    "subhead": 1.35,
    "eyebrow": 1.10,
    "body": 1.45,
    "caption": 1.30,
    "legal": 1.30,
    "footer": 1.10,
}

WEIGHT = {
    "display": 700,
    "headline": 700,
    "subhead": 400,
    "eyebrow": 600,
    "body": 400,
    "caption": 400,
    "legal": 400,
    "footer": 600,
}


@dataclass(frozen=True)
class TypeRole:
    name: str
    size_px: int
    weight: int
    tracking_em: float
    line_height: float

    def css(self, family: str = "Inter") -> str:
        return "%d %dpx/%s %s" % (self.weight, self.size_px, self.line_height, family)


def type_scale(width: int = 1920) -> dict[str, TypeRole]:
    """A full role scale for a canvas width. Doubles cleanly from 1080p to 4K."""
    if not isinstance(width, int) or width < 320 or width > 3840:
        raise ValueError("Type scale needs a canvas width between 320 and 3840")
    factor = width / REFERENCE_WIDTH
    scale = {}
    for role, ratio in SCALE_RATIOS.items():
        size = max(11, int(round(ratio * REFERENCE_WIDTH * factor)))
        scale[role] = TypeRole(role, size, WEIGHT[role], TRACKING_EM[role], LINE_HEIGHT[role])
    return scale


def hierarchy_report(width: int = 1920) -> dict:
    scale = type_scale(width)
    primary = scale["headline"].size_px
    secondary = scale["subhead"].size_px
    tertiary = scale["caption"].size_px
    micro = scale["legal"].size_px
    return {
        "display": scale["display"].size_px,
        "headline": primary,
        "subhead": secondary,
        "caption": tertiary,
        "legal": micro,
        "headline_over_subhead": round(primary / secondary, 2),
        "subhead_over_caption": round(secondary / tertiary, 2),
        "caption_over_legal": round(tertiary / micro, 2),
        "distinct": len({primary, secondary, tertiary, micro}) == 4,
        "minimum_legible_px": min(item.size_px for item in scale.values()),
    }


def hierarchy_issues(width: int = 1920) -> list[str]:
    report = hierarchy_report(width)
    issues = []
    if report["headline_over_subhead"] < 1.4:
        issues.append("Headline is not at least 1.4x the subhead")
    if report["subhead_over_caption"] < 1.2:
        issues.append("Subhead is not at least 1.2x the caption")
    if not report["distinct"]:
        issues.append("Type roles collapse to the same size")
    if report["minimum_legible_px"] < 11:
        issues.append("A type role is below 11 px at this resolution")
    return issues


def stack_issues(stack: str) -> list[str]:
    """Validate a CSS font stack against the pro spec."""
    families = [part.strip().strip("'\"") for part in str(stack).split(",") if part.strip()]
    issues = []
    if not families:
        return ["Empty font stack"]
    lowered = [family.lower() for family in families]
    for forbidden in FORBIDDEN_FONTS:
        if forbidden in lowered:
            issues.append("Forbidden typeface in stack: %s" % forbidden)
    if lowered[0] in DEFAULT_FONTS:
        issues.append("Stack starts with the system default %r instead of a designed face" % families[0])
    if not any(family in BUNDLED_FONTS for family in families):
        issues.append("Stack uses none of the bundled professional families")
    return issues


def available_fonts(font_dir: Path | None = None) -> dict:
    """Inventory of bundled font files, with missing files reported honestly."""
    root = Path(font_dir or FONT_DIR)
    inventory = {}
    missing = []
    for family, weights in BUNDLED_FONTS.items():
        present = {}
        for weight, filename in weights.items():
            path = root / filename
            if path.is_file() and path.stat().st_size > 0:
                present[weight] = {"file": filename, "bytes": path.stat().st_size}
            else:
                missing.append(str(path))
        inventory[family] = {"weights": present, "license": FONT_LICENSES[family]}
    return {
        "directory": str(root),
        "families": inventory,
        "missing": missing,
        "complete": not missing,
        "total_bytes": sum(
            item["bytes"] for family in inventory.values()
            for item in family["weights"].values()
        ),
    }


def font_face_css(relative_prefix: str = "fonts/") -> str:
    """@font-face rules for the bundled files. Paths stay relative to render.html."""
    rules = []
    for family, weights in BUNDLED_FONTS.items():
        for weight, filename in weights.items():
            rules.append(
                "@font-face{font-family:'%s';font-style:normal;font-weight:%d;"
                "font-display:block;src:url('%s%s') format('woff2');}"
                % (family, weight, relative_prefix, filename)
            )
    return "\n".join(rules)


def resolve_stack(role: str = "text", rtl: bool = False) -> str:
    if rtl:
        return RTL_STACK
    return DISPLAY_STACK if role == "display" else TEXT_STACK


def wrap_words(words: list[str], max_chars: int) -> list[list[str]]:
    lines: list[list[str]] = []
    current: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > max_chars:
            lines.append(current)
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        lines.append(current)
    return lines


def kinetic_plan(text: str, fps: int = 60, role: str = "headline",
                 max_words: int = 12) -> dict:
    """Per-word reveal timing for kinetic type.

    Words enter on a stagger, each with a mask reveal plus a small overshoot.
    The last word lands before the hold begins, so the line is readable before
    the shot starts to leave.
    """
    if not isinstance(fps, int) or not 1 <= fps <= 60:
        raise ValueError("Kinetic type needs an fps between 1 and 60")
    words = [word for word in str(text or "").split() if word]
    if not words:
        raise ValueError("Kinetic type needs at least one word")
    words = words[:max_words]

    stagger = max(1, round(fps * 0.055))
    entry_frames = max(6, round(fps * 0.34))
    overshoot = 0.035 if role in ("headline", "display") else 0.02
    anticipation_frames = max(2, round(fps * 0.06))

    items = []
    for index, word in enumerate(words):
        start = index * stagger
        items.append({
            "word": word,
            "start_frame": start,
            "end_frame": start + entry_frames,
            "anticipation_frames": anticipation_frames,
            "overshoot": overshoot,
            "mask": True,
            "direction": "up" if index % 2 == 0 else "up-slight",
        })
    span = items[-1]["end_frame"] if items else 0
    return {
        "fps": fps,
        "role": role,
        "words": items,
        "stagger_frames": stagger,
        "entry_frames": entry_frames,
        "settle_frame": span,
        "hold_seconds": round(max(0.6, span / fps * 1.2), 2),
        "reading_seconds": round(max(0.8, len(words) / 3.2), 2),
    }


def kinetic_issues(plan: dict) -> list[str]:
    issues = []
    if not plan.get("words"):
        issues.append("Kinetic plan contains no words")
    if plan.get("stagger_frames", 0) < 1:
        issues.append("Kinetic type has no stagger; all words would land together")
    if not all(word.get("mask") for word in plan.get("words", [])):
        issues.append("A word is not masked in; text would simply appear")
    if plan.get("settle_frame", 0) <= 0:
        issues.append("Kinetic type has no settle time")
    return issues


def seconds_to_frames(seconds: float, fps: int) -> int:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Frame conversion needs a finite non-negative duration")
    return max(1, int(round(seconds * fps)))
