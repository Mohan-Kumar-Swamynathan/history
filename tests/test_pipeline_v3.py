"""Unit tests for VideoPipelineV3 — intro sync, Shorts, format routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.core.models import BeatType, StoryBeat, TopicCandidate, VideoPackage
from src.pipelines.generate_video_v3 import (
    RENDER_FPS,
    VideoPipelineV3,
    intro_offset_ms,
    resample_intro_frames,
)
from src.renderer.brand import INTRO_DURATION_S, INTRO_FRAMES
from src.renderer.video_renderer import VideoRenderer


def _make_intro_frames(count: int = INTRO_FRAMES) -> list[np.ndarray]:
    return [np.zeros((1080, 1920, 3), dtype=np.uint8) for _ in range(count)]


def test_intro_resampled_to_render_fps():
    intro_frames = _make_intro_frames()
    resampled = resample_intro_frames(intro_frames, RENDER_FPS)
    expected_count = int(INTRO_DURATION_S * RENDER_FPS)
    assert len(resampled) == expected_count
    assert len(resampled) == 28


def test_intro_offset_ms_matches_duration():
    assert intro_offset_ms() == int(INTRO_DURATION_S * 1000)


def test_ffmpeg_encode_failure_raises():
    mock_process = MagicMock()
    mock_process.stdin = MagicMock()
    mock_process.wait.return_value = 1

    pipeline = VideoPipelineV3()
    hook_beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="test narration",
        protagonist="Hero",
        emotion="neutral",
        duration_seconds=5.0,
    )
    pipeline.narrative = MagicMock()
    pipeline.narrative.generate.return_value = MagicMock(beats=[hook_beat])
    pipeline.voice_engine = MagicMock()
    pipeline.voice_engine.synthesize_all_beats.return_value = MagicMock(
        total_duration_seconds=5.0,
        segments=[MagicMock(
            duration_seconds=5.0,
            word_timings=[],
            audio_path="/tmp/audio.mp3",
        )],
        all_word_timings=[],
        narration_path="/tmp/narration.mp3",
    )
    pipeline.image_engine = MagicMock()
    pipeline.image_engine.prefetch_all.return_value = {0: MagicMock()}

    with patch("src.pipelines.generate_video_v3.subprocess.Popen", return_value=mock_process):
        with patch("src.pipelines.generate_video_v3.render_scene_frames", return_value=[np.zeros((1080, 1920, 3), dtype=np.uint8)]):
            with patch("src.pipelines.generate_video_v3.render_intro_frames", return_value=_make_intro_frames()):
                with pytest.raises(RuntimeError, match="Raw video encoding failed"):
                    pipeline._run_long_video(
                        run_id="test_run",
                        run_dir=Path("/tmp/test_run"),
                        topic=TopicCandidate(title_ta="Test"),
                        research=MagicMock(),
                        skip_upload=True,
                        daily_slot=None,
                        include_shorts=False,
                    )


def test_video_format_short_routes_to_shorts_only():
    pipeline = VideoPipelineV3()
    expected_package = VideoPackage(
        run_id="short_run",
        topic=TopicCandidate(title_ta="Short topic"),
        long_video_path="/tmp/shorts.mp4",
        shorts_video_path="/tmp/shorts.mp4",
        format="short",
    )

    with patch.object(pipeline, "_resolve_topic", return_value=TopicCandidate(title_ta="Short topic")):
        with patch.object(pipeline, "research") as mock_research:
            mock_research.collect.return_value = MagicMock()
            with patch.object(pipeline, "_run_shorts_only", return_value=expected_package) as mock_shorts:
                result = pipeline.run(video_format="short")
                mock_shorts.assert_called_once()
                assert result.format == "short"


def test_shorts_package_path_set_without_upload():
    pipeline = VideoPipelineV3()
    topic = TopicCandidate(title_ta="Test topic", protagonist="Hero")
    package = VideoPackage(
        run_id="run1",
        topic=topic,
        long_video_path="/tmp/video.mp4",
        format="long",
    )
    hook_beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="hook text",
        protagonist="Hero",
        emotion="neutral",
        duration_seconds=10.0,
    )
    narration_bundle = MagicMock()
    narration_bundle.segments = [MagicMock(duration_seconds=10.0, audio_path="/tmp/hook.mp3")]

    with patch("src.pipelines.generate_video_v3.generate_shorts", return_value=Path("/tmp/shorts.mp4")):
        updated = pipeline._generate_and_upload_shorts(
            package=package,
            beats=[hook_beat],
            narration_bundle=narration_bundle,
            beat_images={0: MagicMock()},
            topic=topic,
            skip_upload=True,
            run_dir=Path("/tmp/run"),
            run_id="run1",
        )

    assert updated.shorts_video_path == str(Path("/tmp/run/shorts.mp4"))


def test_shorts_upload_uses_upload_shorts():
    pipeline = VideoPipelineV3()
    pipeline.uploader = MagicMock()
    topic = TopicCandidate(title_ta="Test topic", protagonist="Hero")
    from src.core.models import VideoMetadata
    metadata = VideoMetadata(title_ta="Title", description_ta="Description")
    package = VideoPackage(
        run_id="run1",
        topic=topic,
        long_video_path="/tmp/video.mp4",
        metadata=metadata,
        format="long",
    )
    hook_beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="hook text",
        protagonist="Hero",
        emotion="neutral",
        duration_seconds=10.0,
    )
    narration_bundle = MagicMock()
    narration_bundle.segments = [MagicMock(duration_seconds=10.0, audio_path="/tmp/hook.mp3")]

    with patch("src.pipelines.generate_video_v3.generate_shorts", return_value=Path("/tmp/shorts.mp4")):
        pipeline._generate_and_upload_shorts(
            package=package,
            beats=[hook_beat],
            narration_bundle=narration_bundle,
            beat_images={0: MagicMock()},
            topic=topic,
            skip_upload=False,
            run_dir=Path("/tmp/run"),
            run_id="run1",
        )

    pipeline.uploader.upload_shorts.assert_called_once()
    pipeline.uploader.upload.assert_not_called()


def test_mux_audio_strict_raises_on_failure(tmp_path):
    renderer = VideoRenderer()
    video_path = tmp_path / "video.mp4"
    audio_path = tmp_path / "audio.mp3"
    output_path = tmp_path / "out.mp4"
    video_path.write_bytes(b"not-a-video")
    audio_path.write_bytes(b"not-audio")

    with pytest.raises(RuntimeError, match="Audio mux failed"):
        renderer.mux_audio(
            video_path,
            audio_path,
            output_path,
            strict=True,
        )
