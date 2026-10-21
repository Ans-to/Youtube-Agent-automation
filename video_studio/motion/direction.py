#!/usr/bin/env python3
"""The art director: turn a brief into a directed, render-ready timeline.

This is the layer the motion agents call. It decides tone, canvas, palette,
type scale, grading, shot grammar, transitions, camera moves, animation
recipes, layer order and sound cues - deterministically, from the brief, with
no model call and no external service.

Everything it emits is either directly renderable (the storyboard) or checked
by ``compliance.py``. Nothing is described as "professional" without a
machine-checkable property behind it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import camera, palette, typography
from .principles import hold_window, reading_time_seconds
from .transitions import frames_for, normalize as normalize_transition, select as select_transition, upgrade

SCHEMA_VERSION = 1

VISUAL_TYPES = (
    "hero", "stat", "timeline", "diagram", "comparison",
    "code", "quote", "waveform", "kinetic-type", "bar-chart",
)

PURPOSE_TO_VISUAL = {
    "hook": "hero",
    "thesis": "hero",
    "statement": "kinetic-type",
    "evidence": "stat",
    "data": "bar-chart",
    "process": "diagram",
    "sequence": "timeline",
    "proof": "comparison",
    "code": "code",
    "quote": "quote",
    "audio": "waveform",
    "takeaway": "hero",
    "cta": "hero",
}

PLATFORMS = {
    "youtube-4k": {"width": 3840, "height": 2160, "aspect": "16:9", "purpose": "YouTube / broadcast"},
    "broadcast-4k": {"width": 3840, "height": 2160, "aspect": "16:9", "purpose": "Broadcast master"},
    "youtube-1080": {"width": 1920, "height": 1080, "aspect": "16:9", "purpose": "YouTube 1080p"},
    "shorts-4k": {"width": 2160, "height": 3840, "aspect": "9:16", "purpose": "TikTok / Reels / Shorts"},
    "shorts-1080": {"width": 1080, "height": 1920, "aspect": "9:16", "purpose": "TikTok / Reels / Shorts"},
    "square-4k": {"width": 2160, "height": 2160, "aspect": "1:1", "purpose": "Feed / carousel"},
}

LAYER_ORDER = [
    {"name": "background", "contents": "palette base, grid, vignette base", "depth": 0.0},
    {"name": "midground", "contents": "parallax particles, signal nodes, texture", "depth": 0.25},
    {"name": "graphic", "contents": "diagram, chart, code, quote card", "depth": 0.55},
    {"name": "text", "contents": "eyebrow, headline, subhead, legal", "depth": 0.55},
    {"name": "character", "contents": "optional presenter rig", "depth": 0.8},
    {"name": "foreground", "contents": "grade: bloom, grain, vignette", "depth": 0.95},
    {"name": "ui", "contents": "captions, progress, footer", "depth": 1.0},
]

ANIMATION_RECIPES = {
    "hero": {"in": "mask-rise", "out": "fade-down", "stagger": True},
    "stat": {"in": "count-scale", "out": "fade", "stagger": True},
    "diagram": {"in": "node-sweep", "out": "fade", "stagger": True},
    "timeline": {"in": "track-draw", "out": "fade", "stagger": True},
    "comparison": {"in": "split-wipe", "out": "fade", "stagger": True},
    "code": {"in": "line-by-line", "out": "fade", "stagger": True},
    "quote": {"in": "mask-rise", "out": "fade", "stagger": False},
    "waveform": {"in": "grow", "out": "fade", "stagger": False},
    "kinetic-type": {"in": "word-mask", "out": "fade", "stagger": True},
    "bar-chart": {"in": "bar-grow", "out": "fade", "stagger": True},
}

MAX_SCENES = 100
MAX_SECONDS = 1000.0
MAX_FRAMES = 30000


class BriefError(ValueError):
    """Raised when a brief cannot be directed without inventing facts."""


def _text(value, field: str, limit: int = 600) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BriefError("%s must be text" % field)
    if len(value) > limit:
        raise BriefError("%s exceeds the %d-character limit" % (field, limit))
    return value.strip()


def _number(value, field: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BriefError("%s must be a number" % field) from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise BriefError("%s must be between %s and %s" % (field, minimum, maximum))
    return number


def platform_canvas(platform: str | None, tone: str, fps: int | None = None) -> dict:
    key = str(platform or "youtube-4k").strip().lower()
    if key not in PLATFORMS:
        raise BriefError("Unknown platform %r. Choose one of: %s" % (platform, ", ".join(sorted(PLATFORMS))))
    spec = dict(PLATFORMS[key])
    tone_name = palette.normalize_tone(tone)
    # Cinematic and minimalist cuts breathe at 30; impact-led tones run at 60.
    default_fps = 30 if tone_name in ("cinematic", "minimalist") else 60
    chosen = default_fps if fps is None else int(fps)
    if chosen not in (30, 60):
        raise BriefError("Frame rate must be 30 or 60 fps")
    spec.update({"platform": key, "fps": chosen})
    return spec


def _infer_visual(scene: dict, index: int) -> str:
    if scene.get("visual_type") is not None:
        kind = str(scene["visual_type"]).strip().lower()
        if kind not in VISUAL_TYPES:
            raise BriefError("Scene %d uses unsupported visual_type %r" % (index + 1, kind))
        return kind
    purpose = str(scene.get("purpose", "")).strip().lower()
    if purpose in PURPOSE_TO_VISUAL:
        return PURPOSE_TO_VISUAL[purpose]
    return "hero"


def _transition(scene: dict, index: int, tone: str, previous: str | None) -> str:
    if index == 0:
        return "cut"
    raw = scene.get("transition_in")
    if raw is None:
        return select_transition(index, tone, previous, purpose=scene.get("purpose"))
    key = str(raw).strip().lower()
    if key in ("none", ""):
        return "cut"
    return upgrade(key, tone)


def _animation(scene: dict, visual_type: str, tone: palette.Tone, duration: float) -> dict:
    recipe = ANIMATION_RECIPES[visual_type]
    window = hold_window(duration, in_fraction=0.18, out_fraction=0.16)
    return {
        "in": recipe["in"],
        "out": recipe["out"],
        "stagger_frames": tone.stagger_frames,
        "anticipation": tone.anticipation,
        "overshoot": tone.overshoot,
        "squash": tone.squash_allowed,
        "hold": window,
        "easing": dict(tone.easing),
        "masked": True,
        "linear": False,
    }


def _scene_issues(scene: dict, index: int, duration: float, tone: palette.Tone,
                  scale: dict, text_px: int) -> list[str]:
    issues = []
    headline = _text(scene.get("headline"), "headline")
    subhead = _text(scene.get("subhead"), "subhead")
    if not headline:
        issues.append("Scene %d has no headline" % (index + 1))
    words = len(headline.split()) + len(subhead.split())
    if words > 45:
        issues.append("Scene %d carries %d words; over 45 overloads a single frame" % (index + 1, words))
    needed = reading_time_seconds(max(1, len(headline.split())), 200)
    if duration < needed:
        issues.append("Scene %d holds %.2fs but its headline needs %.2fs to read" % (index + 1, duration, needed))
    if text_px < 24:
        issues.append("Scene %d would render its headline at %dpx, below legibility" % (index + 1, text_px))
    if not tone.squash_allowed and scene.get("squash"):
        issues.append("Scene %d requests squash on a rigid tone" % (index + 1))
    return issues


def compile_brief(brief: dict, *, upgrade_legacy: bool = True) -> dict:
    """Compile a brief into ``{"direction": ..., "storyboard": ...}``."""
    if not isinstance(brief, dict):
        raise BriefError("Brief root must be a JSON object")
    title = _text(brief.get("title"), "title", 200)
    goal = _text(brief.get("goal"), "goal", 1200)
    if not title:
        raise BriefError("Brief needs a title")
    if not goal:
        raise BriefError("Brief needs a goal: what should the viewer think or do?")

    try:
        tone_name = palette.normalize_tone(brief.get("tone"))
    except ValueError as exc:
        raise BriefError(str(exc)) from exc
    tone = palette.TONES[tone_name]
    canvas = platform_canvas(brief.get("platform"), tone_name, brief.get("fps"))
    scale = typography.type_scale(canvas["width"])

    scenes = brief.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise BriefError("Brief needs 1..%d scenes" % MAX_SCENES)

    directed = []
    warnings: list[str] = []
    cursor = 0.0
    previous_transition: str | None = None
    for index, raw in enumerate(scenes):
        if not isinstance(raw, dict):
            raise BriefError("Scene %d must be an object" % (index + 1))
        duration = _number(raw.get("duration_seconds"), "Scene %d duration_seconds" % (index + 1), 0.2, 600)
        visual = _infer_visual(raw, index)
        transition = _transition(raw, index, tone_name, previous_transition)
        if not upgrade_legacy and raw.get("transition_in"):
            transition = normalize_transition(raw["transition_in"])
        tone_camera = raw.get("camera_motion")
        move = camera.normalize_move(tone_camera) if tone_camera else camera.select(index, tone_name, raw.get("purpose"))

        headline = _text(raw.get("headline"), "Scene %d headline" % (index + 1))
        subhead = _text(raw.get("subhead"), "Scene %d subhead" % (index + 1))
        narration = _text(raw.get("narration"), "Scene %d narration" % (index + 1), 6000)
        animation = _animation(raw, visual, tone, duration)
        window = animation["hold"]
        transition_frames = frames_for(transition, canvas["fps"]) if transition != "cut" else 0

        issues = _scene_issues(raw, index, duration, tone, scale, scale["headline"].size_px)
        warnings.extend(issues)

        color_override = raw.get("accent")
        if color_override and not palette.is_hex(str(color_override)):
            warnings.append("Scene %d accent is not a hex colour and was ignored" % (index + 1))

        shot = {
            "index": index + 1,
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "label": "%s-%s" % (_timecode(cursor), _timecode(cursor + duration)),
            "purpose": str(raw.get("purpose", "statement")).lower(),
            "visual_type": visual,
            "transition_in": transition,
            "transition_frames": transition_frames,
            "camera_motion": move,
            "animation": animation,
            "hold_seconds": round(window["hold"], 3),
            "impact": bool(raw.get("impact", tone_name in ("edgy", "playful") and index == 0)),
            "headline": headline,
            "subhead": subhead,
            "narration": narration,
        }
        directed.append(shot)
        cursor += duration
        previous_transition = transition

    if cursor > MAX_SECONDS:
        raise BriefError("Directed timeline exceeds the %.0f-second render limit" % MAX_SECONDS)
    total_frames = sum(max(1, round(shot["end"] - shot["start"]) * canvas["fps"]) for shot in directed)
    if total_frames > MAX_FRAMES:
        raise BriefError("Directed timeline exceeds the %d-frame render limit" % MAX_FRAMES)

    timeline = [
        {
            "index": shot["index"],
            "start": shot["start"],
            "end": shot["end"],
            "label": shot["label"],
            "beat": _beat_name(shot["purpose"], shot["index"], len(directed)),
            "purpose": shot["purpose"],
            "visual_type": shot["visual_type"],
            "transition_in": shot["transition_in"],
            "transition_frames": shot["transition_frames"],
            "camera_motion": shot["camera_motion"],
            "hold_seconds": shot["hold_seconds"],
            "headline": shot["headline"],
            "sound": {"cues": []},
        }
        for shot in directed
    ]

    storyboard = {
        "title": title,
        "width": canvas["width"],
        "height": canvas["height"],
        "fps": canvas["fps"],
        "style": {**palette.style_block(tone_name), "master": "4k"},
        "scenes": [
            {
                "duration_seconds": round(shot["end"] - shot["start"], 3),
                "eyebrow": str(scenes[index].get("eyebrow", "")).strip(),
                "headline": shot["headline"],
                "subhead": shot["subhead"],
                "narration": shot["narration"],
                "visual_type": shot["visual_type"],
                "transition_in": shot["transition_in"],
                "transition_frames": shot["transition_frames"] or 0,
                "camera_motion": shot["camera_motion"],
                "easing": shot["animation"]["easing"]["primary"],
                "stagger_frames": shot["animation"]["stagger_frames"],
                "anticipation": shot["animation"]["anticipation"],
                "overshoot": shot["animation"]["overshoot"],
                "masked": True,
                **({key: scenes[index][key] for key in (
                    "graphic_label", "stat_value", "stat_label", "visual_nodes",
                    "timeline_events", "comparison_left_title", "comparison_right_title",
                    "comparison_left", "comparison_right", "code_lines", "quote",
                    "quote_source", "chart_values", "chart_labels", "show_orbit",
                    "character",
                ) if key in scenes[index]}),
            }
            for index, shot in enumerate(directed)
        ],
    }

    cue_plan = build_cues(directed)
    for item, cues in zip(timeline, cue_plan, strict=True):
        item["sound"]["cues"] = cues

    direction = {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "goal": goal,
        "tone": {"name": tone.name, "label": tone.label, "thesis": tone.thesis},
        "platform": canvas,
        "canvas": {
            "width": canvas["width"],
            "height": canvas["height"],
            "fps": canvas["fps"],
            "aspect": canvas["aspect"],
            "title_safe": 0.90,
            "action_safe": 0.93,
        },
        "art_direction": {
            "palette": tone.palette.as_dict(),
            "grade": tone.grade.as_dict(),
            "typography": {
                "display_stack": typography.DISPLAY_STACK,
                "text_stack": typography.TEXT_STACK,
                "scale": {name: role.size_px for name, role in scale.items()},
                "hierarchy": typography.hierarchy_report(canvas["width"]),
            },
            "easing": dict(tone.easing),
            "principles": {
                "anticipation": tone.anticipation,
                "overshoot": tone.overshoot,
                "stagger_frames": tone.stagger_frames,
                "squash_allowed": tone.squash_allowed,
            },
            "camera": {
                "amplitude": tone.camera_amplitude,
                "depth_of_field": "emulated with blur; not a lens simulation",
            },
        },
        "layers": [dict(layer) for layer in LAYER_ORDER],
        "timeline": timeline,
        "warnings": warnings,
        "storyboard": storyboard,
    }
    return {"direction": direction, "storyboard": storyboard}


def _timecode(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, remainder = divmod(total, 60)
    return "%d:%02d" % (minutes, remainder)


def _beat_name(purpose: str, index: int, count: int) -> str:
    purpose = (purpose or "").lower()
    names = {
        "hook": "Hook", "thesis": "Thesis", "statement": "Statement", "evidence": "Evidence",
        "data": "Data", "process": "Process", "sequence": "Sequence", "proof": "Proof",
        "code": "Mechanism", "quote": "Quote", "audio": "Sound", "takeaway": "Takeaway",
        "cta": "Call to action", "impact": "Impact", "reveal": "Reveal",
    }
    base = names.get(purpose, "Scene %d" % index)
    if index == 1:
        return "Intro - " + base
    if index == count:
        return "Outro - " + base
    return base


def build_cues(directed: list[dict]) -> list[list[dict]]:
    """One cue list per shot, keyed by scene start (the edit point)."""
    from .beat import SFX_FOR_TRANSITION, SFX_LENGTH

    cues: list[list[dict]] = [[] for _ in directed]
    for index, shot in enumerate(directed):
        if index > 0:
            kind = SFX_FOR_TRANSITION.get(shot["transition_in"])
            if kind:
                cues[index].append({
                    "kind": kind,
                    "at": 0.0,
                    "length": SFX_LENGTH[kind],
                    "gain": 0.30,
                })
        if shot.get("impact"):
            cues[index].append({
                "kind": "impact",
                "at": round(min(0.25, (shot["end"] - shot["start"]) * 0.12), 3),
                "length": SFX_LENGTH["impact"],
                "gain": 0.34,
            })
    return cues


def format_timeline(direction: dict) -> str:
    """Human-readable timeline in the format the brief asks for."""
    lines = [
        "%s  |  %s  |  %dx%d @ %dfps"
        % (direction["title"], direction["tone"]["label"].upper(),
           direction["canvas"]["width"], direction["canvas"]["height"], direction["canvas"]["fps"]),
        "",
    ]
    for shot in direction["timeline"]:
        lines.append(
            "%-11s %-22s %-13s %-15s %-9s hold %.2fs"
            % (shot["label"], shot["beat"][:22], shot["visual_type"],
               shot["transition_in"], shot["camera_motion"], shot["hold_seconds"])
        )
        if shot["headline"]:
            lines.append("            %s" % shot["headline"][:88])
    lines.append("")
    lines.append("Layers: " + " > ".join(layer["name"] for layer in direction["layers"]))
    if direction["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines.extend("- " + warning for warning in direction["warnings"])
    return "\n".join(lines)


def upgrade_storyboard(storyboard: dict, *, tone: str | None = None) -> dict:
    """Attach direction to an existing storyboard without rewriting its copy.

    Used for projects that already have a storyboard.json. Copy, layout data and
    transitions are preserved; only the transition vocabulary and the style
    block are upgraded.
    """
    if not isinstance(storyboard, dict) or not isinstance(storyboard.get("scenes"), list):
        raise BriefError("Storyboard must be an object with a scenes array")
    tone_name = palette.normalize_tone(tone or (storyboard.get("style") or {}).get("tone"))
    upgraded = json.loads(json.dumps(storyboard))
    upgraded["style"] = palette.style_block(tone_name)
    upgraded["style"]["master"] = "4k" if int(upgraded.get("width", 0) or 0) >= 3840 else "preview"
    tone_item = palette.tone(tone_name)
    fps = int(upgraded.get("fps", 30) or 30)
    for index, scene in enumerate(upgraded["scenes"]):
        # Animation contract applies to every scene, including the opening cut.
        scene.setdefault("easing", tone_item.easing["primary"])
        scene.setdefault("stagger_frames", tone_item.stagger_frames)
        scene.setdefault("anticipation", tone_item.anticipation)
        scene.setdefault("overshoot", tone_item.overshoot)
        scene.setdefault("masked", True)
        if index == 0:
            scene["transition_in"] = "cut"
            scene["transition_frames"] = 0
            continue
        current = str(scene.get("transition_in", "none")).lower()
        scene["transition_in"] = "cut" if current == "none" else upgrade(current, tone_name)
        scene["transition_frames"] = (
            0 if scene["transition_in"] == "cut"
            else int(scene.get("transition_frames") or frames_for(scene["transition_in"], fps))
        )
    return upgraded


def write_json(path: str | Path, data: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load(path: str | Path) -> dict:
    source = Path(path)
    if not source.is_file():
        raise BriefError("File not found: %s" % source)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BriefError("Invalid JSON in %s: %s" % (source, exc)) from exc


def summarize_storyboard(storyboard: dict, tone: str | None = None) -> dict:
    """Build a direction sheet for an existing storyboard without inventing copy.

    The timeline, layers and art direction are derived from the file itself. No
    scenes, claims or narration are added; anything the file does not state is
    absent from the summary and will be reported as not checked.
    """
    if not isinstance(storyboard, dict) or not isinstance(storyboard.get("scenes"), list):
        raise BriefError("Storyboard must be an object with a scenes array")
    tone_name = palette.normalize_tone(tone or (_style_of(storyboard).get("tone")))
    tone_item = palette.TONES[tone_name]
    width = int(storyboard.get("width", 1920) or 1920)
    height = int(storyboard.get("height", 1080) or 1080)
    fps = int(storyboard.get("fps", 30) or 30)
    scale = typography.type_scale(width)

    cursor = 0.0
    timeline = []
    warnings = ["No brief supplied: timeline and pacing are derived from the existing storyboard."]
    for index, scene in enumerate(storyboard["scenes"]):
        try:
            duration = float(scene.get("duration_seconds", 0))
        except (TypeError, ValueError):
            duration = 0.0
        window = hold_window(max(0.2, duration), in_fraction=0.18, out_fraction=0.16)
        timeline.append({
            "index": index + 1,
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "label": "%s-%s" % (_timecode(cursor), _timecode(cursor + duration)),
            "beat": _beat_name(str(scene.get("purpose", "statement")), index + 1, len(storyboard["scenes"])),
            "purpose": str(scene.get("purpose", "statement")),
            "visual_type": str(scene.get("visual_type", "hero")),
            "transition_in": str(scene.get("transition_in", "none")).lower(),
            "transition_frames": scene.get("transition_frames", 0),
            "camera_motion": str(scene.get("camera_motion", "static")),
            "hold_seconds": round(window["hold"], 3),
            "headline": str(scene.get("headline", "")),
            "sound": {"cues": []},
        })
        cursor += duration

    return {
        "schema_version": SCHEMA_VERSION,
        "title": str(storyboard.get("title", "Untitled")),
        "goal": "Compiled from an existing storyboard. No brief was supplied.",
        "tone": {"name": tone_item.name, "label": tone_item.label, "thesis": tone_item.thesis},
        "platform": {"platform": "custom", "purpose": "Existing storyboard", "aspect": "16:9" if width > height else "9:16"},
        "canvas": {"width": width, "height": height, "fps": fps,
                   "aspect": "16:9" if width > height else "9:16",
                   "title_safe": 0.90, "action_safe": 0.93},
        "art_direction": {
            "palette": tone_item.palette.as_dict(),
            "grade": tone_item.grade.as_dict(),
            "typography": {
                "display_stack": typography.DISPLAY_STACK,
                "text_stack": typography.TEXT_STACK,
                "scale": {name: role.size_px for name, role in scale.items()},
                "hierarchy": typography.hierarchy_report(width),
            },
            "easing": dict(tone_item.easing),
            "principles": {
                "anticipation": tone_item.anticipation,
                "overshoot": tone_item.overshoot,
                "stagger_frames": tone_item.stagger_frames,
                "squash_allowed": tone_item.squash_allowed,
            },
            "camera": {"amplitude": tone_item.camera_amplitude,
                       "depth_of_field": "emulated with blur; not a lens simulation"},
        },
        "layers": [dict(layer) for layer in LAYER_ORDER],
        "timeline": timeline,
        "warnings": warnings,
        "storyboard": storyboard,
    }


def _style_of(storyboard: dict) -> dict:
    style = storyboard.get("style")
    return style if isinstance(style, dict) else {}
