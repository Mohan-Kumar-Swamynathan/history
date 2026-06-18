"""Per-segment visual variety — layouts, motion presets, and accent picks."""

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
)

TRANSITION_POOL = ("crossfade", "push", "wipe")


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
        layout_mirror = rng.random() < 0.45
        figure_emotion = self._pick_figure_emotion(rng, visual_segment)
        figure_scale = 0.92 + rng.random() * 0.18
        bg_seed_offset = rng.randint(0, 12)
        accent_icon = rng.choice(ACCENT_ICONS)
        sparkle_phase = rng.random()
        icon_count = 2 if visual_segment % 2 == 0 else 3
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
        return rng.choice(TRANSITION_POOL)

    def _pick_figure_emotion(self, rng: random.Random, visual_segment: int) -> str:
        preferred = _EMOTION_MAP.get(self._base_emotion, "neutral")
        pool = [preferred] + [emotion for emotion in FIGURE_EMOTION_POOL if emotion != preferred]
        index = (visual_segment + rng.randint(0, 2)) % len(pool)
        return pool[index]


_EMOTION_MAP = {
    "sad": "sad",
    "hope": "happy",
    "exciting": "celebrating",
    "inspirational": "celebrating",
    "thinking": "thinking",
    "neutral": "neutral",
}
