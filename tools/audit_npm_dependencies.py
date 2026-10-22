#!/usr/bin/env python3
"""Fail the build on vulnerable npm dependencies, without failing on a flaky registry.

`npm audit --audit-level=high` conflates two very different outcomes:

* the advisory service answered and found high/critical vulnerabilities;
* the advisory service could not be reached at all.

Both produce a non-zero exit code, so a network blip turns into a red security
step and looks identical to a real finding. That is how a security gate loses
credibility and gets disabled. This wrapper separates the two cases:

* findings at or above the threshold always exit non-zero, with the advisory IDs;
* an unreachable advisory service exits ``EXIT_UNAVAILABLE`` (a distinct code) and
  prints an explicit "AUDIT UNAVAILABLE" line, so the caller can decide whether
  to warn or to fail closed (``--require-service``).

Only the audit *service* is retried. A vulnerability is never retried away.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time

EXIT_GATE_FAILED = 1
EXIT_UNAVAILABLE = 3

SEVERITY_ORDER = ["info", "low", "moderate", "high", "critical"]


def severity_rank(name: str) -> int:
    try:
        return SEVERITY_ORDER.index(str(name).strip().lower())
    except ValueError:
        return 0


def parse_audit_json(payload: str) -> dict:
    """Return the parsed npm audit report, or raise ValueError if it is not one.

    ``npm audit --json`` emits a JSON document even when it exits non-zero for
    findings. When the registry is unreachable it instead writes an error object
    or nothing at all, which is what we must not mistake for a clean audit.
    """
    text = (payload or "").strip()
    if not text:
        raise ValueError("npm audit produced no JSON output")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("npm audit output was not JSON: " + str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("npm audit JSON was not an object")
    if data.get("error"):
        error = data["error"]
        detail = error.get("summary") or error.get("detail") if isinstance(error, dict) else str(error)
        raise ValueError("npm audit reported an error: " + str(detail))
    if "vulnerabilities" not in data and "metadata" not in data:
        raise ValueError("npm audit JSON had no vulnerabilities or metadata section")
    return data


def blocking_advisories(report: dict, minimum: str = "high") -> list[dict]:
    """Return the advisories at or above ``minimum``, most severe first."""
    floor = severity_rank(minimum)
    found: list[dict] = []

    for name, entry in (report.get("vulnerabilities") or {}).items():
        if not isinstance(entry, dict):
            continue
        severity = entry.get("severity", "info")
        if severity_rank(severity) < floor:
            continue
        via = entry.get("via") or []
        advisories = []
        for item in via:
            if isinstance(item, dict):
                advisories.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "severity": item.get("severity", severity),
                    "range": item.get("range", ""),
                })
            elif isinstance(item, str):
                advisories.append({"title": item, "url": "", "severity": severity, "range": ""})
        found.append({
            "package": name,
            "severity": severity,
            "range": entry.get("range", ""),
            "fix_available": entry.get("fixAvailable", False),
            "advisories": advisories,
        })

    found.sort(key=lambda item: severity_rank(item["severity"]), reverse=True)
    return found


def run_audit(directory: str, timeout: int, attempts: int, retry_delay: float) -> tuple[dict | None, str]:
    """Run npm audit, retrying only transport failures. Returns (report, error)."""
    npm = shutil.which("npm")
    if not npm:
        return None, "npm is not installed"
    command = [npm, "audit", "--json", "--audit-level=high", f"--fetch-timeout={timeout * 1000 // 2}"]
    last_error = "no attempt made"
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                command,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = f"npm audit timed out after {timeout}s"
        else:
            try:
                return parse_audit_json(result.stdout), ""
            except ValueError as exc:
                last_error = str(exc)
                # A parse failure can also mean findings plus noise on stderr;
                # only treat it as transport trouble when there are no findings.
        if attempt < attempts:
            delay = retry_delay * (2 ** (attempt - 1))
            print(f"npm audit attempt {attempt}/{attempts} unavailable ({last_error}); retrying in {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)
    return None, last_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="video_studio", help="directory holding package.json")
    parser.add_argument("--minimum", default="high", choices=SEVERITY_ORDER, help="lowest blocking severity")
    parser.add_argument("--timeout", type=int, default=45, help="seconds per npm audit attempt")
    parser.add_argument("--attempts", type=int, default=3, help="attempts before giving up on the service")
    parser.add_argument("--retry-delay", type=float, default=5.0, help="base backoff in seconds")
    parser.add_argument(
        "--require-service",
        action="store_true",
        help="fail when the advisory service is unreachable instead of only warning",
    )
    args = parser.parse_args(argv)

    report, error = run_audit(args.directory, args.timeout, args.attempts, args.retry_delay)

    if report is None:
        print(f"AUDIT UNAVAILABLE: could not read the npm advisory service ({error}).", file=sys.stderr)
        print("No vulnerability verdict was produced; this is a transport failure, not a clean result.", file=sys.stderr)
        return EXIT_UNAVAILABLE if args.require_service else 0

    advisories = blocking_advisories(report, args.minimum)
    counts = (report.get("metadata") or {}).get("vulnerabilities") or {}
    if not advisories:
        summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()) if count) or "none"
        print(f"PASS: no {args.minimum}-or-higher vulnerabilities ({summary})")
        return 0

    print(f"FAIL: {len(advisories)} package(s) at {args.minimum} or higher", file=sys.stderr)
    for item in advisories:
        fix = item["fix_available"]
        fix_note = "fix available" if fix is True else ("no fix" if fix is False else f"fix: {fix}")
        print(f"  {item['severity']:>8}  {item['package']} {item['range']}  ({fix_note})", file=sys.stderr)
        for advisory in item["advisories"]:
            if advisory["title"]:
                print(f"            {advisory['title']} {advisory['url']}".rstrip(), file=sys.stderr)
    return EXIT_GATE_FAILED


if __name__ == "__main__":
    sys.exit(main())
