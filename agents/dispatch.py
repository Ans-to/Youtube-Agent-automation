#!/usr/bin/env python3
"""Run one of the 50 specialist role profiles against a local model endpoint."""
import argparse,json,re,urllib.request,urllib.error,urllib.parse,ipaddress
from datetime import datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
ROSTER=BASE/"roster.json"

def load_json(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return default

def find_role(agent_id):
    roles=load_json(ROSTER,{}).get("agents",[])
    return next((r for r in roles if r.get("id")==agent_id),None)

def safe_slug(value):
    return re.sub(r"[^A-Za-z0-9_-]+","-",value).strip("-")[:60] or "task"

def run_role(role,task,context,cfg):
    model=cfg.get("model",{})
    if not model.get("enabled"):
        return ("# "+role["name"]+" — template mode\n\n"
                "**Mission:** "+role["mission"]+"\n\n"
                "## Task\n"+task+"\n\n"
                "## Context supplied\n"+(context[:1200] if context else "No context file supplied.")+"\n\n"
                "## Checklist\n- Complete the task using only supplied evidence.\n"
                "- Separate verified facts from assumptions.\n"
                "- List missing information and required human review.\n\n"
                "Template mode only: no language model was enabled; this is not an AI-generated result.\n")
    url=model.get("base_url","")
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:") or url.startswith("http://[::1]:")):
        raise ValueError("Only a loopback local model endpoint is allowed.")
    body={"model":model.get("model","local-model"),"messages":[
      {"role":"system","content":"You are specialist "+role["name"]+". Mission: "+role["mission"]+" Work only with the supplied task and context. Do not claim web access, verified external actions, or facts unsupported by context. State uncertainty and required human review."},
      {"role":"user","content":"TASK\n"+task+"\n\nSUPPLIED CONTEXT\n"+(context or "(No context supplied.)")}],
      "temperature":0.25,"max_tokens":int(model.get("max_output_tokens",900))}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=int(model.get("timeout_seconds",120))) as response:data=json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent",required=True,help="Role ID such as AGENT-09")
    p.add_argument("--task",required=True,help="Task instruction; max 6000 characters")
    p.add_argument("--context-file",help="Optional local UTF-8 text/Markdown source file")
    p.add_argument("--output",help="Optional output Markdown path")
    a=p.parse_args();task=a.task.strip()
    if not task or len(task)>6000:raise SystemExit("Task must be 1–6000 characters.")
    role=find_role(a.agent.upper())
    if not role:raise SystemExit("Unknown agent ID. Use an ID from agents/roster.json.")
    context=""
    if a.context_file:
        source=Path(a.context_file).expanduser().resolve()
        if not source.is_file():raise SystemExit("Context file not found.")
        if source.suffix.lower() not in {".txt",".md",".json"}:raise SystemExit("Context file must be .txt, .md, or .json.")
        context=source.read_text(encoding="utf-8",errors="replace")[:20000]
    cfg=load_json(ROOT/"config.json",{})
    result=run_role(role,task,context,cfg)
    out=Path(a.output).expanduser().resolve() if a.output else ROOT/"workspace"/"agent-runs"/(safe_slug(role["id"]+"-"+task[:40])+".md")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(result.rstrip()+"\n",encoding="utf-8")
    print("Role:",role["id"],role["name"]);print("Output:",out)
    print("Mode: local model" if cfg.get("model",{}).get("enabled") else "Mode: template fallback; no AI generation performed.")
    print("No external action was performed.")
if __name__=="__main__":main()
