#!/usr/bin/env python3
"""Orchestrate deterministic Canvas2D rendering and FFmpeg encoding."""
import argparse, json, os, shutil, subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
def run(command,cwd=BASE):
 print("+"," ".join(str(x) for x in command),flush=True)
 subprocess.run(command,cwd=str(cwd),check=True)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--storyboard",default="storyboard.example.json")
 p.add_argument("--output",default="outputs/offline-agent-hq-demo.mp4")
 p.add_argument("--with-voice",action="store_true",help="Use local Piper CLI and PIPER_MODEL path")
 a=p.parse_args();node=shutil.which("node");ffmpeg=shutil.which("ffmpeg")
 if not node:raise SystemExit("Node.js was not found. Install Node.js LTS first.")
 if not ffmpeg:raise SystemExit("FFmpeg was not found. Install FFmpeg first.")
 sb=(BASE/a.storyboard).resolve()
 if not sb.is_file():raise SystemExit("Storyboard not found: "+str(sb))
 data=json.loads(sb.read_text(encoding="utf-8"));fps=int(data.get("fps",30))
 if not 1<=fps<=60:raise SystemExit("Storyboard fps must be from 1 to 60.")
 run([node,"render.js",str(sb)])
 manifest=json.loads((BASE/"render-manifest.json").read_text(encoding="utf-8"))
 output=(BASE/a.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
 silent=output.with_name(output.stem+".silent.mp4");frames=BASE/"frames"/"frame-%06d.png"
 run([ffmpeg,"-y","-hide_banner","-loglevel","warning","-framerate",str(fps),"-i",str(frames),"-frames:v",str(manifest["frame_count"]),"-c:v","libx264","-pix_fmt","yuv420p","-crf","20","-movflags","+faststart",str(silent)])
 if a.with_voice:
  piper=shutil.which("piper");model=os.environ.get("PIPER_MODEL","").strip()
  if not piper or not model or not Path(model).is_file():raise SystemExit("Voice requested, but Piper or PIPER_MODEL is missing.")
  text=" ".join(str(scene.get("narration","")) for scene in data["scenes"]).strip()
  if not text:raise SystemExit("No narration text exists in the storyboard.")
  narration=BASE/"narration.wav"
  subprocess.run([piper,"--model",model,"--output_file",str(narration)],input=(text+"\n").encode("utf-8"),cwd=str(BASE),check=True)
  run([ffmpeg,"-y","-hide_banner","-loglevel","warning","-i",str(silent),"-i",str(narration),"-map","0:v:0","-map","1:a:0","-af","apad","-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",str(output)])
  silent.unlink(missing_ok=True)
 else:
  silent.replace(output);print("No voice synthesized. Add --with-voice after installing a local Piper voice.")
 print("SUCCESS:",output);print("Duration:",manifest["duration_seconds"],"seconds");print("Frames:",manifest["frame_count"]);print("Local MP4 only: this pipeline does not upload or publish content.")
if __name__=="__main__":main()
