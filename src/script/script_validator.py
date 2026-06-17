"""Story script validation gates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from src.core.config_loader import load_topics_config
from src.core.models import NarrativeScript, StoryMode, TopicCandidate


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    word_count: int = 0


class ScriptValidator:
    def validate_long_script(self, script: NarrativeScript, topic: TopicCandidate) -> ValidationResult:
        config = load_topics_config().get("script_targets", {})
        min_words = int(config.get("long_min_words", 1000))
        max_words = int(config.get("long_max_words", 2000))
        min_per_beat = int(config.get("long_min_words_per_beat", 30))
        expected_beats = int(config.get("long_beat_count", 24))
        blocklist = load_topics_config().get("blocklist_patterns", [])

        errors: List[str] = []
        word_count = self._count_words(script.full_narration_ta)

        if len(script.beats) < expected_beats:
            errors.append(f"Expected {expected_beats} beats, got {len(script.beats)}")
        if word_count < min_words:
            errors.append(f"Word count {word_count} below minimum {min_words}")
        if word_count > max_words:
            errors.append(f"Word count {word_count} above maximum {max_words}")

        for index, beat in enumerate(script.beats):
            beat_words = self._count_words(beat.narration_ta)
            if beat_words < min_per_beat:
                errors.append(f"Beat {index} has only {beat_words} words (min {min_per_beat})")

        haystack = script.full_narration_ta.lower()
        for pattern in blocklist:
            if pattern.lower() in haystack:
                errors.append(f"Blocklist phrase found: {pattern}")

        if topic.story_mode == StoryMode.BIOGRAPHICAL:
            has_number = bool(re.search(r"\d", script.full_narration_ta))
            has_name = topic.protagonist.lower() in script.full_narration_ta.lower()
            if not has_number:
                errors.append("Biographical script missing numbers/dates")
            if not has_name:
                errors.append("Biographical script missing protagonist name")

        return ValidationResult(valid=not errors, errors=errors, word_count=word_count)

    def validate_shorts_script(self, script: NarrativeScript) -> ValidationResult:
        config = load_topics_config().get("script_targets", {})
        min_words = int(config.get("shorts_min_words", 80))
        max_words = int(config.get("shorts_max_words", 150))
        errors: List[str] = []
        word_count = self._count_words(script.full_narration_ta)
        if word_count < min_words:
            errors.append(f"Shorts word count {word_count} below {min_words}")
        if word_count > max_words:
            errors.append(f"Shorts word count {word_count} above {max_words}")
        return ValidationResult(valid=not errors, errors=errors, word_count=word_count)

    def _count_words(self, text: str) -> int:
        return len(re.findall(r"\S+", text))
