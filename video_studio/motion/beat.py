#!/usr/bin/env python3
"""Beat and onset analysis, so cuts and cues can land on the music.

Pure Python, no dependencies. The FFT is shared with the auditor's DSP so the
studio has one radix-2 implementation rather than two subtly different ones.

What this module can honestly claim: onset times, a tempo estimate, and a beat
grid derived from the audio. What it cannot claim: musical downbeats, phrase
boundaries, or that a cut "feels" musical. Those remain directorial decisions.
"""
from __future__ import annotations

import math
import statistics
import wave
from array import array
from pathlib import Path

from audit.audio import _fft

FFT_SIZE = 1024
HOP = 512
MIN_TEMPO = 60.0
MAX_TEMPO = 180.0
MAX_ANALYSIS_SECONDS = 1_800


def read_wav(path: str | Path) -> tuple[list[float], int]:
    """Read PCM WAV into mono floats in -1..1, at its native sample rate."""
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        width = stream.getsampwidth()
        rate = stream.getframerate()
        frames = stream.getnframes()
        raw = stream.readframes(frames)
    if channels < 1 or channels > 2:
        raise ValueError("Beat analysis supports mono or stereo WAV files")
    if width not in (1, 2, 4):
        raise ValueError("Beat analysis supports 8-, 16- and 32-bit PCM WAV files")
    if rate < 8000 or rate > 192000:
        raise ValueError("Beat analysis needs a sample rate between 8 and 192 kHz")
    if frames <= 0:
        raise ValueError("Audio file contains no samples")
    if frames / rate > MAX_ANALYSIS_SECONDS:
        raise ValueError("Audio file exceeds the 30-minute analysis limit")

    if width == 1:
        values = [(byte - 128) / 128.0 for byte in raw]
    else:
        samples = array("h" if width == 2 else "i")
        samples.frombytes(raw)
        if __import__("sys").byteorder != "little":
            samples.byteswap()
        scale = 32768.0 if width == 2 else 2147483648.0
        values = [value / scale for value in samples]
    if channels == 2:
        values = [(values[index] + values[index + 1]) * 0.5
                  for index in range(0, len(values) - 1, 2)]
    return values, rate


def spectral_flux(samples: list[float], sample_rate: int,
                  fft_size: int = FFT_SIZE, hop: int = HOP) -> dict:
    """Positive spectral difference per frame. The standard onset detector."""
    if fft_size & (fft_size - 1):
        raise ValueError("FFT size must be a power of two")
    if hop < 1 or fft_size < 32:
        raise ValueError("FFT size and hop are out of range")
    if len(samples) < fft_size:
        return {"times": [], "flux": [], "hop": hop, "fft_size": fft_size, "rate": sample_rate}

    window = [0.5 - 0.5 * math.cos(2 * math.pi * index / (fft_size - 1)) for index in range(fft_size)]
    times: list[float] = []
    flux: list[float] = []
    previous: list[float] | None = None
    for start in range(0, len(samples) - fft_size + 1, hop):
        real = [samples[start + index] * window[index] for index in range(fft_size)]
        imag = [0.0] * fft_size
        _fft(real, imag)
        bins = fft_size // 2
        magnitude = [math.hypot(real[index], imag[index]) / bins for index in range(1, bins)]
        if previous is None:
            value = 0.0
        else:
            value = sum(max(0.0, magnitude[index] - previous[index])
                        for index in range(len(magnitude)))
        previous = magnitude
        times.append(start / sample_rate)
        flux.append(value)
    return {"times": times, "flux": flux, "hop": hop, "fft_size": fft_size, "rate": sample_rate}


def detect_onsets(flux: list[float], times: list[float], *,
                  threshold: float = 1.4, min_gap_seconds: float = 0.08) -> list[dict]:
    """Peaks in spectral flux that clear a local adaptive threshold."""
    if len(flux) != len(times):
        raise ValueError("Flux and time series must be the same length")
    if not flux:
        return []
    if threshold < 1.0:
        raise ValueError("Onset threshold must be at least 1.0x the local mean")
    if min_gap_seconds <= 0:
        raise ValueError("Onset gap must be positive")

    window = 8
    onsets = []
    last_time = -1e9
    for index, value in enumerate(flux):
        low = max(0, index - window)
        high = min(len(flux), index + window + 1)
        local = statistics.fmean(flux[low:high])
        absolute = statistics.fmean(flux) * 0.6
        if value < max(local * threshold, absolute) or value <= 0:
            continue
        if index > 0 and flux[index - 1] > value:
            continue
        if index + 1 < len(flux) and flux[index + 1] > value:
            continue
        if times[index] - last_time < min_gap_seconds:
            continue
        onsets.append({
            "time": round(times[index], 3),
            "strength": round(value, 5),
        })
        last_time = times[index]
    return onsets


def estimate_tempo(onsets: list[dict], min_bpm: float = MIN_TEMPO,
                   max_bpm: float = MAX_TEMPO) -> dict:
    """Tempo from inter-onset intervals, folded into a musical range."""
    if min_bpm <= 0 or max_bpm <= min_bpm:
        raise ValueError("Tempo range is invalid")
    times = [item["time"] for item in onsets]
    if len(times) < 4:
        return {"bpm": None, "confidence": 0.0, "samples": len(times),
                "reason": "too few onsets for a tempo estimate"}

    weights: dict[float, float] = {}
    for index in range(1, len(times)):
        interval = times[index] - times[index - 1]
        if not 0.18 <= interval <= 2.0:
            continue
        bpm = 60.0 / interval
        while bpm < min_bpm:
            bpm *= 2.0
        while bpm > max_bpm:
            bpm /= 2.0
        key = round(bpm, 1)
        weights[key] = weights.get(key, 0.0) + 1.0

    if not weights:
        return {"bpm": None, "confidence": 0.0, "samples": len(times),
                "reason": "no interval fell inside the musical range"}

    # Fold harmonically related candidates (half/double time) together.
    folded: dict[float, float] = {}
    for bpm, weight in weights.items():
        candidate = bpm
        for factor in (0.5, 2.0):
            other = round(bpm * factor, 1)
            if other in weights and abs(math.log2(other / candidate)) < 1e-6:
                continue
        folded[candidate] = folded.get(candidate, 0.0) + weight
    best_bpm, best_weight = max(folded.items(), key=lambda item: (item[1], -abs(item[0] - 120.0)))
    total = sum(folded.values())
    return {
        "bpm": round(best_bpm, 1),
        "confidence": round(min(1.0, best_weight / total), 3),
        "samples": len(times),
        "reason": "inter-onset histogram",
    }


def beat_grid(tempo: dict, duration_seconds: float, offset_seconds: float = 0.0) -> list[float]:
    """Evenly spaced beat times from a tempo estimate."""
    if not tempo.get("bpm"):
        return []
    duration = float(duration_seconds)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Beat grid needs a positive duration")
    period = 60.0 / float(tempo["bpm"])
    count = int(math.floor((duration - offset_seconds) / period)) + 1
    return [round(offset_seconds + index * period, 3) for index in range(max(0, count))]


def nearest_beat(time_seconds: float, beats: list[float]) -> tuple[float, float]:
    """Closest beat and the signed distance to it."""
    if not beats:
        return (float(time_seconds), 0.0)
    closest = min(beats, key=lambda beat: abs(beat - time_seconds))
    return (closest, round(closest - float(time_seconds), 3))


def snap_to_beats(times: list[float], beats: list[float], tolerance: float = 0.12) -> dict:
    """Snap cue times to the nearest beat when it is close enough.

    A cue farther than ``tolerance`` from any beat is left alone and reported.
    Silently dragging a cut onto the grid would break narration sync.
    """
    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError("Snap tolerance must be finite and non-negative")
    snapped = []
    moved = 0
    for value in times:
        beat, delta = nearest_beat(value, beats)
        if beats and abs(delta) <= tolerance:
            snapped.append(round(beat, 3))
            if abs(delta) > 1e-6:
                moved += 1
        else:
            snapped.append(round(float(value), 3))
    return {"times": snapped, "moved": moved, "tolerance": tolerance,
            "unsnapped": sum(1 for value in times if abs(nearest_beat(value, beats)[1]) > tolerance)}


SFX_FOR_TRANSITION = {
    "cut": None,
    "whip-pan": "whoosh",
    "masked-reveal": "riser",
    "morph": "swell",
    "glitch": "glitch",
    "match-cut": "click",
    "fade": "swell",
    "wipe-left": "whoosh",
    "wipe-right": "whoosh",
    "slide-left": "whoosh",
    "slide-right": "whoosh",
    "zoom": "riser",
    "push": "riser",
    "dissolve": "swell",
}

SFX_LENGTH = {
    "whoosh": 0.32,
    "riser": 0.55,
    "swell": 0.70,
    "glitch": 0.18,
    "click": 0.09,
    "impact": 0.40,
    "pop": 0.12,
}


def cue_sheet(timeline: list[dict], beats: list[float] | None = None,
              tolerance: float = 0.10, master_gain: float = 1.0) -> dict:
    """Sound cues for a directed timeline.

    ``timeline`` entries need ``start``, ``transition_in`` and ``impact``. Cues
    sit at the scene start (the edit point), never on top of the first word of
    narration; gain is capped so speech stays dominant.
    """
    if not 0.0 <= master_gain <= 1.0:
        raise ValueError("Master gain must be between 0 and 1")
    cues = []
    for index, shot in enumerate(timeline):
        start = float(shot.get("start", 0.0))
        if index > 0:
            kind = SFX_FOR_TRANSITION.get(str(shot.get("transition_in", "cut")).lower())
            if kind:
                cues.append({
                    "scene": index + 1,
                    "at": round(start, 3),
                    "kind": kind,
                    "gain": round(min(0.42, 0.26 + 0.10 * (1 if kind in ("whoosh", "riser") else 0)) * master_gain, 3),
                    "length": SFX_LENGTH[kind],
                })
        if shot.get("impact"):
            cues.append({
                "scene": index + 1,
                "at": round(max(0.0, start + float(shot.get("impact_at", 0.12))), 3),
                "kind": "impact",
                "gain": round(0.34 * master_gain, 3),
                "length": SFX_LENGTH["impact"],
            })
    times = [cue["at"] for cue in cues]
    snapped = snap_to_beats(times, beats or [], tolerance=tolerance) if beats else {
        "times": times, "moved": 0, "tolerance": tolerance, "unsnapped": 0,
    }
    for cue, when in zip(cues, snapped["times"], strict=True):
        cue["at"] = when
    return {
        "cues": cues,
        "snapped": snapped,
        "beat_count": len(beats or []),
        "max_gain": max((cue["gain"] for cue in cues), default=0.0),
        "note": "Cues are short and quiet by design; narration remains foreground.",
    }


def analyze(path: str | Path, duration_seconds: float | None = None) -> dict:
    """Full beat analysis for a WAV file, plus a beat grid when a tempo exists."""
    samples, rate = read_wav(path)
    duration = duration_seconds if duration_seconds is not None else len(samples) / rate
    flux = spectral_flux(samples, rate)
    onsets = detect_onsets(flux["flux"], flux["times"])
    tempo = estimate_tempo(onsets)
    first = onsets[0]["time"] if onsets else 0.0
    grid = beat_grid(tempo, duration, offset_seconds=first)
    return {
        "duration_seconds": round(duration, 3),
        "sample_rate": rate,
        "onsets": onsets,
        "tempo": tempo,
        "beats": grid,
        "beat_count": len(grid),
        "source": "fft-spectral-flux",
    }


def report(path: str | Path, duration_seconds: float | None = None) -> str:
    data = analyze(path, duration_seconds)
    tempo = data["tempo"]
    lines = [
        "BEAT ANALYSIS",
        "File: %s" % Path(path).name,
        "Duration: %.2f s at %d Hz" % (data["duration_seconds"], data["sample_rate"]),
        "Tempo: %s" % ("%.1f BPM (%d%% confidence)" % (tempo["bpm"], round(tempo["confidence"] * 100))
                       if tempo.get("bpm") else "not detectable"),
        "Onsets: %d" % len(data["onsets"]),
        "Beat grid: %d beats" % data["beat_count"],
    ]
    return "\n".join(lines)
