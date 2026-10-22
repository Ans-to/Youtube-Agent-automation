#!/usr/bin/env python3
"""Holographic, loopback-only Offline Agent HQ dashboard; Python stdlib only."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from datetime import datetime
import argparse, json, html, subprocess, sys, threading, mimetypes, re, webbrowser
from app_config import load_config
from web.markdown_renderer import render_markdown_safe
from queue_store import task_queue_lock, load_tasks, save_tasks

BASE = Path(__file__).resolve().parent
TASKS = BASE / "tasks.json"
CONFIG = BASE / "config.json"
OUTPUTS = BASE / "outputs"
LOGS = BASE / "logs"
AGENTS = BASE / "agents" / "roster.json"
MAX_TASK_INPUT_CHARS = 16000
MAX_FORM_BODY_BYTES = 128000
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
    released = False
    with ACTIVE_WORKFLOW_LOCK:
        if ACTIVE_WORKFLOW == name:
            ACTIVE_WORKFLOW = ""
            released = True
    # Resume the queue once when an exclusive workflow releases the command
    # core. Keeping this in one guarded path avoids duplicate worker starts.
    if not released or name == "task runner" or RUNNING or not has_pending_tasks():
        return
    try:
        start_task_runner()
    except Exception as exc:
        try:
            LOGS.mkdir(exist_ok=True)
            with (LOGS / "dashboard.log").open("a", encoding="utf-8") as log_file:
                log_file.write(
                    "Could not resume pending queue after workflow release: "
                    + type(exc).__name__ + "\n"
                )
        except OSError:
            # Queue resumption was already best-effort; a logging failure must
            # not mask the workflow's original completion path.
            pass

def load(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def esc(v): return html.escape(str(v), quote=True)

def task_state():
    raw_tasks = load(TASKS, [])
    tasks = [t for t in raw_tasks if isinstance(t, dict)] if isinstance(raw_tasks, list) else []
    attach_task_progress(tasks)
    counts = {k: sum(1 for t in tasks if str(t.get("status", "pending")).lower() == k) for k in ("running", "completed", "failed", "needs_human_action")}
    counts["pending"] = sum(1 for t in tasks if str(t.get("status", "pending")).lower() in {"pending", "queued"})
    cfg = load_config(CONFIG)
    model = cfg.get("model", {})
    video_task = next((t for t in reversed(tasks) if str(t.get("title", "")).startswith("Video:")), None)
    product_task = next((t for t in reversed(tasks) if str(t.get("title", "")).startswith("Digital product:")), None)
    video_status = str(video_task.get("status", "")) if video_task else ""
    product_status = str(product_task.get("status", "")) if product_task else ""
    video_output = (video_task.get("output_file") or ("Queued " + str(video_task.get("id", "")) + " (" + video_status + ")")) if video_task else VIDEO_LAST_OUTPUT
    product_output = (product_task.get("output_file") or ("Queued " + str(product_task.get("id", "")) + " (" + product_status + ")")) if product_task else PRODUCT_LAST_OUTPUT
    return {"tasks": tasks[-100:], "counts": counts, "model_enabled": bool(model.get("enabled")),
            "model_name": model.get("model", "local-model"), "running": RUNNING, "active_workflow": ACTIVE_WORKFLOW, "pipeline_running": PIPELINE_RUNNING, "pipeline_output": PIPELINE_LAST_OUTPUT,
            "video_running": VIDEO_RUNNING or video_status == "running", "video_output": video_output,
            "product_running": PRODUCT_RUNNING or product_status == "running", "product_output": product_output,
            "training_running": TRAINING_RUNNING, "training_output": TRAINING_LAST_OUTPUT,
            "pipeline": ["CEO Coordinator", "Researching Specialists", "Assigned Workers", "Quality Reviewer"],
            "updated": datetime.now().astimezone().isoformat(timespec="seconds"), "agent_roster": load(AGENTS, {}).get("agents", [])}


def enqueue_task(title, kind, user_input, context_file=""):
    """Persist one validated task for the CEO-led queue runner."""
    title = str(title or "").strip()[:160]
    user_input = str(user_input or "").strip()
    if not title or not user_input or len(user_input) > MAX_TASK_INPUT_CHARS or kind not in {"plan", "draft", "summarize_workspace", "review_output", "youtube_package"}:
        raise ValueError("Task instructions must contain 1–16,000 characters and use a supported workflow.")
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


def has_pending_tasks():
    """Return whether there are queued tasks waiting for the local worker."""
    raw = load(TASKS, [])
    tasks = raw if isinstance(raw, list) else []
    return any(isinstance(task, dict) and str(task.get("status", "pending")).lower() in {"pending", "queued"} for task in tasks)


def has_running_tasks():
    """Return whether the worker must inspect running records for interruption recovery."""
    raw = load(TASKS, [])
    tasks = raw if isinstance(raw, list) else []
    return any(isinstance(task, dict) and str(task.get("status", "")).lower() == "running" for task in tasks)


def start_task_runner():
    """Start the local task worker automatically, draining queued tasks in order."""
    global RUNNING
    if RUNNING:
        return True, ""
    claimed, active = try_claim_workflow("task runner")
    if not claimed:
        if active == "task runner":
            return True, ""
        return False, active
    with RUN_LOCK:
        if RUNNING:
            release_workflow("task runner")
            return True, ""
        RUNNING = True

    def runner():
        global RUNNING
        try:
            LOGS.mkdir(exist_ok=True)
            for cycle_number in range(100):
                # Always perform one queue sweep when a runner starts. agent.py uses
                # that sweep to recover orphaned running tasks even when nothing is queued.
                if cycle_number > 0 and not has_pending_tasks():
                    break
                with (LOGS / "dashboard.log").open("a", encoding="utf-8") as log_file:
                    log_file.write("[" + datetime.now().astimezone().isoformat(timespec="seconds") + "] Auto queue worker cycle " + str(cycle_number + 1) + " started\n")
                    try:
                        result = subprocess.run(
                            [sys.executable, str(BASE / "agent.py"), "--once"],
                            cwd=str(BASE), stdout=log_file, stderr=subprocess.STDOUT,
                            timeout=3600, check=False
                        )
                        log_file.write("Auto queue worker exit code: " + str(result.returncode) + "\n")
                    except (OSError, subprocess.SubprocessError) as exc:
                        log_file.write("Auto queue worker error: " + type(exc).__name__ + ": " + str(exc)[:300] + "\n")
                        break
                if cycle_number == 99 and has_pending_tasks():
                    with (LOGS / "dashboard.log").open("a", encoding="utf-8") as log_file:
                        log_file.write("Auto queue worker stopped after 100 cycles; remaining tasks stay queued for safety.\n")
        finally:
            with RUN_LOCK:
                RUNNING = False
            release_workflow("task runner")
            if has_pending_tasks():
                start_task_runner()

    try:
        threading.Thread(target=runner, daemon=True, name="agent-hq-queue-worker").start()
    except RuntimeError:
        with RUN_LOCK:
            RUNNING = False
        release_workflow("task runner")
        raise
    return True, ""


def attach_task_progress(tasks):
    """Attach the saved stage-progress snapshot to each task for dashboard display."""
    for task in tasks:
        task_id = str(task.get("id", ""))
        if not re.fullmatch(r"TASK-[0-9]{1,8}", task_id):
            continue
        progress_file = BASE / "workspace" / "orchestration" / ("task-" + task_id) / "pipeline-progress.json"
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
            if isinstance(progress, dict):
                task["progress"] = progress
        except (OSError, ValueError, TypeError):
            pass
    return tasks

DECK = BASE / "web" / "deck.html"


def load_deck() -> str:
    """Return the command-deck interface.

    The page lives in web/deck.html so the UI can be edited as HTML instead of
    a Python string literal. It is repository-owned, served only from `/`, and
    contains no external references: stills are local files under web/stills/.
    A missing file is a packaging error and must fail loudly rather than serve
    a half-built dashboard.
    """
    try:
        return DECK.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            "web/deck.html is missing or unreadable; the dashboard interface "
            "ships with the repository. Re-extract the project archive."
        ) from exc


HTML_PAGE = load_deck()

def validate_post_request(headers, server_port):
    """Reject browser POSTs without a same-origin loopback context."""
    host_header = headers.get("Host", "")
    origin = headers.get("Origin")
    content_type = headers.get("Content-Type", "")
    if not host_header:
        return "Missing Host header."
    try:
        parsed_host = urlparse("//" + host_header)
        host_port = parsed_host.port
    except ValueError:
        return "Invalid Host header."
    if (parsed_host.username or parsed_host.password or
            parsed_host.hostname not in {"127.0.0.1", "localhost", "::1"} or
            host_port != server_port or parsed_host.path or parsed_host.query or parsed_host.fragment):
        return "Host must match this loopback dashboard and port."
    # Browser form submissions from modern browsers include Origin. Requiring it
    # closes the missing-Origin CSRF bypass; this dashboard is not a general API.
    if not origin:
        return "Missing Origin header; POST requests must be same-origin."
    try:
        parsed_origin = urlparse(origin)
        origin_port = parsed_origin.port
    except ValueError:
        return "Invalid Origin header."
    if (parsed_origin.scheme != "http" or parsed_origin.username or parsed_origin.password or
            parsed_origin.hostname != parsed_host.hostname or origin_port != server_port or
            parsed_origin.path or parsed_origin.query or parsed_origin.fragment):
        return "Cross-origin POST requests are not allowed."
    if content_type.split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        return "Unsupported request content type."
    if headers.get("Transfer-Encoding"):
        return "Transfer-Encoding is not supported."
    return None


class Handler(BaseHTTPRequestHandler):
    def send(self, body, content_type="text/html; charset=utf-8", status=200):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        parsed = urlparse(self.path); path = parsed.path; query = parse_qs(parsed.query)
        # Serve only fixed, repository-owned PWA assets; never accept arbitrary file paths.
        static_assets = {
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8", False),
            "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8", False),
            "/icon.svg": ("icon.svg", "image/svg+xml; charset=utf-8", False),
            "/offline.html": ("offline.html", "text/html; charset=utf-8", False),
            # PNG icons are served as bytes, not decoded text: a browser that is
            # offered a text-mangled icon refuses the install prompt.
            "/icon-192.png": ("icons/icon-192.png", "image/png", True),
            "/icon-512.png": ("icons/icon-512.png", "image/png", True),
            "/icon-maskable-512.png": ("icons/icon-maskable-512.png", "image/png", True),
            # Command-deck stills. Fixed names only; no arbitrary path is served.
            "/stills/hero.jpg": ("stills/hero.jpg", "image/jpeg", True),
            "/stills/code.jpg": ("stills/code.jpg", "image/jpeg", True),
            "/stills/server.jpg": ("stills/server.jpg", "image/jpeg", True),
            "/stills/studio.jpg": ("stills/studio.jpg", "image/jpeg", True),
        }
        if path in static_assets:
            file_name, content_type, binary = static_assets[path]
            try:
                if binary:
                    asset = (BASE / "web" / file_name).read_bytes()
                else:
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
        request_error = validate_post_request(self.headers, self.server.server_port)
        if request_error:
            return self.send(esc(request_error), status=403)
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return self.send("Missing Content-Length.", status=411)
        try:
            length = int(raw_length)
        except ValueError:
            return self.send("Invalid Content-Length.", status=400)
        if length < 0:
            return self.send("Invalid Content-Length.", status=400)
        if length > MAX_FORM_BODY_BYTES:
            return self.send("Request body must not exceed 128,000 bytes.", status=413)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        if path == "/add":
            title = form.get("title", [""])[0].strip()[:160]
            kind = form.get("kind", ["plan"])[0]
            user_input = form.get("input", [""])[0].strip()
            try:
                enqueue_task(title, kind, user_input)
            except (TimeoutError, ValueError, OSError) as exc:
                return self.send("Could not safely queue task: " + esc(type(exc).__name__), status=503)
            start_task_runner()
            return self._redirect("/")
        if path == "/practice-agent":
            return self.send("Direct specialist execution is disabled. Submit the goal to AGENT-01 (CEO), which selects the specialist team.", status=403)
        if path == "/generate-video":
            topic = form.get("topic", [""])[0].strip()
            fmt = form.get("format", ["long"])[0].strip().lower()
            mode = form.get("render_mode", ["draft"])[0].strip().lower()
            source_file = form.get("source_file", [""])[0].strip()
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
            if mode == "render" and not load_config(CONFIG).get("model", {}).get("enabled"):
                return self.send("A local model is disabled. Enable a compatible local model to render a full-length video, or choose the explicit template-demo mode.", status=400)
            if mode == "template" and (source_file or with_voice):
                return self.send("Template demo mode cannot be combined with source files or voice.", status=400)
            if source_file:
                if len(source_file) > 500 or Path(source_file).suffix.lower() not in {".txt", ".md", ".json"}:
                    return self.send("Source notes must be a .txt, .md, or .json file inside workspace.", status=400)
                workspace = (BASE / "workspace").resolve()
                supplied = Path(source_file).expanduser()
                source_path = (BASE / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
                if source_path == workspace or workspace not in source_path.parents or not source_path.is_file():
                    return self.send("Source notes must be an existing file inside workspace.", status=400)
                if source_path.stat().st_size > 2_000_000:
                    return self.send("Source notes must not exceed 2 MB.", status=400)
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
            try:
                enqueue_task("Video: " + topic[:145], "youtube_package", " ".join(part for part in request_parts if part), source_file)
            except (TimeoutError, ValueError, OSError) as exc:
                return self.send("Could not queue video task for the CEO: " + esc(type(exc).__name__), status=503)
            start_task_runner()
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
            start_task_runner()
            return self._redirect("/")
        if path == "/run-pipeline":
            global PIPELINE_RUNNING, PIPELINE_LAST_OUTPUT
            task = form.get("task", [""])[0].strip()
            # The dashboard is a CEO-only intake surface. Reject legacy/manual role
            # overrides instead of silently allowing users to bypass CEO delegation.
            if form.get("agents", [""])[0].strip():
                return self.send("Manual specialist selection is disabled. Submit the goal to the CEO; AGENT-01 chooses the team.", status=400)
            context_file = form.get("context_file", [""])[0].strip()
            if not task or len(task) > MAX_TASK_INPUT_CHARS:
                return self.send("CEO task must contain 1–16,000 characters.", status=400)
            if context_file:
                if len(context_file) > 500 or Path(context_file).suffix.lower() not in {".txt", ".md", ".json"}:
                    return self.send("Context path must point to a .txt, .md, or .json file.", status=400)
                workspace = (BASE / "workspace").resolve()
                supplied = Path(context_file).expanduser()
                resolved_context = (BASE / supplied).resolve() if not supplied.is_absolute() else supplied.resolve()
                if resolved_context == workspace or workspace not in resolved_context.parents or not resolved_context.is_file():
                    return self.send("Context file must be an existing .txt, .md, or .json file inside the local workspace.", status=400)
                if resolved_context.stat().st_size > 2_000_000:
                    return self.send("Context file must not exceed 2 MB.", status=400)
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
                    if context_file:
                        command.extend(["--context-file", context_file])
                    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as log_file:
                        log_file.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] CEO pipeline started; delegation owner: AGENT-01\n")
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
            started, active = start_task_runner()
            if not started:
                return self.send("Another workflow is already running: "+esc(active)+". The task remains queued and will run after the current workflow ends.", status=409)
            return self._redirect("/")
        if path == "/refresh": return self._redirect("/")
        return self.send("Not found", status=404)

    def _redirect(self, location):
        self.send_response(303); self.send_header("Location", location); self.send_header("Content-Length", "0"); self.end_headers()

    def log_message(self, fmt, *args): pass

def open_when_ready(url, delay=1.2):
    """Open the app in the default browser once the server is listening.

    A launcher that prints a URL and waits for the user to copy it is not an
    installed app. This runs on a daemon timer so it can never hold the process
    open, and a machine with no browser (Termux, a headless PC) simply reports
    the URL instead of failing.
    """
    def attempt():
        try:
            opened = webbrowser.open(url)
        except Exception:  # noqa: BLE001 - no browser is not an error here
            opened = False
        if not opened:
            print("Open this address in a browser: " + url)
    timer = threading.Timer(delay, attempt)
    timer.daemon = True
    timer.start()
    return timer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local Agent HQ dashboard.")
    parser.add_argument("--port", type=int, default=None,
                        help="override the configured port (default 8765)")
    parser.add_argument("--no-open", action="store_true",
                        help="do not open the app in a browser window")
    args = parser.parse_args(argv)

    cfg = load_config(CONFIG)
    host = cfg.get("dashboard", {}).get("host", "127.0.0.1")
    port = args.port if args.port is not None else int(cfg.get("dashboard", {}).get("port", 8765))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Safety check: dashboard must bind to loopback only.")
    # 0 is allowed on purpose: it asks the OS for a free port, which is how tests
    # and second windows avoid a collision. Anything else must be a real port.
    if not 0 <= port <= 65535:
        raise SystemExit("Port must be between 0 and 65535 (0 lets the OS choose).")
    try:
        server = HTTPServer((host, port), Handler)
    except OSError as exc:
        raise SystemExit(
            f"Port {port} is already in use ({exc.strerror or exc}). "
            f"Another Agent HQ window may already be open at http://127.0.0.1:{port} , "
            "or start this one with --port 8766.")
    if has_pending_tasks() or has_running_tasks():
        print("Queued or interrupted task records detected; inspecting and resuming the local queue worker safely.")
        started, active = start_task_runner()
        if not started:
            print("Queue remains pending because another workflow is active: " + active)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Holographic Offline Agent HQ: {url}")
    print("Keep the terminal open. Press Ctrl+C to stop.")
    print("To install it as an app: open that address in Chrome or Edge, then use "
          "the Install button in the address bar (Windows) or Menu > Add to Home screen (Android).")
    if not args.no_open:
        open_when_ready(url)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nDashboard stopped.")
    finally: server.server_close()

if __name__ == "__main__": main()
