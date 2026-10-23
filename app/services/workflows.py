"""Background work: the queue worker and the CEO pipeline.

Both used to be closures inside ``dashboard.py`` with the same three-part dance
- claim the command core, spawn a thread, release and maybe restart - written
twice with slightly different recovery rules. They are one concern: work that
outlives an HTTP request.

The rules, in one place:

1. **One exclusive workflow at a time.** Claimed through
   :class:`app.state.RunState`, released in ``finally``.
2. **A crash must not wedge the app.** The release path always runs, so a
   failing subprocess cannot leave the core permanently claimed.
3. **Queue resumption happens once.** When a workflow releases the core and
   tasks are waiting, the worker is started exactly once, from one guarded path.
4. **Nothing claims a task finished.** This layer starts and stops processes;
   the orchestrator writes task status to the queue.

Every subprocess is injected (``runner``), so tests exercise the state machine
without spawning anything.
"""
from __future__ import annotations

import contextlib
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from app.errors import WorkflowBusyError, describe
from app.paths import ProjectPaths
from app.services.tasks import TaskQueue
from app.state import WORKFLOW_CEO_PIPELINE, WORKFLOW_TASK_RUNNER, RunState

#: A single worker session drains at most this many cycles, then stops and
#: leaves anything still queued for the next session. An unbounded loop in a
#: thread with no owner is how a dashboard keeps working after you close it.
MAX_CYCLES = 100

#: Seconds a single queue cycle may take before it is killed.
CYCLE_TIMEOUT_SECONDS = 3600

#: Seconds a full CEO pipeline may take.
PIPELINE_TIMEOUT_SECONDS = 7200

#: ``runner(args, log_stream) -> returncode`` - injectable for tests.
ProcessRunner = Callable[[list[str], TextIO], int]


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def subprocess_runner(timeout: int, cwd: Path) -> ProcessRunner:
    """The real runner: run one command, stream its output to the log."""

    def run(command: list[str], log: TextIO) -> int:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        return result.returncode

    return run


@contextlib.contextmanager
def open_log(paths: ProjectPaths, name: str):
    """An open log stream, or a sink that swallows output if logging fails.

    The subprocess must still run when ``logs/`` is not writable; losing the log
    is annoying, losing the work is not acceptable.
    """
    stream = None
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        stream = (paths.logs / name).open("a", encoding="utf-8")
    except OSError as exc:
        print("warning: cannot open %s (%s)" % (name, describe(exc)), file=sys.stderr)
    try:
        yield stream if stream is not None else _NullWriter()
    finally:
        if stream is not None:
            stream.close()


class _NullWriter:
    """A file-like sink used when the log cannot be opened."""

    def write(self, message: str) -> int:  # noqa: D401 - file protocol
        return len(message or "")

    def flush(self) -> None:
        return None


class LogWriter:
    """Append-only log file that never raises on a locked or full disk.

    Logging is diagnostics. A machine with a read-only ``logs/`` directory must
    still be able to run the work, so a logging failure is reported once to
    stderr and then ignored.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._warned = False

    def write(self, message: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write("[%s] %s\n" % (_stamp(), message.rstrip()))
        except OSError as exc:
            if not self._warned:
                self._warned = True
                print("warning: cannot write %s (%s)" % (self.path.name, describe(exc)),
                      file=sys.stderr)


class TaskWorker:
    """Drains the task queue by running ``agent.py --once`` in cycles."""

    def __init__(
        self,
        *,
        paths: ProjectPaths,
        state: RunState,
        queue: TaskQueue,
        runner: ProcessRunner | None = None,
        python: str | None = None,
        agent_script: Path | None = None,
        max_cycles: int = MAX_CYCLES,
        on_release: Callable[[], None] | None = None,
    ) -> None:
        self.paths = paths
        self.state = state
        self.queue = queue
        self.python = python or sys.executable
        self.agent_script = agent_script or (paths.root / "agent.py")
        self.max_cycles = max_cycles
        self.on_release = on_release
        self.runner = runner or subprocess_runner(CYCLE_TIMEOUT_SECONDS, paths.root)
        self.log = LogWriter(paths.logs / "dashboard.log")
        self._guard = threading.Lock()

    # ------------------------------------------------------------------ public
    def start(self) -> tuple[bool, str]:
        """Start the worker if it is not already running. Returns (started, holder)."""
        claimed, active = self.state.claim_workflow(WORKFLOW_TASK_RUNNER)
        if not claimed:
            return False, active
        with self._guard:
            if not self.state.begin_worker():
                # Someone else started it between the claim and the lock.
                self.state.release_workflow(WORKFLOW_TASK_RUNNER)
                return True, ""
        try:
            threading.Thread(
                target=self._run, daemon=True, name="agent-hq-queue-worker"
            ).start()
        except RuntimeError:
            self.state.end_worker()
            self.state.release_workflow(WORKFLOW_TASK_RUNNER)
            raise
        return True, ""

    def is_running(self) -> bool:
        return self.state.snapshot()["worker_running"]

    # ------------------------------------------------------------------ internals
    def _run(self) -> None:
        try:
            for cycle in range(self.max_cycles):
                # Cycle zero always runs: the orchestrator uses that sweep to
                # recover tasks left "running" by a killed process, even when
                # the queue looks empty.
                if cycle and not self.queue.has_pending():
                    break
                if not self._cycle(cycle):
                    break
            else:
                if self.queue.has_pending():
                    self.log.write(
                        "Auto queue worker stopped after %d cycles; remaining tasks stay "
                        "queued for safety." % self.max_cycles
                    )
        finally:
            self.state.end_worker()
            self.state.release_workflow(WORKFLOW_TASK_RUNNER)
            self._resume_if_pending()

    def _cycle(self, cycle: int) -> bool:
        self.log.write("Auto queue worker cycle %d started" % (cycle + 1))
        try:
            with self._log_stream("dashboard.log") as log:
                code = self.runner([self.python, str(self.agent_script), "--once"], log)
        except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
            self.log.write("Auto queue worker error: " + describe(exc))
            return False
        self.log.write("Auto queue worker exit code: %d" % code)
        return True

    def _log_stream(self, name: str):
        return open_log(self.paths, name)

    def _resume_if_pending(self) -> None:
        if self.on_release is not None:
            self.on_release()
            return
        if self.queue.has_pending():
            self.start()


class PipelineRunner:
    """Runs one CEO pipeline in the background and owns its claim."""

    def __init__(
        self,
        *,
        paths: ProjectPaths,
        state: RunState,
        queue: TaskQueue,
        runner: ProcessRunner | None = None,
        python: str | None = None,
        orchestrator: Path | None = None,
        on_release: Callable[[], None] | None = None,
    ) -> None:
        self.paths = paths
        self.state = state
        self.queue = queue
        self.python = python or sys.executable
        self.orchestrator = orchestrator or (paths.root / "agents" / "orchestrate.py")
        self.runner = runner or subprocess_runner(PIPELINE_TIMEOUT_SECONDS, paths.root)
        self.on_release = on_release
        self.log = LogWriter(paths.logs / "pipeline.log")

    def start(self, task: str, context_file: str = "") -> str:
        """Start a run and return its output directory.

        Raises :class:`WorkflowBusyError` when another workflow holds the core
        or a pipeline is already in flight.
        """
        claimed, active = self.state.claim_workflow(WORKFLOW_CEO_PIPELINE)
        if not claimed:
            raise WorkflowBusyError("Another workflow is already running.", active=active)
        run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        output = self.paths.pipeline_dir / ("run-" + run_id)
        if not self.state.begin_pipeline(str(output)):
            self.state.release_workflow(WORKFLOW_CEO_PIPELINE)
            raise WorkflowBusyError("A CEO pipeline is already running.")
        command = [self.python, str(self.orchestrator), "--task", task, "--out", str(output)]
        if context_file:
            command.extend(["--context-file", context_file])
        try:
            threading.Thread(
                target=self._run, args=(command,), daemon=True, name="agent-hq-pipeline"
            ).start()
        except RuntimeError:
            self.state.end_pipeline()
            self.state.release_workflow(WORKFLOW_CEO_PIPELINE)
            raise
        return self.paths.relative(output)

    def _log_stream(self, name: str):
        return open_log(self.paths, name)

    def _run(self, command: list[str]) -> None:
        self.log.write("CEO pipeline started; delegation owner: AGENT-01")
        try:
            with self._log_stream("pipeline.log") as log:
                code = self.runner(command, log)
            self.log.write("Pipeline exit code: %d" % code)
        except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
            self.log.write("Pipeline error: " + describe(exc))
        finally:
            self.state.end_pipeline()
            self.state.release_workflow(WORKFLOW_CEO_PIPELINE)
            if self.on_release is not None:
                self.on_release()
            elif self.queue.has_pending():
                TaskWorker(paths=self.paths, state=self.state, queue=self.queue).start()


class WorkflowCoordinator:
    """The single object the UI talks to when it needs background work.

    Holds the two runners and the resume rule, so the HTTP layer never touches
    a thread or a lock.
    """

    def __init__(self, *, paths: ProjectPaths, state: RunState, queue: TaskQueue,
                 runner: ProcessRunner | None = None) -> None:
        self.paths = paths
        self.state = state
        self.queue = queue
        self.worker = TaskWorker(
            paths=paths, state=state, queue=queue, runner=runner, on_release=self.resume
        )
        self.pipeline = PipelineRunner(
            paths=paths, state=state, queue=queue, runner=runner, on_release=self.resume
        )

    def start_queue_worker(self) -> tuple[bool, str]:
        return self.worker.start()

    def start_pipeline(self, task: str, context_file: str = "") -> str:
        return self.pipeline.start(task, context_file)

    def resume(self) -> None:
        """Restart the queue worker if pending work remains and the core is free."""
        if self.state.snapshot()["active_workflow"]:
            return
        if self.queue.has_pending():
            self.worker.start()

    def release(self, name: str) -> bool:
        """Release a claim held by ``name`` and resume queued work."""
        released = self.state.release_workflow(name)
        if released:
            self.resume()
        return released


__all__ = [
    "TaskWorker",
    "PipelineRunner",
    "WorkflowCoordinator",
    "subprocess_runner",
    "MAX_CYCLES",
    "CYCLE_TIMEOUT_SECONDS",
    "PIPELINE_TIMEOUT_SECONDS",
]
