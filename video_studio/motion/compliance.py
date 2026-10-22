#!/usr/bin/env python3
"""Machine enforcement of the professional motion-graphics brief.

A design document is not a standard until something can fail against it. Each
check below maps to a clause in the brief and answers with one of three states:

* ``pass``        - the clause was checked and the artifact complies;
* ``fail``        - the clause was checked and the artifact violates it;
* ``not_applicable`` - the check needs evidence the project does not contain.

``not_applicable`` is never counted as a pass. The report names every check that
did not run, so a clean result cannot be mistaken for a complete review.
"""
from __future__ import annotations

import math

from . import camera, composition, palette, typography
from .curves import CURVES, is_linear_like
from .transitions import LEGACY_NAMES, plan_issues, upgrade

PLACEHOLDER_MARKERS = (
    "lorem ipsum", "dolor sit amet", "todo", "tbd", "placeholder",
    "insert text", "[insert", "xxx", "example metric", "your headline here",
)


def _result(check_id: str, category: str, title: str, status: str,
            detail: str = "", **extra) -> dict:
    item = {
        "id": check_id,
        "category": category,
        "title": title,
        "status": status,
        "detail": detail,
    }
    item.update(extra)
    return item


def _scenes(storyboard: dict) -> list[dict]:
    scenes = storyboard.get("scenes") if isinstance(storyboard, dict) else None
    return scenes if isinstance(scenes, list) else []


def _scene_text(scene: dict) -> str:
    parts = [str(scene.get(key, "")) for key in ("eyebrow", "headline", "subhead", "narration", "caption")]
    for key in ("visual_nodes", "timeline_events", "comparison_left", "comparison_right",
                "code_lines", "chart_labels"):
        value = scene.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(part for part in parts if part)


def _style(storyboard: dict) -> dict:
    style = storyboard.get("style")
    return style if isinstance(style, dict) else {}


def _tone(storyboard: dict) -> str:
    try:
        return palette.normalize_tone(_style(storyboard).get("tone"))
    except ValueError:
        return ""


def check_tone(storyboard: dict) -> dict:
    name = _tone(storyboard)
    if not name:
        return _result("MG-1.1-TONE", "Art direction", "Tone is declared", "fail",
                       "No valid tone in style.tone. The brief requires a chosen tone, not a default.")
    tone = palette.TONES[name]
    return _result("MG-1.1-TONE", "Art direction", "Tone is declared", "pass",
                   "%s: %s" % (tone.label, tone.thesis))


def check_resolution(storyboard: dict) -> dict:
    width = int(storyboard.get("width", 0) or 0)
    height = int(storyboard.get("height", 0) or 0)
    fps = int(storyboard.get("fps", 0) or 0)
    master = str(_style(storyboard).get("master", "4k")).lower()
    problems = []
    if not (320 <= width <= 3840 and 180 <= height <= 3840):
        problems.append("canvas %dx%d is outside the renderer's range" % (width, height))
    short = min(width, height)
    if master == "preview":
        # A declared draft is not pretending to be a master. It may be 1080p, but
        # it must still be a real HD canvas at a supported frame rate.
        if short < 1080:
            problems.append("preview short edge is %dpx; drafts must still be at least 1080px" % short)
    else:
        if short < 1920:
            problems.append("short edge is %dpx; the professional master is 4K UHD (2160px)" % short)
        if width > height and width < 3840:
            problems.append("landscape master is %dpx wide; 4K UHD is 3840" % width)
    if fps not in (30, 60):
        problems.append("fps is %d; the brief allows 30 or 60" % fps)
    if problems:
        return _result("MG-2.1-RESOLUTION", "Technical", "Resolution and frame rate", "fail",
                       "; ".join(problems), width=width, height=height, fps=fps, master=master)
    label = "%dx%d at %d fps" % (width, height, fps)
    if master == "preview":
        label += " (declared preview canvas; not a 4K master)"
    result = _result("MG-2.1-RESOLUTION", "Technical", "Resolution and frame rate", "pass",
                     label, width=width, height=height, fps=fps, master=master)
    if master == "preview":
        result["notice"] = (
            "This canvas is declared a preview, not a 4K master. Render the master at "
            "3840x2160 (or 2160x3840) before delivery."
        )
    return result


def check_composition(storyboard: dict) -> dict:
    width = int(storyboard.get("width", 0) or 0)
    height = int(storyboard.get("height", 0) or 0)
    if width < 320 or height < 180:
        return _result("MG-2.2-COMPOSITION", "Composition", "Thirds, golden section, safe areas",
                       "not_applicable", "Canvas dimensions are invalid, so layout cannot be evaluated.")
    issues = []
    coverage = []
    for shot in _scenes(storyboard):
        visual = str(shot.get("visual_type", "hero")).lower()
        report = composition.audit_layout(width, height, visual)
        coverage.append(report["coverage"])
        for issue in report["issues"]:
            issues.append("%s: %s" % (visual, issue))
    if issues:
        return _result("MG-2.2-COMPOSITION", "Composition", "Thirds, golden section, safe areas",
                       "fail", "; ".join(issues[:6]), checks=len(issues))
    return _result("MG-2.2-COMPOSITION", "Composition", "Thirds, golden section, safe areas",
                   "pass", "All shots inside action-safe with >=40%% negative space (mean ink %.1f%%)."
                   % (100 * sum(coverage) / max(1, len(coverage))))


def check_contrast(storyboard: dict) -> dict:
    style = _style(storyboard)
    tones = style.get("tone")
    try:
        name = palette.normalize_tone(tones)
    except ValueError:
        return _result("MG-2.3-CONTRAST", "Color", "Text contrast", "not_applicable",
                       "No valid tone, so no palette can be checked.")
    item = palette.TONES[name]
    override = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    pal = item.palette
    if override:
        try:
            pal = palette.Palette(**{**pal.as_dict(), **{
                key: override[key] for key in (
                    "bg", "panel", "fg", "muted", "accent", "support", "grid", "line", "scrim"
                ) if key in override
            }})
        except TypeError:
            return _result("MG-2.3-CONTRAST", "Color", "Text contrast", "fail",
                           "Palette override has an invalid shape")
    issues = palette.palette_issues(pal)
    report = palette.contrast_report(pal)
    if issues:
        return _result("MG-2.3-CONTRAST", "Color", "Text contrast", "fail",
                       "; ".join(issues), ratios=report)
    return _result("MG-2.3-CONTRAST", "Color", "Text contrast", "pass",
                   "fg %.2f:1, accent %.2f:1, minimum %.1f:1"
                   % (report["fg_on_bg"], report["accent_on_bg"],
                      min(palette.CONTRAST_REQUIREMENTS.values())), ratios=report)


def check_grade(storyboard: dict) -> dict:
    grade = _style(storyboard).get("grade")
    if not isinstance(grade, dict):
        return _result("MG-2.4-GRADE", "Color", "Vignette and grain", "fail",
                       "No grade block. Every render must declare vignette, grain and contrast.")
    problems = []
    vignette = _float(grade.get("vignette"), "vignette")
    grain = _float(grade.get("grain"), "grain")
    contrast = _float(grade.get("contrast"), "contrast")
    if not 0.0 <= vignette <= 0.40:
        problems.append("vignette %.2f outside 0..0.40" % vignette)
    if not 0.0 <= grain <= 0.08:
        problems.append("grain %.3f outside 0..0.08" % grain)
    if not 0.90 <= contrast <= 1.20:
        problems.append("contrast %.2f outside 0.90..1.20" % contrast)
    if problems:
        return _result("MG-2.4-GRADE", "Color", "Vignette and grain", "fail", "; ".join(problems))
    return _result("MG-2.4-GRADE", "Color", "Vignette and grain", "pass",
                   "vignette %.2f, grain %.3f, contrast %.2f" % (vignette, grain, contrast))


def _float(value, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s must be numeric" % field) from exc
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % field)
    return number


def check_typography(storyboard: dict) -> dict:
    width = int(storyboard.get("width", 1920) or 1920)
    issues = typography.hierarchy_issues(width)
    inventory = typography.available_fonts()
    if not inventory["complete"]:
        issues.append("%d bundled font files are missing" % len(inventory["missing"]))
    style = _style(storyboard)
    typography_style = style.get("typography") if isinstance(style.get("typography"), dict) else {}
    display = typography_style.get("display_stack") or typography.DISPLAY_STACK
    text = typography_style.get("text_stack") or typography.TEXT_STACK
    issues.extend("display stack: " + issue for issue in typography.stack_issues(display))
    issues.extend("text stack: " + issue for issue in typography.stack_issues(text))
    scale = typography.hierarchy_report(width)
    if issues:
        return _result("MG-2.5-TYPE", "Typography", "Type hierarchy and fonts", "fail",
                       "; ".join(issues[:6]), scale=scale)
    return _result("MG-2.5-TYPE", "Typography", "Type hierarchy and fonts", "pass",
                   "headline %dpx / subhead %dpx / caption %dpx / legal %dpx"
                   % (scale["headline"], scale["subhead"], scale["caption"], scale["legal"]),
                   scale=scale)


def check_kinetic_type(storyboard: dict) -> dict:
    scenes = _scenes(storyboard)
    if not scenes:
        return _result("MG-2.6-KINETIC", "Typography", "Text never just appears", "not_applicable",
                       "Storyboard has no scenes.")
    missing = []
    for index, scene in enumerate(scenes):
        headline = str(scene.get("headline", "")).strip()
        if not headline:
            continue
        masked = scene.get("masked")
        easing = str(scene.get("easing", "")).strip().lower()
        if masked is False:
            missing.append("Scene %d disables the text mask" % (index + 1))
        if easing in ("", "linear"):
            missing.append("Scene %d has no non-linear entry easing" % (index + 1))
    if missing:
        return _result("MG-2.6-KINETIC", "Typography", "Text never just appears", "fail",
                       "; ".join(missing[:6]))
    return _result("MG-2.6-KINETIC", "Typography", "Text never just appears", "pass",
                   "All %d headline scenes have a masked, eased entrance." % len(scenes))


def check_easing(storyboard: dict) -> dict:
    problems = []
    for index, scene in enumerate(_scenes(storyboard)):
        name = str(scene.get("easing", "")).strip().lower()
        if not name:
            continue
        if name not in CURVES:
            problems.append("Scene %d uses unknown easing %r" % (index + 1, name))
        elif is_linear_like(name):
            problems.append("Scene %d uses linear easing, which the brief forbids" % (index + 1))
    style_easing = _style(storyboard).get("easing")
    if isinstance(style_easing, dict):
        for role, name in style_easing.items():
            if name not in CURVES:
                problems.append("Role %r uses unknown easing %r" % (role, name))
            elif is_linear_like(name):
                problems.append("Role %r uses linear easing" % role)
    if problems:
        return _result("MG-3.1-EASING", "Motion", "No linear interpolation", "fail",
                       "; ".join(problems[:6]))
    return _result("MG-3.1-EASING", "Motion", "No linear interpolation", "pass",
                   "%d cubic-Bezier curves in use; none linear-like." % len(CURVES))


def check_anticipation(storyboard: dict) -> dict:
    values = [scene.get("anticipation") for scene in _scenes(storyboard)]
    if not values or all(value is None for value in values):
        return _result("MG-3.2-ANTICIPATION", "Motion", "Anticipation", "not_applicable",
                       "Scenes do not declare anticipation; compile the brief to add it.")
    problems = []
    for index, value in enumerate(values):
        if value is None:
            continue
        try:
            amount = float(value)
        except (TypeError, ValueError):
            problems.append("Scene %d anticipation is not numeric" % (index + 1))
            continue
        if not 0.0 <= amount <= 0.25:
            problems.append("Scene %d anticipation %.2f outside 0..0.25" % (index + 1, amount))
    if problems:
        return _result("MG-3.2-ANTICIPATION", "Motion", "Anticipation", "fail", "; ".join(problems))
    active = sum(1 for value in values if value and float(value) > 0)
    return _result("MG-3.2-ANTICIPATION", "Motion", "Anticipation", "pass",
                   "%d/%d scenes declare a counter-move before entry." % (active, len(values)))


def check_follow_through(storyboard: dict) -> dict:
    scenes = _scenes(storyboard)
    staggers = [scene.get("stagger_frames") for scene in scenes]
    if not scenes or all(value is None for value in staggers):
        return _result("MG-3.3-FOLLOW-THROUGH", "Motion", "Follow-through and overlap",
                       "not_applicable", "Scenes do not declare stagger timing.")
    problems = []
    for index, value in enumerate(staggers):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 30:
            problems.append("Scene %d stagger_frames must be an integer 0..30" % (index + 1))
    if problems:
        return _result("MG-3.3-FOLLOW-THROUGH", "Motion", "Follow-through and overlap",
                       "fail", "; ".join(problems))
    average = sum(int(value or 0) for value in staggers) / len(staggers)
    return _result("MG-3.3-FOLLOW-THROUGH", "Motion", "Follow-through and overlap", "pass",
                   "Layers enter on a %.1f-frame stagger; none land together." % average)


def check_transitions(storyboard: dict) -> dict:
    scenes = _scenes(storyboard)
    if not scenes:
        return _result("MG-3.4-TRANSITIONS", "Editing", "Transition design", "not_applicable",
                       "Storyboard has no scenes.")
    names = [str(scene.get("transition_in", "none")).lower() for scene in scenes]
    names = ["cut" if name == "none" else name for name in names]
    problems = plan_issues(names, allow_legacy=False)
    for index, name in enumerate(names):
        if name in LEGACY_NAMES:
            problems.append(
                "Scene %d uses the legacy template transition %r; compile it to %r"
                % (index + 1, name, upgrade(name, _tone(storyboard)))
            )
    for index, scene in enumerate(scenes):
        requested = scene.get("transition_frames")
        if requested is None or names[index] == "cut":
            continue
        if isinstance(requested, bool) or not isinstance(requested, int) or not 0 <= requested <= 60:
            problems.append("Scene %d transition_frames must be 0..60" % (index + 1))
    if problems:
        return _result("MG-3.4-TRANSITIONS", "Editing", "Transition design", "fail",
                       "; ".join(problems[:6]), transitions=names)
    return _result("MG-3.4-TRANSITIONS", "Editing", "Transition design", "pass",
                   "%d scene edits: %s" % (len(names), ", ".join(sorted(set(names)))),
                   transitions=names)


def check_camera(storyboard: dict) -> dict:
    scenes = _scenes(storyboard)
    if not scenes:
        return _result("MG-3.5-CAMERA", "Camera", "Physical camera behaviour", "not_applicable",
                       "Storyboard has no scenes.")
    problems = []
    moves = []
    for index, scene in enumerate(scenes):
        value = scene.get("camera_motion", "static")
        try:
            moves.append(camera.normalize_move(value))
        except ValueError as exc:
            problems.append("Scene %d: %s" % (index + 1, exc))
    if problems:
        return _result("MG-3.5-CAMERA", "Camera", "Physical camera behaviour", "fail",
                       "; ".join(problems))
    moving = sum(1 for move in moves if move != "static")
    if len(scenes) > 2 and moving == 0:
        return _result("MG-3.5-CAMERA", "Camera", "Physical camera behaviour", "fail",
                       "Every shot is locked off; the camera is never treated as a physical object.")
    return _result("MG-3.5-CAMERA", "Camera", "Physical camera behaviour", "pass",
                   "%d/%d shots move (%s)" % (moving, len(moves), ", ".join(sorted(set(moves)))))


def check_beat_sync(storyboard: dict, beats: list[float] | None = None,
                    cue_times: list[float] | None = None) -> dict:
    if not beats:
        return _result("MG-4.1-BEAT-SYNC", "Audio", "Cuts land on the beat", "not_applicable",
                       "No beat grid supplied. Run motion_director.py --beats on the soundtrack to check this.")
    times = cue_times or []
    if not times:
        return _result("MG-4.1-BEAT-SYNC", "Audio", "Cuts land on the beat", "not_applicable",
                       "A beat grid exists but no cue times were supplied.")
    aligned = sum(1 for time in times if min(abs(time - beat) for beat in beats) <= 0.12)
    ratio = aligned / len(times)
    if ratio < 0.6:
        return _result("MG-4.1-BEAT-SYNC", "Audio", "Cuts land on the beat", "fail",
                       "%d/%d cues within 120 ms of a beat" % (aligned, len(times)))
    return _result("MG-4.1-BEAT-SYNC", "Audio", "Cuts land on the beat", "pass",
                   "%d/%d cues within 120 ms of a beat" % (aligned, len(times)))


def check_timeline(direction: dict | None) -> dict:
    if not isinstance(direction, dict):
        return _result("MG-5.1-TIMELINE", "Structure", "Timeline and rhythm", "not_applicable",
                       "No direction sheet supplied, so the timeline cannot be reviewed.")
    timeline = direction.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return _result("MG-5.1-TIMELINE", "Structure", "Timeline and rhythm", "fail",
                       "Direction sheet has no timeline.")
    problems = []
    cursor = 0.0
    for index, shot in enumerate(timeline):
        start = float(shot.get("start", -1))
        end = float(shot.get("end", -1))
        if abs(start - cursor) > 0.01:
            problems.append("Shot %d starts at %.2f, expected %.2f" % (index + 1, start, cursor))
        if end <= start:
            problems.append("Shot %d has no duration" % (index + 1))
        if float(shot.get("hold_seconds", 0)) <= 0:
            problems.append("Shot %d has no readable hold" % (index + 1))
        cursor = end
    if problems:
        return _result("MG-5.1-TIMELINE", "Structure", "Timeline and rhythm", "fail",
                       "; ".join(problems[:6]))
    return _result("MG-5.1-TIMELINE", "Structure", "Timeline and rhythm", "pass",
                   "%d shots, %.1fs total, contiguous and every shot holds." % (len(timeline), cursor))


def check_layers(direction: dict | None) -> dict:
    if not isinstance(direction, dict):
        return _result("MG-5.2-LAYERS", "Structure", "Layer hierarchy", "not_applicable",
                       "No direction sheet supplied.")
    layers = [str(layer.get("name", "")).lower() for layer in direction.get("layers", [])
              if isinstance(layer, dict)]
    required = ["background", "midground", "graphic", "text", "foreground", "ui"]
    missing = [name for name in required if name not in layers]
    if missing:
        return _result("MG-5.2-LAYERS", "Structure", "Layer hierarchy", "fail",
                       "Missing layers: " + ", ".join(missing))
    ordered = layers.index("background") < layers.index("midground") < layers.index("graphic") < layers.index("text")
    if not ordered:
        return _result("MG-5.2-LAYERS", "Structure", "Layer hierarchy", "fail",
                       "Layer order is not back-to-front: " + " > ".join(layers))
    return _result("MG-5.2-LAYERS", "Structure", "Layer hierarchy", "pass",
                   " > ".join(layers))


def check_placeholders(storyboard: dict) -> dict:
    hits = []
    for index, scene in enumerate(_scenes(storyboard)):
        text = _scene_text(scene).lower()
        for marker in PLACEHOLDER_MARKERS:
            if marker in text:
                hits.append("Scene %d contains %r" % (index + 1, marker))
    if hits:
        return _result("MG-5.3-PLACEHOLDER", "Content", "No placeholder copy", "fail",
                       "; ".join(hits[:6]))
    return _result("MG-5.3-PLACEHOLDER", "Content", "No placeholder copy", "pass",
                   "%d scenes contain real copy, no filler markers." % len(_scenes(storyboard)))


def check_density(storyboard: dict) -> dict:
    problems = []
    for index, scene in enumerate(_scenes(storyboard)):
        words = len(" ".join(str(scene.get(key, "")) for key in ("headline", "subhead")).split())
        if words > 45:
            problems.append("Scene %d shows %d words at once" % (index + 1, words))
        text_layers = sum(1 for key in ("eyebrow", "headline", "subhead", "caption")
                          if str(scene.get(key, "")).strip())
        if text_layers > 4:
            problems.append("Scene %d stacks %d text layers" % (index + 1, text_layers))
    if problems:
        return _result("MG-6.1-DENSITY", "Content", "One idea per frame", "fail",
                       "; ".join(problems[:6]))
    return _result("MG-6.1-DENSITY", "Content", "One idea per frame", "pass",
                   "Max %d words per frame; text layers capped."
                   % max([len(" ".join(str(scene.get(key, "")) for key in ("headline", "subhead")).split())
                          for scene in _scenes(storyboard)] or [0]))


def check_structure_limits(storyboard: dict) -> dict:
    scenes = _scenes(storyboard)
    problems = []
    if not 1 <= len(scenes) <= 100:
        problems.append("scene count %d outside 1..100" % len(scenes))
    total = 0.0
    for index, scene in enumerate(scenes):
        try:
            duration = float(scene.get("duration_seconds", 0))
        except (TypeError, ValueError):
            problems.append("Scene %d duration is not numeric" % (index + 1))
            continue
        if not 0 < duration <= 600:
            problems.append("Scene %d duration %.1fs outside 0..600" % (index + 1, duration))
        total += duration
    fps = int(storyboard.get("fps", 30) or 30)
    if total > 1000:
        problems.append("timeline is %.0fs, over the 1000s limit" % total)
    if total * fps > 30000:
        problems.append("timeline is %.0f frames, over the 30000-frame limit" % (total * fps))
    if problems:
        return _result("MG-6.2-LIMITS", "Technical", "Render limits", "fail", "; ".join(problems[:6]))
    return _result("MG-6.2-LIMITS", "Technical", "Render limits", "pass",
                   "%d scenes, %.1fs, %d frames" % (len(scenes), total, round(total * fps)))


def audit_storyboard(storyboard: dict, direction: dict | None = None,
                     beats: list[float] | None = None) -> dict:
    """Run every applicable check and return a structured report."""
    if not isinstance(storyboard, dict):
        raise ValueError("Storyboard must be a JSON object")
    checks = [
        check_tone(storyboard),
        check_resolution(storyboard),
        check_composition(storyboard),
        check_contrast(storyboard),
        check_grade(storyboard),
        check_typography(storyboard),
        check_kinetic_type(storyboard),
        check_easing(storyboard),
        check_anticipation(storyboard),
        check_follow_through(storyboard),
        check_transitions(storyboard),
        check_camera(storyboard),
        check_placeholders(storyboard),
        check_density(storyboard),
        check_structure_limits(storyboard),
        check_timeline(direction),
        check_layers(direction),
    ]
    cue_times = []
    if isinstance(direction, dict):
        for shot in direction.get("timeline", []):
            for cue in (shot.get("sound") or {}).get("cues", []):
                cue_times.append(float(shot.get("start", 0.0)) + float(cue.get("at", 0.0)))
    checks.append(check_beat_sync(storyboard, beats, cue_times))

    violations = [check for check in checks if check["status"] == "fail"]
    not_checked = [check for check in checks if check["status"] == "not_applicable"]
    passed = [check for check in checks if check["status"] == "pass"]

    if violations:
        statement = "MOTION SPEC: FAILED - %d violation(s) detected." % len(violations)
    else:
        statement = "MOTION SPEC: PASSED - No violations detected."

    return {
        "schema_version": 1,
        "statement": statement,
        "status": "failed" if violations else "passed",
        "summary": {
            "checks": len(checks),
            "passed": len(passed),
            "failed": len(violations),
            "not_applicable": len(not_checked),
        },
        "violations": violations,
        "not_checked": not_checked,
        "checks": checks,
        "verified_machine": [check["id"] for check in passed],
        "human_review_required": [
            "Aesthetic judgement and emotional impact",
            "Narration performance and voice quality",
            "Whether the transition serves the story in context",
            "Final review of the encoded file in motion, with sound",
        ],
    }


def _wrap(text: str, width: int = 96) -> list[str]:
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def format_report(report: dict) -> str:
    lines = [report["statement"], ""]
    summary = report["summary"]
    lines.append(
        "Checks: %d passed, %d failed, %d not applicable"
        % (summary["passed"], summary["failed"], summary["not_applicable"])
    )
    if report["violations"]:
        lines.append("")
        lines.append("Violations")
        for item in report["violations"]:
            lines.append("- [%s] %s" % (item["id"], item["title"]))
            for line in _wrap(item["detail"], 92):
                lines.append("  " + line)
    notices = [item for item in report["checks"] if item.get("notice")]
    if notices:
        lines.append("")
        lines.append("Notes")
        for item in notices:
            lines.append("- " + item["notice"])
    if report["not_checked"]:
        lines.append("")
        lines.append("Not checked")
        for item in report["not_checked"]:
            lines.append("- [%s] %s - %s" % (item["id"], item["title"], item["detail"]))
    if report["violations"]:
        lines.append("")
        lines.append("This artifact does not meet the professional motion-graphics spec yet.")
    else:
        lines.append("")
        lines.append("All applicable clauses passed. Aesthetic sign-off still requires human review.")
    return "\n".join(lines)
