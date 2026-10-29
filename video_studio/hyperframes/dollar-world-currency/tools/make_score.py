#!/usr/bin/env python3
"""Deterministic cinematic score for 'Why the Dollar Rules the World' (60 s).

No samples, no external assets: every sound is synthesized so the film is
licence-clean and reproducible. Chapter hits land exactly on the visual
cuts (0 / 6 / 14 / 23 / 32 / 41 / 50 s) and the final lockup hit at 56.8 s.

Run:  python3 tools/make_score.py   ->  assets/audio/score.wav (48 kHz stereo)
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
DUR = 60.0
N = int(SR * DUR)
rng = np.random.default_rng(1944)

mix = np.zeros((N, 2), dtype=np.float64)


def midi(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def add(start: float, signal: np.ndarray, pan: float = 0.0, gain: float = 1.0) -> None:
    """Add a mono signal into the stereo mix. pan: -1 (L) .. +1 (R)."""
    i0 = int(start * SR)
    if i0 >= N:
        return
    seg = signal[: N - i0]
    left = np.sqrt(0.5 * (1.0 - pan))
    right = np.sqrt(0.5 * (1.0 + pan))
    mix[i0 : i0 + len(seg), 0] += seg * gain * left * np.sqrt(2.0)
    mix[i0 : i0 + len(seg), 1] += seg * gain * right * np.sqrt(2.0)


def env_exp(n: int, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.exp(-t / decay)


def one_pole_lp(x: np.ndarray, coeff: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += coeff * (v - acc)
        y[i] = acc
    return y


def pad_chord(start: float, dur: float, notes: list[int], gain: float, bright: float = 0.06) -> None:
    n = int(dur * SR)
    t = np.arange(n) / SR
    attack = np.minimum(1.0, t / 1.2)
    release = np.minimum(1.0, np.maximum(0.0, (dur - t) / 1.4))
    env = attack * release
    for k, m in enumerate(notes):
        f = midi(m)
        sig = (
            np.sin(2 * np.pi * f * t)
            + 0.45 * np.sin(2 * np.pi * f * 1.003 * t)
            + bright * np.sin(2 * np.pi * f * 2.0 * t)
        ) * env
        add(start, sig, pan=-0.35 + 0.7 * (k / max(1, len(notes) - 1)), gain=gain / len(notes))


def boom(start: float, gain: float = 0.8, dur: float = 1.1) -> None:
    n = int(dur * SR)
    t = np.arange(n) / SR
    freq = 64.0 * np.power(30.0 / 64.0, t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sig = np.sin(phase) * env_exp(n, 0.34)
    add(start, sig, gain=gain)
    noise = rng.standard_normal(n) * env_exp(n, 0.07)
    add(start, noise, gain=gain * 0.16)


def whoosh(start: float, gain: float = 0.24, dur: float = 0.38) -> None:
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    t = np.arange(n) / SR
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    sweep = one_pole_lp(noise, 0.10) * env
    add(start, sweep, pan=-0.2, gain=gain)


def riser(start: float, dur: float = 0.55, gain: float = 0.13) -> None:
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = (t / dur) ** 2
    freq = 280.0 * (980.0 / 280.0) ** (t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    add(start, np.sin(phase) * env, gain=gain * 0.5)
    add(start, rng.standard_normal(n) * env * 0.4, gain=gain)


def coin_shing(start: float, gain: float = 0.30) -> None:
    dur = 0.85
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for f, a, d in [(2093, 0.50, 0.30), (2637, 0.34, 0.22), (3520, 0.26, 0.16), (4698, 0.16, 0.10), (6271, 0.07, 0.06)]:
        sig += a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
    add(start, sig, pan=0.12, gain=gain)


def pulse(start: float, gain: float = 0.20) -> None:
    dur = 0.20
    n = int(dur * SR)
    t = np.arange(n) / SR
    freq = 118.0 * (46.0 / 118.0) ** (t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    add(start, np.sin(phase) * env_exp(n, 0.055), gain=gain)


def tick(start: float, pan: float, gain: float = 0.045) -> None:
    n = int(0.035 * SR)
    noise = rng.standard_normal(n)
    hp = noise - one_pole_lp(noise, 0.28)
    add(start, hp * env_exp(n, 0.008), pan=pan, gain=gain)


# --- Harmonic journey, one chord per chapter ---------------------------------
pad_chord(0.0, 7.4, [38, 45, 53, 57], 0.42, bright=0.05)    # S1 Dm — the hook
pad_chord(6.0, 9.4, [46, 53, 58, 62], 0.34, bright=0.05)    # S2 Bb — 1944 deal
pad_chord(14.0, 10.4, [41, 48, 53, 57], 0.36, bright=0.07)  # S3 F — network lift
pad_chord(23.0, 10.4, [38, 45, 50], 0.36, bright=0.04)      # S4 Dm low — oil
pad_chord(32.0, 10.4, [48, 55, 60, 64], 0.34, bright=0.06)  # S5 C — the vault
pad_chord(41.0, 10.4, [39, 46, 51, 57], 0.34, bright=0.05)  # S6 Eb tension — power
pad_chord(50.0, 9.6, [41, 48, 53, 60, 65], 0.40, bright=0.08)  # S7 F major — resolve

# --- Chapter hits, whooshes, risers (synced to visible actions) ---------------
for t0, g in [(0.0, 0.85), (6.0, 0.62), (14.0, 0.66), (23.0, 0.62), (32.0, 0.62), (41.0, 0.66), (50.0, 0.70)]:
    boom(t0, gain=g)
    if t0 > 0:
        whoosh(t0 - 0.14)
for t0 in (13.45, 31.45, 49.45, 56.25):
    riser(t0)
boom(56.8, gain=0.9, dur=1.5)
coin_shing(1.15, 0.26)
coin_shing(50.45, 0.28)
coin_shing(56.95, 0.34)

# --- 100 BPM pulse (6 s -> 50 s) + data ticks (14 s -> 41 s) ------------------
beat = 0.6
t = 6.0
bar = 0
while t < 49.9:
    pulse(t, gain=0.20 if bar % 4 == 0 else 0.11)
    bar += 1
    t += beat
t = 14.3
side = 1
while t < 40.9:
    tick(t, pan=0.45 * side)
    side *= -1
    t += 0.3

# --- Master: gentle saturation, end fade, peak normalize ----------------------
mix[:] = np.tanh(mix * 1.12) / np.tanh(1.12)
fade_n = int(0.8 * SR)
mix[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)[:, None]
peak = float(np.max(np.abs(mix)))
mix *= 0.88 / max(peak, 1e-9)

out = Path(__file__).resolve().parent.parent / "assets" / "audio" / "score.wav"
out.parent.mkdir(parents=True, exist_ok=True)
pcm = (mix * 32767.0).astype(np.int16)
with wave.open(str(out), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
rms = float(np.sqrt(np.mean(mix**2)))
print(f"wrote {out}  peak={peak:.3f} rms={rms:.4f} ({20*np.log10(rms):.1f} dBFS) dur={DUR:.1f}s")
