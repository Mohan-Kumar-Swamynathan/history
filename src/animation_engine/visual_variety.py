"""Per-segment visual variety — layouts, motion presets, and accent picks.

Improvements:
- Beat-type determines emotion pool (not random) — sad scenes stay sad
- Layout mirror only for resolution/lesson beats (not mid-story)
- Richer motion variant set
- Icon count scales with beat type importance
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.core.models import BeatType

MOTION_VARIANTS = (
    "bounce_entrance",
    "gentle_sway",
    "slide_left",
    "slide_right",
    "float_up",
    "pulse_zoom",
    "drift_right",
    "rise_in",
)

FIGURE_EMOTION_POOL = (
    "neutral",
    "happy",
    "thinking",
    "celebrating",
    "walking",
    "sad",
)

ACCENT_ICONS = (
    "star",
    "lightbulb",
    "heart",
    "arrow_up",
    "checkmark",
    "bell",
    "question_mark",
    "graph_up",
    "sprout",
    "thumbs_up",
)

TRANSITION_POOL = ("crossfade", "push", "wipe")

# Beat type → allowed figure emotions
BEAT_EMOTION_MAP: dict[BeatType, tuple[str, ...]] = {
    BeatType.HOOK:          ("thinking", "neutral"),
    BeatType.CONTEXT:       ("neutral", "walking"),
    BeatType.CONFLICT:      ("sad", "thinking"),
    BeatType.ESCALATION:    ("sad", "sad", "thinking"),   # weighted toward sad
    BeatType.TURNING_POINT: ("thinking", "happy", "walking"),
    BeatType.RESOLUTION:    ("happy", "celebrating"),
    BeatType.LESSON:        ("neutral", "happy"),
    BeatType.CTA:           ("celebrating", "happy"),
}

# Beat type → icon count
BEAT_ICON_COUNT: dict[BeatType, int] = {
    BeatType.HOOK:          2,
    BeatType.CONTEXT:       1,
    BeatType.CONFLICT:      2,
    BeatType.ESCALATION:    2,
    BeatType.TURNING_POINT: 3,
    BeatType.RESOLUTION:    2,
    BeatType.LESSON:        2,
    BeatType.CTA:           3,
}

# Beat types where layout mirror makes sense (protagonist on left, text right)
MIRROR_BEATS = {BeatType.RESOLUTION, BeatType.LESSON, BeatType.CTA}


@dataclass(frozen=True)
class VisualSegmentStyle:
    motion_variant: str
    layout_mirror: bool
    figure_emotion: str
    figure_scale: float
    bg_seed_offset: int
    accent_icon: str
    sparkle_phase: float
    icon_count: int


class VisualVarietyDirector:
    def __init__(self, scene_key: str, base_emotion: str, beat_type: BeatType) -> None:
        self._scene_key = scene_key
        self._base_emotion = base_emotion
        self._beat_type = beat_type

    def segment_style(self, visual_segment: int) -> VisualSegmentStyle:
        rng = random.Random(f"{self._scene_key}:{visual_segment}")
        motion_variant = rng.choice(MOTION_VARIANTS)
        # Only mirror for resolution/lesson/cta beats — elsewhere keep figure right
        layout_mirror = self._beat_type in MIRROR_BEATS and rng.random() < 0.55
        figure_emotion = self._pick_figure_emotion(rng, visual_segment)
        figure_scale = 0.92 + rng.random() * 0.16
        bg_seed_offset = rng.randint(0, 12)
        accent_icon = rng.choice(ACCENT_ICONS)
        sparkle_phase = rng.random()
        icon_count = BEAT_ICON_COUNT.get(self._beat_type, 2)
        return VisualSegmentStyle(
            motion_variant=motion_variant,
            layout_mirror=layout_mirror,
            figure_emotion=figure_emotion,
            figure_scale=figure_scale,
            bg_seed_offset=bg_seed_offset,
            accent_icon=accent_icon,
            sparkle_phase=sparkle_phase,
            icon_count=icon_count,
        )

    def scene_transition(self) -> str:
        rng = random.Random(self._scene_key)
        if self._beat_type in {BeatType.HOOK, BeatType.TURNING_POINT, BeatType.CTA}:
            return rng.choice(("push", "wipe", "crossfade"))
        if self._beat_type in {BeatType.CONFLICT, BeatType.ESCALATION}:
            return "crossfade"
        return rng.choice(TRANSITION_POOL)

    def _pick_figure_emotion(self, rng: random.Random, visual_segment: int) -> str:
        pool = BEAT_EMOTION_MAP.get(self._beat_type, FIGURE_EMOTION_POOL)
        return pool[visual_segment % len(pool)]


_EMOTION_MAP = {
    "sad":           "sad",
    "hope":          "happy",
    "exciting":      "celebrating",
    "inspirational": "celebrating",
    "thinking":      "thinking",
    "neutral":       "neutral",
    "celebrating":   "celebrating",
    "happy":         "happy",
}
