"""Runtime state in one place, behind one lock.

The dashboard used to hold twelve module globals - ``RUNNING``, ``RUNNING``'s
three siblings, ``ACTIVE_WORKFLOW``, ``PIPELINE_LAST_OUTPUT`` and so on - each
written by a thread inside an ``if`` and read by the request handler with no
lock at all. Two consequences, both real:

* a reader could see ``pipeline_running=True`` with the old output path;
* four of those globals (``VIDEO_*``, ``PRODUCT_*``, ``TRAINING_*``) were never
  written by anything. They existed only to be read, so the UI reported "not
  running" from a variable that could not become "running".

:class:`RunState` replaces all of them. It owns:

* **which exclusive workflow holds the command core** - a claim, not a boolean,
  because the name is what the "another workflow is running" message needs;
* **the worker and pipeline flags**, updated together with the fields that
  explain them;
* **a consistent snapshot** for rendering, taken under the lock.

It is in-memory by design. The durable truth about work is the task file
(``app.services.tasks``); nothing here survives a restart, and nothing here is
allowed to *claim* that a task finished.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: Workflow names. Constants, so a typo cannot release the wrong claim.
WORKFLOW_TASK_RUNNER = "task runner"
WORKFLOW_CEO_PIPELINE = "CEO command pipeline"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class RunState:
    """Thread-safe owner of the application's volatile run flags."""

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    worker_running: bool = False
    active_workflow: str = ""
    workflow_since: str = ""
    pipeline_running: bool = False
    pipeline_output: str = ""

    # ------------------------------------------------------- exclusive claims
    def claim_workflow(self, name: str) -> tuple[bool, str]:
        """Try to become the one exclusive workflow. Returns (claimed, holder).

        A workflow that already holds the core may claim it again - that is what
        makes a double-clicked "run" button idempotent instead of an error.
        """
        with self._lock:
            if self.active_workflow:
                return (self.active_workflow == name, self.active_workflow)
            self.active_workflow = name
            self.workflow_since = _now()
            return True, ""

    def release_workflow(self, name: str) -> bool:
        """Give the core back, but only if this workflow is the holder."""
        with self._lock:
            if self.active_workflow != name:
                return False
            self.active_workflow = ""
            self.workflow_since = ""
            return True

    def holds_workflow(self, name: str) -> bool:
        with self._lock:
            return self.active_workflow == name

    # -------------------------------------------------------------- the worker
    def begin_worker(self) -> bool:
        """Mark the queue worker as running. False if it already was."""
        with self._lock:
            if self.worker_running:
                return False
            self.worker_running = True
            return True

    def end_worker(self) -> None:
        with self._lock:
            self.worker_running = False

    # ------------------------------------------------------------ the pipeline
    def begin_pipeline(self, output_dir: str) -> bool:
        """Start a CEO pipeline run. False when one is already running."""
        with self._lock:
            if self.pipeline_running:
                return False
            self.pipeline_running = True
            self.pipeline_output = str(output_dir)
            return True

    def end_pipeline(self) -> None:
        with self._lock:
            self.pipeline_running = False

    # ------------------------------------------------------------------ reads
    def snapshot(self) -> dict[str, Any]:
        """A consistent copy for rendering. Never hand out live references."""
        with self._lock:
            return {
                "worker_running": self.worker_running,
                "active_workflow": self.active_workflow,
                "workflow_since": self.workflow_since,
                "pipeline_running": self.pipeline_running,
                "pipeline_output": self.pipeline_output,
            }

    def reset(self) -> None:
        """Return to the initial state. Only tests and a fresh process use this."""
        with self._lock:
            self.worker_running = False
            self.active_workflow = ""
            self.workflow_since = ""
            self.pipeline_running = False
            self.pipeline_output = ""


__all__ = ["RunState", "WORKFLOW_TASK_RUNNER", "WORKFLOW_CEO_PIPELINE"]
