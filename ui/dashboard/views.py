"""HTML for the dashboard's small pages. No business logic, no file access.

The deck (``web/deck.html``) is the main interface and stays a real HTML file -
it is edited as HTML, not as a Python string. The two detail pages and the error
page are built here because they are short and need escaped task data.

Every value that came from a task record passes through :func:`escape` before it
reaches the page. Task records are written by a model, so they are untrusted
input even when the person who queued the task is the machine's owner.
"""
from __future__ import annotations

from html import escape as _escape
from pathlib import Path

#: Shared page chrome for the small pages. The deck supplies its own.
PAGE_STYLE = (
    "body{font:16px/1.65 system-ui;background:#0b090e;color:#f8edf0;"
    "padding:16px;max-width:980px;margin:auto}"
    "a{color:#ff9c3e}"
    ".doc{background:#141019;border:1px solid #512b31;border-radius:16px;"
    "padding:clamp(16px,4vw,32px);overflow-wrap:anywhere}"
    "h1,h2,h3{color:#ffd19b;line-height:1.25}"
    "h2{margin-top:28px;border-bottom:1px solid #54333e;padding-bottom:8px}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0f0c13;"
    "border:1px solid #3a2530;border-radius:10px;padding:12px}"
    "li{margin:7px 0}"
    "blockquote{border-left:3px solid #ff8a32;padding-left:12px;color:#d8bdc6}"
    "hr{border:0;border-top:1px solid #54333e}p{margin:12px 0}"
    ".error{color:#ff777d}.muted{color:#a99ca5}"
)


def escape(value: object) -> str:
    """HTML-escape any value, including ``None``."""
    return _escape("" if value is None else str(value), quote=True)


def page(title: str, body: str) -> str:
    """Wrap body content in the shared document shell."""
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'>"
        "<title>" + escape(title) + "</title>"
        "<style>" + PAGE_STYLE + "</style>"
        "<a href='/'>\u2190 Dashboard</a>" + body
    )


def load_deck(path: Path) -> str:
    """Read the command-deck interface from disk.

    The page lives in ``web/deck.html`` so the UI can be edited as HTML instead
    of a Python string literal. It is repository-owned, served only from ``/``,
    and contains no external references. A missing file is a packaging error and
    must fail loudly rather than serve a half-built dashboard.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            "%s is missing or unreadable; the dashboard interface ships with the "
            "repository. Re-extract the project archive." % Path(path).name
        ) from exc


def task_page(task: dict) -> str:
    """The detail view for one task."""
    body = "<h2>" + escape(task.get("title")) + "</h2>"
    body += "<p><b>Status:</b> " + escape(task.get("status")) + "</p>"
    body += "<p><b>Request</b></p><pre>" + escape(task.get("input")) + "</pre>"
    if task.get("error"):
        body += "<p class='error'><b>Error:</b> " + escape(task["error"]) + "</p>"
    if task.get("output_file"):
        body += "<p><a href='/output?id=" + escape(task.get("id")) + "'>Open output</a></p>"
    return page(str(task.get("title") or "Task"), body)


def output_page(task: dict, relative_path: str, rendered_markdown: str) -> str:
    """A task's Markdown deliverable, rendered safely."""
    body = (
        "<p class='muted'>" + escape(relative_path) + "</p>"
        "<article class='doc'><h1>" + escape(task.get("title")) + "</h1>"
        + rendered_markdown + "</article>"
    )
    return page(str(task.get("title") or "Output"), body)


def error_page(message: str, status: int) -> str:
    """A short, human explanation with no stack trace and no internals."""
    return page(
        "Request failed",
        "<h2 class='error'>Request failed</h2><p>" + escape(message) + "</p>"
        "<p class='muted'>Status " + escape(status) + "</p>",
    )


__all__ = ["escape", "page", "load_deck", "task_page", "output_page", "error_page", "PAGE_STYLE"]
