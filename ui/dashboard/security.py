"""Request-level safety rules for the local dashboard.

The dashboard binds to loopback, so the threat is not the network - it is a
web page in the user's own browser posting to ``127.0.0.1:8765`` on the user's
behalf, and a ``Host`` header that points a request somewhere else.

The rules, unchanged from the version that lived in ``dashboard.py``:

* ``Host`` must be a loopback name **and** this server's port, with no path,
  query, fragment or credentials;
* ``Origin`` must be present and identical, because a missing ``Origin`` is the
  classic CSRF bypass;
* the body must be a urlencoded form with an explicit ``Content-Length`` - no
  chunked encoding, so the server never reads an unbounded body.

The functions return a message string, or ``None`` when the request is fine.
They are pure: pass the headers, get an answer, no server required.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Mapping

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Largest form body accepted. A task description is capped below this anyway.
MAX_FORM_BODY_BYTES = 128000

#: Source/context files a person may attach to a task.
ALLOWED_SOURCE_SUFFIXES = frozenset({".txt", ".md", ".json"})

#: Largest attachable file.
MAX_SOURCE_BYTES = 2_000_000


def validate_post_request(headers: Mapping[str, str], server_port: int) -> str | None:
    """Reject browser POSTs without a same-origin loopback context."""
    host_header = headers.get("Host", "")
    origin = headers.get("Origin")
    content_type = headers.get("Content-Type", "")
    if not host_header:
        return "Missing Host header."
    try:
        parsed_host = urlparse("//" + host_header)
        host_port = parsed_host.port
    except ValueError:
        return "Invalid Host header."
    if (
        parsed_host.username
        or parsed_host.password
        or parsed_host.hostname not in LOOPBACK_HOSTS
        or host_port != server_port
        or parsed_host.path
        or parsed_host.query
        or parsed_host.fragment
    ):
        return "Host must match this loopback dashboard and port."
    if not origin:
        return "Missing Origin header; POST requests must be same-origin."
    try:
        parsed_origin = urlparse(origin)
        origin_port = parsed_origin.port
    except ValueError:
        return "Invalid Origin header."
    if (
        parsed_origin.scheme != "http"
        or parsed_origin.username
        or parsed_origin.password
        or parsed_origin.hostname != parsed_host.hostname
        or origin_port != server_port
        or parsed_origin.path
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        return "Cross-origin POST requests are not allowed."
    if content_type.split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        return "Unsupported request content type."
    if headers.get("Transfer-Encoding"):
        return "Transfer-Encoding is not supported."
    return None


def resolve_workspace_file(workspace: Path, supplied: str) -> Path | None:
    """Resolve a user-supplied source file, or ``None`` if it is not acceptable.

    Accepts a path relative to the project root or an absolute path, and only
    returns a file that (a) exists, (b) is inside ``workspace``, (c) has an
    allowed suffix, and (d) is under the size cap. Every failure is the same
    answer on purpose: the caller shows one message and the response does not
    reveal whether a file outside the workspace exists.
    """
    candidate = Path(supplied).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (workspace.parent / candidate).resolve()
    if resolved == workspace or workspace not in resolved.parents:
        return None
    if resolved.suffix.lower() not in ALLOWED_SOURCE_SUFFIXES:
        return None
    try:
        if not resolved.is_file() or resolved.stat().st_size > MAX_SOURCE_BYTES:
            return None
    except OSError:
        return None
    return resolved


__all__ = [
    "validate_post_request",
    "resolve_workspace_file",
    "LOOPBACK_HOSTS",
    "MAX_FORM_BODY_BYTES",
    "ALLOWED_SOURCE_SUFFIXES",
    "MAX_SOURCE_BYTES",
]
