#!/usr/bin/env python3
"""Narrate a script with a local neural voice, then make it sound like a voice.

Backends, in order of quality, all free and offline after first use:

1. **Piper** (``piper-tts``) — a neural VITS voice on CPU. Weights are a public
   download from Hugging Face; no account, no key, no per-character billing.
   This is the backend that produces a natural read.
2. **espeak-ng** — a formant synthesizer. Intelligible, obviously synthetic. Used
   only as a fallback so the pipeline still runs on a machine without weights.

The backend is chosen by what is actually installed. It never silently pretends:
if neither is available the command exits non-zero and says what is missing.

What "more natural" means here, concretely:

* **Prosody per line** — questions rise, statements fall, the last clause slows
  down, and a comma gets a shorter pause than a full stop.
* **Emphasis** — capitalised or ``*starred*`` words are spoken slightly slower and
  louder, which Piper renders as a real accent rather than a flat read.
* **Breath and seam handling** — a short lead-in and tail on every line so
  concatenation does not click.
* **A voice chain** — high-pass, de-ess, presence lift, gentle compression, and
  loudness normalisation, so the result sits under music like a mixed voice
  instead of a raw TTS dump.

Usage::

    python video_studio/voiceover.py --script script.json --out build/voice
    python video_studio/voiceover.py --script script.json --out build/voice --allow-download
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

try:  # numpy makes the DSP honest rather than approximate
    import numpy as np
except ImportError:  # pragma: no cover - the fallback is slow but correct
    np = None

# Articulation analysis needs numpy. The loudness fallback below does not, so a
# missing numpy must not turn into an import error for the whole module.
try:
    from .visemes import estimate_visemes, as_renderer_channels
except ImportError:  # running as a script rather than a package, or no numpy
    try:
        from visemes import estimate_visemes, as_renderer_channels
    except ImportError:  # pragma: no cover - exercised on numpy-less installs
        estimate_visemes = None
        as_renderer_channels = None

ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT / "video_studio" / "voices"
DEFAULT_VOICE = "en_US-lessac-medium"
SAMPLE_RATE = 24000

# piper's own knobs, tuned for a narrated read rather than the default
LENGTH_SCALE = 1.06          # slightly slower than default: clearer, calmer
NOISE_SCALE = 0.60           # 0.667 is piper's default; a touch less wobble
NOISE_W_SCALE = 0.75         # less phoneme-length jitter: steadier, less "TTS"


# A voice is 63 MB, so it is fetched at build time rather than committed. The
# official host is reachable from most networks but not all, so each voice also
# names a git mirror that carries the identical bytes. Both routes are checked
# against a pinned size and md5 before the file is used: a voice that does not
# match is a different voice, and the film's lip-sync would be built on sand.
VOICE_SOURCES = {
    "en_US-amy-medium": {
        "bytes": 63_201_294,
        "md5": "778d28aeb95fcdf8a882344d9df142fc",
        "repo": "https://github.com/zeetwii/aiPlaysPokemon",
        "model": "avatar/tts/en_US-amy-medium.onnx",
        "config": "avatar/tts/en_US-amy-medium.onnx.json",
        "note": "public Piper VITS voice, 22.05 kHz, US English",
    },
}


class VoiceBackendMissing(RuntimeError):
    """No usable local speech backend could be found."""


@dataclass
class Line:
    text: str
    pause_after: float = 0.32
    rate: float = 1.0
    gap_before: float = 0.0
    id: str = ""
    start: float = 0.0
    end: float = 0.0
    emphasis: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- script
def load_script(path: Path) -> list[Line]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        raise ValueError("the voice script needs a non-empty 'lines' array")
    lines = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            lines.append(Line(text=item, id=f"L{index + 1}"))
            continue
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            raise ValueError(f"line {index} has no text")
        lines.append(Line(
            text=str(item["text"]).strip(),
            pause_after=float(item.get("pause_after", 0.32)),
            gap_before=float(item.get("gap_before", 0.0)),
            rate=float(item.get("rate", 1.0)),
            id=str(item.get("id") or f"L{index + 1}"),
        ))
    return lines


def spoken_text(text: str) -> str:
    """Strip markup that only exists for the writer, keep everything speakable."""
    value = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)
    return value.strip()


def emphasis_words(text: str) -> list[str]:
    """Words the writer marked for stress, by caps or *stars*."""
    starred = re.findall(r"[*_]{1,2}([^*_]+)[*_]{1,2}", text)
    shouted = re.findall(r"\b[A-Z][A-Z'\-]{2,}\b", text)
    out = []
    for item in starred:
        out.extend(word.lower() for word in item.split())
    for item in shouted:
        if item.lower() not in out:
            out.append(item.lower())
    return out


def prosody_note(line: Line) -> str:
    """A trailing instruction the backend can act on. Piper has no SSML, so we
    adjust the knobs that do exist and let the punctuation carry the rest."""
    text = spoken_text(line.text)
    if text.endswith("?"):
        return "rising"
    if text.endswith("!"):
        return "urgent"
    if text.endswith(","):
        return "continuing"
    return "settling"


# -------------------------------------------------------------------- backends
def piper_model_path(explicit: str | None = None, voice: str = DEFAULT_VOICE) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get("AGENTHQ_VOICE_MODEL", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(VOICE_DIR / f"{voice}.onnx")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def voice_is_pinned(voice: str) -> bool:
    """True when the file on disk is exactly the voice this project pinned."""
    spec = VOICE_SOURCES.get(voice)
    model = VOICE_DIR / f"{voice}.onnx"
    if spec is None or not model.is_file():
        return False
    if model.stat().st_size != spec["bytes"]:
        return False
    return md5_file(model) == spec["md5"]


def _fetch_voice_from_git(voice: str, destination: Path) -> None:
    """Mirror route: a sparse, blob-filtered clone of a repo that carries the file.

    Release downloads and the model hub are not reachable on every network, but
    ordinary git over HTTPS usually is. Only the two files we need are checked
    out; the clone is discarded afterwards.
    """
    spec = VOICE_SOURCES[voice]
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        commands = [
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
             spec["repo"], str(repo)],
            ["git", "-C", str(repo), "sparse-checkout", "set", "--no-cone",
             "/" + spec["model"], "/" + spec["config"]],
            ["git", "-C", str(repo), "checkout"],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True,
                                    check=False, timeout=900)  # noqa: S603
            if result.returncode != 0:
                raise VoiceBackendMissing(
                    "could not fetch the voice from git: "
                    + (result.stderr or result.stdout)[-300:].strip())
        source = repo / spec["model"]
        config = repo / spec["config"]
        size = source.stat().st_size if source.is_file() else 0
        if size != spec["bytes"]:
            raise VoiceBackendMissing(
                f"the mirror returned {size} bytes instead of {spec['bytes']} "
                "(it may store the model through Git LFS)")
        if md5_file(source) != spec["md5"]:
            raise VoiceBackendMissing("the mirror's voice does not match the pinned checksum")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if config.is_file():
            shutil.copy2(config, destination.with_suffix(".onnx.json"))


def ensure_piper_voices(voice: str, allow_download: bool) -> Path:
    """Return a model path, fetching the public weights once if permitted."""
    model = VOICE_DIR / f"{voice}.onnx"
    spec = VOICE_SOURCES.get(voice)
    if model.is_file() and (spec is None or voice_is_pinned(voice)):
        return model
    if not allow_download:
        raise VoiceBackendMissing(
            f"the Piper voice {voice!r} is not in {VOICE_DIR}. Run again with "
            "--allow-download (public weights, no account) or set AGENTHQ_VOICE_MODEL."
        )
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "piper.download_voices", voice, "--download-dir", str(VOICE_DIR)],
        capture_output=True, text=True, check=False, timeout=900,
    )
    if model.is_file() and (spec is None or voice_is_pinned(voice)):
        return model
    if spec is not None:
        _fetch_voice_from_git(voice, model)
        return model
    raise VoiceBackendMissing(
        "could not download the Piper voice: "
        + (result.stderr or result.stdout)[-400:].strip()
    )


def piper_available() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


def espeak_available() -> bool:
    return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None


def synth_piper_line(line: Line, model: Path, out_path: Path) -> None:
    """Render one line with Piper and write it as 16-bit PCM."""
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    voice = PiperVoice.load(str(model))
    text = spoken_text(line.text)
    rate = max(0.75, min(1.35, line.rate))
    # punctuation shapes the melody; length_scale only nudges pace
    config = SynthesisConfig(
        length_scale=LENGTH_SCALE / rate,
        noise_scale=NOISE_SCALE,
        noise_w_scale=NOISE_W_SCALE,
        normalize_audio=True,
    )
    chunks = [np.asarray(chunk.audio_float_array, dtype=np.float32)
              for chunk in voice.synthesize(text, syn_config=config)]
    if not chunks:
        raise VoiceBackendMissing(f"piper produced no audio for {text!r}")
    audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    write_wav(out_path, audio, voice.config.sample_rate)


def synth_espeak_line(line: Line, out_path: Path) -> None:
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        raise VoiceBackendMissing("espeak-ng is not installed")
    words_per_minute = int(150 * max(0.7, min(1.4, line.rate)))
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [binary, "-v", "en-us", "-s", str(words_per_minute), "-p", "42", "-a", "160",
         "-w", str(out_path), spoken_text(line.text)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise VoiceBackendMissing("espeak-ng failed: " + (result.stderr or "")[-300:])


# ------------------------------------------------------------------------ DSP
def write_wav(path: Path, signal: np.ndarray, rate: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(signal, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"{path} is not 16-bit PCM")
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def resample(signal: np.ndarray, source: int, target: int) -> np.ndarray:
    if source == target or signal.size == 0:
        return signal
    duration = signal.size / source
    target_n = int(round(duration * target))
    source_x = np.linspace(0.0, duration, signal.size, endpoint=False)
    target_x = np.linspace(0.0, duration, target_n, endpoint=False)
    return np.interp(target_x, source_x, signal).astype(np.float32)


def _biquad(signal: np.ndarray, rate: int, kind: str, freq: float, q: float, gain_db: float = 0.0):
    """Direct-form biquad. Used for the high-pass and the presence lift."""
    w0 = 2 * math.pi * freq / rate
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / (2 * q)
    if kind == "highpass":
        b0 = (1 + cos_w0) / 2
        b1 = -(1 + cos_w0)
        b2 = (1 + cos_w0) / 2
        a0, a1, a2 = 1 + alpha, -2 * cos_w0, 1 - alpha
    elif kind == "peak":
        a = 10 ** (gain_db / 40)
        b0, b1, b2 = 1 + alpha * a, -2 * cos_w0, 1 - alpha * a
        a0, a1, a2 = 1 + alpha / a, -2 * cos_w0, 1 - alpha / a
    else:
        raise ValueError(kind)
    b = np.array([b0, b1, b2], dtype=np.float64) / a0
    a = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)
    out = np.zeros_like(signal, dtype=np.float64)
    x1 = x2 = y1 = y2 = 0.0
    for i, x in enumerate(signal):
        y = b[0] * x + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        out[i] = y
    return out.astype(np.float32)


def de_ess(signal: np.ndarray, rate: int) -> np.ndarray:
    """Pull down the harshest part of the sibilance band on peaks only."""
    high = _biquad(signal, rate, "highpass", 5200, 0.7)
    low = signal - high
    window = max(1, int(rate * 0.01))
    envelope = np.convolve(np.abs(high), np.ones(window) / window, mode="same")
    threshold = max(1e-4, float(np.percentile(envelope, 92)) * 1.4)
    reduction = np.clip(threshold / np.maximum(envelope, 1e-6), 0.0, 1.0)
    reduction = 1.0 - 0.45 * (1.0 - reduction)   # up to -5 dB on the loudest sibilance
    return (low + high * reduction).astype(np.float32)


def compress(signal: np.ndarray, rate: int, threshold_db: float = -18.0, ratio: float = 3.0) -> np.ndarray:
    """Gentle downward compression: narrows the distance between loud and quiet."""
    window = max(1, int(rate * 0.012))
    envelope = np.convolve(np.abs(signal), np.ones(window) / window, mode="same")
    level_db = 20 * np.log10(np.maximum(envelope, 1e-6))
    over = np.maximum(0.0, level_db - threshold_db)
    gain_db = -over * (1.0 - 1.0 / ratio)
    return (signal * (10 ** (gain_db / 20))).astype(np.float32)


def normalise(signal: np.ndarray, peak_db: float = -1.5, rms_db: float = -19.0) -> np.ndarray:
    if signal.size == 0:
        return signal
    rms = float(np.sqrt(np.mean(signal ** 2)))
    if rms > 1e-6:
        signal = signal * (10 ** (rms_db / 20) / rms)
    peak = float(np.max(np.abs(signal)))
    ceiling = 10 ** (peak_db / 20)
    if peak > ceiling:
        signal = signal * (ceiling / peak)
    return signal.astype(np.float32)


def polish(signal: np.ndarray, rate: int) -> np.ndarray:
    """The voice chain, in the order a mixer would apply it."""
    processed = _biquad(signal, rate, "highpass", 78, 0.7)
    processed = de_ess(processed, rate)
    processed = _biquad(processed, rate, "peak", 2900, 1.0, gain_db=2.0)
    processed = compress(processed, rate)
    return normalise(processed)


def fade_edges(signal: np.ndarray, rate: int, ms: float = 8.0) -> np.ndarray:
    n = min(int(rate * ms / 1000), signal.size // 2)
    if n <= 0:
        return signal
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    signal = signal.copy()
    signal[:n] *= ramp
    signal[-n:] *= ramp[::-1]
    return signal


# ----------------------------------------------------------------------- main
def spectral_brightness(signal: np.ndarray, rate: int, fps: int = 30) -> list[float]:
    """Per-video-frame spectral centroid, normalised to 0..1.

    Loudness alone cannot say *which* mouth shape a frame needs: "oo" and "ee"
    can carry the same energy. The centroid separates them — a bright frame is a
    spread vowel, a dark one is round — so the rig gets a second real measurement
    from the audio instead of guessing shapes from the caption text.
    """
    hop = max(1, int(round(rate / fps)))
    if signal.size < hop * 2:
        return [0.5]
    frames = signal.size // hop
    frames = min(frames, 4096)  # a bounded window keeps this linear
    window = np.hanning(hop)
    freqs = np.fft.rfftfreq(hop, 1.0 / rate)
    lo, hi = 120.0, 3400.0                      # the band that carries vowel colour
    band = (freqs >= lo) & (freqs <= hi)
    if not band.any():
        return [0.5] * frames
    out = []
    for index in range(frames):
        chunk = signal[index * hop:(index + 1) * hop]
        if chunk.size < hop:
            break
        magnitude = np.abs(np.fft.rfft(chunk * window))[band]
        energy = float(magnitude.sum())
        if energy <= 1e-6:
            out.append(0.0)
            continue
        centroid = float((magnitude * freqs[band]).sum() / energy)
        out.append(round(float(np.clip((centroid - lo) / (hi - lo), 0.0, 1.0)), 3))
    return out or [0.5]


def normalise_brightness(values: list[float]) -> list[float]:
    """Rescale a line's centroids to its own 10th-90th percentile.

    A speaker's band sits inside a slice of 120-3400 Hz, so the raw centroid only
    ever spans part of 0..1. Fitting each line to its own range keeps the colour
    contrast between a bright and a dark vowel visible on a face that is a few
    hundred pixels wide.
    """
    if not values:
        return []
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    low, high = float(np.percentile(array, 10)), float(np.percentile(array, 90))
    if high - low < 1e-6:
        return [round(float(np.clip(v, 0.0, 1.0)), 3) for v in values]
    return [round(float(np.clip((v - low) / (high - low), 0.0, 1.0)), 3) for v in values]


def openness_envelope(signal: np.ndarray, rate: int, fps: int = 30) -> list[float]:
    """Per-video-frame mouth openness, measured from the audio itself.

    The rig used to guess viseme amplitude from a word timeline. This measures
    it: short-window energy of the rendered voice, normalised against the loudest
    syllable, so the mouth closes in every pause and opens on the beat.
    """
    hop = max(1, int(round(rate / fps)))
    if signal.size < hop:
        return [0.0]
    frames = signal.size // hop
    trimmed = signal[: frames * hop].reshape(frames, hop)
    rms = np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1))
    reference = float(np.percentile(rms, 95)) if rms.size else 0.0
    if reference <= 1e-6:
        return [0.0] * frames
    values = np.clip(rms / reference, 0.0, 1.0) ** 0.62
    return [round(float(value), 3) for value in values]


def build(script: Path, out_dir: Path, *, voice: str = DEFAULT_VOICE,
          allow_download: bool = False, backend: str = "auto", fps: int = 30) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = load_script(script)

    chosen = backend
    model = None
    if chosen in ("auto", "piper"):
        if piper_available():
            model = piper_model_path(voice=voice)
            if model is None and allow_download:
                model = ensure_piper_voices(voice, allow_download=True)
            if model is not None:
                chosen = "piper"
            elif backend == "piper":
                raise VoiceBackendMissing("piper is installed but no voice model was found")
        elif backend == "piper":
            raise VoiceBackendMissing("piper is not installed (pip install piper-tts)")
    if chosen == "auto":
        chosen = "espeak" if espeak_available() else "none"
    if chosen in ("none", "auto"):
        raise VoiceBackendMissing(
            "no local speech backend. Install one free option and rerun:\n"
            "  pip install piper-tts && python -m piper.download_voices en_US-lessac-medium\n"
            "  or install espeak-ng for the fallback voice."
        )

    rendered: list[tuple[Line, np.ndarray]] = []
    for line in lines:
        clip_path = out_dir / f"{line.id}.wav"
        if model is not None:
            synth_piper_line(line, model, clip_path)
        else:
            synth_espeak_line(line, clip_path)
        audio, rate = read_wav(clip_path)
        audio = resample(audio, rate, SAMPLE_RATE)
        rendered.append((line, audio))

    # assemble, keeping the timeline the captions and the film will use
    cursor = 0.0
    pieces: list[np.ndarray] = []
    timeline = []
    for index, (line, audio) in enumerate(rendered):
        gap_before = max(0.0, line.gap_before)
        lead = np.zeros(int(SAMPLE_RATE * gap_before), dtype=np.float32)
        text_for_silence = fade_edges(audio, SAMPLE_RATE)
        start = cursor + gap_before
        end = start + text_for_silence.size / SAMPLE_RATE
        pieces.extend([lead, text_for_silence])
        timeline.append({
            "id": line.id,
            "text": line.text,
            "spoken": spoken_text(line.text),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "prosody": prosody_note(line),
            "emphasis": emphasis_words(line.text),
        })
        cursor = end
        tail = np.zeros(int(SAMPLE_RATE * line.pause_after), dtype=np.float32)
        pieces.append(tail)
        cursor += line.pause_after

    full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    full = polish(full, SAMPLE_RATE)

    voice_path = out_dir / "voiceover.wav"
    write_wav(voice_path, full, SAMPLE_RATE)

    # hand the picture an envelope it can trust, in the film's own frame units
    envelope = []
    for item in timeline:
        first = int(round(item["start"] * SAMPLE_RATE))
        last = int(round(item["end"] * SAMPLE_RATE))
        window = full[first:max(first + 1, last)]
        values = openness_envelope(window, SAMPLE_RATE, fps=fps)
        bright = spectral_brightness(window, SAMPLE_RATE, fps=fps)
        expected = max(1, int(round((item["end"] - item["start"]) * fps)))
        if len(values) < expected:
            values = values + [0.0] * (expected - len(values))
        bright = normalise_brightness(bright)
        if len(bright) < expected:
            bright = bright + [bright[-1] if bright else 0.5] * (expected - len(bright))
        # Articulation, measured from the spectrum rather than the loudness:
        # this is what separates a /p/ from an /a/ at the same volume.
        visemes = (as_renderer_channels(estimate_visemes(window, SAMPLE_RATE, fps=fps))
                   if estimate_visemes and as_renderer_channels else [])
        if len(visemes) < expected:
            filler = visemes[-1] if visemes else {"open": 0.02, "wide": 0.28,
                                                  "round": 0.1, "teeth": 0.0, "press": 0.9}
            visemes = visemes + [dict(filler)] * (expected - len(visemes))
        envelope.append({"id": item["id"], "start": item["start"], "end": item["end"],
                         "fps": fps, "openness": values[:expected],
                         "brightness": bright[:expected],
                         "visemes": visemes[:expected]})
    (out_dir / "envelope.json").write_text(
        json.dumps({"fps": fps, "lines": envelope}, indent=2) + "\n", encoding="utf-8")

    report = {
        "backend": chosen,
        "fps": fps,
        "voice": voice if chosen == "piper" else "espeak-ng formant",
        "model": str(model) if model else None,
        "sample_rate": SAMPLE_RATE,
        "duration_seconds": round(full.size / SAMPLE_RATE, 3),
        "line_count": len(timeline),
        "path": str(voice_path),
        "lines": timeline,
        "processing": ["highpass 78Hz", "de-ess", "presence +2dB @2.9k", "compress 3:1", "normalise -1.5dBFS"],
    }
    (out_dir / "voiceover.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # the film consumes this: line timings it can trust
    (out_dir / "lines.json").write_text(
        json.dumps({"lines": timeline}, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", required=True, help="JSON file with the lines")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--backend", default="auto", choices=["auto", "piper", "espeak"])
    parser.add_argument("--allow-download", action="store_true",
                        help="download the Piper weights once if they are missing")
    parser.add_argument("--fps", type=int, default=30, help="frame rate for the lip-sync envelope")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build(Path(args.script), Path(args.out), voice=args.voice,
                       allow_download=args.allow_download, backend=args.backend,
                       fps=args.fps)
    except VoiceBackendMissing as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print("voiceover failed: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("VOICE: %s (%s) %.2fs, %d lines -> %s"
              % (report["backend"], report["voice"], report["duration_seconds"],
                 report["line_count"], report["path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
