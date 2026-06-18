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
from src.core.models import BeatAudioSegment, NarrationBundle, NarrativeScript, ResearchBrief, ScenePlan, ShortsScript, WordTiming
from src.renderer.bgm_generator import generate_bgm
from src.renderer.frame_stream_encoder import FrameStreamEncoder
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
        research: ResearchBrief | None = None,
    ) -> Path | None:
        targets = load_topics_config().get("script_targets", {})
        min_duration = float(targets.get("shorts_min_duration_seconds", 30))
        max_duration = float(targets.get("shorts_max_duration_seconds", 60))

        narrative = NarrativeScript(topic=shorts_script.topic, beats=shorts_script.beats, format="short")
        beats = self.beat_extractor.extract(narrative)
        if research is None:
            research = self.research_collector.collect(shorts_script.topic)
        scene_plans = self.visual_planner.plan_scenes(beats, research)

        narration_bundle = self.voice_engine.synthesize_all_beats(beats, run_dir / "shorts_audio")
        beats = self._apply_audio_durations(beats, narration_bundle.segments)
        scene_plans = self.visual_planner.plan_scenes(beats, research)

        raw_path = run_dir / "shorts_raw.mp4"
        frame_encoder = FrameStreamEncoder(
            raw_path,
            self.shorts_width,
            self.shorts_height,
            self.fps,
        )
        scene_tail: List[np.ndarray] = []
        for index, scene_plan in enumerate(scene_plans):
            segment = narration_bundle.segments[index]
            frames = self._render_shorts_scene(scene_plan, segment, segment.word_timings)
            frames_to_write, scene_tail = self.animation_engine.plan_scene_stream_chunks(
                scene_tail,
                frames,
                blend_frames=8,
                transition="crossfade",
                is_first_scene=index == 0,
                is_last_scene=index == len(scene_plans) - 1,
            )
            frame_encoder.write_frames(frames_to_write)

        if frame_encoder.frame_count == 0:
            return None

        duration = narration_bundle.total_duration_seconds
        if duration < min_duration:
            pad_frames = int((min_duration - duration) * self.fps)
            if pad_frames > 0 and scene_tail:
                frame_encoder.write_frames([scene_tail[-1].copy() for _ in range(pad_frames)])
            duration = min_duration
        elif duration > max_duration:
            # Re-encode trimmed output below via aligned duration in mux path.
            duration = max_duration

        frame_encoder.close()
        if duration > max_duration:
            trimmed_path = run_dir / "shorts_trimmed.mp4"
            self.video_renderer.align_video_duration(raw_path, max_duration, trimmed_path)
            raw_path = trimmed_path
            duration = max_duration

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
            narration_bundle.all_word_timings,
            run_dir / "shorts_subtitles.ass",
            width=self.shorts_width,
            height=self.shorts_height,
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
