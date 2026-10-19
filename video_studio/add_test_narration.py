#!/usr/bin/env python3
"""Add scene-aligned synthetic test narration to a rendered MP4 (CI evidence only)."""
import argparse, json, shutil, subprocess, tempfile
from pathlib import Path

def run(args):
    subprocess.run([str(x) for x in args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--video",required=True)
    p.add_argument("--storyboard",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--voice",default="en-us")
    a=p.parse_args()
    espeak=shutil.which("espeak-ng") or shutil.which("espeak")
    ffmpeg,ffprobe=shutil.which("ffmpeg"),shutil.which("ffprobe")
    if not espeak or not ffmpeg or not ffprobe:
        raise SystemExit("espeak-ng, ffmpeg and ffprobe are required to create narrated test evidence.")
    storyboard=json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    video=Path(a.video).resolve(); output=Path(a.output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="narration-") as tmp:
        root=Path(tmp); segments=[]
        for i,scene in enumerate(storyboard["scenes"]):
            duration=float(scene["duration_seconds"])
            raw=root/f"raw-{i:03}.wav"; seg=root/f"seg-{i:03}.wav"
            text=str(scene.get("narration") or scene.get("headline") or "").strip()
            if text:
                run([espeak,"-v",a.voice,"-s","158","-w",raw,text])
                audio_input=str(raw)
                run([ffmpeg,"-y","-hide_banner","-loglevel","error","-i",audio_input,
                     "-af",f"apad,atrim=0:{duration:.6f},afade=t=in:st=0:d=0.08,afade=t=out:st={max(0,duration-0.12):.6f}:d=0.12",
                     "-ar","48000","-ac","2","-c:a","pcm_s16le",seg])
            else:
                run([ffmpeg,"-y","-hide_banner","-loglevel","error","-f","lavfi","-i",
                     "anullsrc=r=48000:cl=stereo","-t",str(duration),"-c:a","pcm_s16le",seg])
            segments.append(seg)
        concat=root/"concat.txt"
        concat.write_text("".join("file '"+str(x)+"'\n" for x in segments),encoding="utf-8")
        wav=root/"narration.wav"
        run([ffmpeg,"-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",concat,
             "-c:a","pcm_s16le",wav])
        run([ffmpeg,"-y","-hide_banner","-loglevel","error","-i",video,"-i",wav,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","160k",
             "-shortest","-movflags","+faststart",output])
    print(json.dumps({"output":str(output),"voice":"synthetic CI test narration","voice_id":a.voice,
                      "narrated_scenes":sum(bool(str(s.get("narration") or s.get("headline") or "").strip()) for s in storyboard["scenes"])}))

if __name__=="__main__": main()
