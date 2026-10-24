#!/usr/bin/env python3
"""Check the motion template library against its own rules.

The library in ``video_studio/motion/library.mjs`` claims five things:

``M1 MAP``
    ``agents/motion_templates.json`` - the map the motion agent reads - is the
    code's own output, not a hand-written copy. A stale map is how an agent ends
    up choosing a template that no longer exists.

``M2 SCHEMA``
    Every template declares a purpose, the situations it serves, the situations
    it must not be used for, a duration band, its required props, its regions and
    a sample that the self-check can render.

``M3 REGION``
    Every region is inside the frame and clear of the two areas that belong to
    something else: the live column on the right and the subtitle band at the
    foot. This is the structural half of the owner's "no overlapping text" note -
    a template cannot draw where the ticker or the caption is.

``M4 REACH``
    Every situation names templates that exist, and every template is reachable
    from at least one situation. An unreachable template is dead weight.

``M5 SELFCHECK``
    Every template renders inside its region, and moves. Measured on a real
    canvas by ``library_cli.mjs --selfcheck``.

``M6 USED``
    At least one film draws through the library. A catalogue nothing calls is a
    document, not a system.

``M7 CAMERA``
    No film shakes the frame. The owner rejected a moving camera twice - "dont
    shake the camers", "these are unproffesional" - and the effect kept coming
    back in different places: a camera function, a beat push, a handheld noise
    layer. This rule fails the build when the identifiers come back.

    python tools/check_motion_library.py
    python tools/check_motion_library.py --json
    python tools/check_motion_library.py --skip-selfcheck
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "video_studio"
CLI = STUDIO / "motion" / "library_cli.mjs"
AGENT_MAP = ROOT / "agents" / "motion_templates.json"
FILMS = STUDIO / "films"
MOTION = STUDIO / "motion"

#: Patterns that mean somebody is shaking the picture again. Element-level
#: motion (a panel drifting inside the frame) is allowed; moving the frame itself
#: is not.
SHAKE_PATTERNS = (
    (r"\bshake[XY]\b", "a hand-held offset"),
    (r"\bhandheld\b|\bhand-held\b", "a hand-held camera layer"),
    (r"rotate\(\s*(?:noise\d?|Math\.(?:sin|cos))", "a rotation driven by noise or a sine"),
)

NODE = shutil.which("node")

REQUIRED_TEMPLATE_FIELDS = (
    "id", "name", "purpose", "when", "avoid", "minSeconds", "maxSeconds",
    "needs", "regions", "cost", "sample",
)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def fail(self, rule: str, message: str) -> None:
        self.problems.append(f"{rule} {message}")

    def note(self, message: str) -> None:
        self.notes.append(message)


def run_node(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, str(CLI), *args], cwd=str(STUDIO), capture_output=True, text=True, check=False,
    )


def load_map(report: Report) -> dict | None:
    if not AGENT_MAP.is_file():
        report.fail("M1", "agents/motion_templates.json is missing")
        return None
    try:
        return json.loads(AGENT_MAP.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report.fail("M1", f"agents/motion_templates.json is not JSON: {error}")
        return None


def check_map_current(report: Report, published: dict | None) -> None:
    if NODE is None:
        report.note("node is not installed; the map was not regenerated")
        return
    probe = run_node(["--agent-map"])
    if probe.returncode != 0:
        report.fail("M1", f"the library could not describe itself: {probe.stderr.strip()[:300]}")
        return
    fresh = json.loads(probe.stdout)
    if published != fresh:
        report.fail(
            "M1",
            "agents/motion_templates.json does not match the code. "
            "Run: node video_studio/motion/library_cli.mjs --write-agent-map",
        )


def check_schema(report: Report, catalogue: dict) -> None:
    seen: set[str] = set()
    for template in catalogue.get("templates", []):
        ident = template.get("id", "<no id>")
        if ident in seen:
            report.fail("M2", f"duplicate template id {ident}")
        seen.add(ident)
        for field in REQUIRED_TEMPLATE_FIELDS:
            if field not in template:
                report.fail("M2", f"{ident} has no {field}")
        if not template.get("purpose", "").strip():
            report.fail("M2", f"{ident} has an empty purpose")
        if not template.get("when"):
            report.fail("M2", f"{ident} is not attached to any situation")
        if not template.get("avoid"):
            report.fail("M2", f"{ident} does not say when not to use it")
        low, high = template.get("minSeconds"), template.get("maxSeconds")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            report.fail("M2", f"{ident} has no numeric duration band")
        elif not 0 < low <= high <= 12:
            report.fail("M2", f"{ident} has an impossible band {low}-{high}s")
        if template.get("cost") not in {"low", "medium", "high"}:
            report.fail("M2", f"{ident} has an unknown cost {template.get('cost')!r}")
        if not template.get("regions"):
            report.fail("M2", f"{ident} owns no region")
        if not isinstance(template.get("sample"), dict):
            report.fail("M2", f"{ident} has no renderable sample")
            continue
        for need in template.get("needs", []):
            if need not in template["sample"]:
                report.fail("M2", f"{ident} needs {need} but its sample does not supply it")


def overlaps(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]
    )


def check_regions(report: Report, catalogue: dict) -> None:
    regions = catalogue.get("regions", {})
    reserved = catalogue.get("reserved", {})
    for name, box in regions.items():
        if box["x"] < 0 or box["y"] < 0 or box["x"] + box["w"] > 1.0001 or box["y"] + box["h"] > 1.0001:
            report.fail("M3", f"region {name} is outside the frame")
        for reserved_name, keep_out in reserved.items():
            if overlaps(box, keep_out):
                report.fail("M3", f"region {name} overlaps the reserved {reserved_name} area")
    for template in catalogue.get("templates", []):
        for region in template.get("regions", []):
            if region not in regions:
                report.fail("M3", f"{template.get('id')} claims unknown region {region}")


def check_reach(report: Report, catalogue: dict) -> None:
    ids = {template.get("id") for template in catalogue.get("templates", [])}
    wanted: set[str] = set()
    for situation, spec in catalogue.get("situations", {}).items():
        names = spec.get("wants", [])
        if not names:
            report.fail("M4", f"situation {situation} wants nothing")
        for name in names:
            if name not in ids:
                report.fail("M4", f"situation {situation} wants unknown template {name}")
            wanted.add(name)
    for missing in sorted(ids - wanted):
        report.fail("M4", f"{missing} is not the answer to any situation")


def check_selfcheck(report: Report) -> None:
    if NODE is None:
        report.note("node is not installed; templates were not rendered")
        return
    probe = run_node(["--selfcheck"])
    if probe.returncode != 0:
        detail = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else probe.stderr.strip()
        report.fail("M5", f"the templates do not render inside their regions: {detail[:300]}")
        return
    try:
        payload = json.loads(probe.stdout)
    except json.JSONDecodeError:
        report.fail("M5", "the self-check did not return JSON")
        return
    for failure in payload.get("failures", []):
        report.fail("M5", failure)
    report.note(f"{payload.get('cases', 0)} template/region cases rendered and measured")


def check_used(report: Report) -> None:
    if not FILMS.is_dir():
        report.fail("M6", "video_studio/films is missing")
        return
    users = [
        path.name for path in sorted(FILMS.glob("*.mjs"))
        if "motion/library.mjs" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    if not users:
        report.fail("M6", "no film draws through the motion library yet")
    else:
        report.note("drawn through the library by: " + ", ".join(users))


def check_camera(report: Report) -> None:
    """The frame does not move. Nothing shakes the camera."""
    scanned = 0
    for directory in (FILMS, MOTION):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.mjs")):
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(("//", "*", "/*")):
                    continue
                for pattern, what in SHAKE_PATTERNS:
                    if re.search(pattern, line):
                        report.fail("M7", f"{path.name}:{line_number} has {what}: {stripped[:90]}")
    report.note(f"{scanned} motion sources scanned for camera shake")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--skip-selfcheck", action="store_true", help="do not render the templates")
    args = parser.parse_args(argv)

    report = Report()
    catalogue = load_map(report)
    if catalogue is not None:
        check_map_current(report, catalogue)
        check_schema(report, catalogue)
        check_regions(report, catalogue)
        check_reach(report, catalogue)
        if not args.skip_selfcheck:
            check_selfcheck(report)
        check_used(report)
        check_camera(report)

    if args.json:
        print(json.dumps({
            "passed": not report.problems,
            "problems": report.problems,
            "notes": report.notes,
        }, indent=2))
    elif report.problems:
        print("MOTION LIBRARY: FAILED")
        for problem in report.problems:
            print(f"  {problem}")
        for note in report.notes:
            print(f"  note: {note}")
    else:
        print("MOTION LIBRARY: PASSED - every template declares its use, stays in its region, and is reachable.")
        for note in report.notes:
            print(f"  {note}")
    return 0 if not report.problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
