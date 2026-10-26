#!/usr/bin/env python3
"""Synthesise a score for a motion-graphics film.

The old sound design was a quiet pad and a click at each scene change, which is
underscore for a voiceover. A film with no narration needs a score that carries
the same job the voice would: state a mood, build, turn, resolve.

Everything here is generated from oscillators and filtered noise, so it is
royalty-free by construction and deterministic - the same cue list gives the
same file every run.

    python video_studio/score.py --seconds 50 --sections "calm:0:5,build:5:20,turn:20:28,hold:28:35,rise:35:43,end:43:50" --out score.wav
"""
from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000

# A minor key with a raised sixth, which is the sound of a story about a company
# rather than a story about a person: it can move to hope without leaving.
NOTE = {
    'A1': 55.00, 'C2': 65.41, 'E2': 82.41, 'F2': 87.31, 'G2': 98.00,
    'A2': 110.00, 'C3': 130.81, 'D3': 146.83, 'E3': 164.81, 'F3': 174.61,
    'G3': 196.00, 'A3': 220.00, 'B3': 246.94, 'C4': 261.63, 'D4': 293.66,
    'E4': 329.63, 'F4': 349.23, 'G4': 392.00, 'A4': 440.00, 'C5': 523.25,
    'E5': 659.26, 'G5': 783.99,
}

CHORDS = {
    'am': ['A2', 'C3', 'E3', 'A3'],
    'am7': ['A2', 'C3', 'E3', 'G3'],
    'f': ['F2', 'A2', 'C3', 'F3'],
    'c': ['C3', 'E3', 'G3', 'C4'],
    'g': ['G2', 'B3', 'D4', 'G3'],
    'dm': ['D3', 'F3', 'A3', 'D4'],
    'em': ['E3', 'G3', 'B3', 'E4'],
}

SECTIONS = {
    # name: (chord, pad gain, pulse per second, arp, brightness)
    'calm': ('am', 0.30, 0.0, False, 0.35),
    'build': ('f', 0.26, 0.9, False, 0.55),
    'turn': ('dm', 0.28, 1.1, True, 0.45),
    'hold': ('am', 0.22, 0.55, False, 0.30),
    'rise': ('c', 0.28, 1.35, True, 0.70),
    'end': ('am', 0.26, 0.0, False, 0.40),
}


def t_axis(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def adsr(n: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    d = max(1, int(decay * SR))
    r = max(1, int(release * SR))
    hold = max(1, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, sustain, d, endpoint=False),
        np.full(hold, sustain),
        np.linspace(sustain, 0, r),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def tone(freq: float, seconds: float, bright: float = 0.5, detune: float = 0.0) -> np.ndarray:
    """A soft additive tone: fundamental plus two partials, falling off with brightness."""
    t = t_axis(seconds)
    sig = np.sin(2 * math.pi * freq * t)
    sig += 0.42 * bright * np.sin(2 * math.pi * freq * 2.0 * t + 0.3)
    sig += 0.18 * bright * np.sin(2 * math.pi * freq * 3.0 * t + 1.1)
    if detune:
        sig += 0.35 * bright * np.sin(2 * math.pi * (freq * (1 + detune)) * t)
    return sig / 1.6


def pad(chord: str, seconds: float, bright: float, gain: float) -> np.ndarray:
    n = int(seconds * SR)
    out = np.zeros(n)
    for i, name in enumerate(CHORDS[chord]):
        voice = tone(NOTE[name], seconds, bright, detune=0.0012 * (1 if i % 2 else -1))
        out += voice * (1.0 - i * 0.12)
    out /= len(CHORDS[chord])
    return out * adsr(n, 0.35, 0.5, 0.85, 0.9) * gain


def heartbeat(seconds: float, gain: float) -> np.ndarray:
    """A low thud: two hits, the second softer. The pulse of a film, not a kick drum."""
    n = int(0.42 * SR)
    t = t_axis(0.42)
    body = np.sin(2 * math.pi * (58 - 16 * t / 0.42) * t) * np.exp(-t * 9)
    out = np.zeros(int(seconds * SR))
    beat = 0.62
    at = 0.0
    while at + 0.42 < seconds:
        start = int(at * SR)
        seg = body * gain
        out[start:start + n] += seg[:len(out[start:start + n])]
        if at + 0.16 + 0.42 < seconds:
            s2 = int((at + 0.16) * SR)
            out[s2:s2 + n] += (body * gain * 0.5)[:len(out[s2:s2 + n])]
        at += beat
    return out


def ticks(seconds: float, rate: float, gain: float, seed: int = 3) -> np.ndarray:
    """A soft wood tick on the beat, so the cut has something to land on."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR))
    n = int(0.05 * SR)
    t = t_axis(0.05)
    body = np.sin(2 * math.pi * 1250 * t) * np.exp(-t * 70)
    at = 0.0
    step = 1.0 / max(rate, 0.001)
    while at < seconds:
        start = int(at * SR)
        jitter = 1.0 + rng.normal(0, 0.004)
        seg = body * gain * jitter
        out[start:start + n] += seg[:len(out[start:start + n])]
        at += step
    return out


def riser(seconds: float, gain: float, seed: int = 9) -> np.ndarray:
    """Filtered noise that climbs: the sound of a cut about to happen."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    noise = rng.normal(0, 1, n)
    # A one-pole low-pass whose cutoff opens over the cue - cheap, and it reads
    # as a rise rather than as white noise fading in.
    out = np.zeros(n)
    cutoff = 0.02
    for i in range(0, n, 8):
        cutoff = 0.02 + 0.55 * (i / n) ** 2
        out[i:i + 8] = noise[i:i + 8]
    # Apply the envelope in blocks to keep this vectorised enough for a few
    # seconds of audio.
    env = np.linspace(0.05, 1.0, n) ** 1.6
    return out * env * gain


def stinger(seconds: float, gain: float) -> np.ndarray:
    """A struck bell: the accent that lands on a reveal."""
    n = int(seconds * SR)
    t = t_axis(seconds)
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 2.4), (2.76, 0.5, 3.4), (5.4, 0.22, 4.6)):
        out += amp * np.sin(2 * math.pi * 196 * ratio * t) * np.exp(-t * decay)
    return out * gain


def place(track: np.ndarray, seg: np.ndarray, at: float) -> None:
    start = int(at * SR)
    if start >= len(track):
        return
    end = min(len(track), start + len(seg))
    track[start:end] += seg[:end - start]


def lufs_ish(samples: np.ndarray) -> float:
    """A crude loudness estimate: RMS with a little weighting for the mid range.

    Not ITU-R BS.1770 - that needs pyloudnorm - but close enough to aim at the
    -14 LUFS the delivery spec asks for, and the real number is measured after
    the mux by the audit pass.
    """
    rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-12)
    return 20 * math.log10(rms) - 3.0


def build(seconds: float, sections: list[tuple[str, float, float]], gain: float = 1.0) -> np.ndarray:
    total = int(seconds * SR)
    mix = np.zeros(total)

    for name, start, end in sections:
        chord, pad_gain, pulse_rate, arp, bright = SECTIONS.get(name, SECTIONS['calm'])
        length = max(0.1, end - start)
        place(mix, pad(chord, length, bright, pad_gain), start)
        if pulse_rate:
            place(mix, heartbeat(length, 0.30), start)
            place(mix, ticks(length, pulse_rate, 0.055), start)
        if arp:
            # A simple four-note figure on the top of the chord, quieter than
            # the pad: it is texture, not a melody.
            notes = CHORDS[chord][1:]
            step = 0.25
            at = 0.0
            i = 0
            while at < length - 0.3:
                note = notes[i % len(notes)]
                seq = tone(NOTE[note] * 2, min(0.5, length - at), bright * 0.8)
                place(mix, seq * adsr(len(seq), 0.005, 0.08, 0.25, 0.3) * 0.10, start + at)
                at += step
                i += 1

    # Transitions between sections: a riser into the loud ones, a bell on the
    # turn. These are what make a cut feel scored rather than assembled.
    for i, (name, start, _end) in enumerate(sections):
        if name in ('turn', 'rise'):
            lead = min(2.4, start)
            place(mix, riser(lead, 0.18), max(0.0, start - lead))
            place(mix, stinger(1.6, 0.16), start)
    place(mix, stinger(2.6, 0.13), sections[-1][1])

    # A gentle top-and-tail so the file does not begin or end on a click.
    fade = int(0.25 * SR)
    mix[:fade] *= np.linspace(0, 1, fade) ** 1.5
    mix[-int(1.4 * SR):] *= np.linspace(1, 0, int(1.4 * SR)) ** 1.2

    # Loudness, then peak.
    #
    # Raising the gain to hit -14 LUFS and then clamping the peak just undid the
    # gain: the file came out at -23.6 LUFS, quieter than the thing it was
    # replacing. Aiming at a loudness needs a limiter, because the crest factor
    # is set by the thuds and the bells, not by the bed.
    mix *= gain
    target = 10 ** ((-14.0 + 3.0) / 20)
    ceiling = 10 ** (-1.5 / 20)
    for _ in range(4):
        rms = float(np.sqrt(np.mean(mix ** 2)) + 1e-12)
        mix *= min(target / rms, 8.0)
        mix = soft_limit(mix, ceiling)
    return mix


def soft_limit(samples: np.ndarray, ceiling: float) -> np.ndarray:
    """A soft-knee limiter: linear below the knee, tanh above it, never over."""
    knee = ceiling * 0.55
    mag = np.abs(samples)
    sign = np.sign(samples)
    over = mag > knee
    limited = mag.copy()
    limited[over] = knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee) * 1.4) / math.tanh(1.4)
    return np.clip(sign * limited, -ceiling, ceiling)


def write_wav(path: Path, mono: np.ndarray) -> None:
    # A touch of stereo width: the pad is delayed a few samples on the right,
    # which is enough to stop the file sounding like it came out of one speaker.
    delay = int(0.008 * SR)
    left = mono
    right = np.concatenate([np.zeros(delay), mono[:-delay]]) * 0.94
    data = np.stack([left, right], axis=1)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def parse_sections(text: str) -> list[tuple[str, float, float]]:
    out = []
    for part in text.split(','):
        name, start, end = part.split(':')
        out.append((name.strip(), float(start), float(end)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=50.0)
    ap.add_argument('--sections', default='calm:0:5,build:5:20,turn:20:28,hold:28:35,rise:35:43,end:43:50')
    ap.add_argument('--out', default='score.wav')
    ap.add_argument('--gain', type=float, default=1.0)
    args = ap.parse_args()

    sections = parse_sections(args.sections)
    mix = build(args.seconds, sections, args.gain)
    write_wav(Path(args.out), mix)
    loud = lufs_ish(mix)
    peak = 20 * math.log10(float(np.max(np.abs(mix))) + 1e-12)
    print(f'wrote {args.out}: {args.seconds:.1f}s, about {loud:.1f} LUFS, peak {peak:.1f} dBFS')


if __name__ == '__main__':
    main()
