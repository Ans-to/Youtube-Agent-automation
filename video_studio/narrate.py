"""Narration: lines in, timed wavs out, mixed under the score.

The voice is `voice.py` - phrasing, pauses, EQ, compression, -16 LUFS. This file
only does the bookkeeping: which line belongs to which shot, how long it took, and
how it sits against the music.
"""
from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np

import voice as V
from voice import SR


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as f:
        n, channels, rate = f.getnframes(), f.getnchannels(), f.getframerate()
        data = np.frombuffer(f.readframes(n), dtype='<i2').astype(np.float32) / 32768
    return data.reshape(-1, channels).mean(axis=1), rate


def synth(lines: list[dict], out_dir: Path, voice: str = 'bm_george',
          rate: float = 0.95, engine: str = 'kokoro') -> list[dict]:
    V.require_engine(engine)
    out_dir.mkdir(parents=True, exist_ok=True)
    timing = []
    at = 0.0
    for i, line in enumerate(lines):
        audio = V.synth(line['text'], voice, base_rate=rate)
        # Half a second of air before the first word, a beat between lines.
        lead = 0.55 if i == 0 else 0.30
        name = f'{i:02d}-{line["shot"]}.wav'
        V.write_wav(out_dir / name, audio)
        start = at + lead
        end = start + len(audio) / SR
        timing.append({
            'shot': line['shot'],
            'file': name,
            'start': round(start, 3),
            'end': round(end, 3),
            'vo': round(len(audio) / SR, 3),
            'text': line['text'],
            'words': len(line['text'].split()),
        })
        at = end + 0.35
    (out_dir / 'timing.json').write_text(json.dumps(timing, indent=2))
    return timing


def mix(vo_dir: Path, score_path: Path, out_path: Path, duck: float = 0.42) -> Path:
    """Voice over the score, with the score ducking under the words."""
    timing = json.loads((vo_dir / 'timing.json').read_text())
    # As long as the film, always. The score is cut to the film's exact length, so
    # the voice track may not be shorter than it - `-shortest` at mux time would
    # then cut the last shot off to match the audio.
    with wave.open(str(score_path)) as f:
        score_seconds = f.getnframes() / f.getframerate()
    total = max(max(row['end'] for row in timing) + 1.2, score_seconds)
    master = np.zeros(int(total * SR), np.float32)

    for row in timing:
        line, rate = read_wav(vo_dir / row['file'])
        if rate != SR:
            line = V.resample(line, rate, SR)
        at = int(row['start'] * SR)
        master[at:at + len(line)] += line

    score, rate = read_wav(score_path)
    if rate != SR:
        score = V.resample(score, rate, SR)
    if len(score) < len(master):
        score = np.pad(score, (0, len(master) - len(score)))
    score = score[:len(master)]
    del score_seconds

    # Duck: a smooth envelope that dips where speech is and opens in the gaps.
    speech = np.zeros(len(master), np.float32)
    for row in timing:
        a, b = int(row['start'] * SR), int(row['end'] * SR)
        speech[a:b] = 1.0
    k = np.hanning(int(0.22 * SR))
    k /= k.sum()
    speech = np.convolve(speech, k, mode='same')
    gain = 1.0 - duck * np.clip(speech, 0, 1)
    master_out = master + score * gain * 0.62

    # Loudness first, peak second. Normalising to a peak left the film at -19 LUFS,
    # which is three decibels under every other video on the platform.
    master_out = V.normalise(master_out, target=-16.0, ceiling_db=-1.5)
    V.write_wav(out_path, master_out, stereo=True)
    print(f'wrote {out_path}: {V.lufs(master_out):.1f} LUFS, {len(master_out)/SR:.1f}s')
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('synth')
    s.add_argument('--lines', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--voice', default='bm_george')
    s.add_argument('--rate', type=float, default=0.95)
    s.add_argument('--engine', default='kokoro')

    m = sub.add_parser('mix')
    m.add_argument('--vo', required=True)
    m.add_argument('--score', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--duck', type=float, default=0.42)

    args = ap.parse_args()
    if args.cmd == 'synth':
        rows = synth(json.loads(Path(args.lines).read_text()), Path(args.out),
                     voice=args.voice, rate=args.rate, engine=args.engine)
        for row in rows:
            print(f"  {row['shot']:<18} {row['vo']:5.2f}s  {row['text'][:52]}")
        print(f"spoken: {sum(r['vo'] for r in rows):.1f}s across {len(rows)} lines")
    else:
        mix(Path(args.vo), Path(args.score), Path(args.out), duck=args.duck)


if __name__ == '__main__':
    main()
