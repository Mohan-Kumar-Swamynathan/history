"""Unit tests for unified video platform — Thulir storytelling."""

from __future__ import annotations

import re

import numpy as np
import pytest

from src.core.free_guard import validate_free_only_mode
from src.core.models import BeatType, ContentBucket, NarrativeScript, StoryMode, StoryBeat, TopicCandidate
from src.script.narrative_generator import NarrativeGenerator
from src.script.offline_story_bank import build_offline_long_script
from src.script.script_validator import ScriptValidator
from src.script.shorts_script_generator import ShortsScriptGenerator
from src.storyboard.story_beat_extractor import StoryBeatExtractor
from src.subtitle_engine.subtitle_engine import SubtitleEngine
from src.core.models import WordTiming
from src.topic.topic_scorer import TopicScorer, _builtin_fallback_topics
from src.visual_planner.visual_planner import VisualPlanner
from src.research.research_collector import ResearchCollector
from src.scheduler.content_scheduler import ContentScheduler, DailySlot


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
    topic = scorer._pick_offline_topic(ContentBucket.SUCCESS_FAILURE, [])
    assert topic.title_ta
    assert topic.total_score >= 7.5 or topic.curiosity_score >= 7.5


def test_topic_scorer_rejects_blocklist():
    scorer = TopicScorer()
    candidates = [
        TopicCandidate(
            title_ta="Top 10 success tips",
            curiosity_score=9.0,
            emotion_score=9.0,
            story_score=9.0,
            lesson_score=9.0,
        )
    ]
    result = scorer.score_and_select(candidates)
    assert "top 10" not in result.title_ta.lower() or result.source == "offline"


def test_offline_long_script_meets_targets():
    from src.core.config_loader import load_topics_config

    topic = _builtin_fallback_topics()[0]
    research = ResearchCollector()._offline_brief(topic)
    script = build_offline_long_script(topic, research)
    targets = load_topics_config().get("script_targets", {})
    expected_beats = int(targets.get("long_beat_count", 12))
    min_words = int(targets.get("long_min_words", 600))
    assert len(script.beats) == expected_beats
    validator = ScriptValidator()
    result = validator.validate_long_script(script, topic)
    assert result.word_count >= min_words, f"Only {result.word_count} words"
    assert result.valid, result.errors


def test_shorts_offline_script_word_count():
    topic = _builtin_fallback_topics()[0]
    research = ResearchCollector()._offline_brief(topic)
    script = ShortsScriptGenerator()._generate_offline(topic)
    result = ScriptValidator().validate_shorts_script(
        NarrativeScript(topic=topic, beats=script.beats, format="short")
    )
    assert result.word_count >= 80, f"Only {result.word_count} words"


def test_story_beat_extractor_enriches_entities():
    topic = TopicCandidate(
        title_ta="சென்னையில் வாழும் ரவி",
        category="storytelling",
        protagonist="ரவி",
        curiosity_score=8.0,
        emotion_score=8.0,
        story_score=8.0,
        lesson_score=7.5,
    )
    research = ResearchCollector()._offline_brief(topic)
    script = build_offline_long_script(topic, research)
    beats = StoryBeatExtractor().extract(script)
    from src.core.config_loader import load_topics_config
    expected_beats = int(load_topics_config().get("script_targets", {}).get("long_beat_count", 12))
    assert len(beats) == expected_beats
    assert beats[0].protagonist == "ரவி"


def test_visual_planner_uses_visual_keywords():
    beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="test",
        visual_keywords=["rain", "sad"],
        protagonist="ரவி",
    )
    research = ResearchCollector()._offline_brief(
        TopicCandidate(title_ta="test", category="storytelling")
    )
    plan = VisualPlanner().plan_scene(beat, research, 0)
    assert plan.background_key == "heart_break"


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
    from src.core.font_resolver import load_font
    from PIL import Image, ImageDraw

    font = load_font(130, script="ta")
    draw = ImageDraw.Draw(Image.new("RGB", (400, 200)))
    bbox = draw.textbbox((0, 0), "வணக்கம்", font=font)
    height = bbox[3] - bbox[1]
    assert height > 50


def test_animation_produces_varied_frames():
    pytest.importorskip("cairosvg")
    from src.animation_engine.animation_engine import AnimationEngine
    from src.core.models import ScenePlan

    beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="ஒரு நாள் எல்லாம் மாறியது.",
        emotion="exciting",
        protagonist="ரவி",
        duration_seconds=3.0,
        on_screen_text="Age 10",
    )
    scene_plan = ScenePlan(beat=beat, protagonist="ரவி", emotion="exciting")
    engine = AnimationEngine()
    animation_plan = engine.build_animation_plan(scene_plan)
    frames, _ = engine.render_scene_frames(scene_plan, animation_plan, 0, 1)
    assert len(frames) > 10
    assert not np.array_equal(frames[0], frames[-1])


def test_colored_icons_match_keywords():
    from src.asset_engine.decoration_engine import pick_scene_icons, get_icon_color

    icons = pick_scene_icons("உங்கள் சம்பளம் மற்றும் பயம்")
    assert len(icons) >= 1
    color = get_icon_color("heart")
    assert color[0] > 200


def test_channel_greeting_and_outro():
    from src.script.channel_intro import append_outro_cta, prepend_greeting

    opened = prepend_greeting("கதை தொடங்குகிறது.")
    assert "வணக்கம்" in opened
    closed = append_outro_cta("கதை முடிந்தது.")
    assert "subscribe" in closed.lower()
    assert "share" in closed.lower()
    assert "like" in closed.lower()


def test_topic_deduplicator_blocks_repeat_protagonist(tmp_path, monkeypatch):
    from src.topic.topic_deduplicator import TopicDeduplicator, TRACKED_HISTORY

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


def test_shorts_frame_renders_visible_main_text():
    import ae_engine
    from ae_engine import pick_background, render_frame
    from src.animation_engine.animation_engine import AnimationEngine
    from src.core.models import BeatType, ScenePlan, SceneType, StoryBeat, VisualStyle

    ae_engine.W, ae_engine.H = 1080, 1920
    beat = StoryBeat(
        beat_type=BeatType.HOOK,
        narration_ta="வணக்கம் துளிர் கதை இன்று",
        emotion="exciting",
        protagonist="அர்ஜுன்",
        on_screen_text="24 வயது",
    )
    scene_plan = ScenePlan(
        beat=beat,
        scene_type=SceneType.CHARACTER,
        visual_style=VisualStyle.WHITEBOARD,
        camera="slow_zoom",
        emotion="exciting",
        assets=[],
        protagonist="அர்ஜுன்",
        background_key="clean",
        hero_icon="lightbulb",
        icon_placement="top_right",
    )
    engine = AnimationEngine()
    animation_plan = engine.build_animation_plan(scene_plan)
    frames, _ = engine.render_scene_frames(
        scene_plan,
        animation_plan,
        scene_index=0,
        total_scenes=1,
        duration_seconds=2.0,
        is_shorts=True,
    )
    assert frames
    frame = frames[12]
    # Headline + narration region should contain ink (not blank white canvas).
    ink_pixels = int((frame[:900, :, :] < 240).any(axis=2).sum())
    assert ink_pixels > 200


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


def test_extract_json_array_handles_wrapped_object():
    from src.core.llm_json_parser import extract_json_array

    raw = """{"topics":[{"title_ta":"Test","protagonist":"Hero","curiosity_score":8}]}"""
    parsed = extract_json_array(raw)
    assert len(parsed) == 1
    assert parsed[0]["protagonist"] == "Hero"


def test_extract_json_object_single_topic():
    from src.core.llm_json_parser import extract_json_object

    raw = 'Sure! {"title_ta":"கதை","protagonist":"ரவி","curiosity_score":8.5}'
    parsed = extract_json_object(raw)
    assert parsed is not None
    assert parsed["protagonist"] == "ரவி"


def test_visual_variety_director_returns_segment_styles():
    from src.animation_engine.visual_variety import VisualVarietyDirector
    from src.core.models import BeatType

    director = VisualVarietyDirector("scene-1", "exciting", BeatType.HOOK)
    first = director.segment_style(0)
    second = director.segment_style(1)
    assert first.motion_variant
    assert first.figure_emotion
    assert first.accent_icon
    assert director.scene_transition() in {"crossfade", "push", "wipe"}


def test_enrich_long_script_meets_minimum_words():
    from src.script.script_enricher import enrich_long_script

    topic = _builtin_fallback_topics()[0]
    research = ResearchCollector()._offline_brief(topic)
    short_beats = [
        StoryBeat(
            beat_type=BeatType.HOOK,
            narration_ta="குறுகிய வரி.",
            emotion="exciting",
            protagonist=topic.protagonist,
        )
        for _ in range(12)
    ]
    script = NarrativeScript(topic=topic, beats=short_beats, format="long")
    enriched = enrich_long_script(script, topic, research)
    result = ScriptValidator().validate_long_script(enriched, topic)
    assert result.word_count >= 600, result.errors
    assert result.valid, result.errors


def test_story_mode_enum_values():
    assert StoryMode.BIOGRAPHICAL.value == "biographical"
    assert ContentBucket.BUSINESS.value == "business"


def test_resolve_beat_type_aliases():
    from src.core.models import BeatType, resolve_beat_type

    assert resolve_beat_type("low_point", BeatType.HOOK) == BeatType.CONFLICT
    assert resolve_beat_type("twist", BeatType.HOOK) == BeatType.TURNING_POINT
    assert resolve_beat_type("hook", BeatType.CONFLICT) == BeatType.HOOK
