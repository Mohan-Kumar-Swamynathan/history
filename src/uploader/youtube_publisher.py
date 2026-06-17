"""YouTube upload — long video and Shorts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from youtube_uploader import upload_video  # noqa: E402
from src.core.models import TopicCandidate, VideoMetadata  # noqa: E402

log = logging.getLogger(__name__)


class YouTubePublisher:
    def upload(
        self,
        video_path: Path,
        thumbnail_path: Path,
        metadata: VideoMetadata,
        topic: TopicCandidate,
        slug: str,
    ) -> dict:
        payload = {
            "titles": metadata.title_options or [metadata.title_ta],
            "description": metadata.description_ta,
            "tags": metadata.tags,
        }
        return upload_video(video_path, thumbnail_path, payload, topic.title_ta, slug)

    def upload_shorts(
        self,
        video_path: Path,
        metadata: VideoMetadata,
        topic: TopicCandidate,
        slug: str,
    ) -> dict:
        title = metadata.title_ta
        if "#Shorts" not in title and "#shorts" not in title.lower():
            title = f"{title[:50]} #Shorts"
        payload = {
            "titles": [title],
            "description": f"{metadata.description_ta}\n\n#Shorts #துளிர்",
            "tags": metadata.tags + ["Shorts", "YouTube Shorts"],
        }
        placeholder_thumb = video_path.parent / "thumbnail.jpg"
        thumb = placeholder_thumb if placeholder_thumb.exists() else video_path
        return upload_video(video_path, thumb, payload, topic.title_ta, slug)
