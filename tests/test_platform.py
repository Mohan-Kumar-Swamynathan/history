"""Unit tests for Thulir unified platform (v3 pipeline support code)."""

from __future__ import annotations

from src.core.free_guard import validate_free_only_mode
from src.core.models import TopicCandidate, WordTiming
from src.research.research_collector import ResearchCollector
from src.scheduler.content_scheduler import ContentScheduler, DailySlot
from src.subtitle_engine.subtitle_engine import SubtitleEngine
from src.topic.topic_scorer import TopicScorer, _builtin_fallback


def test_free_guard_passes_without_paid_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    validate_free_only_mode()


def test_topic_candidate_weighted_score():
    topic = TopicCandidate(
        title_ta="Test",
        curiosity_score=10.0,
        emotion_score=10.0,
        story_score=10.0,
        lesson_score=10.0,
    )
    assert topic.total_score == 10.0


def test_topic_scorer_offline_fallback():
    scorer = TopicScorer()
    from src.core.models import ContentBucket

    topic = scorer._from_fallback(ContentBucket.SUCCESS_FAILURE, [])
    assert topic.title_ta
    assert topic.total_score >= 7.5 or topic.curiosity_score >= 7.5


def test_research_collector_offline_brief():
    topic = _builtin_fallback()[0]
    brief = ResearchCollector()._offline_brief(topic)
    assert brief.facts or brief.story_facts


def test_subtitle_engine_writes_srt_and_ass(tmp_path):
    timings = [
        WordTiming(word="வணக்கம்", start_ms=0, end_ms=500),
        WordTiming(word="உலகம்", start_ms=500, end_ms=1000),
    ]
    engine = SubtitleEngine()
    srt = engine.write_srt(timings, tmp_path / "sub.srt")
    ass = engine.write_ass(timings, tmp_path / "sub.ass")
    assert srt.exists()
    assert ass.exists()
    assert "வணக்கம்" in srt.read_text(encoding="utf-8")


def test_content_scheduler_tracks_slots():
    scheduler = ContentScheduler()
    scheduler.mark_slot_complete(DailySlot.MORNING_LONG, "test-run")
    assert scheduler.is_slot_complete(DailySlot.MORNING_LONG)


def test_tamil_font_loads_at_large_size():
    from PIL import Image, ImageDraw

    from src.core.font_resolver import load_font

    font = load_font(130, script="ta")
    draw = ImageDraw.Draw(Image.new("RGB", (400, 200)))
    bbox = draw.textbbox((0, 0), "வணக்கம்", font=font)
    height = bbox[3] - bbox[1]
    assert height > 50


def test_topic_deduplicator_blocks_repeat_protagonist(tmp_path, monkeypatch):
    from src.topic.topic_deduplicator import TopicDeduplicator

    history_path = tmp_path / "topic_history.json"
    history_path.write_text(
        '[{"title_ta":"Old story","protagonist":"Nokia","fingerprint":"old story"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.topic.topic_deduplicator.TRACKED_HISTORY", history_path)

    deduplicator = TopicDeduplicator()
    candidate = TopicCandidate(
        title_ta="Nokia மறுபடியும்",
        protagonist="Nokia",
        curiosity_score=8.0,
        emotion_score=8.0,
        story_score=8.0,
        lesson_score=7.5,
    )
    assert deduplicator.is_duplicate(candidate) is True


def test_hybrid_mode_uses_llm_for_topic_and_script_only():
    from src.core.llm_policy import (
        STAGE_LONG_SCRIPT,
        STAGE_METADATA,
        STAGE_RESEARCH,
        STAGE_SHORTS_SCRIPT,
        STAGE_TOPIC,
        should_derive_shorts_from_long,
        should_use_llm,
        topic_candidate_count,
    )

    import os

    old = os.environ.get("LLM_MODE")
    os.environ["LLM_MODE"] = "hybrid"
    try:
        assert should_use_llm(STAGE_TOPIC) is True
        assert should_use_llm(STAGE_LONG_SCRIPT) is True
        assert should_use_llm(STAGE_SHORTS_SCRIPT) is False
        assert should_use_llm(STAGE_RESEARCH) is False
        assert should_use_llm(STAGE_METADATA) is False
        assert should_derive_shorts_from_long() is True
        assert topic_candidate_count(20) == 5
    finally:
        if old:
            os.environ["LLM_MODE"] = old
        else:
            os.environ.pop("LLM_MODE", None)


def test_ci_strategy_prefers_github_on_actions(monkeypatch):
    from src.core.llm_registry import resolve_ci_strategy, resolve_provider_order

    monkeypatch.delenv("LLM_CI_STRATEGY", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("GEMINI_KEY", raising=False)
    assert resolve_ci_strategy() == "github_first"
    assert resolve_provider_order()[0] == "github"


def test_provider_exhausted_skipped_for_session(monkeypatch):
    from src.core.llm_registry import mark_provider_exhausted, reset_provider_registry, resolve_provider_order

    reset_provider_registry()
    monkeypatch.setenv("GEMINI_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setenv("LLM_CI_STRATEGY", "full_chain")
    mark_provider_exhausted("gemini")
    mark_provider_exhausted("groq")
    order = resolve_provider_order()
    assert order == ["github"]


def test_extract_json_array_handles_markdown_fence():
    from src.core.llm_json_parser import extract_json_array

    raw = """Here are topics:
```json
[{"title_ta":"Test","protagonist":"Hero","curiosity_score":8}]
```"""
    parsed = extract_json_array(raw)
    assert len(parsed) == 1
    assert parsed[0]["protagonist"] == "Hero"
