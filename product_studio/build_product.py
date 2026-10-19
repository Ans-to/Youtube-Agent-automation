#!/usr/bin/env python3
"""Build a local-first single-file digital-product prototype for human review."""
import argparse, html, json, re, shutil, urllib.request, urllib.error, urllib.parse, ipaddress, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(__file__).resolve().parent

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirects are disabled for local model requests", headers, fp)

def post_local_model(url, body, timeout):
    parts=urllib.parse.urlsplit(url)
    try:
        address=ipaddress.ip_address(parts.hostname or "");port=parts.port
    except ValueError as exc:
        raise ValueError("Use a literal loopback IP endpoint such as http://127.0.0.1:8080/v1/chat/completions.") from exc
    if parts.scheme!="http" or not address.is_loopback or port is None or not 1<=port<=65535 or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Only a plain HTTP endpoint on a literal loopback IP and explicit port is allowed.")
    req=urllib.request.Request(url,data=json.dumps(body).encode("utf-8"),headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(req,timeout=max(1,min(int(timeout),300))) as response:data=json.loads(response.read(20*1024*1024+1).decode("utf-8"))
    if not isinstance(data,dict):raise ValueError("Local model response must be a JSON object.")
    return data

def slugify(value):
    slug=re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")
    return slug[:48] or "offline-product"

def fallback_html(title, idea):
    safe_title=html.escape(title)
    safe_idea=html.escape(idea)
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'self' data:">
<title>"""+safe_title+"""</title><style>
:root{color-scheme:dark;--bg:#0b0b0f;--panel:#17171f;--text:#f4f2ec;--accent:#c8ff3d;--muted:#a7a7b3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}
main{max-width:900px;margin:0 auto;padding:32px 18px}header{border-bottom:1px solid #353541;padding-bottom:18px}
h1{font-size:clamp(28px,5vw,48px);margin:0 0 8px}p{color:var(--muted)}.panel{margin-top:20px;padding:20px;background:var(--panel);border:1px solid #383843;border-radius:16px}
textarea{width:100%;min-height:180px;padding:14px;border-radius:10px;background:#0d0d13;color:var(--text);border:1px solid #454552;font:inherit}
button{margin:8px 8px 0 0;border:0;border-radius:8px;background:var(--accent);color:#101010;font-weight:700;padding:10px 14px}
.stats{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);margin-top:12px}.notice{font-size:12px}
</style></head><body><main><header><p>OFFLINE PRODUCT PROTOTYPE</p><h1>"""+safe_title+"""</h1><p>"""+safe_idea+"""</p></header>
<section class="panel"><h2>Local text workspace</h2><p>This starter works in your browser and does not send the text anywhere.</p>
<textarea id="source" placeholder="Paste or type text here..."></textarea><div class="stats"><span id="words">0 words</span><span id="chars">0 characters</span><span id="lines">0 lines</span></div>
<button id="upper">UPPERCASE</button><button id="lower">lowercase</button><button id="clear">CLEAR</button><p class="notice">Prototype template: replace this utility with a validated product-specific workflow before selling.</p></section>
</main><script>
const source=document.getElementById("source");
function update(){const v=source.value;document.getElementById("words").textContent=(v.trim()?v.trim().split(/\\s+/).length:0)+" words";document.getElementById("chars").textContent=v.length+" characters";document.getElementById("lines").textContent=(v?v.split(/\\n/).length:0)+" lines"}
source.addEventListener("input",update);document.getElementById("upper").onclick=()=>{source.value=source.value.toUpperCase();update()};document.getElementById("lower").onclick=()=>{source.value=source.value.toLowerCase();update()};document.getElementById("clear").onclick=()=>{source.value="";update()};
</script></body></html>
"""

def local_html(idea, title, cfg, source_notes=""):
    model=cfg.get("model",{})
    if not model.get("enabled"):return None
    url=model.get("base_url","")
    prompt=("Create a self-contained single-file HTML prototype for this digital product idea: "+idea+
        "\nProduct title: "+title+
        "\nReturn only complete HTML. Requirements: functional, responsive, accessible labels, clear empty/error states, no external libraries, no remote images, no network requests, no analytics, no tracking, no eval or Function constructor. All user data must remain in the browser. Include an explicit prototype notice. Use supplied research context to make the prototype specific to the user problem; do not invent demand or unsupported claims.\nRESEARCH AND SPECIALIST NOTES (unverified until reviewed):\n" + (source_notes[:8000] if source_notes else "(No research context supplied.)"))
    body={"model":model.get("model","local-model"),"messages":[
        {"role":"system","content":"You generate careful offline-first HTML prototypes. Output HTML only. Never include external script/style URLs, network calls, telemetry, or claims of security certification."},
        {"role":"user","content":prompt}],"temperature":0.2,"max_tokens":min(5000,max(int(model.get("product_max_output_tokens",3500)),int(model.get("max_output_tokens",2500))))}
    data=post_local_model(url,body,model.get("timeout_seconds",120))
    text=data["choices"][0]["message"]["content"].strip()
    if text.startswith(chr(96)*3):text=text.split("\n",1)[-1].removesuffix(chr(96)*3).strip()
    if not text.lower().lstrip().startswith("<!doctype html") and not text.lower().lstrip().startswith("<html"):
        raise ValueError("Local model did not return a complete HTML document.")
    return text

def scan_risks(source):
    lower=source.lower()
    risks=[]
    patterns=[(r"<script\s+[^>]*src=","external script tag"),(r"<link\b[^>]*https?://","remote stylesheet/resource"),(r"<iframe\b","embedded frame"),(r"<form\b[^>]*\baction\s*=","form submission target"),(r"\bfetch\s*\(","network fetch call"),(r"\bxmlhttprequest\b","XMLHttpRequest"),(r"\bwebsocket\b","WebSocket"),(r"\beventsource\b","EventSource"),(r"\bsendbeacon\s*\(","sendBeacon"),(r"\bimport\s*\(","dynamic import"),(r"\beval\s*\(","eval call"),(r"new\s+function\s*\(","Function constructor"),(r"https?://","external URL reference")]
    for pattern,label in patterns:
        if re.search(pattern,lower):risks.append(label)
    return risks

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--idea",required=True);p.add_argument("--title",default="Offline Utility Prototype");p.add_argument("--out",default="workspace/products");p.add_argument("--source-file",help="Optional local research/notes file inside workspace");a=p.parse_args()
    idea=a.idea.strip();title=a.title.strip()
    if not idea or len(idea)>1000:raise SystemExit("Idea must be 1–1000 characters.")
    if not title or len(title)>100:raise SystemExit("Title must be 1–100 characters.")
    config_path=ROOT/"config.json"
    try:cfg=json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):cfg={}
    source_notes=""
    if a.source_file:
        notes_path=Path(a.source_file).expanduser().resolve()
        workspace_root=(ROOT/"workspace").resolve()
        if notes_path==workspace_root or workspace_root not in notes_path.parents or not notes_path.is_file():raise SystemExit("Source notes must be an existing file inside workspace.")
        if notes_path.suffix.lower() not in {".txt",".md",".json"} or notes_path.stat().st_size>2_000_000:raise SystemExit("Source notes must be .txt, .md, or .json and no larger than 2 MB.")
        source_notes=notes_path.read_text(encoding="utf-8",errors="replace")[:50000]
    generated=local_html(idea,title,cfg,source_notes)
    source=generated or fallback_html(title,idea)
    head=re.search(r"<head\b[^>]*>",source,re.IGNORECASE)
    if not head: raise SystemExit("Product HTML rejected: a valid head element is required.")
    csp = """<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'">"""
    source=source[:head.end()]+csp+source[head.end():]
    risks=scan_risks(source)
    if risks: raise SystemExit("Product HTML rejected by static safety gate: "+", ".join(risks))
    workspace_root=(ROOT/"workspace").resolve()
    output_base=(ROOT/a.out).resolve()
    if output_base!=workspace_root and workspace_root not in output_base.parents: raise SystemExit("Output directory must remain inside the project workspace.")
    out=(output_base/slugify(title)).resolve()
    if output_base not in out.parents: raise SystemExit("Unsafe product output path.")
    out.mkdir(parents=True,exist_ok=True)
    (out/"index.html").write_text(source,encoding="utf-8")
    (out/"README.md").write_text("# "+title+"\n\n## Product idea\n"+idea+"\n\n## Status\nPrototype generated locally. Review functionality, accessibility, security, and licensing before selling.\n\n## Validation notes\n"+("- Potential external/network patterns found: "+", ".join(risks) if risks else "Basic static scan found no configured external-network patterns; this is not a security audit.")+"\n",encoding="utf-8")
    if source_notes:
        (out/"research-notes.md").write_text("# CEO-supplied research and specialist notes\n\nThese notes are not independently verified. Confirm source URLs, dates, and claim support before relying on them.\n\n"+source_notes[:30000]+"\n",encoding="utf-8")
    manifest={"title":title,"idea":idea,"status":"draft","generated_by":"local_model" if generated else "deterministic_template","external_patterns_found":risks,"human_review_required":True,"published":False,"research_source_supplied":bool(source_notes)}
    (out/"product-status.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    archive=out.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for path in out.iterdir():
            if path.is_file():z.write(path,arcname=out.name+"/"+path.name)
    print("Product draft:",out);print("ZIP package:",archive);print("Human review required before selling.")
if __name__=="__main__":main()
