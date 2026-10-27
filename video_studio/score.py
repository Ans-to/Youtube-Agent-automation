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
import json
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
    # The opening was the quietest two seconds of the film and it faded in from
    # nothing, so the first sound a viewer heard arrived at -29 dBFS half a second
    # in. A hook is not the place for the score to be shy.
    'calm':    ('am-low', 0.30, False, 0.62, 0.30, -2.0),
    'warm':    ('f', 0.24, True, 0.0, 0.35, -3.0),
    'moving':  ('am7', 0.22, True, 0.9, 0.32, -1.0),
    'tense':   ('dm', 0.24, True, 1.15, 0.28, -2.5),
    'sparse':  ('am-low', 0.24, True, 0.42, 0.24, -5.0),
    'history': ('c', 0.24, True, 0.0, 0.38, -4.0),
    'build':   ('g', 0.34, True, 0.85, 0.36, 0.0),
    'resolve': ('am', 0.30, True, 0.0, 0.30, -0.5),
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


def pad(chord: str, seconds: float, bright: float, gain: float,
        fade_in: float = 0.35, fade_out: float = 1.4) -> np.ndarray:
    """A soft choir-ish pad: detuned sines, low-passed, slow in and out.

    The envelope is short at the front and long at the back on purpose. It used
    to be 0.9 in and 1.2 out inside the section's own length, so every bed had
    gone quiet 1.2 s before its cut and the next one only reached level 0.9 s
    after it: a hole at every join. The bed now spills past its cut and the next
    one rises under it, which is a crossfade rather than a gap.
    """
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
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    if fi + fo >= n:
        # A very short section: keep the shape, squeeze it to fit.
        fi = max(1, int(n * fade_in / max(fade_in + fade_out, 1e-6)))
        fo = max(1, n - fi - 1)
    env = np.concatenate([
        np.linspace(0, 1, fi),
        np.ones(max(1, n - fi - fo)),
        np.linspace(1, 0, fo),
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
    if kind == 'tick':
        # A hard cut: a transient, not a boom. Thirty milliseconds of felt on a
        # table, low enough to sit under a word and short enough to be gone
        # before the next frame.
        n = int(0.20 * SR)
        out = np.zeros(n)
        place(out, lowpass(_grain(0.055, 5), 2600) * 0.55, 0.0)
        place(out, thud(0.20, 0.30 * gain), 0.0)
        return out * gain
    if kind == 'whoosh':
        # A wipe or a push: the room moving past the lens. Dark noise that opens
        # and closes again - two filtered copies crossfaded, because a filter
        # whose cutoff changes needs a filter per block and this needs to stay
        # cheap and deterministic.
        dur = 0.62
        n = int(dur * SR)
        x = _grain(dur, 9)
        t = np.arange(n) / SR
        env = np.minimum(1, t / (dur * 0.6)) ** 1.6 * np.exp(-np.maximum(0, t - dur * 0.6) / (dur * 0.13))
        dark = lowpass(x, 700) * env
        bright = lowpass(x, 2400) * env
        k = np.clip((t / dur - 0.35) / 0.5, 0, 1)
        out = dark * (1 - k) + bright * k
        return out * gain
    if kind == 'rustle':
        # Paper: a join that turns from one era to the next. Three grains, all
        # under 3.6 kHz, so it reads as a page and not as a hiss.
        dur = 0.42
        n = int(dur * SR)
        out = np.zeros(n)
        for i, at in enumerate((0.0, 0.07, 0.16)):
            seg = _grain(0.09, 13 + i)
            seg = highpass(lowpass(seg, 3400), 700)
            env = np.exp(-np.arange(len(seg)) / (0.022 * SR))
            place(out, seg * env * (0.5 - i * 0.09) * gain, at)
        return out
    if kind == 'pull':
        # A rack focus: the same trick as the whoosh, closing instead of opening.
        dur = 0.55
        n = int(dur * SR)
        x = _grain(dur, 17)
        t = np.arange(n) / SR
        # a focus pull opens before it closes: 110 ms to rise, then decay
        env = np.minimum(1, t / 0.11) ** 1.5 * np.exp(-np.maximum(0, t - 0.11) / (dur * 0.34))
        bright = lowpass(x, 2200) * env
        dark = lowpass(x, 520) * env
        k = np.clip(t / dur, 0, 1)
        return (bright * (1 - k) + dark * k) * gain * 0.9
    if kind == 'close':
        # An iris: the light going out of the frame. A tone falling, under a thud.
        n = int(1.1 * SR)
        t = np.arange(n) / SR
        sweep = 132 - 76 * np.minimum(1, t / 0.9)
        phase = 2 * math.pi * np.cumsum(sweep) / SR
        tone = np.sin(phase) * np.minimum(1, t / 0.13) ** 1.4 * np.exp(-t / 0.55)
        out = tone * 0.35
        place(out, thud(0.9, 0.42 * gain), 0.0)
        return out * gain
    raise SystemExit(f'unknown cue {kind!r}')


def _grain(seconds: float, seed: int) -> np.ndarray:
    """Deterministic noise. The score has to render the same film twice."""
    n = int(seconds * SR)
    return np.random.default_rng(seed).normal(0, 1, n)


# --------------------------------------------------------------------------
# Which sound belongs on which join.
#
# A cut is not a cue sheet entry, it is a decision the director already made:
# `motion/director.mjs` picks `cut` when something changes, `dissolve` when time
# passes in the same place, `wipe-left` when the film travels. The soundtrack
# reads the same list, so the sound follows the picture's own grammar - and a
# different film gets its own effects without anybody typing them again.
#
# `lead` is how far *before* the boundary the sound starts. A transient that
# begins exactly on the cut arrives after it - the ear hears sound as the
# consequence of an edit instead of the two landing together. Everything here is
# pre-lapped so its energy peaks on the frame.
# --------------------------------------------------------------------------
# kind, seconds from the start of the sound to its loudest moment, pan, level.
#
# Measured, not guessed: each of these was rendered, its envelope smoothed and
# its maximum located. A cut's transient peaks in 10 ms, a whoosh halfway through
# its sweep, a bloom three tenths after it opens.
TRANSITION_CUE = {
    'cut':        ('tick', 0.007, 0.0, 1.00),
    'rack':       ('pull', 0.124, 0.0, 0.80),
    'dissolve':   ('bloom', 1.861, 0.0, 0.85),
    'fade-paper': ('rustle', 0.162, 0.0, 0.90),
    'iris':       ('close', 0.132, 0.0, 0.85),
    'wipe-left':  ('whoosh', 0.356, -0.55, 1.00),
    'push-left':  ('whoosh', 0.356, -0.35, 0.85),
    'wipe-right': ('whoosh', 0.356, 0.55, 1.00),
    'push-right': ('whoosh', 0.356, 0.35, 0.85),
    'push-up':    ('whoosh', 0.356, 0.0, 0.80),
}


def cues_from_starts(shots: list[dict]) -> list[tuple[float, str, float, float]]:
    """One sound per join, read off the film's own edit list."""
    out = []
    for shot in shots[1:]:
        row = TRANSITION_CUE.get((shot.get('transition') or 'cut').strip())
        if row is None:
            raise SystemExit(f'no sound for the {shot.get("transition")!r} join in {shot.get("id")!r}')
        kind, peak, pan, level = row
        at = max(0.0, float(shot['start']) - peak)
        out.append((at, kind, level, pan))
    return out


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

def cue_bus(total: int, cues: list[tuple[float, ...]]) -> np.ndarray:
    """Place every effect in stereo, at equal power, at its own pan position."""
    bus = np.zeros((2, total))
    for row in cues:
        at, kind = float(row[0]), str(row[1])
        level = float(row[2]) if len(row) > 2 else 1.0
        pan = float(row[3]) if len(row) > 3 else 0.0
        seg = cue(kind, gain=level)
        # Normalise the event itself, then weigh it: otherwise a 20 ms tick and a
        # 3 s bloom land at wildly different levels for the same `level`. Twelve
        # decibels under full scale is two above the bed's RMS and eight under its
        # peaks - a join you hear without the music getting out of its way.
        top = float(np.abs(seg).max()) + 1e-9
        seg = seg / top * 10 ** (-12.0 / 20)
        start = int(at * SR)
        if start >= total or start < 0:
            continue
        end = min(total, start + len(seg))
        seg = seg[:end - start]
        # equal power: -1 hard left, 0 centre, +1 hard right
        angle = (np.clip(pan, -1, 1) + 1) * math.pi / 4
        bus[0, start:end] += seg * math.cos(angle)
        bus[1, start:end] += seg * math.sin(angle)
    return bus


def build(seconds: float, sections: list[tuple[str, float, float]], gain: float = 1.0,
          cues: list[tuple[str, float]] | None = None, starts: list[dict] | None = None,
          stereo: bool = False):
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
        # Beds overlap across a cut, so the join is a crossfade and not a hole.
        # The last one does not spill: it ends *with* the film, on a short decay,
        # so the final chord is still ringing when the picture goes black.
        last = end >= seconds - 0.05
        spill = 0.0 if last else 1.2
        place(mix, pad(chord, length + spill, bright, pad_gain,
                       fade_in=(0.45 if start <= 0.01 else 0.35),
                       fade_out=(0.35 if last else 1.4)) * const_gain, start)

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

    # One breath of air into the turns, at low level.
    #
    # `moving` is in this list because of the film's first edit: between the end
    # of the opening line and the cut at 5.9 s there was a 1.2 s hole at -29 dBFS,
    # and the ear reads a hole in the sound as the film stopping.
    for name, start, _end in sections:
        if name in ('moving', 'tense', 'build'):
            lead = min(1.6, start)
            place(mix, swell(lead, 0.055), max(0.0, start - lead))

    mix = reverb(mix, wet=0.22, decay=1.9)

    # Gentle shaping: nothing above 7 kHz, a little weight below 200 Hz removed
    # so the pad does not boom, and a soft top-and-tail.
    mix = lowpass(mix, 7000)
    mix = highpass(mix, 38)
    fade = int(0.12 * SR)
    mix[:fade] *= np.linspace(0, 1, fade) ** 1.2
    # The old tail was two seconds, which on this film was a second and a quarter
    # of digital silence after the last word: it read as the sound dropping out.
    # The chord now decays on its own and this fade only stops the click.
    tail = int(0.2 * SR)
    mix[-tail:] *= np.linspace(1, 0, tail) ** 1.1

    mix *= gain
    # Normalise on the loud passages, not on the average: normalising the mean
    # is what flattened the score in the first place.
    target = 10 ** ((-14.0 + 3.0) / 20)
    ceiling = 10 ** (-1.5 / 20)
    for _ in range(4):
        rms = float(np.sqrt(np.mean(mix ** 2)) + 1e-12)
        mix *= min(target / rms, 6.0)
        mix = soft_limit(mix, ceiling)

    events = list(cues or [])
    if starts:
        events += cues_from_starts(starts)
    bus = cue_bus(total, events)

    delay = int(0.011 * SR)
    wide = np.stack([mix, np.concatenate([np.zeros(delay), mix[:-delay]]) * 0.96])
    # The bed is limited on its own and leaves the effects three decibels of
    # room. Limiting the sum instead meant every effect at every join was squashed
    # by the music it was supposed to punctuate - measured, a -17 dBFS tick was
    # arriving 14 dB quieter than it was rendered.
    bed = soft_limit(wide, ceiling * 0.80)
    out = bed + bus
    if np.abs(out).max() > ceiling:
        out = soft_limit(out, ceiling)
    # (frames, channels) on the way out: a stereo pair written row-major as
    # (channels, frames) is white noise, and it sounds like a fault in the mixer.
    return out.T if stereo else out.mean(axis=0)


def soft_limit(x: np.ndarray, ceiling: float) -> np.ndarray:
    knee = ceiling * 0.62
    mag = np.abs(x)
    sign = np.sign(x)
    over = mag > knee
    out = mag.copy()
    out[over] = knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee) * 1.2) / math.tanh(1.2)
    return np.clip(sign * out, -ceiling, ceiling)


def write_wav(path: Path, data: np.ndarray) -> None:
    """Write a stereo pair, or a mono signal widened by a hair."""
    if data.ndim == 1:
        delay = int(0.011 * SR)
        left = data
        right = np.concatenate([np.zeros(delay), data[:-delay]]) * 0.96
        data = np.stack([left, right], axis=1)
    elif data.shape[0] == 2 and data.shape[1] > 2:
        data = data.T
    pcm = (np.clip(data, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def parse_cues(text: str) -> list[tuple[float, str, float, float]]:
    out = []
    for part in text.split(','):
        if not part.strip():
            continue
        bits = part.split(':')
        at, kind = float(bits[0]), bits[1].strip()
        level = float(bits[2]) if len(bits) > 2 else 1.0
        pan = float(bits[3]) if len(bits) > 3 else 0.0
        out.append((at, kind, level, pan))
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
    ap.add_argument('--cues', default='', help='time:kind[:level[:pan]], comma separated')
    ap.add_argument('--starts', default='',
                    help="the film's --starts.json: one sound per join, from its transitions")
    args = ap.parse_args()

    starts = None
    if args.starts:
        starts = json.loads(Path(args.starts).read_text())
    mix = build(args.seconds, parse_sections(args.sections), args.gain,
                parse_cues(args.cues) if args.cues else None,
                starts=starts, stereo=True)
    write_wav(Path(args.out), mix)
    rms = 20 * math.log10(float(np.sqrt(np.mean(mix ** 2))) + 1e-12)
    peak = 20 * math.log10(float(np.max(np.abs(mix))) + 1e-12)
    print(f'wrote {args.out}: {args.seconds:.1f}s, about {rms - 3:.1f} LUFS, peak {peak:.1f} dBFS')


if __name__ == '__main__':
    main()
