#!/usr/bin/env python3
"""Command-line art director and motion-spec auditor.

Examples
--------
Compile a brief into a direction sheet and a render-ready storyboard::

    python video_studio/motion_director.py --brief brief.json --out-dir build

Audit an existing storyboard against the professional motion spec::

    python video_studio/motion_director.py --storyboard storyboard.json --tone cinematic

Analyse a soundtrack and print its beat grid::

    python video_studio/motion_director.py --beats soundtrack.wav

Exit codes: 0 clean, 1 violations, 2 invalid input, 3 cannot run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from motion import beat, compliance, direction, palette, transitions, typography  # noqa: E402


def _fail(message: str, code: int = 2) -> int:
    print("motion_director: " + message, file=sys.stderr)
    return code


def _write_outputs(direction_sheet: dict, storyboard: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "direction": out_dir / "direction.json",
        "storyboard": out_dir / "storyboard.json",
        "timeline": out_dir / "timeline.txt",
        "report_txt": out_dir / "motion-report.txt",
        "report_json": out_dir / "motion-report.json",
    }
    direction.write_json(paths["direction"], direction_sheet)
    direction.write_json(paths["storyboard"], storyboard)
    paths["timeline"].write_text(direction.format_timeline(direction_sheet) + "\n", encoding="utf-8")
    return {name: str(path) for name, path in paths.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Professional motion-graphics direction and audit.")
    parser.add_argument("--brief", help="Brief JSON to direct into a storyboard.")
    parser.add_argument("--storyboard", help="Existing storyboard to upgrade and audit.")
    parser.add_argument("--tone", help="Override tone: " + ", ".join(sorted(palette.TONES)))
    parser.add_argument("--out-dir", default="motion-build", help="Directory for generated files.")
    parser.add_argument("--direction", help="Direction sheet to audit against.")
    parser.add_argument("--beats", help="WAV file to analyse for a beat grid.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--catalogue", action="store_true", help="Print the easing, transition, camera and type catalogues.")
    parser.add_argument("--no-upgrade", action="store_true", help="Keep legacy transitions instead of upgrading them.")
    args = parser.parse_args(argv)

    if args.catalogue:
        payload = {
            "tones": {name: palette.style_block(name) for name in sorted(palette.TONES)},
            "fonts": typography.available_fonts(),
            "transitions": transitions.catalogue(),
            "type_scale_4k": {name: role.size_px for name, role in typography.type_scale(3840).items()},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # --beats is a standalone report only when there is nothing to direct.
    # With --brief or --storyboard it becomes the beat source for the audit.
    if args.beats and not args.brief and not args.storyboard:
        try:
            analysis = beat.analyze(args.beats)
        except (ValueError, OSError) as exc:
            return _fail(str(exc))
        if args.json:
            print(json.dumps(analysis, ensure_ascii=False, indent=2))
        else:
            print(beat.report(args.beats))
        return 0

    if not args.brief and not args.storyboard:
        parser.print_help()
        return 2

    out_dir = Path(args.out_dir)
    beats: list[float] = []
    if args.beats:
        try:
            beats = beat.analyze(args.beats)["beats"]
        except (ValueError, OSError) as exc:
            return _fail(str(exc))

    try:
        if args.brief:
            brief = direction.load(args.brief)
            compiled = direction.compile_brief(brief, upgrade_legacy=not args.no_upgrade)
            sheet, storyboard = compiled["direction"], compiled["storyboard"]
            sheet["beats"] = {"count": len(beats), "source": args.beats} if beats else None
        else:
            raw = direction.load(args.storyboard)
            storyboard = direction.upgrade_storyboard(raw, tone=args.tone)
            sheet = direction.summarize_storyboard(storyboard, args.tone)
    except (direction.BriefError, ValueError) as exc:
        return _fail(str(exc))

    if args.direction:
        try:
            sheet = direction.load(args.direction)
        except direction.BriefError as exc:
            return _fail(str(exc))

    report = compliance.audit_storyboard(storyboard, sheet, beats=beats or None)
    paths = _write_outputs(sheet, storyboard, out_dir)
    Path(paths["report_txt"]).write_text(compliance.format_report(report) + "\n", encoding="utf-8")
    direction.write_json(paths["report_json"], report)

    if args.json:
        print(json.dumps({"report": report, "files": paths}, ensure_ascii=False, indent=2))
    else:
        print(direction.format_timeline(sheet))
        print()
        print(compliance.format_report(report))
        print()
        print("Written:")
        for name, path in paths.items():
            print("  %-12s %s" % (name, path))

    if not typography.available_fonts()["complete"]:
        return 3
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
