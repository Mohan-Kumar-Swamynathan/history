"""Topic discovery and scoring — Thulir storytelling channel."""

from __future__ import annotations

import json
import logging
import random
import re
from typing import List, Optional

import yaml

from src.core.config_loader import CONFIG_DIR, get_output_dir, load_topics_config
from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_policy import STAGE_TOPIC, max_tokens_for_stage, should_use_llm, topic_candidate_count
from src.core.models import ContentBucket, StoryMode, TopicCandidate
from src.topic.topic_deduplicator import TopicDeduplicator

log = logging.getLogger(__name__)

ROTATION_FILE = get_output_dir() / "state" / "content_mix_rotation.json"


class TopicScorer:
    def __init__(self) -> None:
        self.deduplicator = TopicDeduplicator()

    def discover_topic(
        self,
        category: Optional[str] = None,
        content_bucket: Optional[ContentBucket] = None,
    ) -> TopicCandidate:
        topics_config = load_topics_config()
        used_titles = self.deduplicator.load_used_titles()
        target_bucket = content_bucket or self._pick_content_bucket()

        if has_llm_credentials() and should_use_llm(STAGE_TOPIC):
            try:
                return self._discover_with_llm(target_bucket, used_titles)
            except Exception as exc:
                log.warning("LLM topic discovery failed: %s — using offline topic", exc)

        return self._pick_offline_topic(target_bucket, used_titles)

    def generate_candidates(
        self,
        content_bucket: ContentBucket,
        used_titles: List[str],
        count: int = 20,
    ) -> List[TopicCandidate]:
        count = topic_candidate_count(count)
        if count == 0 or not has_llm_credentials():
            return self._offline_candidate_pool(content_bucket, used_titles)

        bucket_label = content_bucket.value
        story_mode = self._story_mode_for_bucket(content_bucket)
        prompt = f"""You are a YouTube Content Strategist for "துளிர்" (Thulir) — Tamil storytelling channel like Almost Everything.

Content bucket: {bucket_label}
Story mode: {story_mode.value}
Generate exactly {count} UNIQUE story topic candidates.

Rules:
- Real STORIES not tips, not generic motivation, not Wikipedia summaries
- Each must have conflict, struggle, turning point, lesson as reward
- Biographical mode: real named person (Kalam, Sanders, Jobs, Murthy, Nokia story, etc.)
- Composite mode: fictional Tamil name in real situation (salary, rejection, anxiety)
- Reject generic titles like "work hard" or "success secrets"

Already used — DO NOT repeat these titles or protagonists:
{self.deduplicator.recent_avoid_list(20)}

Return JSON array of {count} objects:
[{{"title_ta":"...","hook":"...","protagonist":"...","protagonist_age":"...",
"situation":"...","core_problem":"...","emotional_hook":"...","turning_point":"...",
"lesson":"...","hook_question":"...","open_loop":"...",
"story_mode":"{story_mode.value}","content_bucket":"{bucket_label}",
"wikipedia_subject":"English Wikipedia title if biographical else empty",
"curiosity_score":8.5,"emotion_score":8.0,"story_score":8.5,"lesson_score":7.5}}]"""

        raw = generate_text(
            prompt,
            max_tokens=max_tokens_for_stage(STAGE_TOPIC, 1500),
            preferred="gemini",
        )
        candidates = _parse_candidate_array(raw)
        return [self._normalize_candidate(item) for item in candidates if item]

    def score_and_select(self, candidates: List[TopicCandidate]) -> TopicCandidate:
        topics_config = load_topics_config()
        min_score = float(topics_config.get("min_accept_score", 7.5))
        blocklist = topics_config.get("blocklist_patterns", [])
        used_titles = self.deduplicator.load_used_titles()

        valid: List[TopicCandidate] = []
        for candidate in candidates:
            if self.deduplicator.is_duplicate(candidate):
                continue
            if candidate.title_ta in used_titles:
                continue
            if self._matches_blocklist(candidate, blocklist):
                continue
            if candidate.total_score < min_score:
                continue
            valid.append(candidate)

        if not valid:
            log.warning("No candidates passed scoring — relaxing to best available")
            valid = [candidate for candidate in candidates if candidate.title_ta not in used_titles]
        if not valid:
            return self._pick_offline_topic(ContentBucket.SUCCESS_FAILURE, used_titles)

        valid.sort(key=lambda topic: topic.total_score, reverse=True)
        winner = valid[0]
        log.info(
            "Selected topic '%s' score=%.2f bucket=%s mode=%s",
            winner.title_ta[:50],
            winner.total_score,
            winner.content_bucket.value,
            winner.story_mode.value,
        )
        return winner

    def record_topic(self, topic: TopicCandidate) -> None:
        self.deduplicator.record_topic(topic)

    def _discover_with_llm(self, bucket: ContentBucket, used_titles: List[str]) -> TopicCandidate:
        count = int(load_topics_config().get("candidate_count", 20))
        candidates = self.generate_candidates(bucket, used_titles, count=count)
        if not candidates:
            raise ValueError("LLM returned no topic candidates")
        return self.score_and_select(candidates)

    def _pick_content_bucket(self) -> ContentBucket:
        topics_config = load_topics_config()
        mix = topics_config.get("content_mix", {})
        buckets = list(ContentBucket)
        weights = [float(mix.get(bucket.value, 0.25)) for bucket in buckets]
        return random.choices(buckets, weights=weights, k=1)[0]

    def _story_mode_for_bucket(self, bucket: ContentBucket) -> StoryMode:
        rotation = load_topics_config().get("story_mode_rotation", "mixed")
        if rotation != "mixed":
            return StoryMode(rotation)
        if bucket in {ContentBucket.SUCCESS_FAILURE, ContentBucket.HISTORICAL_STORY}:
            return StoryMode.BIOGRAPHICAL if random.random() < 0.5 else StoryMode.COMPOSITE
        if bucket == ContentBucket.BUSINESS:
            return StoryMode.BIOGRAPHICAL if random.random() < 0.6 else StoryMode.COMPOSITE
        return StoryMode.COMPOSITE

    def _pick_offline_topic(self, bucket: ContentBucket, used_titles: List[str]) -> TopicCandidate:
        pool = self._offline_candidate_pool(bucket, used_titles)
        if not pool:
            pool = self._load_fallback_topics_from_yaml()
        available = [topic for topic in pool if not self.deduplicator.is_duplicate(topic)] or pool
        chosen = random.choice(available)
        return chosen.model_copy(update={"source": "offline"})

    def _offline_candidate_pool(self, bucket: ContentBucket, used_titles: List[str]) -> List[TopicCandidate]:
        return [
            topic for topic in self._load_fallback_topics_from_yaml()
            if topic.content_bucket == bucket and not self.deduplicator.is_duplicate(topic)
        ]

    def _load_fallback_topics_from_yaml(self) -> List[TopicCandidate]:
        path = CONFIG_DIR / "fallback_topics.yml"
        if not path.exists():
            return _builtin_fallback_topics()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        topics = []
        for item in data.get("topics", []):
            topics.append(_dict_to_topic_candidate(item, source="offline"))
        return topics or _builtin_fallback_topics()

    def _load_used_titles(self) -> List[str]:
        return self.deduplicator.load_used_titles()

    def _matches_blocklist(self, candidate: TopicCandidate, patterns: List[str]) -> bool:
        haystack = f"{candidate.title_ta} {candidate.hook} {candidate.lesson}".lower()
        for pattern in patterns:
            if pattern.lower() in haystack:
                return True
        return False

    def _normalize_candidate(self, data: dict) -> TopicCandidate:
        return _dict_to_topic_candidate(data, source="llm")


def _dict_to_topic_candidate(data: dict, source: str) -> TopicCandidate:
    bucket_raw = data.get("content_bucket", "success_failure")
    mode_raw = data.get("story_mode", "composite")
    try:
        bucket = ContentBucket(bucket_raw)
    except ValueError:
        bucket = ContentBucket.SUCCESS_FAILURE
    try:
        mode = StoryMode(mode_raw)
    except ValueError:
        mode = StoryMode.COMPOSITE

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


def _parse_candidate_array(raw: str) -> List[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    return json.loads(match.group())


def _builtin_fallback_topics() -> List[TopicCandidate]:
    return [
        TopicCandidate(
            title_ta="1009 முறை நிராகரிக்கப்பட்ட Colonel Sanders-ன் கதை",
            hook="65 வயதில் அவர் எல்லாவற்றையும் இழந்தார். ஆனால் நடந்தது யாரும் எதிர்பார்க்கவில்லை.",
            protagonist="Colonel Sanders",
            protagonist_age="65",
            situation="Kentucky, USA — சிறு roadside restaurant",
            core_problem="1009 முறை investors அவரை நிராகரித்தனர்",
            emotional_hook="வயதானதால் யாரும் அவரை நம்பவில்லை",
            turning_point="1009வது முயற்சியில் KFC உருவானது",
            lesson="தோல்வி ஒரு முடிவு அல்ல — ஒரு திருப்புமுனை",
            hook_question="65 வயதில் எல்லாம் முடிந்துவிட்டதா என்று நினைத்தவர் எப்படி பில்லியனர் ஆனார்?",
            open_loop="ஆனால் அடுத்து நடந்தது யாரும் எதிர்பார்க்கவில்லை...",
            story_mode=StoryMode.BIOGRAPHICAL,
            content_bucket=ContentBucket.SUCCESS_FAILURE,
            wikipedia_subject="Colonel Sanders",
            curiosity_score=9.2,
            emotion_score=8.8,
            story_score=9.5,
            lesson_score=8.5,
            source="offline",
        ),
        TopicCandidate(
            title_ta="₹28,000 சம்பளத்தில் அப்பாவை நம்பிக்கை வைக்க முடியாத அர்ஜுன்",
            hook="உன் சம்பளம் பற்றி யாராவது கேட்கும்போது நீ என்ன சொல்வாய்?",
            protagonist="அர்ஜுன்",
            protagonist_age="24",
            situation="Coimbatore IT job, ₹28,000/month",
            core_problem="அப்பாவின் எதிர்பார்ப்புக்கும் தன் தகுதிக்கும் இடையில் சிக்கினான்",
            emotional_hook="அப்பா கேட்டார் — மகனே உன்னால் சம்பாரிக்க முடியாதா?",
            turning_point="ஒரு தவறிலிருந்து ஒரு மிகப்பெரிய பாடம் கற்றான்",
            lesson="உன் மதிப்பு உன் சம்பளத்தில் இல்லை",
            hook_question="உன் சம்பளம் பற்றி யாராவது கேட்கும்போது நீ என்ன சொல்வாய்?",
            open_loop="ஆனால் அடுத்த வாரம் நடந்தது அவனை முற்றிலும் மாற்றியது...",
            story_mode=StoryMode.COMPOSITE,
            content_bucket=ContentBucket.PSYCHOLOGY,
            curiosity_score=8.5,
            emotion_score=8.7,
            story_score=8.2,
            lesson_score=8.0,
            source="offline",
        ),
        TopicCandidate(
            title_ta="Nokia ஏன் வீழ்ந்தது? ஒரு தவறான முடிவின் கதை",
            hook="2007ல் Nokia உலகின் மிகப்பெரிய மொபைல் நிறுவனமாக இருந்தது. 6 வருடங்களில் எல்லாம் முடிந்தது.",
            protagonist="Nokia",
            protagonist_age="",
            situation="Finland, global mobile market leader 2007",
            core_problem="Smartphone revolution-ஐ ignore செய்தது",
            emotional_hook="Board room-ல் எடுக்கப்பட்ட ஒரு முடிவு",
            turning_point="iPhone launch-க்குப் பிறகும் Symbian-ஐ தொடர்ந்தது",
            lesson="சந்தை மாறும்போது மாறாதவர்கள் வீழ்வார்கள்",
            hook_question="உலகின் #1 company எப்படி 6 வருடங்களில் மறைந்தது?",
            open_loop="ஆனால் அந்த ஒரு meeting-ல் என்ன நடந்தது தெரியுமா?",
            story_mode=StoryMode.BIOGRAPHICAL,
            content_bucket=ContentBucket.BUSINESS,
            wikipedia_subject="Nokia",
            curiosity_score=9.0,
            emotion_score=7.5,
            story_score=9.0,
            lesson_score=8.5,
            source="offline",
        ),
    ]
