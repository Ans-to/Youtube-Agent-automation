"""Every filesystem location, declared once.

Twelve modules used to build their own paths with
``BASE = Path(__file__).resolve().parent`` followed by ``BASE / "tasks.json"``.
That is how a test ended up patching ``dashboard.TASKS`` and then watching the
worker write to the real queue: the path was a module constant, copied.

:class:`ProjectPaths` is a value object. Pass it to a service instead of letting
the service guess, and a test can point the whole application at a temporary
directory by constructing one.

    paths = ProjectPaths(root=tmp_path)
    queue = TaskQueue(paths.tasks)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

#: Point this at another checkout to run the app against a copy. Relative paths
#: are resolved from the current working directory.
ROOT_ENV_VAR = "AGENT_HQ_HOME"

#: The repository root, two levels up from this file (``app/paths.py``).
_DEFAULT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProjectPaths:
    """Immutable set of locations the application reads and writes."""

    root: Path = _DEFAULT_ROOT

    def __post_init__(self) -> None:
        # normalise once: every other property is derived from root
        object.__setattr__(self, "root", Path(self.root).resolve())

    @classmethod
    def discover(
        cls, root: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None
    ) -> "ProjectPaths":
        """Build from an argument, else ``$AGENT_HQ_HOME``, else this checkout."""
        env = os.environ if environ is None else environ
        chosen = root or env.get(ROOT_ENV_VAR) or _DEFAULT_ROOT
        return cls(Path(chosen).expanduser())

    # ---------------------------------------------------------------- inputs
    @property
    def config(self) -> Path:
        """Private runtime settings. Optional; never committed."""
        return self.root / "config.json"

    @property
    def config_example(self) -> Path:
        """The committed, safe template for :attr:`config`."""
        return self.root / "config.example.json"

    @property
    def env_file(self) -> Path:
        """Optional ``.env``; real environment variables win over it."""
        return self.root / ".env"

    @property
    def tasks(self) -> Path:
        """The durable task queue - the single source of truth for work."""
        return self.root / "tasks.json"

    @property
    def agents(self) -> Path:
        return self.root / "agents"

    @property
    def roster(self) -> Path:
        return self.agents / "roster.json"

    @property
    def web(self) -> Path:
        """Repository-owned UI assets. Served by fixed name only."""
        return self.root / "web"

    @property
    def deck(self) -> Path:
        return self.web / "deck.html"

    # --------------------------------------------------------------- outputs
    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def pipeline_dir(self) -> Path:
        """Where the CEO pipeline writes one directory per run."""
        return self.workspace / "orchestration"

    def task_progress(self, task_id: str) -> Path:
        """Saved stage progress for one task, written by the orchestrator."""
        return self.pipeline_dir / ("task-" + task_id) / "pipeline-progress.json"

    # --------------------------------------------------------------- helpers
    def relative(self, path: str | os.PathLike[str]) -> str:
        """Path relative to the project root, or the original string if outside.

        The dashboard shows this in the UI and stores it in task records, so it
        must never raise for a path a user typed.
        """
        candidate = Path(path)
        try:
            return str(candidate.resolve().relative_to(self.root))
        except (OSError, ValueError):
            return str(path)

    def ensure_runtime_dirs(self) -> None:
        """Create the writable directories the app expects to exist."""
        for directory in (self.logs, self.outputs, self.workspace):
            directory.mkdir(parents=True, exist_ok=True)


def default_paths() -> ProjectPaths:
    """The paths for the running installation (honours ``$AGENT_HQ_HOME``)."""
    return ProjectPaths.discover()


__all__ = ["ProjectPaths", "default_paths", "ROOT_ENV_VAR"]
