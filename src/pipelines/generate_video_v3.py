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
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from src.core.config_loader import get_output_dir, load_emotions_config
from src.core.free_guard import validate_free_only_mode
from src.core.models import VideoPackage, WordTiming
from src.research.research_collector import ResearchCollector
from src.renderer.bgm_generator import generate_bgm
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
from src.renderer.intro_renderer import (
    render_intro_frames,
    render_lower_third,
    apply_green_tint,
)
from src.image_engine.image_engine import ImageEngine
from src.renderer.ae_engine_v3 import render_scene_frames, render_transition
from src.renderer.shorts_fast import generate_shorts

log = logging.getLogger(__name__)


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
        log.info("Run %s starting (v3 pipeline)", run_id)

        # ── 1. Topic ───────────────────────────────────────────────────
        if topic_override:
            from src.core.models import TopicCandidate
            topic = TopicCandidate(
                title_ta=topic_override,
                category=category or "storytelling",
                protagonist=topic_override.split()[0],
                source="manual",
            )
        else:
            topic = self.topic_scorer.discover_topic(category=category)
        log.info("Topic: %s", topic.title_ta)

        # ── 2. Research ────────────────────────────────────────────────
        research = self.research.collect(topic)

        # ── 3. Script — 6 beats ────────────────────────────────────────
        script = self.narrative.generate(topic, research)
        beats  = script.beats
        log.info("Script: %d beats", len(beats))

        # ── 4. Voice synthesis ─────────────────────────────────────────
        audio_dir = run_dir / "audio"
        narration_bundle = self.voice_engine.synthesize_all_beats(beats, audio_dir)
        log.info("Audio: %.0fs", narration_bundle.total_duration_seconds)

        # Apply audio durations to beats
        for i, (beat, seg) in enumerate(zip(beats, narration_bundle.segments)):
            beats[i] = beat.model_copy(update={"duration_seconds": seg.duration_seconds + 0.3})

        # ── 5. Prefetch all images ────────────────────────────────────
        log.info("Fetching scene images from Pexels...")
        beat_images = self.image_engine.prefetch_all(beats, topic.title_ta)
        log.info("Images ready: %d", len(beat_images))

        # ── 6. Render all scenes ──────────────────────────────────────
        log.info("Rendering frames (12fps, PIL only)...")
        all_frame_batches: List[List[np.ndarray]] = []
        hook_frame = None

        for i, beat in enumerate(beats):
            seg        = narration_bundle.segments[i]
            image_panel = beat_images.get(i, beat_images.get(0))

            frames = render_scene_frames(
                beat_narration = beat.narration_ta,
                image_panel    = image_panel,
                duration_s     = beat.duration_seconds,
                word_timings   = seg.word_timings,
                fps            = 12,
                scene_idx      = i,
            )

            if hook_frame is None and frames:
                hook_frame = frames[int(len(frames) * 0.7)]

            all_frame_batches.append(frames)
            log.info("Scene %d/%d — %d frames", i + 1, len(beats), len(frames))

        # ── 7. Assemble with transitions ──────────────────────────────
        log.info("Assembling video...")

        # Generate branded intro (3.5s)
        log.info("Rendering intro card...")
        intro_frames = render_intro_frames(
            channel_name_ta = "துளிர்",
            tagline_ta      = "உண்மையான கதைகள். உண்மையான பாடங்கள்.",
            handle          = "@thulir",
            topic_ta        = topic.title_ta[:35],
        )
        log.info("Intro: %d frames", len(intro_frames))

        TRANSITION_FRAMES = 4   # ~0.3s at 12fps — quick wipe like AE
        raw_video_path = run_dir / "raw_video.mp4"

        import subprocess
        enc_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", "1920x1080", "-pix_fmt", "rgb24", "-r", "12",
            "-i", "pipe:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(raw_video_path),
        ]
        enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)

        import hashlib as _hlib
        prev_hash = None
        prev_bytes = None

        def write_frame(f: np.ndarray) -> None:
            nonlocal prev_hash, prev_bytes
            h = _hlib.md5(f[::16, ::16].tobytes()).digest()
            if h == prev_hash and prev_bytes:
                enc_proc.stdin.write(prev_bytes)
            else:
                raw = f.tobytes()
                enc_proc.stdin.write(raw)
                prev_hash, prev_bytes = h, raw

        # Write intro frames first (3.5s @ 12fps = 42 frames)
        # These have NO word timings — pure branding
        for f in intro_frames:
            write_frame(f)
        
        # Offset all word timings by intro duration so subtitles sync correctly
        INTRO_OFFSET_MS = int(len(intro_frames) / 12 * 1000)  # ~3500ms
        for i, timing in enumerate(narration_bundle.all_word_timings):
            narration_bundle.all_word_timings[i] = timing.model_copy(
                update={
                    "start_ms": timing.start_ms + INTRO_OFFSET_MS,
                    "end_ms":   timing.end_ms   + INTRO_OFFSET_MS,
                }
            )

        for batch_i, batch in enumerate(all_frame_batches):
            is_last = batch_i == len(all_frame_batches) - 1
            beat = beats[batch_i]
            # Build lower-third subtitle: protagonist + role
            lt_subtitle = beat.on_screen_text or beat.situation[:30] if hasattr(beat, 'situation') else ""

            # Lower-third only on hook + first beat (not all 2100 frames)
            _show_lower_third = (batch_i == 0)

            def _write_batch_frames(frames, start_fi=0):
                """Write frames, lower-third only on hook beat."""
                for fi, f in enumerate(frames):
                    if _show_lower_third and (start_fi + fi) < 36:  # first 3s
                        try:
                            pil_f = Image.fromarray(f)
                            pil_f = render_lower_third(
                                pil_f,
                                protagonist       = beat.protagonist,
                                subtitle          = lt_subtitle,
                                beat_frame        = start_fi + fi,
                                total_beat_frames = len(batch),
                                fps               = 12,
                            )
                            f = np.array(pil_f)
                        except Exception:
                            pass
                    write_frame(f)

            if batch_i > 0:
                prev_batch = all_frame_batches[batch_i - 1]
                tail = prev_batch[-TRANSITION_FRAMES:] if len(prev_batch) >= TRANSITION_FRAMES else prev_batch
                head = batch[:TRANSITION_FRAMES]
                for ti in range(min(len(tail), len(head), TRANSITION_FRAMES)):
                    t_progress = (ti + 1) / TRANSITION_FRAMES
                    blended = render_transition(tail[ti], head[ti], t_progress, style="flipbook")
                    write_frame(blended)
                # Write rest of batch WITH lower-third
                _write_batch_frames(batch[TRANSITION_FRAMES:], start_fi=TRANSITION_FRAMES)
            else:
                _write_batch_frames(batch)

        enc_proc.stdin.close()
        enc_proc.wait()
        log.info("Raw video encoded")

        # ── 8. Align duration to audio ────────────────────────────────
        aligned_path = run_dir / "aligned.mp4"
        self.video_renderer.align_video_duration(
            raw_video_path,
            narration_bundle.total_duration_seconds,
            aligned_path,
        )

        # ── 9. BGM + mux audio ────────────────────────────────────────
        dominant_emotion = max(
            set(b.emotion for b in beats),
            key=lambda e: sum(1 for b in beats if b.emotion == e)
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
        )

        # ── 10. Subtitles ─────────────────────────────────────────────
        log.info("Step 10: subtitles...")
        final_path = run_dir / "video.mp4"
        srt_path   = run_dir / "subtitles.srt"
        ass_path   = run_dir / "subtitles.ass"
        try:
            srt_path = self.subtitle_engine.write_srt(
                narration_bundle.all_word_timings, srt_path)
            ass_path = self.subtitle_engine.write_ass(
                narration_bundle.all_word_timings, ass_path)
            self.subtitle_engine.burn_ass_into_video(
                muxed_path, ass_path, final_path,
                word_timings=narration_bundle.all_word_timings, fps=12)
            log.info("✅ Subtitles burned")
        except Exception as e:
            log.warning("Subtitle step failed (%s) — copying muxed as final", e)
            import shutil; shutil.copy(muxed_path, final_path)
            srt_path.write_text("", encoding="utf-8")

        # ── 11. Metadata + thumbnail ──────────────────────────────────
        log.info("Step 11: metadata + thumbnail...")
        chapters = [{"time": "00:00:00", "title": b.beat_type.value} for b in beats]
        try:
            metadata = self.metadata_gen.generate(topic, beats, chapters)
            log.info("✅ Metadata done: %s", metadata.title_ta[:40])
        except Exception as e:
            log.warning("Metadata failed (%s) — offline", e)
            from src.seo.metadata_generator import MetadataGenerator as MG
            metadata = MG()._offline(topic, "", beats)

        try:
            thumb_path = self.thumbnail_gen.generate(
                topic, run_dir / "thumbnail.jpg",
                hook_frame=hook_frame,
                thumbnail_text=metadata.thumbnail_text,
                emotion_trigger=metadata.emotion_trigger)
            log.info("✅ Thumbnail done")
        except Exception as e:
            log.warning("Thumbnail failed (%s) — blank", e)
            from PIL import Image as _PILImg
            thumb_path = run_dir / "thumbnail.jpg"
            _PILImg.new("RGB", (1280, 720), (29, 48, 16)).save(thumb_path)

        # ── 12. Upload ────────────────────────────────────────────────
        log.info("Step 12: upload (skip=%s)...", skip_upload)
        slug = hashlib.md5(topic.title_ta.encode()).hexdigest()[:12]
        if not skip_upload:
            try:
                result = self.uploader.upload(
                    final_path, thumb_path, metadata, topic, slug)
                log.info("✅ Uploaded: %s", result.get("youtube_url", "?"))
            except Exception as e:
                log.error("❌ Upload FAILED: %s", e)
                import traceback; traceback.print_exc()
                raise
        # ── 13. Shorts ───────────────────────────────────────────────
        if include_shorts and not skip_upload:
            log.info("Step 13: generating Shorts...")
            try:
                hook_beat      = beats[0]
                hook_seg       = narration_bundle.segments[0]
                hook_image     = beat_images.get(0)
                shorts_path    = run_dir / "shorts.mp4"
                shorts_audio   = Path(hook_seg.audio_path)
                generate_shorts(
                    hook_narration = hook_beat.narration_ta,
                    hook_audio_path= shorts_audio,
                    hook_image     = hook_image,
                    protagonist    = topic.protagonist,
                    output_path    = shorts_path,
                    duration_s     = min(hook_seg.duration_seconds + 2, 55.0),
                )
                # Upload Shorts
                shorts_title = f"{topic.title_ta[:50]} #Shorts"
                shorts_slug  = slug + "_s"
                from src.uploader.youtube_publisher import YouTubePublisher as _YTP
                shorts_meta  = metadata.__class__(
                    title_ta       = shorts_title,
                    title_options  = [shorts_title],
                    description_ta = (metadata.description_ta or "") + "\n\n#Shorts #துளிர் #TamilShorts",
                    tags           = (metadata.tags or []) + ["Shorts","YouTube Shorts","Tamil Shorts"],
                    thumbnail_text = metadata.thumbnail_text,
                    emotion_trigger= metadata.emotion_trigger,
                )
                self.uploader.upload(shorts_path, thumb_path, shorts_meta, topic, shorts_slug)
                log.info("✅ Shorts uploaded")
                package = package.model_copy(update={"shorts_video_path": str(shorts_path)})
            except Exception as e:
                log.warning("Shorts generation/upload failed: %s", e)

        self.topic_scorer.record_topic(topic)
        if daily_slot:
            try:
                self.scheduler.mark_slot_complete(DailySlot(daily_slot), run_id)
            except Exception:
                pass

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
        try:
            (run_dir / "manifest.json").write_text(
                package.model_dump_json(indent=2))
        except Exception as e:
            log.warning("Manifest write failed (%s) — skipping", e)
            import json as _json
            (run_dir / "manifest.json").write_text(_json.dumps({
                "run_id": run_id, "topic": topic.title_ta,
                "video": str(final_path), "format": "long"
            }, ensure_ascii=False))
        log.info("Run %s complete — %s", run_id, final_path)
        return package
