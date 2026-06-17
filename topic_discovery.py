#!/usr/bin/env python3
"""Discover trending Tamil history topics from Wikipedia On This Day and news RSS."""

import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

from llm_client import generate_text

log = logging.getLogger(__name__)

WIKIPEDIA_FEEDS = [
    "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month:02d}/{day:02d}",
    "https://ta.wikipedia.org/api/rest_v1/feed/onthisday/events/{month:02d}/{day:02d}",
]
NEWS_RSS_URL = (
    "https://news.google.com/rss/search?"
    "q=Tamil+history+OR+India+history+OR+Tamil+Nadu+history&hl=en-IN&gl=IN&ceid=IN:en"
)
VALID_HOOKS = {
    "mystery", "architecture", "rebellion", "literature", "trade",
    "temple", "conflict", "empire", "tragedy", "emotion",
    "engineering", "culture",
}

TOPIC_PICK_PROMPT = """நீங்கள் "வரலாறு விழிப்பு" Tamil History YouTube channel-க்கு இன்றைய video topic தேர்வு செய்கிறீர்கள்.

Today's date: {date}
Recent topics already covered (do NOT repeat): {used_topics}
Candidate events/headlines:
{candidates}

Pick ONE compelling Tamil history YouTube topic. Prefer Tamil Nadu / Tamil diaspora / South Indian relevance.
If a candidate fits, adapt it into an engaging Tamil title. If none fit, invent a fresh original topic.

Return JSON only (no markdown):
{{"topic":"Tamil title under 80 chars","era":"Tamil era label","hook":"one of: mystery|architecture|rebellion|literature|trade|temple|conflict|empire|tragedy|emotion|engineering|culture","source":"wikipedia|news|llm_generated","reason":"one sentence"}}"""

TOPIC_RETRY_PROMPT = """The topic "{duplicate_topic}" was already covered recently.

Today's date: {date}
Topics to avoid: {used_topics}
Candidates:
{candidates}

Invent a NEW original Tamil history topic not in the avoid list.
Return JSON only:
{{"topic":"Tamil title","era":"Tamil era label","hook":"mystery|architecture|rebellion|literature|trade|temple|conflict|empire|tragedy|emotion|engineering|culture","source":"llm_generated","reason":"one sentence"}}"""


def _http_get_json(url: str, timeout: int = 20) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "VaralaruVizhippuBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "VaralaruVizhippuBot/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_on_this_day_events(month: int, day: int) -> List[str]:
    """Fetch historical events for today's date from English and Tamil Wikipedia."""
    events: List[str] = []
    for template in WIKIPEDIA_FEEDS:
        url = template.format(month=month, day=day)
        try:
            data = _http_get_json(url)
            for entry in data.get("events", [])[:15]:
                text = entry.get("text", "").strip()
                year = entry.get("year", "")
                if text:
                    label = f"{year}: {text}" if year else text
                    events.append(label)
        except Exception as exc:
            log.warning(f"Wikipedia fetch failed ({url}): {exc}")
    return _dedupe_preserve_order(events)[:20]


def fetch_history_headlines() -> List[str]:
    """Fetch recent history headlines from Google News RSS."""
    headlines: List[str] = []
    try:
        xml_text = _http_get_text(NEWS_RSS_URL)
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            if title:
                headlines.append(title)
    except Exception as exc:
        log.warning(f"News RSS fetch failed: {exc}")
    return headlines


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _parse_topic_json(raw: str) -> Optional[Dict]:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

    topic = data.get("topic", "").strip()
    if not topic:
        return None

    hook = data.get("hook", "mystery").strip().lower()
    if hook not in VALID_HOOKS:
        hook = "mystery"

    return {
        "topic": topic,
        "era": data.get("era", "வரலாற்று காலம்").strip(),
        "hook": hook,
        "source": data.get("source", "llm_generated").strip(),
        "reason": data.get("reason", "").strip(),
    }


def _is_duplicate(topic: str, used_topics: List[str]) -> bool:
    normalized = topic.strip().lower()
    for used in used_topics:
        if used.strip().lower() == normalized:
            return True
    return False


def _ask_llm_for_topic(prompt: str) -> Optional[Dict]:
    try:
        raw = generate_text(prompt, max_tokens=1024)
        return _parse_topic_json(raw)
    except Exception as exc:
        log.warning(f"LLM topic pick failed: {exc}")
        return None


def pick_trending_topic(used_topics: List[str]) -> Dict:
    """Discover today's trending Tamil history topic via hybrid sources + LLM."""
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")

    wiki_events = fetch_on_this_day_events(now.month, now.day)
    news_headlines = fetch_history_headlines()
    candidates = _dedupe_preserve_order(wiki_events + news_headlines)

    if not candidates:
        candidates = ["No external candidates — invent a compelling Tamil history topic for today."]

    candidate_block = "\n".join(f"- {c}" for c in candidates[:20])
    used_block = "\n".join(f"- {t}" for t in used_topics[-30:]) if used_topics else "(none)"

    prompt = TOPIC_PICK_PROMPT.format(
        date=date_str,
        used_topics=used_block,
        candidates=candidate_block,
    )
    topic = _ask_llm_for_topic(prompt)

    if topic and _is_duplicate(topic["topic"], used_topics):
        log.info(f"Duplicate topic detected: {topic['topic']}, retrying with LLM invent")
        retry_prompt = TOPIC_RETRY_PROMPT.format(
            duplicate_topic=topic["topic"],
            date=date_str,
            used_topics=used_block,
            candidates=candidate_block,
        )
        topic = _ask_llm_for_topic(retry_prompt)

    if not topic:
        topic = {
            "topic": f"இன்றைய தமிழ் வரலாற்று நிகழ்வு — {now.strftime('%B %d')}",
            "era": "வரலாற்று காலம்",
            "hook": "mystery",
            "source": "llm_generated",
            "reason": "Fallback topic when discovery sources and LLM parsing failed",
        }

    log.info(f"Discovered topic [{topic.get('source')}]: {topic['topic']}")
    return topic
