#!/usr/bin/env python3
"""Composition: thirds, golden section, safe areas, negative space.

The numbers here mirror the renderer's layout. When the renderer changes, this
module and its tests must change with it, which is why the layout is expressed
once as fractions and checked rather than described in prose.
"""
from __future__ import annotations

from dataclasses import dataclass

from .typography import type_scale

TITLE_SAFE = 0.90   # 5% margin on every side
ACTION_SAFE = 0.93  # 3.5% margin on every side
THIRDS = (1.0 / 3.0, 2.0 / 3.0)
GOLDEN = (0.381966, 0.618034)

# Renderer geometry, expressed as fractions of the canvas.
LEFT = 0.078
CONTENT_WIDTH = 0.844
HERO_TEXT_WIDTH = 0.490
TEXT_WIDTH = 0.490
GRAPHIC_X = 0.635
GRAPHIC_Y = 0.360
GRAPHIC_WIDTH = 0.225
GRAPHIC_HEIGHT = 0.315
CAPTION_LANDSCAPE_WIDTH = 0.600
FOOTER_Y = 0.910
FOOTER_OFFSET = 0.035


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def as_dict(self) -> dict:
        return {"x": round(self.x, 4), "y": round(self.y, 4),
                "width": round(self.width, 4), "height": round(self.height, 4)}


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    portrait: bool
    text: Box
    graphic: Box
    caption: Box
    title_safe: Box
    action_safe: Box
    footer_y: float

    def as_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "portrait": self.portrait,
            "text": self.text.as_dict(),
            "graphic": self.graphic.as_dict(),
            "caption": self.caption.as_dict(),
            "title_safe": self.title_safe.as_dict(),
            "action_safe": self.action_safe.as_dict(),
            "footer_y": round(self.footer_y, 4),
        }


def safe_box(width: int, height: int, fraction: float) -> Box:
    margin_x = width * (1.0 - fraction) / 2.0
    margin_y = height * (1.0 - fraction) / 2.0
    return Box(margin_x, margin_y, width * fraction, height * fraction)


def layout_for(width: int, height: int, visual_type: str = "hero") -> Layout:
    if width < 320 or height < 180:
        raise ValueError("Layout needs a canvas of at least 320x180")
    portrait = height > width
    kind = str(visual_type or "hero").lower()
    if kind == "kinetic-type":
        # The type is the graphic, so it owns the full content lane.
        text_width = CONTENT_WIDTH * width
    else:
        text_width = (HERO_TEXT_WIDTH if kind == "hero" else TEXT_WIDTH) * width
    # Portrait stacks eyebrow 0.31h, headline 0.43h, subhead 0.59h; the block
    # therefore ends before the 0.63h graphic band.
    text_y = height * (0.31 if portrait else 0.33)
    text_height = height * (0.30 if portrait else 0.34)
    if portrait:
        graphic = Box(LEFT * width, (0.63 if kind == "bar-chart" else 0.68) * height,
                      CONTENT_WIDTH * width, (0.14 if kind == "bar-chart" else 0.08) * height)
        caption = Box(LEFT * width, height * 0.80, CONTENT_WIDTH * width, height * 0.08)
    elif kind == "kinetic-type":
        graphic = Box(0.0, 0.0, 0.0, 0.0)
        caption = Box(LEFT * width, height * 0.80,
                      min(CAPTION_LANDSCAPE_WIDTH, CONTENT_WIDTH) * width, height * 0.08)
    else:
        graphic = Box(GRAPHIC_X * width, GRAPHIC_Y * height,
                      GRAPHIC_WIDTH * width, GRAPHIC_HEIGHT * height)
        caption = Box(LEFT * width, height * 0.80,
                      min(CAPTION_LANDSCAPE_WIDTH, CONTENT_WIDTH) * width, height * 0.08)
    return Layout(
        width=width,
        height=height,
        portrait=portrait,
        text=Box(LEFT * width, text_y, text_width, text_height),
        graphic=graphic,
        caption=caption,
        title_safe=safe_box(width, height, TITLE_SAFE),
        action_safe=safe_box(width, height, ACTION_SAFE),
        footer_y=FOOTER_Y * height,
    )


def contains(outer: Box, inner: Box, tolerance: float = 0.0) -> bool:
    return (inner.x >= outer.x - tolerance and inner.y >= outer.y - tolerance
            and inner.right <= outer.right + tolerance
            and inner.bottom <= outer.bottom + tolerance)


def overlap(a: Box, b: Box) -> bool:
    return (a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom)


def overlap_area(a: Box, b: Box) -> float:
    width = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    height = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return width * height


def focus_points(width: int, height: int) -> list[dict]:
    points = []
    for name, values in (("thirds", THIRDS), ("golden", GOLDEN)):
        for x in values:
            for y in values:
                points.append({"system": name, "x": round(x * width, 1), "y": round(y * height, 1),
                               "x_fraction": round(x, 4), "y_fraction": round(y, 4)})
    return points


def nearest_focus(width: int, height: int, x: float, y: float) -> dict:
    """Closest composition anchor to a pixel position, with distance in pixels."""
    best = None
    for point in focus_points(width, height):
        distance = ((point["x"] - x) ** 2 + (point["y"] - y) ** 2) ** 0.5
        if best is None or distance < best["distance_px"]:
            best = dict(point, distance_px=round(distance, 1))
    return best


def estimate_ink_coverage(width: int, height: int, visual_type: str = "hero") -> float:
    """Approximate fraction of the frame covered by type and graphics.

    Deliberately conservative: it treats text as solid rectangles, so real ink
    coverage is lower. The value is used to guarantee negative space, not to
    make a beauty claim.
    """
    layout = layout_for(width, height, visual_type)
    scale = type_scale(width)
    frame = float(width * height)

    headline = scale["headline"].size_px * 1.14 * 2.4  # up to three lines
    eyebrow = scale["eyebrow"].size_px * 1.5
    subhead = scale["subhead"].size_px * 1.35 * 2.0
    text_area = layout.text.width * (headline + eyebrow + subhead)
    graphic_area = layout.graphic.width * layout.graphic.height
    caption_area = layout.caption.width * (scale["caption"].size_px * 1.3 * 2 + 18)
    return round(min(1.0, (text_area + graphic_area + caption_area) / frame), 4)


def audit_layout(width: int, height: int, visual_type: str = "hero") -> dict:
    """Machine check of the renderer's composition for one aspect ratio and shot."""
    layout = layout_for(width, height, visual_type)
    issues: list[str] = []
    checks: dict[str, bool] = {}

    checks["text_inside_title_safe"] = contains(layout.title_safe, layout.text, tolerance=1.0)
    # Kinetic type has no graphic of its own; the zero box is not a layout failure.
    checks["graphic_inside_action_safe"] = (
        layout.graphic.width == 0 or contains(layout.action_safe, layout.graphic, tolerance=1.0)
    )
    checks["caption_inside_action_safe"] = contains(layout.action_safe, layout.caption, tolerance=1.0)
    checks["footer_inside_title_safe"] = (
        layout.footer_y + FOOTER_OFFSET * height <= layout.title_safe.bottom + 1.0
    )
    checks["text_clear_of_graphic"] = not overlap(layout.text, layout.graphic)

    if not layout.portrait and layout.graphic.width > 0:
        # Graphics are aligned by their leading edge to the golden section.
        checks["graphic_on_golden_section"] = abs(layout.graphic.x / width - GOLDEN[1]) <= 0.06
    else:
        checks["graphic_on_golden_section"] = True

    coverage = estimate_ink_coverage(width, height, visual_type)
    checks["negative_space_at_least_40_percent"] = coverage <= 0.60

    for name, ok in checks.items():
        if not ok:
            issues.append("%s failed at %dx%d (%s)" % (name, width, height, visual_type))

    return {
        "checks": checks,
        "issues": issues,
        "coverage": coverage,
        "negative_space": round(1.0 - coverage, 4),
        "layout": layout.as_dict(),
        "safe": {"title": TITLE_SAFE, "action": ACTION_SAFE},
    }


def audit_aspect_ratios() -> dict:
    """Every aspect ratio the studio ships must pass the same composition rules."""
    results = {}
    for name, (width, height) in {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
    }.items():
        results[name] = {kind: audit_layout(width, height, kind)
                         for kind in ("hero", "diagram", "bar-chart")}
    return results
