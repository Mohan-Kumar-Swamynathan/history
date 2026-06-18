"""Expand LLM scripts to meet duration and beat-length targets."""

from __future__ import annotations

import re

from src.core.config_loader import load_topics_config
from src.core.models import NarrativeScript, ResearchBrief, StoryBeat, TopicCandidate
from src.script.offline_story_bank import _expand_narration, _min_words_per_beat


def enrich_long_script(
    script: NarrativeScript,
    topic: TopicCandidate,
    research: ResearchBrief,
) -> NarrativeScript:
    targets = load_topics_config().get("script_targets", {})
    min_total_words = int(targets.get("long_min_words", 600))
    min_per_beat = _min_words_per_beat()

    enriched_beats = [
        _enrich_beat(beat, topic, research, min_per_beat)
        for beat in script.beats
    ]
    script = _rebuild_script(script, enriched_beats)
    return _pad_total_word_count(script, topic, research, min_total_words)


def _rebuild_script(script: NarrativeScript, beats: list[StoryBeat]) -> NarrativeScript:
    narration = " ".join(beat.narration_ta for beat in beats)
    return NarrativeScript(
        topic=script.topic,
        beats=beats,
        format=script.format,
        full_narration_ta=narration,
    )


def _enrich_beat(
    beat: StoryBeat,
    topic: TopicCandidate,
    research: ResearchBrief,
    min_per_beat: int,
) -> StoryBeat:
    narration = beat.narration_ta.strip()
    word_count = _count_words(narration)
    if word_count >= min_per_beat:
        return beat

    context_snippet = _context_snippet(topic, research, beat.beat_type.value)
    expanded_base = f"{narration} {context_snippet}".strip()
    if topic.protagonist.lower() not in expanded_base.lower():
        expanded_base = f"{topic.protagonist}. {expanded_base}"
    if topic.story_mode.value == "biographical" and not re.search(r"\d", expanded_base):
        expanded_base = f"{expanded_base} {topic.protagonist_age or '1990'}."
    return beat.model_copy(
        update={"narration_ta": _expand_narration(expanded_base, min_per_beat)}
    )


def _pad_total_word_count(
    script: NarrativeScript,
    topic: TopicCandidate,
    research: ResearchBrief,
    min_total_words: int,
) -> NarrativeScript:
    beats = list(script.beats)
    padding_fact = research.story_facts[0] if research.story_facts else topic.situation
    beat_index = 0
    while _count_words(" ".join(beat.narration_ta for beat in beats)) < min_total_words:
        beat = beats[beat_index % len(beats)]
        extra = f" {topic.protagonist}-ன் கதையில் {padding_fact}."
        beats[beat_index % len(beats)] = beat.model_copy(
            update={"narration_ta": _expand_narration(beat.narration_ta + extra, _min_words_per_beat())}
        )
        beat_index += 1
        if beat_index > len(beats) * 4:
            break
    return _rebuild_script(script, beats)


def _context_snippet(topic: TopicCandidate, research: ResearchBrief, beat_type: str) -> str:
    fact = research.story_facts[0] if research.story_facts else topic.situation
    snippets = {
        "hook": f"{topic.hook_question} {topic.open_loop}",
        "context": f"{topic.situation} {fact}",
        "conflict": f"{topic.core_problem} {topic.emotional_hook}",
        "escalation": f"{topic.core_problem} அந்த நாட்கள் மிகக் கடினமாக இருந்தன.",
        "turning_point": f"{topic.turning_point} யாரும் எதிர்பார்க்கவில்லை.",
        "resolution": f"{topic.protagonist} மீண்டும் எழுந்தார்.",
        "lesson": f"பாடம்: {topic.lesson}",
        "cta": "இந்த கதை உங்களுக்கு பிடித்திருந்தால் like, share, subscribe செய்யுங்கள்.",
    }
    return snippets.get(beat_type, fact or topic.hook)


def _count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))
