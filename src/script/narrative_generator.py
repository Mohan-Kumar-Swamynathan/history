"""24-beat long-form narrative generation — Thulir storytelling."""

from __future__ import annotations

import json
import logging
import re
from typing import List

from src.core.config_loader import load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_policy import STAGE_LONG_SCRIPT, should_use_llm
from src.core.models import BeatType, NarrativeScript, ResearchBrief, StoryBeat, TopicCandidate
from src.script.channel_intro import append_outro_cta, prepend_greeting
from src.script.offline_story_bank import BEAT_ORDER, BEAT_EMOTIONS, build_offline_long_script
from src.script.script_validator import ScriptValidator

log = logging.getLogger(__name__)


class NarrativeGenerator:
    def __init__(self) -> None:
        self.validator = ScriptValidator()

    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if has_llm_credentials() and should_use_llm(STAGE_LONG_SCRIPT):
            try:
                script = self._generate_with_llm(topic, research)
                result = self.validator.validate_long_script(script, topic)
                if result.valid:
                    return script
                log.warning("Script validation failed: %s — retrying", result.errors)
                script = self._generate_with_llm(topic, research, feedback=result.errors)
                result = self.validator.validate_long_script(script, topic)
                if result.valid:
                    return script
                log.warning("Retry failed validation: %s — offline fallback", result.errors)
            except Exception as exc:
                log.warning("LLM narrative failed: %s — using offline script", exc)
        return build_offline_long_script(topic, research)

    def _generate_with_llm(
        self,
        topic: TopicCandidate,
        research: ResearchBrief,
        feedback: List[str] | None = None,
    ) -> NarrativeScript:
        targets = load_topics_config().get("script_targets", {})
        beat_count = int(targets.get("long_beat_count", 24))
        min_words = int(targets.get("long_min_words", 1000))
        max_words = int(targets.get("long_max_words", 2000))

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
- Exactly {beat_count} beats in this order (3 each): hook, context, conflict, escalation, turning_point, resolution, lesson, cta
- Each beat 40-80 words — specific numbers, dialogue, places
- 3rd person narration. No preaching. Story is the topic, lesson is the reward
- Beat 1 must open with channel greeting: "வணக்கம்! துளிர் channel..."
- Final beat must ask viewer to like, share, subscribe, and hit the bell
- Beat 2 must contain open loop
{feedback_text}

Return JSON array of {beat_count} objects:
[{{"beat_type":"hook","narration_ta":"...","emotion":"exciting",
"on_screen_text":"Age 10","visual_keywords":["street","newspaper"],
"retention_hook":"question","open_loop":"..."}}]"""

        raw = generate_text(prompt, max_tokens=16000)
        beats = self._parse_beats(raw, topic)
        if beats:
            beats[0] = beats[0].model_copy(
                update={"narration_ta": prepend_greeting(beats[0].narration_ta)}
            )
            beats[-1] = beats[-1].model_copy(
                update={"narration_ta": append_outro_cta(beats[-1].narration_ta)}
            )
        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _parse_beats(self, raw: str, topic: TopicCandidate) -> List[StoryBeat]:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            raise ValueError("No beat array in LLM response")
        beat_data = json.loads(match.group())
        beats: List[StoryBeat] = []
        for index, item in enumerate(beat_data):
            beat_type = BeatType(item.get("beat_type", BEAT_ORDER[index % len(BEAT_ORDER)].value))
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
