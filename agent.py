#!/usr/bin/env python3
"""Offline Agent HQ: local task queue with constrained specialist stages."""
import argparse, json, time, urllib.request, urllib.error, urllib.parse, ipaddress
from pathlib import Path
from datetime import datetime
from queue_store import task_queue_lock, load_tasks, save_tasks
from quality_outputs import youtube_package, structured_plan, structured_draft, structured_review

BASE = Path(__file__).resolve().parent
TASKS = BASE / "tasks.json"
CONFIG = BASE / "config.json"
WORKSPACE = BASE / "workspace"
OUTPUTS = BASE / "outputs"
LOGS = BASE / "logs"

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirects are disabled for local model requests", headers, fp)

def post_local_model(url, body, timeout):
    parts = urllib.parse.urlsplit(url)
    try:
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError as exc:
        raise ValueError("Use a literal loopback IP endpoint such as http://127.0.0.1:8080/v1/chat/completions.") from exc
    if parts.scheme != "http" or not address.is_loopback or port is None or not 1 <= port <= 65535 or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Only a plain HTTP endpoint on a literal loopback IP and explicit port is allowed.")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type":"application/json","Accept":"application/json"}, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(req, timeout=max(1,min(int(timeout),300))) as response:
        data = json.loads(response.read(20*1024*1024+1).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Local model response must be a JSON object.")
    return data

def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def log(msg):
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "agent.log").open("a", encoding="utf-8") as f:
        f.write(f"[{stamp()}] {msg}\n")

def safe_id(value):
    out = "".join(c for c in str(value) if c.isalnum() or c in "-_")
    return out[:60] or "TASK"

def workspace_text(cfg):
    limit = int(cfg.get("runner", {}).get("max_workspace_file_chars", 3000))
    chunks = []
    for p in sorted(WORKSPACE.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".txt", ".md", ".json"}:
            try:
                chunks.append(f"\n--- {p.relative_to(WORKSPACE)} ---\n" +
                              p.read_text(encoding="utf-8", errors="replace")[:limit])
            except OSError:
                pass
    return "\n".join(chunks)[:10000] or "(Workspace has no readable text files.)"

def ask_local_model(prompt, cfg):
    m = cfg.get("model", {})
    if not m.get("enabled"):
        return None
    url = m.get("base_url", "")
    body = {
        "model": m.get("model", "local-model"),
        "messages": [
            {"role": "system", "content": "You are Offline Agent HQ. Work only with the supplied prompt and local context. Never claim to browse or access other apps. State uncertainty and give a useful, checked result."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": min(max(int(m.get("max_output_tokens", 900)), 4500), 7000) if task.get("kind") == "youtube_package" else int(m.get("max_output_tokens", 900))
    }
    data = post_local_model(url, body, m.get("timeout_seconds", 120))
    return data["choices"][0]["message"]["content"].strip()

def fallback(task, kind, context):
    title, user_input = task.get("title", "Untitled"), task.get("input", "")
    if kind == "youtube_package":
        return youtube_package(title, user_input)
    if kind == "plan":
        return structured_plan(title, user_input)
    if kind == "draft":
        return structured_draft(title, user_input)
    if kind == "summarize_workspace":
        return f"""# Workspace inventory

{context}

## Limitation
Template mode cannot perform semantic summarization. The text above is an inventory of readable local workspace content.
"""
    return structured_review(title, context)

