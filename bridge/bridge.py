#!/usr/bin/env python3
"""Allowlisted GitHub polling bridge for Offline Agent HQ. No remote shell."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import pathlib
import tempfile
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("AGENT_HQ_REPO", "Ans-to/Youtube-Agent-automation")
# The application runtime defaults to main; AGENT_HQ_BRANCH selects the separate request/result inbox branch.
BRANCH = os.environ.get("AGENT_HQ_BRANCH", "main")
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
ALLOWED_ACTIONS = {"status", "self_test", "create_task", "run_task"}


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
        ref = urllib.parse.quote(BRANCH, safe="")
        return api_get(f"/repos/{REPO}/contents/{path}?ref={ref}", token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def api_put_json(path: str, content: dict, token: str, message: str) -> dict:
    """Create a JSON file at a fixed, caller-controlled repository path."""
    body = {
        "message": message,
        "branch": BRANCH,
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


def load_seen_request_ids(path: pathlib.Path) -> set[str]:
    """Load deduplication state strictly; corrupt state must never enable request replay."""
    path = pathlib.Path(path)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError("Bridge deduplication state is unreadable; refusing to process requests.") from exc
    if not isinstance(data, list) or any(not valid_request_id(item) for item in data) or len(data) != len(set(data)):
        raise ValueError("Bridge deduplication state is invalid; refusing to process requests.")
    return set(data)


def request_replay_state(request_id: str, state_dir: pathlib.Path) -> str:
    """Return new, completed, or interrupted so a partially handled request is never replayed."""
    root = pathlib.Path(state_dir)
    if (root / (request_id + ".result.json")).is_file():
        return "completed"
    if (root / (request_id + ".processing.json")).is_file():
        return "interrupted"
    return "new"


def claim_request(request_id: str, state_dir: pathlib.Path, request_sha256: str) -> bool:
    """Atomically claim a request before side effects; stale claims require human review."""
    marker = pathlib.Path(state_dir) / (request_id + ".processing.json")
    try:
        with marker.open("x", encoding="utf-8") as stream:
            json.dump({
                "id": request_id,
                "request_sha256": request_sha256,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }, stream)
    except FileExistsError:
        return False
    return True


def write_json_atomic(path: pathlib.Path, data: object) -> None:
    """Write JSON via a unique same-directory temporary file and atomic replacement."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


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
            if name in {"agent.py", "dashboard.py", "queue_store.py", "dispatch.py", "orchestrate.py", "skillbooks.json", "practice.py", "bridge.py", "studio.py", "capabilities.py", "render_lock.py", "production.py", "voice_backends.py", "piper_urdu_tts_adapter.py", "urdu_tts_adapter.py", "voice_preview.py", "captions.py", "research.py", "validate_render.py", "validate_frames.py", "quality_audit.py", "release_gate.py", "publish_youtube.py", "build_product.py", "run_quality_gate.py", "config.example.json"}
        ]
    elif action in {"create_task", "run_task"}:
        public["result"]["task_id"] = result.get("task_id")
        public["result"]["status"] = result.get(
            "status", "queued" if action == "create_task" and result.get("ok")
            else ("completed" if result.get("ok") else "failed_or_refused")
        )
        if action == "run_task":
            public["result"]["returncode"] = result.get("returncode")
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
    python_files = [
        PROJECT / "agent.py", PROJECT / "dashboard.py", PROJECT / "queue_store.py",
        PROJECT / "agents" / "dispatch.py", PROJECT / "agents" / "orchestrate.py", PROJECT / "agents" / "practice.py",
        PROJECT / "bridge" / "bridge.py",
        PROJECT / "video_studio" / "studio.py", PROJECT / "video_studio" / "capabilities.py",
        PROJECT / "video_studio" / "render_lock.py", PROJECT / "video_studio" / "production.py",
        PROJECT / "video_studio" / "voice_backends.py", PROJECT / "video_studio" / "piper_urdu_tts_adapter.py",
        PROJECT / "video_studio" / "urdu_tts_adapter.py", PROJECT / "video_studio" / "voice_preview.py",
        PROJECT / "video_studio" / "captions.py", PROJECT / "video_studio" / "research.py",
        PROJECT / "video_studio" / "validate_render.py", PROJECT / "video_studio" / "validate_frames.py",
        PROJECT / "video_studio" / "quality_audit.py", PROJECT / "video_studio" / "release_gate.py",
        PROJECT / "video_studio" / "publish_youtube.py", PROJECT / "product_studio" / "build_product.py",
        PROJECT / "tools" / "run_quality_gate.py",
    ]
    json_files = [PROJECT / "agents" / "roster.json", PROJECT / "agents" / "skillbooks.json", PROJECT / "config.example.json"]
    documentation_files = [PROJECT / "agents" / "MOTION_DESIGN_SYSTEM.md", PROJECT / "agents" / "TRAINING.md"]
    required = python_files + json_files + documentation_files
    missing = [str(path.relative_to(PROJECT)) for path in required if not path.is_file()]
    if missing:
        return {"ok": False, "reason": "Required project files are missing", "missing": missing}
    checked = []
    for path in python_files:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            cwd=str(PROJECT), capture_output=True, text=True, timeout=20, check=False,
        )
        if proc.returncode:
            return {"ok": False, "checked": checked, "file": path.name,
                    "error": (proc.stderr or proc.stdout)[-1000:]}
        checked.append(path.name)
    try:
        for path in json_files:
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError(path.name + " root must be a JSON object")
            if path.name == "skillbooks.json":
                ids = [profile.get("agent_id") for profile in data.get("profiles", []) if isinstance(profile, dict)]
                if len(ids) != len(set(ids)) or not ids:
                    raise ValueError("skillbooks.json profile IDs are empty or duplicated")
            checked.append(path.name)
        checked.extend(path.name for path in documentation_files)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "checked": checked, "error": str(exc)[:1000]}
    return {"ok": True, "syntax_checked": checked,
            "note": "Python syntax and required JSON profiles checked. No tasks were run and tasks.json was not modified intentionally."}

def create_local_task(title: object, kind: object, user_input: object) -> dict:
    """Create a bounded CEO task from an explicitly approved GitHub request."""
    title = title.strip() if isinstance(title, str) else ""
    user_input = user_input.strip() if isinstance(user_input, str) else ""
    allowed_kinds = {"plan", "draft", "summarize_workspace", "review_output", "youtube_package"}
    if not title or len(title) > 160:
        return {"ok": False, "reason": "title must contain 1–160 characters"}
    if not isinstance(kind, str) or kind not in allowed_kinds:
        return {"ok": False, "reason": "kind is not allowlisted"}
    if not user_input or len(user_input) > 16000:
        return {"ok": False, "reason": "input must contain 1–16,000 characters"}
    tasks_path = PROJECT / "tasks.json"
    if not PROJECT.is_dir():
        return {"ok": False, "reason": "Project directory not found"}
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    try:
        from queue_store import task_queue_lock, load_tasks, save_tasks
        with task_queue_lock(tasks_path):
            tasks = load_tasks(tasks_path)
            numbers = [
                int(str(item.get("id", "")).split("-")[-1])
                for item in tasks
                if str(item.get("id", "")).startswith("TASK-")
                and str(item.get("id", "")).split("-")[-1].isdigit()
            ]
            task_id = "TASK-%04d" % (max(numbers, default=0) + 1)
            tasks.append({
                "id": task_id,
                "title": title,
                "kind": kind,
                "input": user_input,
                "status": "pending",
                "error": "",
                "research_status": "pending",
                "created_via": "approved_github_mobile_bridge",
            })
            save_tasks(tasks_path, tasks)
    except (OSError, ValueError, TimeoutError, ImportError) as exc:
        return {"ok": False, "reason": "Could not safely write the local task queue (" + type(exc).__name__ + ")"}
    return {
        "ok": True,
        "task_id": task_id,
        "kind": kind,
        "status": "queued",
        "note": "Queued locally only; this request does not start the task or publish anything.",
    }


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
        r"\bpublish (?:the|this|my|finished|final)\b", r"\bpublish\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file|draft)\b",
        r"\bupload (?:the|this|my|finished|final)\b", r"\bupload\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file|draft)\b",
        r"\bsend (?:the|this|an? email|a message|the message)\b", r"\bemail .+ to .+",
        r"\bpost (?:the|this|my|finished|final)\b", r"\bpost\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file)\b",
        r"\bmake (?:a )?payment\b",
        r"\btransfer money\b", r"\bdelete (?:the|this|my)\b",
        r"\b(?:transfer|send|withdraw)\s+(?:money|funds|payment|cash)\b",
        r"\b(?:purchase|buy|order)\s+(?:the|this|a|an|any|some)\b",
        r"\b(?:delete|erase|remove)\s+(?:all|every|any|the|this|my|these|those|files?|folders?|records?|data|account|task)\b",
    ]
    if any(re.search(pattern, request_text, re.IGNORECASE) for pattern in external_patterns):
        return {"ok": False, "reason": "Task appears to request an external action; human action required"}
    # Runner processes the pending queue, so require this to be the ONLY pending task.
    pending = [t for t in tasks if isinstance(t, dict) and str(t.get("status", "")).lower() in {"pending", "queued"}]
    if len(pending) != 1 or str(pending[0].get("id", "")) != task_id:
        return {"ok": False, "reason": "Refusing ambiguous queue: target must be the only pending task"}
    try:
        proc = subprocess.run(
            [sys.executable, str(agent_path), "--once", "--task-id", task_id],
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
        seen = load_seen_request_ids(seen_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

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
        if not isinstance(request, dict):
            print("Ignoring request whose JSON root is not an object:", item["name"])
            continue
        req_id = request.get("id")
        if not valid_request_id(req_id) or req_id in seen:
            continue
        if request.get("approved") is not True:
            print("Request not approved; skipped:", req_id)
            continue
        replay_state = request_replay_state(req_id, STATE_DIR)
        if replay_state != "new":
            seen.add(req_id)
            if replay_state == "interrupted":
                print("Request has an unfinished local processing marker; refusing automatic replay and requiring human review:", req_id, file=sys.stderr)
            continue
        action = request.get("action")
        # Reject extra fields so requests cannot smuggle command strings or arguments.
        expected_fields = {"id", "approved", "action"}
        if action == "create_task":
            expected_fields.update({"title", "kind", "input"})
        elif action == "run_task":
            expected_fields.add("task_id")
        if set(request) != expected_fields or action not in ALLOWED_ACTIONS:
            print("Rejected request with unsupported fields/action:", req_id)
            seen.add(req_id)
            continue

        if not claim_request(req_id, STATE_DIR, digest):
            seen.add(req_id)
            print("Request was claimed by another run or has an unfinished marker; refusing automatic replay:", req_id, file=sys.stderr)
            continue

        if action == "status":
            result = project_status()
        elif action == "self_test":
            result = run_self_test()
        elif action == "create_task":
            result = create_local_task(request.get("title"), request.get("kind"), request.get("input"))
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
        write_json_atomic(out, response)
        marker = STATE_DIR / (req_id + ".processing.json")
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
        seen.add(req_id)
        processed += 1
        published, detail = publish_result(response, token)
        if published:
            print(f"{req_id}: {action} finished; local result: {out}; GitHub report: {detail}")
        else:
            print(f"{req_id}: {action} finished locally; GitHub report unavailable: {detail}")

    write_json_atomic(seen_path, sorted(seen))
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
