"""Documentary-style scene frames — stats, maps, timelines."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.models import ScenePlan, SceneType, WordTiming


def render_documentary_scene(
    scene_plan: ScenePlan,
    total_frames: int,
    fps: int = 24,
) -> List[np.ndarray]:
    from visual_renderer import render_map_frames, render_stat_frames, render_timeline_frames

    scene_type = scene_plan.scene_type
    text = scene_plan.beat.narration_ta
    frames: list = []

    if scene_type == SceneType.STATISTIC:
        numbers = re.findall(r"\d+", text)
        number = numbers[0] if numbers else "100"
        frames = render_stat_frames(number, "", total_frames, bg_color=(255, 255, 255))
    elif scene_type == SceneType.TIMELINE:
        dates = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", text)
        entity_dates = scene_plan.beat.entities.get("dates") or []
        dates = dates or entity_dates or ["2020", "2024"]
        frames = render_timeline_frames(str(dates[0]), [str(d) for d in dates], total_frames)
    elif scene_type == SceneType.MAP:
        location = "India"
        for keyword in ("சென்னை", "இந்தியா", "தமிழ்நாடு", "Chennai", "India"):
            if keyword in text:
                location = keyword
                break
        frames = render_map_frames(location, total_frames)
    else:
        frames = render_stat_frames("1", "", total_frames, bg_color=(255, 255, 255))

    rgb_frames = []
    for frame in frames:
        if frame.shape[2] == 3:
            rgb_frames.append(frame[:, :, ::-1].copy())
        else:
            rgb_frames.append(frame)
    return rgb_frames
