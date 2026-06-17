#!/usr/bin/env python3
"""YouTube upload via OAuth credentials stored as base64 env vars."""

import base64
import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict

log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "upload_state.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_EDUCATION = "27"


def _load_credentials_from_token():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    raw = os.environ.get("YOUTUBE_TOKEN_BASE64", "")
    if not raw:
        raise RuntimeError("YOUTUBE_TOKEN_BASE64 not set")

    token_bytes = base64.b64decode(raw)
    try:
        creds = pickle.loads(token_bytes)
        if hasattr(creds, "refresh") and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception:
        pass

    token_info = json.loads(token_bytes.decode("utf-8"))
    creds = Credentials.from_authorized_user_info(token_info, YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _build_youtube_service():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_load_credentials_from_token())


def load_upload_state() -> Dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text("utf-8"))
    return {"uploads": []}


def save_upload_state(state: Dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def was_already_uploaded(slug: str) -> bool:
    state = load_upload_state()
    return any(entry.get("slug") == slug for entry in state.get("uploads", []))


def upload_video(video_path: Path, thumbnail_path: Path, metadata: Dict, topic: str, slug: str) -> Dict:
    from googleapiclient.http import MediaFileUpload

    if was_already_uploaded(slug):
        log.info(f"Video already uploaded for slug {slug}, skipping")
        for entry in load_upload_state().get("uploads", []):
            if entry.get("slug") == slug:
                return entry

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    title = metadata.get("titles", [topic])[0][:100]
    description = metadata.get("description", topic)[:5000]
    tags = metadata.get("tags", ["Tamil history", "varalaru"])[:30]

    youtube = _build_youtube_service()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": YOUTUBE_CATEGORY_EDUCATION,
            "defaultLanguage": "ta",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }

    log.info(f"Uploading to YouTube: {title}")
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    log.info(f"YouTube upload complete: {video_url}")

    if thumbnail_path.exists():
        try:
            thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            log.info("Custom thumbnail set")
        except Exception as exc:
            log.warning(f"Thumbnail upload failed (video still published): {exc}")

    result = {
        "slug": slug,
        "topic": topic,
        "video_id": video_id,
        "youtube_url": video_url,
        "title": title,
        "uploaded_at": datetime.utcnow().isoformat(),
    }

    state = load_upload_state()
    state.setdefault("uploads", []).append(result)
    save_upload_state(state)
    return result
