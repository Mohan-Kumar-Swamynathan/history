"""24-beat long-form narrative generation — Thulir storytelling."""

from __future__ import annotations

import logging
import re
from typing import List

from src.core.config_loader import load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_json_parser import extract_json_array
from src.core.llm_policy import (
    STAGE_LONG_SCRIPT,
    max_tokens_for_stage,
    preferred_provider_for_stage,
    resolve_llm_mode,
    should_use_llm,
)
from src.core.models import BeatType, NarrativeScript, ResearchBrief, StoryBeat, TopicCandidate, resolve_beat_type
from src.script.channel_intro import append_outro_cta, prepend_greeting
from src.script.offline_story_bank import BEAT_EMOTIONS, build_offline_long_script, resolve_long_beat_order
from src.script.script_enricher import enrich_long_script
from src.script.script_validator import ScriptValidator

log = logging.getLogger(__name__)

MAX_SCRIPT_ATTEMPTS = 2


class NarrativeGenerator:
    def __init__(self) -> None:
        self.validator = ScriptValidator()

    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if not should_use_llm(STAGE_LONG_SCRIPT):
            log.info("Using offline long script (%d beats, llm_mode=%s)", len(resolve_long_beat_order()), resolve_llm_mode())
            return build_offline_long_script(topic, research)

        if not has_llm_credentials():
            return build_offline_long_script(topic, research)

        validation_errors: List[str] | None = None
        for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
            try:
                script = self._generate_with_llm(topic, research, feedback=validation_errors)
                script = enrich_long_script(script, topic, research)
                result = self.validator.validate_long_script(script, topic)
                if result.valid:
                    log.info(
                        "Long script accepted via llm (attempt %d, %d words)",
                        attempt,
                        result.word_count,
                    )
                    return script
                validation_errors = result.errors
                log.warning("Script validation attempt %d failed: %s", attempt, result.errors)
            except Exception as exc:
                validation_errors = [str(exc)]
                log.warning("LLM narrative attempt %d failed: %s", attempt, exc)

        log.warning("Using offline long script after %d LLM attempts", MAX_SCRIPT_ATTEMPTS)
        return build_offline_long_script(topic, research)

    def _generate_with_llm(
        self,
        topic: TopicCandidate,
        research: ResearchBrief,
        feedback: List[str] | None = None,
    ) -> NarrativeScript:
        targets = load_topics_config().get("script_targets", {})
        beat_count = len(resolve_long_beat_order())
        min_words = int(targets.get("long_min_words", 600))
        max_words = int(targets.get("long_max_words", 900))
        min_per_beat = max(40, min_words // beat_count)

        feedback_text = ""
        if feedback:
            feedback_text = f"\nFix these validation errors: {'; '.join(feedback)}"

        prompt = f"""நீங்கள் "துளிர்" Tamil storytelling YouTube channel-க்கு script எழுதுகிறீர்கள்.
Style: Almost Everything — real story, 3rd person, emotional journey. NOT motivation speech. NOT fact list.

TOPIC: {topic.title_ta}
Protagonist: {topic.protagonist} (age {topic.protagonist_age})
Situation: {topic.situation}
Problem: {topic.core_problem}
Emotional hook: {topic.emotional_hook}
Turning point: {topic.turning_point}
Lesson: {topic.lesson}
Opening question: {topic.hook_question}
Open loop: {topic.open_loop}
Research: {research.story_facts[:5]}

RULES:
- Total {min_words}-{max_words} Tamil words across all beats
- Exactly {beat_count} beats in this order (repeat cycle): hook, context, conflict, escalation, turning_point, resolution, lesson, cta
- Each beat MUST be {min_per_beat}-70 Tamil words with specific numbers, dialogue, places
- Include protagonist name "{topic.protagonist}" and at least 3 numbers/dates across script
- 3rd person narration. No preaching. Story is the topic, lesson is the reward
- Beat 1 opens with: "வணக்கம்! துளிர் channel..."
- Final beat asks viewer to like, share, subscribe, and hit the bell
- Beat 2 must contain open loop
{feedback_text}

Return JSON array of exactly {beat_count} objects:
[{{"beat_type":"hook","narration_ta":"...","emotion":"exciting",
"on_screen_text":"Age 10","visual_keywords":["street","newspaper"],
"retention_hook":"question","open_loop":"..."}}]

Return ONLY the JSON array. No markdown fences."""

        raw = generate_text(
            prompt,
            max_tokens=max_tokens_for_stage(STAGE_LONG_SCRIPT, 8000),
            preferred=preferred_provider_for_stage(STAGE_LONG_SCRIPT),
        )
        beats = self._parse_beats(raw, topic)
        if not beats:
            raise ValueError("No beat array in LLM response")
        beats[0] = beats[0].model_copy(
            update={"narration_ta": prepend_greeting(beats[0].narration_ta)}
        )
        beats[-1] = beats[-1].model_copy(
            update={"narration_ta": append_outro_cta(beats[-1].narration_ta)}
        )
        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _parse_beats(self, raw: str, topic: TopicCandidate) -> List[StoryBeat]:
        beat_data = extract_json_array(raw)
        if not beat_data:
            raise ValueError("No beat array in LLM response")
        beat_order = resolve_long_beat_order()
        beats: List[StoryBeat] = []
        for index, item in enumerate(beat_data):
            beat_type = resolve_beat_type(
                item.get("beat_type"),
                beat_order[index % len(beat_order)],
            )
            beats.append(
                StoryBeat(
                    beat_type=beat_type,
                    narration_ta=item["narration_ta"],
                    emotion=item.get("emotion", BEAT_EMOTIONS.get(beat_type, "neutral")),
                    protagonist=topic.protagonist,
                    on_screen_text=item.get("on_screen_text", ""),
                    visual_keywords=item.get("visual_keywords", []),
                    retention_hook=item.get("retention_hook", ""),
                    open_loop=item.get("open_loop", ""),
                    macro_index=index // 3,
                )
            )
        return beats
