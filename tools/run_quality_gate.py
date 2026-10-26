#!/usr/bin/env python3
"""Portable local quality gate for Windows, Linux, and macOS.

Default mode runs syntax checks, the full unittest suite, renderer JavaScript
syntax validation when Node.js is installed, and the device-capability probe.
Pass --render-smoke to require FFmpeg, FFprobe, Node.js, installed Puppeteer
dependencies, and actual landscape + vertical MP4 renders. Pass --urdu-voice-smoke
to synthesize real Urdu-English narration, render a vertical MP4, and run strict
technical audio/video QA. That option requires a current human-approved local voice profile.
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
        "--urdu-voice-smoke",
        action="store_true",
        help="render an actual Urdu-English narrated Shorts MP4 and run strict technical audio/video QA; requires a current voice approval in config.json",
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
        [sys.executable, "-m", "compileall", "-q", "dashboard.py", "agent.py", "app", "ui",
         "queue_store.py", "app_config.py", "bridge", "agents", "video_studio",
         "product_studio", "tools"],
        timeout=180,
    ))
    # A film can pass every picture check and still be unwatchable because of its
    # narration. That check lives with the film build; this one proves the
    # narration gate itself still works.
    results.append(run_step(
        "Narration gate (speed, air, delivery level)",
        [sys.executable, "-m", "unittest", "tests.test_check_narration", "tests.test_voiceover"],
        timeout=300,
    ))
    results.append(run_step(
        "North Star invariants (free, local, confined)",
        [sys.executable, "tools/check_invariants.py"],
        timeout=120,
    ))
    # Structure rots silently: a run flag reappearing, a helper copied instead of
    # shared, an import pointing the wrong way. This check makes that fail.
    results.append(run_step(
        "Code structure (layers, state, duplication, naming)",
        [sys.executable, "tools/check_structure.py"],
        timeout=120,
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
                stream_output=True,
            )
            results.append(result)
            if result.get("error") == "interrupted by user":
                # Do not launch more test processes after an explicit interruption.
                break

    node = shutil.which("node")
    if node:
        results.append(run_step("Renderer JavaScript syntax", [node, "--check", "video_studio/render.js"], timeout=30))
        # Chunked rendering is an assumption, not a law: the same frame number has
        # to produce the same pixels in any process and after any lead-in. This
        # renders a window three times - twice identically, once behind a longer
        # lead-in - and compares the bytes.
        results.append(run_step(
            "Render repeatability (same frame, three renders)",
            [sys.executable, "tools/check_determinism.py", "--json"],
            timeout=300,
        ))
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

    if args.urdu_voice_smoke:
        # Unlike --render-smoke, this test intentionally uses the real local TTS
        # model and requires the user-reviewed voice approval to remain current.
        earlier_failures = [result for result in results if result["status"] == "FAIL"]
        if earlier_failures:
            results.append(skipped(
                "Urdu-English narrated MP4 smoke",
                "Earlier syntax, unit-test, renderer-syntax, or capability checks failed; fix those first.",
            ))
        else:
            free_bytes = shutil.disk_usage(ROOT).free
            minimum_free_bytes = 1024 * 1024 * 1024
            missing = [tool for tool in ("node", "ffmpeg", "ffprobe") if not shutil.which(tool)]
            if not (ROOT / "video_studio" / "node_modules" / "puppeteer").exists():
                missing.append("video_studio/node_modules/puppeteer (run npm install in video_studio)")
            if free_bytes < minimum_free_bytes:
                results.append({
                    "name": "Urdu-English narrated MP4 smoke",
                    "status": "FAIL",
                    "reason": (
                        "At least 1 GiB free disk space is required before rendering; "
                        f"only {free_bytes // (1024 * 1024)} MiB is free."
                    ),
                })
            elif missing:
                results.append({
                    "name": "Urdu-English narrated MP4 smoke",
                    "status": "FAIL",
                    "reason": "Missing required renderer dependencies: " + ", ".join(missing),
                })
            else:
                approval_code = (
                    "import sys; from pathlib import Path; "
                    "sys.path.insert(0, str((Path.cwd() / 'video_studio').resolve())); "
                    "from voice_backends import load_project_config, require_urdu_voice_human_approval; "
                    "cfg=load_project_config(Path.cwd()); "
                    "require_urdu_voice_human_approval(cfg); "
                    "print('Current approved voice profile:', cfg['video_studio']['urdu_voice_approved_profile_sha256'])"
                )
                approval = run_step(
                    "Verify current human-approved Urdu voice profile",
                    [sys.executable, "-c", approval_code],
                    timeout=60,
                )
                results.append(approval)
                if approval["status"] != "PASS":
                    results.append(skipped(
                        "Urdu-English narrated MP4 render and strict QA",
                        "The configured voice profile is not approved or its approval fingerprint is stale.",
                    ))
                else:
                    output_dir = ROOT / "video_studio" / "outputs"
                    stem = "ci-smoke-urdu"
                    video = output_dir / (stem + ".mp4")
                    qc_report = output_dir / (stem + ".qc.json")
                    # Remove only fixed, tool-owned smoke artifacts so old files
                    # cannot make a failed render appear to have succeeded.
                    for suffix in (
                        ".mp4", ".silent.mp4", ".srt", ".vtt",
                        ".capabilities.json", ".qc.json",
                    ):
                        (output_dir / (stem + suffix)).unlink(missing_ok=True)
                    render = run_step(
                        "Urdu-English narrated vertical Shorts MP4 render",
                        [
                            sys.executable, "video_studio/studio.py",
                            "--storyboard", "storyboard.smoke-urdu.json",
                            "--output", "outputs/ci-smoke-urdu.mp4",
                            "--language", "ur-en", "--with-voice",
                        ],
                        timeout=1200,
                    )
                    results.append(render)
                    if render["status"] == "PASS":
                        audit = run_step(
                            "Strict technical audio/video audit for Urdu MP4",
                            [
                                sys.executable, "video_studio/quality_audit.py", str(video),
                                "--strict", "--max-black-seconds", "0.25",
                                "--max-freeze-seconds", "3.0", "--max-silence-seconds", "1.5",
                                "--report", str(qc_report),
                            ],
                            timeout=600,
                        )
                        results.append(audit)
                    else:
                        results.append(skipped(
                            "Strict technical audio/video audit for Urdu MP4",
                            "The narrated render failed; no stale output is audited as the new result.",
                        ))
                    for suffix in (".mp4", ".srt", ".vtt", ".capabilities.json", ".qc.json"):
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
