#!/usr/bin/env python3
"""Offline Agent HQ: local task queue with constrained specialist stages."""
import argparse, json, time, urllib.request, urllib.error, urllib.parse, ipaddress, sys
from pathlib import Path
from datetime import datetime
from queue_store import task_queue_lock, load_tasks, save_tasks
from quality_outputs import youtube_package, structured_plan, structured_draft, structured_review

BASE = Path(__file__).resolve().parent
AGENT_DIR = BASE / "agents"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
from orchestrate import run_pipeline as run_ceo_pipeline
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

def ask_local_model(prompt, cfg, kind=''):
    m = cfg.get("model", {})
    if not m.get("enabled"):
        return None
    url = m.get("base_url", "")
    body = {
        "model": m.get("model", "local-model"),
        "messages": [
            {"role": "system", "content": "You are Offline Agent HQ. Use only the supplied prompt, retrieved research report, and local context. Do not claim to access other apps or pages beyond the supplied report. Cite source URLs when supported by retrieved page text; distinguish evidence from inference and state uncertainty."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": min(max(int(m.get("max_output_tokens", 900)), 4500), 7000) if kind == "youtube_package" else int(m.get("max_output_tokens", 900))
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

def build_prompt(task, kind, context, cfg):
    max_chars = int(cfg.get("runner", {}).get("max_input_chars", 6000))
    context_limit = max(max_chars, 18000)
    return f"""Perform the task using the supplied request, local workspace context, and any AUTOMATED WEB RESEARCH section included below.
Use these stages internally:
Coordinator: identify goal and constraints.
Planner: choose a short approach.
Worker: complete the deliverable.
Reviewer: check for unsupported claims, contradictions, omissions, and unsafe suggestions; revise.
Do not claim access to sensors, other apps, or files not included below. Internet research is only available through the explicitly supplied research section; never claim pages were fetched or checked unless the report says so. Never request secrets.
CRITICAL ACTION-VERIFICATION RULES:
- Generating text, instructions, a plan, or a draft does not perform an external action.
- Never say an alarm was set, a reminder scheduled, a message sent, a file uploaded, or content published unless the supplied context contains reliable confirmation from the relevant service or tool.
- If no such confirmation is supplied, explicitly state that the action was NOT performed or verified and explain what the user must do themselves.
- Never invent tool calls, confirmations, execution logs, or success messages.
- The Reviewer must check every statement claiming that an action was completed against the supplied evidence. If evidence is absent, correct the claim.
Return the final deliverable in clear Markdown. Do not claim tests, independently verified facts, publishing, or external actions unless supplied evidence confirms them. Cite source URLs from the research report for claims supported by retrieved page text; label unresolved or weakly supported claims [VERIFY].

For youtube_package tasks, create a detailed faceless YouTube package: include a narrative thesis, scene-by-scene script with timecodes, Urdu narration with English technical terms unless requested otherwise, motion-graphics/compositing instructions, audio/editing notes, title/thumbnail/description options, Shorts cutdown, source register, and release QA. Match requested duration with plausible narration word counts; do not call a short outline a 15-minute script. Never invent facts, numbers, quotes, citations, or research. Mark unsupported claims [VERIFY] and state what evidence is needed. Distinguish source-supported details from assumptions. End with unresolved issues.

TASK TYPE: {kind}
TITLE: {task.get('title', '')}
REQUEST:
{task.get('input', '')[:max_chars]}

LOCAL WORKSPACE:
{context[:max_chars]}
"""

def process(task, cfg):
    kind = task.get("kind", "")
    if kind not in {"plan", "draft", "summarize_workspace", "review_output", "youtube_package"}:
        raise ValueError("Unsupported task type.")

    # Every queued task is sent to the CEO, who delegates distinct subtasks to specialists.
    title = str(task.get("title", "Untitled")).strip()
    user_request = str(task.get("input", "")).strip()
    goal = (
        "TASK TYPE: " + kind + "\n"
        "TASK TITLE: " + title + "\n"
        "USER REQUEST:\n" + user_request + "\n\n"
        "REQUIRED OUTCOME: produce the requested usable deliverable, not just advice about how to make it. "
        "Respect the task type, supplied constraints, privacy, and human approval boundaries. "
        "Specialists must research the task before working, use source-linked evidence where relevant, "
        "create their assigned deliverables, and pass unresolved issues forward. "
        "Do not claim an artifact was executed, rendered, uploaded, published, or externally verified unless the available tools and evidence confirm it."
    )
    context = workspace_text(cfg) if kind in {"summarize_workspace", "review_output"} else ""
    destination = (WORKSPACE / "orchestration" / ("task-" + safe_id(task.get("id")))).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    out_dir, manifest = run_ceo_pipeline(
        goal,
        context=context,
        agent_ids=None,
        output_dir=destination,
        config=cfg,
    )

    # Aggregate specialist deliverables into the queue's stable output path.
    sections = [
        "# CEO-led task result",
        "",
        "- Task ID: " + safe_id(task.get("id")),
        "- Task type: " + kind,
        "- Delegation mode: " + str(manifest.get("delegation_mode", "unknown")),
        "- Model enabled: " + str(bool(manifest.get("model_enabled"))),
        "- Specialist stages: " + str(len(manifest.get("pipeline", []))),
        "- Research: attempted by the CEO when model-enabled and by each specialist stage",
        "- Independent fact verification: not guaranteed; review source reports and claims",
        "",
        "## CEO delegation plan",
        "",
    ]
    for item in manifest.get("ceo_assignments", []):
        sections.append("- " + str(item.get("agent_id", "unknown")) + ": " + str(item.get("task", "")))
    sections.extend(["", "## Specialist deliverables", ""])
    total_chars = 0
    for record in manifest.get("pipeline", []):
        sections.extend(["### " + str(record.get("role", record.get("agent_id", "Specialist"))), ""])
        sections.append("- Status: " + str(record.get("status", "unknown")))
        if record.get("assigned_task"):
            sections.append("- Assigned task: " + str(record["assigned_task"]))
        output_file = record.get("output_file")
        if output_file:
            candidate = (out_dir / output_file).resolve()
            if out_dir.resolve() in candidate.parents and candidate.is_file():
                body = candidate.read_text(encoding="utf-8", errors="replace")[:12000]
                remaining = max(0, 48000 - total_chars)
                body = body[:remaining]
                sections.extend(["", body, ""])
                total_chars += len(body)
            else:
                sections.append("- Deliverable file was not found at the expected workspace location.")
        if record.get("error"):
            sections.append("- Error: " + str(record["error"])[:500])
        sections.append("")
        if total_chars >= 48000:
            sections.append("[Output aggregation truncated to the configured size limit.]")
            break
    if manifest.get("status") == "failed":
        sections.extend(["## Pipeline status", "", "The CEO pipeline stopped after a specialist failure. Review the saved pipeline manifest and logs before retrying.", ""])
    sections.extend(["", "## Built-in artifact tools", ""])
    if manifest.get("tool_runs"):
        for tool in manifest["tool_runs"]:
            sections.append("- " + str(tool.get("tool", "tool")) + ": " + str(tool.get("status", "unknown")))
            if tool.get("artifact_dir"):
                sections.append("  - Artifact directory: " + str(tool["artifact_dir"]))
            if tool.get("log_file"):
                sections.append("  - Tool log: " + str(tool["log_file"]))
            if tool.get("reason"):
                sections.append("  - Note: " + str(tool["reason"]))
            if tool.get("error"):
                sections.append("  - Error: " + str(tool["error"]))
    else:
        sections.append("- No additional built-in artifact tool was selected for this task.")
    sections.extend([
        "## Review requirements",
        "",
        "- Treat search snippets and extracted pages as evidence to evaluate, not automatic proof.",
        "- Check citations, dates, source independence, and whether each source supports its associated claim.",
        "- Confirm generated code, documents, renders, and other artifacts exist and meet the user's acceptance criteria.",
        "- External actions such as publishing, payments, deletion, or messaging remain approval-gated.",
        "",
        "## Pipeline manifest",
        "",
        "Saved at: " + str((out_dir / "pipeline-status.json").relative_to(BASE)),
    ])
    result = "\n".join(sections).rstrip() + "\n"
    OUTPUTS.mkdir(exist_ok=True)
    path = OUTPUTS / (safe_id(task.get("id")) + ".md")
    path.write_text(result, encoding="utf-8")

    request_text = " ".join(str(task.get(k, "")) for k in ("title", "input")).strip().lower()
    external_action_patterns = [
        r"\bset (?:an? )?alarm\b",
        r"\b(?:wake me|remind me|schedule (?:a )?reminder)\b",
        r"\bpublish (?:the|this|my|finished|final)\b",
        r"\bpublish\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file|draft)\b",
        r"\bupload (?:the|this|my|finished|final)\b",
        r"\bupload\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file|draft)\b",
        r"\bsend (?:the|this|an? email|a message|the message)\b",
        r"\bemail .+ to .+",
        r"\bpost (?:the|this|my|finished|final)\b",
        r"\bpost\s+(?:the\s+|this\s+|my\s+|a\s+|an\s+)?(?:video|short|content|file)\b",
        r"\bmake (?:a )?payment\b",
        r"\btransfer money\b",
        r"\b(?:transfer|send|withdraw)\s+(?:money|funds|payment|cash)\b",
        r"\b(?:purchase|buy|order)\s+(?:the|this|a|an|any|some)\b",
        r"\b(?:delete|erase|remove)\s+(?:all|every|any|the|this|my|these|those|files?|folders?|records?|data|account|task)\b",
        r"\bdelete (?:the|this|my)\b",
    ]
    import re
    needs_action = any(re.search(pattern, request_text, re.IGNORECASE) for pattern in external_action_patterns)
    if manifest.get("status") == "failed":
        task.update(
            status="failed",
            completed_at=stamp(),
            research_status="attempted_by_ceo_and_specialists",
            output_file=str(path.relative_to(BASE)),
            error="CEO pipeline or a required artifact builder failed. Partial output was saved; inspect the manifest and tool logs before retrying.",
        )
        log(f"FAILED {task.get('id')} -> partial output {path.name}")
    elif needs_action:
        task.update(
            status="needs_human_action",
            completed_at="",
            research_status="attempted_by_ceo_and_specialists",
            output_file=str(path.relative_to(BASE)),
            error="Deliverables generated only. This local system did not perform or verify the requested external action.",
        )
        log(f"NEEDS HUMAN ACTION {task.get('id')} -> {path.name}")
    else:
        task.update(
            status="completed",
            completed_at=stamp(),
            research_status="attempted_by_ceo_and_specialists",
            output_file=str(path.relative_to(BASE)),
            error="",
        )
        log(f"COMPLETED {task.get('id')} -> {path.name}")
    return path


def cycle(task_id=None):
    cfg = load(CONFIG, {})
    max_tasks = max(1, min(20, int(cfg.get("runner", {}).get("max_tasks_per_cycle", 3))))
    count = 0
    requested_task_id = task_id
    while count < max_tasks:
        with task_queue_lock(TASKS):
            tasks = load_tasks(TASKS)
            task = next((t for t in tasks if str(t.get("status", "pending")).lower() in {"pending", "queued"} and (requested_task_id is None or str(t.get("id", "")) == requested_task_id)), None)
            if task is None:
                break
            task_id = str(task.get("id", ""))
            if not task_id:
                task["status"] = "failed"
                task["error"] = "Task is missing an ID."
                save_tasks(TASKS, tasks)
                count += 1
                continue
            task["status"] = "running"
            task["started_at"] = stamp()
            task["error"] = ""
            save_tasks(TASKS, tasks)
        try:
            process(task, cfg)
            if task.get("status") == "failed":
                print(f"Failed {task_id}: {task.get('error', '')}")
            elif task.get("status") == "needs_human_action":
                print(f"Needs human action {task_id} -> {task.get('output_file', '')}")
            else:
                print(f"Completed {task_id} -> {task.get('output_file', '')}")
        except Exception as e:
            task.update(status="failed", error=str(e)[:400], completed_at=stamp())
            log(f"FAILED {task_id}: {type(e).__name__}: {e}")
            print(f"Failed {task_id}: {type(e).__name__}: {e}")
        with task_queue_lock(TASKS):
            latest = load_tasks(TASKS)
            match = next((item for item in latest if str(item.get("id", "")) == task_id), None)
            if match is not None:
                match.update({k: v for k, v in task.items() if k in {
                    "status", "started_at", "completed_at", "output_file", "error", "research_status"
                }})
                save_tasks(TASKS, latest)
        count += 1
        if requested_task_id is not None:
            break
    if count == 0:
        print("No pending tasks.")
    return count

def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=None)
    ap.add_argument("--task-id", help="Process only this exact existing local task ID")
    args = ap.parse_args()
    if args.loop:
        cfg = load(CONFIG, {})
        interval = max(10, args.interval or int(cfg.get("runner", {}).get("interval_seconds", 60)))
        print(f"Agent loop running every {interval}s. Ctrl+C to stop.")
        try:
            while True:
                cycle(args.task_id)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        cycle(args.task_id)

if __name__ == "__main__":
    main()
