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


def band_mask(x: np.ndarray, low: float, high: float, depth: float) -> np.ndarray:
    """Pull one band down: used for de-essing and for taking the boxiness out."""
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    mask = np.ones_like(freqs)
    inside = (freqs >= low) & (freqs <= high)
    feather = np.clip((freqs - low) / max(1.0, (high - low) * 0.25), 0, 1) * np.clip((high - freqs) / max(1.0, (high - low) * 0.25), 0, 1)
    mask[inside] = 1 - depth * feather[inside]
    return np.fft.irfft(spec * mask, n)


def highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll = np.ones_like(freqs)
    under = freqs < cutoff
    roll[under] = np.clip((freqs[under] / max(cutoff, 1.0)) ** 2, 0, 1)
    return np.fft.irfft(spec * roll, n)


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll = np.ones_like(freqs)
    over = freqs > cutoff
    roll[over] = np.clip(1 - ((freqs[over] - cutoff) / max(cutoff, 1.0)) ** 2, 0, 1)
    return np.fft.irfft(spec * roll, n)


def compress(x: np.ndarray, ratio: float = 2.4, threshold_db: float = -22.0,
             attack: float = 0.006, release: float = 0.12, makeup_db: float = 3.0) -> np.ndarray:
    """A simple envelope-follower compressor.

    Flat text-to-speech is flat because every syllable arrives at the same level.
    Evening that out, and then lifting the quiet parts, is most of what makes a
    synthetic read sound like a person who is speaking rather than announcing.
    """
    win = max(1, int(0.005 * SR))
    env = np.abs(x)
    kernel = np.ones(win) / win
    env = np.convolve(env, kernel, mode='same')
    db = 20 * np.log10(env + 1e-7)
    over = np.maximum(0.0, db - threshold_db)
    gain_db = -over * (1 - 1 / ratio)
    # Attack and release on the gain, not the signal.
    a = math.exp(-1 / (attack * SR))
    r = math.exp(-1 / (release * SR))
    smoothed = np.empty_like(gain_db)
    g = 0.0
    for i, target in enumerate(gain_db):
        coeff = a if target < g else r
        g = coeff * g + (1 - coeff) * target
        smoothed[i] = g
    return x * (10 ** ((smoothed + makeup_db) / 20))


def reverb(x: np.ndarray, wet: float = 0.12, decay: float = 0.55) -> np.ndarray:
    """A small bright room: enough to stop the voice sounding sealed in a box."""
    n_ir = int(decay * SR)
    rng = np.random.default_rng(5)
    ir = rng.normal(0, 1, n_ir) * np.exp(-np.arange(n_ir) / (SR * decay * 0.30))
    ir = lowpass(ir, 5000)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    size = 1 << int(math.ceil(math.log2(len(x) + len(ir))))
    wet_sig = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return (1 - wet) * x + wet * wet_sig


def process_voice(x: np.ndarray) -> np.ndarray:
    """The chain a narration pass would get in a studio, in order."""
    x = highpass(x, 85.0)          # rumble out of the way of the score
    x = band_mask(x, 250, 400, 0.35)  # take the boxiness out of the low mids
    x = compress(x)                # even the syllables, lift the quiet ones
    x = band_mask(x, 5500, 8500, 0.45)  # de-ess
    # No presence lift. Measured: Kokoro already puts 11-13 % of its energy above
    # 4 kHz, which is normal speech, and lifting 2-4 kHz pushed the centroid up a
    # further 100-220 Hz and made it brittle. If anything, ease the top instead.
    x = lowpass(x, 9500)
    x = reverb(x, wet=0.10, decay=0.5)
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * 0.87


def synth(lines: list[dict], out_dir: Path, voice: str = 'am_michael', speed: float = 1.0,
          processed: bool = True) -> dict:
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(MODEL), str(VOICES))
    out_dir.mkdir(parents=True, exist_ok=True)
    timing = []
    for i, line in enumerate(lines):
        audio, rate = kokoro.create(line['text'], voice=voice, speed=speed, lang='en-us')
        audio = trim(np.asarray(audio, dtype=np.float32))
        if processed:
            audio = resample(audio, rate, SR)
            audio = process_voice(audio)
            rate = SR
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
    s.add_argument('--speed', type=float, default=0.94)
    s.add_argument('--raw', action='store_true', help='skip the processing chain')

    m = sub.add_parser('mix')
    m.add_argument('--vo', required=True)
    m.add_argument('--score', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--duck', type=float, default=-7.0)

    args = ap.parse_args()
    if args.cmd == 'synth':
        lines = json.loads(Path(args.lines).read_text())
        synth(lines, Path(args.out), voice=args.voice, speed=args.speed, processed=not args.raw)
    else:
        mix(Path(args.vo), Path(args.score), Path(args.out), duck_db=args.duck)


if __name__ == '__main__':
    main()
