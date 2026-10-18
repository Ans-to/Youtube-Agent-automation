#!/usr/bin/env python3
"""Holographic, loopback-only Offline Agent HQ dashboard; Python stdlib only."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from datetime import datetime
import json, html, subprocess, sys, threading, mimetypes

BASE = Path(__file__).resolve().parent
TASKS = BASE / "tasks.json"
CONFIG = BASE / "config.json"
OUTPUTS = BASE / "outputs"
LOGS = BASE / "logs"
RUN_LOCK = threading.Lock()
RUNNING = False

def load(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def esc(v): return html.escape(str(v), quote=True)

def task_state():
    tasks = load(TASKS, [])
    counts = {k: sum(1 for t in tasks if t.get("status", "pending") == k) for k in ("pending", "running", "completed", "failed", "needs_human_action")}
    cfg = load(CONFIG, {})
    model = cfg.get("model", {})
    return {"tasks": tasks[-100:], "counts": counts, "model_enabled": bool(model.get("enabled")),
            "model_name": model.get("model", "local-model"), "running": RUNNING,
            "pipeline": ["Coordinator", "Planner", "Worker", "Reviewer"],
            "updated": datetime.now().astimezone().isoformat(timespec="seconds")}

HTML_PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#09070b"><title>Offline Agent HQ // Command Deck</title>
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
@media(min-width:850px){main{padding:22px}.deck{min-height:430px}.panel{padding:18px}}@media(max-width:720px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.deck{min-height:350px}.brand h1{font-size:17px}header{padding:15px 13px}main{padding:12px}.agent-list{grid-template-columns:1fr 1fr}}@media(max-width:390px){.agent-list{grid-template-columns:1fr}.deck{min-height:330px}.nodes{inset:7px}.node{font-size:9px;max-width:110px}}
</style></head><body>
<header><div class="brand"><div class="logo">⌘</div><div><h1>OFFLINE AGENT HQ</h1><p>Local intelligence // command deck</p></div></div><div class="live"><i></i><span id="liveText">LOCAL SYSTEM</span></div></header>
<main>
<section class="metrics"><div class="metric"><div class="eyebrow">Total tasks</div><div class="num" id="total">0</div></div><div class="metric"><div class="eyebrow">In queue</div><div class="num" id="pending">0</div></div><div class="metric"><div class="eyebrow">Completed</div><div class="num" id="completed">0</div></div><div class="metric"><div class="eyebrow">Failed</div><div class="num" id="failed">0</div></div><div class="metric"><div class="eyebrow">Needs human action</div><div class="num" id="needsHuman">0</div></div></section>
<div class="layout"><div>
<section class="panel deck"><div class="panel-head" style="position:absolute;top:15px;left:15px;right:15px;z-index:4"><h2>Neural command core</h2><span class="tag" id="modelTag">checking model</span></div>
<svg class="connections" viewBox="0 0 600 420" preserveAspectRatio="none"><line x1="300" y1="210" x2="100" y2="95"/><line x1="300" y1="210" x2="500" y2="95"/><line x1="300" y1="210" x2="100" y2="325"/><line x1="300" y1="210" x2="500" y2="325"/></svg>
<div class="nodes"><div class="node"><b>01 / COORDINATOR</b><span class="dot"></span>Task routing</div><div class="node"><b>02 / PLANNER</b><span class="dot"></span>Breakdown</div><div class="node"><b>03 / WORKER</b><span class="dot"></span>Execution</div><div class="node"><b>04 / REVIEWER</b><span class="dot"></span>Quality check</div></div>
<div class="core"><svg viewBox="0 0 100 100" fill="none" stroke="#ffe0a0" stroke-width="2"><path d="M50 13c-13-9-28 1-26 15-14 5-13 23-3 29-5 15 5 26 18 24l11 7 11-7c13 2 23-9 18-24 10-6 11-24-3-29 2-14-13-24-26-15Z"/><path d="M50 14v72M24 30l19 10-8 15 14 10M76 30 57 40l8 15-14 10M22 57l20 4M78 57l-20 4M39 80l11-16 11 16"/></svg></div><div class="core-label">CENTRAL COORDINATOR</div><div class="hint">LOCAL-FIRST · HUMAN-CONTROLLED · NO CLOUD API</div></section>
<section class="panel"><div class="panel-head"><h2>Task intake</h2><span class="tag">New operation</span></div><form method="post" action="/add"><label for="title">TASK TITLE</label><input id="title" name="title" maxlength="160" required placeholder="e.g. Build a faceless video plan"><label for="kind">WORKFLOW</label><select id="kind" name="kind"><option value="plan">Plan / strategy</option><option value="draft">Draft content</option><option value="summarize_workspace">Summarize local workspace</option><option value="review_output">Review local workspace</option></select><label for="input">INSTRUCTIONS</label><textarea id="input" name="input" maxlength="6000" required placeholder="Describe the result, constraints, and format you need..."></textarea><button type="submit">＋ QUEUE TASK</button></form><div class="actions"><form method="post" action="/run"><button type="submit">▶ RUN PENDING</button></form><form method="post" action="/refresh"><button class="secondary" type="submit">↻ REFRESH STATE</button></form></div><p class="error" id="runInfo"></p></section>
</div><div>
<section class="panel"><div class="panel-head"><h2>Agent roster</h2><span class="tag">Pipeline roles</span></div><div class="agent-list"><div class="agent"><div class="agent-icon">⌘</div><div><strong>Coordinator</strong><small>Goal & constraints</small></div><span class="state">Ready</span></div><div class="agent"><div class="agent-icon">◈</div><div><strong>Planner</strong><small>Task decomposition</small></div><span class="state">Ready</span></div><div class="agent"><div class="agent-icon">⚙</div><div><strong>Worker</strong><small>Local generation</small></div><span class="state">Ready</span></div><div class="agent"><div class="agent-icon">✓</div><div><strong>Reviewer</strong><small>Quality & safety</small></div><span class="state">Ready</span></div></div><p style="color:var(--muted);font-size:11px;margin:12px 0 0">These are stages handled by one local runner, not four separate background processes.</p></section>
<section class="panel"><div class="panel-head"><h2>System activity</h2><span class="tag" id="updated">live refresh</span></div><div id="activity"><div class="empty">Loading task activity…</div></div></section>
<section class="panel"><div class="panel-head"><h2>Generated outputs</h2><span class="tag">Local files</span></div><div id="outputs"><div class="empty">Outputs appear here after a task completes.</div></div></section>
</div></div><div class="foot">OFFLINE AGENT HQ · Dashboard bound to loopback only · Keep Termux sessions open for processing</div></main><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);let lastState='';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2600)}
async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();$('total').textContent=d.tasks.length;$('pending').textContent=d.counts.pending+d.counts.running;$('completed').textContent=d.counts.completed;$('failed').textContent=d.counts.failed;$('needsHuman').textContent=d.counts.needs_human_action||0;$('modelTag').textContent=d.model_enabled?'MODEL CONFIGURED':'TEMPLATE MODE';$('modelTag').style.color=d.model_enabled?'var(--green)':'var(--gold)';$('liveText').textContent=d.running?'PROCESSING TASK':'LOCAL SYSTEM';$('updated').textContent=new Date(d.updated).toLocaleTimeString();
const recent=[...d.tasks].reverse().slice(0,8);$('activity').innerHTML=recent.length?recent.map(t=>`<article class="task"><div class="task-top"><div><h3>${esc(t.title||'Untitled')}</h3><div class="eyebrow">${esc(t.id)} · ${esc(t.kind)}</div></div><span class="status ${esc(t.status||'pending')}">${esc(t.status||'pending')}</span></div>${t.error?`<p class="error">${esc(t.error)}</p>`:''}<div class="task-links">${t.output_file?`<a href="/output?id=${encodeURIComponent(t.id)}">Open generated output ↗</a>`:''}<a href="/task?id=${encodeURIComponent(t.id)}">Task details</a></div></article>`).join(''):'<div class="empty">No tasks queued yet. Create your first operation.</div>';
const done=[...d.tasks].reverse().filter(t=>t.output_file).slice(0,6);$('outputs').innerHTML=done.length?done.map(t=>`<div class="task"><div class="task-top"><div><h3>${esc(t.title||t.id)}</h3><div class="eyebrow">${esc(t.output_file)}</div></div><a class="tag" href="/output?id=${encodeURIComponent(t.id)}">OPEN</a></div></div>`).join(''):'<div class="empty">No output files recorded yet.</div>';
}catch(e){$('liveText').textContent='DASHBOARD API ERROR';$('activity').innerHTML='<div class="empty">Could not refresh state: '+esc(e.message)+'</div>'}}
refresh();setInterval(refresh,4000);
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
            return self.send("<!doctype html><meta name='viewport' content='width=device-width'><title>"+esc(task.get("title"))+"</title><body style='font:15px/1.6 system-ui;background:#0b090e;color:#f8edf0;padding:20px;max-width:900px;margin:auto'><a style='color:#ff9c3e' href='/'>← Dashboard</a><h1>"+esc(task.get("title"))+"</h1><p style='color:#a99ca5'>Markdown output · "+esc(rel)+"</p><pre style='white-space:pre-wrap;overflow-wrap:anywhere;background:#17121b;border:1px solid #51211e;border-radius:12px;padding:16px'>"+esc(content)+"</pre></body>")
        return self.send("Not found", status=404)

    def do_POST(self):
        global RUNNING
        path = urlparse(self.path).path
        length = min(int(self.headers.get("Content-Length", "0")), 12000)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        if path == "/add":
            title = form.get("title", [""])[0].strip()[:160]
            kind = form.get("kind", ["plan"])[0]
            user_input = form.get("input", [""])[0].strip()[:6000]
            if not title or not user_input or kind not in {"plan", "draft", "summarize_workspace", "review_output"}:
                return self.send("Invalid task. Go back and check title, type, and instructions.", status=400)
            tasks = load(TASKS, [])
            # Use the largest existing numeric ID to avoid reusing IDs after deletions.
            nums = [int(t.get("id", "TASK-0000").split("-")[-1]) for t in tasks if str(t.get("id", "")).startswith("TASK-") and str(t.get("id", "")).split("-")[-1].isdigit()]
            task_id = "TASK-%04d" % (max(nums, default=0) + 1)
            tasks.append({"id": task_id, "title": title, "kind": kind, "input": user_input, "status": "pending", "error": ""})
            save(TASKS, tasks)
            return self._redirect("/")
        if path == "/run":
            def runner():
                global RUNNING
                with RUN_LOCK:
                    RUNNING = True
                    try: subprocess.run([sys.executable, str(BASE / "agent.py"), "--once"], cwd=str(BASE), timeout=3600)
                    finally: RUNNING = False
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
