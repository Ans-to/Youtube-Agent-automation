"""The HTTP layer: routing, request limits, and error mapping. Nothing else.

``dashboard.py`` used to be 563 lines holding page templates, queue logic, four
threads, twelve globals and this handler. Now:

* **routing and limits** are here;
* **what a form means** is ``app.services.requests``;
* **what the queue does** is ``app.services.tasks``;
* **who is running** is ``app.state``;
* **what a page looks like** is ``ui.dashboard.views``.

The handler reads everything it needs from an injected
:class:`DashboardContext`, so a test can run the real HTTP surface against a
temporary queue without patching a module constant.

Error handling is one wrapper, not twelve try blocks. Expected failures
(``HQError``) map to their status and a short message; anything else is logged
with its type and answered with a 500 that never echoes the exception text.
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Callable
from urllib.parse import parse_qs, urlparse

from app.errors import (
    HQError,
    BadRequestError,
    PayloadTooLargeError,
    describe,
    status_for,
)
from app.paths import ProjectPaths
from app.services import status as status_service
from app.services.requests import (
    build_pipeline_request,
    build_plain_request,
    build_product_request,
    build_video_request,
    TaskRequest,
)
from app.services.tasks import TaskQueue
from app.services.workflows import WorkflowCoordinator
from app.state import RunState
from ui.dashboard import views
from ui.dashboard.security import (
    MAX_FORM_BODY_BYTES,
    resolve_workspace_file,
    validate_post_request,
)

#: Response headers applied to every reply. Values, not policy: keep them here
#: so a new route cannot accidentally ship without them.
SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy",
     "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
     "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
     "worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; "
     "base-uri 'self'; form-action 'self'"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
)

#: Fixed PWA assets: (file relative to web/, content type, binary?).
STATIC_ASSETS: dict[str, tuple[str, str, bool]] = {
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8", False),
    "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8", False),
    "/icon.svg": ("icon.svg", "image/svg+xml; charset=utf-8", False),
    "/offline.html": ("offline.html", "text/html; charset=utf-8", False),
    "/icon-192.png": ("icons/icon-192.png", "image/png", True),
    "/icon-512.png": ("icons/icon-512.png", "image/png", True),
    "/icon-maskable-512.png": ("icons/icon-maskable-512.png", "image/png", True),
    "/stills/hero.jpg": ("stills/hero.jpg", "image/jpeg", True),
    "/stills/code.jpg": ("stills/code.jpg", "image/jpeg", True),
    "/stills/server.jpg": ("stills/server.jpg", "image/jpeg", True),
    "/stills/studio.jpg": ("stills/studio.jpg", "image/jpeg", True),
}


@dataclass
class DashboardContext:
    """Everything the handler needs, injected once at startup."""

    paths: ProjectPaths
    state: RunState
    queue: TaskQueue
    workflows: WorkflowCoordinator
    deck: str
    config_loader: Callable[[], dict]

    def config(self) -> dict:
        return self.config_loader()

    def resolve_source(self, supplied: str):
        return resolve_workspace_file(self.paths.workspace.resolve(), supplied)


def _render_markdown(text: str) -> str:
    from web.markdown_renderer import render_markdown_safe

    return render_markdown_safe(text)


def build_handler(context: DashboardContext) -> type[BaseHTTPRequestHandler]:
    """Return a handler class bound to ``context``.

    A class (not an instance) because ``HTTPServer((host, port), handler)``
    instantiates it per request, and because tests construct it the same way.
    """

    class Handler(BaseHTTPRequestHandler):
        ctx = context

        # ---------------------------------------------------------- plumbing
        def send(self, body, content_type="text/html; charset=utf-8", status=200):
            raw = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser navigated away; nothing to report

        def send_json(self, payload, status=200):
            self.send(json.dumps(payload), "application/json; charset=utf-8", status)

        def _redirect(self, location):
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _fail(self, message: str, status: int, *, as_json: bool = False):
            if as_json:
                return self.send_json({"error": message}, status)
            return self.send(views.error_page(message, status), status=status)

        def log_message(self, fmt, *args):
            """Keep the console quiet; the app logs to files instead."""

        def _guarded(self, action: Callable[[], None], *, as_json: bool) -> None:
            """Run one route, mapping failures to honest statuses."""
            try:
                action()
            except HQError as exc:
                self._fail(exc.user_message(), exc.status, as_json=as_json)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:  # noqa: BLE001 - the boundary owns this
                # A boundary is the one place a broad except is correct: the
                # alternative is a traceback in the browser and a dead thread.
                print("[dashboard] " + describe(exc), file=sys.stderr)
                traceback.print_exc(limit=3)
                self._fail(
                    "The request could not be completed. See the terminal for the details.",
                    status_for(exc),
                    as_json=as_json,
                )

        # -------------------------------------------------------------- routes
        def do_GET(self):
            parsed = urlparse(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            as_json = path.startswith("/api/")
            self._guarded(lambda: self._get(path, query), as_json=as_json)

        def _get(self, path: str, query: dict):
            if path in STATIC_ASSETS:
                return self._send_asset(path)
            if path == "/":
                return self.send(self.ctx.deck)
            if path == "/api/state":
                return self.send_json(status_service.build_status(
                    paths=self.ctx.paths, config=self.ctx.config(),
                    queue=self.ctx.queue, state=self.ctx.state,
                ))
            if path == "/health":
                return self.send_json(status_service.health(self.ctx.queue, self.ctx.paths))
            if path in {"/task", "/output"}:
                return self._task_or_output(path, query.get("id", [""])[0])
            return self.send("Not found", status=404)

        def _send_asset(self, path: str):
            file_name, content_type, binary = STATIC_ASSETS[path]
            target = self.ctx.paths.web / file_name
            try:
                asset = target.read_bytes() if binary else target.read_text(encoding="utf-8")
            except OSError:
                return self.send("PWA asset unavailable", status=503)
            return self.send(asset, content_type)

        def _task_or_output(self, path: str, task_id: str):
            task = self.ctx.queue.find(task_id)
            if not task:
                return self.send("Task not found", status=404)
            if path == "/task":
                return self.send(views.task_page(task))
            relative = task.get("output_file", "")
            candidate = status_service.output_path(self.ctx.paths, relative)
            if candidate is None:
                return self.send("Output file not found", status=404)
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return self.send("Output file could not be read", status=503)
            return self.send(views.output_page(task, relative, _render_markdown(content)))

        # ------------------------------------------------------------- writes
        def do_POST(self):
            path = urlparse(self.path).path
            self._guarded(lambda: self._post(path), as_json=path.startswith("/api/"))

        def _post(self, path: str):
            request_error = validate_post_request(self.headers, self.server.server_port)
            if request_error:
                return self._fail(request_error, 403)
            form = self._read_form()
            if path == "/add":
                return self._enqueue(build_plain_request(form), "Could not safely queue task")
            if path == "/practice-agent":
                return self._fail(
                    "Direct specialist execution is disabled. Submit the goal to AGENT-01 (CEO), "
                    "which selects the specialist team.",
                    403,
                )
            if path == "/generate-video":
                enabled = bool(self.ctx.config().get("model", {}).get("enabled"))
                return self._enqueue(
                    build_video_request(form, resolve_file=self.ctx.resolve_source, model_enabled=enabled),
                    "Could not queue video task for the CEO",
                )
            if path == "/build-product":
                return self._enqueue(build_product_request(form), "Could not queue product task for the CEO")
            if path == "/run-pipeline":
                return self._run_pipeline(form)
            if path == "/run":
                started, active = self.ctx.workflows.start_queue_worker()
                if not started:
                    return self._fail(
                        "Another workflow is already running: " + active + ". The task remains "
                        "queued and will run after the current workflow ends.",
                        409,
                    )
                return self._redirect("/")
            if path == "/refresh":
                return self._redirect("/")
            return self.send("Not found", status=404)

        def _read_form(self) -> dict:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise BadRequestError("Missing Content-Length.")
            try:
                length = int(raw_length)
            except ValueError:
                raise BadRequestError("Invalid Content-Length.") from None
            if length < 0:
                raise BadRequestError("Invalid Content-Length.")
            if length > MAX_FORM_BODY_BYTES:
                raise PayloadTooLargeError("Request body must not exceed 128,000 bytes.")
            body = self.rfile.read(length).decode("utf-8", "replace")
            return parse_qs(body)

        def _enqueue(self, request: TaskRequest, failure: str):
            task_id = self.ctx.queue.enqueue(
                request.title, request.kind, request.text, request.context_file
            )
            started, active = self.ctx.workflows.start_queue_worker()
            if not started:
                print("[dashboard] %s: task %s queued; %s holds the core" % (failure, task_id, active))
            return self._redirect("/")

        def _run_pipeline(self, form: dict):
            request = build_pipeline_request(form, resolve_file=self.ctx.resolve_source)
            output = self.ctx.workflows.start_pipeline(request.task, request.context_file)
            print("[dashboard] CEO pipeline started -> " + output)
            return self._redirect("/")

    return Handler


def make_server(context: DashboardContext, host: str, port: int):
    """Bind an HTTPServer to a handler bound to ``context``."""
    from http.server import HTTPServer

    return HTTPServer((host, port), build_handler(context))


__all__ = ["DashboardContext", "build_handler", "make_server", "STATIC_ASSETS", "SECURITY_HEADERS"]
