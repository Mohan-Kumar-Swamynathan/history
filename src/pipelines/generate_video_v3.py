"""Clean video pipeline v3 — Pexels images + AE-style render.

Pipeline:
  1. Topic discovery
  2. Research (Wikipedia)
  3. Script — 6 beats, AE rhythm
  4. Voice synthesis (edge-tts)
  5. Images — prefetch all 6 from Pexels, convert to sketch
  6. Render — PIL only, fast, ~8-12 min on CI
  7. Mux audio
  8. Burn subtitles (ffmpeg filter)
  9. Thumbnail
 10. Upload
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from src.core.config_loader import get_output_dir, load_emotions_config
from src.core.free_guard import validate_free_only_mode
from src.core.models import TopicCandidate, VideoPackage, WordTiming
from src.research.research_collector import ResearchCollector
from src.renderer.bgm_generator import generate_bgm
from src.renderer.brand import INTRO_DURATION_S
from src.renderer.video_renderer import VideoRenderer
from src.scheduler.content_scheduler import ContentScheduler, DailySlot
from src.seo.metadata_generator import MetadataGenerator
from src.subtitle_engine.subtitle_engine import SubtitleEngine
from src.thumbnail.thumbnail_generator import ThumbnailGenerator
from src.topic.topic_scorer import TopicScorer
from src.uploader.youtube_publisher import YouTubePublisher
from src.voice_engine.voice_engine import VoiceEngine

# v3 components
from src.script.narrative_generator_v3 import NarrativeGeneratorV3
from src.renderer.intro_renderer import render_intro_frames, render_lower_third
from src.image_engine.image_engine import ImageEngine
from src.renderer.ae_engine_v3 import render_scene_frames, render_transition
from src.renderer.shorts_fast import generate_shorts

log = logging.getLogger(__name__)

RENDER_FPS = 8  # render at 8fps — 33% fewer PIL frames


def resample_intro_frames(intro_frames: List[np.ndarray], render_fps: int) -> List[np.ndarray]:
    """Evenly sample intro frames so intro duration matches INTRO_DURATION_S at render_fps."""
    target_count = max(1, int(INTRO_DURATION_S * render_fps))
    if not intro_frames:
        return intro_frames
    if len(intro_frames) == target_count:
        return intro_frames
    indices = np.linspace(0, len(intro_frames) - 1, target_count, dtype=int)
    return [intro_frames[index] for index in indices]


def intro_offset_ms() -> int:
    return int(INTRO_DURATION_S * 1000)


class VideoPipelineV3:
    def __init__(self, voice_key: str = "default") -> None:
        validate_free_only_mode()
        self.topic_scorer    = TopicScorer()
        self.research        = ResearchCollector()
        self.narrative       = NarrativeGeneratorV3()
        self.image_engine    = ImageEngine()
        self.voice_engine    = VoiceEngine(voice_key=voice_key)
        self.video_renderer  = VideoRenderer()
        self.subtitle_engine = SubtitleEngine()
        self.thumbnail_gen   = ThumbnailGenerator()
        self.metadata_gen    = MetadataGenerator()
        self.uploader        = YouTubePublisher()
        self.scheduler       = ContentScheduler()

    def run(
        self,
        category:       Optional[str] = None,
        topic_override: Optional[str] = None,
        skip_upload:    bool = True,
        video_format:   str = "long",
        daily_slot:     Optional[str] = None,
        include_shorts: bool = False,
    ) -> VideoPackage:
        run_id  = datetime.utcnow().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        run_dir = get_output_dir() / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        log.info("Run %s starting (v3 pipeline, format=%s)", run_id, video_format)

        topic = self._resolve_topic(category, topic_override)
        log.info("Topic: %s", topic.title_ta)

        research = self.research.collect(topic)

        if video_format == "short":
            return self._run_shorts_only(
                run_id, run_dir, topic, research, skip_upload, daily_slot
            )

        return self._run_long_video(
            run_id, run_dir, topic, research, skip_upload, daily_slot, include_shorts
        )

    def _resolve_topic(
        self,
        category: Optional[str],
        topic_override: Optional[str],
    ) -> TopicCandidate:
        if topic_override:
            return TopicCandidate(
                title_ta=topic_override,
                category=category or "storytelling",
                protagonist=topic_override.split()[0],
                source="manual",
            )
        return self.topic_scorer.discover_topic(category=category)

    def _run_shorts_only(
        self,
        run_id: str,
        run_dir: Path,
        topic: TopicCandidate,
        research,
        skip_upload: bool,
        daily_slot: Optional[str],
    ) -> VideoPackage:
        script = self.narrative.generate(topic, research)
        hook_beat = script.beats[0]

        audio_dir = run_dir / "audio"
        narration_bundle = self.voice_engine.synthesize_all_beats([hook_beat], audio_dir)
        hook_segment = narration_bundle.segments[0]

        beat_images = self.image_engine.prefetch_all([hook_beat], topic.title_ta)
        hook_image = beat_images.get(0)

        shorts_path = run_dir / "shorts.mp4"
        generate_shorts(
            hook_narration=hook_beat.narration_ta,
            hook_audio_path=Path(hook_segment.audio_path),
            hook_image=hook_image,
            protagonist=topic.protagonist,
            output_path=shorts_path,
            duration_s=min(hook_segment.duration_seconds + 2, 55.0),
        )

        chapters = [{"time": "00:00:00", "title": hook_beat.beat_type.value}]
        try:
            metadata = self.metadata_gen.generate(topic, [hook_beat], chapters)
        except Exception as exc:
            log.warning("Metadata failed (%s) — offline", exc)
            metadata = MetadataGenerator()._offline(topic, "", [hook_beat])

        if not skip_upload:
            shorts_slug = hashlib.md5(f"{topic.title_ta}-shorts-{run_id}".encode()).hexdigest()[:12]
            self.uploader.upload_shorts(shorts_path, metadata, topic, shorts_slug)

        self._finalize_run(topic, daily_slot, run_id)

        package = VideoPackage(
            run_id=run_id,
            topic=topic,
            long_video_path=str(shorts_path),
            shorts_video_path=str(shorts_path),
            metadata=metadata,
            format="short",
        )
        self._write_manifest(run_dir, package)
        log.info("Run %s complete — Shorts %s", run_id, shorts_path)
        return package

    def _run_long_video(
        self,
        run_id: str,
        run_dir: Path,
        topic: TopicCandidate,
        research,
        skip_upload: bool,
        daily_slot: Optional[str],
        include_shorts: bool,
    ) -> VideoPackage:
        script = self.narrative.generate(topic, research)
        beats  = script.beats
        log.info("Script: %d beats", len(beats))

        audio_dir = run_dir / "audio"
        narration_bundle = self.voice_engine.synthesize_all_beats(beats, audio_dir)
        log.info("Audio: %.0fs", narration_bundle.total_duration_seconds)

        for index, (beat, segment) in enumerate(zip(beats, narration_bundle.segments)):
            beats[index] = beat.model_copy(
                update={"duration_seconds": segment.duration_seconds + 0.3}
            )

        log.info("Fetching scene images from Pexels...")
        beat_images = self.image_engine.prefetch_all(beats, topic.title_ta)
        log.info("Images ready: %d", len(beat_images))

        log.info("Rendering frames (%dfps → 24fps output, PIL only)...", RENDER_FPS)
        all_frame_batches: List[List[np.ndarray]] = []
        hook_frame = None

        for index, beat in enumerate(beats):
            segment = narration_bundle.segments[index]
            image_panel = beat_images.get(index, beat_images.get(0))

            frames = render_scene_frames(
                beat_narration=beat.narration_ta,
                image_panel=image_panel,
                duration_s=beat.duration_seconds,
                word_timings=segment.word_timings,
                fps=RENDER_FPS,
                scene_idx=index,
            )

            if hook_frame is None and frames:
                hook_frame = frames[int(len(frames) * 0.7)]

            all_frame_batches.append(frames)
            log.info("Scene %d/%d — %d frames", index + 1, len(beats), len(frames))

        log.info("Assembling video...")
        log.info("Rendering intro card...")
        intro_frames_raw = render_intro_frames(
            channel_name_ta="துளிர்",
            tagline_ta="உண்மையான கதைகள். உண்மையான பாடங்கள்.",
            handle="@thulir",
            topic_ta=topic.title_ta[:35],
        )
        intro_frames = resample_intro_frames(intro_frames_raw, RENDER_FPS)
        log.info("Intro: %d frames (resampled from %d)", len(intro_frames), len(intro_frames_raw))

        transition_frames = 4
        raw_video_path = run_dir / "raw_video.mp4"

        enc_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", "1920x1080", "-pix_fmt", "rgb24",
            "-r", str(RENDER_FPS),
            "-i", "pipe:0",
            "-vf", "fps=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(raw_video_path),
        ]
        enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)

        prev_hash = None
        prev_bytes = None

        def write_frame(frame: np.ndarray) -> None:
            nonlocal prev_hash, prev_bytes
            frame_hash = hashlib.md5(frame[::16, ::16].tobytes()).digest()
            if frame_hash == prev_hash and prev_bytes:
                enc_proc.stdin.write(prev_bytes)
            else:
                raw = frame.tobytes()
                enc_proc.stdin.write(raw)
                prev_hash, prev_bytes = frame_hash, raw

        for frame in intro_frames:
            write_frame(frame)

        offset_ms = intro_offset_ms()
        for index, timing in enumerate(narration_bundle.all_word_timings):
            narration_bundle.all_word_timings[index] = timing.model_copy(
                update={
                    "start_ms": timing.start_ms + offset_ms,
                    "end_ms": timing.end_ms + offset_ms,
                }
            )

        lower_third_frame_limit = int(3 * RENDER_FPS)

        for batch_index, batch in enumerate(all_frame_batches):
            beat = beats[batch_index]
            situation_text = topic.situation[:30] if topic.situation else ""
            lt_subtitle = beat.on_screen_text or situation_text
            show_lower_third = batch_index == 0

            def write_batch_frames(frames, start_frame_index=0):
                for frame_index, frame in enumerate(frames):
                    if show_lower_third and (start_frame_index + frame_index) < lower_third_frame_limit:
                        try:
                            pil_frame = Image.fromarray(frame)
                            pil_frame = render_lower_third(
                                pil_frame,
                                protagonist=beat.protagonist,
                                subtitle=lt_subtitle,
                                beat_frame=start_frame_index + frame_index,
                                total_beat_frames=len(batch),
                                fps=RENDER_FPS,
                            )
                            frame = np.array(pil_frame)
                        except Exception as exc:
                            log.warning("Lower-third render failed: %s", exc)
                    write_frame(frame)

            if batch_index > 0:
                previous_batch = all_frame_batches[batch_index - 1]
                tail = (
                    previous_batch[-transition_frames:]
                    if len(previous_batch) >= transition_frames
                    else previous_batch
                )
                head = batch[:transition_frames]
                for transition_index in range(min(len(tail), len(head), transition_frames)):
                    transition_progress = (transition_index + 1) / transition_frames
                    blended = render_transition(
                        tail[transition_index], head[transition_index],
                        transition_progress, style="flipbook",
                    )
                    write_frame(blended)
                write_batch_frames(batch[transition_frames:], start_frame_index=transition_frames)
            else:
                write_batch_frames(batch)

        enc_proc.stdin.close()
        encode_return_code = enc_proc.wait()
        if encode_return_code != 0:
            raise RuntimeError(f"Raw video encoding failed (exit code {encode_return_code})")
        log.info("Raw video encoded")

        total_video_seconds = INTRO_DURATION_S + narration_bundle.total_duration_seconds
        log.info(
            "Video duration: intro=%.1fs + audio=%.1fs = total=%.1fs",
            INTRO_DURATION_S,
            narration_bundle.total_duration_seconds,
            total_video_seconds,
        )
        aligned_path = run_dir / "aligned.mp4"
        self.video_renderer.align_video_duration(
            raw_video_path,
            total_video_seconds,
            aligned_path,
        )

        dominant_emotion = max(
            set(beat.emotion for beat in beats),
            key=lambda emotion: sum(1 for beat in beats if beat.emotion == emotion),
        )
        emotions_cfg = load_emotions_config()
        bgm_volume = float(emotions_cfg.get(dominant_emotion, {}).get("bgm_volume", 0.06))
        bgm_path = generate_bgm(
            run_dir / "bgm.mp3",
            duration_seconds=int(narration_bundle.total_duration_seconds) + 10,
            dominant_emotion=dominant_emotion,
        )
        muxed_path = run_dir / "muxed.mp4"
        self.video_renderer.mux_audio(
            aligned_path,
            Path(narration_bundle.narration_path),
            muxed_path,
            bgm_path,
            bgm_volume=bgm_volume,
            intro_delay_seconds=INTRO_DURATION_S,
            strict=True,
        )

        log.info("Step 10: subtitles...")
        final_path = run_dir / "video.mp4"
        srt_path = run_dir / "subtitles.srt"
        ass_path = run_dir / "subtitles.ass"
        try:
            srt_path = self.subtitle_engine.write_srt(
                narration_bundle.all_word_timings, srt_path)
            ass_path = self.subtitle_engine.write_ass(
                narration_bundle.all_word_timings, ass_path)
            self.subtitle_engine.burn_ass_into_video(
                muxed_path, ass_path, final_path,
                word_timings=narration_bundle.all_word_timings, fps=RENDER_FPS)
            log.info("Subtitles burned")
        except Exception as exc:
            log.warning("Subtitle step failed (%s) — copying muxed as final", exc)
            shutil.copy(muxed_path, final_path)
            srt_path.write_text("", encoding="utf-8")

        log.info("Step 11: metadata + thumbnail...")
        chapters = [{"time": "00:00:00", "title": beat.beat_type.value} for beat in beats]
        try:
            metadata = self.metadata_gen.generate(topic, beats, chapters)
            log.info("Metadata done: %s", metadata.title_ta[:40])
        except Exception as exc:
            log.warning("Metadata failed (%s) — offline", exc)
            metadata = MetadataGenerator()._offline(topic, "", beats)

        try:
            thumb_path = self.thumbnail_gen.generate(
                topic, run_dir / "thumbnail.jpg",
                hook_frame=hook_frame,
                thumbnail_text=metadata.thumbnail_text,
                emotion_trigger=metadata.emotion_trigger)
            log.info("Thumbnail done")
        except Exception as exc:
            log.warning("Thumbnail failed (%s) — blank", exc)
            thumb_path = run_dir / "thumbnail.jpg"
            Image.new("RGB", (1280, 720), (29, 48, 16)).save(thumb_path)

        log.info("Step 12: upload (skip=%s)...", skip_upload)
        slug = hashlib.md5(topic.title_ta.encode()).hexdigest()[:12]
        if not skip_upload:
            try:
                result = self.uploader.upload(
                    final_path, thumb_path, metadata, topic, slug)
                yt_url = result.get("youtube_url","") if isinstance(result,dict) else ""
                log.info("Uploaded: %s", yt_url)
                try: package = package.model_copy(update={"youtube_url": yt_url})
                except: pass
            except Exception as exc:
                log.error("Upload FAILED: %s", exc)
                raise

        package = VideoPackage(
            run_id=run_id,
            topic=topic,
            long_video_path=str(final_path),
            thumbnail_path=str(thumb_path),
            srt_path=str(srt_path),
            ass_path=str(ass_path),
            metadata=metadata,
            format="long",
        )

        if include_shorts:
            package = self._generate_and_upload_shorts(
                package, beats, narration_bundle, beat_images, topic, skip_upload, run_dir, run_id
            )

        self._finalize_run(topic, daily_slot, run_id)
        self._write_manifest(run_dir, package)
        log.info("Run %s complete — %s", run_id, final_path)
        return package

    def _generate_and_upload_shorts(
        self,
        package: VideoPackage,
        beats,
        narration_bundle,
        beat_images,
        topic: TopicCandidate,
        skip_upload: bool,
        run_dir: Path,
        run_id: str,
    ) -> VideoPackage:
        log.info("Step 13: generating Shorts...")
        try:
            hook_beat = beats[0]
            hook_segment = narration_bundle.segments[0]
            hook_image = beat_images.get(0)
            shorts_path = run_dir / "shorts.mp4"
            generate_shorts(
                hook_narration=hook_beat.narration_ta,
                hook_audio_path=Path(hook_segment.audio_path),
                hook_image=hook_image,
                protagonist=topic.protagonist,
                output_path=shorts_path,
                duration_s=min(hook_segment.duration_seconds + 2, 55.0),
            )
            package = package.model_copy(update={"shorts_video_path": str(shorts_path)})

            if not skip_upload:
                shorts_slug = hashlib.md5(
                    f"{topic.title_ta}-shorts-{run_id}".encode()
                ).hexdigest()[:12]
                assert package.metadata is not None
                # Add full video link to Shorts description for view funneling
                shorts_meta = package.metadata
                long_url = package.youtube_url if hasattr(package, "youtube_url") else ""
                if long_url:
                    from copy import deepcopy
                    try:
                        shorts_meta = deepcopy(package.metadata)
                        old_desc = shorts_meta.description_ta or ""
                        shorts_meta.description_ta = (
                            f"🎬 முழு வீடியோ இங்கே: {long_url}\n\n{old_desc}"
                        )
                    except Exception:
                        pass
                self.uploader.upload_shorts(
                    shorts_path, shorts_meta, topic, shorts_slug
                )
                log.info("✅ Shorts uploaded — linked to full video")
        except Exception as exc:
            if skip_upload:
                log.warning("Shorts generation failed: %s", exc)
            else:
                log.error("Shorts generation/upload failed: %s", exc)
                raise
        return package

    def _finalize_run(
        self,
        topic: TopicCandidate,
        daily_slot: Optional[str],
        run_id: str,
    ) -> None:
        self.topic_scorer.record_topic(topic)
        if daily_slot:
            try:
                self.scheduler.mark_slot_complete(DailySlot(daily_slot), run_id)
            except ValueError as exc:
                log.warning("Unknown daily slot: %s", exc)

    def _write_manifest(self, run_dir: Path, package: VideoPackage) -> None:
        manifest_path = run_dir / "manifest.json"
        try:
            manifest_path.write_text(package.model_dump_json(indent=2))
        except Exception as exc:
            log.warning("Manifest write failed (%s) — skipping", exc)
            manifest_path.write_text(json.dumps({
                "run_id": package.run_id,
                "topic": package.topic.title_ta,
                "video": package.long_video_path,
                "format": package.format,
            }, ensure_ascii=False))
