#!/usr/bin/env python3
"""Say whether a brief can be published before a single frame is drawn.

A ten-film batch taught this the expensive way. The first pass paid for nine
minutes of voice synthesis and frame rendering to discover that six of the ten
scripts were wrong: three had a spoken line so long the caption band could not
hold it, three had a line that left the screen unchanged for more than eight
seconds, one had a chapter too short for YouTube's own rules, and one was so
evenly paced that no beat stood out. Every one of those faults is visible in the
narration timings alone - no picture required.

So this tool does the cheap half of the pipeline and then stops:

    brief.json -> voice lines -> narration (Kokoro) -> subtitle cues -> craft rules

    python tools/preflight_brief.py --brief video_studio/briefs/ten-minutes.json

It exits 0 when the script would pass the craft gate, 1 when it would not (with
the numbers printed), 2 when the brief cannot be read. The work it writes lives
in a scratch directory (``--work``) and is thrown away; the real render repeats
the same voice stage, so nothing here can drift from what ships.

Run it before a batch, not during one.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import craft  # noqa: E402
import film_subtitles  # noqa: E402
import render_authored_film as render  # noqa: E402

DEFAULT_VOICE = "am_michael"


def preflight(brief_path: Path, work: Path, *, voice: str, backend: str) -> dict:
    """Build the narration for one brief and measure it against the craft rules."""
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    work.mkdir(parents=True, exist_ok=True)

    import brief_to_voice

    # The voice script is rebuilt every run, never reused: a cached one is how a
    # preflight once reported a pass for text that had already been rewritten.
    script = work / "voice.json"
    script.write_text(json.dumps(brief_to_voice.build(brief), indent=2) + "\n",
                      encoding="utf-8")

    voice_dir = work / "voice"
    render.step_voice(script, voice_dir, voice=voice, allow_download=True,
                      backend=backend, fps=int(brief.get("fps") or 30))
    lines_path = voice_dir / "lines.json"

    cues = film_subtitles.build_cues(film_subtitles.load_lines(lines_path))
    srt_path = work / "preflight.srt"
    srt_path.write_text(film_subtitles.to_srt(cues), encoding="utf-8")

    report = craft.verify(
        lines_path,
        srt_path,
        title=brief.get("title"),
        thumbnail_text=(brief.get("thumbnail") or {}).get("line"),
    )
    return {
        "brief": str(brief_path),
        "title": brief.get("title"),
        "passed": report.passed,
        "failed": [{"rule": rule.id, "detail": rule.detail} for rule in report.failures],
        "rules": len(report.rules),
        "metrics": report.metrics,
    }


def report_one(brief: Path, work: Path, *, voice: str, backend: str) -> tuple[int, dict | None]:
    """Preflight one brief and print its verdict. Returns (exit code, result)."""
    try:
        result = preflight(brief, work, voice=voice, backend=backend)
    except Exception as exc:  # the brief, the voice, or the model is at fault
        print(f"{brief.name}: preflight could not run: {exc}", file=sys.stderr)
        return 2, None
    metrics = result["metrics"]
    print(f"{brief.name}: {metrics['duration_s']:.1f}s, {metrics['cues']} cues, "
          f"mean beat {metrics['mean_beat_s']:.2f}s, sd/mean {metrics['beat_sd_ratio']:.2f}, "
          f"slowest change {metrics['longest_gap_s']:.2f}s gap")
    if result["passed"]:
        print(f"  PREFLIGHT: PASS ({result['rules']}/{result['rules']} craft rules)")
        return 0, result
    print(f"  PREFLIGHT: FAIL ({len(result['failed'])} of {result['rules']} rules)")
    for item in result["failed"]:
        print(f"    - {item['rule']}: {item['detail']}")
    return 1, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brief", type=Path,
                        help="one brief; omit it with --all to check the whole folder")
    parser.add_argument("--all", action="store_true",
                        help="preflight every brief in video_studio/briefs")
    parser.add_argument("--jobs", type=int, default=2,
                        help="how many briefs to check at once in --all mode (default 2)")
    parser.add_argument("--work", type=Path, default=None,
                        help="scratch directory (default: a temporary directory)")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--voice-backend", default="kokoro",
                        choices=["kokoro", "piper", "espeak"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.all and args.brief is None:
        parser.error("give --brief, or --all to check every brief in the folder")

    briefs = ([args.brief] if args.brief else
              sorted((ROOT / "video_studio" / "briefs").glob("*.json")))
    missing = [brief for brief in briefs if not brief.is_file()]
    if missing:
        print(f"no such brief: {missing[0]}", file=sys.stderr)
        return 2

    root = args.work or Path(tempfile.mkdtemp(prefix="preflight-"))
    own_work = args.work is None
    codes: list[int] = []
    results: dict[str, dict] = {}
    try:
        if len(briefs) == 1:
            code, result = report_one(briefs[0], root / briefs[0].stem,
                                      voice=args.voice, backend=args.voice_backend)
            codes.append(code)
            if result:
                results[briefs[0].stem] = result
        else:
            # Two at a time by default: the read is the expensive part and a small
            # runner has two cores, so more workers makes the batch slower, not faster.
            from concurrent.futures import ThreadPoolExecutor

            def run(brief: Path) -> tuple[str, int, dict | None]:
                code, result = report_one(brief, root / brief.stem,
                                          voice=args.voice, backend=args.voice_backend)
                return brief.stem, code, result

            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                for stem, code, result in pool.map(run, briefs):
                    codes.append(code)
                    if result:
                        results[stem] = result
            failed = sorted(stem for stem, result in results.items() if not result["passed"])
            print(f"\n{len(briefs)} briefs checked: "
                  f"{len(briefs) - len(failed)} publishable, {len(failed)} to fix")
            if failed:
                print("  " + ", ".join(failed))
    finally:
        if own_work:
            shutil.rmtree(root, ignore_errors=True)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    return 0 if codes and all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
