"""Story beat extraction and entity parsing."""

from __future__ import annotations

import re
from typing import Dict, List

from src.core.models import NarrativeScript, StoryBeat


class StoryBeatExtractor:
    def extract(self, script: NarrativeScript) -> List[StoryBeat]:
        enriched_beats: List[StoryBeat] = []
        for beat in script.beats:
            entities = self._extract_entities(beat.narration_ta)
            word_count = len(beat.narration_ta.split())
            duration = max(3.5, word_count / 2.2)
            enriched_beats.append(
                beat.model_copy(
                    update={
                        "entities": entities,
                        "duration_seconds": duration,
                        "protagonist": script.topic.protagonist,
                    }
                )
            )
        return enriched_beats

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        numbers = re.findall(r"\d+", text)
        dates = re.findall(r"\b(19|20)\d{2}\b", text)
        locations = []
        for keyword in ("சென்னை", "இந்தியா", "அலுவலக", "வீடு"):
            if keyword in text:
                locations.append(keyword)
        actions = []
        for keyword in ("மாற்ற", "முடிவு", "பயம்", "வெற்றி"):
            if keyword in text:
                actions.append(keyword)
        return {
            "numbers": numbers,
            "dates": dates,
            "locations": locations,
            "actions": actions,
        }
