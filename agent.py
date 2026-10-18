#!/usr/bin/env python3
"""Offline Agent HQ: local task queue with constrained specialist stages."""
import argparse, json, time, urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
TASKS = BASE / "tasks.json"
CONFIG = BASE / "config.json"
WORKSPACE = BASE / "workspace"
OUTPUTS = BASE / "outputs"
LOGS = BASE / "logs"

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
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:") or url.startswith("http://[::1]:")):
        raise ValueError("Offline mode permits only a localhost/loopback model endpoint.")
    body = {
        "model": m.get("model", "local-model"),
        "messages": [
            {"role": "system", "content": "You are Offline Agent HQ. Work only with the supplied prompt and local context. Never claim to browse or access other apps. State uncertainty and give a useful, checked result."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": int(m.get("max_output_tokens", 900))
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=int(m.get("timeout_seconds", 120))) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()

def fallback(task, kind, context):
    title, user_input = task.get("title", "Untitled"), task.get("input", "")
    if kind == "plan":
        return f"""# {title}

## Goal
{user_input}

## Work plan
1. Define the required final result and constraints.
2. Break the work into small, checkable steps.
3. Use only the supplied local information and available offline tools.
4. Check the result against the original requirements.
5. Record unresolved questions and anything that needs human approval.

## Review status
Template mode only: no language model was enabled, so this is a structured starting plan rather than AI-generated research.
"""
    if kind == "draft":
        return f"""# Draft: {title}

## Source request
{user_input}

## Draft status
Template mode only: no local language model is enabled. Enable a compatible local model to generate the requested content.
"""
    if kind == "summarize_workspace":
        return f"""# Workspace inventory

{context}

## Limitation
Template mode cannot perform semantic summarization. The text above is an inventory of readable local workspace content.
"""
    return f"""# Review checklist: {title}

- Does the output answer the task?
- Are factual claims supported by supplied local files?
- Are assumptions and missing inputs stated?
- Are there contradictions or incomplete steps?
- Does the result avoid unsafe external actions?

## Limitation
No semantic review was performed because a local language model is not enabled.
"""

def build_prompt(task, kind, context, cfg):
    max_chars = int(cfg.get("runner", {}).get("max_input_chars", 6000))
    return f"""Perform the task using only the supplied request and local workspace context.
Use these stages internally:
Coordinator: identify goal and constraints.
Planner: choose a short approach.
Worker: complete the deliverable.
Reviewer: check for unsupported claims, contradictions, omissions, and unsafe suggestions; revise.
Do not claim access to the internet, sensors, other apps, or files not included below. Never request secrets.
CRITICAL ACTION-VERIFICATION RULES:
- Generating text, instructions, a plan, or a draft does not perform an external action.
- Never say an alarm was set, a reminder scheduled, a message sent, a file uploaded, or content published unless the supplied context contains reliable confirmation from the relevant service or tool.
- If no such confirmation is supplied, explicitly state that the action was NOT performed or verified and explain what the user must do themselves.
- Never invent tool calls, confirmations, execution logs, or success messages.
- The Reviewer must check every statement claiming that an action was completed against the supplied evidence. If evidence is absent, correct the claim.
Return the final deliverable in clear Markdown.

TASK TYPE: {kind}
TITLE: {task.get('title', '')}
REQUEST:
{task.get('input', '')[:max_chars]}

LOCAL WORKSPACE:
{context[:max_chars]}
"""

def process(task, cfg):
    kind = task.get("kind", "")
    if kind not in {"plan", "draft", "summarize_workspace", "review_output"}:
        raise ValueError("Unsupported task type.")
    context = workspace_text(cfg) if kind in {"summarize_workspace", "review_output"} else ""
    result = ask_local_model(build_prompt(task, kind, context, cfg), cfg)
    if not result:
        result = fallback(task, kind, context)
    OUTPUTS.mkdir(exist_ok=True)
    path = OUTPUTS / (safe_id(task.get("id")) + ".md")
    path.write_text(result.rstrip() + "\n", encoding="utf-8")

    # Generated text is not proof that an external action happened.
    request_text = " ".join(
        str(task.get(k, "")) for k in ("title", "input")
    ).strip().lower()

    # Flag explicit execution requests, not ordinary drafting or planning.
    external_action_patterns = [
        r"\bset (?:an? )?alarm\b",
        r"\b(?:wake me|remind me|schedule (?:a )?reminder)\b",
        r"\bpublish (?:the|this|my|finished|final)\b",
        r"\bupload (?:the|this|my|finished|final)\b",
        r"\bsend (?:the|this|an? email|a message|the message)\b",
        r"\bemail .+ to .+",
        r"\bpost (?:the|this|my|finished|final)\b",
        r"\bmake (?:a )?payment\b",
        r"\btransfer money\b",
        r"\bdelete (?:the|this|my)\b",
    ]
    import re
    needs_action = any(
        re.search(pattern, request_text, re.IGNORECASE)
        for pattern in external_action_patterns
    )

    if needs_action:
        status = "needs_human_action"
        message = (
            "Plan or draft generated only. This local runner did not perform "
            "or verify the requested external action."
        )
        task.update(
            status=status,
            completed_at="",
            output_file=str(path.relative_to(BASE)),
            error=message,
        )
        log(f"NEEDS HUMAN ACTION {task.get('id')} -> {path.name}")
    else:
        task.update(
            status="completed",
            completed_at=stamp(),
            output_file=str(path.relative_to(BASE)),
            error="",
        )
        log(f"COMPLETED {task.get('id')} -> {path.name}")

    return path

def cycle():
    cfg = load(CONFIG, {})
    tasks = load(TASKS, [])
    pending = [t for t in tasks if t.get("status", "pending") == "pending"]
    count = 0
    for task in pending[:int(cfg.get("runner", {}).get("max_tasks_per_cycle", 3))]:
        task["status"] = "running"
        save(TASKS, tasks)
        try:
            path = process(task, cfg)
            if task.get("status") == "needs_human_action":
                print(f"Needs human action {task.get('id')} -> {path}")
            else:
                print(f"Completed {task.get('id')} -> {path}")
        except Exception as e:
            task.update(status="failed", error=str(e)[:400])
            log(f"FAILED {task.get('id')}: {e}")
            print(f"Failed {task.get('id')}: {e}")
        save(TASKS, tasks)
        count += 1
    if count == 0:
        print("No pending tasks.")
    return count

def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=None)
    args = ap.parse_args()
    if args.loop:
        cfg = load(CONFIG, {})
        interval = max(10, args.interval or int(cfg.get("runner", {}).get("interval_seconds", 60)))
        print(f"Agent loop running every {interval}s. Ctrl+C to stop.")
        try:
            while True:
                cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        cycle()

if __name__ == "__main__":
    main()
