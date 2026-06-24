"""Unit tests for stock video engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.models import BeatType, StoryBeat
from src.renderer.stock_video_engine import (
    build_beat_scenes,
    build_short_scene,
    is_stock_video_enabled,
)


def _beat(duration: float = 12.0) -> StoryBeat:
    return StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="test",
        protagonist="Hero",
        emotion="neutral",
        duration_seconds=duration,
    )


def test_build_beat_scenes_uses_beat_duration():
    beats = [_beat(10.0), _beat(20.0)]
    scenes = build_beat_scenes(beats)
    assert len(scenes) == 2
    assert scenes[0]["duration_seconds"] == 10.0
    assert scenes[1]["duration_seconds"] == 20.0


def test_build_short_scene_caps_duration():
    scenes = build_short_scene(90.0)
    assert len(scenes) == 1
    assert scenes[0]["duration_seconds"] == 55.0


def test_is_stock_video_enabled_requires_api_key(monkeypatch):
    monkeypatch.setenv("USE_STOCK_VIDEO", "true")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert is_stock_video_enabled() is False

    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    assert is_stock_video_enabled() is True


@patch("src.renderer.stock_video_engine._download_stock_video_file", return_value=True)
@patch("src.renderer.stock_video_engine._search_pexels_video_url", return_value="https://example.com/v.mp4")
def test_fetch_beat_stock_videos_downloads_per_beat(mock_search, mock_download, tmp_path, monkeypatch):
    monkeypatch.setenv("USE_STOCK_VIDEO", "true")
    monkeypatch.setenv("PEXELS_API_KEY", "test-key")

    from src.renderer.stock_video_engine import fetch_beat_stock_videos

    beats = [_beat(8.0), _beat(9.0)]
    downloaded = fetch_beat_stock_videos(beats, "Test Topic", tmp_path, orientation="landscape")
    assert len(downloaded) == 2
    assert mock_search.call_count >= 2
