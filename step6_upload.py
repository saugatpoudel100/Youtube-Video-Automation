"""STEP 6 — Upload finished videos to YouTube as Shorts.

YouTube Data API v3. One-time OAuth: create a Desktop OAuth client in Google
Cloud Console (enable YouTube Data API v3), download it as client_secret.json
next to this file. First run opens a browser; the token caches in token.json.

Appends image attribution (required by Commons CC licenses) to the description.
Reads 'video_ready' posts -> status 'published'. Default privacy is 'unlisted'.

pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""
import shutil
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from store import get_by_status, update_post

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = config.BASE_DIR / "client_secret.json"
TOKEN_FILE = config.BASE_DIR / "token.json"


def _service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise SystemExit("Missing client_secret.json (see module docstring).")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _upload(youtube, post):
    content = post.get("content", {})
    title = content.get("title", "Football News")[:100]
    description = content.get("description", "")
    description = (description + "\n\n#Shorts").strip()
    credits = post.get("image_credits") or []
    if credits:
        description += "\n\nImage credits: " + "; ".join(credits)
    description = description[:4900]
    tags = content.get("tags", [])[:15]

    body = {
        "snippet": {"title": title, "description": description, "tags": tags,
                    "categoryId": config.YOUTUBE_CATEGORY_ID},
        "status": {"privacyStatus": config.YOUTUBE_PRIVACY,
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(post["video_file"], chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def _cleanup(post, code):
    """Delete local media files once a video is safely on YouTube."""
    # stock images folder
    stock_dir = config.STOCK_IMAGES_DIR / code
    if stock_dir.exists():
        shutil.rmtree(stock_dir, ignore_errors=True)
    # ig reference images folder
    ig_dir = config.IG_IMAGES_DIR / code
    if ig_dir.exists():
        shutil.rmtree(ig_dir, ignore_errors=True)
    # audio file(s)
    for p in config.AUDIO_DIR.glob(f"{code}.*"):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    # video file
    vid = post.get("video_file")
    if vid:
        try:
            Path(vid).unlink(missing_ok=True)
        except Exception:
            pass


def run():
    todo = get_by_status("video_ready")
    print(f"[upload] {len(todo)} videos to upload (privacy={config.YOUTUBE_PRIVACY}).")
    if not todo:
        return {}
    youtube = _service()
    for code, post in todo.items():
        if not Path(post.get("video_file", "")).exists():
            print(f"   ! missing video file for {code}")
            continue
        try:
            vid = _upload(youtube, post)
        except Exception as e:
            print(f"   ! upload failed ({code}): {e}")
            continue
        update_post(code, youtube_id=vid, status="published")
        _cleanup(post, code)
        print(f"   + {code}: https://youtu.be/{vid}")
    return get_by_status("published")


if __name__ == "__main__":
    run()
