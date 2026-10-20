"""Cross-process lock for the renderer's shared working files.

The renderer writes fixed intermediate paths (frames/, render-manifest.json, and
voice_segments/). Concurrent renders would overwrite one another, so every
render must hold this lock before touching those paths.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def render_lock(
    lock_path: str | Path,
    *,
    timeout_seconds: float = 24 * 60 * 60,
    poll_interval_seconds: float = 1.0,
) -> Iterator[None]:
    """Acquire an OS-level exclusive lock, waiting safely for another render.

    The lock file is intentionally persistent. Removing it after unlock can
    let a third process lock a new inode while another process waits on the
    old one.
    """
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")

    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        # msvcrt.locking locks a byte range and requires the byte to exist.
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        started = time.monotonic()
        announced_wait = False
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError) as exc:
                elapsed = time.monotonic() - started
                if elapsed >= timeout_seconds:
                    raise TimeoutError(
                        f"Timed out waiting for renderer lock: {path}"
                    ) from exc
                if not announced_wait:
                    print(
                        "Another video render is active; waiting for its shared "
                        "intermediate files to become available.",
                        flush=True,
                    )
                    announced_wait = True
                time.sleep(min(poll_interval_seconds, max(0.01, timeout_seconds - elapsed)))

        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
