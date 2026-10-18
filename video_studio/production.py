#!/usr/bin/env python3
"""Create a script/storyboard package from a topic using a local model when configured."""
import argparse, json, subprocess, sys, urllib.request, urllib.error, urllib.parse, ipaddress
from pathlib import Path
BASE = Path(__file__).resolve().parent

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

def load_config():
    try:
        return json.loads((BASE.parent / "config.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def local_generate(topic, cfg):
    model = cfg.get("model", {})
    if not model.get("enabled"):
        return None
    url = model.get("base_url", "")
    prompt = ("Create a responsible faceless YouTube video package for this topic: " + topic + "\n"
        "Return only valid JSON with keys title, description, script, scenes. scenes must be an array of 4 to 8 objects with duration_seconds (number), eyebrow, headline, subhead, narration. "
        "Use concise factual language; do not invent research, citations, or claim you browsed the web. Mark claims that need sourcing in the script. "
        "Narration should be in Urdu with English technical terms by default, unless the topic explicitly asks for another language. Make visual beats practical for deterministic typography and geometric Canvas2D graphics.")
    body = {"model": model.get("model", "local-model"),
        "messages": [{"role": "system", "content": "You are a careful video production assistant operating offline. Never claim to browse or verify external facts."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": int(model.get("max_output_tokens", 1800))}
    data = post_local_model(url, body, model.get("timeout_seconds", 120))
    text = data["choices"][0]["message"]["content"].strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.split("\n", 1)[-1]
        if text.endswith(fence):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)

def fallback(topic):
    scenes = [
      {"duration_seconds":5,"eyebrow":"THE QUESTION","headline":topic[:80],"subhead":"A topic package created with the offline template.","narration":topic},
      {"duration_seconds":5,"eyebrow":"THE CONTEXT","headline":"What we know","subhead":"Add trusted source notes before presenting factual claims.","narration":"Known context se shuru karein aur factual claims ko reliable sources se verify karein."},
      {"duration_seconds":5,"eyebrow":"THE EXPLANATION","headline":"How it works","subhead":"Use one concept per scene, with a simple visual metaphor.","narration":"Core idea ko step by step explain karein, har scene mein ek concept rakhein."},
      {"duration_seconds":5,"eyebrow":"THE TAKEAWAY","headline":"What to remember","subhead":"Review, fact-check, and edit before publication.","narration":"Practical takeaway summarize karein. Yeh sirf template hai, researched ya fact-checked content nahi."}]
    return {"title":topic[:90],"description":"Offline template package. Research and verify factual claims before publication.",
      "script":"# "+topic+"\n\nTemplate only: no local model was enabled and no web research was performed. Add trustworthy sources and verify claims before publishing.\n","scenes":scenes}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic",required=True);parser.add_argument("--out",default="workspace/generated");parser.add_argument("--format",choices=["long","shorts"],default="long");parser.add_argument("--render",action="store_true");parser.add_argument("--with-voice",action="store_true",help="Use local Piper voice; requires --render and PIPER_MODEL")
    args=parser.parse_args();topic=args.topic.strip()
    if not topic or len(topic)>500:raise SystemExit("Topic must be 1–500 characters.")
    if args.with_voice and not args.render:raise SystemExit("--with-voice requires --render.")
    data=local_generate(topic,load_config()) or fallback(topic);scenes=data.get("scenes")
    if not isinstance(scenes,list) or not 1<=len(scenes)<=100:raise SystemExit("Generated package invalid: scenes must be a list of 1–100.")
    total_seconds=0
    for index,scene in enumerate(scenes):
        if not isinstance(scene,dict) or not isinstance(scene.get("duration_seconds"),(int,float)) or isinstance(scene.get("duration_seconds"),bool) or scene["duration_seconds"]<=0 or scene["duration_seconds"]>600:
            raise SystemExit("Invalid scene duration at index "+str(index))
        if not all(isinstance(scene.get(key,""),str) for key in ("eyebrow","headline","subhead","narration")):
            raise SystemExit("Scene text fields must be strings at index "+str(index))
        total_seconds+=scene["duration_seconds"]
    if total_seconds>1000:raise SystemExit("Generated package exceeds the 1000-second render limit.")
    workspace_root=(BASE.parent/"workspace").resolve()
    output_dir=(BASE.parent/args.out).resolve()
    if output_dir!=workspace_root and workspace_root not in output_dir.parents:
        raise SystemExit("Output directory must remain inside the project workspace.")
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"script.md").write_text("# "+str(data.get("title",topic))+"\n\n"+str(data.get("description",""))+"\n\n"+str(data.get("script",""))+"\n",encoding="utf-8")
    storyboard={"title":str(data.get("title",topic)),"width":1080 if args.format=="shorts" else 1920,"height":1920 if args.format=="shorts" else 1080,"fps":30,"scenes":scenes}
    (output_dir/"storyboard.json").write_text(json.dumps(storyboard,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output_dir/"package-status.json").write_text(json.dumps({"status":"draft","format":args.format,"topic":topic,"research_performed":False,"human_review_required":True,"published":False},indent=2)+"\n",encoding="utf-8")
    print("Draft package:",output_dir);print("Research performed: no. Verify facts and add source notes before publishing.")
    if args.render:
        command=[sys.executable,str(BASE/"studio.py"),"--storyboard",str(output_dir/"storyboard.json"),"--output",str(output_dir/"video.mp4")]
        if args.with_voice:command.append("--with-voice")
        subprocess.run(command,check=True)

if __name__=="__main__":main()
