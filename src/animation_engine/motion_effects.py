"""Per-frame motion calculation — emotion-aware camera and element offsets."""

from __future__ import annotations

import math
from typing import Dict

from src.core.config_loader import load_emotions_config
from src.core.models import BeatType


class MotionCalculator:
    def __init__(self, emotion: str, beat_type: BeatType, motion_variant: str = "gentle_sway") -> None:
        self.emotion_config = load_emotions_config().get(emotion, load_emotions_config().get("neutral", {}))
        self.beat_type = beat_type
        self.motion_variant = motion_variant
        self.speed = float(self.emotion_config.get("animation_speed", 1.0))
        self.camera_speed = float(self.emotion_config.get("camera_speed", 1.0))

    def compute(self, progress: float, frame_ratio: float) -> Dict[str, float | int]:
        eased = _ease_out_cubic(min(1.0, progress * self.speed))
        entrance = _ease_out_back(min(1.0, progress * 2.2 * self.speed))

        figure_offset_x, figure_offset_y = self._figure_motion(progress, entrance)
        bg_offset_x, bg_offset_y = self._background_motion(progress)
        camera_zoom = self._camera_zoom(progress)
        text_drift_y = int((1.0 - eased) * 22)
        word_pop = max(0.0, math.sin(frame_ratio * math.pi)) if frame_ratio < 1.0 else 0.0

        camera_pan_x, camera_pan_y = self._camera_pan(progress)

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
            "bg_progress_multiplier": 0.65 + progress * 0.85,
            "figure_progress_multiplier": 0.55 + progress * 1.05,
        }

    def _figure_motion(self, progress: float, entrance: float) -> tuple[int, int]:
        variant = self.motion_variant
        if variant == "bounce_entrance":
            bounce = abs(math.sin(progress * math.pi * 2.5)) * (1.0 - progress) * 14
            return int((1.0 - entrance) * 200), int(bounce)
        if variant == "slide_left":
            return int((1.0 - entrance) * 240), int(math.sin(progress * math.pi * 3) * 8)
        if variant == "slide_right":
            return int((entrance - 1.0) * 180), int(math.cos(progress * math.pi * 2) * 10)
        if variant == "float_up":
            return int(math.sin(progress * math.pi) * 12), int(-progress * 28)
        if variant == "pulse_zoom":
            pulse = math.sin(progress * math.pi * 4) * 8
            return int(pulse), int(math.sin(progress * math.pi * 2) * 6)
        return int((1.0 - entrance) * 160), int(math.sin(progress * math.pi * 4 * self.speed) * 10)

    def _background_motion(self, progress: float) -> tuple[int, int]:
        drift_x = int(-progress * 32 * self.camera_speed)
        drift_y = int(math.sin(progress * math.pi * 2.5) * 8)
        if self.motion_variant == "slide_right":
            drift_x = int(progress * 28)
        elif self.motion_variant == "float_up":
            drift_y = int(-progress * 18)
        return drift_x, drift_y

    def _camera_zoom(self, progress: float) -> float:
        base = 1.0 + progress * 0.014 * self.camera_speed
        if self.beat_type == BeatType.HOOK:
            base = 1.0 + progress * 0.02
        elif self.beat_type == BeatType.TURNING_POINT:
            base = 1.0 + progress * 0.018
        if self.motion_variant == "pulse_zoom":
            base += 0.008 * math.sin(progress * math.pi * 3)
        return base

    def _camera_pan(self, progress: float) -> tuple[int, int]:
        pan_x = 0
        pan_y = 0
        if self.beat_type in {BeatType.ESCALATION, BeatType.CONFLICT}:
            pan_x = int(progress * -24 * self.camera_speed)
        elif self.beat_type in {BeatType.RESOLUTION, BeatType.LESSON}:
            pan_y = int(progress * -18 * self.camera_speed)
        if self.motion_variant == "slide_left":
            pan_x += int(progress * 16)
        elif self.motion_variant == "slide_right":
            pan_x += int(-progress * 16)
        return pan_x, pan_y

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


def apply_camera_transform(
    frame_image,
    zoom: float,
    pan_x: int,
    pan_y: int,
    anchor: str = "top_left",
):
    """Apply subtle Ken Burns zoom + pan. Anchor top-left so narration text stays visible."""
    from PIL import Image

    if zoom <= 1.001 and pan_x == 0 and pan_y == 0:
        return frame_image

    width, height = frame_image.size
    crop_w = max(1, int(width / max(zoom, 1.001)))
    crop_h = max(1, int(height / max(zoom, 1.001)))

    if anchor == "top_left":
        left = max(0, min(width - crop_w, pan_x))
        top = max(0, min(height - crop_h, pan_y))
    else:
        left = max(0, min(width - crop_w, (width - crop_w) // 2 + pan_x))
        top = max(0, min(height - crop_h, (height - crop_h) // 2 + pan_y))

    cropped = frame_image.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((width, height), Image.Resampling.LANCZOS)
