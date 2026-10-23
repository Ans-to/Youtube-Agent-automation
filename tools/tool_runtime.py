#!/usr/bin/env python3
"""Sandboxed local tool layer: the actions an agent may take on a workspace.

The runtime is deliberately small and boring. It gives the orchestrator four
capabilities — list, read, write, and (opt-in) execute — with three guarantees:

1. **Containment.** Every path is canonicalized and must resolve inside one
   sandbox root. Absolute paths, drive-qualified paths, and `..` escapes are
   rejected, and symlinks are resolved before the containment check.
2. **Bounded cost.** Reads, writes, captured output, argument counts, and
   subprocess duration all have hard caps.
3. **Structured failure.** A tool never raises into the orchestrator; it returns
   ``{"status": "error", ...}`` so a failed step becomes a repairable observation.

Honest limitation: ``run_command`` is a **program allowlist with a confined
working directory**, not an operating-system sandbox. A deliberately hostile
program could still read paths outside the workspace. It is therefore disabled
unless the operator explicitly opts in, and the allowlist is intentionally tiny.

This module has no network access and imports nothing outside the standard
library plus ``tools.path_utils``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

try:  # Package import (tests, tools.run_quality_gate) and script import both work.
    from tools.path_utils import canonical_path, is_within, safe_relative_path
except ImportError:  # pragma: no cover - exercised when run as a standalone script
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from path_utils import canonical_path, is_within, safe_relative_path

MAX_READ_BYTES = 512_000
MAX_WRITE_BYTES = 512_000
MAX_OUTPUT_BYTES = 64_000
MAX_LIST_ENTRIES = 200
MAX_ARGS = 64
MAX_ARG_LENGTH = 2_000
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600

# Expanding this set is a security decision, not a convenience. Each program can
# execute arbitrary code from files inside the sandbox.
ALLOWED_PROGRAMS = ("python", "python3", "node")

# The child-process environment is shared with tools/test_fix.py so the two
# allowlists cannot drift apart; see tools/process_env.py.
try:
    from tools.process_env import clean_environment
except ImportError:  # script execution from tools/
    from process_env import clean_environment


class ToolError(ValueError):
    """A tool request was invalid or could not be completed safely."""


@dataclass(frozen=True)
class ToolSpec:
    """A declarative description the planner can reason about."""

    name: str
    summary: str
    side_effect: str
    schema: Mapping[str, Any]
    requires_exec: bool = False

    def prompt_entry(self) -> dict:
        return {
            "name": self.name,
            "summary": self.summary,
            "side_effect": self.side_effect,
            "input": dict(self.schema),
        }


def _type_name(value: Any) -> str:
    return {
        dict: "object", list: "array", str: "string", bool: "boolean",
        int: "integer", float: "number", type(None): "null",
    }.get(type(value), type(value).__name__)


def validate_arguments(value: Any, schema: Mapping[str, Any], path: str = "arguments") -> Any:
    """Validate against the small JSON-Schema subset this runtime supports.

    Supported: object/array/string/integer/boolean, ``required``,
    ``additionalProperties: false``, ``maxLength``, ``pattern``, ``minimum``,
    ``maximum``, ``maxItems``, and ``enum``. Anything else is ignored rather
    than silently mis-enforced.
    """
    if not isinstance(schema, Mapping):
        raise ToolError(f"{path}: tool schema is malformed")

    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ToolError(f"{path} must be an object, got {_type_name(value)}")
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise ToolError(f"{path}: tool schema properties are malformed")
        required = schema.get("required") or ()
        for key in required:
            if key not in value:
                raise ToolError(f"{path} is missing required field '{key}'")
        if schema.get("additionalProperties", False) is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ToolError(f"{path} has unsupported field(s): {', '.join(unknown)}")
        return {key: validate_arguments(item, properties[key], f"{path}.{key}") for key, item in value.items()}
    if expected == "array":
        if not isinstance(value, list):
            raise ToolError(f"{path} must be an array, got {_type_name(value)}")
        maximum = schema.get("maxItems")
        if isinstance(maximum, int) and len(value) > maximum:
            raise ToolError(f"{path} must contain at most {maximum} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            return [validate_arguments(item, item_schema, f"{path}[{index}]") for index, item in enumerate(value)]
        return list(value)
    if expected == "string":
        if not isinstance(value, str):
            raise ToolError(f"{path} must be a string, got {_type_name(value)}")
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError(f"{path} must be an integer, got {_type_name(value)}")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ToolError(f"{path} must be true or false, got {_type_name(value)}")
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ToolError(f"{path} must be a number, got {_type_name(value)}")

    enum = schema.get("enum")
    if isinstance(enum, (list, tuple)) and value not in enum:
        raise ToolError(f"{path} must be one of: {', '.join(str(item) for item in enum)}")
    if expected == "string":
        maximum_length = schema.get("maxLength")
        if isinstance(maximum_length, int) and len(value) > maximum_length:
            raise ToolError(f"{path} must be at most {maximum_length} characters")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, value):
            raise ToolError(f"{path} does not match the required pattern")
    if expected in {"integer", "number"}:
        minimum, maximum = schema.get("minimum"), schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise ToolError(f"{path} must be at least {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise ToolError(f"{path} must be at most {maximum}")
    return value


class WorkspaceSandbox:
    """One confined directory tree plus the policy for what may happen inside it."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        allow_exec: bool = False,
        max_write_bytes: int = MAX_WRITE_BYTES,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not 1 <= max_write_bytes <= MAX_WRITE_BYTES:
            raise ToolError(f"max_write_bytes must be between 1 and {MAX_WRITE_BYTES}")
        if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ToolError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
        self.root = canonical_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.allow_exec = bool(allow_exec)
        self.max_write_bytes = max_write_bytes
        self.timeout_seconds = timeout_seconds

    def resolve(self, value: str) -> Path:
        """Map a sandbox-relative path to a canonical absolute path, or refuse."""
        if not isinstance(value, str) or not value.strip():
            raise ToolError("path must be a non-empty string")
        if "\0" in value:
            raise ToolError("path must not contain a null byte")
        candidate = Path(value)
        if candidate.is_absolute() or candidate.drive or candidate.anchor:
            raise ToolError("absolute paths are not allowed; use a path relative to the workspace")
        target = canonical_path(self.root / value)
        if not is_within(target, self.root, allow_equal=True):
            raise ToolError("path escapes the workspace sandbox")
        return target

    def display(self, path: Path) -> str:
        try:
            return safe_relative_path(path, self.root).as_posix()
        except ValueError:
            return "<outside-workspace>"


def default_specs(*, allow_exec: bool = False, max_write_bytes: int = MAX_WRITE_BYTES) -> list[ToolSpec]:
    """The tools every registry starts with, described but not yet bound.

    Kept separate from ``ToolRegistry`` so a caller that only needs to *describe*
    the catalog — the task router, a prompt builder, documentation — can do so
    without creating a sandbox directory first. Registering and executing still
    happens only inside a registry bound to a confined root.
    """
    specs = [
        ToolSpec(
            name="list_files",
            summary="List files and directories inside the workspace.",
            side_effect="read",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 400, "default": "."},
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="read_file",
            summary="Read a UTF-8 text file from the workspace.",
            side_effect="read",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 400},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="write_file",
            summary="Create or replace a UTF-8 text file inside the workspace.",
            side_effect="write",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 400},
                    "content": {"type": "string", "maxLength": max_write_bytes},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        ),
    ]
    if allow_exec:
        specs.append(ToolSpec(
            name="run_command",
            summary=(
                "Run an allowlisted interpreter inside the workspace and capture output. "
                "Programs: " + ", ".join(ALLOWED_PROGRAMS) + ". No shell."
            ),
            side_effect="execute",
            requires_exec=True,
            schema={
                "type": "object",
                "properties": {
                    "program": {"type": "string", "enum": list(ALLOWED_PROGRAMS)},
                    "args": {
                        "type": "array",
                        "maxItems": MAX_ARGS,
                        "items": {"type": "string", "maxLength": MAX_ARG_LENGTH},
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TIMEOUT_SECONDS,
                    },
                },
                "required": ["program"],
                "additionalProperties": False,
            },
        ))
    return specs


def default_tool_catalog(*, allow_exec: bool = False) -> list[dict]:
    """Prompt-ready catalog of the default tool set, without a sandbox."""
    return [spec.prompt_entry() for spec in default_specs(allow_exec=allow_exec)]


class ToolRegistry:
    """Register tool specs, describe them to a planner, and execute them safely."""

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self.sandbox = sandbox
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict], dict]] = {}
        self._register_defaults()

    # -- registration -----------------------------------------------------
    def register(self, spec: ToolSpec, handler: Callable[[dict], dict]) -> None:
        if spec.name in self._specs:
            raise ToolError(f"tool '{spec.name}' is already registered")
        if not spec.name or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", spec.name):
            raise ToolError(f"invalid tool name '{spec.name}'")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def prompt_catalog(self) -> list[dict]:
        """Compact catalog for injection into a planner prompt."""
        return [spec.prompt_entry() for spec in self.specs()]

    def catalog_json(self, *, max_chars: int = 6_000) -> str:
        encoded = json.dumps(self.prompt_catalog(), ensure_ascii=False, separators=(",", ":"))
        return encoded[:max_chars]

    # -- execution --------------------------------------------------------
    def execute(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict:
        """Run a tool. Never raises: failures become observations a planner can fix."""
        spec = self._specs.get(name)
        if spec is None:
            return {
                "tool": str(name)[:60],
                "status": "error",
                "error": "unknown tool",
                "available_tools": sorted(self._specs),
            }
        try:
            validated = validate_arguments(dict(arguments or {}), spec.schema)
        except ToolError as exc:
            return {"tool": name, "status": "error", "error": str(exc)}
        try:
            result = self._handlers[name](validated)
        except ToolError as exc:
            return {"tool": name, "status": "error", "error": str(exc)}
        except subprocess.TimeoutExpired:
            return {"tool": name, "status": "error", "error": "command timed out"}
        except (OSError, UnicodeError) as exc:
            return {"tool": name, "status": "error", "error": f"{type(exc).__name__}: operation failed"}
        if not isinstance(result, dict):
            return {"tool": name, "status": "error", "error": "tool returned an unsupported result type"}
        return {"tool": name, "status": "ok", **result}

    # -- built-in tools ---------------------------------------------------
    def _register_defaults(self) -> None:
        """Bind the declarative specs to their handlers.

        The specs live in :func:`default_specs` so that describing the catalog
        and enforcing it cannot drift apart: the registry registers exactly the
        specs a prompt was built from.
        """
        handlers: dict[str, Callable[[dict], dict]] = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "run_command": self._run_command,
        }
        for spec in default_specs(allow_exec=self.sandbox.allow_exec,
                                  max_write_bytes=self.sandbox.max_write_bytes):
            self.register(spec, handlers[spec.name])

    def _list_files(self, arguments: dict) -> dict:
        target = self.sandbox.resolve(arguments.get("path") or ".")
        if not target.exists():
            raise ToolError("path does not exist")
        if not target.is_dir():
            raise ToolError("path is not a directory")
        entries = []
        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if len(entries) >= MAX_LIST_ENTRIES:
                break
            try:
                size = child.stat().st_size if child.is_file() else None
            except OSError:
                size = None
            entries.append({
                "path": self.sandbox.display(child),
                "type": "directory" if child.is_dir() else "file",
                "size": size,
            })
        return {
            "path": self.sandbox.display(target),
            "entries": entries,
            "truncated": len(entries) >= MAX_LIST_ENTRIES,
        }

    def _read_file(self, arguments: dict) -> dict:
        target = self.sandbox.resolve(arguments["path"])
        if not target.exists():
            raise ToolError("file does not exist")
        if not target.is_file():
            raise ToolError("path is not a file")
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise ToolError(f"file is larger than the {MAX_READ_BYTES}-byte read limit")
        text = target.read_text(encoding="utf-8", errors="replace")
        return {"path": self.sandbox.display(target), "content": text, "bytes": size}

    def _write_file(self, arguments: dict) -> dict:
        target = self.sandbox.resolve(arguments["path"])
        content = arguments["content"]
        encoded = content.encode("utf-8")
        if len(encoded) > self.sandbox.max_write_bytes:
            raise ToolError(f"content exceeds the {self.sandbox.max_write_bytes}-byte write limit")
        if target.exists() and target.is_dir():
            raise ToolError("path is a directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        created = not target.exists()
        target.write_text(content, encoding="utf-8", newline="\n")
        return {
            "path": self.sandbox.display(target),
            "bytes_written": len(encoded),
            "created": created,
        }

    def _run_command(self, arguments: dict) -> dict:
        if not self.sandbox.allow_exec:
            raise ToolError("command execution is disabled for this workspace")
        program = arguments["program"]
        resolved = shutil.which(program)
        if not resolved:
            raise ToolError(f"program '{program}' is not installed on this machine")
        args = list(arguments.get("args") or [])
        timeout = arguments.get("timeout_seconds") or self.sandbox.timeout_seconds
        # argv list, no shell, program already allowlisted and resolved to a path.
        completed = subprocess.run(  # noqa: S603
            [resolved, *args],
            cwd=str(self.sandbox.root),
            env=self._clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        stderr = completed.stderr[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return {
            "program": program,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": len(completed.stdout) > MAX_OUTPUT_BYTES,
            "stderr_truncated": len(completed.stderr) > MAX_OUTPUT_BYTES,
        }

    def _clean_environment(self) -> dict:
        return clean_environment()


def task_sandbox(
    workspace_root: str | os.PathLike[str],
    task_id: str,
    *,
    allow_exec: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> WorkspaceSandbox:
    """Create a per-task sandbox under ``<workspace_root>/projects/<slug>``."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(task_id).lower()).strip("-")[:48] or "task"
    base = canonical_path(workspace_root)
    sandbox = WorkspaceSandbox(base / "projects" / slug, allow_exec=allow_exec, timeout_seconds=timeout_seconds)
    if not is_within(sandbox.root, base, allow_equal=False):
        raise ToolError("task sandbox escapes the workspace root")
    return sandbox


def build_registry(
    workspace_root: str | os.PathLike[str],
    task_id: str,
    *,
    allow_exec: bool | None = None,
) -> ToolRegistry:
    """Convenience factory used by orchestration code and tests."""
    if allow_exec is None:
        allow_exec = os.environ.get("AGENT_HQ_ALLOW_EXEC", "").strip().lower() in {"1", "true", "yes", "on"}
    return ToolRegistry(task_sandbox(workspace_root, task_id, allow_exec=allow_exec))


def main() -> int:
    """Print the catalog a planner would receive. Creates nothing in the repository."""
    import tempfile

    allow_exec = os.environ.get("AGENT_HQ_ALLOW_EXEC", "").strip().lower() in {"1", "true", "yes", "on"}
    with tempfile.TemporaryDirectory() as directory:
        registry = ToolRegistry(WorkspaceSandbox(directory, allow_exec=allow_exec))
        print(json.dumps(registry.prompt_catalog(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
