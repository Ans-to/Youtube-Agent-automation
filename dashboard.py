#!/usr/bin/env python3
"""Offline Agent HQ dashboard - the composition root.

This file used to be the whole application: 563 lines of HTML building, queue
writes, thread management and twelve module globals. It is now a *wiring* file:
it constructs the objects the app needs, hands them to one handler, and keeps a
few backwards-compatible names so existing scripts and tests keep working.

Where the behaviour lives now:

===============  ===========================================================
what             where
===============  ===========================================================
routing          ``ui/dashboard/server.py``
pages            ``ui/dashboard/views.py`` + ``web/deck.html``
request safety   ``ui/dashboard/security.py``
form rules       ``app/services/requests.py``
queue            ``app/services/tasks.py``
background work  ``app/services/workflows.py``
run flags        ``app.state.RunState``
paths            ``app/paths.py``
===============  ===========================================================

Run it the same way as before::

    python dashboard.py            # http://127.0.0.1:8765
    python dashboard.py --port 0   # any free port (tests, second window)
"""
from __future__ import annotations

import argparse
import threading
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from app.paths import ProjectPaths, default_paths
from app.services.tasks import TaskQueue
from app.services.workflows import WorkflowCoordinator
from app.state import RunState
from app_config import load_config
from ui.dashboard.server import DashboardContext, build_handler
from ui.dashboard.security import MAX_FORM_BODY_BYTES, validate_post_request  # noqa: F401 - public
from ui.dashboard.views import load_deck
from web.markdown_renderer import render_markdown_safe  # noqa: F401 - public (used by tests)

# --------------------------------------------------------------------- wiring
BASE: Path = Path(__file__).resolve().parent
PATHS: ProjectPaths = default_paths()
TASKS = PATHS.tasks          # kept for callers that read the path
CONFIG = PATHS.config
OUTPUTS = PATHS.outputs
LOGS = PATHS.logs
DECK = PATHS.deck
HTML_PAGE = load_deck(DECK)

STATE = RunState()
QUEUE = TaskQueue(TASKS)
WORKFLOWS = WorkflowCoordinator(paths=PATHS, state=STATE, queue=QUEUE)

CONTEXT = DashboardContext(
    paths=PATHS,
    state=STATE,
    queue=QUEUE,
    workflows=WORKFLOWS,
    deck=HTML_PAGE,
    config_loader=lambda: load_config(CONFIG),
)

Handler = build_handler(CONTEXT)


# ------------------------------------------------- backwards-compatible helpers
# Kept because launch scripts and older tests call them. Each is a one-line
# delegation to the object that now owns the behaviour; none of them keep state.
def _queue() -> TaskQueue:
    """The queue for the current ``TASKS`` path.

    ``TASKS`` stays a module attribute so existing code - and tests - can point
    the dashboard at another file. When it points somewhere else, a queue for
    that path is created instead of silently writing to the configured one.
    """
    return QUEUE if Path(TASKS) == QUEUE.path else TaskQueue(TASKS)


def enqueue_task(title, kind, user_input, context_file=""):
    """Persist one validated task for the CEO-led queue runner."""
    return _queue().enqueue(title, kind, user_input, context_file)


def has_pending_tasks() -> bool:
    return _queue().has_pending()


def has_running_tasks() -> bool:
    return _queue().has_running()


def attach_task_progress(tasks):
    pipeline_dir = Path(BASE) / "workspace" / "orchestration"
    return _queue().attach_progress(tasks, pipeline_dir)


def start_task_runner():
    return WORKFLOWS.start_queue_worker()


def try_claim_workflow(name: str) -> tuple[bool, str]:
    return STATE.claim_workflow(name)


def release_workflow(name: str) -> bool:
    return WORKFLOWS.release(name)


def build_state() -> dict:
    """The ``/api/state`` payload. Kept for callers that imported it."""
    from app.services.status import build_status

    return build_status(paths=PATHS, config=load_config(CONFIG), queue=QUEUE, state=STATE)


# ``task_state`` was the old name for the same read model.
task_state = build_state


def __getattr__(name: str):
    """Read-only views of run flags, for code written against the old globals.

    Assigning to these names would shadow them and silently do nothing, which is
    exactly the bug this refactor removes - so writes are refused with a clear
    message instead of being accepted and ignored.
    """
    snapshot = STATE.snapshot()
    if name == "RUNNING":
        return snapshot["worker_running"]
    if name == "ACTIVE_WORKFLOW":
        return snapshot["active_workflow"]
    if name == "PIPELINE_RUNNING":
        return snapshot["pipeline_running"]
    if name == "PIPELINE_LAST_OUTPUT":
        return snapshot["pipeline_output"]
    raise AttributeError(name)


# -------------------------------------------------------------------- launcher
def open_when_ready(url, delay=1.2):
    """Open the app in the default browser once the server is listening.

    A launcher that prints a URL and waits for the user to copy it is not an
    installed app. This runs on a daemon timer so it can never hold the process
    open, and a machine with no browser (Termux, a headless PC) reports the URL
    instead of failing.
    """

    def attempt():
        try:
            opened = webbrowser.open(url)
        except Exception:  # noqa: BLE001 - no browser is not an error here
            opened = False
        if not opened:
            print("Open this address in a browser: " + url)

    timer = threading.Timer(delay, attempt)
    timer.daemon = True
    timer.start()
    return timer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local Agent HQ dashboard.")
    parser.add_argument("--port", type=int, default=None,
                        help="override the configured port (default 8765)")
    parser.add_argument("--no-open", action="store_true",
                        help="do not open the app in a browser window")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(CONFIG)
    except ValueError as exc:
        raise SystemExit("Configuration error: " + str(exc))
    dashboard_cfg = cfg.get("dashboard", {})
    host = dashboard_cfg.get("host", "127.0.0.1")
    port = args.port if args.port is not None else int(dashboard_cfg.get("port", 8765))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Safety check: dashboard must bind to loopback only.")
    # 0 is allowed on purpose: it asks the OS for a free port, which is how tests
    # and second windows avoid a collision. Anything else must be a real port.
    if not 0 <= port <= 65535:
        raise SystemExit("Port must be between 0 and 65535 (0 lets the OS choose).")
    try:
        server = HTTPServer((host, port), Handler)
    except OSError as exc:
        raise SystemExit(
            "Port %d is already in use (%s). Another Agent HQ window may already be "
            "open at http://127.0.0.1:%d , or start this one with --port 8766."
            % (port, exc.strerror or exc, port)
        )
    if has_pending_tasks() or has_running_tasks():
        print("Queued or interrupted task records detected; inspecting and resuming "
              "the local queue worker safely.")
        started, active = start_task_runner()
        if not started:
            print("Queue remains pending because another workflow is active: " + active)
    url = "http://127.0.0.1:%d" % server.server_port
    print("Holographic Offline Agent HQ: " + url)
    print("Keep the terminal open. Press Ctrl+C to stop.")
    print("To install it as an app: open that address in Chrome or Edge, then use "
          "the Install button in the address bar (Windows) or Menu > Add to Home screen (Android).")
    if not args.no_open:
        open_when_ready(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
