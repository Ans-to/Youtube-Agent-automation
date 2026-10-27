#!/usr/bin/env python3
"""Turn the Nokia film's real shot clock into its five-section score plan.

The optional WAV is music only: effects must remain on a separate bus for review.
The procedural moods are a starting point, not proof of a finished mix's level,
style or intelligibility. The source script and its timings are never altered.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PROFILE = Path(__file__).resolve().parent / "films" / "nokia_music.json"


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a finite number") from None
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def build_plan(starts: list[dict], profile: dict) -> dict:
    """Require a complete, continuous, ordered clock before deriving music cues."""
    if not isinstance(starts, list) or not starts:
        raise ValueError("the shot clock must be a non-empty array")
    sections = profile.get("sections") if isinstance(profile, dict) else None
    if not isinstance(sections, list) or not sections:
        raise ValueError("the music profile has no sections")
    by_scene: dict[int, list[float]] = {}
    seen_ids = set()
    last_end = 0.0
    last_scene = 0
    for i, row in enumerate(starts):
        if not isinstance(row, dict):
            raise ValueError(f"shot {i + 1} must be an object")
        shot = row.get("id")
        scene = row.get("scene")
        if not isinstance(shot, str) or not shot.strip() or shot in seen_ids:
            raise ValueError(f"shot {i + 1} has a missing or duplicate id")
        if isinstance(scene, bool) or not isinstance(scene, int) or scene < 1:
            raise ValueError(f"{shot}: scene must be a positive integer")
        start, end = _number(row.get("start"), "start"), _number(row.get("end"), "end")
        if start < 0 or end <= start or abs(start - last_end) > 0.002:
            raise ValueError(f"{shot}: shot clock has a gap, overlap, or invalid duration")
        if scene < last_scene:
            raise ValueError(f"{shot}: scenes are out of order")
        if scene not in by_scene:
            by_scene[scene] = [start, end]
        else:
            by_scene[scene][1] = end
        seen_ids.add(shot)
        last_end, last_scene = end, scene

    output = []
    covered: list[int] = []
    for entry in sections:
        if not isinstance(entry, dict):
            raise ValueError("invalid music section")
        scene_range = entry.get("scenes")
        if (not isinstance(scene_range, list) or len(scene_range) != 2
                or any(isinstance(n, bool) or not isinstance(n, int) for n in scene_range)
                or scene_range[0] < 1 or scene_range[1] < scene_range[0]):
            raise ValueError("invalid scene range in music profile")
        first, last = scene_range
        required = list(range(first, last + 1))
        if any(scene not in by_scene for scene in required):
            raise ValueError(f"{entry.get('id')}: one or more scenes are missing from the clock")
        for key in ("id", "style", "score_mood", "direction"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"music section is missing {key}")
        covered.extend(required)
        output.append({**entry, "start": by_scene[first][0], "end": by_scene[last][1]})
    if covered != sorted(by_scene):
        raise ValueError("music sections must cover each scene exactly once and in order")
    return {
        "schema_version": 1,
        "film": profile.get("film"),
        "duration_seconds": last_end,
        "sections": output,
        "audio_targets": profile.get("audio_targets", {}),
        "note": "Scene times come from the supplied shot clock; levels must be measured on the final master and stems.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starts", required=True, help="shot clock from nokia_empire.mjs --starts")
    parser.add_argument("--plan", required=True, help="output JSON plan")
    parser.add_argument("--score", help="optional music-only WAV generated from this plan (requires numpy)")
    args = parser.parse_args(argv)
    try:
        starts = json.loads(Path(args.starts).read_text(encoding="utf-8"))
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        plan = build_plan(starts, profile)
        if args.score:
            try:
                from . import score
            except ImportError:
                import score
            sections = [(s["score_mood"], s["start"], s["end"]) for s in plan["sections"]]
            # Do not combine transition effects with the music bed; they need a
            # separate, independently measurable bus in the final mix.
            audio = score.build(plan["duration_seconds"], sections, stereo=True)
            target = Path(args.score)
            target.parent.mkdir(parents=True, exist_ok=True)
            score.write_wav(target, audio)
        path = Path(args.plan)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, ImportError, json.JSONDecodeError) as exc:
        print(f"NOKIA MUSIC PLAN FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"NOKIA MUSIC PLAN: {len(plan['sections'])} sections, {plan['duration_seconds']:.3f}s -> {args.plan}")
    if args.score:
        print(f"Music-only procedural draft: {args.score}. Mix, meter and listen before approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
