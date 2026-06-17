"""Standalone Shorts script — 80-150 words, 30-60 seconds."""

from __future__ import annotations

import json
import logging
import re
from typing import List

from src.core.config_loader import load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_policy import STAGE_SHORTS_SCRIPT, should_use_llm
from src.core.models import BeatType, NarrativeScript, ResearchBrief, ShortsScript, StoryBeat, TopicCandidate, resolve_beat_type
from src.script.channel_intro import append_outro_cta, prepend_greeting
from src.script.offline_story_bank import _expand_narration
from src.script.script_validator import ScriptValidator

log = logging.getLogger(__name__)

SHORTS_BEAT_TYPES = [
    BeatType.HOOK,
    BeatType.CONFLICT,
    BeatType.TURNING_POINT,
    BeatType.LESSON,
    BeatType.CTA,
]


class ShortsScriptGenerator:
    def __init__(self) -> None:
        self.validator = ScriptValidator()

    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> ShortsScript:
        if has_llm_credentials() and should_use_llm(STAGE_SHORTS_SCRIPT):
            try:
                script = self._generate_with_llm(topic, research)
                narrative = NarrativeScript(topic=topic, beats=script.beats, format="short")
                result = self.validator.validate_shorts_script(narrative)
                if result.valid:
                    return script
            except Exception as exc:
                log.warning("LLM shorts script failed: %s — offline", exc)
        return self._generate_offline(topic)

    def _generate_with_llm(self, topic: TopicCandidate, research: ResearchBrief) -> ShortsScript:
        targets = load_topics_config().get("script_targets", {})
        min_words = int(targets.get("shorts_min_words", 80))
        max_words = int(targets.get("shorts_max_words", 150))
        beat_count = int(targets.get("shorts_beat_count", 5))

        prompt = f"""60-second Tamil YouTube Shorts script — Almost Everything storytelling style.

Story: {topic.title_ta}
Character: {topic.protagonist} ({topic.protagonist_age})
Problem: {topic.core_problem}
Hook: {topic.hook_question}
Turning point: {topic.turning_point}
Lesson: {topic.lesson}

FORMAT: exactly {beat_count} beats, {min_words}-{max_words} total Tamil words.
Structure: hook → conflict → turning_point → lesson → cta
Use ONLY these beat_type values: hook, conflict, turning_point, lesson, cta
3rd person. Specific numbers. Emotional. NOT generic motivation.

Return JSON array:
[{{"beat_type":"hook","narration_ta":"...","emotion":"exciting","on_screen_text":"...",
"visual_keywords":["street"],"retention_hook":"question"}}]"""

        raw = generate_text(prompt, max_tokens=2000)
        beats = self._parse_beats(raw, topic)
        return ShortsScript(topic=topic, beats=beats)

    def _generate_offline(self, topic: TopicCandidate) -> ShortsScript:
        p = topic.protagonist
        narrations = [
            prepend_greeting(_expand_narration(
                f"{topic.hook_question} {p}-ன் கதை இது. {topic.situation or 'ஒரு சாதாரண வாழ்க்கை'}.", 16
            ), is_shorts=True),
            _expand_narration(f"ஆனால் {topic.core_problem}. {topic.emotional_hook} அந்த தருணம் அவரை உடைத்தது.", 18),
            _expand_narration(f"ஆனால் {topic.turning_point}. யாரும் எதிர்பார்க்காத மாற்றம் வந்தது.", 18),
            _expand_narration(f"இன்று {p} அந்த கதையை நினைவு கூர்ந்தால் சொல்வார் — {topic.lesson}.", 16),
            append_outro_cta(_expand_narration(
                "இந்த கதை உங்களுக்கு inspiration ஆக இருந்தால் like, share, subscribe செய்யுங்கள்.",
                14,
            ), is_shorts=True),
        ]
        beats = [
            StoryBeat(
                beat_type=beat_type,
                narration_ta=narrations[index],
                emotion=["exciting", "sad", "thinking", "inspirational", "exciting"][index],
                protagonist=p,
                on_screen_text=["!", "?", "திருப்புமுனை", "பாடம்", "துளிர்"][index],
                visual_keywords=["street", "rain", "lightbulb", "star", "bell"][index: index + 1],
                retention_hook=["question", "emotion", "twist", "reveal", "surprise"][index],
            )
            for index, beat_type in enumerate(SHORTS_BEAT_TYPES)
        ]
        return ShortsScript(topic=topic, beats=beats)

    def _parse_beats(self, raw: str, topic: TopicCandidate) -> List[StoryBeat]:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            raise ValueError("No shorts beat array")
        beat_data = json.loads(match.group())
        beats: List[StoryBeat] = []
        for index, item in enumerate(beat_data):
            beat_type = resolve_beat_type(
                item.get("beat_type"),
                SHORTS_BEAT_TYPES[index % len(SHORTS_BEAT_TYPES)],
            )
            beats.append(
                StoryBeat(
                    beat_type=beat_type,
                    narration_ta=item["narration_ta"],
                    emotion=item.get("emotion", "neutral"),
                    protagonist=topic.protagonist,
                    on_screen_text=item.get("on_screen_text", ""),
                    visual_keywords=item.get("visual_keywords", []),
                    retention_hook=item.get("retention_hook", ""),
                )
            )
        return beats
