#!/usr/bin/env python3
"""Audit a finished video for content safety, brand safety, legal, and technical QA.

Exit codes:

* ``0`` — audit passed with every rule verified
* ``1`` — at least one violation was found
* ``2`` — no violation found, but some rules could not be verified
* ``3`` — the audit could not run (missing file, bad arguments)

``--allow-incomplete`` treats an incomplete audit as success, for CI stages that
only care about detected violations. Use it deliberately: an incomplete audit is
not a clean bill of health.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from audit import audit_video, render_json, render_markdown  # noqa: E402
from audit.auditor import FLAGGED, PASSED  # noqa: E402
from audit.media import capabilities  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", help="media file to audit")
    parser.add_argument("--subtitles", help="SRT/VTT transcript to use instead of local ASR")
    parser.add_argument("--whisper-model", default="base",
                        help="local faster-whisper model size (default: base); ignored with --no-asr")
    parser.add_argument("--no-asr", action="store_true", help="do not attempt local speech recognition")
    parser.add_argument("--no-ocr", action="store_true", help="do not attempt local on-screen text reading")
    parser.add_argument("--competitor", action="append", default=[],
                        help="competitor brand name to flag (repeatable)")
    parser.add_argument("--require-disclosure", action="append", default=[],
                        help="legal text that must appear on screen, e.g. 'paid partnership' (repeatable)")
    parser.add_argument("--hate-lexicon", help="JSON file containing a list of terms to match in the transcript")
    parser.add_argument("--max-profanity-per-minute", type=float, default=2.0,
                        help="profanity rate that triggers a brand-safety flag (default: 2.0)")
    parser.add_argument("--sample-fps", type=float, default=10.0,
                        help="frame sampling rate for luminance and strobe analysis (default: 10)")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report")
    parser.add_argument("--report", help="write the report to this path (.json or .md)")
    parser.add_argument("--attest", action="append", default=[], metavar="RULE_ID",
                        help="declare a rule as manually reviewed, e.g. --attest CS-ADULT (repeatable)")
    parser.add_argument("--attested-by", default="", help="name of the person attesting; required with --attest")
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="exit 0 when no violations were found even if rules could not be verified")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    video = Path(args.video)
    if not video.is_file():
        print(f"error: no such file: {video}", file=sys.stderr)
        return 3
    if args.sample_fps <= 0:
        print("error: --sample-fps must be positive", file=sys.stderr)
        return 3

    lexicon = None
    if args.hate_lexicon:
        try:
            data = json.loads(Path(args.hate_lexicon).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read lexicon: {exc}", file=sys.stderr)
            return 3
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            print("error: lexicon must be a JSON array of strings", file=sys.stderr)
            return 3
        lexicon = data

    if args.attest and not args.attested_by.strip():
        print("error: --attest requires --attested-by so the report records who vouched for it",
              file=sys.stderr)
        return 3
    if args.attest:
        print(
            "warning: " + ", ".join(args.attest) + " will be recorded as human-attested, not machine-verified",
            file=sys.stderr,
        )

    try:
        report = audit_video(
            video,
            subtitle_path=args.subtitles,
            whisper_model=None if args.no_asr else args.whisper_model,
            ocr=not args.no_ocr,
            competitor_terms=args.competitor,
            required_disclosures=args.require_disclosure,
            hate_lexicon=lexicon,
            max_profanity_per_minute=args.max_profanity_per_minute,
            sample_fps=args.sample_fps,
            attested=args.attest,
            attested_by=args.attested_by,
        )
    except (OSError, ValueError) as exc:
        print(f"error: audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    report["capabilities"] = capabilities()
    print(render_json(report) if args.json else render_markdown(report), end="")

    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = render_json(report) if target.suffix.lower() == ".json" else render_markdown(report)
        target.write_text(text, encoding="utf-8")
        print(f"\nReport written to {target}")

    if report["status"] == FLAGGED:
        return 1
    if report["status"] == PASSED:
        return 0
    return 0 if args.allow_incomplete else 2


if __name__ == "__main__":
    raise SystemExit(main())
