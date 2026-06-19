"""Topic scorer v2 — trend-aware, dedup-enforced, Wikipedia-validated.

Discovery pipeline:
  1. TrendEngine fetches Google Trends India + Wikipedia pageviews
  2. LLM converts trending term → full TopicCandidate with story arc
  3. Deduplicator checks against 30-day history
  4. Score and select best fit for channel

Fallback: curated fallback_topics.yml (7 strong stories)
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
from src.topic.trend_engine import TrendEngine

log = logging.getLogger(__name__)


class TopicScorer:
    def __init__(self) -> None:
        self.deduplicator = TopicDeduplicator()
        history_path = get_output_dir() / ".." / "data" / "topic_history.json"
        self._trend_engine = TrendEngine(history_path)

    def discover_topic(
        self,
        category: Optional[str] = None,
        content_bucket: Optional[ContentBucket] = None,
    ) -> TopicCandidate:
        used_titles = self.deduplicator.load_used_titles()
        target_bucket = content_bucket or self._pick_content_bucket()

        # ── Step 1: Try trend-aware discovery ────────────────────────
        if has_llm_credentials() and should_use_llm(STAGE_TOPIC):
            try:
                topic = self._discover_from_trends(target_bucket, used_titles)
                if topic:
                    log.info("✅ Trend topic: %s", topic.title_ta[:60])
                    return topic
            except Exception as exc:
                log.warning("Trend discovery failed: %s", exc)

        # ── Step 2: LLM topic generation (no trend data) ─────────────
        if has_llm_credentials() and should_use_llm(STAGE_TOPIC):
            try:
                topic = self._discover_with_llm(target_bucket, used_titles)
                log.info("✅ LLM topic: %s", topic.title_ta[:60])
                return topic
            except Exception as exc:
                log.warning("LLM topic failed: %s", exc)

        # ── Step 3: Curated fallback bank ────────────────────────────
        topic = self._pick_offline_topic(target_bucket, used_titles)
        log.info("✅ Fallback topic: %s", topic.title_ta[:60])
        return topic

    def _discover_from_trends(
        self,
        bucket: ContentBucket,
        used_titles: List[str],
    ) -> Optional[TopicCandidate]:
        """Fetch trending topic and convert to story candidate."""
        llm_fn = generate_text if has_llm_credentials() else None
        trending = self._trend_engine.discover(llm_fn=llm_fn, count=3)

        if not trending:
            log.info("No trending topics found")
            return None

        # Pick the best fit for our bucket
        for trend in trending:
            wiki_subject = trend.get("wikipedia_subject", trend["name"])
            log.info("Processing trend: %s (wiki: %s)", trend["name"], wiki_subject)

            # Ask LLM to build a full story arc from this trending person
            topic = self._trend_to_topic(trend, bucket)
            if topic and not self.deduplicator.is_duplicate(topic):
                return topic

        return None

    def _trend_to_topic(self, trend: dict, bucket: ContentBucket) -> Optional[TopicCandidate]:
        """Convert a trending term + Wikipedia extract into a full TopicCandidate."""
        name = trend["name"]
        wiki = trend.get("wikipedia_subject", name)
        extract = trend.get("extract", "")
        hook = trend.get("hook", "")
        why = trend.get("why_trending", "")

        prompt = f"""Convert this trending person/company into a Tamil YouTube story topic.

Subject: {name}
Wikipedia: {wiki}
Context: {extract[:400]}
Why trending now: {why}

Create a compelling biographical story arc. Return ONLY JSON:
{{
  "title_ta": "Tamil YouTube title with emotional hook (max 60 chars)",
  "protagonist": "{name}",
  "protagonist_age": "age at key moment or empty",
  "situation": "specific place + year + context",
  "core_problem": "specific failure or challenge they faced",
  "emotional_hook": "the most dramatic/surprising specific moment",
  "turning_point": "the specific moment things changed",
  "lesson": "what Tamil viewers will take away",
  "hook_question": "compelling question in Tamil (60 chars max)",
  "open_loop": "incomplete sentence creating suspense in Tamil",
  "wikipedia_subject": "{wiki}",
  "story_mode": "biographical",
  "content_bucket": "{bucket.value}",
  "curiosity_score": 8.5,
  "emotion_score": 8.0,
  "story_score": 8.5,
  "lesson_score": 8.0
}}"""

        try:
            raw = generate_text(prompt, max_tokens=800, preferred=preferred_provider_for_stage(STAGE_TOPIC))
            data = extract_json_object(raw)
            if data:
                return _dict_to_topic(data, source="trend")
        except Exception as e:
            log.warning("trend_to_topic failed for %s: %s", name, e)
        return None

    # ── Unchanged methods from original ──────────────────────────────

    def generate_candidates(self, content_bucket, used_titles, count=20):
        count = topic_candidate_count(count)
        if count == 0 or not has_llm_credentials():
            return self._offline_candidate_pool(content_bucket, used_titles)

        bucket_label = content_bucket.value
        story_mode = self._story_mode_for_bucket(content_bucket)
        prompt = f"""You are a YouTube Content Strategist for "துளிர்" Tamil storytelling channel.

QUALITY BAR — your topics must match this level:
- Colonel Sanders: 1009 rejections at 65 → built KFC
- Nokia: #1 phone brand → destroyed by one wrong decision
- APJ Kalam: newspaper boy → India's missile man
- Sundar Pichai: scholarship student → Google CEO

Rules:
- Real people with Wikipedia articles (biographical preferred)
- SPECIFIC: exact year, exact number, exact place, exact failure
- Not generic motivation — real story arc with conflict and turning point
- Tamil audience connection: Indian origin or universal human struggle

Avoid already used:
{self.deduplicator.recent_avoid_list(15)}

Content bucket: {bucket_label}
Generate {count} candidates. Return JSON array:
[{{"title_ta":"...","protagonist":"...","protagonist_age":"...","situation":"...",
"core_problem":"...","emotional_hook":"...","turning_point":"...","lesson":"...",
"hook_question":"...","open_loop":"...","story_mode":"{story_mode.value}",
"content_bucket":"{bucket_label}","wikipedia_subject":"exact Wikipedia title",
"curiosity_score":8.5,"emotion_score":8.0,"story_score":8.5,"lesson_score":7.5}}]"""

        raw = generate_text(prompt, max_tokens=max_tokens_for_stage(STAGE_TOPIC, 2000),
                            preferred=preferred_provider_for_stage(STAGE_TOPIC))
        candidates = [_dict_to_topic(d, source="llm", default_bucket=content_bucket,
                                     default_mode=story_mode)
                      for d in (extract_json_array(raw) or [])]
        return candidates or self._offline_candidate_pool(content_bucket, used_titles)

    def score_and_select(self, candidates):
        cfg = load_topics_config()
        min_score = float(cfg.get("min_accept_score", 7.5))
        blocklist = cfg.get("blocklist_patterns", [])
        valid = [c for c in candidates
                 if not self.deduplicator.is_duplicate(c)
                 and not self._blocked(c, blocklist)
                 and c.total_score >= min_score]
        if not valid:
            valid = [c for c in candidates if not self.deduplicator.is_duplicate(c)]
        if not valid:
            return self._pick_offline_topic(ContentBucket.SUCCESS_FAILURE, [])
        valid.sort(key=lambda t: t.total_score, reverse=True)
        return valid[0]

    def record_topic(self, topic):
        self.deduplicator.record_topic(topic)

    def _discover_with_llm(self, bucket, used_titles):
        candidates = self.generate_candidates(bucket, used_titles)
        if not candidates:
            raise ValueError("No candidates")
        return self.score_and_select(candidates)

    def _pick_content_bucket(self):
        mix = load_topics_config().get("content_mix", {})
        buckets = list(ContentBucket)
        weights = [float(mix.get(b.value, 0.25)) for b in buckets]
        return random.choices(buckets, weights=weights, k=1)[0]

    def _story_mode_for_bucket(self, bucket):
        # Always biographical for better content quality
        return StoryMode.BIOGRAPHICAL

    def _pick_offline_topic(self, bucket, used_titles):
        all_topics = self._load_fallback()
        available = [t for t in all_topics if not self.deduplicator.is_duplicate(t)]
        bucket_topics = [t for t in available if t.content_bucket == bucket]
        pool = bucket_topics or available or all_topics
        return random.choice(pool).model_copy(update={"source": "offline"})

    def _offline_candidate_pool(self, bucket, used_titles):
        return [t for t in self._load_fallback()
                if t.content_bucket == bucket and not self.deduplicator.is_duplicate(t)]

    def _load_fallback(self):
        path = CONFIG_DIR / "fallback_topics.yml"
        if not path.exists():
            return _builtin_fallback()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        topics = [_dict_to_topic(item, source="offline") for item in data.get("topics", [])]
        return topics or _builtin_fallback()

    def _blocked(self, candidate, patterns):
        text = f"{candidate.title_ta} {candidate.hook}".lower()
        return any(p.lower() in text for p in patterns)


def _dict_to_topic(data, source="llm", default_bucket=None, default_mode=None):
    bucket_raw = data.get("content_bucket") or (default_bucket.value if default_bucket else "success_failure")
    mode_raw   = data.get("story_mode") or (default_mode.value if default_mode else "biographical")
    try:    bucket = ContentBucket(bucket_raw)
    except: bucket = ContentBucket.SUCCESS_FAILURE
    try:    mode   = StoryMode(mode_raw)
    except: mode   = StoryMode.BIOGRAPHICAL
    return TopicCandidate(
        title_ta=data.get("title_ta") or data.get("story_title", "Untitled"),
        category=data.get("category", "storytelling"),
        hook=data.get("hook", data.get("hook_question", "")),
        protagonist=data.get("protagonist", "நாயகன்"),
        protagonist_age=str(data.get("protagonist_age", "")),
        situation=data.get("situation", ""),
        core_problem=data.get("core_problem", ""),
        emotional_hook=data.get("emotional_hook", ""),
        turning_point=data.get("turning_point", ""),
        lesson=data.get("lesson", ""),
        hook_question=data.get("hook_question", data.get("hook", "")),
        open_loop=data.get("open_loop", ""),
        story_mode=mode,
        content_bucket=bucket,
        curiosity_score=float(data.get("curiosity_score", 8.0)),
        emotion_score=float(data.get("emotion_score", 8.0)),
        story_score=float(data.get("story_score", 8.0)),
        lesson_score=float(data.get("lesson_score", 7.5)),
        wikipedia_subject=data.get("wikipedia_subject", ""),
        source=source,
    )


def _builtin_fallback():
    return [
        TopicCandidate(
            title_ta="1009 முறை நிராகரிக்கப்பட்ட Colonel Sanders",
            hook="65 வயதில் 1009 முறை தோற்றார். KFC ஆனது.",
            protagonist="Colonel Sanders", protagonist_age="65",
            situation="Kentucky USA 1952",
            core_problem="1009 restaurants rejected his recipe",
            emotional_hook="யாரும் நம்பவில்லை",
            turning_point="1009th attempt — Pete Harman said yes",
            lesson="Age is not the limit. Persistence is the key.",
            hook_question="65 வயதில் எல்லாம் முடிந்தவர் billionaire ஆனது எப்படி?",
            open_loop="ஆனால் 1009வது முறை என்ன நடந்தது?",
            story_mode=StoryMode.BIOGRAPHICAL,
            content_bucket=ContentBucket.SUCCESS_FAILURE,
            wikipedia_subject="Colonel Sanders",
            curiosity_score=9.5, emotion_score=9.0,
            story_score=9.5, lesson_score=8.5, source="offline",
        ),
    ]
