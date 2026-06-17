"""Shorts video renderer — standalone 30-60s vertical video."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.animation_engine.animation_engine import AnimationEngine
from src.core.config_loader import load_emotions_config, load_platform_config, load_topics_config
from src.core.models import BeatAudioSegment, NarrationBundle, NarrativeScript, ScenePlan, ShortsScript, WordTiming
from src.renderer.bgm_generator import generate_bgm
from src.renderer.video_renderer import VideoRenderer
from src.research.research_collector import ResearchCollector
from src.storyboard.story_beat_extractor import StoryBeatExtractor
from src.subtitle_engine.subtitle_engine import SubtitleEngine
from src.visual_planner.visual_planner import VisualPlanner
from src.voice_engine.voice_engine import VoiceEngine

log = logging.getLogger(__name__)


class ShortsRenderer:
    def __init__(self) -> None:
        platform = load_platform_config()
        video = platform.get("video", {})
        self.shorts_width = video.get("shorts_width", 1080)
        self.shorts_height = video.get("shorts_height", 1920)
        self.fps = video.get("fps", 24)
        self.animation_engine = AnimationEngine()
        self.video_renderer = VideoRenderer()
        self.voice_engine = VoiceEngine()
        self.beat_extractor = StoryBeatExtractor()
        self.visual_planner = VisualPlanner()
        self.research_collector = ResearchCollector()
        self.subtitle_engine = SubtitleEngine()

    def render_shorts(
        self,
        shorts_script: ShortsScript,
        output_path: Path,
        run_dir: Path,
    ) -> Path | None:
        targets = load_topics_config().get("script_targets", {})
        min_duration = float(targets.get("shorts_min_duration_seconds", 30))
        max_duration = float(targets.get("shorts_max_duration_seconds", 60))

        narrative = NarrativeScript(topic=shorts_script.topic, beats=shorts_script.beats, format="short")
        beats = self.beat_extractor.extract(narrative)
        research = self.research_collector.collect(shorts_script.topic)
        scene_plans = self.visual_planner.plan_scenes(beats, research)

        narration_bundle = self.voice_engine.synthesize_all_beats(beats, run_dir / "shorts_audio")
        beats = self._apply_audio_durations(beats, narration_bundle.segments)
        scene_plans = self.visual_planner.plan_scenes(beats, research)

        all_frames: List[np.ndarray] = []
        for index, scene_plan in enumerate(scene_plans):
            segment = narration_bundle.segments[index]
            frames = self._render_shorts_scene(scene_plan, segment, segment.word_timings)
            if all_frames:
                all_frames = self.animation_engine.apply_crossfade(
                    all_frames, frames, blend_frames=8, transition="crossfade"
                )
            else:
                all_frames.extend(frames)

        if not all_frames:
            return None

        duration = narration_bundle.total_duration_seconds
        if duration < min_duration:
            all_frames = self._pad_frames(all_frames, min_duration, duration)
            duration = min_duration
        elif duration > max_duration:
            max_frames = int(max_duration * self.fps)
            all_frames = all_frames[:max_frames]
            duration = max_duration

        raw_path = run_dir / "shorts_raw.mp4"
        self.video_renderer.encode_frames(all_frames, raw_path)

        emotions = load_emotions_config()
        dominant = beats[0].emotion if beats else "exciting"
        bgm_volume = float(emotions.get(dominant, {}).get("bgm_volume", 0.08))
        bgm_path = generate_bgm(
            run_dir / "shorts_bgm.mp3",
            duration_seconds=int(duration) + 5,
            dominant_emotion=dominant,
        )

        narration_path = Path(narration_bundle.narration_path)
        muxed_path = run_dir / "shorts_muxed.mp4"
        self.video_renderer.mux_audio(raw_path, narration_path, muxed_path, bgm_path, bgm_volume=bgm_volume)

        ass_path = self.subtitle_engine.write_ass(
            narration_bundle.all_word_timings, run_dir / "shorts_subtitles.ass"
        )
        self.subtitle_engine.burn_ass_into_video(
            muxed_path,
            ass_path,
            output_path,
            word_timings=narration_bundle.all_word_timings,
            fps=self.fps,
        )
        return output_path

    def _render_shorts_scene(
        self,
        scene_plan: ScenePlan,
        segment: BeatAudioSegment,
        word_timings: List[WordTiming],
    ) -> List[np.ndarray]:
        import ae_engine

        original_size = (ae_engine.W, ae_engine.H)
        ae_engine.W, ae_engine.H = self.shorts_width, self.shorts_height
        try:
            animation_plan = self.animation_engine.build_animation_plan(scene_plan)
            frames, _ = self.animation_engine.render_scene_frames(
                scene_plan,
                animation_plan,
                scene_index=0,
                total_scenes=1,
                word_timings=word_timings,
                duration_seconds=max(1.0, segment.duration_seconds + 0.15),
                is_shorts=True,
            )
            return frames
        finally:
            ae_engine.W, ae_engine.H = original_size

    def _apply_audio_durations(self, beats, segments: List[BeatAudioSegment]):
        updated = []
        for beat, segment in zip(beats, segments):
            updated.append(beat.model_copy(update={"duration_seconds": segment.duration_seconds + 0.15}))
        return updated

    def _pad_frames(self, frames: List[np.ndarray], target_duration: float, current_duration: float) -> List[np.ndarray]:
        if not frames:
            return frames
        extra_frames = int((target_duration - current_duration) * self.fps)
        return frames + [frames[-1].copy() for _ in range(max(0, extra_frames))]
