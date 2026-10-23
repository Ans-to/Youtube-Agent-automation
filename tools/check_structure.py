#!/usr/bin/env python3
"""Enforce the project's structure rules, so messiness fails a check.

``tools/check_invariants.py`` guards the product rules (no paid services, no
secrets, loopback only). This guards the *codebase* rules in
``docs/ARCHITECTURE.md`` - the ones that quietly rot because nothing notices:

``S1 LAYER``
    ``app/`` must not import the UI, and ``ui/`` must not import a workflow's
    internals. Dependency direction is a one-way street; an import in the wrong
    direction is how a "business layer" stops being one.

``S2 STATE``
    No new module-level run flags. ``dashboard.py`` carries 12 of them once and
    four were never written; the replacement is ``app.state.RunState``.

``S3 DUP``
    No copied function bodies. Two functions with the same normalized AST and
    eight or more statements are a copy-paste, not a coincidence. This is the
    rule that would have failed on the three copies of ``post_local_model``.

``S4 NAME``
    Files, classes, functions and constants follow the documented conventions.

``S5 ROOT``
    The repository root stays a short list of entry points. A new top-level
    script needs to be added here *and* documented, on purpose.

``S6 SIZE``
    An entry point that grows past its budget is reported: ``dashboard.py`` was
    563 lines and is the reason this file exists.

Run it from the repository root, from CI, or from ``tools/run_quality_gate.py``::

    python tools/check_structure.py
    python tools/check_structure.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Directories that hold first-party Python.
SOURCE_DIRS = ("app", "ui", "agents", "tools", "video_studio", "bridge", "product_studio", "scripts")

#: Directories that are never scanned.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", ".venv-piper-urdu", "venv",
    "build", "dist", "outputs", "workspace", "tests", ".mypy_cache", ".pytest_cache",
}

#: Files allowed at the repository root. Each is a documented entry point or a
#: shared boundary module. Adding to this list is a deliberate act.
ROOT_PYTHON_ALLOWED = {
    "agent.py",          # queue worker entry point
    "dashboard.py",      # HTTP/UI entry point
    "app_config.py",     # configuration boundary (documented in ARCHITECTURE.md)
    "queue_store.py",    # cross-process queue locking
    "quality_outputs.py",  # offline fallback artifact templates
}

#: Line budget per entry point. Exceeding it is reported, not fatal: the number
#: is there to make growth visible in review rather than to ban a large file.
ENTRY_POINT_BUDGET = {
    "dashboard.py": 300,
    "agent.py": 520,
    "queue_store.py": 160,
    "app_config.py": 260,
    "quality_outputs.py": 220,
}

#: Copies that are deliberate. Each entry is (module, function) -> reason.
#: Keep this list short; "it was easier" is not a reason.
ALLOWED_DUPLICATES: dict[tuple[str, str], str] = {
    ("video_studio/voice_mix.py", "read_wav"): "audio helper the mix stage keeps dependency-free",
    ("video_studio/voiceover.py", "read_wav"): "same helper; different module, no shared audio package yet",
}

#: Module-level names that look like run flags. Prevents the old dashboard shape
#: from coming back: ``RUNNING = False`` next to the code that reads it.
RUN_FLAG = re.compile(r"^(?:[A-Z_]*(?:RUNNING|ACTIVE_WORKFLOW|LAST_OUTPUT|LOCK)[A-Z_]*)$")
RUN_FLAG_ALLOWED = {
    ("app/services/workflows.py", "MAX_CYCLES"),
    ("app/services/workflows.py", "PIPELINE_TIMEOUT_SECONDS"),
    ("app/services/workflows.py", "CYCLE_TIMEOUT_SECONDS"),
}

SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*$")
CONSTANT = re.compile(r"^_{0,2}[A-Z][A-Z0-9_]*$")
PASCAL = re.compile(r"^_*[A-Z][A-Za-z0-9]*$")

#: Functions that are legitimately small and repeated (protocol methods).
IGNORED_FUNCTIONS = {"__init__", "__repr__", "__str__", "__enter__", "__exit__", "as_dict"}

#: A duplicate must be at least this many statements to be reported.
DUPLICATE_MIN_STATEMENTS = 8


@dataclass
class Finding:
    rule: str
    path: str
    line: int
    message: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "path": self.path, "line": self.line, "message": self.message}

    def __str__(self) -> str:
        return f"{self.rule} {self.path}:{self.line} {self.message}"


def as_posix(path: Path | str) -> str:
    """A path as ``tools/two.py`` on every platform.

    ``str(Path(...))`` is ``tools\\two.py`` on Windows, and every rule here
    compares or reports path strings. The backslash is replaced explicitly as
    well: on POSIX a backslash is an ordinary filename character, so
    ``Path(...).as_posix()`` alone would leave a Windows-style path untouched
    when the tests run on Linux.
    """
    return Path(path).as_posix().replace("\\", "/")


def iter_python_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        if relative.parts and relative.parts[0] == "tests":
            continue
        files.append(relative)
    return files


def parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------- rules
def check_layer(relative: str, tree: ast.Module) -> list[Finding]:
    relative = as_posix(relative)
    """S1 - app/ must not depend on the UI."""
    findings: list[Finding] = []
    if not relative.startswith("app/"):
        return findings
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
        for module in modules:
            if module.split(".")[0] in {"ui", "web", "dashboard"}:
                findings.append(Finding(
                    "S1", relative, node.lineno,
                    f"app/ imports the presentation layer ({module}); invert the dependency "
                    "or move the value into app.services",
                ))
    return findings


def check_state(relative: str, tree: ast.Module) -> list[Finding]:
    relative = as_posix(relative)
    """S2 - no module-level mutable run flags."""
    findings: list[Finding] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name) or not RUN_FLAG.match(target.id):
                continue
            if (relative, target.id) in RUN_FLAG_ALLOWED:
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, (bool, str, type(None))):
                findings.append(Finding(
                    "S2", relative, node.lineno,
                    f"module-level run flag {target.id}; use app.state.RunState so one lock "
                    "owns every flag",
                ))
    return findings


def _normalized(function: ast.AST) -> str:
    """A stable fingerprint of a function body, ignoring docstrings and comments."""
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    clone = ast.Module(body=body, type_ignores=[])
    return ast.dump(clone, annotate_fields=False, include_attributes=False)


def _statement_count(function: ast.AST) -> int:
    return sum(1 for node in ast.walk(function) if isinstance(node, ast.stmt))


def collect_function_fingerprints(
    files: list[Path], root: Path = ROOT
) -> dict[str, list[tuple[str, int, str]]]:
    fingerprints: dict[str, list[tuple[str, int, str]]] = {}
    for relative in files:
        tree = parse(root / relative)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in IGNORED_FUNCTIONS:
                continue
            if _statement_count(node) < DUPLICATE_MIN_STATEMENTS:
                continue
            fingerprints.setdefault(_normalized(node), []).append(
                (as_posix(relative), node.lineno, node.name)
            )
    return fingerprints


def check_duplicates(files: list[Path], root: Path = ROOT) -> list[Finding]:
    """S3 - no copied function bodies."""
    findings: list[Finding] = []
    for occurrences in collect_function_fingerprints(files, root).values():
        if len(occurrences) < 2:
            continue
        # A copy is reported once, at every site after the first.
        first = occurrences[0]
        for path, line, name in occurrences[1:]:
            if (path, name) in ALLOWED_DUPLICATES or (first[0], first[2]) in ALLOWED_DUPLICATES:
                continue
            findings.append(Finding(
                "S3", path, line,
                f"{name}() is a copy of {first[2]}() in {first[0]}:{first[1]}; "
                "move it to a shared module",
            ))
    return findings


def check_names(relative: str, tree: ast.Module) -> list[Finding]:
    relative = as_posix(relative)
    """S4 - naming conventions."""
    findings: list[Finding] = []
    stem = Path(relative).stem
    if not SNAKE.match(stem):
        findings.append(Finding("S4", relative, 1, f"module name {stem!r} is not snake_case"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not PASCAL.match(node.name):
            findings.append(Finding("S4", relative, node.lineno,
                                    f"class {node.name!r} is not PascalCase"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                continue
            if not SNAKE.match(node.name) and not node.name.startswith("__"):
                findings.append(Finding("S4", relative, node.lineno,
                                        f"function {node.name!r} is not snake_case"))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and not CONSTANT.match(target.id):
                    findings.append(Finding("S4", relative, node.lineno,
                                            f"constant {target.id!r} is not UPPER_SNAKE_CASE"))
    return findings


def check_root(files: list[Path], root: Path = ROOT) -> list[Finding]:
    """S5/S6 - the repository root stays short, and entry points stay thin."""
    findings: list[Finding] = []
    for relative in files:
        path = Path(relative)
        if len(path.parts) != 1:
            continue
        relative = as_posix(relative)
        if relative not in ROOT_PYTHON_ALLOWED:
            findings.append(Finding(
                "S5", relative, 1,
                "new top-level script; put it in tools/ or app/ instead "
                "(or add it to ROOT_PYTHON_ALLOWED with a documented reason)",
            ))
            continue
        budget = ENTRY_POINT_BUDGET.get(relative)
        if budget is None:
            continue
        lines = len((root / relative).read_text(encoding="utf-8").splitlines())
        if lines > budget:
            findings.append(Finding(
                "S6", relative, 1,
                f"{lines} lines exceeds the {budget}-line budget for an entry point; "
                "move a responsibility into app/ or ui/",
            ))
    return findings


# ---------------------------------------------------------------------- main
def run_checks(root: Path = ROOT) -> list[Finding]:
    files = [path for path in iter_python_files(root) if path.parts[0] in SOURCE_DIRS or len(path.parts) == 1]
    findings: list[Finding] = []
    for relative in files:
        tree = parse(root / relative)
        if tree is None:
            continue
        name = as_posix(relative)
        findings.extend(check_layer(name, tree))
        findings.extend(check_state(name, tree))
        findings.extend(check_names(name, tree))
    findings.extend(check_duplicates(files, root))
    findings.extend(check_root(files, root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--root", default=str(ROOT), help="repository root (default: this checkout)")
    args = parser.parse_args(argv)

    findings = run_checks(Path(args.root).resolve())
    if args.json:
        print(json.dumps({"passed": not findings, "count": len(findings),
                          "findings": [f.as_dict() for f in findings]}, indent=2))
    elif findings:
        for finding in findings:
            print(finding)
        print(f"\nSTRUCTURE: FAILED - {len(findings)} finding(s). See docs/ARCHITECTURE.md.")
    else:
        print("STRUCTURE: PASSED - layers, state, duplication, naming, root layout.")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
