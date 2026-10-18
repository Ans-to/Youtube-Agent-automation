#!/usr/bin/env python3
"""Create a local approval record for a reviewed package; this does not publish."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
def sha256(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--package",required=True);a=p.parse_args()
 root=Path(a.package).resolve();video=root/"video.mp4"
 for item in (root/"script.md",root/"storyboard.json",video):
  if not item.is_file():raise SystemExit("Required package file missing: "+item.name)
 print("Package:",root);print("Video SHA-256:",sha256(video));print("This records approval only; it does not upload or publish.")
 expected="APPROVE PACKAGE "+root.name
 if input("Type exactly '"+expected+"' to approve: ").strip()!=expected:raise SystemExit("Approval cancelled.")
 record={"approved":True,"approved_at":datetime.now(timezone.utc).isoformat(),"package_dir":str(root),"video_file":str(video),"video_sha256":sha256(video),"script_reviewed":True,"storyboard_reviewed":True,"publishing_performed":False}
 (root/"release-approval.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
 status_path=root/"package-status.json"
 if status_path.is_file():
  status=json.loads(status_path.read_text(encoding="utf-8"));status.update({"status":"approved_for_upload","human_review_required":False,"publishing_performed":False,"approved_at":record["approved_at"]})
  status_path.write_text(json.dumps(status,indent=2)+"\n",encoding="utf-8")
 print("Approval record written:",root/"release-approval.json")
if __name__=="__main__":main()
