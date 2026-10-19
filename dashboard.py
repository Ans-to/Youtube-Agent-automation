#!/usr/bin/env python3
"""Holographic, loopback-only Offline Agent HQ dashboard; Python stdlib only."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from datetime import datetime
import json, html, subprocess, sys, threading, mimetypes, re
from queue_store import task_queue_lock, load_tasks, save_tasks

BASE = Path(__file__).resolve().parent
TASKS = BASE / "tasks.json"
CONFIG = BASE / "config.json"
OUTPUTS = BASE / "outputs"
LOGS = BASE / "logs"
AGENTS = BASE / "agents" / "roster.json"
RUN_LOCK = threading.Lock()
RUNNING = False
PIPELINE_LOCK = threading.Lock()
PIPELINE_RUNNING = False
PIPELINE_LAST_OUTPUT = ""
VIDEO_RUNNING = False
VIDEO_LAST_OUTPUT = ""
PRODUCT_RUNNING = False
PRODUCT_LAST_OUTPUT = ""
TRAINING_RUNNING = False
TRAINING_LAST_OUTPUT = ""
VIDEO_LOCK = threading.Lock()
PRODUCT_LOCK = threading.Lock()
ACTIVE_WORKFLOW = ""
ACTIVE_WORKFLOW_LOCK = threading.Lock()


def try_claim_workflow(name):
    global ACTIVE_WORKFLOW
    with ACTIVE_WORKFLOW_LOCK:
        if ACTIVE_WORKFLOW:
            return False, ACTIVE_WORKFLOW
        ACTIVE_WORKFLOW = name
        return True, ""


def release_workflow(name):
    global ACTIVE_WORKFLOW
    with ACTIVE_WORKFLOW_LOCK:
        if ACTIVE_WORKFLOW == name:
            ACTIVE_WORKFLOW = ""

def load(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def esc(v): return html.escape(str(v), quote=True)

def render_markdown_safe(source):
    """Render a safe, readable subset of Markdown without executing generated HTML."""
    output = []
    list_tag = None

    def close_list():
        nonlocal list_tag
        if list_tag:
            output.append("</" + list_tag + ">")
            list_tag = None

    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            output.append("<h" + str(level) + ">" + esc(heading.group(2)) + "</h" + str(level) + ">")
        elif line.startswith("- "):
            if list_tag != "ul":
                close_list()
                output.append("<ul>")
                list_tag = "ul"
            output.append("<li>" + esc(line[2:]) + "</li>")
        elif re.match(r"^\d+\.\s+", line):
            if list_tag != "ol":
                close_list()
                output.append("<ol>")
                list_tag = "ol"
            output.append("<li>" + esc(re.sub(r"^\d+\.\s+", "", line)) + "</li>")
        elif line == "---":
            close_list()
            output.append("<hr>")
        elif line.startswith("> "):
            close_list()
            output.append("<blockquote>" + esc(line[2:]) + "</blockquote>")
        else:
            close_list()
            safe = esc(line)
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
            output.append("<p>" + safe + "</p>")
    close_list()
    return "\n".join(output)


def task_state():
    raw_tasks = load(TASKS, [])
    tasks = [t for t in raw_tasks if isinstance(t, dict)] if isinstance(raw_tasks, list) else []
    counts = {k: sum(1 for t in tasks if str(t.get("status", "pending")).lower() == k) for k in ("running", "completed", "failed", "needs_human_action")}
    counts["pending"] = sum(1 for t in tasks if str(t.get("status", "pending")).lower() in {"pending", "queued"})
    cfg = load(CONFIG, {})
    model = cfg.get("model", {})
    return {"tasks": tasks[-100:], "counts": counts, "model_enabled": bool(model.get("enabled")),
            "model_name": model.get("model", "local-model"), "running": RUNNING, "active_workflow": ACTIVE_WORKFLOW, "pipeline_running": PIPELINE_RUNNING, "pipeline_output": PIPELINE_LAST_OUTPUT,
            "video_running": VIDEO_RUNNING, "video_output": VIDEO_LAST_OUTPUT,
            "product_running": PRODUCT_RUNNING, "product_output": PRODUCT_LAST_OUTPUT,
            "training_running": TRAINING_RUNNING, "training_output": TRAINING_LAST_OUTPUT,
            "pipeline": ["CEO Coordinator", "Researching Specialists", "Assigned Workers", "Quality Reviewer"],
            "updated": datetime.now().astimezone().isoformat(timespec="seconds"), "agent_roster": load(AGENTS, {}).get("agents", [])}


def enqueue_task(title, kind, user_input, context_file=""):
    """Persist one validated task for the CEO-led queue runner."""
    title = str(title or "").strip()[:160]
    user_input = str(user_input or "").strip()[:6000]
    if not title or not user_input or kind not in {"plan", "draft", "summarize_workspace", "review_output", "youtube_package"}:
        raise ValueError("Invalid task title, workflow, or instructions.")
    with task_queue_lock(TASKS):
        tasks = load_tasks(TASKS)
        nums = [
            int(str(t.get("id", "TASK-0000")).split("-")[-1])
            for t in tasks
            if str(t.get("id", "")).startswith("TASK-")
            and str(t.get("id", "")).split("-")[-1].isdigit()
        ]
        task_id = "TASK-%04d" % (max(nums, default=0) + 1)
        item = {"id": task_id, "title": title, "kind": kind, "input": user_input,
                "status": "pending", "error": "", "research_status": "pending"}
        if context_file:
            item["context_file"] = str(context_file)
        tasks.append(item)
        save_tasks(TASKS, tasks)
    return task_id

HTML_PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#09070b"><meta name="description" content="Local-first AI agent command centre for task management, video production, and digital product prototyping."><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/icon.svg" type="image/svg+xml"><title>Offline Agent HQ // Command Deck</title>
<style>
:root{--bg:#08070b;--panel:#111016;--panel2:#17121b;--line:#51211e;--red:#ff3b2f;--orange:#ff8a32;--gold:#ffc56c;--muted:#a99ca5;--text:#f8edf0;--green:#72f6b2;--blue:#73dfff;--radius:16px}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% 38%,#281016 0,#0b080e 42%,#050509 100%);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;min-height:100vh}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.14;background-image:linear-gradient(#ff5a3514 1px,transparent 1px),linear-gradient(90deg,#ff5a3514 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,black,transparent 90%)}
header{position:relative;padding:20px 16px 14px;border-bottom:1px solid #6b292a;background:#0a080de8;box-shadow:0 5px 28px #ff2b2010;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}.logo{width:43px;height:43px;border:1px solid var(--orange);border-radius:13px;display:grid;place-items:center;color:var(--gold);font-size:23px;box-shadow:0 0 20px #ff4a2a36,inset 0 0 15px #ff4a2a19}.brand h1{font-size:20px;letter-spacing:.12em;margin:0;font-weight:800}.brand p{margin:3px 0 0;color:var(--muted);font-size:11px;letter-spacing:.1em;text-transform:uppercase}.live{border:1px solid #305743;background:#102219;color:var(--green);border-radius:99px;padding:7px 11px;font-size:11px;letter-spacing:.08em;white-space:nowrap}.live i{display:inline-block;width:7px;height:7px;background:var(--green);border-radius:50%;margin-right:7px;box-shadow:0 0 10px var(--green)}
main{max-width:1250px;margin:auto;padding:16px;position:relative}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.metric,.panel{background:linear-gradient(145deg,#17121bdf,#0d0b11f5);border:1px solid #4b2429;border-radius:var(--radius);box-shadow:0 8px 24px #0006,inset 0 0 22px #ff462a05}.metric{padding:12px 13px;min-width:0}.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.15em;color:var(--muted)}.num{font-size:25px;font-weight:800;margin-top:4px;color:var(--gold);text-shadow:0 0 16px #ff8a3240}.layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:14px}.panel{padding:15px;margin-bottom:14px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:13px}.panel h2{font-size:13px;text-transform:uppercase;letter-spacing:.14em;margin:0}.tag{font-size:10px;color:var(--orange);border:1px solid #69312b;border-radius:6px;padding:4px 7px;text-transform:uppercase;letter-spacing:.08em}
.deck{min-height:370px;position:relative;overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:center;background:radial-gradient(ellipse at center,#39151b44 0,transparent 63%),linear-gradient(135deg,#171019,#0b090f)}.deck:before,.deck:after{content:"";position:absolute;border:1px solid #ff4a2b65;border-radius:50%;width:240px;height:240px;box-shadow:0 0 25px #ff39241a,inset 0 0 24px #ff39241a;transform:rotateX(62deg)}.deck:after{width:320px;height:320px;border-color:#ff8a3233}.core{position:relative;z-index:2;width:112px;height:112px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle,#ffb15b 0,#ff502f 20%,#44121c 55%,#140b15 75%);border:1px solid #ffac60;box-shadow:0 0 18px #ff4a2a,0 0 55px #ff311d66,inset 0 0 25px #ffcf6b45;animation:pulse 3s ease-in-out infinite}.core svg{width:72px;filter:drop-shadow(0 0 7px #ffba68)}.core-label{position:relative;z-index:2;margin-top:12px;padding:7px 14px;border:1px solid #a44a34;background:#190d13;border-radius:7px;font-size:11px;letter-spacing:.16em;color:#ffd19b;box-shadow:0 0 20px #ff402233}.connections{position:absolute;inset:0;width:100%;height:100%;z-index:1;pointer-events:none}.connections line{stroke:#ff4c34;stroke-width:1;stroke-dasharray:4 7;opacity:.6;animation:dash 8s linear infinite}.nodes{position:absolute;z-index:3;inset:12px;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;pointer-events:none}.node{align-self:start;justify-self:start;border:1px solid #8e382d;background:#150c13eF;color:#ffe0c2;padding:7px 9px;border-radius:8px;font-size:10px;box-shadow:0 0 16px #ff4c2a1c;max-width:125px}.node:nth-child(2){justify-self:end}.node:nth-child(3){align-self:end}.node:nth-child(4){align-self:end;justify-self:end}.node b{display:block;font-size:11px}.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--green);margin-right:5px;box-shadow:0 0 8px currentColor}.hint{position:absolute;bottom:10px;left:12px;right:12px;text-align:center;color:#9d858c;font-size:10px;letter-spacing:.06em;z-index:2}
.agent-list{display:grid;grid-template-columns:1fr 1fr;gap:8px}.agent{padding:10px;border:1px solid #3d252d;border-radius:10px;background:#100d13;display:flex;align-items:center;gap:9px}.agent-icon{width:30px;height:30px;flex-shrink:0;border:1px solid #78392d;border-radius:9px;display:grid;place-items:center;color:var(--orange);background:#251017}.agent strong{font-size:11px;display:block}.agent small{color:var(--muted);font-size:10px}.agent .state{margin-left:auto;color:var(--green);font-size:9px;text-transform:uppercase}
form label{display:block;color:#ddcbd0;font-size:11px;margin:10px 0 5px;letter-spacing:.04em}input,select,textarea{width:100%;border:1px solid #54333e;border-radius:9px;background:#09080e;color:var(--text);padding:12px;font:inherit;outline:none}input:focus,select:focus,textarea:focus{border-color:var(--orange);box-shadow:0 0 0 2px #ff8a321b}textarea{min-height:100px;resize:vertical}button,.btn{border:1px solid #ff7542;border-radius:9px;background:linear-gradient(100deg,#ff4b31,#ff9c3e);color:#1a0908;font-weight:800;padding:12px 14px;width:100%;cursor:pointer;letter-spacing:.03em;box-shadow:0 0 18px #ff4b2a1b}button:active{transform:translateY(1px)}button.secondary{background:#171019;color:#ffbd86;border-color:#65352d;box-shadow:none}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.task{border:1px solid #38232b;background:#100d13;border-radius:11px;padding:12px;margin:8px 0}.task-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.task h3{font-size:13px;margin:0 0 5px;overflow-wrap:anywhere}.task p{font-size:12px;color:#b7a8b0;margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}.status{font-size:9px;letter-spacing:.07em;text-transform:uppercase;border-radius:99px;padding:4px 7px;border:1px solid #604c37;color:var(--gold);white-space:nowrap}.status.completed{color:var(--green);border-color:#275941}.status.failed{color:#ff777d;border-color:#793139}.status.running{color:var(--blue);border-color:#285a70}.task-links{display:flex;gap:12px;flex-wrap:wrap;font-size:11px}.task-links a{color:var(--orange);text-decoration:none}.task-links a:hover{text-decoration:underline}.empty{padding:18px;text-align:center;color:var(--muted);border:1px dashed #4a3038;border-radius:10px}.foot{text-align:center;color:#766873;font-size:10px;padding:4px 0 22px}.error{color:#ff8588;font-size:12px;white-space:pre-wrap}.toast{position:fixed;z-index:9;bottom:20px;left:50%;transform:translateX(-50%);background:#24141b;border:1px solid #a84a35;padding:10px 14px;border-radius:10px;display:none;max-width:90vw}
@keyframes pulse{0%,100%{transform:scale(.98);filter:brightness(.95)}50%{transform:scale(1.04);filter:brightness(1.18)}}@keyframes dash{to{stroke-dashoffset:-100}}
.quick-nav{display:flex;gap:8px;overflow-x:auto;padding:10px 16px;background:#0c0a10;border-bottom:1px solid #38232b;position:sticky;top:0;z-index:8;scrollbar-width:thin}.quick-nav a{flex:0 0 auto;color:#ffbd86;text-decoration:none;border:1px solid #55312e;border-radius:99px;padding:8px 12px;font-size:11px;white-space:nowrap}.quick-nav a:focus,.quick-nav a:hover{border-color:var(--orange);background:#211019}.panel{scroll-margin-top:65px}@media(min-width:850px){main{padding:22px}.deck{min-height:430px}.panel{padding:18px}}@media(max-width:720px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.deck{min-height:350px}.brand h1{font-size:17px}header{padding:15px 13px}main{padding:12px}.agent-list{grid-template-columns:1fr 1fr}}@media(max-width:390px){.agent-list{grid-template-columns:1fr}.deck{min-height:330px}.nodes{inset:7px}.node{font-size:9px;max-width:110px}}
</style></head><body>
<header><div class="brand"><div class="logo">⌘</div><div><h1>OFFLINE AGENT HQ</h1><p>Local intelligence // command deck</p></div></div><div class="live"><i></i><span id="liveText">LOCAL SYSTEM</span></div></header>
<nav class="quick-nav" aria-label="Quick navigation"><a href="#task-intake">New task</a><a href="#video-studio">Video studio</a><a href="#product-studio">Product studio</a><a href="#specialist-pipeline">Agent pipeline</a><a href="#system-activity">Activity</a><a href="#generated-outputs">Results</a></nav>
<main>
<section class="metrics"><div class="metric"><div class="eyebrow">Total tasks</div><div class="num" id="total">0</div></div><div class="metric"><div class="eyebrow">In queue</div><div class="num" id="pending">0</div></div><div class="metric"><div class="eyebrow">Completed</div><div class="num" id="completed">0</div></div><div class="metric"><div class="eyebrow">Failed</div><div class="num" id="failed">0</div></div><div class="metric"><div class="eyebrow">Needs human action</div><div class="num" id="needsHuman">0</div></div></section>
<div class="layout"><div>
<section class="panel deck"><div class="panel-head" style="position:absolute;top:15px;left:15px;right:15px;z-index:4"><h2>Neural command core</h2><span class="tag" id="modelTag">checking model</span></div>
<svg class="connections" viewBox="0 0 600 420" preserveAspectRatio="none"><line x1="300" y1="210" x2="100" y2="95"/><line x1="300" y1="210" x2="500" y2="95"/><line x1="300" y1="210" x2="100" y2="325"/><line x1="300" y1="210" x2="500" y2="325"/></svg>
<div class="nodes"><div class="node"><b>01 / CEO</b><span class="dot"></span>Task routing</div><div class="node"><b>02 / PLANNER</b><span class="dot"></span>Breakdown</div><div class="node"><b>03 / WORKER</b><span class="dot"></span>Execution</div><div class="node"><b>04 / REVIEWER</b><span class="dot"></span>Quality check</div></div>
<div class="core"><svg viewBox="0 0 100 100" fill="none" stroke="#ffe0a0" stroke-width="2"><path d="M50 13c-13-9-28 1-26 15-14 5-13 23-3 29-5 15 5 26 18 24l11 7 11-7c13 2 23-9 18-24 10-6 11-24-3-29 2-14-13-24-26-15Z"/><path d="M50 14v72M24 30l19 10-8 15 14 10M76 30 57 40l8 15-14 10M22 57l20 4M78 57l-20 4M39 80l11-16 11 16"/></svg></div><div class="core-label">CEO COMMAND CORE</div><div class="hint">LOCAL-FIRST · HUMAN-CONTROLLED · NO CLOUD API</div></section>
<section class="panel" id="task-intake"><div class="panel-head"><h2>Task intake</h2><span class="tag">CEO-managed queue</span></div><p style="color:var(--muted);font-size:11px">All queued tasks are routed through the CEO, who delegates research and execution to specialist roles before the result is marked complete.</p><form method="post" action="/add"><label for="title">TASK TITLE</label><input id="title" name="title" maxlength="160" required placeholder="e.g. Build a faceless video plan"><label for="kind">WORKFLOW</label><select id="kind" name="kind"><option value="youtube_package">YouTube production package (detailed)</option><option value="plan">Plan / strategy</option><option value="draft">Draft content</option><option value="summarize_workspace">Summarize local workspace</option><option value="review_output">Review local workspace</option></select><label for="input">INSTRUCTIONS</label><textarea id="input" name="input" maxlength="6000" required placeholder="Describe the result, constraints, and format you need..."></textarea><button type="submit">＋ QUEUE TASK</button></form><div class="actions"><form method="post" action="/run"><button type="submit">▶ RUN PENDING</button></form><form method="post" action="/refresh"><button class="secondary" type="submit">↻ REFRESH STATE</button></form></div><p class="error" id="runInfo"></p></section>
</div><div>
<section class="panel"><div class="panel-head"><h2>Specialist practice lab</h2><span class="tag">Human-reviewed improvement</span></div><p style="color:var(--muted);font-size:11px">Run a role-specific practice task. Review the artifact and score every quality gate in Termux; only human-reviewed feedback is re-used. No model weights are changed.</p><form method="post" action="/practice-agent"><label for="practiceAgent">SPECIALIST</label><select id="practiceAgent" name="agent_id"><option value="AGENT-51">AGENT-51 / Motion Graphics Creative Director</option><option value="AGENT-52">AGENT-52 / Motion Systems & Compositing Specialist</option><option value="ALL">BATCH / Practice selected number of all specialists</option></select><label for="practiceLimit">BATCH SIZE (1–51; set 51 for all executable roles)</label><input id="practiceLimit" name="limit" type="number" min="1" max="51" value="5"><label for="practiceTask">PRACTICE TASK</label><textarea id="practiceTask" name="task" maxlength="6000" required placeholder="Give the specialist a concrete assignment and expected output..."></textarea><label for="practiceContext">OPTIONAL SOURCE FILE (inside workspace)</label><input id="practiceContext" name="context_file" maxlength="500" placeholder="workspace/source-notes.md"><button type="submit">RUN SPECIALIST PRACTICE</button></form><p id="trainingInfo" style="color:var(--muted);font-size:11px;overflow-wrap:anywhere">No practice run has started in this session.</p></section><section class="panel" id="video-studio"><div class="panel-head"><h2>Video studio</h2><span class="tag">Local render pipeline</span></div><p style="color:var(--muted);font-size:11px">Build an outline, scene-by-scene script, storyboard, optional source-search leads, and optional MP4. Review the package before release; nothing is uploaded automatically.</p><form method="post" action="/generate-video"><label for="videoTopic">VIDEO TOPIC</label><input id="videoTopic" name="topic" maxlength="500" required placeholder="e.g. How AI agents are changing software"><label for="videoFormat">FORMAT</label><select id="videoFormat" name="format"><option value="long">Long-form (default target 15 min)</option><option value="shorts">Shorts (default target 1 min)</option></select><label for="videoMinutes">TARGET MINUTES (0.25–16)</label><input id="videoMinutes" name="target_minutes" type="number" min="0.25" max="16" step="0.25" placeholder="Leave blank for format default"><label for="videoSources">SOURCE NOTES FILE (optional, inside workspace)</label><input id="videoSources" name="source_file" maxlength="500" placeholder="workspace/source-notes.md"><label><input type="checkbox" name="research" value="yes"> Collect free web-search leads (not fact-checked)</label><label for="videoMode">OUTPUT MODE</label><select id="videoMode" name="render_mode"><option value="draft">Draft package only</option><option value="render">Generate and render MP4 (requires local model)</option><option value="template">Render explicit 20-second template demo (no AI)</option></select><label><input type="checkbox" name="with_voice" value="yes"> Add local Piper narration (requires voice model; only with MP4 rendering)</label><button type="submit">QUEUE VIDEO TASK FOR CEO</button></form><p id="videoInfo" style="color:var(--muted);font-size:11px;overflow-wrap:anywhere">No video package has run in this session.</p></section>
<section class="panel" id="product-studio"><div class="panel-head"><h2>Digital product studio</h2><span class="tag">Local prototype</span></div><p style="color:var(--muted);font-size:11px">Generate a draft HTML utility and ZIP package. Review the code and test it before real use or selling.</p><form method="post" action="/build-product"><label for="productTitle">PRODUCT TITLE</label><input id="productTitle" name="product_title" maxlength="100" required placeholder="e.g. Invoice Helper"><label for="productIdea">PRODUCT IDEA / USER PROBLEM</label><textarea id="productIdea" name="product_idea" maxlength="1000" required placeholder="Describe the problem, target user, and core utility..."></textarea><button type="submit">QUEUE PRODUCT TASK FOR CEO</button></form><p id="productInfo" style="color:var(--muted);font-size:11px;overflow-wrap:anywhere">No product package has run in this session.</p></section><section class="panel" id="specialist-pipeline"><div class="panel-head"><h2>CEO Command Deck</h2><span class="tag">CEO-led delegation</span></div><p style="color:var(--muted);font-size:11px">Give the task to the CEO. The CEO selects specialist roles, assigns distinct subtasks, and sends each specialist into its own research-before-work cycle. You may optionally override the CEO with specific role IDs. Template mode is not general-purpose AI; review every deliverable.</p><form method="post" action="/run-pipeline"><label for="pipelineTask">PIPELINE GOAL</label><textarea id="pipelineTask" name="task" maxlength="6000" required placeholder="e.g. Create a fact-checkable Urdu tech video script and scene plan"></textarea><label for="pipelineAgents">OPTIONAL SPECIALIST OVERRIDE (leave blank for CEO delegation)</label><input id="pipelineAgents" name="agents" maxlength="500" placeholder="Leave blank: CEO chooses the team; or AGENT-02,AGENT-08"><label for="pipelineContext">OPTIONAL LOCAL SOURCE FILE PATH</label><input id="pipelineContext" name="context_file" maxlength="500" placeholder="workspace/source-notes.md"><button type="submit">RUN SPECIALIST PIPELINE</button></form><p id="pipelineInfo" style="color:var(--muted);font-size:11px;overflow-wrap:anywhere">Latest pipeline output path will appear here.</p></section><section class="panel"><div class="panel-head"><h2>Specialist roster</h2><span class="tag" id="rosterCount">52 role profiles</span></div><p style="color:var(--muted);font-size:11px;margin:0 0 10px">Configured specialist roles for the local workflow. They are profiles, not 50 separate running models.</p><details><summary style="cursor:pointer;color:var(--orange);padding:8px 0">View all specialist profiles</summary><div id="agentRoster" class="agent-list"></div></details></section><section class="panel" id="system-activity"><div class="panel-head"><h2>System activity</h2><span class="tag" id="updated">live refresh</span></div><div id="activity"><div class="empty">Loading task activity…</div></div></section>
<section class="panel" id="generated-outputs"><div class="panel-head"><h2>Generated outputs</h2><span class="tag">Local files</span></div><div id="outputs"><div class="empty">Outputs appear here after a task completes.</div></div></section>
</div></div><div class="foot">OFFLINE AGENT HQ · Dashboard bound to loopback only · Keep Termux sessions open for processing</div></main><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);let lastState='';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2600)}
async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();$('total').textContent=d.tasks.length;$('pending').textContent=d.counts.pending+d.counts.running;$('completed').textContent=d.counts.completed;$('failed').textContent=d.counts.failed;$('needsHuman').textContent=d.counts.needs_human_action||0;$('modelTag').textContent=d.model_enabled?'MODEL CONFIGURED':'TEMPLATE MODE';$('modelTag').style.color=d.model_enabled?'var(--green)':'var(--gold)';$('liveText').textContent=d.video_running?'VIDEO STUDIO':(d.product_running?'PRODUCT STUDIO':(d.pipeline_running?'SPECIALIST PIPELINE':(d.running?'PROCESSING TASK':'LOCAL SYSTEM')));if($('pipelineInfo'))$('pipelineInfo').textContent=d.pipeline_output?'Latest output: '+d.pipeline_output:'No specialist pipeline has run in this session.';if($('videoInfo'))$('videoInfo').textContent=(d.video_running?'Video generation running. ':'')+(d.video_output?'Latest video package: '+d.video_output:'No video package has run in this session.');if($('productInfo'))$('productInfo').textContent=(d.product_running?'Product prototype running. ':'')+(d.product_output?'Latest product package: '+d.product_output:'No product package has run in this session.');$('updated').textContent=new Date(d.updated).toLocaleTimeString();
const roles=Array.isArray(d.agent_roster)?d.agent_roster:[];$('rosterCount').textContent=roles.length+' role profiles';$('agentRoster').innerHTML=roles.map(a=>'<div class="agent"><div class="agent-icon">◈</div><div><strong>'+esc(a.id)+' / '+esc(a.name)+'</strong><small>'+esc(a.department)+' — '+esc(a.mission)+'</small></div><span class="state">'+(a.approval_required?'Approval':'Profile')+'</span></div>').join('')||'<div class="empty">Roster file not found.</div>';const practiceSelect=$('practiceAgent');if(practiceSelect){const prior=practiceSelect.value;const allowed=roles.filter(a=>!a.approval_required&&a.id!=='AGENT-50');practiceSelect.innerHTML='<option value="ALL">BATCH / Practice selected number of all specialists</option>'+allowed.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.id)+' / '+esc(a.name)+'</option>').join('');if(allowed.some(a=>a.id===prior))practiceSelect.value=prior;else if(allowed.some(a=>a.id==='AGENT-51'))practiceSelect.value='AGENT-51';}$('trainingInfo').textContent=(d.training_running?'Practice run running. ':'')+(d.training_output?'Latest practice output root: '+d.training_output:'No practice run has started in this session.');const recent=[...d.tasks].reverse().slice(0,8);$('activity').innerHTML=recent.length?recent.map(t=>`<article class="task"><div class="task-top"><div><h3>${esc(t.title||'Untitled')}</h3><div class="eyebrow">${esc(t.id)} · ${esc(t.kind)}</div></div><span class="status ${esc(t.status||'pending')}">${esc(t.status||'pending')}</span></div>${t.error?`<p class="error">${esc(t.error)}</p>`:''}<div class="task-links">${t.output_file?`<a href="/output?id=${encodeURIComponent(t.id)}">Open generated output ↗</a>`:''}<a href="/task?id=${encodeURIComponent(t.id)}">Task details</a></div></article>`).join(''):'<div class="empty">No tasks queued yet. Create your first operation.</div>';
const done=[...d.tasks].reverse().filter(t=>t.output_file).slice(0,6);$('outputs').innerHTML=done.length?done.map(t=>`<div class="task"><div class="task-top"><div><h3>${esc(t.title||t.id)}</h3><div class="eyebrow">${esc(t.output_file)}</div></div><a class="tag" href="/output?id=${encodeURIComponent(t.id)}">OPEN</a></div></div>`).join(''):'<div class="empty">No output files recorded yet.</div>';
}catch(e){$('liveText').textContent='DASHBOARD API ERROR';$('activity').innerHTML='<div class="empty">Could not refresh state: '+esc(e.message)+'</div>'}}
refresh();setInterval(refresh,4000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/service-worker.js').catch(()=>{});}
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send(self, body, content_type="text/html; charset=utf-8", status=200):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        parsed = urlparse(self.path); path = parsed.path; query = parse_qs(parsed.query)
        # Serve only fixed, repository-owned PWA assets; never accept arbitrary file paths.
        static_assets = {
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
            "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8"),
            "/icon.svg": ("icon.svg", "image/svg+xml; charset=utf-8"),
            "/offline.html": ("offline.html", "text/html; charset=utf-8"),
        }
        if path in static_assets:
            file_name, content_type = static_assets[path]
            try:
                asset = (BASE / "web" / file_name).read_text(encoding="utf-8")
            except OSError:
                return self.send("PWA asset unavailable", status=503)
            return self.send(asset, content_type)
        if path == "/": return self.send(HTML_PAGE)
        if path == "/api/state": return self.send(json.dumps(task_state()), "application/json; charset=utf-8")
        if path == "/health": return self.send(json.dumps({"status":"ok","task_count":len(load(TASKS, []))}), "application/json; charset=utf-8")
        if path in {"/task", "/output"}:
            task_id = query.get("id", [""])[0]
            task = next((t for t in load(TASKS, []) if t.get("id") == task_id), None)
            if not task: return self.send("Task not found", status=404)
            if path == "/task":
                body = "<h2>"+esc(task.get("title"))+"</h2><p><b>Status:</b> "+esc(task.get("status"))+"</p><p><b>Request</b></p><pre>"+esc(task.get("input"))+"</pre>"
                if task.get("error"): body += "<p style='color:#ff777d'><b>Error:</b> "+esc(task["error"])+"</p>"
                if task.get("output_file"): body += "<p><a href='/output?id="+esc(task_id)+"'>Open output</a></p>"
                return self.send("<!doctype html><meta name='viewport' content='width=device-width'><body style='font:16px system-ui;background:#0b090e;color:#f8edf0;padding:20px'><a style='color:#ff9c3e' href='/'>← Dashboard</a>"+body+"</body>")
            rel = task.get("output_file", "")
            candidate = (BASE / rel).resolve()
            if not rel or BASE not in candidate.parents or not candidate.is_file(): return self.send("Output file not found", status=404)
            content = candidate.read_text(encoding="utf-8", errors="replace")
            # Render Markdown as safe preformatted text; no JS or HTML from task output is executed.
            return self.send("<!doctype html><meta name='viewport' content='width=device-width'><title>"+esc(task.get("title"))+"</title><style>body{font:16px/1.65 system-ui;background:#09080e;color:#f8edf0;padding:16px;max-width:980px;margin:auto}.doc{background:#141019;border:1px solid #512b31;border-radius:16px;padding:clamp(16px,4vw,32px);overflow-wrap:anywhere}h1,h2,h3{color:#ffd19b;line-height:1.25}h2{margin-top:28px;border-bottom:1px solid #54333e;padding-bottom:8px}a{color:#ffbd86}li{margin:7px 0}blockquote{border-left:3px solid #ff8a32;padding-left:12px;color:#d8bdc6}hr{border:0;border-top:1px solid #54333e}p{margin:12px 0}</style><a href='/'>← Dashboard</a><p style='color:#a99ca5'>"+esc(rel)+"</p><article class='doc'><h1>"+esc(task.get("title"))+"</h1>"+render_markdown_safe(content)+"</article></body>")
        return self.send("Not found", status=404)

    def do_POST(self):
        global RUNNING
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send("Invalid Content-Length.", status=400)
        if length < 0 or length > 12000:
            return self.send("Request body must not exceed 12000 bytes.", status=413)
        origin = self.headers.get("Origin")
        if origin:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme != "http" or parsed_origin.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed_origin.port != self.server.server_port:
                return self.send("Cross-origin POST requests are not allowed.", status=403)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        if path == "/add":
            title = form.get("title", [""])[0].strip()[:160]
            kind = form.get("kind", ["plan"])[0]
            user_input = form.get("input", [""])[0].strip()[:6000]
            try:
                enqueue_task(title, kind, user_input)
            except (TimeoutError, ValueError, OSError) as exc:
                return self.send("Could not safely queue task: " + esc(type(exc).__name__), status=503)
            return self._redirect("/")
        if path == "/practice-agent":
            global TRAINING_RUNNING, TRAINING_LAST_OUTPUT
            agent_id = form.get("agent_id", [""])[0].strip().upper()
            task = form.get("task", [""])[0].strip()
            context_file = form.get("context_file", [""])[0].strip()
            roster = load(AGENTS, {}).get("agents", [])
            batch_mode = agent_id == "ALL"
            batch_limit = 5
            if batch_mode:
                try:
                    batch_limit = int(form.get("limit", ["5"])[0])
                except ValueError:
                    return self.send("Batch size must be a whole number from 1 to 51.", status=400)
                if not 1 <= batch_limit <= 51:
                    return self.send("Batch size must be from 1 to 51. Use 51 to practice every executable specialist role.", status=400)
            else:
                role = next((r for r in roster if r.get("id") == agent_id), None)
                if not role or role.get("approval_required") or agent_id == "AGENT-50":
                    return self.send("Select an executable specialist. The human approval gate cannot be run automatically.", status=400)
            if not task or len(task) > 6000:
                return self.send("Practice task must contain 1–6000 characters.", status=400)
            if context_file:
                if len(context_file) > 500 or Path(context_file).suffix.lower() not in {".txt", ".md", ".json"}:
                    return self.send("Context path must point to a .txt, .md, or .json file inside workspace.", status=400)
                workspace = (BASE / "workspace").resolve()
                supplied = Path(context_file).expanduser()
                resolved_context = (BASE / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
                if resolved_context == workspace or workspace not in resolved_context.parents or not resolved_context.is_file():
                    return self.send("Context file must be an existing file inside workspace.", status=400)
                context_file = str(resolved_context)
            workflow_name = "specialist practice batch" if batch_mode else "specialist practice"
            claimed, active = try_claim_workflow(workflow_name)
            if not claimed:
                return self.send("Another workflow is already running: "+esc(active)+".", status=409)
            TRAINING_RUNNING = True
            run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
            TRAINING_LAST_OUTPUT = "workspace/training/runs/dashboard-" + run_id
            def run_practice():
                global TRAINING_RUNNING
                try:
                    LOGS.mkdir(exist_ok=True)
                    command = [sys.executable, str(BASE / "agents" / "practice.py"), "practice"]
                    if batch_mode:
                        command.extend(["--all", "--limit", str(batch_limit)])
                    else:
                        command.extend(["--agent", agent_id])
                    command.extend(["--task", task, "--out", TRAINING_LAST_OUTPUT])
                    if context_file:
                        command.extend(["--context-file", context_file])
                    timeout_seconds = 14400 if batch_mode else 3600
                    with (LOGS / "training.log").open("a", encoding="utf-8") as log_file:
                        log_file.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] Practice started: {'batch size '+str(batch_limit) if batch_mode else agent_id}\n")
                        try:
                            result = subprocess.run(command, cwd=str(BASE), stdout=log_file,
                                                    stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False)
                            log_file.write(f"Practice exit code: {result.returncode}\n")
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            log_file.write(f"Practice error: {type(exc).__name__}\n")
                finally:
                    TRAINING_RUNNING = False
                    release_workflow(workflow_name)
            threading.Thread(target=run_practice, daemon=True).start()
            return self._redirect("/")
        if path == "/generate-video":
            topic = form.get("topic", [""])[0].strip()
            fmt = form.get("format", ["long"])[0].strip().lower()
            mode = form.get("render_mode", ["draft"])[0].strip().lower()
            source_file = form.get("source_file", [""])[0].strip()
            do_research = form.get("research", [""])[0] == "yes"
            with_voice = form.get("with_voice", [""])[0] == "yes"
            if not topic or len(topic) > 500 or fmt not in {"long", "shorts"} or mode not in {"draft", "render", "template"}:
                return self.send("Invalid video request. Check topic, format, and output mode.", status=400)
            target_raw = form.get("target_minutes", [""])[0].strip()
            target_minutes = None
            if target_raw:
                try:
                    target_minutes = float(target_raw)
                except ValueError:
                    return self.send("Target minutes must be a number between 0.25 and 16.", status=400)
                if not 0.25 <= target_minutes <= 16:
                    return self.send("Target minutes must be between 0.25 and 16.", status=400)
            if with_voice and mode != "render":
                return self.send("Local narration can only be selected with the full render mode.", status=400)
            if mode == "render" and not load(CONFIG, {}).get("model", {}).get("enabled"):
                return self.send("A local model is disabled. Enable a compatible local model to render a full-length video, or choose the explicit template-demo mode.", status=400)
            if mode == "template" and (do_research or source_file or with_voice):
                return self.send("Template demo mode cannot be combined with research, source files, or voice.", status=400)
            if source_file:
                if len(source_file) > 500 or Path(source_file).suffix.lower() not in {".txt", ".md", ".json"}:
                    return self.send("Source notes must be a .txt, .md, or .json file inside workspace.", status=400)
                workspace = (BASE / "workspace").resolve()
                supplied = Path(source_file).expanduser()
                source_path = (BASE / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
                if source_path == workspace or workspace not in source_path.parents or not source_path.is_file():
                    return self.send("Source notes must be an existing file inside workspace.", status=400)
                source_file = str(source_path)
            duration_note = ("target_minutes: " + str(target_minutes)) if target_minutes is not None else ""
            request_parts = [
                "Create a faceless YouTube video package about " + topic + ".",
                "Format: " + fmt + ".",
                duration_note,
                "Requested mode: " + mode + ".",
                "Collect current web research and create the actual script and storyboard deliverables.",
            ]
            if mode == "render":
                request_parts.append("Render the final video to MP4.")
            if mode == "template":
                request_parts.append("Explicitly authorized: template demo render, not a full AI-generated video.")
            if with_voice:
                request_parts.append("Add local Piper narration with voice.")
            if not do_research and mode != "template":
                request_parts.append("Research is still required by the system; the checkbox only controls the former standalone workflow.")
            try:
                enqueue_task("Video: " + topic[:145], "youtube_package", " ".join(part for part in request_parts if part), source_file)
            except (TimeoutError, ValueError, OSError) as exc:
                return self.send("Could not queue video task for the CEO: " + esc(type(exc).__name__), status=503)
            return self._redirect("/")
        if path == "/build-product":
            title = form.get("product_title", [""])[0].strip()
            idea = form.get("product_idea", [""])[0].strip()
            if not title or len(title) > 100 or not idea or len(idea) > 1000:
                return self.send("Product title must be 1–100 characters and product idea 1–1000 characters.", status=400)
            task_text = (
                "Build a digital product prototype called " + title + ". "
                "User problem and product idea: " + idea + ". "
                "Research the user need and similar solutions, produce a usable local HTML/ZIP prototype, "
                "document its limitations, and do not claim market validation without evidence."
            )
            try:
                enqueue_task("Digital product: " + title, "draft", task_text)
            except (TimeoutError, ValueError, OSError) as exc:
                return self.send("Could not queue product task for the CEO: " + esc(type(exc).__name__), status=503)
            return self._redirect("/")
        if path == "/run-pipeline":
            global PIPELINE_RUNNING, PIPELINE_LAST_OUTPUT
            task = form.get("task", [""])[0].strip()
            agents = form.get("agents", [""])[0].strip().upper()
            context_file = form.get("context_file", [""])[0].strip()
            ids = [item.strip() for item in agents.split(",") if item.strip()]
            if not task or len(task) > 6000 or len(ids) > 51 or len(set(ids)) != len(ids):
                return self.send("Invalid CEO request. Provide a goal and, only if overriding delegation, 1–51 unique specialist IDs.", status=400)
            if any(not re.fullmatch(r"AGENT-[0-9]{2}", item) for item in ids) or "AGENT-50" in ids or "AGENT-01" in ids:
                return self.send("Invalid specialist ID. AGENT-01 is the CEO and AGENT-50 is the human approval gate; neither can run as an ordinary worker.", status=400)
            if context_file:
                if len(context_file) > 500 or Path(context_file).suffix.lower() not in {".txt", ".md", ".json"}:
                    return self.send("Context path must point to a .txt, .md, or .json file.", status=400)
                workspace = (BASE / "workspace").resolve()
                supplied = Path(context_file).expanduser()
                resolved_context = (BASE / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
                if resolved_context == workspace or workspace not in resolved_context.parents or not resolved_context.is_file():
                    return self.send("Context file must be an existing .txt, .md, or .json file inside the local workspace.", status=400)
                context_file = str(resolved_context)
            claimed, active = try_claim_workflow("CEO command pipeline")
            if not claimed:
                return self.send("Another workflow is already running: "+esc(active)+".", status=409)
            with PIPELINE_LOCK:
                if PIPELINE_RUNNING:
                    release_workflow("CEO command pipeline")
                    return self.send("A CEO pipeline is already running.", status=409)
                PIPELINE_RUNNING = True
            run_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            PIPELINE_LAST_OUTPUT = "workspace/orchestration/run-" + run_id
            def run_pipeline():
                global PIPELINE_RUNNING
                try:
                    LOGS.mkdir(exist_ok=True)
                    command = [sys.executable, str(BASE / "agents" / "orchestrate.py"),
                               "--task", task, "--out", PIPELINE_LAST_OUTPUT]
                    if ids:
                        command.extend(["--agents", ",".join(ids)])
                    if context_file:
                        command.extend(["--context-file", context_file])
                    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as log_file:
                        log_file.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] Pipeline started: {','.join(ids)}\n")
                        try:
                            result = subprocess.run(command, cwd=str(BASE), stdout=log_file,
                                                    stderr=subprocess.STDOUT, timeout=7200, check=False)
                            log_file.write(f"Pipeline exit code: {result.returncode}\n")
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            log_file.write(f"Pipeline error: {type(exc).__name__}\n")
                finally:
                    PIPELINE_RUNNING = False
                    release_workflow("CEO command pipeline")
            threading.Thread(target=run_pipeline, daemon=True).start()
            return self._redirect("/")
        if path == "/run":
            claimed, active = try_claim_workflow("task runner")
            if not claimed:
                return self.send("Another workflow is already running: "+esc(active)+".", status=409)
            if RUNNING:
                release_workflow("task runner")
                return self.send("A task cycle is already running. Wait for it to finish before starting another.", status=409)
            RUNNING = True

            def runner():
                global RUNNING
                try:
                    with RUN_LOCK:
                        subprocess.run(
                            [sys.executable, str(BASE / "agent.py"), "--once"],
                            cwd=str(BASE), timeout=3600, check=False
                        )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    LOGS.mkdir(exist_ok=True)
                    with (LOGS / "dashboard.log").open("a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] RUN ERROR: {type(exc).__name__}\n")
                finally:
                    RUNNING = False
                    release_workflow("task runner")

            threading.Thread(target=runner, daemon=True).start()
            return self._redirect("/")
        if path == "/refresh": return self._redirect("/")
        return self.send("Not found", status=404)

    def _redirect(self, location):
        self.send_response(303); self.send_header("Location", location); self.send_header("Content-Length", "0"); self.end_headers()

    def log_message(self, fmt, *args): pass

def main():
    cfg = load(CONFIG, {})
    host = cfg.get("dashboard", {}).get("host", "127.0.0.1")
    port = int(cfg.get("dashboard", {}).get("port", 8765))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Safety check: dashboard must bind to loopback only.")
    server = HTTPServer((host, port), Handler)
    print(f"Holographic Offline Agent HQ: http://127.0.0.1:{port}")
    print("Keep Termux open. Press Ctrl+C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nDashboard stopped.")
    finally: server.server_close()

if __name__ == "__main__": main()
