"""Speak through libespeak-ng directly, so no system package is required.

The narration backend used to need one of two things: a neural voice model
downloaded from the internet (not allowed here, and a 60 MB download on a phone),
or the `espeak-ng` command on PATH, which on Windows means finding an installer
and on a locked-down machine means an administrator.

`libespeak-ng` is distributed as a Python wheel (`pip install espeakng-loader`),
which ships the shared library *and* its language data for Linux, macOS, Windows
and the Raspberry Pi. Loading it with `ctypes` gives the same synthesizer without
a system package, without `PATH`, and without a network call at any point.

The audio goes through the same prosody the CLI exposes: voice, words per
minute, pitch and amplitude, so a caller can still shape a line.
"""

from __future__ import annotations

import ctypes
import tempfile
from pathlib import Path

# espeak_Initialize output mode
AUDIO_OUTPUT_RETRIEVAL = 2
# espeak_SetParameter ids
PARAM_RATE = 1
PARAM_PITCH = 3
PARAM_AMPLITUDE = 4

_LIB = None
_RATE = 0
_ERROR = None


class EspeakUnavailable(RuntimeError):
    """Neither the shared library nor the command is present."""


def _load():
    """Load the library once. Returns (lib, sample_rate) or raises."""
    global _LIB, _RATE, _ERROR
    if _LIB is not None:
        return _LIB, _RATE
    if _ERROR is not None:
        raise EspeakUnavailable(_ERROR)

    try:
        import espeakng_loader
    except Exception as exc:  # noqa: BLE001 - any import failure is the same answer
        _ERROR = ("the speech library is not installed: pip install espeakng-loader "
                  f"({exc.__class__.__name__})")
        raise EspeakUnavailable(_ERROR) from None

    try:
        lib = ctypes.CDLL(espeakng_loader.get_library_path())
    except OSError as exc:
        _ERROR = f"the speech library could not be loaded: {exc}"
        raise EspeakUnavailable(_ERROR) from None

    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    rate = lib.espeak_Initialize(AUDIO_OUTPUT_RETRIEVAL, 400,
                                 str(espeakng_loader.get_data_path()).encode("utf-8"), 0)
    if rate <= 0:
        _ERROR = "the speech library initialised without a sample rate"
        raise EspeakUnavailable(_ERROR)

    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetParameter.restype = ctypes.c_int
    lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.espeak_Synth.restype = ctypes.c_int
    lib.espeak_Synth.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p,
    ]
    lib.espeak_Synchronize.restype = ctypes.c_int
    lib.espeak_Synchronize.argtypes = []

    _LIB, _RATE = lib, int(rate)
    return _LIB, _RATE


def available() -> bool:
    try:
        _load()
    except EspeakUnavailable:
        return False
    return True


def why_unavailable() -> str:
    try:
        _load()
    except EspeakUnavailable as exc:
        return str(exc)
    return ""


def sample_rate() -> int:
    _, rate = _load()
    return rate


CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int,
                            ctypes.POINTER(ctypes.c_void_p))


def synthesize(text: str, *, voice: str = "en-us", wpm: int = 150, pitch: int = 45,
               amplitude: int = 150) -> tuple[bytes, int]:
    """Render `text` to 16-bit mono PCM. Returns (pcm_bytes, sample_rate)."""
    lib, rate = _load()

    if lib.espeak_SetVoiceByName(voice.encode("utf-8")) != 0:
        raise EspeakUnavailable(f"the speech library has no voice {voice!r}")

    # Pitch and amplitude are 0..99; rate is words per minute.
    lib.espeak_SetParameter(PARAM_RATE, max(80, min(450, int(wpm))), 0)
    lib.espeak_SetParameter(PARAM_PITCH, max(0, min(99, int(pitch))), 0)
    lib.espeak_SetParameter(PARAM_AMPLITUDE, max(0, min(200, int(amplitude))), 0)

    chunks: list[bytes] = []

    def _collect(samples, count, _events):
        if count > 0 and samples:
            chunks.append(ctypes.string_at(samples, count * 2))
        return 0

    callback = CALLBACK(_collect)
    lib.espeak_SetSynthCallback(callback)

    payload = text.encode("utf-8")
    uid = ctypes.c_uint()
    # position_type 1 = the position is a character index; 0x01 = UTF-8 input
    status = lib.espeak_Synth(payload, len(payload) + 1, 0, 1, 0, 0x01,
                             ctypes.byref(uid), None)
    lib.espeak_Synchronize()
    if status != 0:
        raise EspeakUnavailable(f"the speech library returned status {status}")

    pcm = b"".join(chunks)
    if not pcm:
        raise EspeakUnavailable(f"the speech library produced no audio for {text!r}")
    return pcm, rate


def write_wav(path: str | Path, pcm: bytes, rate: int) -> Path:
    """Write 16-bit mono PCM as a WAV file."""
    import wave

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(pcm)
    return target


def say(text: str, path: str | Path | None = None, **options) -> Path:
    """Convenience wrapper: synthesise and write a WAV, returning its path."""
    pcm, rate = synthesize(text, **options)
    if path is None:
        handle, name = tempfile.mkstemp(suffix=".wav", prefix="espeak-")
        Path(handle).close() if isinstance(handle, int) else None
        path = name
    return write_wav(path, pcm, rate)
