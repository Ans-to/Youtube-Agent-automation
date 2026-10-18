#!/usr/bin/env python3
"""Allowlisted GitHub polling bridge for Offline Agent HQ. No remote shell."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("AGENT_HQ_REPO", "Ans-to/Youtube-Agent-automation")
API = "https://api.github.com"
PROJECT = pathlib.Path(os.environ.get(
    "AGENT_HQ_PROJECT",
    "/storage/emulated/0/Download/OfflineAgentHQ/OfflineAgentHQ"
)).expanduser()
TOKEN_FILE = pathlib.Path(os.environ.get(
    "AGENT_HQ_TOKEN_FILE", str(pathlib.Path.home() / ".config/offline-agent-hq/github-token")
)).expanduser()
STATE_DIR = pathlib.Path(os.environ.get(
    "AGENT_HQ_STATE_DIR", str(pathlib.Path.home() / ".local/state/offline-agent-hq")
)).expanduser()
# Deliberately narrow: never add shell, arbitrary code, package installation, or task execution.
ALLOWED_ACTIONS = {"status", "self_test", "run_task"}


def api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Offline-Agent-HQ-Safe-Bridge",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_file(path: str, token: str) -> dict | None:
    try:
        return api_get(f"/repos/{REPO}/contents/{path}", token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def decode_content(item: dict) -> str:
    import base64
    if item.get("encoding") != "base64":
        raise ValueError("Unexpected GitHub content encoding")
    return base64.b64decode(item["content"]).decode("utf-8")


def project_status() -> dict:
    result = {
        "project_exists": PROJECT.is_dir(),
        "project_path": str(PROJECT),
        "files": {},
    }
    for name in ("agent.py", "dashboard.py", "config.json", "tasks.json"):
        path = PROJECT / name
        result["files"][name] = {
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
        }
    # Do not return task contents, configuration values, credentials, or prompts.
    return result


def run_self_test() -> dict:
    if not PROJECT.is_dir():
        return {"ok": False, "reason": "Project directory not found"}
    files = [PROJECT / "agent.py", PROJECT / "dashboard.py"]
    present = [str(p.name) for p in files if p.is_file()]
    if not present:
        return {"ok": False, "reason": "No expected Python source files found"}
    # Syntax-check source files only. This does not run agent.py or process tasks.
    checked = []
    for path in files:
        if path.is_file():
            proc = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                cwd=str(PROJECT),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode:
                return {"ok": False, "checked": checked, "file": path.name,
                        "error": (proc.stderr or proc.stdout)[-1000:]}
            checked.append(path.name)
    return {"ok": True, "syntax_checked": checked,
            "note": "No tasks were run and tasks.json was not modified intentionally."}


def run_one_queued_task(task_id: str) -> dict:
    """Run only the specifically named, locally queued safe task; never accept task text remotely."""
    tasks_path = PROJECT / "tasks.json"
    agent_path = PROJECT / "agent.py"
    if not tasks_path.is_file() or not agent_path.is_file():
        return {"ok": False, "reason": "tasks.json or agent.py is missing"}
    try:
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "reason": f"Cannot safely read tasks.json: {type(exc).__name__}"}
    if not isinstance(tasks, list):
        return {"ok": False, "reason": "Unsupported tasks.json format; expected a list"}
    matches = [t for t in tasks if isinstance(t, dict) and str(t.get("id", "")) == task_id]
    if len(matches) != 1:
        return {"ok": False, "reason": "Task ID must match exactly one existing local task"}
    task = matches[0]
    if str(task.get("status", "")).lower() not in {"pending", "queued"}:
        return {"ok": False, "reason": "Task is not pending/queued; refusing to rerun"}
    if task.get("kind") not in {"plan", "draft", "summarize_workspace", "review_output"}:
        return {"ok": False, "reason": "Task type is not allowlisted"}
    # Conservative gate: do not run tasks whose wording requests an external action.
    import re
    request_text = " ".join(str(task.get(k, "")) for k in ("title", "input")).lower()
    external_patterns = [
        r"\bset (?:an? )?alarm\b", r"\b(?:wake me|remind me|schedule (?:a )?reminder)\b",
        r"\bpublish (?:the|this|my|finished|final)\b", r"\bupload (?:the|this|my|finished|final)\b",
        r"\bsend (?:the|this|an? email|a message|the message)\b", r"\bemail .+ to .+",
        r"\bpost (?:the|this|my|finished|final)\b", r"\bmake (?:a )?payment\b",
        r"\btransfer money\b", r"\bdelete (?:the|this|my)\b",
    ]
    if any(re.search(pattern, request_text, re.IGNORECASE) for pattern in external_patterns):
        return {"ok": False, "reason": "Task appears to request an external action; human action required"}
    # Runner processes the pending queue, so require this to be the ONLY pending task.
    pending = [t for t in tasks if isinstance(t, dict) and str(t.get("status", "")).lower() in {"pending", "queued"}]
    if len(pending) != 1 or str(pending[0].get("id", "")) != task_id:
        return {"ok": False, "reason": "Refusing ambiguous queue: target must be the only pending task"}
    try:
        proc = subprocess.run(
            [sys.executable, str(agent_path), "--once"],
            cwd=str(PROJECT), capture_output=True, text=True, timeout=3600, check=False
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "Task runner timed out; inspect local logs before retrying"}
    return {
        "ok": proc.returncode == 0,
        "task_id": task_id,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
        "note": "Only the existing local queue was eligible; no task text or shell command was accepted from GitHub."
    }


def main() -> int:
    if not TOKEN_FILE.is_file():
        print("Missing GitHub token file:", TOKEN_FILE, file=sys.stderr)
        print("Create it locally; never commit it or paste it into chat.", file=sys.stderr)
        return 2
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        print("GitHub token file is empty.", file=sys.stderr)
        return 2
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seen_path = STATE_DIR / "seen-request-ids.json"
    try:
        seen = set(json.loads(seen_path.read_text(encoding="utf-8"))) if seen_path.exists() else set()
    except (json.JSONDecodeError, OSError):
        seen = set()

    listing = get_file("bridge/requests", token)
    if listing is None:
        print("Bridge connected. No bridge/requests directory found.")
        return 0
    items = listing if isinstance(listing, list) else [listing]
    processed = 0
    for item in items:
        if item.get("type") != "file" or not item.get("name", "").endswith(".json"):
            continue
        request_item = get_file(item["path"], token)
        if not request_item:
            continue
        raw = decode_content(request_item)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            print("Ignoring invalid JSON request:", item["name"])
            continue
        req_id = request.get("id")
        if not isinstance(req_id, str) or not req_id or req_id in seen:
            continue
        if request.get("approved") is not True:
            print("Request not approved; skipped:", req_id)
            continue
        action = request.get("action")
        # Reject extra fields so requests cannot smuggle command strings or arguments.
        expected_fields = {"id", "approved", "action"}
        if action == "run_task":
            expected_fields.add("task_id")
        if set(request) != expected_fields or action not in ALLOWED_ACTIONS:
            print("Rejected request with unsupported fields/action:", req_id)
            seen.add(req_id)
            continue

        if action == "status":
            result = project_status()
        elif action == "self_test":
            result = run_self_test()
        elif action == "run_task":
            task_id = request.get("task_id")
            if not isinstance(task_id, str) or not task_id or len(task_id) > 100:
                result = {"ok": False, "reason": "Invalid task_id"}
            else:
                result = run_one_queued_task(task_id)
        else:
            result = {"ok": False, "reason": "Action not allowlisted"}

        response = {
            "id": req_id,
            "request_sha256": digest,
            "action": action,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        # Write locally only; do not publish machine details back to GitHub by default.
        out = STATE_DIR / (req_id.replace("/", "_") + ".result.json")
        out.write_text(json.dumps(response, indent=2), encoding="utf-8")
        seen.add(req_id)
        processed += 1
        print(f"{req_id}: {action} finished; local result: {out}")

    seen_path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")
    print(f"Bridge check complete. New requests processed: {processed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
