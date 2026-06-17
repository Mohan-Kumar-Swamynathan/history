"""Map story beats to visual scene plans."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from icon_library import pick_icon_for_text  # noqa: E402
from src.core.config_loader import load_emotions_config
from src.core.models import (
    BeatType,
    ResearchBrief,
    ScenePlan,
    SceneType,
    StoryBeat,
    VisualStyle,
)

ICON_BY_BEAT = {
    BeatType.HOOK: ("top_right", "lightbulb"),
    BeatType.CONFLICT: ("left_margin", "anxious_face"),
    BeatType.ESCALATION: ("left_margin", "sad_face"),
    BeatType.TURNING_POINT: ("top_right", "arrow_up"),
    BeatType.RESOLUTION: ("bottom_center", "graph_up"),
    BeatType.LESSON: ("top_right", "star"),
    BeatType.CTA: ("bottom_center", "bell"),
}


class VisualPlanner:
    def plan_scenes(self, beats: List[StoryBeat], research: ResearchBrief) -> List[ScenePlan]:
        return [self.plan_scene(beat, research, index) for index, beat in enumerate(beats)]

    def plan_scene(self, beat: StoryBeat, research: ResearchBrief, scene_index: int) -> ScenePlan:
        scene_type = self._detect_scene_type(beat, research)
        visual_style = (
            VisualStyle.DOCUMENTARY
            if scene_type in {SceneType.STATISTIC, SceneType.TIMELINE, SceneType.MAP}
            else VisualStyle.WHITEBOARD
        )
        assets = self._build_assets(beat, research, scene_type)
        background_key = self._background_key(beat, scene_index)
        placement, default_icon = ICON_BY_BEAT.get(beat.beat_type, ("bottom_left", "lightbulb"))
        hero_icon = pick_icon_for_text(beat.narration_ta) or default_icon

        return ScenePlan(
            beat=beat,
            scene_type=scene_type,
            visual_style=visual_style,
            camera="slow_zoom",
            emotion=beat.emotion,
            assets=assets,
            protagonist=beat.protagonist,
            background_key=background_key,
            hero_icon=hero_icon,
            icon_placement=placement,
        )

    def _detect_scene_type(self, beat: StoryBeat, research: ResearchBrief) -> SceneType:
        text = beat.narration_ta
        if beat.entities.get("numbers"):
            return SceneType.STATISTIC
        if beat.entities.get("dates") or research.dates:
            return SceneType.TIMELINE
        if beat.entities.get("locations") or research.locations:
            return SceneType.MAP
        if "?" in text or '"' in text:
            return SceneType.QUOTE
        if "முன்" in text and "பின்" in text:
            return SceneType.COMPARISON
        if "படி" in text or "வழி" in text:
            return SceneType.DIAGRAM
        return SceneType.CHARACTER

    def _build_assets(self, beat: StoryBeat, research: ResearchBrief, scene_type: SceneType) -> List[str]:
        assets = [beat.protagonist, beat.emotion]
        assets.extend(beat.entities.get("actions", []))
        assets.extend(beat.entities.get("locations", []))
        if scene_type == SceneType.STATISTIC:
            assets.extend(beat.entities.get("numbers", []))
        return list(dict.fromkeys(assets))

    def _background_key(self, beat: StoryBeat, scene_index: int) -> str:
        keyword_to_bg = {
            "street": "clean",
            "office": "office",
            "factory": "office",
            "school": "clean",
            "home": "home",
            "rain": "heart_break",
            "empty_room": "think",
            "lightbulb": "think",
            "path_up": "path_up",
            "sunrise": "path_up",
            "trophy": "trophy",
            "graph_up": "path_up",
            "celebration": "trophy",
            "newspaper": "clean",
            "sad": "heart_break",
        }
        for keyword in beat.visual_keywords:
            mapped = keyword_to_bg.get(keyword.lower())
            if mapped:
                return mapped

        text = beat.narration_ta.lower()
        keyword_map = {
            "சம்பள": "money",
            "வேலை": "office",
            "அலுவலக": "office",
            "மொபைல்": "phone",
            "வீடு": "home",
            "யோசி": "think",
            "வெற்றி": "trophy",
            "பயம்": "heart_break",
            "மாற்ற": "path_up",
        }
        for keyword, key in keyword_map.items():
            if keyword in text:
                return key
        defaults = ["clean", "office", "heart_break", "think", "path_up", "home", "trophy", "clean"]
        return defaults[scene_index % len(defaults)]
