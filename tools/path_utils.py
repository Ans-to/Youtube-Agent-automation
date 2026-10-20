"""Cross-platform path canonicalization and workspace containment helpers."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


def canonical_path(value: str | os.PathLike[str]) -> Path:
    """Resolve a path and expand Windows 8.3 aliases where the filesystem allows it.

    Path.resolve() follows symlinks, but on Windows it can preserve a short alias
    such as C:\\Users\\RUNNER~1 while another equivalent path uses C:\\Users\\runneradmin.
    Expand the nearest existing ancestor, then reattach any not-yet-created suffix.
    """
    resolved = Path(value).expanduser().resolve()
    if os.name != "nt":
        return resolved

    missing_parts: list[str] = []
    existing = resolved
    while not existing.exists() and existing.parent != existing:
        missing_parts.append(existing.name)
        existing = existing.parent

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_long_path = kernel32.GetLongPathNameW
        get_long_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        get_long_path.restype = ctypes.c_uint32
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_long_path(str(existing), buffer, len(buffer))
        if 0 < length < len(buffer):
            existing = Path(buffer.value)
    except (AttributeError, OSError, TypeError, ValueError):
        # Containment checks still fail closed if Windows cannot expand the alias.
        return resolved

    for component in reversed(missing_parts):
        existing = existing / component
    return existing


def safe_relative_path(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> Path:
    """Return a canonical path relative to root, raising ValueError if it escapes."""
    return canonical_path(path).relative_to(canonical_path(root))


def is_within(
    path: str | os.PathLike[str],
    root: str | os.PathLike[str],
    *,
    allow_equal: bool = True,
) -> bool:
    """Check canonical containment without mistaking Windows short/long aliases."""
    try:
        relative = safe_relative_path(path, root)
    except (OSError, RuntimeError, ValueError):
        return False
    return allow_equal or relative != Path(".")
