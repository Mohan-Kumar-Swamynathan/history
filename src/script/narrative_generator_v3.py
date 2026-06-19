"""Narrative generator v3 — AE rhythm, 6 beats, 8-10 words per sentence.

Key changes from v2:
- 6 beats only (not 12) — AE pacing
- Max 12 Tamil words per beat narration
- Each beat = ONE specific moment, ONE visual image
- Script instructs LLM to write like AE: specific year/age/place/number
- No greetings, no channel branding in narration
- Strong open loop in beat 1
- beat_type maps to 6-beat structure: hook, rise, fall, turn, win, lesson
"""

from __future__ import annotations

import logging
import re
from typing import List

from src.core.config_loader import load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_json_parser import extract_json_array
from src.core.models import BeatType, NarrativeScript, StoryBeat, TopicCandidate, ResearchBrief, resolve_beat_type
from src.script.script_validator import ScriptValidator

log = logging.getLogger(__name__)

# AE uses 6 beats for a 4-5 min video
AE_BEAT_ORDER = [
    BeatType.HOOK,
    BeatType.CONTEXT,
    BeatType.CONFLICT,
    BeatType.TURNING_POINT,
    BeatType.RESOLUTION,
    BeatType.LESSON,
]

BEAT_EMOTIONS = {
    BeatType.HOOK:          "exciting",
    BeatType.CONTEXT:       "neutral",
    BeatType.CONFLICT:      "sad",
    BeatType.TURNING_POINT: "exciting",
    BeatType.RESOLUTION:    "inspirational",
    BeatType.LESSON:        "neutral",
}

# Pexels search query per beat type — what image to fetch
BEAT_IMAGE_QUERIES = {
    BeatType.HOOK:          "determined person closeup portrait",
    BeatType.CONTEXT:       "vintage old photo office street",
    BeatType.CONFLICT:      "stressed person failure rejection",
    BeatType.TURNING_POINT: "light bulb idea realization moment",
    BeatType.RESOLUTION:    "success happy achievement celebration",
    BeatType.LESSON:        "wisdom book thinking philosophy",
}

MAX_SCRIPT_ATTEMPTS = 2


class NarrativeGeneratorV3:
    def __init__(self) -> None:
        self.validator = ScriptValidator()

    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if not has_llm_credentials():
            return self._offline_script(topic)

        for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
            try:
                script = self._generate_with_llm(topic, research)
                log.info("Script ready — %d beats (attempt %d)", len(script.beats), attempt)
                return script
            except Exception as exc:
                log.warning("LLM attempt %d failed: %s", attempt, exc)

        return self._offline_script(topic)

    def _generate_with_llm(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        facts = research.story_facts[:6]
        dates = research.dates[:3]
        numbers = research.key_numbers[:4]

        prompt = f"""You are writing a Tamil narration script for a YouTube channel called "துளிர்".
Style: EXACTLY like "Almost Everything" YouTube channel — real stories, whiteboard animation style.

TOPIC: {topic.title_ta}
Protagonist: {topic.protagonist} (age {topic.protagonist_age})
Core problem: {topic.core_problem}
Turning point: {topic.turning_point}
Lesson: {topic.lesson}
Key facts: {facts}
Key dates: {dates}
Key numbers: {numbers}

STRICT RULES — follow exactly:
1. EXACTLY 6 beats: hook, context, conflict, turning_point, resolution, lesson
2. Each beat narration: MAX 15 Tamil words. Short. Punchy. ONE idea per beat.
3. Use SPECIFIC details: exact year, exact age, exact place, exact number
4. Write in conversational Tamil — as if telling a friend, NOT formal essay
5. Hook beat: drop viewer into story mid-scene. Use a number or specific moment. NO greeting.
   GOOD: "1009 முறை. அவர் கையில் வெறும் ஒரு recipe மட்டும் இருந்தது."
   BAD: "வணக்கம்! இன்று ஒரு சுவாரஸ்யமான கதை..."
6. Each beat must have 2-3 visual_keywords (English words for image search)
7. on_screen_text: 1-3 word callout shown on screen (Tamil or number)

Return ONLY a JSON array of exactly 6 objects:
[
  {{
    "beat_type": "hook",
    "narration_ta": "12 Tamil words max here",
    "emotion": "exciting",
    "on_screen_text": "1009 முறை",
    "visual_keywords": ["rejection", "old man", "recipe"]
  }},
  ...
]

No markdown, no explanation. JSON array only."""

        raw = generate_text(prompt, max_tokens=3000)
        beats_data = extract_json_array(raw)
        if not beats_data:
            raise ValueError("No JSON array in LLM response")

        beats = []
        for i, item in enumerate(beats_data[:6]):
            bt = resolve_beat_type(item.get("beat_type"), AE_BEAT_ORDER[i % len(AE_BEAT_ORDER)])
            narration = item.get("narration_ta", "").strip()
            # Enforce word limit — truncate at sentence boundary if too long
            narration = _trim_to_sentences(narration, max_words=20)
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=narration,
                emotion=item.get("emotion", BEAT_EMOTIONS.get(bt, "neutral")),
                protagonist=topic.protagonist,
                on_screen_text=item.get("on_screen_text", ""),
                visual_keywords=item.get("visual_keywords", [bt.value]),
                retention_hook="",
                open_loop="",
                macro_index=i // 2,
            ))

        # Pad to 6 if LLM returned fewer
        while len(beats) < 6:
            bt = AE_BEAT_ORDER[len(beats)]
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=f"{topic.protagonist} — {bt.value}.",
                emotion=BEAT_EMOTIONS.get(bt, "neutral"),
                protagonist=topic.protagonist,
                visual_keywords=[bt.value],
            ))

        # Add CTA to final beat naturally
        last = beats[-1]
        if "subscribe" not in last.narration_ta.lower() and "bell" not in last.narration_ta.lower():
            beats[-1] = last.model_copy(update={
                "narration_ta": last.narration_ta.rstrip(".")
                    + ". Like செய்யுங்கள், subscribe செய்யுங்கள்."
            })

        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _offline_script(self, topic: TopicCandidate) -> NarrativeScript:
        """Hardcoded fallback script when LLM unavailable."""
        name = topic.protagonist or "அவர்"
        beats = [
            StoryBeat(beat_type=BeatType.HOOK, narration_ta=f"{name} — ஒரு தோல்வியில் இருந்து தொடங்கியது.", emotion="exciting", protagonist=name, visual_keywords=["person", "struggle"]),
            StoryBeat(beat_type=BeatType.CONTEXT, narration_ta=f"{name}-க்கு எல்லாம் சாதாரணமாக தொடங்கியது.", emotion="neutral", protagonist=name, visual_keywords=["vintage", "background"]),
            StoryBeat(beat_type=BeatType.CONFLICT, narration_ta="ஆனால் தோல்வி மீது தோல்வி வந்தது.", emotion="sad", protagonist=name, visual_keywords=["failure", "rejection"]),
            StoryBeat(beat_type=BeatType.TURNING_POINT, narration_ta="ஒரு நிமிடம் எல்லாவற்றையும் மாற்றியது.", emotion="exciting", protagonist=name, visual_keywords=["idea", "light"]),
            StoryBeat(beat_type=BeatType.RESOLUTION, narration_ta=f"{name} வெற்றி அடைந்தார்.", emotion="inspirational", protagonist=name, visual_keywords=["success", "achievement"]),
            StoryBeat(beat_type=BeatType.LESSON, narration_ta="தோல்வி, வெற்றியின் முதல் படி. Like செய்யுங்கள்!", emotion="neutral", protagonist=name, visual_keywords=["wisdom", "lesson"]),
        ]
        return NarrativeScript(topic=topic, beats=beats, format="long")


def _trim_to_sentences(text: str, max_words: int = 20) -> str:
    """Trim narration to max_words, cutting at sentence boundary."""
    words = text.split()
    if len(words) <= max_words:
        return text
    # Try to cut at last sentence boundary within limit
    truncated = " ".join(words[:max_words])
    last_period = max(truncated.rfind("।"), truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_period > len(truncated) // 2:
        return truncated[:last_period + 1]
    return truncated + "."
