"""Local audio analysis: speech/music separation, clipping, and loudness.

Pure Python on purpose. Everything here is deterministic DSP over PCM samples,
so it runs with no NumPy, no model download, and no network — and every threshold
can be unit-tested with synthetic tones.

What this can establish:

* how loud the program is, and whether it is quiet or hot enough to be a problem;
* whether the signal is clipping (a distorted, unsalvageable master);
* whether a segment behaves more like music than speech, from continuity,
  spectral stability, and rhythmic flux (a heuristic, labelled as one).

What it cannot establish: whether that music is licensed. That stays a manual
check in the auditor.
"""
from __future__ import annotations

import cmath
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_RATE = 16_000
WINDOW = 1_024
HOP = 1_600  # 0.1 s at 16 kHz
SILENCE_DBFS = -45.0
HOT_DBFS = -3.0
CLIP_THRESHOLD = 0.995
MAX_FRAMES = 200_000


@dataclass(frozen=True)
class FrameFeatures:
    """Per-window spectral and level features."""

    time: float
    rms_db: float
    zcr: float
    centroid_hz: float
    flatness: float
    flux: float
    low_ratio: float
    mid_ratio: float
    high_ratio: float
    clipped_ratio: float


@dataclass
class MusicEstimate:
    """A heuristic judgement about whether music is present, with its reasoning."""

    present: bool = False
    confidence: float = 0.0
    continuity: float = 0.0
    stability: float = 0.0
    periodicity: float = 0.0
    tonal: float = 0.0
    segments: list[tuple[float, float]] = field(default_factory=list)
    reason: str = ""


@dataclass
class AudioProfile:
    """Everything the audio detectors need."""

    duration: float = 0.0
    sample_rate: int = SAMPLE_RATE
    frames: list[FrameFeatures] = field(default_factory=list)
    integrated_db: float = -96.0
    peak_db: float = -96.0
    music: MusicEstimate = field(default_factory=MusicEstimate)
    speech_like_ratio: float = 0.0

    @property
    def clipped_frames(self) -> list[FrameFeatures]:
        return [frame for frame in self.frames if frame.clipped_ratio > 0.001]

    def spans(self, predicate, gap: float = 0.15) -> list[tuple[float, float]]:
        """Group frames matching ``predicate`` into merged time spans."""
        spans: list[list[float]] = []
        for frame in self.frames:
            if not predicate(frame):
                continue
            if spans and frame.time <= spans[-1][1] + gap + HOP / SAMPLE_RATE:
                spans[-1][1] = frame.time + HOP / SAMPLE_RATE
            else:
                spans.append([frame.time, frame.time + HOP / SAMPLE_RATE])
        return [(start, end) for start, end in spans]


def dbfs(value: float) -> float:
    """Convert a 0..1 amplitude to dBFS, flooring at -96 dB."""
    if value <= 1e-9:
        return -96.0
    return max(-96.0, 20.0 * math.log10(min(1.0, value)))


def _fft(real: list[float], imag: list[float]) -> None:
    """In-place iterative radix-2 FFT. Length must be a power of two."""
    size = len(real)
    if size & (size - 1):
        raise ValueError("FFT length must be a power of two")
    index = 0
    for position in range(1, size):
        bit = size >> 1
        while index & bit:
            index ^= bit
            bit >>= 1
        index ^= bit
        if position < index:
            real[position], real[index] = real[index], real[position]
            imag[position], imag[index] = imag[index], imag[position]
    length = 2
    while length <= size:
        angle = -2 * math.pi / length
        step = cmath.exp(complex(0, angle))
        for start in range(0, size, length):
            rotation = complex(1, 0)
            half = length // 2
            for offset in range(half):
                even = complex(real[start + offset], imag[start + offset])
                odd = complex(real[start + offset + half], imag[start + offset + half]) * rotation
                real[start + offset] = even.real + odd.real
                imag[start + offset] = even.imag + odd.imag
                real[start + offset + half] = even.real - odd.real
                imag[start + offset + half] = even.imag - odd.imag
                rotation *= step
        length <<= 1


def _band(index: int, bins: int) -> str:
    hertz = index * SAMPLE_RATE / (2 * bins)
    if hertz < 250:
        return "low"
    if hertz < 2_000:
        return "mid"
    return "high"


def frame_features(samples: list[float], start_time: float,
                   previous_magnitudes: list[float] | None = None) -> tuple[FrameFeatures, list[float]]:
    """Compute features for one window, returning them with the magnitude spectrum.

    The spectrum is returned so the caller can compute spectral flux against the
    previous frame without a second FFT.
    """
    size = len(samples)
    if size == 0:
        empty = [0.0] * (WINDOW // 2)
        return FrameFeatures(start_time, -96.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), empty
    total = 0.0
    clipped = 0
    crossings = 0
    previous = samples[0]
    for sample in samples:
        total += sample * sample
        if abs(sample) >= CLIP_THRESHOLD:
            clipped += 1
        if (sample >= 0) != (previous >= 0):
            crossings += 1
        previous = sample
    rms = math.sqrt(total / size)

    padded = list(samples) + [0.0] * (WINDOW - size) if size < WINDOW else list(samples[:WINDOW])
    real = padded[:WINDOW]
    imag = [0.0] * WINDOW
    # Hann window reduces spectral leakage so band ratios are meaningful.
    for index in range(WINDOW):
        real[index] *= 0.5 - 0.5 * math.cos(2 * math.pi * index / (WINDOW - 1))
    _fft(real, imag)

    magnitudes = [math.hypot(real[index], imag[index]) for index in range(WINDOW // 2)]
    nyquist_energy = sum(magnitudes) or 1e-9
    centroid = sum(index * magnitude for index, magnitude in enumerate(magnitudes)) / nyquist_energy
    centroid_hz = centroid * SAMPLE_RATE / WINDOW
    geometric = math.exp(sum(math.log(max(value, 1e-12)) for value in magnitudes) / len(magnitudes))
    arithmetic = nyquist_energy / len(magnitudes)
    flatness = min(1.0, geometric / arithmetic) if arithmetic else 0.0

    low = sum(magnitude for index, magnitude in enumerate(magnitudes) if _band(index, WINDOW) == "low")
    mid = sum(magnitude for index, magnitude in enumerate(magnitudes) if _band(index, WINDOW) == "mid")
    high = sum(magnitude for index, magnitude in enumerate(magnitudes) if _band(index, WINDOW) == "high")
    normalized = [magnitude / nyquist_energy for magnitude in magnitudes]
    flux = 0.0
    if previous_magnitudes is not None:
        flux = sum(
            max(0.0, current - prior)
            for current, prior in zip(normalized, previous_magnitudes, strict=False)
        ) / len(normalized)
    return FrameFeatures(
        time=round(start_time, 4),
        rms_db=dbfs(rms),
        zcr=crossings / size,
        centroid_hz=round(centroid_hz, 1),
        flatness=round(flatness, 5),
        flux=round(flux, 6),
        low_ratio=round(low / nyquist_energy, 4),
        mid_ratio=round(mid / nyquist_energy, 4),
        high_ratio=round(high / nyquist_energy, 4),
        clipped_ratio=clipped / size,
    ), normalized


def _autocorrelation_peak(values: list[float], min_lag: int, max_lag: int) -> float:
    """Best normalized autocorrelation of a series within a lag range."""
    if len(values) <= max_lag or max_lag <= min_lag:
        return 0.0
    mean_value = sum(values) / len(values)
    centered = [value - mean_value for value in values]
    denominator = sum(value * value for value in centered)
    if denominator < 1e-9:
        return 0.0
    best = 0.0
    for lag in range(min_lag, max_lag):
        numerator = sum(centered[index] * centered[index + lag] for index in range(len(centered) - lag))
        best = max(best, numerator / denominator)
    return max(0.0, best)


def estimate_music(frames: list[FrameFeatures]) -> MusicEstimate:
    """Estimate whether music is present, from continuity, stability and rhythm.

    This is a heuristic and the auditor labels it as one. It answers "does this
    behave like a music bed", not "is this a licensed recording".
    """
    audible = [frame for frame in frames if frame.rms_db > SILENCE_DBFS]
    if len(audible) < 20:
        return MusicEstimate(reason="Too little audible audio to judge.")

    continuity = len(audible) / len(frames)
    centroids = [frame.centroid_hz for frame in audible]
    mean_centroid = sum(centroids) / len(centroids)
    if mean_centroid <= 1.0:
        return MusicEstimate(reason="Degenerate spectrum; cannot judge.")
    variance = sum((value - mean_centroid) ** 2 for value in centroids) / len(centroids)
    coefficient = math.sqrt(variance) / mean_centroid
    stability = max(0.0, min(1.0, 1.0 - coefficient / 0.6))

    flux = [frame.flux for frame in frames]
    periodicity = _autocorrelation_peak(flux, min_lag=3, max_lag=20)

    # Broadband noise is spectrally flat; tonal music is not. Without this the
    # heuristic mistakes hiss and wind for a music bed.
    mean_flatness = sum(frame.flatness for frame in audible) / len(audible)
    tonal = max(0.0, min(1.0, 1.0 - (mean_flatness - 0.05) / 0.45))

    score = 0.30 * continuity + 0.25 * stability + 0.25 * periodicity + 0.20 * tonal
    present = score >= 0.60 and continuity >= 0.55 and tonal >= 0.40
    segments = [
        (start, end) for start, end in _merge(
            [(frame.time, frame.time + HOP / SAMPLE_RATE) for frame in audible]
        )
        if end - start >= 3.0
    ]
    return MusicEstimate(
        present=present,
        confidence=round(min(95.0, 35.0 + 60.0 * score), 1),
        continuity=round(continuity, 3),
        stability=round(stability, 3),
        periodicity=round(periodicity, 3),
        tonal=round(tonal, 3),
        segments=segments[:20],
        reason=(
            "Sustained, spectrally stable audio with rhythmic flux, which behaves like a music bed."
            if present else
            "Audio does not show the continuity, spectral stability, tonality and rhythmic flux of a music bed."
        ),
    )


def _merge(spans: list[tuple[float, float]], gap: float = 0.35) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def analyze_samples(samples: list[float], sample_rate: int = SAMPLE_RATE) -> AudioProfile:
    """Analyze normalized samples. The entry point used by tests."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    profile = AudioProfile(duration=len(samples) / sample_rate, sample_rate=sample_rate)
    hop = int(sample_rate * HOP / SAMPLE_RATE) or 1
    window = int(sample_rate * WINDOW / SAMPLE_RATE) or 1
    previous_magnitudes: list[float] | None = None
    peak = 0.0
    total_energy = 0.0
    for index, start in enumerate(range(0, max(0, len(samples) - window + 1), hop)):
        if index >= MAX_FRAMES:
            break
        chunk = samples[start:start + window]
        features, previous_magnitudes = frame_features(chunk, start / sample_rate, previous_magnitudes)
        profile.frames.append(features)
        peak = max(peak, max(abs(value) for value in chunk))
        total_energy += sum(value * value for value in chunk)

    if samples:
        profile.peak_db = dbfs(peak)
        profile.integrated_db = dbfs(math.sqrt(total_energy / len(samples)))
    profile.music = estimate_music(profile.frames)
    speech_frames = [
        frame for frame in profile.frames
        if frame.rms_db > SILENCE_DBFS and frame.zcr > 0.02 and frame.flatness < 0.35
    ]
    profile.speech_like_ratio = round(len(speech_frames) / len(profile.frames), 3) if profile.frames else 0.0
    return profile


def analyze_file(path: str | Path, ffmpeg: str | None = None) -> AudioProfile | None:
    """Decode a file to mono PCM and analyze it. Returns None when FFmpeg is absent."""
    import array

    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    command = [
        ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-",
    ]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, resolved binary, no shell
            command, capture_output=True, timeout=1_800, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    raw = array.array("h")
    raw.frombytes(result.stdout[: len(result.stdout) - (len(result.stdout) % 2)])
    samples = [value / 32768.0 for value in raw]
    return analyze_samples(samples, SAMPLE_RATE)
