#!/usr/bin/env python3
"""Run a project's test suite, read the failure, and repair it only when proven.

This is the first module in the system that *changes someone else's code*, so it
is built around one rule: **a repair counts only if the suite goes green again
afterwards.** Nothing here reports a fix because a change looked plausible. If
the re-run fails, the change is reverted and the failure is recorded.

Three consequences shape the design:

1. **No guessing.** With no model available the module attempts only repairs
   that the test output itself names — a wrong discovery pattern, an unimportable
   test package. Everything else becomes a diagnosis, honestly labelled as one.
2. **Tests are never edited.** Their contents are fingerprinted before the first
   run and compared after the last. A change to a test file is reported as
   tampering, not as a fix, and never counts as verified.
3. **The tree is left as it was found.** Every attempted edit is reverted unless
   the following run passes, so a failed repair cannot leave a project worse than
   the session that found it.

Standard library only. No network. Subprocess execution is opt-in at the caller.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:  # Package import and standalone import both work.
    from tools.path_utils import canonical_path, is_within, safe_relative_path
except ImportError:  # pragma: no cover - exercised when run as a standalone script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from path_utils import canonical_path, is_within, safe_relative_path

MAX_OUTPUT_CHARS = 40_000
MAX_TIMEOUT_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3
MAX_FAILURES_REPORTED = 20
MAX_FILE_BYTES = 400_000
MAX_PROMPT_CHARS = 12_000

#: Test files are recognised by name, not by directory, so a project that keeps
#: tests beside its code is diagnosed the same way as one that does not.
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")

_ENV_ALLOWLIST = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
    "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS", "APPDATA", "LOCALAPPDATA",
    "LANG", "LC_ALL",
)


class FixError(ValueError):
    """A project could not be diagnosed or repaired safely."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def python_program() -> str:
    """An interpreter that exists here, or an empty string.

    Windows installs ``python`` and not ``python3``; naming a program that is not
    present turns "the tests did not run" into an unexplained failure.
    """
    for name in ("python3", "python"):
        if shutil.which(name):
            return name
    return sys.executable if Path(sys.executable).is_file() else ""


def discover_test_files(project: Path) -> list[Path]:
    """Every test file under the project, sorted, without descending into junk."""
    found: list[Path] = []
    for pattern in TEST_FILE_PATTERNS:
        for path in sorted(project.rglob(pattern)):
            relative = path.relative_to(project)
            if any(part.startswith(".") or part in {"node_modules", "__pycache__", ".venv", "venv"}
                   for part in relative.parts):
                continue
            if path.is_file() and path not in found:
                found.append(path)
    return sorted(found, key=lambda item: item.as_posix())


def fingerprint(project: Path, files: list[Path]) -> dict[str, str]:
    """Content hashes, so "the tests were not edited" is a check rather than a claim."""
    hashes: dict[str, str] = {}
    for path in files:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        try:
            hashes[safe_relative_path(path, project).as_posix()] = digest
        except ValueError:
            continue
    return hashes


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Names whose content differs between two fingerprints."""
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def detect_command(project: Path) -> tuple[list[str], str, str]:
    """The command that runs this project's tests. Returns (argv, framework, reason)."""
    program = python_program()
    if not program:
        return [], "", "no Python interpreter was found on this machine"
    tests_dir = project / "tests"
    root_tests = [path for path in discover_test_files(project)]
    if tests_dir.is_dir() and any(path.is_relative_to(tests_dir) for path in root_tests):
        argv = [program, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]
    elif root_tests:
        argv = [program, "-m", "unittest", "discover", "-s", ".", "-t", ".", "-v"]
    elif (project / "package.json").is_file():
        return [], "node", ("this looks like a Node project; only Python test suites are "
                            "run, because npm is not on the execution allowlist")
    else:
        return [], "", "no Python test files (test_*.py or *_test.py) were found"
    return argv, "unittest", ""


# ---------------------------------------------------------------------------
# Running and parsing
# ---------------------------------------------------------------------------

def _clean_environment() -> dict[str, str]:
    environment = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("LC_ALL", "C.UTF-8")
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run_suite(project: Path, argv: list[str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Run one command in the project. Never raises; a failure is an observation."""
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, no shell, program resolved above
            argv,
            cwd=str(project),
            env=_clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout[:MAX_OUTPUT_CHARS].decode("utf-8", "replace")
        exit_code, timed_out = completed.returncode, False
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or b""
        output = partial[:MAX_OUTPUT_CHARS].decode("utf-8", "replace")
        output += f"\n[timed out after {timeout}s]"
        exit_code, timed_out = -1, True
    except OSError as exc:
        return {
            "command": list(argv), "exit_code": -1, "output": "",
            "green": False, "timed_out": False, "error": f"{type(exc).__name__}: {exc}"[:300],
            "duration_seconds": round(time.monotonic() - started, 2),
            "tests_ran": 0, "failures": [], "summary": "",
        }
    parsed = parse_failures(output)
    return {
        "command": list(argv),
        "exit_code": exit_code,
        "output": output[-MAX_OUTPUT_CHARS:],
        "green": exit_code == 0 and parsed["tests_ran"] > 0,
        "timed_out": timed_out,
        "error": "",
        "duration_seconds": round(time.monotonic() - started, 2),
        "tests_ran": parsed["tests_ran"],
        "failures": parsed["failures"],
        "summary": parsed["summary"],
    }


_BLOCK_START = re.compile(r"(?m)^(FAIL|ERROR):\s+(.+?)\s*$")
_FRAME = re.compile(r'(?m)^\s*File "(.+?)", line (\d+)(?:, in (.+?))?\s*$')
_RAN = re.compile(r"(?m)^Ran (\d+) tests? in [\d.]+s")
_SUMMARY = re.compile(r"(?m)^(OK|FAILED .*|NO TESTS RAN.*)$")
_HEADER = re.compile(r"^([\w.]+)\s*(?:\((.+)\))?$")
_RULE = re.compile(r"^-{20,}\s*$")


def parse_failures(output: str) -> dict:
    """Turn unittest output into a structured list of failures.

    Only the shapes unittest actually prints are recognised. Anything else leaves
    ``tests_ran`` at zero, which makes the caller report "could not read the
    output" rather than inventing a passing run.
    """
    text = str(output or "")
    failures: list[dict] = []
    blocks = list(_BLOCK_START.finditer(text))
    for index, match in enumerate(blocks[:MAX_FAILURES_REPORTED]):
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
        body = text[match.end():end]
        # A failure block ends at the next rule line; everything after it is the
        # run summary, which would otherwise be read as the failure's message.
        trimmed: list[str] = []
        seen_content = False
        for line in body.splitlines():
            if _RULE.match(line):
                if seen_content:
                    break
                continue
            trimmed.append(line)
            seen_content = seen_content or bool(line.strip())
        body = "\n".join(trimmed)
        header_text = match.group(2)
        header = _HEADER.match(header_text)
        name = header.group(1) if header else header_text
        qualified = (header.group(2) or "").strip() if header else ""
        frames = [
            {"file": frame.group(1), "line": int(frame.group(2)), "function": (frame.group(3) or "").strip()}
            for frame in _FRAME.finditer(body)
        ][-6:]
        message = ""
        for line in reversed([item.strip() for item in body.splitlines() if item.strip()]):
            if line.startswith("---") or line.startswith("===="):
                continue
            if line.startswith("File \""):
                break
            message = line
            break
        failures.append({
            "test": qualified or name,
            "kind": "error" if match.group(1) == "ERROR" else "failure",
            "message": message[:400],
            "frames": frames,
        })
    ran = _RAN.search(text)
    summary = _SUMMARY.search(text)
    return {
        "tests_ran": int(ran.group(1)) if ran else 0,
        "failures": failures,
        "summary": (summary.group(1).strip() if summary else "")[:200],
        "truncated": len(blocks) > MAX_FAILURES_REPORTED,
    }


# ---------------------------------------------------------------------------
# Repairs
# ---------------------------------------------------------------------------

def _revert(target: Path, original: str | None) -> bool:
    """Restore a file to its pre-repair content, or delete one this run created."""
    try:
        if original is None:
            if target.is_file():
                target.unlink()
        else:
            target.write_text(original, encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True


def _written(path: Path) -> str | None:
    """Read a file, or None when it does not exist."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _discovery_pattern_repair(project: Path, run: dict) -> dict | None:
    """The project names its tests ``*_test.py``, which discovery ignores.

    Justified by the run itself: zero tests executed, yet such files exist. The
    repair is a discovery flag, not a code change.
    """
    if run.get("tests_ran", 0) > 0:
        return None
    argv = list(run.get("command") or [])
    if not argv or "-p" in argv:
        return None
    missed = [path for path in discover_test_files(project) if path.name.endswith("_test.py")
              and not path.name.startswith("test")]
    if not missed:
        return None
    return {
        "kind": "discovery_pattern",
        "argv": argv + ["-p", "*_test.py"],
        "path": "",
        "why": (f"{len(missed)} test file(s) use the *_test.py suffix, which the default "
                "unittest pattern (test*.py) never collects"),
    }


def _package_marker_repair(project: Path, run: dict) -> dict | None:
    """A ``tests`` directory without ``__init__.py`` that unittest cannot import."""
    output = str(run.get("output", ""))
    if "is not importable" not in output and "No module named 'tests'" not in output:
        return None
    tests_dir = project / "tests"
    marker = tests_dir / "__init__.py"
    if not tests_dir.is_dir() or marker.exists():
        return None
    return {
        "kind": "package_marker",
        "argv": [],
        "path": "tests/__init__.py",
        "content": "",
        "why": "unittest could not import the tests directory; an empty package marker "
               "makes it importable without changing any test",
    }


def build_repair_prompt(failure_text: str, files: dict[str, str]) -> str:
    """Compose the repair prompt. Deterministic, so it can be asserted exactly."""
    listing = "\n\n".join(f"FILE {name}\n{content}" for name, content in files.items())
    return (
        "You repair failing Python tests. Return JSON only: "
        '{"path":"relative/file.py","content":"<complete new file>","why":"one clause"} '
        'or {"give_up":true}. Rules: edit only a file listed below; never edit a test file; '
        "return the whole file, not a diff; no placeholders; no new dependencies; no network.\n\n"
        "FAILING OUTPUT\n" + failure_text[:6_000] + "\n\nFILES\n" + listing
    )[:MAX_PROMPT_CHARS]


def validate_proposal(project: Path, proposal: object, allowed: set[str]) -> tuple[dict | None, str]:
    """Accept only a complete, parseable rewrite of a file the failure named."""
    if not isinstance(proposal, dict):
        return None, "the proposal was not a JSON object"
    if proposal.get("give_up"):
        return None, "the model declined to propose a repair"
    path_value = str(proposal.get("path", "")).strip().replace("\\", "/")
    content = proposal.get("content")
    if not path_value or not isinstance(content, str) or not content.strip():
        return None, "the proposal has no path or no content"
    if Path(path_value).name.startswith("test_") or Path(path_value).name.endswith("_test.py"):
        return None, "the proposal edits a test file"
    if path_value not in allowed:
        return None, "the proposal edits a file the failure did not name"
    target = canonical_path(project / path_value)
    if not is_within(target, canonical_path(project), allow_equal=False):
        return None, "the proposal escapes the project"
    if target.suffix != ".py":
        return None, "the proposal edits a non-Python file"
    if len(content) > MAX_FILE_BYTES:
        return None, "the proposal is too large"
    if target.is_file() and "\0" in content:
        return None, "the proposal contains a null byte"
    try:
        ast.parse(content)
    except (SyntaxError, ValueError):
        return None, "the proposed file is not valid Python"
    return {"path": path_value, "content": content, "why": str(proposal.get("why", ""))[:200]}, ""


def _is_test_name(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test.py")


def _imported_modules(text: str) -> list[str]:
    """Top-level module names a file imports, without executing it."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.append(node.module.split(".")[0])
    return names


def repair_candidates(project: Path, failure: dict) -> list[str]:
    """Files a repair may touch, derived only from the failure itself.

    A traceback inside the code under test names the file directly. An assertion
    failure names only the test, so in that case the modules that test imports are
    used — still a closed set read from disk, never a guess.
    """
    root = canonical_path(project)
    names: list[str] = []
    test_files: list[str] = []
    for frame in failure.get("frames") or []:
        try:
            relative = safe_relative_path(canonical_path(str(frame.get("file", ""))), root).as_posix()
        except (ValueError, OSError):
            continue
        if not relative.endswith(".py"):
            continue
        if _is_test_name(Path(relative).name):
            if relative not in test_files:
                test_files.append(relative)
        elif relative not in names:
            names.append(relative)
    if names:
        return names
    for relative in test_files[:3]:
        text = _written(root / relative) or ""
        for module in _imported_modules(text):
            for candidate in (f"{module.replace('.', '/')}.py", f"{module.replace('.', '/')}/__init__.py"):
                if (root / candidate).is_file() and not _is_test_name(Path(candidate).name):
                    if candidate not in names:
                        names.append(candidate)
    return names


def model_proposer(model_call, project: Path):
    """Adapt ``(prompt, tokens) -> str`` into a proposal function.

    Every failure mode returns None: a broken model response must degrade into a
    diagnosis, never into an exception or an unchecked edit.
    """
    def propose(run: dict) -> dict | None:
        names: list[str] = []
        for failure in (run.get("failures") or [])[:MAX_FAILURES_REPORTED]:
            for name in repair_candidates(project, failure):
                if name not in names:
                    names.append(name)
        if not names:
            return None
        files = {name: (_written(project / name) or "")[:3_000] for name in names[:3]}
        prompt = build_repair_prompt(str(run.get("output", "")), files)
        try:
            response = model_call(prompt, 2_000)
        except Exception:  # noqa: BLE001 - a repair attempt must never end the run
            return None
        from_reply = _first_json_object(response)
        proposal, _ = validate_proposal(project, from_reply, set(files))
        return proposal
    return propose


def _first_json_object(text: object) -> dict | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", str(text or "")):
        try:
            parsed, _ = decoder.raw_decode(str(text)[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def next_repair(project: Path, run: dict, propose=None) -> dict:
    """The next repair to try: a structural one the output justifies, else a proposal."""
    for builder in (_discovery_pattern_repair, _package_marker_repair):
        repair = builder(project, run)
        if repair:
            return repair
    if propose is not None:
        repair = propose(run)
        if repair:
            return {"kind": "model_patch", **repair}
    return {}


def apply_repair(project: Path, repair: dict) -> tuple[bool, str, Path | None, str | None]:
    """Apply one repair. Returns (ok, reason, target, original content)."""
    if repair.get("argv"):
        return True, "", None, None
    relative = str(repair.get("path", "")).strip()
    if not relative:
        return False, "the repair names no file", None, None
    try:
        target = canonical_path(project / relative)
    except (OSError, RuntimeError, ValueError):
        return False, "the repair path could not be resolved", None, None
    if not is_within(target, canonical_path(project), allow_equal=False):
        return False, "the repair path escapes the project", None, None
    if target.name.startswith("test_") or target.name.endswith("_test.py"):
        return False, "a repair may not edit a test file", None, None
    original = _written(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(repair.get("content", "")), encoding="utf-8", newline="\n")
    except OSError:
        return False, "the repair could not be written", None, None
    return True, "", target, original


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------

def diagnose(project: str | Path, *, allow_exec: bool = True,
             timeout: int = DEFAULT_TIMEOUT_SECONDS, max_attempts: int = MAX_ATTEMPTS,
             run=run_suite, propose=None, title: str = "") -> dict:
    """Run the suite, try bounded repairs, and report what is actually true.

    ``run`` and ``propose`` are injected so the loop can be tested without a model
    or a subprocess; the defaults do the real work.
    """
    root = canonical_path(project)
    timeout = max(5, min(int(timeout), MAX_TIMEOUT_SECONDS))
    max_attempts = max(0, min(int(max_attempts), MAX_ATTEMPTS))
    label = (title or "").strip() or f"Test report: {root.name}"

    report: dict = {
        "schema": 1,
        "title": label,
        "project": root.name,
        "framework": "",
        "command": [],
        "command_text": "",
        "exec_enabled": bool(allow_exec),
        "runs": [],
        "failures": [],
        "repairs": [],
        "verified_fix": False,
        "test_files_modified": False,
        "changed_test_files": [],
        "no_run_reason": "",
        "limits": [
            "A repair counts only when the suite passes afterwards. A code edit that "
            "does not turn the suite green is reverted; a structural repair (such as "
            "an empty package marker) is kept and named, because the suite cannot "
            "run without it.",
            "Tests themselves are never edited: their contents are hashed before "
            "and after the run, and any change is reported as tampering.",
            "Only Python unittest suites are run. npm is not on the execution "
            "allowlist, so Node projects are diagnosed but not repaired.",
        ],
        "generated_by": "deterministic_test_doctor",
        "ai_generated": False,
        "human_review_required": True,
    }
    if not root.is_dir():
        report["no_run_reason"] = "the project directory does not exist"
        return report

    tests_before = discover_test_files(root)
    hashes_before = fingerprint(root, tests_before)

    if not allow_exec:
        report["no_run_reason"] = (
            "command execution is disabled, so the suite was not run; set "
            "AGENT_HQ_ALLOW_EXEC=1 to allow it")
        return report

    argv, framework, reason = detect_command(root)
    report["framework"] = framework
    if not argv:
        report["no_run_reason"] = reason
        return report
    report["command"] = argv
    report["command_text"] = " ".join(argv)

    result = run(root, argv, timeout)
    result["phase"] = "before"
    result["index"] = len(report["runs"]) + 1
    report["runs"].append(result)
    report["failures"] = result.get("failures") or []

    attempt = 0
    while not result.get("green") and attempt < max_attempts:
        repair = next_repair(root, result, propose)
        if not repair:
            break
        attempt += 1
        record = {
            "attempt": attempt,
            "kind": repair.get("kind", "unknown"),
            "path": repair.get("path", ""),
            "why": repair.get("why", ""),
            "verified": False,
            "reverted": False,
        }
        if repair.get("argv"):
            argv = list(repair["argv"])
            report["command"] = argv
            report["command_text"] = " ".join(argv)
            record["command_text"] = report["command_text"]
            report["repairs"].append(record)
            result = run(root, argv, timeout)
            result["phase"] = f"attempt-{attempt}"
            result["index"] = len(report["runs"]) + 1
            report["runs"].append(result)
            report["failures"] = result.get("failures") or []
            if result.get("green"):
                record["verified"] = True
                break
            continue
        ok, problem, target, original = apply_repair(root, repair)
        if not ok:
            record["reverted"] = True
            record["why"] = (record["why"] + " | rejected: " + problem)[:400]
            report["repairs"].append(record)
            break
        report["repairs"].append(record)
        outcome = run(root, argv, timeout)
        outcome["phase"] = f"attempt-{attempt}"
        outcome["index"] = len(report["runs"]) + 1
        report["runs"].append(outcome)
        report["failures"] = outcome.get("failures") or []
        result = outcome
        if outcome.get("green"):
            record["verified"] = True
            break
        if repair.get("kind") == "model_patch":
            # A code edit that did not fix the suite is undone: the project must not
            # be left holding a change that was never shown to help.
            if target is not None and _revert(target, original):
                record["reverted"] = True
        else:
            # A structural repair changes how the suite is discovered, not what it
            # asserts. It is kept because the next attempt cannot run without it,
            # and the report names it.
            record["kept"] = True

    last = report["runs"][-1] if report["runs"] else {}
    report["verified_fix"] = bool(last.get("green")) and any(r.get("verified") for r in report["repairs"])
    hashes_after = fingerprint(root, tests_before)
    changed = changed_files(hashes_before, hashes_after)
    report["changed_test_files"] = changed
    report["test_files_modified"] = bool(changed)
    if report["test_files_modified"]:
        # A green suite reached by editing a test is not a fix.
        report["verified_fix"] = False
    report["green"] = bool(last.get("green"))
    report["tests_ran"] = int(last.get("tests_ran") or 0)
    if not report["green"] and not report["failures"]:
        report["no_run_reason"] = report["no_run_reason"] or (
            "the suite did not pass and its output named no individual failing test")
    return report


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _short(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def render_markdown(report: dict) -> str:
    """A report a person can act on: what ran, what broke, what changed."""
    runs = report.get("runs") or []
    repairs = report.get("repairs") or []
    failures = report.get("failures") or []
    lines = [f"# {report.get('title', 'Test report')}", ""]
    lines.append("> Generated offline by Agent HQ from a real test run. A repair is "
                 "recorded as fixed only when the suite passed afterwards; nothing "
                 "here is inferred from reading the code.")
    lines.append("")
    lines.append(f"- Project: `{report.get('project', '')}`")
    if report.get("command_text"):
        lines.append(f"- Command: `{report['command_text']}`")
    if runs:
        first, last = runs[0], runs[-1]
        lines.append(f"- Runs: {len(runs)} (exit {first.get('exit_code')} → {last.get('exit_code')})")
        lines.append(f"- Tests seen in the last run: {report.get('tests_ran', 0)}")
    lines.append(f"- Result: {'suite passing' if report.get('green') else 'suite not passing'}"
                 f"{'; repair verified' if report.get('verified_fix') else ''}")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if report.get("no_run_reason"):
        lines.append(report["no_run_reason"] + ".")
        lines.append("")
    if failures:
        lines.append(f"{len(failures)} failing test(s) were named in the output:")
        lines.append("")
        for failure in failures[:MAX_FAILURES_REPORTED]:
            location = ""
            if failure.get("frames"):
                frame = failure["frames"][-1]
                location = f" — `{Path(str(frame['file'])).name}:{frame['line']}`"
            lines.append(f"- **{_short(failure.get('test'), 160)}** "
                         f"({failure.get('kind', 'failure')}){location}: "
                         f"{_short(failure.get('message'), 200) or 'no message'}")
        lines.append("")
    elif runs and report.get("green"):
        lines.append(f"The suite passed on run {len(runs)} with "
                     f"{report.get('tests_ran', 0)} test(s).")
        lines.append("")
    elif runs:
        lines.append("The suite did not pass, but its output named no individual failing test.")
        lines.append("")

    lines.append("## Repairs")
    lines.append("")
    if not repairs:
        lines.append("No repair was attempted. Nothing was changed.")
        lines.append("")
    else:
        for repair in repairs:
            state = ("verified by a passing re-run" if repair.get("verified")
                     else "reverted — the re-run still failed" if repair.get("reverted")
                     else "kept — the suite still failed" if repair.get("kept")
                     else "applied")
            target = f"`{repair['path']}`" if repair.get("path") else "the test command"
            lines.append(f"{repair.get('attempt', '?')}. {target} — {repair.get('kind')}: "
                         f"{_short(repair.get('why'), 200)} ({state}).")
        lines.append("")
        if report.get("test_files_modified"):
            lines.append("A test file changed during this run, so the result is not a fix: "
                         + ", ".join(f"`{name}`" for name in report["changed_test_files"][:5]))
            lines.append("")

    lines.append("## Limits")
    lines.append("")
    for limit in report.get("limits") or []:
        lines.append(f"- {limit}")
    lines.append("- This diagnoses one test command. It does not know why the code was "
                 "written that way, and a passing suite is not proof of correctness.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict, directory: str | Path) -> dict[str, str]:
    """Persist the JSON and Markdown forms. Returns the files written."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "test-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "fix-plan.md").write_text(render_markdown(report), encoding="utf-8")
    return {"report": "test-report.json", "plan": "fix-plan.md"}


def main(argv: list[str] | None = None) -> int:
    """Diagnose a project from the command line: ``python tools/test_fix.py <dir>``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run a project's tests and report honestly.")
    parser.add_argument("project", help="directory containing the project")
    parser.add_argument("--out", default="", help="where to write test-report.json and fix-plan.md")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    report = diagnose(args.project, timeout=args.timeout)
    if args.out:
        write_report(report, args.out)
    print(render_markdown(report))
    return 0 if report.get("green") else 1


if __name__ == "__main__":
    raise SystemExit(main())
