#!/usr/bin/env python3
"""Upload an explicitly approved local MP4 to YouTube; OAuth and confirmation are required."""
import argparse,hashlib,json
from pathlib import Path
def sha256(path):
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
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
 if approval.get("approved") is not True:raise SystemExit("Approval record is not approved.")
 if Path(approval.get("video_file","")).resolve()!=video:raise SystemExit("Approval record references a different video.")
 if approval.get("video_sha256")!=sha256(video):raise SystemExit("Video changed after approval; review and approve it again.")
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
 body={"snippet":{"title":a.title[:100],"description":a.description[:5000],"tags":[x.strip() for x in a.tags.split(",") if x.strip()][:500],"categoryId":"28"},"status":{"privacyStatus":a.privacy,"selfDeclaredMadeForKids":a.made_for_kids=="yes"}}
 media=MediaFileUpload(str(video),chunksize=8*1024*1024,resumable=True,mimetype="video/mp4")
 request=youtube.videos().insert(part="snippet,status",body=body,media_body=media);response=None
 while response is None:
  status,response=request.next_chunk()
  if status:print("Upload progress: {:.1f}%".format(status.progress()*100),flush=True)
 print(json.dumps({"uploaded":True,"video_id":response.get("id"),"privacy":a.privacy,"watch_url":"https://www.youtube.com/watch?v="+str(response.get("id")),"note":"Upload accepted; processing and visibility may take time."},indent=2))
if __name__=="__main__":main()
