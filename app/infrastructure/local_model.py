"""The one way this application talks to a local language model.

``post_local_model`` existed three times - in ``agent.py``, in
``agents/dispatch.py`` and in ``product_studio/build_product.py`` - as the same
forty lines with different whitespace. Three copies of a security check is three
chances to fix only two of them, so the check now lives here once.

What the check guarantees:

* the URL is plain ``http`` on a **literal loopback IP** - not a hostname that
  could resolve elsewhere, not ``https``, not ``http://user:pass@host``;
* there is an explicit port in range, and no query or fragment, because a
  fragment is a place to hide a second destination;
* proxies are disabled, so ``HTTP_PROXY`` cannot redirect the request off-box;
* redirects are refused rather than followed to an unchecked host;
* the response is size-capped and must be a JSON object.

Everything else decides *what* to ask the model. That belongs to the caller.
"""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.errors import LocalModelError

#: A model that answers with more than this is not a chat completion.
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 300
MIN_TIMEOUT_SECONDS = 1

ENDPOINT_HINT = (
    "Use a literal loopback IP endpoint such as "
    "http://127.0.0.1:8080/v1/chat/completions."
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect; the destination was never validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        # ``msg`` and ``newurl`` are part of the handler protocol; the point of
        # this override is that ``newurl`` is never followed.
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirects are disabled for local model requests", headers, fp
        )


def validate_loopback_url(url: str) -> str:
    """Return ``url`` unchanged, or raise :class:`LocalModelError`.

    Separated from the request so the rule can be tested without a server.
    """
    parts = urllib.parse.urlsplit(str(url or ""))
    try:
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError as exc:
        raise LocalModelError(ENDPOINT_HINT, detail=type(exc).__name__) from exc
    if (
        parts.scheme != "http"
        or not address.is_loopback
        or port is None
        or not 1 <= port <= 65535
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise LocalModelError(
            "Only a plain HTTP endpoint on a literal loopback IP and explicit port is allowed."
        )
    return url


def _clamp_timeout(timeout: Any) -> int:
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        value = 120
    return max(MIN_TIMEOUT_SECONDS, min(value, MAX_TIMEOUT_SECONDS))


def post_local_model(url: str, body: dict, timeout: int | float = 120) -> dict:
    """POST one JSON body to a validated loopback endpoint and return the object."""
    validate_loopback_url(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=_clamp_timeout(timeout)) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # The status is useful; the body may quote the prompt, so it is dropped.
        raise LocalModelError(
            "The local model returned an error.", detail="HTTP %s" % exc.code
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LocalModelError(
            "Could not reach the local model endpoint.",
            detail=type(getattr(exc, "reason", exc)).__name__,
        ) from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise LocalModelError("The local model response was too large.")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalModelError("The local model returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise LocalModelError("Local model response must be a JSON object.")
    return data


__all__ = ["post_local_model", "validate_loopback_url", "MAX_RESPONSE_BYTES"]
