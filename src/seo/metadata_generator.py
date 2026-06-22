"""SEO metadata generator — content bible compliant.

Generates:
  - 10 title variants (curiosity-driven, A/B test ready)
  - Full Tamil description with timestamps + keywords
  - 25-30 ASCII tags (trending + evergreen)
  - Pinned comment with engagement hook
  - Thumbnail text (2-4 words max)
  - Shorts description
"""

from __future__ import annotations

import logging
import re
from typing import List

from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_policy import STAGE_METADATA, should_use_llm
from src.core.models import StoryBeat, TopicCandidate, VideoMetadata

log = logging.getLogger(__name__)

METADATA_PROMPT = """You are SEO strategist for "துளிர்" Tamil storytelling YouTube channel.

Story: {title_ta}
Protagonist: {protagonist}
Hook: {hook}
Lesson: {lesson}
Script preview: {preview}
Beat timestamps (approximate): {timestamps}

Generate complete YouTube metadata. Return ONLY JSON:
{{
  "titles": [
    "10 Tamil titles — curiosity-driven, under 70 chars each",
    "Mix: some start with numbers (1009 முறை...), some with questions (எப்படி?)",
    "Some with drama (உலகம் அதிர்ந்தது), some with contrast (எல்லோரும் சிரித்தனர்...)"
  ],
  "best_title": "Best single title for upload",
  "description_ta": "Full Tamil description: 150-200 words. Include: hook paragraph, what viewers will learn, 3-5 timestamps in MM:SS format, subscribe CTA, hashtags at end",
  "tags": ["25-30 ASCII English tags: protagonist name, story keywords, channel name, niche tags"],
  "thumbnail_text": "2-4 words MAX for thumbnail — the most shocking number or phrase",
  "pinned_comment": "Tamil comment with hook question to pin — drives engagement. End with emoji",
  "emotion_trigger": "One of: surprise|shock|hope|triumph|failure|excitement|mystery",
  "chapters": ["MM:SS Title" list for description]
}}"""


class MetadataGenerator:
    def generate(
        self,
        topic: TopicCandidate,
        beats: List[StoryBeat],
        chapters: List[dict],
    ) -> VideoMetadata:
        preview    = " ".join(b.narration_ta for b in beats[:2])[:500]
        timestamps = self._beat_timestamps(beats)

        if has_llm_credentials() and should_use_llm(STAGE_METADATA):
            try:
                return self._with_llm(topic, preview, timestamps, beats)
            except Exception as e:
                log.warning("LLM metadata failed: %s", e)

        return self._offline(topic, preview, beats)

    def _with_llm(self, topic, preview, timestamps, beats) -> VideoMetadata:
        prompt = METADATA_PROMPT.format(
            title_ta    = topic.title_ta,
            protagonist = topic.protagonist,
            hook        = topic.hook_question or topic.emotional_hook or "",
            lesson      = topic.lesson or "",
            preview     = preview,
            timestamps  = timestamps,
        )
        raw = generate_text(prompt, max_tokens=2000)

        import json, re as re_
        match = re_.search(r'\{.*\}', raw, re_.DOTALL)
        if not match:
            return self._offline(topic, preview, beats)

        data = json.loads(match.group())
        titles = data.get("titles", [topic.title_ta])

        # Build description with chapters
        desc = data.get("description_ta", "")
        chapters_text = self._format_chapters(beats)
        if chapters_text and "00:00" not in desc:
            desc = desc + "\n\n" + chapters_text

        return VideoMetadata(
            title_ta        = data.get("best_title", titles[0] if titles else topic.title_ta),
            title_options   = titles[:10],
            description_ta  = desc,
            tags            = _clean_tags(data.get("tags", []) or SAFE_DEFAULT_TAGS),
            thumbnail_text  = data.get("thumbnail_text", _extract_hook_text(topic.title_ta)),
            emotion_trigger = data.get("emotion_trigger", "surprise"),
            pinned_comment  = data.get("pinned_comment", self._default_pin(topic)),
            chapters        = self._parse_chapters(beats),
        )

    def _offline(self, topic, preview, beats) -> VideoMetadata:
        protagonist = topic.protagonist
        hook_q      = topic.hook_question or ""
        lesson      = topic.lesson or ""
        title       = topic.title_ta

        # Generate 5 offline title variants
        title_variants = [
            title,
            f"{protagonist} — உண்மையான கதை | துளிர்",
            f"யாரும் சொல்லாத {protagonist}-ன் கதை",
            f"இந்த கதை உங்களை அதிரவைக்கும் | {protagonist}",
            f"{protagonist}: {lesson[:40]}",
        ]

        # Description with timestamps
        chapters_text = self._format_chapters(beats)
        desc = (
            f"{hook_q}\n\n"
            f"🌱 துளிர் — உண்மையான கதைகள். உண்மையான பாடங்கள்.\n\n"
            f"இந்த வீடியோவில்:\n"
            f"✅ {protagonist}-ன் உண்மையான கதை\n"
            f"✅ {lesson}\n\n"
            f"⏱️ நேரடி அட்டவணை:\n{chapters_text}\n\n"
            f"👍 லைக் செய்யுங்கள் | 🔔 சந்தா செய்யுங்கள் | 💬 கருத்து சொல்லுங்கள்\n\n"
            f"📺 எங்கள் மற்ற சேனல்கள்:\n"
            f"🕉️ பக்தி கதைகள் → youtube.com/@aalayamani\n"
            f"💰 நிதி உதவி → youtube.com/@nidhineethi\n"
            f"🚗 கார் செய்திகள் → youtube.com/@cartamiltv\n\n"
            f"#துளிர் #TamilStorytelling #தமிழ்கதைகள் #TamilYouTube #MotivationalTamil"
        )
        tags = _clean_tags(_default_tags(protagonist, topic.content_bucket.value if hasattr(topic, 'content_bucket') else "") + SAFE_DEFAULT_TAGS)
        return VideoMetadata(
            title_ta        = title,
            title_options   = title_variants,
            description_ta  = desc,
            tags            = tags,
            thumbnail_text  = _extract_hook_text(title),
            emotion_trigger = "surprise",
            pinned_comment = self._default_pin(topic),
            chapters        = self._parse_chapters(beats),
        )

    def _default_pin(self, topic) -> str:
        q = topic.hook_question or topic.open_loop or ""
        return f"💬 {q}\n\nComment பண்ணுங்கள் 👇 #thuLir"

    def _beat_timestamps(self, beats) -> str:
        ts = []
        ms = 0
        labels = ["Hook","Setup","Conflict","Worst Point","Turning Point","Resolution","Lesson"]
        for i, beat in enumerate(beats):
            mins, secs = divmod(ms // 1000, 60)
            label = labels[i] if i < len(labels) else f"Part {i+1}"
            ts.append(f"{mins:02d}:{secs:02d} — {label}")
            dur = int(getattr(beat, 'duration_seconds', 45) * 1000)
            ms += dur
        return "\n".join(ts)

    def _format_chapters(self, beats) -> str:
        labels = ["🎣 தொடக்கம்","📖 பின்னணி","⚡ சோதனை","🔥 கடினமான தருணம்",
                  "💡 திருப்புமுனை","✅ வெற்றி","🌱 பாடம்"]
        lines  = []
        # Offset by intro duration (3.5s)
        ms     = 3500
        for i, beat in enumerate(beats):
            mins, secs = divmod(ms // 1000, 60)
            label = labels[i] if i < len(labels) else f"பகுதி {i+1}"
            lines.append(f"{mins:02d}:{secs:02d} {label}")
            dur = int(getattr(beat, 'duration_seconds', 45) * 1000)
            ms += dur
        return "\n".join(lines)

    def _parse_chapters(self, beats) -> List[dict]:
        labels = ["Hook","Setup","Conflict","Worst Point","Turning Point","Resolution","Lesson"]
        result = []
        ms     = 0
        for i, beat in enumerate(beats):
            mins, secs = divmod(ms // 1000, 60)
            result.append({"time": f"{mins:02d}:{secs:02d}", "title": labels[i] if i < len(labels) else f"Part {i+1}"})
            ms += int(getattr(beat, 'duration_seconds', 45) * 1000)
        return result


def _clean_tags(tags: list) -> list:
    """Strip ALL non-ASCII from tags — YouTube API HTTP 400 on Tamil script.
    
    YouTube tags MUST be ASCII only. Any Unicode character (Tamil, emoji, etc.)
    causes: 'The request metadata specifies invalid video keywords.'
    """
    clean = []
    for tag in tags:
        if not isinstance(tag, str): continue
        # Remove ALL non-ASCII characters
        ascii_tag = tag.encode("ascii", errors="ignore").decode()
        # Remove special chars except hyphen, space, apostrophe
        import re
        ascii_tag = re.sub(r"[^a-zA-Z0-9\s\-\'&]", "", ascii_tag)
        ascii_tag = " ".join(ascii_tag.split()).strip()  # normalise spaces
        ascii_tag = ascii_tag[:100]
        if ascii_tag and len(ascii_tag) >= 2:
            clean.append(ascii_tag)
    # Deduplicate
    seen = set(); deduped = []
    for t in clean:
        if t.lower() not in seen:
            seen.add(t.lower()); deduped.append(t)
    return deduped[:30]


SAFE_DEFAULT_TAGS = [
    "thulir", "tamil storytelling", "tamil motivation 2026",
    "true story tamil", "real stories tamil", "almost everything tamil",
    "tamil youtube 2026", "interesting facts tamil", "tamil documentary",
    "motivational stories tamil", "biography tamil", "success stories tamil",
    "thuLir stories", "tamil history stories", "inspired by real events tamil",
]

def _default_tags(protagonist: str, bucket: str) -> list:
    # Always start with guaranteed safe ASCII tags
    base = [
        "thulir", "tamil storytelling", "tamil motivation 2026",
        "true story tamil", "real stories tamil", "almost everything tamil",
        "tamil youtube 2026", "interesting facts tamil", "tamil documentary",
        "motivational stories tamil", "biography tamil", "success stories tamil",
        "thuLir stories", "tamil history stories", "inspired by real events tamil",
    ]
    p_en = protagonist.encode("ascii","ignore").decode().strip()
    if p_en:
        base = [p_en, p_en.lower().replace(" ",""), f"{p_en} story tamil",
                f"{p_en} biography", f"{p_en} success story"] + base
    bucket_tags = {
        "business":         ["business failure tamil", "company story tamil",
                             "entrepreneur story tamil", "startup failure success"],
        "historical_story": ["history story tamil", "world history tamil",
                             "forgotten history", "historical facts tamil"],
        "success_failure":  ["success story tamil", "failure to success tamil",
                             "rags to riches tamil", "never give up tamil"],
        "psychology":       ["psychology facts tamil", "human behavior tamil",
                             "interesting facts tamil", "mind facts"],
        "science":          ["science facts tamil", "invention story tamil",
                             "scientist biography tamil"],
    }
    base += bucket_tags.get(bucket, [])
    return _clean_tags(base)[:30]

def _extract_hook_text(title_ta: str) -> str:
    nums = re.findall(r'\d+', title_ta)
    if nums:
        n   = nums[0]
        idx = title_ta.find(n)
        raw = title_ta[max(0,idx-3):idx+len(n)+12].strip()
        return raw[:22]
    words = title_ta.split()
    return " ".join(words[:3]) if words else title_ta[:15]
