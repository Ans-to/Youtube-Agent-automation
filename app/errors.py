"""One exception vocabulary for the whole application.

Before this module every layer invented its own failures: ``ValueError`` for a
bad task, ``RuntimeError`` for a busy workflow, ``OSError`` for a write, and a
bare string in the HTTP layer that turned all three into a 500. The problem was
not the message - it was that the caller could not tell "the user typed
something wrong" (400) from "the disk is full" (503) from "another job is
running" (409), so the dashboard showed the same unhelpful page for each.

Rules
-----
* Every application error derives from :class:`HQError`.
* Each error also inherits from the built-in it used to be, so existing
  ``except ValueError`` / ``except RuntimeError`` call sites keep working while
  code migrates.
* :attr:`HQError.status` is the HTTP status the UI should answer with.
* :meth:`HQError.user_message` is safe to render: type name, fixed text, and a
  short detail. Never a token, a path, or a stack trace.
"""
from __future__ import annotations

from typing import Any

MAX_DETAIL_CHARS = 300


class HQError(Exception):
    """Base class for every expected application failure."""

    status = 500
    code = "hq_error"

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = str(message)
        self.detail = str(detail)[:MAX_DETAIL_CHARS]

    def user_message(self) -> str:
        """A line that can be shown to a person without leaking internals."""
        if self.detail:
            return "%s (%s)" % (self.message, self.detail)
        return self.message

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.user_message()}


class ConfigError(HQError, ValueError):
    """Configuration is malformed or an override is invalid."""

    status = 500
    code = "config_error"


class TaskInputError(HQError, ValueError):
    """A task could not be accepted as given."""

    status = 400
    code = "task_input_error"


class WorkflowBusyError(HQError, RuntimeError):
    """Another exclusive workflow holds the command core."""

    status = 409
    code = "workflow_busy"

    def __init__(self, message: str, *, active: str = "") -> None:
        super().__init__(message, detail=active)
        self.active = active


class BadRequestError(HQError, ValueError):
    """The request itself is malformed - missing length, wrong encoding."""

    status = 400
    code = "bad_request"


class PayloadTooLargeError(HQError, ValueError):
    """The request body exceeds the size this server will read."""

    status = 413
    code = "payload_too_large"


class StorageError(HQError, OSError):
    """A durable write or read could not complete."""

    status = 503
    code = "storage_error"


class DependencyMissing(HQError, RuntimeError):
    """A required external tool (FFmpeg, Node, a voice model) is absent."""

    status = 503
    code = "dependency_missing"


class LocalModelError(HQError, ValueError):
    """The loopback model endpoint is invalid or returned something unusable."""

    status = 502
    code = "local_model_error"


#: Status for an exception that is not an ``HQError`` at all.
DEFAULT_ERROR_STATUS = 500


def status_for(exc: BaseException) -> int:
    """HTTP status for any exception, without leaking the exception type."""
    if isinstance(exc, HQError):
        return exc.status
    if isinstance(exc, (ValueError, TypeError)):  # bad input, not our fault
        return 400
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return 503
    return DEFAULT_ERROR_STATUS


def describe(exc: BaseException) -> str:
    """``TypeName: first 300 characters`` - for logs, never for credentials.

    Exception text can contain a URL, and a URL can contain a user name. The
    caller decides whether this is safe to show; the HTTP layer uses
    :meth:`HQError.user_message` instead, which never surprises.
    """
    text = str(exc).replace("\n", " ").strip()
    return ("%s: %s" % (type(exc).__name__, text))[:MAX_DETAIL_CHARS] if text else type(exc).__name__


__all__ = [
    "HQError",
    "ConfigError",
    "TaskInputError",
    "BadRequestError",
    "PayloadTooLargeError",
    "WorkflowBusyError",
    "StorageError",
    "DependencyMissing",
    "LocalModelError",
    "status_for",
    "describe",
]
