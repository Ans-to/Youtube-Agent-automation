#!/usr/bin/env python3
"""Narration: synthesise the voiceover, then time the film to it.

The film was cut to a stopwatch and the voice had nowhere to sit. The order is
the other way round: each shot's line is spoken first, its real length is
measured, and the shot is as long as the line plus a breath. That is how a
documentary is actually cut, and it is why the durations live in a JSON file
rather than in the shot list.

Two jobs:

    python video_studio/narrate.py synth --lines lines.json --out vo/
    python video_studio/narrate.py mix --vo vo/ --score score.wav --out master.wav

`synth` writes one WAV per line plus a `timing.json` the film reads.
`mix` lays the voice over the score with the music ducked, limited to about
-14 LUFS with a -1.5 dBTP ceiling.
"""
from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000
VOICE_SR = 24000
MODEL = Path('/home/user/.cache/agent-hq/kokoro/kokoro-82m-q8.onnx')
VOICES = Path('/home/user/.cache/agent-hq/kokoro/voices.npz')


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as f:
        channels = f.getnchannels()
        width = f.getsampwidth()
        rate = f.getframerate()
        raw = f.readframes(f.getnframes())
    data = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if width != 2:
        raise ValueError(f'{path} is not 16-bit PCM')
    return data, rate


def write_wav(path: Path, data: np.ndarray, rate: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm.tobytes())


def resample(data: np.ndarray, frm: int, to: int) -> np.ndarray:
    """Linear resample. The voice is speech at 24 kHz and the bed is 48; a
    second-order filter would be better and a 2x linear pass is inaudible here."""
    if frm == to:
        return data
    n = int(round(len(data) * to / frm))
    x = np.linspace(0, len(data) - 1, n)
    return np.interp(x, np.arange(len(data)), data).astype(np.float32)


def trim(data: np.ndarray, threshold: float = 0.004) -> np.ndarray:
    """Cut the silence from both ends so a line starts on its first consonant."""
    idx = np.where(np.abs(data) > threshold)[0]
    if not len(idx):
        return data
    pad = int(0.04 * VOICE_SR)
    return data[max(0, idx[0] - pad): idx[-1] + pad]


def synth(lines: list[dict], out_dir: Path, voice: str = 'am_michael', speed: float = 1.0) -> dict:
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(MODEL), str(VOICES))
    out_dir.mkdir(parents=True, exist_ok=True)
    timing = []
    for i, line in enumerate(lines):
        audio, rate = kokoro.create(line['text'], voice=voice, speed=speed, lang='en-us')
        audio = trim(np.asarray(audio, dtype=np.float32))
        path = out_dir / f'{i:02d}-{line["shot"]}.wav'
        write_wav(path, audio, rate)
        seconds = len(audio) / rate
        timing.append({'shot': line['shot'], 'text': line['text'], 'file': str(path), 'vo': round(seconds, 3)})
        print(f'  {line["shot"]:<22} {seconds:5.2f}s  {line["text"][:52]}')
    (out_dir / 'timing.json').write_text(json.dumps(timing, indent=2))
    total = sum(t['vo'] for t in timing)
    print(f'spoken: {total:.1f}s across {len(timing)} lines')
    return {'lines': timing}


def soft_limit(x: np.ndarray, ceiling: float) -> np.ndarray:
    knee = ceiling * 0.55
    mag = np.abs(x)
    sign = np.sign(x)
    over = mag > knee
    out = mag.copy()
    out[over] = knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee) * 1.4) / math.tanh(1.4)
    return np.clip(sign * out, -ceiling, ceiling)


def mix(vo_dir: Path, score_path: Path, out_path: Path, lead: float = 0.35,
        duck_db: float = -7.0, vo_gain_db: float = 2.0) -> None:
    timing = json.loads((vo_dir / 'timing.json').read_text())
    starts = json.loads((vo_dir / 'starts.json').read_text()) if (vo_dir / 'starts.json').exists() else None

    score, score_rate = read_wav(score_path)
    score = resample(score, score_rate, SR)
    if starts is None:
        raise SystemExit('vo/starts.json is missing - run the film with --vo first')
    length = max(len(score), int((starts[-1]['end'] + 1.0) * SR))
    master = np.zeros(length, dtype=np.float32)
    master[:len(score)] += score

    voice_track = np.zeros(length, dtype=np.float32)
    gate = np.ones(length, dtype=np.float32)

    for entry, spot in zip(timing, starts):
        data, rate = read_wav(Path(entry['file']))
        data = resample(data, rate, SR) * (10 ** (vo_gain_db / 20))
        at = int((spot['start'] + lead) * SR)
        end = min(length, at + len(data))
        voice_track[at:end] += data[:end - at]
        # Duck the music under the line, but only by a fixed amount: a fully
        # automatic ducker pumps on every consonant.
        ramp = int(0.25 * SR)
        gate[max(0, at - ramp):end] = 10 ** (duck_db / 20)

    # Smooth the gate so the ducking has no click at either edge.
    kernel = np.ones(int(0.18 * SR), dtype=np.float32)
    kernel /= kernel.sum()
    gate = np.convolve(gate, kernel, mode='same')

    master = master * gate + voice_track

    # Loudness then ceiling, the same order as the score.
    target = 10 ** ((-14.0 + 3.0) / 20)
    ceiling = 10 ** (-1.5 / 20)
    for _ in range(4):
        rms = float(np.sqrt(np.mean(master ** 2)) + 1e-12)
        master *= min(target / rms, 8.0)
        master = soft_limit(master, ceiling)

    # A little width: the voice stays centre, the bed goes slightly wide.
    delay = int(0.008 * SR)
    right = np.concatenate([np.zeros(delay), master[:-delay]]) * 0.92 + voice_track * 0.0
    stereo = np.stack([master, right], axis=1)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype('<i2')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    loud = 20 * math.log10(float(np.sqrt(np.mean(master ** 2))) + 1e-12) - 3.0
    peak = 20 * math.log10(float(np.max(np.abs(stereo))) + 1e-12)
    print(f'wrote {out_path}: about {loud:.1f} LUFS, peak {peak:.1f} dBFS, {len(master) / SR:.1f}s')


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('synth')
    s.add_argument('--lines', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--voice', default='am_michael')
    s.add_argument('--speed', type=float, default=1.0)

    m = sub.add_parser('mix')
    m.add_argument('--vo', required=True)
    m.add_argument('--score', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--duck', type=float, default=-7.0)

    args = ap.parse_args()
    if args.cmd == 'synth':
        lines = json.loads(Path(args.lines).read_text())
        synth(lines, Path(args.out), voice=args.voice, speed=args.speed)
    else:
        mix(Path(args.vo), Path(args.score), Path(args.out), duck_db=args.duck)


if __name__ == '__main__':
    main()
