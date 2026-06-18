"""Almost Everything style scene renderer with enhanced motion."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ae_engine import crossfade, pick_background, render_frame  # noqa: E402
from src.animation_engine.motion_effects import (  # noqa: E402
    MotionCalculator,
    apply_camera_transform,
)
from src.asset_engine.background_tints import tint_key_from_background, wrap_background_with_color
from src.asset_engine.decoration_engine import composite_scene_decorations
from src.core.config_loader import load_platform_config  # noqa: E402
from src.animation_engine.documentary_scenes import render_documentary_scene
from src.core.models import AnimationPlan, ScenePlan, SceneType, WordTiming  # noqa: E402


SHORTS_VISUAL_CHANGE_SECONDS = 1.5
LONG_VISUAL_CHANGE_SECONDS = 2.5


class AnimationEngine:
    def __init__(self) -> None:
        platform = load_platform_config()
        video = platform.get("video", {})
        self.width = video.get("width", 1920)
        self.height = video.get("height", 1080)
        self.fps = video.get("fps", 24)

    def build_animation_plan(self, scene_plan: ScenePlan) -> AnimationPlan:
        emotion_map = {
            "sad": "sad",
            "hope": "happy",
            "exciting": "celebrating",
            "inspirational": "celebrating",
            "thinking": "thinking",
            "neutral": "neutral",
        }
        motion = MotionCalculator(scene_plan.emotion, scene_plan.beat.beat_type)
        return AnimationPlan(
            scene_plan=scene_plan,
            camera_motion="zoom_in",
            element_animations=["draw", "highlight", "walk_in", "word_pop", "parallax"],
            transition=motion.transition_style(),
            figure_emotion=emotion_map.get(scene_plan.emotion, "neutral"),
        )

    def render_scene_frames(
        self,
        scene_plan: ScenePlan,
        animation_plan: AnimationPlan,
        scene_index: int,
        total_scenes: int,
        word_timings: List[WordTiming] | None = None,
        duration_seconds: float | None = None,
        is_shorts: bool = False,
    ) -> Tuple[List[np.ndarray], List[WordTiming]]:
        words = re.findall(r"\S+", scene_plan.beat.narration_ta)
        duration = duration_seconds or scene_plan.beat.duration_seconds
        total_frames = max(int(duration * self.fps), self.fps * 2)
        beat_timings = word_timings or []
        use_documentary = (
            not is_shorts
            and scene_plan.scene_type in {
                SceneType.STATISTIC,
                SceneType.TIMELINE,
                SceneType.MAP,
            }
        )

        if use_documentary:
            doc_frames = render_documentary_scene(scene_plan, total_frames, self.fps)
            return doc_frames, beat_timings

        motion = MotionCalculator(scene_plan.emotion, scene_plan.beat.beat_type)
        frames: List[np.ndarray] = []
        previous_visible = 0
        visual_interval = SHORTS_VISUAL_CHANGE_SECONDS if is_shorts else LONG_VISUAL_CHANGE_SECONDS
        segment_frames = max(int(self.fps * visual_interval), self.fps)

        for frame_index in range(total_frames):
            current_ms = int((frame_index / self.fps) * 1000)
            progress = frame_index / max(total_frames - 1, 1)
            visible_words = self._visible_word_count(beat_timings, current_ms, len(words))
            visual_segment = frame_index // segment_frames
            segment_progress = (frame_index % segment_frames) / max(segment_frames - 1, 1)
            motion_params = motion.compute(segment_progress, frame_ratio=segment_progress)

            word_just_appeared = visible_words > previous_visible
            word_pop = 1.0 if word_just_appeared else max(0.0, 1.0 - (frame_index % 8) / 8.0)
            previous_visible = visible_words

            bg_seed = scene_index * 100 + visual_segment + hash(scene_plan.background_key) % 17
            bg_draw_fn = pick_background(scene_plan.beat.narration_ta, bg_seed)
            if bg_draw_fn is not None:
                tint_key = tint_key_from_background(scene_plan.background_key)
                bg_draw_fn = wrap_background_with_color(bg_draw_fn, tint_key)

            figure_base = 0.18 if is_shorts else 0.08
            bg_base = 0.22 if is_shorts else 0.10
            figure_progress = min(
                1.0,
                figure_base + segment_progress * float(motion_params["figure_progress_multiplier"]),
            )
            bg_progress = min(
                1.0,
                bg_base + segment_progress * float(motion_params["bg_progress_multiplier"]),
            )

            pil_frame = render_frame(
                all_words=words,
                visible=visible_words,
                figure_progress=figure_progress,
                bg_progress=bg_progress,
                emotion=animation_plan.figure_emotion,
                protagonist=scene_plan.protagonist,
                bg_draw_fn=bg_draw_fn,
                scene_num=scene_index,
                total_scenes=total_scenes,
                is_shorts=is_shorts,
                on_screen_text=scene_plan.beat.on_screen_text or "",
                figure_offset_x=int(motion_params["figure_offset_x"] * (0.25 if is_shorts else 1.0)),
                figure_offset_y=int(motion_params["figure_offset_y"]),
                bg_offset_x=int(motion_params["bg_offset_x"]),
                bg_offset_y=int(motion_params["bg_offset_y"]),
                text_drift_y=int(motion_params["text_drift_y"]),
                word_pop=word_pop if word_just_appeared or visible_words == len(words) else word_pop * 0.3,
            )

            camera_zoom = float(motion_params["camera_zoom"])
            if is_shorts:
                camera_zoom = min(camera_zoom, 1.02)
            pil_frame = apply_camera_transform(
                pil_frame,
                zoom=camera_zoom,
                pan_x=int(motion_params["camera_pan_x"]),
                pan_y=int(motion_params["camera_pan_y"]),
                anchor="top_left",
            )
            pil_frame = composite_scene_decorations(
                pil_frame,
                scene_text=scene_plan.beat.narration_ta,
                emotion=scene_plan.emotion,
                progress=progress,
                frame_index=frame_index,
                scene_plan=scene_plan,
            )
            frames.append(np.array(pil_frame.convert("RGB")))

        return frames, beat_timings

    def _visible_word_count(
        self,
        timings: List[WordTiming],
        current_ms: int,
        total_words: int,
    ) -> int:
        if not timings:
            return max(1, min(total_words, int(current_ms / 400) + 1))
        visible = sum(1 for timing in timings if timing.start_ms <= current_ms)
        if visible == 0 and total_words > 0:
            return 1
        return min(visible, total_words)

    def apply_crossfade(
        self,
        frames_a: List[np.ndarray],
        frames_b: List[np.ndarray],
        blend_frames: int = 12,
        transition: str = "crossfade",
    ) -> List[np.ndarray]:
        if not frames_a:
            return list(frames_b)
        if not frames_b:
            return list(frames_a)

        if transition == "push":
            return self._apply_push_transition(frames_a, frames_b, blend_frames)

        blend_count = min(blend_frames, len(frames_a), len(frames_b))
        if blend_count < 2:
            return frames_a + frames_b
        blended: List[np.ndarray] = []
        target_height, target_width = frames_a[0].shape[0], frames_a[0].shape[1]
        for index in range(blend_count):
            blend_ratio = index / max(blend_count - 1, 1)
            pil_a = Image.fromarray(frames_a[-(blend_count - index)])
            pil_b = Image.fromarray(self._resize_frame_array(frames_b[index], target_width, target_height))
            merged = crossfade(pil_a, pil_b, blend_ratio)
            blended.append(np.array(merged))
        return frames_a[:-blend_count] + blended + frames_b[blend_count:]

    def _resize_frame_array(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        if frame.shape[0] == height and frame.shape[1] == width:
            return frame
        pil_frame = Image.fromarray(frame)
        return np.array(pil_frame.resize((width, height), Image.LANCZOS))

    def _apply_push_transition(
        self,
        frames_a: List[np.ndarray],
        frames_b: List[np.ndarray],
        blend_frames: int,
    ) -> List[np.ndarray]:
        width = frames_a[0].shape[1]
        blend_count = min(blend_frames, len(frames_a), len(frames_b))
        if blend_count < 2:
            return frames_a + frames_b

        pushed: List[np.ndarray] = []
        for index in range(blend_count):
            t = index / max(blend_count - 1, 1)
            offset = int(width * t)
            canvas = Image.new("RGB", (width, frames_a[0].shape[0]), (255, 255, 255))
            frame_a = Image.fromarray(frames_a[-(blend_count - index)])
            frame_b = Image.fromarray(frames_b[index])
            canvas.paste(frame_a, (-offset, 0))
            canvas.paste(frame_b, (width - offset, 0))
            pushed.append(np.array(canvas))
        return frames_a[:-blend_count] + pushed + frames_b[blend_count:]
