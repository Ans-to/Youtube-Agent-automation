"""The task queue as a use case, not as dashboard internals.

Everything here used to be a function inside ``dashboard.py`` - ``enqueue_task``,
``has_pending_tasks``, ``has_running_tasks``, ``attach_task_progress`` - reading
a module constant ``TASKS`` that pointed at the real ``tasks.json``. A test had
to patch that constant, and any code path that skipped the patch wrote to the
user's live queue.

:class:`TaskQueue` takes its path in the constructor. The dashboard creates one
at startup; tests create one in a temporary directory.

Durability rules (do not relax them):

* every write happens under :func:`queue_store.task_queue_lock`, so two
  processes cannot assign the same task id;
* status moves forward only through the states in :data:`STATUSES`;
* a task that was ``running`` when a process died is *not* replayed blindly -
  the orchestrator's recovery sweep decides, and this module only reports it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.errors import StorageError, TaskInputError
from app.infrastructure.jsonio import read_json
from queue_store import load_tasks, save_tasks, task_queue_lock

#: Every status a task may hold. ``queued`` is accepted on read for old records.
STATUSES = frozenset({"pending", "queued", "running", "completed", "failed", "needs_human_action"})
PENDING_STATUSES = frozenset({"pending", "queued"})

#: Workflows the CEO orchestrator knows how to run.
TASK_KINDS = frozenset({"plan", "draft", "summarize_workspace", "review_output", "youtube_package"})

MAX_TITLE_CHARS = 160
MAX_INPUT_CHARS = 16000
TASK_ID_PATTERN = re.compile(r"TASK-([0-9]{1,8})")


def _status(task: Any) -> str:
    return str(task.get("status", "pending")).lower() if isinstance(task, dict) else ""


def _tasks(raw: Any) -> list[dict]:
    """Coerce a decoded queue into records, discarding anything that is not one."""
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


@dataclass
class TaskQueue:
    """Reads and writes one ``tasks.json`` file."""

    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    # ------------------------------------------------------------------ reads
    def read(self) -> list[dict]:
        """All task records. A missing file is an empty queue; a corrupt one raises."""
        try:
            return load_tasks(self.path)
        except ValueError as exc:
            raise StorageError("The task queue is not readable.", detail=str(exc)[:200]) from exc

    def safe_read(self) -> list[dict]:
        """All task records, or an empty list. For rendering paths only."""
        try:
            return self.read()
        except (StorageError, OSError):
            return []

    def has_pending(self) -> bool:
        return any(_status(task) in PENDING_STATUSES for task in self.safe_read())

    def has_running(self) -> bool:
        """True when a record claims to be running - the recovery sweep reads this."""
        return any(_status(task) == "running" for task in self.safe_read())

    def find(self, task_id: str) -> dict | None:
        return next((task for task in self.safe_read() if task.get("id") == task_id), None)

    def counts(self, tasks: Iterable[dict] | None = None) -> dict[str, int]:
        records = list(self.safe_read() if tasks is None else tasks)
        counts = {
            key: sum(1 for task in records if _status(task) == key)
            for key in ("running", "completed", "failed", "needs_human_action")
        }
        counts["pending"] = sum(1 for task in records if _status(task) in PENDING_STATUSES)
        return counts

    def latest_starting_with(self, prefix: str, tasks: Iterable[dict] | None = None) -> dict | None:
        """Most recent task whose title starts with ``prefix`` (newest wins)."""
        records = list(self.safe_read() if tasks is None else tasks)
        return next(
            (task for task in reversed(records) if str(task.get("title", "")).startswith(prefix)),
            None,
        )

    # ----------------------------------------------------------------- writes
    def enqueue(self, title: str, kind: str, text: str, context_file: str = "") -> str:
        """Validate and persist one pending task. Returns its id.

        Raises :class:`TaskInputError` for anything a person could have typed
        wrong, and :class:`StorageError` when the queue cannot be written.
        """
        title = str(title or "").strip()[:MAX_TITLE_CHARS]
        text = str(text or "").strip()
        if not title or not text or len(text) > MAX_INPUT_CHARS or kind not in TASK_KINDS:
            raise TaskInputError(
                "Task instructions must contain 1-16,000 characters and use a supported workflow."
            )
        try:
            with task_queue_lock(self.path):
                tasks = self.read()
                task_id = self._next_id(tasks)
                tasks.append({
                    "id": task_id,
                    "title": title,
                    "kind": kind,
                    "input": text,
                    "status": "pending",
                    "error": "",
                    "research_status": "pending",
                    **({"context_file": context_file} if context_file else {}),
                })
                save_tasks(self.path, tasks)
        except (TimeoutError, OSError) as exc:
            raise StorageError(
                "Could not queue the task safely.", detail=type(exc).__name__
            ) from exc
        return task_id

    @staticmethod
    def _next_id(tasks: Iterable[dict]) -> str:
        numbers = [
            int(match.group(1))
            for task in tasks
            if (match := TASK_ID_PATTERN.fullmatch(str(task.get("id", ""))))
        ]
        return "TASK-%04d" % (max(numbers, default=0) + 1)

    # --------------------------------------------------------------- display
    def attach_progress(self, tasks: list[dict], pipeline_dir: Path | None = None) -> list[dict]:
        """Attach the orchestrator's saved stage progress to each task, in place.

        Progress is derived, never authoritative: a missing file simply means
        the task has not started, and an unreadable one must not break the page.
        """
        for task in tasks:
            task_id = str(task.get("id", ""))
            if not TASK_ID_PATTERN.fullmatch(task_id) or pipeline_dir is None:
                continue
            progress = read_json(
                Path(pipeline_dir) / ("task-" + task_id) / "pipeline-progress.json"
            )
            if isinstance(progress, dict):
                task["progress"] = progress
        return tasks


__all__ = [
    "TaskQueue",
    "STATUSES",
    "PENDING_STATUSES",
    "TASK_KINDS",
    "MAX_TITLE_CHARS",
    "MAX_INPUT_CHARS",
]
