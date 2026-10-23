"""Find FFmpeg once, for every workflow that needs it.

The same fifteen lines lived in ``tools/assemble_voiceover.py``,
``tools/render_motion_film.py`` and ``video_studio/repeat_frames.py``: try the
system binary, else the binary bundled inside the ``imageio-ffmpeg`` wheel,
else fail. Only the failure text differed - which is the tell that it is one
concern with three copies.

``ffprobe`` has no bundled fallback: the wheel ships ``ffmpeg`` only, so a
machine without a system FFmpeg can encode but cannot probe. Saying so is
better than a stack trace inside a render.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.errors import DependencyMissing

INSTALL_HINT = (
    "FFmpeg is not installed. Install it (apt-get install ffmpeg, "
    "brew install ffmpeg, or winget install Gyan.FFmpeg) "
    "or run: python -m pip install imageio-ffmpeg"
)


def find_ffmpeg() -> str | None:
    """The FFmpeg to use, or ``None``. Never raises."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # the optional convenience; an absent wheel is not an error
        import imageio_ffmpeg  # type: ignore[import-not-found]

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - any failure here means "not available"
        return None
    return bundled if bundled and Path(bundled).is_file() else None


def find_ffprobe() -> str | None:
    """The FFprobe to use, or ``None``. The wheel does not bundle one."""
    return shutil.which("ffprobe")


def require_ffmpeg(
    *,
    message: str | None = None,
    error: type[Exception] = DependencyMissing,
) -> str:
    """Return FFmpeg or raise ``error(message)``.

    ``error`` lets a caller keep its own exception class - the render drivers
    already translate a missing dependency into their own exit code, and that
    behaviour is worth preserving.
    """
    binary = find_ffmpeg()
    if binary:
        return binary
    raise error(message or INSTALL_HINT)


def require_ffmpeg_and_probe(
    *,
    message: str | None = None,
    error: type[Exception] = DependencyMissing,
) -> tuple[str, str]:
    """Return ``(ffmpeg, ffprobe)`` or raise. Used by the render drivers."""
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if not ffmpeg or not ffprobe:
        raise error(message or ("Both ffmpeg and ffprobe must be installed. " + INSTALL_HINT))
    return ffmpeg, ffprobe


__all__ = [
    "find_ffmpeg",
    "find_ffprobe",
    "require_ffmpeg",
    "require_ffmpeg_and_probe",
    "INSTALL_HINT",
]
