"""Unified video generation pipeline — Thulir storytelling channel."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.animation_engine.animation_engine import AnimationEngine
from src.asset_engine.asset_engine import AssetEngine
from src.core.config_loader import get_output_dir, load_emotions_config
from src.core.free_guard import validate_free_only_mode
from src.core.models import BeatAudioSegment, BeatType, NarrativeScript, TopicCandidate, VideoPackage, WordTiming
from src.research.research_collector import ResearchCollector
from src.renderer.bgm_generator import generate_bgm
from src.renderer.shorts_renderer import ShortsRenderer
from src.renderer.video_renderer import VideoRenderer
from src.scheduler.content_scheduler import ContentScheduler, DailySlot
from src.script.narrative_generator import NarrativeGenerator
from src.script.shorts_script_generator import ShortsScriptGenerator
from src.seo.metadata_generator import MetadataGenerator
from src.storyboard.story_beat_extractor import StoryBeatExtractor
from src.subtitle_engine.subtitle_engine import SubtitleEngine
from src.thumbnail.thumbnail_generator import ThumbnailGenerator
from src.topic.topic_scorer import TopicScorer
from src.uploader.youtube_publisher import YouTubePublisher
from src.visual_planner.visual_planner import VisualPlanner
from src.voice_engine.voice_engine import VoiceEngine

log = logging.getLogger(__name__)

BEAT_DURATION_PADDING_SECONDS = 0.3


class VideoPipeline:
    def __init__(self, voice_key: str = "default") -> None:
        validate_free_only_mode()
        self.topic_scorer = TopicScorer()
        self.research_collector = ResearchCollector()
        self.narrative_generator = NarrativeGenerator()
        self.shorts_script_generator = ShortsScriptGenerator()
        self.beat_extractor = StoryBeatExtractor()
        self.visual_planner = VisualPlanner()
        self.asset_engine = AssetEngine()
        self.animation_engine = AnimationEngine()
        self.voice_engine = VoiceEngine(voice_key=voice_key)
        self.subtitle_engine = SubtitleEngine()
        self.video_renderer = VideoRenderer()
        self.thumbnail_generator = ThumbnailGenerator()
        self.shorts_renderer = ShortsRenderer()
        self.metadata_generator = MetadataGenerator()
        self.youtube_publisher = YouTubePublisher()
        self.content_scheduler = ContentScheduler()

    def run(
        self,
        category: Optional[str] = None,
        topic_override: Optional[str] = None,
        skip_upload: bool = True,
        video_format: str = "long",
        daily_slot: Optional[str] = None,
        include_shorts: bool = True,
    ) -> VideoPackage:
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        run_dir = get_output_dir() / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        log.info("Run %s — format=%s starting pipeline", run_id, video_format)

        topic = self._resolve_topic(category, topic_override)
        research = self.research_collector.collect(topic)

        if video_format == "short":
            return self._run_shorts_only(run_id, run_dir, topic, research, skip_upload, daily_slot)

        package = self._run_long_video(
            run_id, run_dir, topic, research, skip_upload, daily_slot, include_shorts=include_shorts
        )

        if daily_slot:
            try:
                self.content_scheduler.mark_slot_complete(DailySlot(daily_slot), run_id)
            except ValueError:
                log.warning("Unknown daily slot: %s", daily_slot)

        return package

    def _run_long_video(
        self,
        run_id: str,
        run_dir: Path,
        topic: TopicCandidate,
        research,
        skip_upload: bool,
        daily_slot: Optional[str],
        include_shorts: bool = True,
    ) -> VideoPackage:
        script = self.narrative_generator.generate(topic, research)
        beats = self.beat_extractor.extract(script)

        narration_bundle = self.voice_engine.synthesize_all_beats(beats, run_dir / "audio")
        beats = self._apply_audio_durations(beats, narration_bundle.segments)
        scene_plans = self.visual_planner.plan_scenes(beats, research)

        all_frames: List = []
        hook_frames: List = []
        all_word_timings: List[WordTiming] = narration_bundle.all_word_timings

        for index, scene_plan in enumerate(scene_plans):
            segment = narration_bundle.segments[index]
            self.asset_engine.resolve_assets(scene_plan)
            animation_plan = self.animation_engine.build_animation_plan(scene_plan)
            scene_frames, _ = self.animation_engine.render_scene_frames(
                scene_plan,
                animation_plan,
                index,
                len(scene_plans),
                word_timings=segment.word_timings,
                duration_seconds=scene_plan.beat.duration_seconds,
            )
            if index == 0:
                hook_frames = scene_frames
            if all_frames:
                transition = animation_plan.transition
                blend = 16 if transition == "crossfade" else 14
                all_frames = self.animation_engine.apply_crossfade(
                    all_frames, scene_frames, blend_frames=blend, transition=transition
                )
            else:
                all_frames.extend(scene_frames)

        raw_video_path = run_dir / "raw_video.mp4"
        self.video_renderer.encode_frames(all_frames, raw_video_path)

        aligned_video_path = run_dir / "aligned_video.mp4"
        self.video_renderer.align_video_duration(
            raw_video_path,
            narration_bundle.total_duration_seconds,
            aligned_video_path,
        )

        dominant_emotion = self._dominant_emotion(beats)
        emotions = load_emotions_config()
        bgm_volume = float(emotions.get(dominant_emotion, {}).get("bgm_volume", 0.08))
        bgm_path = generate_bgm(
            run_dir / "bgm.mp3",
            duration_seconds=max(60, int(narration_bundle.total_duration_seconds) + 10),
            dominant_emotion=dominant_emotion,
        )

        muxed_path = run_dir / "muxed.mp4"
        narration_path = Path(narration_bundle.narration_path)
        self.video_renderer.mux_audio(
            aligned_video_path,
            narration_path,
            muxed_path,
            bgm_path,
            bgm_volume=bgm_volume,
        )

        srt_path = self.subtitle_engine.write_srt(all_word_timings, run_dir / "subtitles.srt")
        ass_path = self.subtitle_engine.write_ass(all_word_timings, run_dir / "subtitles.ass")
        final_video_path = run_dir / "video.mp4"
        self.subtitle_engine.burn_ass_into_video(
            muxed_path, ass_path, final_video_path,
            word_timings=all_word_timings, fps=self.animation_engine.fps,
        )

        chapters = self._build_macro_chapters(narration_bundle.segments, beats)
        metadata = self.metadata_generator.generate(topic, beats, chapters)

        hook_frame = self.thumbnail_generator.pick_hook_frame(hook_frames)
        thumbnail_path = self.thumbnail_generator.generate(
            topic, run_dir / "thumbnail.jpg",
            hook_frame=hook_frame,
            thumbnail_text=metadata.thumbnail_text,
            emotion_trigger=metadata.emotion_trigger,
        )

        slug = hashlib.md5(topic.title_ta.encode()).hexdigest()[:12]
        if not skip_upload:
            self.youtube_publisher.upload(final_video_path, thumbnail_path, metadata, topic, slug)

        self.topic_scorer.record_topic(topic)

        if daily_slot:
            try:
                self.content_scheduler.mark_slot_complete(DailySlot(daily_slot), run_id)
            except ValueError:
                pass

        package = VideoPackage(
            run_id=run_id,
            topic=topic,
            long_video_path=str(final_video_path),
            thumbnail_path=str(thumbnail_path),
            srt_path=str(srt_path),
            ass_path=str(ass_path),
            metadata=metadata,
            format="long",
        )

        if include_shorts:
            shorts_script = self.shorts_script_generator.generate(topic, research, long_script=script)
            shorts_path = run_dir / "shorts.mp4"
            shorts_result = self.shorts_renderer.render_shorts(
                shorts_script, shorts_path, run_dir, research=research
            )
            if shorts_result:
                package.shorts_video_path = str(shorts_result)
                if not skip_upload:
                    self.youtube_publisher.upload_shorts(
                        shorts_result,
                        metadata,
                        topic,
                        slug=hashlib.md5(f"{topic.title_ta}-shorts".encode()).hexdigest()[:12],
                    )

        (run_dir / "manifest.json").write_text(package.model_dump_json(indent=2), encoding="utf-8")
        log.info("Run %s — complete: %s (%.0fs)", run_id, final_video_path, narration_bundle.total_duration_seconds)
        return package

    def _run_shorts_only(
        self,
        run_id: str,
        run_dir: Path,
        topic: TopicCandidate,
        research,
        skip_upload: bool,
        daily_slot: Optional[str],
    ) -> VideoPackage:
        shorts_script = self.shorts_script_generator.generate(topic, research)
        shorts_path = run_dir / "shorts.mp4"
        result = self.shorts_renderer.render_shorts(shorts_script, shorts_path, run_dir, research=research)
        beats = shorts_script.beats
        chapters = [{"time": "00:00:00", "title": beat.beat_type.value} for beat in beats[:4]]
        metadata = self.metadata_generator.generate(topic, beats, chapters)
        metadata.title_ta = f"{metadata.title_ta[:50]} #Shorts"

        if result and not skip_upload:
            self.youtube_publisher.upload_shorts(
                result, metadata, topic,
                slug=hashlib.md5(f"{topic.title_ta}-shorts-{run_id}".encode()).hexdigest()[:12],
            )

        if daily_slot:
            try:
                self.content_scheduler.mark_slot_complete(DailySlot(daily_slot), run_id)
            except ValueError:
                pass

        self.topic_scorer.record_topic(topic)
        package = VideoPackage(
            run_id=run_id,
            topic=topic,
            long_video_path=str(result or ""),
            shorts_video_path=str(result) if result else None,
            metadata=metadata,
            format="short",
        )
        (run_dir / "manifest.json").write_text(package.model_dump_json(indent=2), encoding="utf-8")
        return package

    def _apply_audio_durations(self, beats, segments: List[BeatAudioSegment]):
        updated = []
        for beat, segment in zip(beats, segments):
            updated.append(
                beat.model_copy(
                    update={"duration_seconds": segment.duration_seconds + BEAT_DURATION_PADDING_SECONDS}
                )
            )
        return updated

    def _dominant_emotion(self, beats) -> str:
        counts: dict[str, int] = {}
        for beat in beats:
            counts[beat.emotion] = counts.get(beat.emotion, 0) + 1
        return max(counts, key=counts.get) if counts else "neutral"

    def _build_macro_chapters(self, segments: List[BeatAudioSegment], beats) -> List[dict]:
        chapters = []
        last_type: BeatType | None = None
        for segment, beat in zip(segments, beats):
            if beat.beat_type != last_type:
                chapters.append({
                    "time": _format_chapter_time(segment.start_ms),
                    "title": beat.beat_type.value,
                })
                last_type = beat.beat_type
        return chapters

    def _resolve_topic(self, category: Optional[str], topic_override: Optional[str]) -> TopicCandidate:
        if topic_override:
            return TopicCandidate(
                title_ta=topic_override,
                category=category or "storytelling",
                hook=topic_override[:60],
                hook_question=topic_override[:80],
                protagonist="நாயகன்",
                curiosity_score=8.0,
                emotion_score=8.0,
                story_score=8.0,
                lesson_score=7.5,
                source="manual",
            )
        return self.topic_scorer.discover_topic(category=category)


def _format_chapter_time(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
