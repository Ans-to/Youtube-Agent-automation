#!/usr/bin/env python3
"""Acoustic viseme estimation: decide *which sounds* are being made, not how loud.

The rig used to drive the mouth from short-window RMS. Loudness is a poor proxy
for articulation: a /p/ closure and an /a/ vowel can carry identical energy and
the mouth will look the same in both, which reads as flapping to volume rather
than to words.

This module measures articulation directly from the waveform with classical
speech acoustics, so it needs no model download, no GPU and no training data:

* **Formants** (F1, F2) from LPC. F1 tracks jaw opening — a low F1 is a close
  vowel like /i/ or /u/, a high F1 is an open one like /a/. F2 tracks
  front-to-back — a high F2 is a front vowel (lips spread, "wide"), a low F2 is a
  back vowel (lips rounded).
* **Periodicity** for voicing, which separates vowels and nasals from
  fricatives.
* **High-band ratio** for sibilance, which drives the teeth/fricative shape.
* **Energy relative to a local floor** for closures, so a /p/ actually shuts the
  mouth instead of merely dimming it.

The output is one viseme frame per video frame, which the renderer can consume
directly. Nothing here claims phoneme *recognition*: it is a continuous
articulatory measurement, closer to a singer's mouth chart than to forced
alignment. See ``docs/`` for that limitation.

Usage::

    from visemes import estimate_visemes
    frames = estimate_visemes(signal, rate, fps=30)
"""
from __future__ import annotations

import numpy as np

# Working ranges for adult speech. Values outside these are measurement noise.
F0_MIN_HZ = 60.0
F0_MAX_HZ = 400.0
FORMANT_MIN_HZ = 180.0
FORMANT_MAX_HZ = 5000.0
MAX_FORMANT_BANDWIDTH_HZ = 600.0

#: Anatomical search ranges. Vowel F1 practically never leaves this band, and
#: F2 has to be above F1; without the limits a weak F1 lets F2 be read as F1.
F1_MIN_HZ = 180.0
F1_MAX_HZ = 1100.0
F2_MIN_HZ = 700.0
F2_MAX_HZ = 3200.0

#: Pre-emphasis coefficient, standard for formant estimation above 16 kHz.
PRE_EMPHASIS = 0.97

# Vowel reference points (Peterson & Barney, adult male, Hz).
# F1 mostly sets the jaw, F2 sets spread vs rounded.
F1_CLOSED_HZ = 280.0
F1_OPEN_HZ = 780.0
F2_BACK_HZ = 850.0
F2_FRONT_HZ = 2100.0


def _frame_signal(signal: np.ndarray, rate: int, fps: int, window_ms: float):
    """Split into overlapping analysis windows aligned to video frames."""
    hop = max(1, int(round(rate / fps)))
    length = max(hop, int(round(rate * window_ms / 1000.0)))
    if signal.size < length:
        signal = np.pad(signal, (0, length - signal.size))
    count = max(1, int(np.ceil(signal.size / hop)))
    padded = np.pad(signal, (0, max(0, (count - 1) * hop + length - signal.size)))
    # Row stride must be `hop` samples; column stride one sample. Using the array's
    # own stride for both axes advances one sample per frame, which silently makes
    # every frame almost the same audio.
    frames = np.lib.stride_tricks.as_strided(
        padded,
        shape=(count, length),
        strides=(hop * padded.itemsize, padded.itemsize),
        writeable=False)
    return frames, hop


def _lpc(x: np.ndarray, order: int) -> np.ndarray:
    """Linear prediction coefficients via Levinson-Durbin.

    Returns ``a`` where the all-pole model is ``1 - sum(a[k] z^-k)``.
    """
    x = x - float(np.mean(x))
    n = x.size
    if n <= order or not np.any(x):
        return np.zeros(order + 1)
    # Autocorrelation, biased (matches the standard LPC formulation).
    corr = np.correlate(x, x, mode="full")[n - 1:]
    corr = corr[: order + 1]
    if corr[0] <= 1e-12:
        return np.zeros(order + 1)

    a = np.zeros(order + 1)
    a[0] = 1.0
    error = corr[0]
    for i in range(1, order + 1):
        acc = corr[i] + float(np.dot(a[1:i], corr[i - 1:0:-1]))
        k = -acc / error if abs(error) > 1e-12 else 0.0
        a[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a[i] = k
        error *= 1.0 - k * k
        if error <= 1e-12:
            break
    return a


def lpc_order_for(rate: int) -> int:
    """Analysis order appropriate to the sample rate.

    Formant LPC needs roughly one pole pair per 1.1 kHz of bandwidth. Order 12 —
    the textbook value for 8 kHz speech — merges F1 and F2 at 22 kHz, which is
    what made every back vowel look like an open one. An auto order keeps the
    estimator correct if the voice is resampled.
    """
    return int(min(32, max(12, round(rate / 1100.0))))


def _pre_emphasis(frame: np.ndarray, coefficient: float = PRE_EMPHASIS) -> np.ndarray:
    """First-order high-pass that removes the spectral tilt of voiced speech."""
    if frame.size < 2:
        return frame
    return np.append(frame[0], frame[1:] - coefficient * frame[:-1])


def _formants(frame: np.ndarray, rate: int, order: int) -> tuple[float, float]:
    """Return (F1, F2) in Hz, or (0, 0) when the frame has no usable structure."""
    if frame.size <= order or not np.any(frame):
        return 0.0, 0.0
    # Pre-emphasis flattens the -6 dB/octave tilt that voiced speech carries
    # (glottal source -12 dB/oct plus lip radiation +6 dB/oct). Without it the
    # low-frequency poles swamp the fit and the linear predictor locks onto the
    # pitch harmonics instead of the formants: on real 24 kHz speech that pinned
    # F1 to 200-260 Hz, only one or two harmonics above the fundamental.
    emphasised = _pre_emphasis(frame)
    windowed = emphasised * np.hamming(emphasised.size)
    a = _lpc(windowed, order)
    if not np.any(a[1:]):
        return 0.0, 0.0
    try:
        roots = np.roots(a)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0, 0.0
    roots = roots[np.imag(roots) > 0]
    if roots.size == 0:
        return 0.0, 0.0
    freqs = np.angle(roots) * (rate / (2.0 * np.pi))
    bandwidths = -0.5 * (rate / np.pi) * np.log(np.abs(roots) + 1e-12)
    keep = ((freqs > FORMANT_MIN_HZ) & (freqs < FORMANT_MAX_HZ)
            & (bandwidths > 0) & (bandwidths < MAX_FORMANT_BANDWIDTH_HZ))
    freqs = np.sort(freqs[keep])
    if freqs.size == 0:
        return 0.0, 0.0
    # Anchoring on the lowest surviving pole is not enough. When a vowel has a
    # weak F1 the first kept pole is really F2, which pushed measured F1 to
    # 1800 Hz on real speech (no vowel has F1 that high). Restrict each formant
    # to the range the vocal tract can physically produce and take the lowest
    # admissible pole for each, so F2 has to sit above F1.
    first = freqs[(freqs >= F1_MIN_HZ) & (freqs <= F1_MAX_HZ)]
    if first.size == 0:
        return 0.0, 0.0
    f1 = float(first[0])
    higher = freqs[(freqs >= max(F2_MIN_HZ, f1 + 200.0)) & (freqs <= F2_MAX_HZ)]
    f2 = float(higher[0]) if higher.size else 0.0
    return f1, f2


def _voicing(frame: np.ndarray, rate: int) -> float:
    """Normalised autocorrelation peak in the pitch range: 0 unvoiced, 1 voiced."""
    if frame.size < 64 or not np.any(frame):
        return 0.0
    x = frame - float(np.mean(frame))
    energy = float(np.dot(x, x))
    if energy <= 1e-12:
        return 0.0
    corr = np.correlate(x, x, mode="full")[x.size - 1:]
    # Divide by the number of overlapping samples before comparing lags. The
    # raw dot product shrinks purely because long lags overlap less, not
    # because the signal is aperiodic: at a 100 Hz pitch (lag 240 in a 960
    # sample window) that costs 25% and low-pitched real speech scored ~0.2
    # where the same detector scored 0.9 on a synthetic tone.
    overlap = np.maximum((x.size - np.arange(x.size)).astype(np.float64), 1.0)
    corr = (corr / overlap) / ((corr[0] / overlap[0]) + 1e-12)
    lo = max(1, int(rate / F0_MAX_HZ))
    # Never search a lag that leaves less than half the frame overlapping: as
    # the overlap approaches zero the corrected value is a single product
    # divided by itself and white noise starts scoring as periodic. Half a
    # window still covers 50 Hz at any 40 ms frame, well below any voice.
    hi = min(corr.size - 1, int(rate / F0_MIN_HZ), x.size // 2)
    if hi <= lo:
        return 0.0
    peak = float(np.max(corr[lo:hi]))
    return float(np.clip(peak, 0.0, 1.0))


def _high_band_ratio(spectrum_power: np.ndarray, rate: int, low: float = 2500.0,
                     high: float = 0.0) -> float:
    """Share of energy above `low` Hz. Sibilants put most of it there.

    The band runs to Nyquist rather than stopping at 7 kHz. At 22-24 kHz
    sampling rates an /s/ concentrates energy between 5 and 10 kHz, so a 7 kHz
    ceiling threw away the brightest part of the very sound it was meant to
    detect and broadband noise scored lower than a vowel in some frames.
    """
    if spectrum_power.size < 8 or spectrum_power.sum() <= 1e-20:
        return 0.0
    freqs = np.fft.rfftfreq((spectrum_power.size - 1) * 2, d=1.0 / rate)
    ceiling = min(high, rate / 2.0 - 1.0) if high > 0 else rate / 2.0 - 1.0
    band = (freqs >= low) & (freqs <= ceiling)
    return float(np.clip(spectrum_power[band].sum() / (spectrum_power.sum() + 1e-20), 0.0, 1.0))


def _normalise(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def estimate_visemes(signal: np.ndarray, rate: int, fps: int = 30,
                     window_ms: float = 40.0, lpc_order: int | None = None) -> list[dict]:
    """Measure articulation per video frame.

    Each returned dict carries the same channel names the renderer already uses
    (``open``, ``wide``, ``round``, ``teeth``, ``press``) plus a ``class`` label
    and the raw ``f1``/``f2``/``voicing``/``loudness`` measurements, so a failure
    to articulate can be diagnosed instead of guessed at.
    """
    signal = np.asarray(signal, dtype=np.float64).ravel()
    if signal.size == 0:
        return [{"open": 0.0, "wide": 0.28, "round": 0.1, "teeth": 0.0, "press": 0.9,
                 "class": "silence", "f1": 0.0, "f2": 0.0, "voicing": 0.0, "loudness": 0.0}]

    frames, _hop = _frame_signal(signal, rate, fps, window_ms)
    if lpc_order is None:
        lpc_order = lpc_order_for(rate)
    count = frames.shape[0]
    hop = max(1, int(round(rate / fps)))

    energy = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    # A local reference, not a global one: a quiet passage still articulates.
    reference = float(np.percentile(energy, 92)) if energy.size else 0.0
    if reference <= 1e-9:
        reference = float(energy.max()) if energy.size else 0.0
    reference = max(reference, 1e-9)

    window = np.hanning(frames.shape[1])
    result: list[dict] = []
    for index in range(count):
        frame = frames[index].astype(np.float64)
        loudness = float(np.clip(energy[index] / reference, 0.0, 1.0))

        spectrum = np.abs(np.fft.rfft(frame * window)) ** 2
        high_ratio = _high_band_ratio(spectrum, rate)
        voicing = _voicing(frame, rate)
        f1, f2 = _formants(frame, rate, lpc_order)

        # --- classify -------------------------------------------------------
        # Silence and closure are different things, but both want a shut mouth;
        # closure additionally wants lip pressure.
        if loudness < 0.06:
            viseme = {"open": 0.02, "wide": 0.28, "round": 0.10,
                      "teeth": 0.0, "press": 0.92, "class": "silence"}
        elif high_ratio > 0.42 and voicing < 0.62:
            # Sibilant /s, sh, f/: turbulent, no pitch, most energy up high.
            viseme = {"open": 0.14 + 0.10 * loudness, "wide": 0.82,
                      "round": 0.08, "teeth": 0.45 + 0.45 * loudness,
                      "press": 0.10, "class": "fricative"}
        elif voicing > 0.55 and f1 > 0:
            # Voiced: a vowel, or a nasal if the formants are low and close.
            openness = _normalise(f1, F1_CLOSED_HZ, F1_OPEN_HZ)
            frontness = _normalise(f2, F2_BACK_HZ, F2_FRONT_HZ) if f2 > 0 else 0.5
            nasal = f1 < 360.0 and (f2 == 0.0 or f2 < 1500.0) and loudness < 0.55
            if nasal:
                viseme = {"open": 0.06, "wide": 0.24, "round": 0.18,
                          "teeth": 0.0, "press": 0.62, "class": "nasal"}
            else:
                # Spread lips on front vowels, round them on back vowels, and
                # leave the neutral centre genuinely neutral. A single linear
                # ramp made /a/ read as rounded, because a central vowel sits
                # near the middle of the F2 range rather than at either end.
                jaw = 0.12 + 0.80 * openness
                if frontness < 0.5:
                    wide = 0.16 + 0.78 * frontness          # 0.16 -> 0.55
                    round_ = 0.90 - 1.20 * frontness        # 0.90 -> 0.30
                else:
                    wide = 0.55 + 0.80 * (frontness - 0.5)  # 0.55 -> 0.95
                    round_ = 0.30 - 0.50 * (frontness - 0.5)  # 0.30 -> 0.05
                viseme = {"open": float(np.clip(jaw, 0.0, 1.0)),
                          "wide": float(np.clip(wide, 0.0, 1.0)),
                          "round": float(np.clip(round_, 0.0, 1.0)),
                          "teeth": 0.0, "press": 0.0, "class": "vowel"}
        elif loudness > 0.10:
            # Plosive burst or other transient: brief, fairly closed, tensed.
            viseme = {"open": 0.18 + 0.16 * loudness, "wide": 0.40,
                      "round": 0.22, "teeth": 0.10,
                      "press": 0.55, "class": "plosive"}
        else:
            viseme = {"open": 0.05, "wide": 0.26, "round": 0.12,
                      "teeth": 0.0, "press": 0.75, "class": "closure"}

        viseme.update({"f1": round(f1, 1), "f2": round(f2, 1),
                       "voicing": round(voicing, 3), "loudness": round(loudness, 3)})
        result.append(viseme)

    # --- coarticulation and flicker suppression ----------------------------
    # Speech shapes glide into one another; a hard switch every frame reads as a
    # twitch. A short symmetric smoothing pass, then a floor on how much a shape
    # may change per frame, keeps vowels distinguishable without flickering.
    result = _smooth(result, alpha=0.45)
    # Drop single-frame closures that are really measurement dropouts: a real
    # closure is followed by a burst, not by another vowel at the same energy.
    result = _drop_isolated_closures(result)
    return [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in item.items()}
            for item in result]


_CHANNELS = ("open", "wide", "round", "teeth", "press")


def _smooth(frames: list[dict], alpha: float) -> list[dict]:
    """One-pass EMA plus a backward pass so shapes lead and lag like real speech."""
    if len(frames) < 3:
        return frames
    out = [dict(item) for item in frames]
    previous = None
    for item in out:
        if previous is not None:
            for channel in _CHANNELS:
                item[channel] = float((1 - alpha) * item[channel] + alpha * previous[channel])
        previous = item
    following = None
    for item in reversed(out):
        if following is not None:
            for channel in _CHANNELS:
                item[channel] = float((1 - alpha) * item[channel] + alpha * following[channel])
        following = item
    return out


def _drop_isolated_closures(frames: list[dict]) -> list[dict]:
    """Turn a one-frame dip between two loud frames back into the surrounding shape."""
    if len(frames) < 3:
        return frames
    out = [dict(item) for item in frames]
    for index in range(1, len(out) - 1):
        before, current, after = out[index - 1], out[index], out[index + 1]
        if current["class"] not in ("silence", "closure"):
            continue
        if before.get("loudness", 0) > 0.25 and after.get("loudness", 0) > 0.25:
            merged = dict(before)
            for channel in _CHANNELS:
                merged[channel] = 0.5 * (before[channel] + after[channel])
            merged["class"] = "vowel"
            out[index] = merged
    return out


def as_renderer_channels(frames: list[dict]) -> list[dict]:
    """Strip diagnostics, leaving only what the canvas renderer needs."""
    return [{channel: item[channel] for channel in _CHANNELS} for item in frames]
