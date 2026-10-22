#!/usr/bin/env python3
"""Show every write as a change, not a dump.

Phase 3's last item: a reviewer should be able to see what a run *did* to a
workspace without reading whole files back. This module turns a before/after
snapshot into a bounded unified diff and a small machine-readable record.

Two rules:

1. **A change record is evidence, not a summary.** Lines are taken from a real
   diff of the real files. Nothing is described in prose the reader cannot check.
2. **Bounded.** A file diff is capped in lines, the number of files is capped, and
   a binary file is named rather than rendered. A huge generated file must not
   turn a review into a second copy of the artifact.

Standard library only; no network; the caller passes content in, so this module
never decides what is safe to read.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

SCHEMA = 1
MAX_DIFF_LINES = 80
MAX_FILES = 40
MAX_REPORT_CHARS = 60_000
_BINARY_MARKER = "\x00"


def read_text_file(path: Path) -> str | None:
    """Current content of a file, or None when it does not exist."""
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _split(text: str) -> list[str]:
    # keepends=False: a line diff, not a byte diff, and no trailing blank line
    # from a final newline that a reader would mistake for a change.
    return text.splitlines()


def is_binary(text: str) -> bool:
    return _BINARY_MARKER in text


def _diff_lines(path: str, before: str, after: str) -> list[str]:
    return list(difflib.unified_diff(
        _split(before), _split(after),
        fromfile="a/" + path, tofile="b/" + path, lineterm="",
    ))


def change_record(path: str, before: str | None, after: str | None) -> dict:
    """One file's change: what it was, what it is, and the lines in between."""
    label = str(path).replace("\\", "/")
    record = {
        "path": label,
        "kind": "unchanged",
        "added": 0,
        "removed": 0,
        "binary": False,
        "truncated": False,
        "diff": [],
    }
    if before is None and after is None:
        record["kind"] = "missing"
        return record
    if after is None:
        record["kind"] = "deleted"
        record["removed"] = len(_split(before or ""))
        return record
    old = before if before is not None else ""
    if old == after:
        if before is None:
            # An empty file that was created is still a change.
            record["kind"] = "created"
        return record
    record["kind"] = "created" if before is None else "modified"
    if is_binary(old) or is_binary(after):
        record["binary"] = True
        record["kind"] = "binary"
        return record
    lines = _diff_lines(label, old, after)
    if len(lines) > MAX_DIFF_LINES:
        record["truncated"] = True
        lines = lines[:MAX_DIFF_LINES] + ["... diff truncated after "
                                          f"{MAX_DIFF_LINES} lines of {len(lines)}"]
    record["diff"] = lines
    record["added"] = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    record["removed"] = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return record


def build_changes(root: str | Path, baseline: dict[str, str | None], *, title: str = "") -> dict:
    """Compare a baseline snapshot with the files on disk now.

    ``baseline`` maps a path relative to ``root`` to its content before the run
    (None when the file did not exist). Only those paths are considered: a review
    describes what the run touched, not everything in the directory.
    """
    base = Path(root)
    files: list[dict] = []
    unchanged: list[str] = []
    for path in sorted(baseline, key=lambda item: str(item).lower()):
        record = change_record(str(path), baseline[path], read_text_file(base / str(path)))
        if record["kind"] == "unchanged":
            unchanged.append(record["path"])
        elif record["kind"] != "missing":
            files.append(record)
        if len(files) >= MAX_FILES:
            break
    summary = {
        "files_changed": len(files),
        "created": sum(1 for item in files if item["kind"] == "created"),
        "modified": sum(1 for item in files if item["kind"] == "modified"),
        "deleted": sum(1 for item in files if item["kind"] == "deleted"),
        "binary": sum(1 for item in files if item["kind"] == "binary"),
        "added_lines": sum(item["added"] for item in files),
        "removed_lines": sum(item["removed"] for item in files),
        "truncated": any(item["truncated"] for item in files) or len(files) >= MAX_FILES,
    }
    return {
        "schema": SCHEMA,
        "title": str(title or "")[:200],
        "files": files,
        "unchanged": unchanged[:MAX_FILES],
        "summary": summary,
        "limits": [
            f"Diffs are capped at {MAX_DIFF_LINES} lines per file and {MAX_FILES} files.",
            "A binary file is named, not diffed.",
            "This records what changed on disk during this run; it is not a claim "
            "that the change is correct.",
        ],
    }


def _one_line(value: object, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def render_markdown(changes: dict, *, title: str = "") -> str:
    """A review page: every file that changed, with the lines that changed."""
    files = changes.get("files") or []
    summary = changes.get("summary") or {}
    heading = str(title or changes.get("title") or "").strip() or "Changes in this run"
    lines = [f"# {heading}", ""]
    if not files:
        lines.append("No files were written or changed by this run.")
        lines.append("")
    else:
        lines.append(
            f"{summary.get('files_changed', len(files))} file(s) changed: "
            f"{summary.get('created', 0)} created, {summary.get('modified', 0)} modified, "
            f"{summary.get('deleted', 0)} deleted, {summary.get('binary', 0)} binary — "
            f"+{summary.get('added_lines', 0)} −{summary.get('removed_lines', 0)} lines."
        )
        lines.append("")
        for record in files:
            kind = record.get("kind", "modified")
            lines.append(f"## `{record['path']}` ({kind})")
            lines.append("")
            if record.get("diff"):
                lines.append("```diff")
                lines.extend(record["diff"])
                lines.append("```")
            elif kind == "binary":
                lines.append("Binary file; not diffed.")
            elif kind == "deleted":
                lines.append(f"Deleted; {record.get('removed', 0)} line(s) removed.")
            elif kind == "created":
                lines.append("Created empty.")
            lines.append("")
    lines.append("## Limits")
    lines.append("")
    for limit in changes.get("limits") or []:
        lines.append(f"- {limit}")
    lines.append("")
    return "\n".join(lines)[:MAX_REPORT_CHARS]


def write(root: str | Path, changes: dict, *, title: str = "") -> dict[str, str]:
    """Write ``changes.json`` and ``changes.md`` into a directory."""
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    (target / "changes.json").write_text(
        json.dumps(changes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "changes.md").write_text(render_markdown(changes, title=title), encoding="utf-8")
    return {"report": "changes.json", "review": "changes.md"}


def manifest_entry(changes: dict) -> dict:
    """The bounded form that belongs in a manifest: names and counts, no bodies."""
    summary = dict(changes.get("summary") or {})
    return {
        "report": "changes.json",
        "review": "changes.md",
        "files": [item["path"] for item in (changes.get("files") or [])][:MAX_FILES],
        "summary": summary,
    }


def render_aggregate(entries: list[dict], *, title: str = "") -> str:
    """One review index for a whole run: what each tool changed, and where to look."""
    lines = [f"# {str(title or 'Changes in this run').strip()}", ""]
    lines.append("Every artifact write in this run, per builder. Full diffs live beside "
                 "each builder's output; this page is the index.")
    lines.append("")
    if not entries:
        lines.append("No builder wrote files in this run.")
        lines.append("")
        return "\n".join(lines)
    for entry in entries:
        summary = entry.get("summary") or {}
        lines.append(f"## {entry.get('tool', 'builder')} — {entry.get('artifact_dir', '')}")
        lines.append("")
        lines.append(
            f"{summary.get('files_changed', len(entry.get('files') or []))} file(s): "
            f"{summary.get('created', 0)} created, {summary.get('modified', 0)} modified, "
            f"{summary.get('deleted', 0)} deleted — "
            f"+{summary.get('added_lines', 0)} −{summary.get('removed_lines', 0)} lines."
        )
        lines.append("")
        for path in (entry.get("files") or [])[:MAX_FILES]:
            lines.append(f"- `{path}`")
        if entry.get("review"):
            lines.append("")
            lines.append(f"Full diff: `{entry.get('artifact_dir', '')}/{entry['review']}`")
        lines.append("")
    lines.append("## Limits")
    lines.append("")
    lines.append("- This index lists paths and counts. The lines themselves are in each "
                 "builder's `changes.md`; nothing here restates file content.")
    lines.append("")
    return "\n".join(lines)[:MAX_REPORT_CHARS]
