"""JSON files: read defensively, write atomically, parse models' prose.

Three helpers that were copied around the repository:

``read_json``
    was ``load(path, default)`` in four modules. A missing file and a corrupt
    file are different problems, and a caller that cannot tell them apart ends
    up silently ignoring a corrupt task queue.
``write_json_atomic``
    existed in ``bridge/bridge.py`` and ``video_studio/publish_youtube.py``. The
    bridge copy had already learned the Windows sharing-violation retry that the
    publishing copy had not; that fix is now shared by both.
``extract_json_object``
    existed verbatim in ``agents/routing.py`` and ``tools/tool_agent.py``.
    Local models wrap JSON in prose, so both planners needed the same tolerance.

This module never logs file contents. A JSON file in this project can hold a
task description, and a task description can hold anything.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

#: Windows can briefly deny ``os.replace`` while another writer replaces the
#: same target. Serialising in-process writers is cheaper than sleeping first.
_REPLACE_LOCK = threading.Lock()
_REPLACE_ATTEMPTS = 8


class JsonFileError(ValueError):
    """A JSON file exists but cannot be understood."""


def read_json(path: str | os.PathLike[str], default: Any = None, *, strict: bool = False) -> Any:
    """Read JSON, returning ``default`` when the file is absent.

    ``strict=True`` turns a corrupt file into :class:`JsonFileError` instead of
    a default. Use it where a default would silently lose user data - the task
    queue, an approval record - and leave it off for optional configuration.
    """
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if strict:
            raise JsonFileError("%s is not valid JSON" % source.name) from exc
        return default
    except OSError as exc:
        if strict:
            raise JsonFileError("cannot read %s (%s)" % (source.name, type(exc).__name__)) from exc
        return default


def write_json_atomic(path: str | os.PathLike[str], value: Any, *, indent: int = 2) -> None:
    """Write JSON through a same-directory temporary file and an atomic replace.

    Same directory matters: ``os.replace`` is only atomic within one filesystem,
    and a temp file in ``%TEMP%`` may live on another drive.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=indent)
            stream.write("\n")
        with _REPLACE_LOCK:
            for attempt in range(_REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary_name, target)
                    return
                except PermissionError:
                    if attempt == _REPLACE_ATTEMPTS - 1:
                        raise
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def extract_json_object(text: str) -> dict | None:
    """The first JSON object that decodes, tolerating prose around it."""
    if not isinstance(text, str):
        return None
    decoder = json.JSONDecoder()
    for match in _object_starts(text):
        try:
            parsed, _ = decoder.raw_decode(text[match:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _object_starts(text: str):
    index = text.find("{")
    while index != -1:
        yield index
        index = text.find("{", index + 1)


__all__ = ["read_json", "write_json_atomic", "extract_json_object", "JsonFileError"]
