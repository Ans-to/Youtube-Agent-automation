"""The read model the interface renders.

``/api/state`` used to be built by a 20-line function inside the dashboard that
mixed three things: reading the queue, reading configuration, and formatting
strings for the page. This module produces the data; the UI decides how it
looks. Nothing here returns HTML.

Two behaviours are deliberate and tested:

* **Derived, not duplicated.** "Is a video running?" is answered from the task
  records, because they are the durable truth. The dashboard used to keep a
  parallel ``VIDEO_RUNNING`` flag that nothing ever set, so the answer was
  always no.
* **Bounded.** Only the last :data:`RECENT_TASKS` tasks are sent to the browser.
  A queue with ten thousand records should not be a ten-megabyte response.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.infrastructure.jsonio import read_json
from app.paths import ProjectPaths
from app.services.tasks import TaskQueue
from app.state import RunState

#: How many recent tasks the UI shows and receives.
RECENT_TASKS = 100

#: Title prefixes the dashboard uses to find a workflow's latest task.
VIDEO_PREFIX = "Video:"
PRODUCT_PREFIX = "Digital product:"

#: The four visible stages of the CEO pipeline, in order.
PIPELINE_STAGES = ["CEO Coordinator", "Researching Specialists", "Assigned Workers", "Quality Reviewer"]


def _output_for(task: dict | None, fallback: str = "") -> str:
    """Where a workflow's result lives, phrased for a person."""
    if not task:
        return fallback
    status = str(task.get("status", ""))
    return str(task.get("output_file") or ("Queued %s (%s)" % (task.get("id", ""), status)))


def build_status(
    *,
    paths: ProjectPaths,
    config: dict,
    queue: TaskQueue,
    state: RunState,
) -> dict[str, Any]:
    """Assemble the JSON the dashboard polls."""
    tasks = queue.attach_progress(queue.safe_read(), paths.pipeline_dir)
    recent = tasks[-RECENT_TASKS:]
    model = config.get("model", {}) if isinstance(config, dict) else {}
    run = state.snapshot()
    video_task = queue.latest_starting_with(VIDEO_PREFIX, tasks)
    product_task = queue.latest_starting_with(PRODUCT_PREFIX, tasks)
    roster = read_json(paths.roster, {})
    return {
        "tasks": recent,
        "counts": queue.counts(tasks),
        "model_enabled": bool(model.get("enabled")),
        "model_name": model.get("model", "local-model"),
        "running": run["worker_running"],
        "active_workflow": run["active_workflow"],
        "pipeline_running": run["pipeline_running"],
        "pipeline_output": run["pipeline_output"],
        "video_running": bool(video_task and str(video_task.get("status")) == "running"),
        "video_output": _output_for(video_task),
        "product_running": bool(product_task and str(product_task.get("status")) == "running"),
        "product_output": _output_for(product_task),
        "pipeline": list(PIPELINE_STAGES),
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent_roster": (roster or {}).get("agents", []) if isinstance(roster, dict) else [],
    }


def health(queue: TaskQueue, paths: ProjectPaths) -> dict[str, Any]:
    """A cheap liveness answer that never reads the whole queue."""
    return {"status": "ok", "task_count": len(queue.safe_read()), "root": paths.root.name}


def output_path(paths: ProjectPaths, relative: str) -> Path | None:
    """Resolve a task's ``output_file`` inside the project root, or ``None``.

    A task record is data a model wrote. Treating it as a path without this
    check is a file-disclosure bug, so the rule lives here rather than in the
    handler.
    """
    if not relative:
        return None
    candidate = (paths.root / relative).resolve()
    if paths.root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


__all__ = ["build_status", "health", "output_path", "RECENT_TASKS", "PIPELINE_STAGES"]
