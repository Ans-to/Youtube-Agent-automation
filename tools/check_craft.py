#!/usr/bin/env python3
"""The craft gate's command line.

The rules and the measurement live in `video_studio/craft.py`, next to the
reference in `docs/youtube-craft.md`. This is the wrapper the pipeline and CI
call, kept in `tools/` like every other gate so the invocation is the same shape
as `check_composition.py` and `check_repeat_frames.py`.

    python tools/check_craft.py --script voice/lines.json --srt film.srt \
        --title "How to Review AI-Written Code in 60 Seconds" \
        --thumbnail-text "60 SECOND REVIEW"

Exit codes: 0 every rule passed, 1 a rule failed (the numbers are printed),
2 the input could not be read.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

import craft  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(craft.main())
