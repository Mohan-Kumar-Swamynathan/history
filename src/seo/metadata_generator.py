"""SEO metadata — titles, thumbnails, descriptions."""

from __future__ import annotations

import json
import logging
import re
from typing import List

from src.core.llm_client import generate_text, has_llm_credentials
from src.core.models import StoryBeat, TopicCandidate, VideoMetadata

log = logging.getLogger(__name__)


class MetadataGenerator:
    def generate(
        self,
        topic: TopicCandidate,
        beats: List[StoryBeat],
        chapters: List[dict],
    ) -> VideoMetadata:
        preview = " ".join(beat.narration_ta for beat in beats[:3])[:400]
        if has_llm_credentials():
            try:
                return self._generate_with_llm(topic, preview, chapters)
            except Exception as exc:
                log.warning("LLM metadata failed: %s — offline", exc)
        return self._generate_offline(topic, preview, chapters)

    def _generate_with_llm(
        self,
        topic: TopicCandidate,
        preview: str,
        chapters: List[dict],
    ) -> VideoMetadata:
        prompt = f"""Thulir Tamil storytelling YouTube channel metadata.
Story: {topic.title_ta}
Character: {topic.protagonist} ({topic.protagonist_age})
Hook: {topic.hook_question}
Lesson: {topic.lesson}
Bucket: {topic.content_bucket.value}
Preview: {preview}

Return ONLY valid JSON:
{{"title_options":["10 curiosity Tamil titles max 58 chars each"],
"title_ta":"best title",
"description_ta":"500 char Tamil description with hook + 3 story moments + lesson + hashtags",
"tags":["10+ Tamil/English tags"],
"pinned_comment":"Tamil question forcing comment",
"thumbnail_text":"2-4 Tamil words max — emotional hook",
"thumbnail_concept":"visual description",
"emotion_trigger":"surprise|shock|hope|empathy"}}"""

        raw = generate_text(prompt, max_tokens=2000)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
        title_options = data.get("title_options", [topic.title_ta])
        return VideoMetadata(
            title_ta=(data.get("title_ta") or title_options[0])[:100],
            title_options=title_options[:10],
            description_ta=data.get("description_ta", self._default_description(topic, preview)),
            tags=data.get("tags", self._default_tags(topic)),
            chapters=chapters,
            pinned_comment=data.get("pinned_comment", "இந்த கதையில் உன்னை எந்த moment-ல் பார்த்தாய்?"),
            thumbnail_text=data.get("thumbnail_text", topic.hook_question[:20])[:30],
            thumbnail_concept=data.get("thumbnail_concept", ""),
            emotion_trigger=data.get("emotion_trigger", "hope"),
        )

    def _generate_offline(self, topic: TopicCandidate, preview: str, chapters: List[dict]) -> VideoMetadata:
        thumb = _short_thumbnail_text(topic)
        return VideoMetadata(
            title_ta=topic.title_ta[:100],
            title_options=[topic.title_ta, topic.hook_question[:58]],
            description_ta=self._default_description(topic, preview),
            tags=self._default_tags(topic),
            chapters=chapters,
            pinned_comment="இந்த கதையில் உன்னை எந்த moment-ல் பார்த்தாய்? 👇",
            thumbnail_text=thumb,
            thumbnail_concept=f"{topic.protagonist} emotional moment",
            emotion_trigger="empathy",
        )

    def _default_description(self, topic: TopicCandidate, preview: str) -> str:
        return (
            f"{topic.hook_question}\n\n{preview[:300]}\n\n"
            f"பாடம்: {topic.lesson}\n\n#துளிர் #TamilStory #RealStory #{topic.content_bucket.value}"
        )

    def _default_tags(self, topic: TopicCandidate) -> List[str]:
        return [
            "துளிர்",
            "Tamil story",
            "real story Tamil",
            "Tamil YouTube",
            topic.content_bucket.value,
            topic.protagonist,
            "storytelling Tamil",
        ]


def _short_thumbnail_text(topic: TopicCandidate) -> str:
    words = re.findall(r"\S+", topic.title_ta)
    if len(words) <= 4:
        return topic.title_ta[:30]
    return " ".join(words[:4])[:30]
