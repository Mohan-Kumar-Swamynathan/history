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
PROJECT_ROOT = Path(__file__).parent
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_EDUCATION = "27"

LOCAL_TOKEN_PATHS = (
    PROJECT_ROOT / "youtube_token.pickle",
    PROJECT_ROOT / "token.json",
)


def _load_credentials_from_bytes(token_bytes: bytes):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    try:
        creds = pickle.loads(token_bytes)
    except Exception:
        try:
            token_info = json.loads(token_bytes.decode("utf-8"))
            creds = Credentials.from_authorized_user_info(token_info, YOUTUBE_SCOPES)
        except Exception as exc:
            raise RuntimeError("YouTube token is not valid pickle or JSON credentials") from exc

    if hasattr(creds, "refresh") and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            log.info("YouTube token refreshed successfully — persisting to secrets")
            _persist_refreshed_token(creds)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "YouTube token expired and refresh failed. Re-run "
                "scripts/encode_youtube_credentials.py and update YOUTUBE_TOKEN_BASE64."
            ) from exc
    return creds



def _persist_refreshed_token(creds) -> None:
    """Push refreshed token back to GitHub Secrets so next run works."""
    import urllib.request
    from base64 import b64encode
    from nacl import bindings, encoding

    token_bytes = pickle.dumps(creds)
    token_b64 = base64.b64encode(token_bytes).decode()

    repo = os.environ.get("GITHUB_REPOSITORY", "Mohan-Kumar-Swamynathan/history")
    pat = os.environ.get("GH_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not pat:
        log.warning("No PAT available — cannot persist refreshed YouTube token to secrets")
        return

    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Get repo public key
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as r:
            key_data = json.loads(r.read())
    except Exception as exc:
        log.warning(f"Failed to fetch GitHub public key: {exc}")
        return

    # Encrypt using libsodium sealed box
    pub_key_bytes = base64.b64decode(key_data["key"])
    encrypted = bindings.crypto_box_seal(token_b64.encode(), pub_key_bytes)
    encrypted_b64 = b64encode(encrypted).decode()

    # Update secret
    payload = json.dumps({
        "encrypted_value": encrypted_b64,
        "key_id": key_data["key_id"],
    }).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/YOUTUBE_TOKEN_BASE64",
        data=payload,
        headers=headers,
        method="PUT",
    )
    try:
        urllib.request.urlopen(req)
        log.info("✅ Refreshed YouTube token persisted back to GitHub Secrets")
    except Exception as exc:
        log.warning(f"Failed to persist refreshed token to GitHub Secrets: {exc}")

def _load_credentials_from_token():
    raw = os.environ.get("YOUTUBE_TOKEN_BASE64", "")
    if raw:
        return _load_credentials_from_bytes(base64.b64decode(raw))

    for token_path in LOCAL_TOKEN_PATHS:
        if token_path.exists():
            log.info("Loading YouTube credentials from %s", token_path.name)
            return _load_credentials_from_bytes(token_path.read_bytes())

    raise RuntimeError(
        "YouTube credentials not found. Set YOUTUBE_TOKEN_BASE64 or place "
        "youtube_token.pickle / token.json in the project root."
    )


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
    # Final safety strip — YouTube API rejects ANY non-ASCII in tags
    import re as _re
    def _strip(t): return _re.sub(r"[^a-zA-Z0-9\s\-\'&]","",t.encode("ascii","ignore").decode()).strip()
    tags = [s for t in tags if (s := _strip(t)) and len(s) >= 2][:30]
    if not tags:
        tags = ["thulir", "tamil storytelling", "tamil youtube", "biography tamil"]

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
