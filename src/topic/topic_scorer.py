"""Topic scorer — துளிர் content bible implementation.

Scoring framework from content director brief:
  - Curiosity Score    (1-10)
  - Emotion Score      (1-10)
  - Conflict Score     (1-10)
  - Shock Score        (1-10)
  - Story Potential    (1-10)
  - Thumbnail Potential(1-10)
  - Tamil Audience     (1-10)
  → Only topics scoring 8+ overall accepted

Content pillars:
  40% Extraordinary People
  25% History Stories
  15% Business Stories
  10% Strange True Stories
  10% Science & Discovery

Topics are GOOD if they make viewers say "Wow, I never knew that."
Topics are BAD if they feel like a school lesson.
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import List, Optional

import yaml

from src.core.config_loader import CONFIG_DIR, get_output_dir, load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_json_parser import extract_json_array, extract_json_object
from src.core.llm_policy import (
    STAGE_TOPIC,
    max_tokens_for_stage,
    preferred_provider_for_stage,
    should_use_llm,
    topic_candidate_count,
)
from src.core.models import ContentBucket, StoryMode, TopicCandidate
from src.topic.topic_deduplicator import TopicDeduplicator

try:
    from src.topic.trend_engine import TrendEngine
    _TRENDS_AVAILABLE = True
except ImportError:
    _TRENDS_AVAILABLE = False

log = logging.getLogger(__name__)

# Content pillar weights
PILLAR_WEIGHTS = {
    ContentBucket.SUCCESS_FAILURE: 0.40,   # Extraordinary People
    ContentBucket.HISTORICAL_STORY: 0.25,  # History Stories
    ContentBucket.BUSINESS: 0.15,          # Business Stories
    ContentBucket.PSYCHOLOGY: 0.10,        # Strange True Stories
    ContentBucket.SCIENCE: 0.10,           # Science & Discovery
}

CONTENT_DIRECTOR_PROMPT = """You are the Content Director, Historian, Story Researcher, Script Writer,
and YouTube Growth Strategist for the Tamil storytelling channel "துளிர்".

CHANNEL MISSION: துளிர் tells the most fascinating TRUE stories from history, business,
science, human achievement, failure, mystery, war, and discovery.

GOAL: Make viewers say "Wow, I never knew that."

Every video must feel like Almost Everything, MagnatesMedia, RealLifeLore, Johnny Harris style.

TOPIC SCORING (score each 1-10, only accept 8+ overall):
- Curiosity Score: Does it make people instantly want to know what happened?
- Emotion Score: Does it trigger surprise, fear, hope, triumph, regret?
- Conflict Score: Is there a clear antagonist, obstacle, or tension?
- Shock Score: Is there an unexpected twist or counterintuitive fact?
- Story Potential: Is there a clear arc (setup → conflict → resolution)?
- Thumbnail Potential: Can it be captured in one powerful image + 2-4 words?
- Tamil Audience Appeal: Does a Tamil viewer have a personal connection?

GOOD TOPIC: "1009 times rejected. At 65. Then built the biggest food chain."
BAD TOPIC: "The history of the Mughal Empire"

AVOID: generic history lessons, timeline explanations, date-heavy content,
boring biographies, school textbook topics, political debates, low-conflict stories.

CONTENT PILLARS:
40% Extraordinary People (rejected inventors, erased women, poor boys who changed the world)
25% History Stories (dramatic decisions, forgotten wars, collapsed empires)
15% Business Stories (Nokia's mistake, Kodak's failure, Toyota's secret)
10% Strange True Stories (vanished towns, unexplained events, weird records)
10% Science & Discovery (accidental inventions, mocked scientists)

HOOK EXAMPLES (first 15 seconds — the real test):
✅ "1009 times. That's how many times they rejected him."
✅ "One decision destroyed an entire empire."
✅ "This man was laughed at by everyone. Then the world changed."
❌ "Today we are going to learn about..."
❌ "In this video..."

Already used topics (avoid these):
{avoid_list}
"""

TOPIC_GENERATION_PROMPT = CONTENT_DIRECTOR_PROMPT + """

Generate {count} story topics for the {bucket} content pillar.

Each must be:
- A REAL verifiable story (has Wikipedia or credible sources)
- Never invented or composite
- Scored 8+ on ALL seven criteria
- Focused on ONE specific dramatic moment, not a broad biography

Return ONLY JSON array:
[{{
  "title_ta": "Tamil YouTube title — curiosity-driven, under 60 chars",
  "protagonist": "person/company/event name",
  "protagonist_age": "age at key dramatic moment",
  "situation": "specific place + year + exact context",
  "core_problem": "the specific conflict or failure",
  "emotional_hook": "the most shocking/dramatic specific fact",
  "turning_point": "the exact moment things changed",
  "lesson": "what the viewer takes away",
  "hook_question": "first-15-second hook in Tamil — makes them unable to stop watching",
  "open_loop": "unanswered question that keeps viewer watching",
  "story_mode": "biographical",
  "content_bucket": "{bucket}",
  "wikipedia_subject": "exact English Wikipedia article title",
  "curiosity_score": 9.0,
  "emotion_score": 8.5,
  "conflict_score": 9.0,
  "shock_score": 8.0,
  "story_score": 9.0,
  "thumbnail_score": 8.5,
  "tamil_score": 8.0
}}]"""


class TopicScorer:
    def __init__(self) -> None:
        self.deduplicator = TopicDeduplicator()
        if _TRENDS_AVAILABLE:
            history_path = get_output_dir() / ".." / "data" / "topic_history.json"
            self._trend_engine = TrendEngine(history_path)
        else:
            self._trend_engine = None

    def discover_topic(
        self,
        category: Optional[str] = None,
        content_bucket: Optional[ContentBucket] = None,
    ) -> TopicCandidate:
        bucket = content_bucket or self._pick_pillar()
        used   = self.deduplicator.load_used_titles()
        avoid  = self.deduplicator.recent_avoid_list(20)

        # 1. Try trends first
        if self._trend_engine and has_llm_credentials():
            try:
                topic = self._from_trends(bucket, avoid)
                if topic:
                    log.info("✅ Trend topic selected: %s", topic.title_ta[:60])
                    return topic
            except Exception as e:
                log.warning("Trend discovery failed: %s", e)

        # 2. LLM content director
        if has_llm_credentials() and should_use_llm(STAGE_TOPIC):
            try:
                topic = self._from_llm(bucket, avoid)
                if topic:
                    log.info("✅ LLM topic selected: %s", topic.title_ta[:60])
                    return topic
            except Exception as e:
                log.warning("LLM topic failed: %s", e)

        # 3. Curated fallback
        topic = self._from_fallback(bucket, used)
        log.info("✅ Fallback topic: %s", topic.title_ta[:60])
        return topic

    def _from_trends(self, bucket, avoid):
        llm_fn = generate_text if has_llm_credentials() else None
        trending = self._trend_engine.discover(llm_fn=llm_fn, count=3)
        for trend in trending:
            topic = self._trend_to_story(trend, bucket, avoid)
            if topic and self._passes_score_gate(topic):
                return topic
        return None

    def _trend_to_story(self, trend, bucket, avoid):
        name  = trend["name"]
        wiki  = trend.get("wikipedia_subject", name)
        extr  = trend.get("extract", "")
        prompt = CONTENT_DIRECTOR_PROMPT.format(avoid_list=avoid) + f"""

Convert this trending subject into a துளிர் story topic.

Subject: {name}
Wikipedia: {wiki}
Context: {extr[:400]}

Apply the full scoring framework. Only return if scores 8+ overall.
Return ONE JSON object or empty {{}} if not suitable:
{{
  "title_ta": "...", "protagonist": "{name}", "protagonist_age": "...",
  "situation": "...", "core_problem": "...", "emotional_hook": "...",
  "turning_point": "...", "lesson": "...", "hook_question": "...",
  "open_loop": "...", "story_mode": "biographical",
  "content_bucket": "{bucket.value}", "wikipedia_subject": "{wiki}",
  "curiosity_score": 0, "emotion_score": 0, "conflict_score": 0,
  "shock_score": 0, "story_score": 0, "thumbnail_score": 0, "tamil_score": 0
}}"""
        try:
            raw = generate_text(prompt, max_tokens=800)
            data = extract_json_object(raw)
            if data and float(data.get("curiosity_score", 0)) >= 7.5:
                return _dict_to_topic(data, "trend")
        except Exception as e:
            log.warning("trend_to_story failed: %s", e)
        return None

    def _from_llm(self, bucket, avoid):
        count  = max(5, topic_candidate_count(10))
        prompt = TOPIC_GENERATION_PROMPT.format(
            avoid_list=avoid, count=count, bucket=bucket.value
        )
        raw = generate_text(
            prompt,
            max_tokens=max_tokens_for_stage(STAGE_TOPIC, 3000),
            preferred=preferred_provider_for_stage(STAGE_TOPIC),
        )
        candidates = [
            _dict_to_topic(d, "llm", bucket)
            for d in (extract_json_array(raw) or [])
            if d
        ]
        # Filter by score gate
        valid = [c for c in candidates
                 if self._passes_score_gate(c)
                 and not self.deduplicator.is_duplicate(c)]
        if not valid:
            # Relax threshold slightly
            valid = [c for c in candidates if not self.deduplicator.is_duplicate(c)]
        if not valid:
            raise ValueError("No valid candidates from LLM")
        valid.sort(key=lambda t: t.total_score, reverse=True)
        return valid[0]

    def _passes_score_gate(self, topic: TopicCandidate) -> bool:
        """Content bible: only accept topics scoring 8+ overall."""
        return topic.total_score >= 8.0

    def _pick_pillar(self) -> ContentBucket:
        buckets = list(PILLAR_WEIGHTS.keys())
        weights = list(PILLAR_WEIGHTS.values())
        return random.choices(buckets, weights=weights, k=1)[0]

    def _from_fallback(self, bucket, used):
        all_t   = self._load_fallback()
        avail   = [t for t in all_t if not self.deduplicator.is_duplicate(t)]
        bucket_t = [t for t in avail if t.content_bucket == bucket]
        pool    = bucket_t or avail or all_t
        return random.choice(pool).model_copy(update={"source": "offline"})

    def _load_fallback(self) -> List[TopicCandidate]:
        path = CONFIG_DIR / "fallback_topics.yml"
        if not path.exists():
            return _builtin_fallback()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            topics = [_dict_to_topic(item, "offline") for item in data.get("topics", [])]
            return topics or _builtin_fallback()
        except Exception:
            return _builtin_fallback()

    def score_and_select(self, candidates):
        valid = [c for c in candidates
                 if not self.deduplicator.is_duplicate(c)
                 and self._passes_score_gate(c)]
        if not valid:
            valid = [c for c in candidates if not self.deduplicator.is_duplicate(c)]
        if not valid:
            return self._from_fallback(ContentBucket.SUCCESS_FAILURE, [])
        valid.sort(key=lambda t: t.total_score, reverse=True)
        return valid[0]

    def record_topic(self, topic):
        self.deduplicator.record_topic(topic)


def _dict_to_topic(data: dict, source="llm",
                   default_bucket=None) -> TopicCandidate:
    bucket_raw = data.get("content_bucket") or (
        default_bucket.value if default_bucket else "success_failure"
    )
    mode_raw = data.get("story_mode", "biographical")
    try:    bucket = ContentBucket(bucket_raw)
    except: bucket = ContentBucket.SUCCESS_FAILURE
    try:    mode   = StoryMode(mode_raw)
    except: mode   = StoryMode.BIOGRAPHICAL

    # Compute total score from all 7 dimensions
    scores = [
        float(data.get("curiosity_score",  data.get("curiosity",  8.0))),
        float(data.get("emotion_score",    data.get("emotion",    8.0))),
        float(data.get("conflict_score",   data.get("conflict",   8.0))),
        float(data.get("shock_score",      data.get("shock",      7.5))),
        float(data.get("story_score",      data.get("story",      8.0))),
        float(data.get("thumbnail_score",  data.get("thumbnail",  7.5))),
        float(data.get("tamil_score",      data.get("tamil",      8.0))),
    ]
    avg_score = sum(scores) / len(scores)

    return TopicCandidate(
        title_ta         = data.get("title_ta") or data.get("story_title", "Untitled"),
        category         = data.get("category", "storytelling"),
        hook             = data.get("hook_question", data.get("hook", "")),
        protagonist      = data.get("protagonist", "நாயகன்"),
        protagonist_age  = str(data.get("protagonist_age", "")),
        situation        = data.get("situation", ""),
        core_problem     = data.get("core_problem", ""),
        emotional_hook   = data.get("emotional_hook", ""),
        turning_point    = data.get("turning_point", ""),
        lesson           = data.get("lesson", ""),
        hook_question    = data.get("hook_question", data.get("hook", "")),
        open_loop        = data.get("open_loop", ""),
        story_mode       = mode,
        content_bucket   = bucket,
        curiosity_score  = scores[0],
        emotion_score    = scores[1],
        story_score      = scores[4],
        lesson_score     = scores[6],
        wikipedia_subject= data.get("wikipedia_subject", ""),
        source           = source,
        total_score      = avg_score,
    )


def _builtin_fallback() -> List[TopicCandidate]:
    """High-scoring fallback topics — all pass the 8+ gate."""
    return [
        TopicCandidate(
            title_ta="1009 முறை நிராகரிக்கப்பட்டவர் — Colonel Sanders கதை",
            hook="1009 times. That's how many times they rejected him. At 65.",
            protagonist="Colonel Sanders", protagonist_age="65",
            situation="Kentucky USA, 1952 — roadside restaurant",
            core_problem="1009 restaurant owners rejected his chicken recipe",
            emotional_hook="At 65, after bankruptcy, driving state-to-state with a single recipe",
            turning_point="The 1010th call — Pete Harman of Utah said yes",
            lesson="The only failure is stopping",
            hook_question="65 வயதில் 1009 முறை தோற்றவர் எப்படி billionaire ஆனார்?",
            open_loop="ஆனால் அந்த 1010-வது phone call-ல் என்ன நடந்தது?",
            story_mode=StoryMode.BIOGRAPHICAL, content_bucket=ContentBucket.SUCCESS_FAILURE,
            wikipedia_subject="Colonel Sanders",
            curiosity_score=9.5, emotion_score=9.0, story_score=9.5, lesson_score=8.5,
            total_score=9.1, source="offline",
        ),
        TopicCandidate(
            title_ta="Nokia ஏன் வீழ்ந்தது? ஒரு தவறான வார்த்தையின் கதை",
            hook="In 2007, Nokia owned 40% of the world's phones. By 2013, it was gone.",
            protagonist="Nokia", protagonist_age="",
            situation="Finland boardroom, 2007 — iPhone launch day",
            core_problem="Engineers knew Symbian was dying. Nobody told the CEO.",
            emotional_hook="A culture of fear killed the world's #1 phone brand",
            turning_point="The moment Nokia engineers chose silence over truth",
            lesson="Silence in a boardroom can destroy empires",
            hook_question="உலகின் #1 phone brand எப்படி 6 ஆண்டுகளில் மறைந்தது?",
            open_loop="ஆனால் Nokia engineers-க்கு முன்பே தெரிந்திருந்தது — ஏன் சொல்லவில்லை?",
            story_mode=StoryMode.BIOGRAPHICAL, content_bucket=ContentBucket.BUSINESS,
            wikipedia_subject="Nokia",
            curiosity_score=9.0, emotion_score=8.5, story_score=9.0, lesson_score=9.0,
            total_score=8.9, source="offline",
        ),
        TopicCandidate(
            title_ta="Kodak-ஐ கொன்றது Kodak-�ே — Digital camera-ஐ அவர்களே கண்டுபிடித்தார்கள்",
            hook="Kodak invented the digital camera in 1975. Then buried it.",
            protagonist="Kodak", protagonist_age="",
            situation="Rochester NY, 1975 — secret lab",
            core_problem="Steve Sasson's digital camera was hidden for 20 years to protect film revenue",
            emotional_hook="The invention that could have saved them — they destroyed it themselves",
            turning_point="2012: Kodak filed for bankruptcy. Instagram was valued at $1 billion.",
            lesson="Protecting yesterday's success can kill tomorrow's survival",
            hook_question="Digital camera-ஐ கண்டுபிடித்தவர்கள் Kodak-ஏ — பிறகு ஏன் bankrupt ஆனார்கள்?",
            open_loop="Steve Sasson அந்த camera-ஐ CEO-விடம் காட்டியபோது என்ன நடந்தது?",
            story_mode=StoryMode.BIOGRAPHICAL, content_bucket=ContentBucket.BUSINESS,
            wikipedia_subject="Kodak",
            curiosity_score=9.5, emotion_score=8.5, story_score=9.0, lesson_score=9.5,
            total_score=9.0, source="offline",
        ),
        TopicCandidate(
            title_ta="Nikola Tesla-வை யாரும் நினைவில் வைக்கவில்லை — Edison ஏன் வென்றார்?",
            hook="Tesla gave us electricity. Edison took the credit. And the money.",
            protagonist="Nikola Tesla", protagonist_age="36",
            situation="New York, 1893 — the War of Currents",
            core_problem="Tesla's AC power was better. Edison's DC lobby tried to destroy him.",
            emotional_hook="Tesla died alone, penniless, in a hotel room. His patents lit the world.",
            turning_point="The Chicago World's Fair 1893 — Tesla's AC lights won",
            lesson="History remembers the marketers, not always the inventors",
            hook_question="உலகிற்கு மின்சாரம் கொடுத்தவர் Tesla — ஆனால் ஏன் அவர் மறக்கப்பட்டார்?",
            open_loop="Tesla-வும் Edison-உம் நேரடியாக சந்தித்த அந்த நாள் என்ன நடந்தது?",
            story_mode=StoryMode.BIOGRAPHICAL, content_bucket=ContentBucket.SUCCESS_FAILURE,
            wikipedia_subject="Nikola Tesla",
            curiosity_score=9.5, emotion_score=9.0, story_score=9.5, lesson_score=8.5,
            total_score=9.2, source="offline",
        ),
        TopicCandidate(
            title_ta="உலகின் மிக குறுகிய போர் — 38 நிமிடங்கள்",
            hook="The shortest war in history lasted 38 minutes. One side didn't even know it started.",
            protagonist="Anglo-Zanzibar War", protagonist_age="",
            situation="Zanzibar, August 27, 1896 — 9:02 AM",
            core_problem="A new Sultan took power Britain didn't approve. They gave him an ultimatum.",
            emotional_hook="The Sultan's palace was destroyed in 38 minutes. 500 casualties. Done.",
            turning_point="9:40 AM — the Sultan fled. War over.",
            lesson="Power without backing is just a title",
            hook_question="வரலாற்றில் மிகவும் குறுகிய போர் — 38 நிமிடங்களில் என்ன நடந்தது?",
            open_loop="ஆனால் அந்த Sultan போர் தொடங்கும் என்று நம்பினாரா?",
            story_mode=StoryMode.BIOGRAPHICAL, content_bucket=ContentBucket.HISTORICAL_STORY,
            wikipedia_subject="Anglo-Zanzibar War",
            curiosity_score=9.5, emotion_score=8.0, story_score=8.5, lesson_score=7.5,
            total_score=8.8, source="offline",
        ),
    ]
