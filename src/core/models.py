"""Pydantic domain models for the unified video pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class BeatType(str, Enum):
    HOOK = "hook"
    CONTEXT = "context"
    CONFLICT = "conflict"
    ESCALATION = "escalation"
    TURNING_POINT = "turning_point"
    RESOLUTION = "resolution"
    LESSON = "lesson"
    CTA = "cta"


class SceneType(str, Enum):
    CHARACTER = "character"
    TIMELINE = "timeline"
    STATISTIC = "statistic"
    COMPARISON = "comparison"
    MAP = "map"
    QUOTE = "quote"
    DIAGRAM = "diagram"


class VisualStyle(str, Enum):
    WHITEBOARD = "whiteboard"
    DOCUMENTARY = "documentary"


class StoryMode(str, Enum):
    BIOGRAPHICAL = "biographical"
    COMPOSITE = "composite"


class ContentBucket(str, Enum):
    SUCCESS_FAILURE = "success_failure"
    BUSINESS = "business"
    HISTORICAL_STORY = "historical_story"
    PSYCHOLOGY = "psychology"


class RetentionHookType(str, Enum):
    QUESTION = "question"
    SURPRISE = "surprise"
    CONFLICT = "conflict"
    REVEAL = "reveal"
    TWIST = "twist"
    EMOTION = "emotion"


class TopicCandidate(BaseModel):
    title_ta: str
    category: str = "storytelling"
    hook: str = ""
    protagonist: str = "நாயகன்"
    protagonist_age: str = ""
    situation: str = ""
    core_problem: str = ""
    emotional_hook: str = ""
    turning_point: str = ""
    lesson: str = ""
    hook_question: str = ""
    open_loop: str = ""
    story_mode: StoryMode = StoryMode.COMPOSITE
    content_bucket: ContentBucket = ContentBucket.SUCCESS_FAILURE
    curiosity_score: float = 0.0
    emotion_score: float = 0.0
    story_score: float = 0.0
    lesson_score: float = 0.0
    engagement_score: float = 0.0
    novelty_score: float = 0.0
    search_score: float = 0.0
    source: str = "offline"
    wikipedia_subject: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_score(self) -> float:
        from src.core.config_loader import load_topics_config
        weights = load_topics_config().get("scoring_weights", {})
        if weights.get("curiosity") is not None:
            return (
                self.curiosity_score * float(weights.get("curiosity", 0.40))
                + self.emotion_score * float(weights.get("emotion", 0.25))
                + self.story_score * float(weights.get("story", 0.20))
                + self.lesson_score * float(weights.get("lesson", 0.15))
            )
        return (
            self.engagement_score
            + self.novelty_score
            + self.search_score
            + self.emotion_score
        )


class ResearchBrief(BaseModel):
    topic: str
    facts: List[str] = Field(default_factory=list)
    story_facts: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    figures: List[str] = Field(default_factory=list)
    timeline: List[str] = Field(default_factory=list)
    key_numbers: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class StoryBeat(BaseModel):
    beat_type: BeatType
    narration_ta: str
    emotion: str = "neutral"
    protagonist: str = "நாயகன்"
    duration_seconds: float = 5.0
    entities: Dict[str, List[str]] = Field(default_factory=dict)
    on_screen_text: str = ""
    visual_keywords: List[str] = Field(default_factory=list)
    retention_hook: str = ""
    open_loop: str = ""
    macro_index: int = 0


class NarrativeScript(BaseModel):
    topic: TopicCandidate
    beats: List[StoryBeat]
    full_narration_ta: str = ""
    format: str = "long"

    def model_post_init(self, __context: Any) -> None:
        if not self.full_narration_ta:
            self.full_narration_ta = " ".join(beat.narration_ta for beat in self.beats)


class ShortsScript(BaseModel):
    topic: TopicCandidate
    beats: List[StoryBeat]
    full_narration_ta: str = ""
    target_word_count: int = 120

    def model_post_init(self, __context: Any) -> None:
        if not self.full_narration_ta:
            self.full_narration_ta = " ".join(beat.narration_ta for beat in self.beats)


class ScenePlan(BaseModel):
    beat: StoryBeat
    scene_type: SceneType = SceneType.CHARACTER
    visual_style: VisualStyle = VisualStyle.WHITEBOARD
    camera: str = "slow_zoom"
    emotion: str = "neutral"
    assets: List[str] = Field(default_factory=list)
    protagonist: str = "நாயகன்"
    background_key: Optional[str] = None
    hero_icon: Optional[str] = None
    icon_placement: str = "bottom_left"


class AnimationPlan(BaseModel):
    scene_plan: ScenePlan
    camera_motion: str = "zoom_in"
    element_animations: List[str] = Field(default_factory=lambda: ["draw", "fade"])
    transition: str = "crossfade"
    figure_emotion: str = "neutral"
    bg_progress_curve: str = "ease_in"
    figure_progress_curve: str = "ease_in"


class WordTiming(BaseModel):
    word: str
    start_ms: int
    end_ms: int


class BeatAudioSegment(BaseModel):
    beat_index: int
    audio_path: str
    duration_seconds: float
    word_timings: List[WordTiming] = Field(default_factory=list)
    start_ms: int = 0


class NarrationBundle(BaseModel):
    narration_path: str
    segments: List[BeatAudioSegment] = Field(default_factory=list)
    all_word_timings: List[WordTiming] = Field(default_factory=list)
    total_duration_seconds: float = 0.0


class RenderedScene(BaseModel):
    scene_index: int
    frame_count: int
    duration_seconds: float
    word_timings: List[WordTiming] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    title_ta: str
    title_options: List[str] = Field(default_factory=list)
    description_ta: str
    tags: List[str] = Field(default_factory=list)
    chapters: List[Dict[str, str]] = Field(default_factory=list)
    pinned_comment: str = ""
    thumbnail_text: str = ""
    thumbnail_concept: str = ""
    emotion_trigger: str = ""


class VideoPackage(BaseModel):
    run_id: str
    topic: TopicCandidate
    long_video_path: str
    shorts_video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    srt_path: Optional[str] = None
    ass_path: Optional[str] = None
    metadata: Optional[VideoMetadata] = None
    format: str = "long"
