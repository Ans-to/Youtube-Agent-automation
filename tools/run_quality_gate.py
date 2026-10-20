#!/usr/bin/env python3
"""Portable local quality gate for Windows, Linux, and macOS.

Default mode runs syntax checks, the full unittest suite, renderer JavaScript
syntax validation when Node.js is installed, and the device-capability probe.
Pass --render-smoke to require FFmpeg, FFprobe, Node.js, installed Puppeteer
dependencies, and actual landscape + vertical MP4 renders.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(
    name: str,
    command: list[str],
    *,
    timeout: int = 300,
    stream_output: bool = False,
) -> dict:
    started = time.monotonic()
    print(f"\n=== {name} ===", flush=True)
    process = None
    try:
        if stream_output:
            # Inherit the console so long-running checks show progress instead
            # of appearing frozen while subprocess.run buffers all output.
            process = subprocess.Popen(command, cwd=ROOT)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
        else:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)
            returncode = result.returncode

        status = "PASS" if returncode == 0 else "FAIL"
        return {
            "name": name,
            "status": status,
            "returncode": returncode,
            "duration_seconds": round(time.monotonic() - started, 2),
            "command": command,
        }
    except subprocess.TimeoutExpired:
        print(f"FAIL: timed out after {timeout} seconds", file=sys.stderr)
        return {
            "name": name,
            "status": "FAIL",
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 2),
            "command": command,
            "error": f"timeout after {timeout} seconds",
        }
    except KeyboardInterrupt:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        print("INTERRUPTED by user; this step is not marked PASS.", file=sys.stderr)
        return {
            "name": name,
            "status": "FAIL",
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 2),
            "command": command,
            "error": "interrupted by user",
        }


def skipped(name: str, reason: str) -> dict:
    print(f"\n=== {name}: SKIP ===\n{reason}")
    return {"name": name, "status": "SKIP", "reason": reason}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--render-smoke",
        action="store_true",
        help="also render and validate actual landscape and vertical MP4 smoke tests",
    )
    parser.add_argument(
        "--report",
        default="",
        help="optional path for a JSON report (relative paths resolve from the repository root)",
    )
    args = parser.parse_args()
    results = []

    results.append(run_step(
        "Python syntax compilation",
        [sys.executable, "-m", "compileall", "-q", "dashboard.py", "agent.py", "queue_store.py", "bridge", "agents", "video_studio", "product_studio", "tools"],
        timeout=180,
    ))
    test_files = sorted((ROOT / "tests").glob("test_*.py"))
    if not test_files:
        results.append({
            "name": "Full unit test suite",
            "status": "FAIL",
            "reason": "No tests/test_*.py modules were found.",
        })
    else:
        for test_file in test_files:
            result = run_step(
                "Unit tests: " + test_file.name,
                [
                    sys.executable, "-m", "unittest", "discover",
                    "-s", "tests", "-p", test_file.name, "-v",
                ],
                timeout=900,
                # Capture per-test chatter and print it only when the module exits.
                # This avoids fragile interleaved console writes on Windows PowerShell.
                stream_output=False,
            )
            results.append(result)
            if result.get("error") == "interrupted by user":
                # Do not launch more test processes after an explicit interruption.
                break

    node = shutil.which("node")
    if node:
        results.append(run_step("Renderer JavaScript syntax", [node, "--check", "video_studio/render.js"], timeout=30))
    elif args.render_smoke:
        results.append({"name": "Renderer JavaScript syntax", "status": "FAIL", "reason": "Node.js is required for --render-smoke"})
    else:
        results.append(skipped("Renderer JavaScript syntax", "Node.js is not installed; Python tests still ran."))

    results.append(run_step(
        "Device capability profile",
        [sys.executable, "video_studio/studio.py", "--print-capabilities"],
        timeout=30,
    ))

    if args.render_smoke:
        # These tiny smoke videos validate rendering, not the local TTS model.
        # Explicit English allows the renderer smoke test to stay offline and
        # avoids accidentally requiring an Urdu TTS model just to test visuals.
        free_bytes = shutil.disk_usage(ROOT).free
        minimum_free_bytes = 1024 * 1024 * 1024
        if free_bytes < minimum_free_bytes:
            results.append({
                "name": "Actual MP4 render smoke tests",
                "status": "FAIL",
                "reason": (
                    "At least 1 GiB free disk space is required before rendering; "
                    f"only {free_bytes // (1024 * 1024)} MiB is free. Free disk space and retry."
                ),
            })
        else:
            missing = [tool for tool in ("node", "ffmpeg", "ffprobe") if not shutil.which(tool)]
            if not (ROOT / "video_studio" / "node_modules" / "puppeteer").exists():
                missing.append("video_studio/node_modules/puppeteer (run npm install in video_studio)")
            if missing:
                results.append({
                    "name": "Actual MP4 render smoke tests",
                    "status": "FAIL",
                    "reason": "Missing required renderer dependencies: " + ", ".join(missing),
                })
            else:
                results.append(run_step(
                    "Landscape MP4 render smoke",
                    [sys.executable, "video_studio/studio.py", "--storyboard", "storyboard.smoke.json", "--output", "outputs/ci-smoke.mp4", "--language", "en"],
                    timeout=1200,
                ))
                results.append(run_step(
                    "Vertical Shorts MP4 render smoke",
                    [sys.executable, "video_studio/studio.py", "--storyboard", "storyboard.smoke-shorts.json", "--output", "outputs/ci-smoke-shorts.mp4", "--language", "en"],
                    timeout=1200,
                ))
                output_dir = ROOT / "video_studio" / "outputs"
                for stem in ("ci-smoke", "ci-smoke-shorts"):
                    for suffix in (".mp4", ".srt", ".vtt", ".capabilities.json"):
                        artifact = output_dir / (stem + suffix)
                        results.append({
                            "name": f"Output integrity: {artifact.relative_to(ROOT)}",
                            "status": "PASS" if artifact.is_file() and artifact.stat().st_size > 0 else "FAIL",
                            "path": str(artifact.relative_to(ROOT)),
                        })

    failures = [result for result in results if result["status"] == "FAIL"]
    report = {
        "schema_version": 1,
        "repository_root": str(ROOT),
        "completed_at_epoch": time.time(),
        "overall_status": "FAIL" if failures else "PASS",
        "summary": {
            "passed": sum(result["status"] == "PASS" for result in results),
            "failed": len(failures),
            "skipped": sum(result["status"] == "SKIP" for result in results),
        },
        "results": results,
    }
    print("\n=== QUALITY GATE SUMMARY ===")
    print(json.dumps(report["summary"], indent=2))
    print("OVERALL:", report["overall_status"])
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Report:", report_path)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
