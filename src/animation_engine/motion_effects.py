"""Per-frame motion calculation — emotion-aware camera and element offsets."""

from __future__ import annotations

import math
from typing import Dict

from src.core.config_loader import load_emotions_config
from src.core.models import BeatType


class MotionCalculator:
    def __init__(self, emotion: str, beat_type: BeatType) -> None:
        self.emotion_config = load_emotions_config().get(emotion, load_emotions_config().get("neutral", {}))
        self.beat_type = beat_type
        self.speed = float(self.emotion_config.get("animation_speed", 1.0))
        self.camera_speed = float(self.emotion_config.get("camera_speed", 1.0))

    def compute(self, progress: float, frame_ratio: float) -> Dict[str, float | int]:
        eased = _ease_out_cubic(min(1.0, progress * self.speed))
        entrance = _ease_out_back(min(1.0, progress * 2.2 * self.speed))

        figure_offset_x = int((1.0 - entrance) * 180)
        figure_offset_y = int(math.sin(progress * math.pi * 4 * self.speed) * 6)

        bg_offset_x = int(-progress * 25 * self.camera_speed)
        bg_offset_y = int(math.sin(progress * math.pi * 2) * 4)

        camera_zoom = 1.0 + progress * 0.045 * self.camera_speed
        if self.beat_type == BeatType.HOOK:
            camera_zoom = 1.0 + progress * 0.07
        elif self.beat_type == BeatType.TURNING_POINT:
            camera_zoom = 1.02 + progress * 0.05

        text_drift_y = int((1.0 - eased) * 18)
        word_pop = max(0.0, math.sin(frame_ratio * math.pi)) if frame_ratio < 1.0 else 0.0

        camera_pan_x = 0
        camera_pan_y = 0
        if self.beat_type in {BeatType.ESCALATION, BeatType.CONFLICT}:
            camera_pan_x = int(progress * -20 * self.camera_speed)
        elif self.beat_type in {BeatType.RESOLUTION, BeatType.LESSON}:
            camera_pan_y = int(progress * -15 * self.camera_speed)

        return {
            "figure_offset_x": figure_offset_x,
            "figure_offset_y": figure_offset_y,
            "bg_offset_x": bg_offset_x,
            "bg_offset_y": bg_offset_y,
            "camera_zoom": camera_zoom,
            "camera_pan_x": camera_pan_x,
            "camera_pan_y": camera_pan_y,
            "text_drift_y": text_drift_y,
            "word_pop": word_pop,
            "bg_progress_multiplier": 0.8 + progress * 0.6,
            "figure_progress_multiplier": 0.7 + progress * 0.8,
        }

    def transition_style(self) -> str:
        if self.emotion_config.get("figure_emotion") == "sad":
            return "crossfade"
        if self.beat_type in {BeatType.HOOK, BeatType.CTA, BeatType.TURNING_POINT}:
            return "push"
        return "crossfade"


def _ease_out_cubic(t: float) -> float:
    return 1.0 - pow(1.0 - t, 3)


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


def apply_camera_transform(frame_image, zoom: float, pan_x: int, pan_y: int):
    """Apply subtle Ken Burns zoom + pan to a PIL Image."""
    from PIL import Image

    width, height = frame_image.size
    crop_w = int(width / zoom)
    crop_h = int(height / zoom)
    left = max(0, min(width - crop_w, (width - crop_w) // 2 + pan_x))
    top = max(0, min(height - crop_h, (height - crop_h) // 2 + pan_y))
    cropped = frame_image.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((width, height), Image.Resampling.LANCZOS)
