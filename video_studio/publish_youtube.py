#!/usr/bin/env python3
"""Upload an explicitly approved local MP4 to YouTube; OAuth and confirmation are required."""
import argparse,hashlib,json,sys,os
from datetime import datetime,timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from release_gate import (validate_qc_report, validate_project_audit, requires_nokia_profile,
                          requires_script_profile, require_nokia_audit_if_applicable)

def sha256(path):
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
 return h.hexdigest()

def write_json_atomic(path, value):
 """Persist approval state atomically so an interrupted write cannot corrupt the record.

 The implementation is shared with the bridge (see app/infrastructure/jsonio.py),
 which is where the Windows sharing-violation retry lives.
 """
 from app.infrastructure.jsonio import write_json_atomic as write
 write(path, value)

def validate_approval(approval, video, requested):
 if not isinstance(approval,dict) or approval.get("approved") is not True:
  raise ValueError("Approval record is not approved.")
 upload_record = approval.get("upload")
 if isinstance(upload_record, dict):
  if upload_record.get("uploaded") is True or upload_record.get("status") == "uploaded":
   raise ValueError("This approval record has already been used for an upload; create and review a new package approval before uploading again.")
  if upload_record.get("status") in {"in_progress", "outcome_unknown"}:
   raise ValueError("A previous upload attempt has an uncertain outcome. Check YouTube Studio for the video, then create and review a fresh approval before retrying.")
 if Path(approval.get("video_file","")).resolve()!=video.resolve():
  raise ValueError("Approval record references a different video.")
 if approval.get("video_sha256")!=sha256(video):
  raise ValueError("Video changed after approval; review and approve it again.")
 if Path(approval.get("package_dir","")).resolve()!=video.resolve().parent:
  raise ValueError("Approval record package directory must be the video's parent directory.")
 script_path=video.parent/"script.md"
 storyboard_path=video.parent/"storyboard.json"
 if not script_path.is_file() or not storyboard_path.is_file():
  raise ValueError("Reviewed script.md and storyboard.json must remain beside the approved video.")
 if approval.get("script_sha256")!=sha256(script_path):
  raise ValueError("Script changed after approval; review and approve the package again.")
 if approval.get("storyboard_sha256")!=sha256(storyboard_path):
  raise ValueError("Storyboard changed after approval; review and approve the package again.")
 qc_path=video.parent/"video.qc.json"
 if not qc_path.is_file():
  raise ValueError("Strict video.qc.json report is required beside the approved video.")
 if approval.get("quality_audit_passed") is not True:
  raise ValueError("Approval record does not attest to a passing strict quality audit.")
 if approval.get("qc_report_sha256")!=sha256(qc_path):
  raise ValueError("Quality report changed after approval; rerun strict QA and approve again.")
 try:
  qc_report=json.loads(qc_path.read_text(encoding="utf-8"))
  validate_qc_report(qc_report,video)
 except (OSError,json.JSONDecodeError,ValueError) as exc:
  raise ValueError("Strict video quality audit is no longer valid: "+str(exc))
 project_at_approval=approval.get("project_audit")
 if (project_at_approval is not None or (video.parent/"release-profile.json").exists()
     or requires_script_profile(video.parent) or requires_nokia_profile(video.parent,title=requested.get("title",""))):
  try:
   project_now=validate_project_audit(video.parent,required=True)
   require_nokia_audit_if_applicable(video.parent,project_now,title=requested.get("title",""))
  except ValueError as exc:
   raise ValueError("Project audit is no longer valid: "+str(exc))
  if not isinstance(project_at_approval,dict) or project_at_approval!=project_now:
   raise ValueError("Project profile or audit changed after approval; review and approve again.")
 approved=approval.get("approved_metadata")
 if not isinstance(approved,dict):
  raise ValueError("Approval is missing metadata review; recreate approval with release_gate.py.")
 if requested!=approved:
  raise ValueError("Upload metadata differs from the approved record; review and approve the exact metadata again.")
 title=requested.get("title","")
 description=requested.get("description","")
 tags=requested.get("tags",[])
 if not isinstance(title,str) or not title or len(title)>100:
  raise ValueError("Title must contain 1–100 characters.")
 if not isinstance(description,str) or len(description)>5000:
  raise ValueError("Description must be at most 5000 characters.")
 if not isinstance(tags,list) or len(tags)>500 or not all(isinstance(tag,str) and len(tag)<=100 for tag in tags):
  raise ValueError("Tags must be a list of at most 500 strings, each up to 100 characters.")
 if requested.get("privacy") not in {"private","unlisted","public"} or requested.get("made_for_kids") not in {"yes","no"}:
  raise ValueError("Approved visibility or made-for-kids setting is invalid.")
 return approved

def claim_upload_attempt(approval_path, video, requested, privacy):
 """Atomically claim one approval and persist a fail-closed marker before the upload request."""
 approval_path = Path(approval_path).resolve()
 lock_path = approval_path.with_name(approval_path.name + ".upload.lock")
 try:
  lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
 except FileExistsError as exc:
  raise ValueError("Another upload process holds the approval lock. Do not retry; inspect the approval and YouTube Studio first.") from exc
 try:
  with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_stream:
   lock_stream.write(str(os.getpid()))
  current = json.loads(approval_path.read_text(encoding="utf-8"))
  approved = validate_approval(current, video, requested)
  current["upload"] = {
   "status": "in_progress",
   "uploaded": False,
   "attempt_started_at": datetime.now(timezone.utc).isoformat(),
   "video_sha256": sha256(video),
   "privacy": privacy,
   "outcome": "unknown_until_confirmed",
  }
  write_json_atomic(approval_path, current)
  return current, approved
 finally:
  try:
   lock_path.unlink()
  except FileNotFoundError:
   pass

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--video",required=True);p.add_argument("--approval",required=True)
 p.add_argument("--title",required=True);p.add_argument("--description",default="");p.add_argument("--tags",default="")
 p.add_argument("--privacy",choices=["private","unlisted","public"],default="private");p.add_argument("--made-for-kids",choices=["yes","no"],required=True,help="Choose this accurately for the uploaded content")
 p.add_argument("--client-secrets",default="client_secret.json");p.add_argument("--token-file",default="youtube-token.json")
 p.add_argument("--confirm-publish",action="store_true");p.add_argument("--confirm-public",action="store_true")
 a=p.parse_args()
 if not a.confirm_publish:raise SystemExit("Upload blocked. Pass --confirm-publish only after reviewing the exact video.")
 if a.privacy=="public" and not a.confirm_public:raise SystemExit("Public upload blocked. Explicit --confirm-public is also required.")
 video=Path(a.video).resolve();approval_path=Path(a.approval).resolve()
 if not video.is_file() or not approval_path.is_file():raise SystemExit("Video or approval record is missing.")
 approval=json.loads(approval_path.read_text(encoding="utf-8"))
 requested={"title":a.title.strip(),"description":a.description.strip(),"tags":[x.strip() for x in a.tags.split(",") if x.strip()],"privacy":a.privacy,"made_for_kids":a.made_for_kids}
 try:
  approved=validate_approval(approval,video,requested)
 except ValueError as exc:
  raise SystemExit(str(exc))

 try:
  from google.auth.transport.requests import Request
  from google.oauth2.credentials import Credentials
  from google_auth_oauthlib.flow import InstalledAppFlow
  from googleapiclient.discovery import build
  from googleapiclient.http import MediaFileUpload
 except ImportError:raise SystemExit("Install optional dependencies: pip install -r video_studio/requirements-publish.txt")
 scopes=["https://www.googleapis.com/auth/youtube.upload"];token=Path(a.token_file).resolve();client=Path(a.client_secrets).resolve()
 credentials=Credentials.from_authorized_user_file(str(token),scopes) if token.is_file() else None
 if credentials and credentials.expired and credentials.refresh_token:credentials.refresh(Request())
 if not credentials or not credentials.valid:
  if not client.is_file():raise SystemExit("Google OAuth desktop client JSON not found: "+str(client))
  credentials=InstalledAppFlow.from_client_secrets_file(str(client),scopes).run_local_server(port=0)
  token.write_text(credentials.to_json(),encoding="utf-8")
 youtube=build("youtube","v3",credentials=credentials)
 approval,approved=claim_upload_attempt(approval_path,video,requested,a.privacy)
 body={"snippet":{"title":approved["title"],"description":approved["description"],"tags":approved["tags"],"categoryId":"28"},"status":{"privacyStatus":approved["privacy"],"selfDeclaredMadeForKids":approved["made_for_kids"]=="yes"}}
 media=MediaFileUpload(str(video),chunksize=8*1024*1024,resumable=True,mimetype="video/mp4")
 request=youtube.videos().insert(part="snippet,status",body=body,media_body=media);response=None
 while response is None:
  status,response=request.next_chunk()
  if status:print("Upload progress: {:.1f}%".format(status.progress()*100),flush=True)
 uploaded_at=datetime.now(timezone.utc).isoformat();video_id=response.get("id")
 approval["upload"]={"status":"uploaded","uploaded":True,"uploaded_at":uploaded_at,"video_id":video_id,"privacy":a.privacy};write_json_atomic(approval_path,approval)
 status_path=Path(approval.get("package_dir",str(video.parent)))/"package-status.json"
 if status_path.is_file():
  package_status=json.loads(status_path.read_text(encoding="utf-8"));package_status.update({"status":"uploaded","uploaded":True,"published":a.privacy=="public","upload_privacy":a.privacy,"youtube_video_id":video_id,"uploaded_at":uploaded_at})
  status_path.write_text(json.dumps(package_status,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"uploaded":True,"video_id":video_id,"privacy":a.privacy,"watch_url":"https://www.youtube.com/watch?v="+str(video_id),"note":"Upload accepted; processing and visibility may take time."},indent=2))
if __name__=="__main__":main()
