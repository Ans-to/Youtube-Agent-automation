#!/usr/bin/env python3
"""Put a voice on top of a score, and duck the score while the voice speaks.

A voiceover laid on top of music at unity gain is the single most common reason
a good cut sounds amateur: the score and the consonants fight for the same band.
Broadcast does it with a ducker. So this module does the same thing:

1. read the score and the voice, resample both to one rate,
2. follow the voice with an envelope detector (fast attack, slow release) so the
   music drops *before* the first syllable and comes back *after* the last,
3. apply the resulting gain curve to the score (a fixed number of dB, not a
   guess), and sum the two at a level where speech stays intelligible,
4. peak-limit the sum so nothing clips when the impact cue lands under a line.

Everything is numpy on purpose: no extra dependency, and the duck curve is
inspectable instead of hidden inside a filter graph.

Usage::

    python video_studio/voice_mix.py --music score.wav --voice vo.wav --out mix.wav
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 24000
# A ducker that breathes: quick to get out of the way, unhurried to come back.
ATTACK_SECONDS = 0.018
RELEASE_SECONDS = 0.42
SPEECH_FLOOR_DB = -46.0     # below this the voice is not speaking
DEFAULT_DEPTH_DB = 8.5      # how far the score drops under speech


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        packed = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        packed = np.where(packed >= 1 << 23, packed - (1 << 24), packed)
        data = packed.astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(frames, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise ValueError(f"{path}: unsupported sample width {width}")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def write_wav(path: Path, signal: np.ndarray, rate: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(signal, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def resample(signal: np.ndarray, source: int, target: int) -> np.ndarray:
    if source == target or signal.size == 0:
        return signal.astype(np.float32)
    duration = signal.size / source
    target_n = max(1, int(round(duration * target)))
    source_x = np.linspace(0.0, duration, signal.size, endpoint=False)
    target_x = np.linspace(0.0, duration, target_n, endpoint=False)
    return np.interp(target_x, source_x, signal).astype(np.float32)


def _smooth_attack_release(level: np.ndarray, rate: int, attack: float, release: float) -> np.ndarray:
    """One-pole follower: instant-ish up, slow down. This is the duck shape."""
    up = math.exp(-1.0 / max(1.0, attack * rate))
    down = math.exp(-1.0 / max(1.0, release * rate))
    out = np.empty_like(level)
    value = float(level[0]) if level.size else 0.0
    for index, target in enumerate(level):
        coefficient = up if target > value else down
        value = coefficient * value + (1.0 - coefficient) * float(target)
        out[index] = value
    return out


def speech_curve(voice: np.ndarray, rate: int) -> np.ndarray:
    """0 = silence, 1 = talking, with a musical attack and release."""
    window = max(1, int(rate * 0.01))
    energy = np.convolve(voice.astype(np.float64) ** 2, np.ones(window) / window, mode="same")
    level_db = 10 * np.log10(np.maximum(energy, 1e-12))
    # map the speaking range onto 0..1 rather than using a hard gate
    loudest = float(np.percentile(level_db, 98)) if level_db.size else -60.0
    span = max(8.0, loudest - SPEECH_FLOOR_DB)
    target = np.clip((level_db - SPEECH_FLOOR_DB) / span, 0.0, 1.0)
    return _smooth_attack_release(target.astype(np.float32), rate,
                                  ATTACK_SECONDS * 0.5, RELEASE_SECONDS)


def duck_db(curve: np.ndarray, depth_db: float) -> np.ndarray:
    return -depth_db * curve


def db_to_gain(db: np.ndarray) -> np.ndarray:
    return np.power(10.0, db / 20.0)


def peak_limit(signal: np.ndarray, ceiling: float = 0.89) -> np.ndarray:
    """Transparent peak limiter: only touches the few samples that overshoot."""
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    if peak <= ceiling:
        return signal
    # soft knee over the last 3 dB, hard stop at the ceiling
    knee = ceiling * 0.708
    out = signal.copy()
    over = np.abs(out) > knee
    out[over] = np.sign(out[over]) * (
        knee + (ceiling - knee) * np.tanh((np.abs(out[over]) - knee) / (ceiling - knee))
    )
    return out


def mix(music_path: Path, voice_path: Path, out_path: Path, *,
        depth_db: float = DEFAULT_DEPTH_DB, voice_gain_db: float = 1.5,
        music_gain_db: float = 0.0, rate: int = SAMPLE_RATE) -> dict:
    music, music_rate = read_wav(Path(music_path))
    voice, voice_rate = read_wav(Path(voice_path))
    music = resample(music, music_rate, rate)
    voice = resample(voice, voice_rate, rate)

    length = max(music.size, voice.size)
    if music.size < length:
        music = np.pad(music, (0, length - music.size))
    if voice.size < length:
        voice = np.pad(voice, (0, length - voice.size))

    curve = speech_curve(voice, rate)
    gain = db_to_gain(duck_db(curve, depth_db))
    ducked = music * gain * (10 ** (music_gain_db / 20.0))
    voice_scaled = voice * (10 ** (voice_gain_db / 20.0))
    mixed = peak_limit(ducked + voice_scaled)

    write_wav(Path(out_path), mixed, rate)

    speaking = curve > 0.5
    overhead = float(np.mean(mixed[~speaking] ** 2)) if (~speaking).any() else 0.0
    under = float(np.mean(voice[speaking] ** 2)) if speaking.any() else 0.0
    return {
        "path": str(out_path),
        "sample_rate": rate,
        "duration_seconds": round(length / rate, 3),
        "duck_depth_db": depth_db,
        "duck_trigger_share": round(float(np.mean(speaking)), 4),
        "mean_duck_db": round(float(np.mean(duck_db(curve, depth_db))), 2),
        "voice_to_bed_db": round(
            10 * math.log10((under + 1e-12) / (overhead + 1e-12)), 1) if overhead else None,
        "peak": round(float(np.max(np.abs(mixed))), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--music", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--depth-db", type=float, default=DEFAULT_DEPTH_DB)
    parser.add_argument("--voice-gain-db", type=float, default=1.5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        info = mix(Path(args.music), Path(args.voice), Path(args.out),
                   depth_db=args.depth_db, voice_gain_db=args.voice_gain_db)
    except (OSError, ValueError, wave.Error) as exc:
        print("mix failed: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("MIX: %.2fs, duck %.1f dB under speech (%.0f%% of the cut), peak %.2f -> %s"
              % (info["duration_seconds"], info["duck_depth_db"],
                 info["duck_trigger_share"] * 100, info["peak"], info["path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
