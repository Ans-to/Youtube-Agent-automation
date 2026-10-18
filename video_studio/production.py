#!/usr/bin/env python3
"""Create a script/storyboard package from a topic using a local model when configured."""
import argparse, json, subprocess, sys, urllib.request
from pathlib import Path
BASE = Path(__file__).resolve().parent

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
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:") or url.startswith("http://[::1]:")):
        raise ValueError("Only a loopback local model endpoint is allowed.")
    prompt = ("Create a responsible faceless YouTube video package for this topic: " + topic + "\n"
        "Return only valid JSON with keys title, description, script, scenes. scenes must be an array of 4 to 8 objects with duration_seconds (number), eyebrow, headline, subhead, narration. "
        "Use concise factual language; do not invent research, citations, or claim you browsed the web. Mark claims that need sourcing in the script. "
        "Use clear English unless the topic explicitly asks for Urdu. Make visual beats practical for deterministic typography and geometric Canvas2D graphics.")
    body = {"model": model.get("model", "local-model"),
        "messages": [{"role": "system", "content": "You are a careful video production assistant operating offline. Never claim to browse or verify external facts."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": int(model.get("max_output_tokens", 1800))}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=int(model.get("timeout_seconds", 120))) as response:
        data = json.loads(response.read().decode("utf-8"))
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
      {"duration_seconds":5,"eyebrow":"THE CONTEXT","headline":"What we know","subhead":"Add trusted source notes before presenting factual claims.","narration":"Start with the known context and verify factual claims against reliable sources."},
      {"duration_seconds":5,"eyebrow":"THE EXPLANATION","headline":"How it works","subhead":"Use one concept per scene, with a simple visual metaphor.","narration":"Explain the core idea step by step, using one concept per scene."},
      {"duration_seconds":5,"eyebrow":"THE TAKEAWAY","headline":"What to remember","subhead":"Review, fact-check, and edit before publication.","narration":"Summarize the practical takeaway. This is a template, not researched or fact-checked content."}]
    return {"title":topic[:90],"description":"Offline template package. Research and verify factual claims before publication.",
      "script":"# "+topic+"\n\nTemplate only: no local model was enabled and no web research was performed. Add trustworthy sources and verify claims before publishing.\n","scenes":scenes}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic",required=True);parser.add_argument("--out",default="workspace/generated");parser.add_argument("--render",action="store_true")
    args=parser.parse_args();topic=args.topic.strip()
    if not topic or len(topic)>500:raise SystemExit("Topic must be 1–500 characters.")
    data=local_generate(topic,load_config()) or fallback(topic);scenes=data.get("scenes")
    if not isinstance(scenes,list) or not 1<=len(scenes)<=100:raise SystemExit("Generated package invalid: scenes must be a list of 1–100.")
    for index,scene in enumerate(scenes):
        if not isinstance(scene,dict) or not isinstance(scene.get("duration_seconds"),(int,float)) or scene["duration_seconds"]<=0:
            raise SystemExit("Invalid scene at index "+str(index))
    output_dir=(BASE.parent/args.out).resolve();output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"script.md").write_text("# "+str(data.get("title",topic))+"\n\n"+str(data.get("description",""))+"\n\n"+str(data.get("script",""))+"\n",encoding="utf-8")
    storyboard={"title":str(data.get("title",topic)),"width":1920,"height":1080,"fps":30,"scenes":scenes}
    (output_dir/"storyboard.json").write_text(json.dumps(storyboard,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output_dir/"package-status.json").write_text(json.dumps({"status":"draft","topic":topic,"research_performed":False,"human_review_required":True,"published":False},indent=2)+"\n",encoding="utf-8")
    print("Draft package:",output_dir);print("Research performed: no. Verify facts and add source notes before publishing.")
    if args.render:
        subprocess.run([sys.executable,str(BASE/"studio.py"),"--storyboard",str(output_dir/"storyboard.json"),"--output",str(output_dir/"video.mp4")],check=True)

if __name__=="__main__":main()
