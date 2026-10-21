#!/usr/bin/env python3
"""Assemble a voiceover from pre-rendered line clips.

`voiceover.build()` synthesises speech itself (Piper or espeak-ng). Some sessions
have a better voice available elsewhere — a hosted model, a human read, a studio
render — and those arrive as one clip per line. This tool takes those clips and
produces exactly the three artifacts the film consumes, using the same loudness
chain and the same timing maths as the built-in path:

    voiceover.wav   the assembled, polished, 24 kHz mono narration
    lines.json      the timings the picture is retimed to
    envelope.json   per-video-frame mouth openness measured from that audio

Nothing here invents timing: a line starts where the previous one plus its pause
ended, so the numbers handed to the film are the numbers of the audio on disk.

    python tools/assemble_voiceover.py \
        --script video_studio/films/character_ships_it.voice.json \
        --clips workspace/voice-source --out workspace/generated/ships-it/voice

Exit codes: 0 assembled, 1 a step failed, 2 bad input, 3 a dependency is missing.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video_studio"))

CLIP_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".aiff")
# Anything quieter than this at the head or tail of a clip is room tone, not speech.
SILENCE_FLOOR = 10 ** (-45 / 20)


class DependencyMissing(RuntimeError):
    """FFmpeg or numpy is missing."""


def resolve_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:  # the same optional convenience the render drivers offer
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(bundled).is_file():
            return bundled
    except Exception:  # noqa: BLE001 - an absent optional dependency is not an error
        pass
    raise DependencyMissing("FFmpeg is not installed (apt-get install ffmpeg, or pip install imageio-ffmpeg)")


def find_clip(clips: Path, line_id: str) -> Path:
    for suffix in CLIP_SUFFIXES:
        candidate = clips / f"{line_id}{suffix}"
        if candidate.is_file():
            return candidate
    for suffix in CLIP_SUFFIXES:
        candidate = clips / f"{line_id.lower()}{suffix}"
        if candidate.is_file():
            return candidate
    raise ValueError(f"no clip for line {line_id} in {clips} (looked for {line_id}.wav, {line_id}.mp3, ...)")


def decode(clip: Path, target: Path, rate: int, ffmpeg: str) -> None:
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(clip), "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - fixed argv
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"could not decode {clip.name}: " + (result.stderr or "")[-400:])


def trim_silence(signal, rate: int, floor: float = SILENCE_FLOOR, handle: float = 0.035):
    """Drop room tone at both ends, keeping a short handle so consonants survive."""
    import numpy as np

    if signal.size == 0:
        return signal
    loud = np.flatnonzero(np.abs(signal) > floor)
    if loud.size == 0:
        return signal[:0]
    pad = int(rate * handle)
    start = max(0, int(loud[0]) - pad)
    stop = min(signal.size, int(loud[-1]) + pad)
    return signal[start:stop]


def assemble(script: Path, clips: Path, out_dir: Path, *, fps: int = 30,
             backend: str = "external clip") -> dict:
    try:
        import numpy as np  # noqa: F401 - imported for its side effect check only
    except ImportError as exc:  # pragma: no cover - exercised by the CI image
        raise DependencyMissing("numpy is required to assemble a voiceover (pip install numpy)") from exc

    import voiceover

    ffmpeg = resolve_ffmpeg()
    lines = voiceover.load_script(script)
    out_dir.mkdir(parents=True, exist_ok=True)
    rate = voiceover.SAMPLE_RATE

    rendered = []
    with tempfile.TemporaryDirectory() as tmp:
        for line in lines:
            clip = find_clip(clips, line.id)
            decoded = Path(tmp) / f"{line.id}.wav"
            decode(clip, decoded, rate, ffmpeg)
            audio, source_rate = voiceover.read_wav(decoded)
            audio = voiceover.resample(audio, source_rate, rate)
            audio = trim_silence(audio, rate)
            if audio.size == 0:
                raise ValueError(f"{clip.name} contains no audio above the silence floor")
            rendered.append((line, audio))

        pieces = []
        timeline = []
        cursor = 0.0
        for index, (line, audio) in enumerate(rendered):
            gap_before = max(0.0, line.gap_before)
            start = cursor + gap_before
            clip = voiceover.fade_edges(audio, rate)
            end = start + clip.size / rate
            pieces.extend([np.zeros(int(rate * gap_before), dtype=np.float32), clip])
            timeline.append({
                "id": line.id,
                "text": line.text,
                "spoken": voiceover.spoken_text(line.text),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "prosody": voiceover.prosody_note(line),
                "emphasis": voiceover.emphasis_words(line.text),
            })
            cursor = end
            pieces.append(np.zeros(int(rate * line.pause_after), dtype=np.float32))
            cursor += line.pause_after

    full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    full = voiceover.polish(full, rate)

    voice_path = out_dir / "voiceover.wav"
    voiceover.write_wav(voice_path, full, rate)

    envelope = []
    for item in timeline:
        first = int(round(item["start"] * rate))
        last = int(round(item["end"] * rate))
        values = voiceover.openness_envelope(full[first:max(first + 1, last)], rate, fps=fps)
        expected = max(1, int(round((item["end"] - item["start"]) * fps)))
        if len(values) < expected:
            values = values + [0.0] * (expected - len(values))
        envelope.append({"id": item["id"], "start": item["start"], "end": item["end"],
                         "fps": fps, "openness": values[:expected]})
    (out_dir / "envelope.json").write_text(
        json.dumps({"fps": fps, "lines": envelope}, indent=2) + "\n", encoding="utf-8")

    report = {
        "backend": backend,
        "fps": fps,
        "voice": backend,
        "model": None,
        "sample_rate": rate,
        "duration_seconds": round(full.size / rate, 3),
        "line_count": len(timeline),
        "path": str(voice_path),
        "lines": timeline,
        "processing": ["trim < -45 dBFS", "highpass 78Hz", "de-ess", "presence +2dB @2.9k",
                       "compress 3:1", "normalise -1.5dBFS"],
    }
    (out_dir / "voiceover.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "lines.json").write_text(
        json.dumps({"lines": timeline}, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--script", required=True, help="JSON file with the lines")
    parser.add_argument("--clips", required=True, help="directory of <line-id>.wav/.mp3 clips")
    parser.add_argument("--out", required=True, help="output directory for the assembled voice")
    parser.add_argument("--fps", type=int, default=30, help="frame rate for the lip-sync envelope")
    parser.add_argument("--backend", default="external clip", help="label recorded as provenance")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = assemble(Path(args.script), Path(args.clips), Path(args.out),
                          fps=args.fps, backend=args.backend)
    except DependencyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, OSError, RuntimeError) as exc:
        print("voice assembly failed: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("VOICE: %s, %.2fs, %d lines -> %s"
              % (args.backend, report["duration_seconds"], report["line_count"], report["path"]))
        for line in report["lines"]:
            print("  %5.2f-%5.2f  %s" % (line["start"], line["end"], line["text"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
