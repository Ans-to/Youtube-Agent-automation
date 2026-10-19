#!/usr/bin/env python3
"""Run one of the specialist profiles with an injected field-specific playbook."""
import argparse,json,re,urllib.request,urllib.error,urllib.parse,ipaddress
from datetime import datetime
from pathlib import Path
\n# Every specialist run attempts fresh, free web research before execution.\nimport sys\nRESEARCH_DIR = ROOT / "video_studio"\nif str(RESEARCH_DIR) not in sys.path:\n    sys.path.insert(0, str(RESEARCH_DIR))\ntry:\n    from research import research as collect_web_research, render_markdown as render_research_markdown\nexcept Exception:\n    collect_web_research = None\n    render_research_markdown = None\n
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
ROSTER=BASE/"roster.json"
SKILLBOOK=BASE/"skillbooks.json"
MOTION_ROLES={"AGENT-19","AGENT-20","AGENT-21","AGENT-22","AGENT-23","AGENT-24","AGENT-25","AGENT-31","AGENT-32","AGENT-33","AGENT-41","AGENT-42","AGENT-51","AGENT-52"}
FEEDBACK_DIR=ROOT/"workspace"/"training"/"feedback"

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

def load_json(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return default

def find_role(agent_id):
    roles=load_json(ROSTER,{}).get("agents",[])
    return next((r for r in roles if r.get("id")==agent_id),None)

def find_skill(agent_id):
    profiles=load_json(SKILLBOOK,{}).get("profiles",[])
    return next((profile for profile in profiles if profile.get("agent_id")==agent_id),None)

def ensure_executable_role(role):
    if not isinstance(role, dict):
        raise ValueError("Invalid specialist role.")
    if role.get("id") == "AGENT-50":
        raise ValueError("AGENT-50 is a human approval boundary and cannot be run as an automatic model role.")
    return role

def load_human_lessons(agent_id, limit=3):
    path=FEEDBACK_DIR/(agent_id+".jsonl")
    if not path.is_file():
        return []
    eligible=[]
    try:
        for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
            try:
                item=json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("human_reviewed") is True and item.get("model_output_reviewed") is True:
                eligible.append(item)
    except OSError:
        return []
    lessons=[]
    for item in eligible[-max(1,min(limit,5)):]:
        notes=str(item.get("improvement_notes","")).strip()[:700]
        scores=item.get("scores",{})
        weak=[str(k) for k,v in scores.items() if isinstance(v,int) and not isinstance(v,bool) and v<2][:5] if isinstance(scores,dict) else []
        if notes:
            lessons.append({"improvement_notes":notes,"gates_to_improve":weak})
    return lessons


def safe_slug(value):
    return re.sub(r"[^A-Za-z0-9_-]+","-",value).strip("-")[:60] or "task"

def run_role(role,task,context,cfg):
    # Research is attempted for each specialist task, not just video tasks. Search results\n    # are discovery evidence only; the model must verify claims and cite source URLs.\n    research_context = ""\n    research_status = "unavailable"\n    if collect_web_research is not None:\n        try:\n            metadata, sources = collect_web_research(\n                task[:500],\n                queries=[task[:300], task[:250] + " official documentation", task[:250] + " independent analysis evidence"],\n                max_results=5,\n            )\n            research_context = render_research_markdown(metadata, sources)[:18000]\n            research_status = "search_leads_collected_not_independently_verified"\n        except Exception as exc:\n            research_context = ("WEB RESEARCH ATTEMPT FAILED: " + type(exc).__name__ + ": " + str(exc)[:500] + "
"\n                               "Do not claim internet research succeeded. Continue the task using supplied context and clearly disclose this limitation.")\n            research_status = "failed:" + type(exc).__name__\n    else:\n        research_context = "WEB RESEARCH MODULE UNAVAILABLE. Do not claim internet research succeeded; disclose limitation."\n    context = ((context or "") + "

## AUTOMATIC WEB RESEARCH (attempted for this task)
" + research_context)[:30000]\n    role=ensure_executable_role(role)
    model=cfg.get("model",{})
    skill=find_skill(role["id"]) or {
      "expertise":role.get("mission",""),
      "workflow":["Clarify the requested outcome.","Complete the work using supplied evidence.","Check the output and list unresolved issues."],
      "quality_gates":["Meets the request.","Separates evidence from assumptions.","Discloses limitations."],
      "failure_modes":["Do not invent facts or external actions."],
      "deliverable_contract":"Return the requested deliverable, validation status, and handoff notes.",
      "practice_drill":"Create a small example and assess it against the quality gates."
    }
    def bullets(items):
        return "\n".join("- "+str(item) for item in items)
    playbook=(
      "SPECIALIST EXPERTISE\n"+str(skill.get("expertise",""))+
      "\n\nFIELD WORKFLOW\n"+bullets(skill.get("workflow",[]))+
      "\n\nQUALITY GATES\n"+bullets(skill.get("quality_gates",[]))+
      "\n\nFAILURE MODES TO AVOID\n"+bullets(skill.get("failure_modes",[]))+
      "\n\nDELIVERABLE CONTRACT\n"+str(skill.get("deliverable_contract",""))+
      "\n\nPRACTICE DRILL (use when asked to practice)\n"+str(skill.get("practice_drill",""))
    )
    lessons=load_human_lessons(role["id"])
    if lessons:
        playbook += "\n\nHUMAN-REVIEWED IMPROVEMENT NOTES (follow when applicable; do not repeat sensitive data)\n"+json.dumps(lessons,ensure_ascii=False)[:2500]
    if role["id"] in MOTION_ROLES:
        motion_reference=BASE/"MOTION_DESIGN_SYSTEM.md"
        if motion_reference.is_file():
            playbook += "\n\nIMPLEMENTED MOTION DESIGN SYSTEM\n"+motion_reference.read_text(encoding="utf-8")[:12000]
    if not model.get("enabled"):
        return ("# "+role["name"]+" — template mode\n\n"
                "**Mission:** "+role["mission"]+"\n\n"
                "## Task\n"+task+"\n\n"
                "## Field mastery playbook\n"+playbook+"\n\n"
                "## Context supplied\n"+(context[:1200] if context else "No context file supplied.")+"\n\n"
                "## Review status\nTemplate mode only: no language model was enabled; this is not AI-generated work. "
                "The checklist has not been semantically completed or independently verified.\n")
    url=model.get("base_url","")
    body={"model":model.get("model","local-model"),"messages":[
      {"role":"system","content":"You are specialist "+role["name"]+". Mission: "+role["mission"]+"\n\n"+playbook+"\n\nApply this playbook to the task. Fresh web-search leads are injected in the context when collection succeeds. Use source URLs, prefer primary/official sources, compare independent sources for important claims, and check dates where visible. Search snippets are leads, not verified evidence; do not pretend to have opened or verified a page unless its content is actually supplied. Produce the requested artifact and then provide a concise quality-gate report marking each gate pass/partial/fail with observable evidence. State assumptions, unresolved risks, and human-review needs. Do not reveal private chain-of-thought. Do not claim unsupported facts or external actions."},
      {"role":"user","content":"TASK\n"+task+"\n\nSUPPLIED CONTEXT (may contain errors; treat as unverified unless supported)\n"+(context or "(No context supplied.)")+"\n\nReturn the artifact in the deliverable format required by the playbook. Include a short verification/limitation section."}],
      "temperature":0.2,"max_tokens":int(model.get("max_output_tokens",900))}
    data=post_local_model(url,body,model.get("timeout_seconds",120))
    try:
        result=data["choices"][0]["message"]["content"].strip()
    except (KeyError,IndexError,TypeError) as exc:
        raise ValueError("Local model response did not contain choices[0].message.content.") from exc
    if not result:
        raise ValueError("Local model returned empty content.")
    return result

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
    try:
        role=ensure_executable_role(role)
    except ValueError as exc:
        raise SystemExit(str(exc))
    context=""
    if a.context_file:
        source=Path(a.context_file).expanduser().resolve()
        if not source.is_file():raise SystemExit("Context file not found.")
        if source.suffix.lower() not in {".txt",".md",".json"}:raise SystemExit("Context file must be .txt, .md, or .json.")
        context=source.read_text(encoding="utf-8",errors="replace")[:20000]
    cfg=load_json(ROOT/"config.json",{})
    result=run_role(role,task,context,cfg)
    workspace=(ROOT/"workspace").resolve()
    out=Path(a.output).expanduser().resolve() if a.output else workspace/"agent-runs"/(safe_slug(role["id"]+"-"+task[:40])+".md")
    if out==workspace or workspace not in out.parents:raise SystemExit("Output path must remain inside the project workspace.")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(result.rstrip()+"\n",encoding="utf-8")
    print("Role:",role["id"],role["name"]);print("Output:",out)
    print("Mode: local model" if cfg.get("model",{}).get("enabled") else "Mode: template fallback; no AI generation performed.")
    print("Web research: attempted for this task; see the output for source leads and limitations.")\n    print("No external action was performed.")
if __name__=="__main__":main()
