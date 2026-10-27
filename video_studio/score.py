#!/usr/bin/env python3
"""Synthesise a restrained score for a motion-graphics film.

The first version was irritating and the measurement said why: at three points in
the film, 81% of the audio energy sat above 4 kHz with a spectral centroid near
11 kHz, at a level louder than the music. That is broadband noise. The function
called `riser` computed a filter cutoff and then never applied it - it wrote the
raw white noise straight out. Two other things made it worse: a 1,250 Hz click on
every beat, and a bell with inharmonic partials at 2.76x and 5.4x, which is the
recipe for a metallic ring.

This version is built the other way round: everything tonal, everything
low-passed, nothing above about 6 kHz except a breath of felt on the plucks, and
a reverb to sit it all in one room.

    python video_studio/score.py --seconds 51 --sections "calm:0:4,..." --out score.wav

Deterministic: the same section list gives the same file.
"""
from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000

NOTE = {
    'A1': 55.00, 'C2': 65.41, 'D2': 73.42, 'E2': 82.41, 'F2': 87.31, 'G2': 98.00,
    'A2': 110.00, 'C3': 130.81, 'D3': 146.83, 'E3': 164.81, 'F3': 174.61,
    'G3': 196.00, 'A3': 220.00, 'B3': 246.94, 'C4': 261.63, 'D4': 293.66,
    'E4': 329.63, 'F4': 349.23, 'G4': 392.00, 'A4': 440.00, 'C5': 523.25,
    'E5': 659.26,
}

CHORDS = {
    'am': ['A2', 'C3', 'E3', 'A3'],
    'am7': ['A2', 'E3', 'G3', 'A3'],
    'f': ['F2', 'A2', 'C3', 'F3'],
    'c': ['C3', 'G3', 'C4', 'E4'],
    'g': ['G2', 'B3', 'D4', 'G3'],
    'dm': ['D3', 'F3', 'A3', 'D4'],
    'em': ['E3', 'G3', 'B3', 'E4'],
    'am-low': ['A1', 'A2', 'E3', 'C4'],
}

# name: chord, pad gain, pluck pattern on/off, pulse per second, brightness
# A section is (chord, pad gain, plucks, pulse rate, brightness, level).
#
# The level is the fix for a mix that measured flat: every two seconds of the
# delivered film sat between -15 and -22 dB, so fifty-seven seconds of music had
# the dynamic range of a room tone. Each mood had its own harmony and its own
# pulse, but they all arrived at the master at the same loudness, because the
# whole score was normalised once at the end. A quiet passage has to *be* quiet.
# These are decibels relative to the loudest section, and they follow the film:
# under the first hook it is present, under "too late" it almost leaves, and the
# reveal at 48.7 s opens up.
SECTIONS = {
    'calm':    ('am-low', 0.30, False, 0.0, 0.30, -6.0),
    'warm':    ('f', 0.24, True, 0.0, 0.35, -3.0),
    'moving':  ('am7', 0.22, True, 0.9, 0.32, -1.0),
    'tense':   ('dm', 0.24, True, 1.15, 0.28, -2.5),
    'sparse':  ('am-low', 0.18, False, 0.55, 0.22, -6.0),
    'history': ('c', 0.24, True, 0.0, 0.38, -4.0),
    'build':   ('g', 0.22, True, 0.85, 0.36, 0.0),
    'resolve': ('am', 0.26, True, 0.0, 0.30, -1.5),
}


# --------------------------------------------------------------------------
# Filters. No scipy here, so: FFT masking for static shapes, block-wise for
# anything that opens over time.
# --------------------------------------------------------------------------

def lowpass(x: np.ndarray, cutoff: float, order: float = 2.0) -> np.ndarray:
    """Smooth low-pass by masking the spectrum with a raised cosine above cutoff."""
    n = len(x)
    if n == 0:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll = np.ones_like(freqs)
    band = cutoff * 0.6
    over = freqs > cutoff
    roll[over] = 0.5 * (1 + np.cos(np.pi * np.clip((freqs[over] - cutoff) / band, 0, 1))) ** order
    return np.fft.irfft(spec * roll, n)


def highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    roll = np.ones_like(freqs)
    band = max(cutoff * 0.5, 1)
    under = freqs < cutoff
    roll[under] = 0.5 * (1 - np.cos(np.pi * np.clip((cutoff - freqs[under]) / band, 0, 1)))
    return np.fft.irfft(spec * roll, n)


def opening_filter(x: np.ndarray, start_hz: float, end_hz: float, blocks: int = 12) -> np.ndarray:
    """A filter whose cutoff opens across the signal, crossfaded between blocks."""
    n = len(x)
    out = np.zeros(n)
    bounds = np.linspace(0, n, blocks + 1).astype(int)
    fade = min(int(0.06 * SR), max(1, n // (blocks * 4)))
    for i in range(blocks):
        a, b = bounds[i], bounds[i + 1]
        if b <= a:
            continue
        k = i / max(1, blocks - 1)
        cut = start_hz + (end_hz - start_hz) * (k ** 2)
        seg = lowpass(x[max(0, a - fade): min(n, b + fade)], cut)
        seg = seg[(a - max(0, a - fade)): (b - max(0, a - fade))]
        if len(seg) < b - a:
            seg = np.pad(seg, (0, (b - a) - len(seg)))
        window = np.ones(b - a)
        if i > 0:
            window[:fade] = np.linspace(0, 1, fade)
        if i < blocks - 1:
            window[-fade:] = np.linspace(1, 0, fade)
        out[a:b] = seg[: b - a] * window
    return out


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------

def t_axis(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def pluck(freq: float, seconds: float = 1.6, bright: float = 0.4) -> np.ndarray:
    """A felted note: sine, a soft second harmonic, no metallic partials."""
    t = t_axis(seconds)
    body = np.sin(2 * math.pi * freq * t)
    body += 0.22 * bright * np.sin(2 * math.pi * freq * 2.0 * t + 0.2)
    body += 0.06 * bright * np.sin(2 * math.pi * freq * 3.0 * t + 0.9)
    attack = np.minimum(1, t / 0.012)
    decay = np.exp(-t * 2.6)
    out = body * attack * decay
    # The felt: a touch of noise, filtered hard so it is texture not hiss.
    rng = np.random.default_rng(int(freq * 10) % 9999)
    felt = lowpass(rng.normal(0, 1, len(t)), 1800) * np.exp(-t * 28) * 0.05
    return (out + felt) * 0.5


def pad(chord: str, seconds: float, bright: float, gain: float) -> np.ndarray:
    """A soft choir-ish pad: detuned sines, low-passed, slow in and out."""
    n = int(seconds * SR)
    out = np.zeros(n)
    for i, name in enumerate(CHORDS[chord]):
        f = NOTE[name]
        voice = np.zeros(n)
        for detune in (-0.0016, 0.0, 0.0019):
            voice += np.sin(2 * math.pi * f * (1 + detune) * np.arange(n) / SR + i)
        voice /= 3
        voice += 0.18 * bright * np.sin(2 * math.pi * f * 2 * np.arange(n) / SR)
        out += voice * (1.0 - i * 0.10)
    out = lowpass(out, 2600)
    out /= len(CHORDS[chord])
    env = np.concatenate([
        np.linspace(0, 1, int(0.9 * SR)),
        np.ones(max(1, n - int(2.1 * SR))),
        np.linspace(1, 0, int(1.2 * SR)),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return out * env[:n] * gain


def pulse(seconds: float, gain: float, rate: float) -> np.ndarray:
    """A heartbeat: 55 Hz, low-passed, well under the music."""
    n = int(0.5 * SR)
    t = t_axis(0.5)
    body = np.sin(2 * math.pi * (52 - 8 * t / 0.5) * t) * np.exp(-t * 7)
    body = lowpass(body, 220)
    out = np.zeros(int(seconds * SR))
    at = 0.0
    step = 1.0 / max(rate, 0.001)
    while at + 0.5 < seconds:
        start = int(at * SR)
        seg = body * gain
        seg2 = body * gain * 0.42
        out[start:start + n] += seg[:len(out[start:start + n])]
        s2 = int((at + 0.19) * SR)
        out[s2:s2 + n] += seg2[:len(out[s2:s2 + n])]
        at += step
    return out


def swell(seconds: float, gain: float) -> np.ndarray:
    """Air that opens: noise, but filtered to a narrow band and kept quiet.

    This is the only noise in the score, it never exceeds 1.5 kHz, and it sits
    about 20 dB under the pad. The old riser was broadband and louder than
    everything - that is the sound the owner called irritating, and they are
    right.
    """
    n = int(seconds * SR)
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 1, n)
    shaped = opening_filter(noise, 300, 1400)
    env = (np.linspace(0, 1, n) ** 2.2)
    return shaped * env * gain


def bell(freq: float, seconds: float = 2.6, gain: float = 0.5) -> np.ndarray:
    """A struck tone with only harmonic partials.

    The first version used 2.76x and 5.4x, which is what makes a bell sound like
    a saucepan. A film bell is a sine, its octave, and a fifth above that, all
    decaying together.
    """
    t = t_axis(seconds)
    body = np.sin(2 * math.pi * freq * t)
    body += 0.32 * np.sin(2 * math.pi * freq * 2.0 * t)
    body += 0.14 * np.sin(2 * math.pi * freq * 3.0 * t)
    body += 0.06 * np.sin(2 * math.pi * freq * 4.0 * t)
    attack = np.minimum(1, t / 0.006)
    decay = np.exp(-t * 1.35)
    return body * attack * decay * gain * 0.25


def thud(seconds: float = 1.1, gain: float = 0.5) -> np.ndarray:
    """The floor moving: a pitch drop, not an impact sample."""
    t = t_axis(seconds)
    sweep = 78 - 44 * np.minimum(1, t / 0.7)
    phase = 2 * math.pi * np.cumsum(sweep) / SR
    body = np.sin(phase) * np.exp(-t * 3.2)
    return lowpass(body, 240) * gain


def cluster(freqs: list[float], seconds: float, gain: float = 0.4) -> np.ndarray:
    """A held chord that leans: two notes a semitone apart, under a third."""
    n = int(seconds * SR)
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        out += np.sin(2 * math.pi * f * np.arange(n) / SR + i * 0.7)
    out /= max(1, len(freqs))
    out = lowpass(out, 2200)
    ramp = np.concatenate([
        np.linspace(0, 1, int(0.7 * SR)),
        np.ones(max(1, n - int(1.7 * SR))),
        np.linspace(1, 0, int(1.0 * SR)),
    ])[:n]
    if len(ramp) < n:
        ramp = np.pad(ramp, (0, n - len(ramp)))
    return out * ramp * gain


def ringtone(gain: float = 0.30) -> np.ndarray:
    """A handset ring: two beeps, three times.

    Not a quotation - an interval, played short, the way a phone in another room
    sounds through a wall. Tonal, so it carries the scene instead of hissing
    through it.
    """
    beat = 0.11
    gap = 0.055
    pattern = [NOTE['E5'], NOTE['A4'], NOTE['E5'], NOTE['A4'], NOTE['E5'], NOTE['A4']]
    total = len(pattern) * (beat + gap) + 0.5
    out = np.zeros(int(total * SR))
    at = 0.0
    for i, freq in enumerate(pattern):
        seg = bell(freq, beat + 0.25, 1.0)
        seg = seg[: int((beat + 0.25) * SR)]
        seg = seg * np.minimum(1, np.arange(len(seg)) / (0.004 * SR))
        place(out, seg, at)
        at += beat + gap
        if i % 2 == 1:
            at += 0.16
    return out * gain


def cue(kind: str, gain: float = 1.0) -> np.ndarray:
    """One named sound event. Every film uses these; none of them is noise."""
    if kind == 'ring':
        return ringtone(0.34 * gain)
    if kind == 'turn':
        # The ground moving: a low thud under a semitone cluster that opens out.
        out = thud(1.4, 0.55 * gain)
        lean = cluster([NOTE['D4'], NOTE['D#4'], NOTE['A3']], 2.6, 0.30 * gain)
        place(out, lean, 0.05)
        return out
    if kind == 'reveal':
        out = bell(NOTE['A5'], 3.0, 0.5 * gain)
        place(out, bell(NOTE['E5'], 3.0, 0.32 * gain), 0.02)
        place(out, bell(NOTE['C6'], 2.6, 0.16 * gain), 0.06)
        return out
    if kind == 'impact':
        return thud(1.8, 0.62 * gain)
    if kind == 'bloom':
        return cluster([NOTE['F4'], NOTE['A4'], NOTE['C5']], 3.4, 0.26 * gain)
    raise SystemExit(f'unknown cue {kind!r}')


def place(track: np.ndarray, seg: np.ndarray, at: float) -> None:
    start = int(at * SR)
    if start >= len(track):
        return
    end = min(len(track), start + len(seg))
    track[start:end] += seg[:end - start]


def reverb(x: np.ndarray, wet: float = 0.20, decay: float = 1.9) -> np.ndarray:
    """A small room, made from filtered noise and convolved with FFT."""
    n_ir = int(decay * SR)
    rng = np.random.default_rng(11)
    ir = rng.normal(0, 1, n_ir) * np.exp(-np.arange(n_ir) / (SR * decay * 0.42))
    ir = lowpass(ir, 3200)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    size = 1 << int(math.ceil(math.log2(len(x) + len(ir))))
    wet_sig = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return (1 - wet) * x + wet * wet_sig


# --------------------------------------------------------------------------
# Arrangement
# --------------------------------------------------------------------------

def build(seconds: float, sections: list[tuple[str, float, float]], gain: float = 1.0,
          cues: list[tuple[float, str, float]] | None = None) -> np.ndarray:
    total = int(seconds * SR)
    mix = np.zeros(total)

    for name, start, end in sections:
        # A typo used to fall through to 'calm' and quietly change the mood of a
        # whole passage. Fail instead.
        if name not in SECTIONS:
            raise SystemExit(f'unknown section {name!r}; known: {", ".join(sorted(SECTIONS))}')
        chord, pad_gain, plucks, rate, bright, level_db = SECTIONS[name]
        length = max(0.2, end - start)
        # the section's own loudness, so the score breathes with the film
        const_gain = 10 ** (level_db / 20)
        place(mix, pad(chord, length, bright, pad_gain) * const_gain, start)

        if rate:
            place(mix, pulse(length, 0.16, rate) * const_gain, start)

        if plucks:
            # A slow figure, four notes to the bar at about 72 bpm.
            notes = CHORDS[chord][1:]
            step = 0.62
            at = 0.25
            i = 0
            while at < length - 0.9:
                note = notes[i % len(notes)]
                place(mix, pluck(NOTE[note]) * 0.13 * const_gain, start + at)
                # Every other note an octave up, quietly, for movement.
                if i % 4 == 2:
                    place(mix, pluck(NOTE[note] * 2, bright=0.5) * 0.05 * const_gain, start + at + 0.30)
                at += step
                i += 1

    # One breath of air into the two biggest turns, at low level.
    for name, start, _end in sections:
        if name in ('tense', 'build'):
            lead = min(1.6, start)
            place(mix, swell(lead, 0.055), max(0.0, start - lead))

    mix = reverb(mix, wet=0.22, decay=1.9)

    # Gentle shaping: nothing above 7 kHz, a little weight below 200 Hz removed
    # so the pad does not boom, and a soft top-and-tail.
    mix = lowpass(mix, 7000)
    mix = highpass(mix, 38)
    fade = int(0.4 * SR)
    mix[:fade] *= np.linspace(0, 1, fade) ** 1.4
    tail = int(2.0 * SR)
    mix[-tail:] *= np.linspace(1, 0, tail) ** 1.2

    mix *= gain
    # Normalise on the loud passages, not on the average: normalising the mean
    # is what flattened the score in the first place.
    target = 10 ** ((-14.0 + 3.0) / 20)
    ceiling = 10 ** (-1.5 / 20)
    for _ in range(4):
        rms = float(np.sqrt(np.mean(mix ** 2)) + 1e-12)
        mix *= min(target / rms, 6.0)
        mix = soft_limit(mix, ceiling)
    return mix


def soft_limit(x: np.ndarray, ceiling: float) -> np.ndarray:
    knee = ceiling * 0.62
    mag = np.abs(x)
    sign = np.sign(x)
    over = mag > knee
    out = mag.copy()
    out[over] = knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee) * 1.2) / math.tanh(1.2)
    return np.clip(sign * out, -ceiling, ceiling)


def write_wav(path: Path, mono: np.ndarray) -> None:
    delay = int(0.011 * SR)
    left = mono
    right = np.concatenate([np.zeros(delay), mono[:-delay]]) * 0.96
    data = np.stack([left, right], axis=1)
    pcm = (np.clip(data, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def parse_cues(text: str) -> list[tuple[float, str, float]]:
    out = []
    for part in text.split(','):
        if not part.strip():
            continue
        bits = part.split(':')
        at, kind = float(bits[0]), bits[1].strip()
        level = float(bits[2]) if len(bits) > 2 else 1.0
        out.append((at, kind, level))
    return out


def parse_sections(text: str) -> list[tuple[str, float, float]]:
    out = []
    for part in text.split(','):
        name, start, end = part.split(':')
        out.append((name.strip(), float(start), float(end)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=51.0)
    ap.add_argument('--sections', default='calm:0:4,warm:4:9,moving:9:16,tense:16:23,sparse:23:30,history:30:37,build:37:44,resolve:44:51')
    ap.add_argument('--out', default='score.wav')
    ap.add_argument('--gain', type=float, default=1.0)
    ap.add_argument('--cues', default='', help='time:kind[:level], comma separated')
    args = ap.parse_args()

    mix = build(args.seconds, parse_sections(args.sections), args.gain,
                parse_cues(args.cues) if args.cues else None)
    write_wav(Path(args.out), mix)
    rms = 20 * math.log10(float(np.sqrt(np.mean(mix ** 2))) + 1e-12)
    peak = 20 * math.log10(float(np.max(np.abs(mix))) + 1e-12)
    print(f'wrote {args.out}: {args.seconds:.1f}s, about {rms - 3:.1f} LUFS, peak {peak:.1f} dBFS')


if __name__ == '__main__':
    main()
