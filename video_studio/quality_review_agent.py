#!/usr/bin/env python3
"""Fail-closed multimodal editor review against licensed professional video references."""
import argparse, base64, json, os, shutil, subprocess, sys, tempfile, urllib.error, urllib.request
from pathlib import Path
VIDEO_EXTS={".mp4",".mov",".mkv",".webm"}
SYSTEM="""You are the professional editor-review agent. Compare candidate frames with professional reference frames. Score visual_polish, typography, composition, variety, continuity from 0 to 10. Return JSON only: {"approved":boolean,"scores":{"visual_polish":0,"typography":0,"composition":0,"variety":0,"continuity":0},"blocking_issues":[],"fixes":[]}. Approve only if all scores >=7 and no blocking issues. Be strict and specific. Do not claim to assess audio."""
def run(args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=120)
def frames(path,count):
    ffmpeg,ffprobe=shutil.which("ffmpeg"),shutil.which("ffprobe")
    if not ffmpeg or not ffprobe: raise RuntimeError("ffmpeg/ffprobe required")
    duration=float(json.loads(run([ffprobe,"-v","error","-show_entries","format=duration","-of","json",str(path)]).stdout)["format"]["duration"])
    if duration<=0: raise RuntimeError("Invalid video duration: "+str(path))
    result=[]
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(count):
            ts=min(max(.05,duration*(i+.5)/count),max(.05,duration-.05)); p=Path(tmp)/f"{i}.jpg"
            run([ffmpeg,"-y","-hide_banner","-loglevel","error","-ss",str(ts),"-i",str(path),"-frames:v","1","-vf","scale=768:-2","-q:v","4",str(p)])
            result.append(base64.b64encode(p.read_bytes()).decode())
    return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--video",required=True); ap.add_argument("--out"); ap.add_argument("--reference-dir",default=os.getenv("VIDEO_REFERENCE_DIR","video_studio/references")); a=ap.parse_args()
    video=Path(a.video).resolve(); out=Path(a.out).resolve() if a.out else video.with_suffix(".editor-review.json")
    report={"approved":False,"gate":"professional_visual_editor_agent","video":str(video)}
    try:
        endpoint=os.getenv("VIDEO_REVIEWER_URL","").strip(); model=os.getenv("VIDEO_REVIEWER_MODEL","local-vision-reviewer").strip()
        if not video.is_file(): raise RuntimeError("Candidate video is missing")
        if not endpoint: raise RuntimeError("VIDEO_REVIEWER_URL missing: configure an OpenAI-compatible multimodal local reviewer. No metadata-only approval is permitted.")
        rd=Path(a.reference_dir); refs=sorted(p for p in rd.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS) if rd.is_dir() else []
        if not refs: raise RuntimeError("No professional reference videos in "+str(rd)+"; add licensed/owned examples before rendering release candidates.")
        ref_images=[]; ref_names=[]
        for p in refs[:3]: ref_images.extend(frames(p,3)); ref_names.append(p.name)
        candidate=frames(video,8)
        parts=[{"type":"text","text":"PROFESSIONAL REFERENCE FRAMES; filenames: "+", ".join(ref_names)}]
        parts += [{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+x}} for x in ref_images]
        parts += [{"type":"text","text":"CANDIDATE VIDEO FRAMES IN CHRONOLOGICAL ORDER"}]
        parts += [{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+x}} for x in candidate]
        body={"model":model,"temperature":0,"max_tokens":1200,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":parts}]}
        req=urllib.request.Request(endpoint.rstrip("/")+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=int(os.getenv("VIDEO_REVIEWER_TIMEOUT","180"))) as resp: raw=json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        if isinstance(raw,list): raw="".join(x.get("text","") for x in raw if isinstance(x,dict))
        raw=str(raw).strip()
        if raw.startswith("```"): raw=raw.split("\n",1)[-1].removesuffix("```").strip()
        r=json.loads(raw); scores=r.get("scores",{}); keys=("visual_polish","typography","composition","variety","continuity")
        if any(not isinstance(scores.get(k),(int,float)) or isinstance(scores.get(k),bool) or not 0<=scores[k]<=10 for k in keys): raise RuntimeError("Reviewer returned missing/invalid scores")
        r["approved"]=r.get("approved") is True and min(scores[k] for k in keys)>=7 and not r.get("blocking_issues")
        report.update(r); report["reference_assets"]=ref_names; report["sampled_candidate_frames"]=len(candidate)
    except Exception as e: report["blocking_issues"]=[str(e)]; report["approved"]=False
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["approved"]: print("EDITOR REVIEW FAILED: release blocked.",file=sys.stderr); raise SystemExit(1)
if __name__=="__main__": main()
