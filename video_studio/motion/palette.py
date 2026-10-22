#!/usr/bin/env python3
"""Art-direction palettes with measurable contrast.

Every tone in the studio ships a complete role palette. Contrast is computed
with WCAG relative luminance, so "high contrast" is a checked number rather
than a matter of taste. Grading values are part of the palette so a shot cannot
be rendered without a defined vignette and grain treatment.
"""
from __future__ import annotations

from dataclasses import dataclass, field

HEX_DIGITS = set("0123456789abcdef")


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    panel: str
    fg: str
    muted: str
    accent: str
    support: str
    grid: str
    line: str
    scrim: str
    light: bool = False

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "bg": self.bg,
            "panel": self.panel,
            "fg": self.fg,
            "muted": self.muted,
            "accent": self.accent,
            "support": self.support,
            "grid": self.grid,
            "line": self.line,
            "scrim": self.scrim,
            "light": self.light,
        }


@dataclass(frozen=True)
class Grade:
    vignette: float
    grain: float
    bloom: float
    contrast: float
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "vignette": self.vignette,
            "grain": self.grain,
            "bloom": self.bloom,
            "contrast": self.contrast,
            "description": self.description,
        }


@dataclass(frozen=True)
class Tone:
    name: str
    label: str
    thesis: str
    palette: Palette
    grade: Grade
    easing: dict
    anticipation: float
    overshoot: float
    stagger_frames: int
    camera_amplitude: float
    squash_allowed: bool
    transitions: tuple
    typography: dict
    notes: tuple = field(default_factory=tuple)


PALETTES: dict[str, Palette] = {
    "corporate": Palette(
        "corporate", "#0A1628", "#101F36", "#F3F6FB", "#9AAAC2",
        "#5B8FFF", "#7FD1C0", "#182A44", "#24395A", "#0A1628",
    ),
    "edgy": Palette(
        "edgy", "#08080A", "#141419", "#F5F4EF", "#8B8B94",
        "#FF4438", "#FFC53D", "#1A1A20", "#2A2A33", "#0A0A0C",
    ),
    "minimalist": Palette(
        "minimalist", "#F6F4EF", "#FFFFFF", "#121110", "#5E5A52",
        "#1B36E8", "#B23A0B", "#E6E1D8", "#CFC8BB", "#FFFFFF",
        light=True,
    ),
    "cinematic": Palette(
        "cinematic", "#0C0B0A", "#16130F", "#F4EDE1", "#A2957F",
        "#E9A13B", "#6E93A8", "#221D17", "#372E24", "#070706",
    ),
    "playful": Palette(
        "playful", "#14121F", "#1D1A2C", "#FFF7EA", "#B6AEC6",
        "#FF5D8F", "#5CE1E6", "#262134", "#38314C", "#0E0C17",
    ),
}

GRADES: dict[str, Grade] = {
    "corporate": Grade(0.10, 0.012, 0.08, 1.04, "Neutral cool grade, almost no grain."),
    "edgy": Grade(0.24, 0.045, 0.05, 1.12, "Crushed blacks, visible grain, hard vignette."),
    "minimalist": Grade(0.06, 0.006, 0.03, 1.02, "Clean paper grade; texture kept below perception."),
    "cinematic": Grade(0.30, 0.032, 0.16, 1.08, "Warm highlights, cool shadows, soft vignette, fine grain."),
    "playful": Grade(0.12, 0.014, 0.12, 1.05, "Bright, low-contrast, light bloom around accents."),
}

TONES: dict[str, Tone] = {
    "corporate": Tone(
        name="corporate", label="Corporate",
        thesis="Clarity and control: generous negative space, one idea per shot, "
               "movement that reads as confidence rather than excitement.",
        palette=PALETTES["corporate"], grade=GRADES["corporate"],
        easing={"primary": "editorial", "entrance": "entrance", "exit": "exit", "accent": "snap"},
        anticipation=0.03, overshoot=0.25, stagger_frames=3, camera_amplitude=0.6,
        squash_allowed=False,
        transitions=("cut", "masked-reveal", "morph", "match-cut"),
        typography={"display": "Inter", "text": "Inter", "tracking": "tight"},
    ),
    "edgy": Tone(
        name="edgy", label="Edgy",
        thesis="Impact and interruption: hard cuts, whip pans, glitch textures, "
               "type that snaps into place and holds.",
        palette=PALETTES["edgy"], grade=GRADES["edgy"],
        easing={"primary": "snap", "entrance": "snap", "exit": "exit", "accent": "settle"},
        anticipation=0.12, overshoot=0.8, stagger_frames=1, camera_amplitude=1.2,
        squash_allowed=False,
        transitions=("whip-pan", "glitch", "cut", "masked-reveal"),
        typography={"display": "Space Grotesk", "text": "Inter", "tracking": "wide"},
    ),
    "minimalist": Tone(
        name="minimalist", label="Minimalist",
        thesis="Restraint as the message: a single accent, one line of type at a "
               "time, long holds, motion measured in millimetres.",
        palette=PALETTES["minimalist"], grade=GRADES["minimalist"],
        easing={"primary": "editorial", "entrance": "entrance", "exit": "exit", "accent": "glide"},
        anticipation=0.02, overshoot=0.1, stagger_frames=5, camera_amplitude=0.3,
        squash_allowed=False,
        transitions=("cut", "morph", "masked-reveal", "match-cut"),
        typography={"display": "Inter", "text": "Inter", "tracking": "tight"},
    ),
    "cinematic": Tone(
        name="cinematic", label="Cinematic",
        thesis="A title sequence: slow pushes, deep negative space, one warm "
               "accent, type that arrives from darkness and settles.",
        palette=PALETTES["cinematic"], grade=GRADES["cinematic"],
        easing={"primary": "dramatic", "entrance": "entrance", "exit": "exit", "accent": "settle"},
        anticipation=0.06, overshoot=0.35, stagger_frames=4, camera_amplitude=0.9,
        squash_allowed=False,
        transitions=("masked-reveal", "match-cut", "morph", "cut"),
        typography={"display": "Space Grotesk", "text": "Inter", "tracking": "normal"},
    ),
    "playful": Tone(
        name="playful", label="Playful",
        thesis="Bounce and colour: letters overshoot, labels pop, layers overlap "
               "but never crowd the focal point.",
        palette=PALETTES["playful"], grade=GRADES["playful"],
        easing={"primary": "settle", "entrance": "snap", "exit": "exit", "accent": "settle"},
        anticipation=0.10, overshoot=1.0, stagger_frames=2, camera_amplitude=0.8,
        squash_allowed=True,
        transitions=("whip-pan", "masked-reveal", "morph", "glitch"),
        typography={"display": "Space Grotesk", "text": "Inter", "tracking": "wide"},
    ),
}

DEFAULT_TONE = "corporate"


def normalize_tone(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if key in ("", "default"):
        return DEFAULT_TONE
    aliases = {"energetic": "edgy", "premium": "cinematic", "clean": "minimalist", "fun": "playful"}
    key = aliases.get(key, key)
    if key not in TONES:
        raise ValueError("Unknown tone %r. Choose one of: %s" % (value, ", ".join(sorted(TONES))))
    return key


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6 or any(character not in HEX_DIGITS for character in text.lower()):
        raise ValueError("Invalid hex colour: %r" % (value,))
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _channel_luminance(channel: int) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    red, green, blue = _parse_hex(value)
    return (0.2126 * _channel_luminance(red)
            + 0.7152 * _channel_luminance(green)
            + 0.0722 * _channel_luminance(blue))


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio, 1.0 (identical) to 21.0 (black on white)."""
    a, b = relative_luminance(first), relative_luminance(second)
    lighter, darker = (a, b) if a >= b else (b, a)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def is_hex(value: str) -> bool:
    try:
        _parse_hex(value)
        return True
    except ValueError:
        return False


# The thresholds are deliberately stricter than WCAG AA for the roles that
# carry meaning, because video is compressed and viewed small.
CONTRAST_REQUIREMENTS = {
    "fg_on_bg": 7.0,
    "muted_on_bg": 4.5,
    "accent_on_bg": 4.5,
    "support_on_bg": 3.0,
    "fg_on_scrim": 7.0,
    "fg_on_panel": 7.0,
}


def contrast_report(palette: Palette) -> dict:
    return {
        "fg_on_bg": contrast_ratio(palette.fg, palette.bg),
        "muted_on_bg": contrast_ratio(palette.muted, palette.bg),
        "accent_on_bg": contrast_ratio(palette.accent, palette.bg),
        "support_on_bg": contrast_ratio(palette.support, palette.bg),
        "fg_on_scrim": contrast_ratio(palette.fg, palette.scrim),
        "fg_on_panel": contrast_ratio(palette.fg, palette.panel),
        "accent_on_scrim": contrast_ratio(palette.accent, palette.scrim),
    }


def palette_issues(palette: Palette) -> list[str]:
    issues = []
    report = contrast_report(palette)
    for role, minimum in CONTRAST_REQUIREMENTS.items():
        actual = report.get(role, 0.0)
        if actual < minimum:
            issues.append("%s is %.2f:1, needs %.1f:1" % (role, actual, minimum))
    return issues


def validate_palettes() -> dict:
    """Full check used by the tests and the compliance report."""
    return {
        name: {"report": contrast_report(palette), "issues": palette_issues(palette)}
        for name, palette in PALETTES.items()
    }


def tone(value: str | None = None) -> Tone:
    return TONES[normalize_tone(value)]


def style_block(value: str | None = None) -> dict:
    """The renderer-facing style object for a tone."""
    from . import typography

    item = tone(value)
    return {
        "tone": item.name,
        "palette": item.palette.as_dict(),
        "grade": item.grade.as_dict(),
        "easing": dict(item.easing),
        "typography": {
            **dict(item.typography),
            "display_stack": typography.DISPLAY_STACK,
            "text_stack": typography.TEXT_STACK,
        },
        "squash_allowed": item.squash_allowed,
    }


def roles(value: str | None = None) -> dict:
    return tone(value).palette.as_dict()
