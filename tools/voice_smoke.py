#!/usr/bin/env python3
"""Narrate one short sentence, and fail loudly if the runner cannot.

    python tools/voice_smoke.py

Why this exists: a batch render once sat in the voice stage for twenty minutes on
a fresh runner with no way to tell, from outside, whether it was working or hung.
Synthesising one sentence costs about ten seconds and turns that into a step that
passes or fails on its own, before the job spends its budget on a film.

It also prints the numbers that matter - how long the synthesis took, how many
samples came back, and the peak level - so a run's log says whether the narrator
is present and audible rather than merely exit-zero.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "video_studio"))

import render_authored_film as render  # noqa: E402

LINE = "This is one sentence, to prove the narrator is here."
# The shape the narrator actually reads: a flat list of lines with ids.
SCRIPT = {
    "title": "Voice smoke test",
    "lines": [{"id": "L001", "text": LINE, "gap_before": 0.1, "pause_after": 0.2}],
}


def main() -> int:
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        script = work / "voice.json"
        script.write_text(json.dumps(SCRIPT, indent=2) + "\n", encoding="utf-8")
        voice_dir = work / "voice"
        render.step_voice(script, voice_dir, voice="am_michael", allow_download=True,
                          backend="kokoro", fps=30)
        wav = voice_dir / "voiceover.wav"
        if not wav.is_file():
            print(f"no narration was written to {wav}", file=sys.stderr)
            return 1
        import wave

        with wave.open(str(wav)) as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            width = handle.getsampwidth()
            raw = handle.readframes(frames)
        seconds = frames / float(rate or 1)
        peak = 0
        if width == 2:
            import array

            samples = array.array("h")
            samples.frombytes(raw)
            peak = max((abs(value) for value in samples), default=0)
        if seconds < 0.5 or peak < 500:
            print(f"narration is not audible: {seconds:.2f}s, peak {peak}", file=sys.stderr)
            return 1
        print(f"narrator ok: {seconds:.2f}s of speech at {rate} Hz, peak {peak}, "
              f"{time.monotonic() - started:.1f}s to synthesise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
