#!/usr/bin/env python3
"""Allowlisted GitHub polling bridge for Offline Agent HQ. No remote shell."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import pathlib
import subprocess
import sys
import time
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


def api_put_json(path: str, content: dict, token: str, message: str) -> dict:
    """Create a JSON file at a fixed, caller-controlled repository path."""
    body = {
        "message": message,
        "content": base64.b64encode(
            (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ).decode("ascii"),
    }
    req = urllib.request.Request(
        API + f"/repos/{REPO}/contents/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Offline-Agent-HQ-Safe-Bridge",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def valid_request_id(value: object) -> bool:
    """Restrict IDs so they cannot escape the local or repository result folders."""
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is not None


def public_result(response: dict) -> dict:
    """Return a minimal report; never publish prompts, output text, paths, or raw logs."""
    action = response.get("action")
    result = response.get("result", {})
    public = {
        "id": response.get("id"),
        "action": action,
        "completed_at": response.get("completed_at"),
        "result": {"ok": bool(result.get("ok", result.get("project_exists", True)))},
    }
    if action == "self_test":
        public["result"]["syntax_checked"] = [
            name for name in result.get("syntax_checked", [])
            if name in {"agent.py", "dashboard.py"}
        ]
    elif action == "run_task":
        public["result"]["task_id"] = result.get("task_id")
        public["result"]["returncode"] = result.get("returncode")
        public["result"]["status"] = result.get(
            "status", "completed" if result.get("ok") else "failed_or_refused"
        )
    elif action == "status":
        public["result"]["status"] = "status_check_completed"
    return public


def publish_result(response: dict, token: str) -> tuple[bool, str]:
    """Publish only sanitized metadata. A result path is write-once to avoid overwrites."""
    req_id = response["id"]
    path = f"bridge/results/{req_id}.json"
    try:
        if get_file(path, token) is not None:
            return False, "A result file with this ID already exists; refusing to overwrite it."
        api_put_json(
            path,
            public_result(response),
            token,
            f"Record Agent HQ result for {req_id}",
        )
        return True, path
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return False, f"GitHub result upload failed ({type(exc).__name__}); local result was retained."


def decode_content(item: dict) -> str:
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
    final_status = "unknown"
    try:
        updated_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        updated = [
            t for t in updated_tasks
            if isinstance(t, dict) and str(t.get("id", "")) == task_id
        ]
        if len(updated) == 1:
            final_status = str(updated[0].get("status", "unknown"))
    except (json.JSONDecodeError, OSError):
        pass
    success_status = final_status in {"completed", "needs_human_action"}
    return {
        "ok": proc.returncode == 0 and success_status,
        "task_id": task_id,
        "status": final_status,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
        "note": "Only the existing local queue was eligible; no task text or shell command was accepted from GitHub."
    }


def run_once() -> int:
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
        if not valid_request_id(req_id) or req_id in seen:
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
        # Persist locally before attempting reporting so a network/write failure never
        # loses the execution record or causes a completed task to be rerun on next poll.
        out = STATE_DIR / (req_id + ".result.json")
        out.write_text(json.dumps(response, indent=2), encoding="utf-8")
        seen.add(req_id)
        processed += 1
        published, detail = publish_result(response, token)
        if published:
            print(f"{req_id}: {action} finished; local result: {out}; GitHub report: {detail}")
        else:
            print(f"{req_id}: {action} finished locally; GitHub report unavailable: {detail}")

    seen_path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")
    print(f"Bridge check complete. New requests processed: {processed}.")
    return 0


def main() -> int:
    watch = "--watch" in sys.argv[1:]
    interval = 30
    for arg in sys.argv[1:]:
        if arg.startswith("--interval="):
            try:
                interval = int(arg.split("=", 1)[1])
            except ValueError:
                print("Invalid --interval; use a whole number of seconds.", file=sys.stderr)
                return 2
    if interval < 10 or interval > 3600:
        print("--interval must be between 10 and 3600 seconds.", file=sys.stderr)
        return 2
    if not watch:
        return run_once()
    print(f"Offline Agent HQ bridge watching GitHub every {interval}s. Press Ctrl+C to stop.")
    while True:
        try:
            code = run_once()
            if code != 0:
                print(f"Bridge check returned {code}; will retry.")
            time.sleep(interval)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            print(f"Bridge check failed ({type(exc).__name__}); will retry.")
            time.sleep(interval)
        except KeyboardInterrupt:
            print("Bridge stopped by user.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
