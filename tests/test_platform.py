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


def test_offline_long_script_has_24_beats():
    topic = _builtin_fallback_topics()[0]
    research = ResearchCollector()._offline_brief(topic)
    script = build_offline_long_script(topic, research)
    assert len(script.beats) == 24
    validator = ScriptValidator()
    result = validator.validate_long_script(script, topic)
    assert result.word_count >= 1000, f"Only {result.word_count} words"
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
    assert len(beats) == 24
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
    assert len(icons) == 1
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


def test_story_mode_enum_values():
    assert StoryMode.BIOGRAPHICAL.value == "biographical"
    assert ContentBucket.BUSINESS.value == "business"
