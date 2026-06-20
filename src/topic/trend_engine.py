"""Trend-aware topic discovery engine.

Pipeline:
  1. Google Trends India (pytrends) → get what India is searching today
  2. Filter: only people/companies/events that have Wikipedia articles
  3. Score against channel fit (biographical, story arc, Tamil relevance)
  4. Cross-check dedup history → skip already-used topics
  5. Fetch Wikipedia to confirm story quality before committing

Fallback chain:
  pytrends → LLM trend oracle → curated fallback bank
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Topics that are trending but NOT suitable for storytelling
# Content bible: avoid news events, politics, war, sports scores
TREND_BLOCKLIST = [
    # Sports/entertainment (low story potential)
    "cricket", "ipl", "match", "score", "movie", "trailer",
    "song", "album", "singer", "actor", "actress", "serial",
    # News/current events (not evergreen)
    "war", "attack", "bomb", "killed", "died", "death", "accident",
    "flood", "earthquake", "fire", "protest", "arrested", "riot",
    "election", "vote", "poll", "party", "minister", "government",
    "iran", "israel", "ukraine", "russia", "pakistan", "china war",
    # Financial tickers
    "stock", "share", "price", "rate", "weather", "forecast",
    "sensex", "nifty", "bitcoin", "crypto",
    # Too generic
    "news", "today", "live", "breaking", "update", "latest",
]

# Wikipedia articles that are clearly suitable for storytelling
STORY_SIGNALS = [
    "founder", "ceo", "entrepreneur", "scientist", "inventor",
    "athlete", "player", "director", "reformer", "pioneer",
    "freedom fighter", "activist", "philosopher",
    "founded", "invented", "discovered", "created", "built",
    "failed", "rejected", "bankrupt", "struggled", "overcame",
    "million", "billion", "crore", "first", "only", "youngest",
    "despite", "although", "however", "eventually", "finally",
]

# Score minimum raised — content bible requires 8+
SCORE_THRESHOLD = 6.8  # slightly lower for trend pass, LLM will re-score

# Keywords that signal a GOOD story topic (person has overcome something)
STORY_SIGNALS = [
    "founder", "ceo", "entrepreneur", "scientist", "inventor",
    "athlete", "player", "director", "singer", "actor",
    "freedom fighter", "leader", "reformer", "pioneer",
    "poor", "struggled", "rejected", "built", "created",
]


def _fetch_google_trends_india() -> list[str]:
    """Fetch today's trending searches in India via pytrends."""
    try:
        from pytrends.request import TrendReq
        # method_whitelist removed in urllib3 >=2.0 — use requests_kwargs
        try:
            pt = TrendReq(hl="en-IN", tz=330, timeout=(15, 30), retries=2,
                          requests_kwargs={"verify": True})
        except TypeError:
            pt = TrendReq(hl="en-IN", tz=330, timeout=(15, 30))
        df = pt.trending_searches(pn="india")
        trends = df[0].tolist()
        log.info("Google Trends India: %d trending topics", len(trends))
        return trends[:25]
    except Exception as e:
        log.warning("pytrends failed: %s — using Wikipedia only", e)
        return []


def _fetch_google_trends_tamil() -> list[str]:
    """Fetch real-time trending in Tamil Nadu specifically."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="ta", tz=330, timeout=(15, 30))
        # Tamil Nadu geo code
        df = pt.trending_searches(pn="india")  # pytrends doesn't support state-level
        return df[0].tolist()[:15]
    except Exception as e:
        log.warning("Tamil trends failed: %s", e)
        return []


def _fetch_wikipedia_pageviews_trending() -> list[str]:
    """Get Wikipedia's most-viewed articles (proxy for what people are searching)."""
    try:
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y/%m/%d")
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{yesterday}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "ThulirBot/1.0 (Tamil storytelling channel)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        articles = data["items"][0]["articles"]
        # Filter out non-person/non-company articles
        names = []
        skip_prefixes = ["Main_Page", "Special:", "Wikipedia:", "Portal:", "List_of",
                         "Deaths_in", "2026_in", "United_States", "India_national"]
        for a in articles[:50]:
            title = a["article"].replace("_", " ")
            if any(title.startswith(p) for p in skip_prefixes):
                continue
            names.append(title)
        log.info("Wikipedia trending: %d articles", len(names))
        return names[:20]
    except Exception as e:
        log.warning("Wikipedia trending failed: %s", e)
        return []


def _is_story_worthy(term: str) -> bool:
    """Check if a trending term could be a good storyline topic."""
    tl = term.lower()
    # Blocklist check — content bible says avoid news/politics/sports
    if any(b in tl for b in TREND_BLOCKLIST):
        return False
    # Too short (abbreviations, codes)
    if len(term.replace(" ","")) < 4:
        return False
    # Pure number (year, date)
    if term.strip().replace(" ","").isdigit():
        return False
    # Must look like a person name or company (capitalized) OR have a story signal
    words = term.split()
    is_proper_noun = any(w[0].isupper() for w in words if w)
    has_story_signal = any(s in tl for s in STORY_SIGNALS[:8])
    return is_proper_noun or has_story_signal


def _has_wikipedia(term: str) -> Optional[str]:
    """Check if term has a Wikipedia article. Returns article title or None."""
    try:
        encoded = urllib.parse.quote(term.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract", "")
        if len(extract) < 100:
            return None
        return data.get("title", term)
    except Exception:
        return None


def _score_topic_fit(term: str, wiki_extract: str) -> float:
    """Score how well this topic fits the channel (0-10)."""
    score = 5.0
    text = (term + " " + wiki_extract).lower()

    # Story signals
    for signal in STORY_SIGNALS:
        if signal in text:
            score += 0.4

    # Indian connection (Tamil audience)
    india_signals = ["india", "indian", "tamil", "chennai", "mumbai", "delhi",
                     "bangalore", "kerala", "gujarat", "punjab"]
    for s in india_signals:
        if s in text:
            score += 0.5
            break

    # Has clear failure/struggle narrative
    failure_signals = ["failed", "rejected", "struggled", "poor", "bankrupt",
                       "fired", "dropped", "lost", "crisis", "despite"]
    for s in failure_signals:
        if s in text:
            score += 0.8
            break

    # Has specific numbers (makes story concrete)
    if re.search(r"\b\d{4}\b", wiki_extract):  # has year
        score += 0.5
    if re.search(r"\$|₹|million|billion|crore|lakh", wiki_extract, re.I):
        score += 0.5

    return min(score, 10.0)


def _llm_trend_oracle(used_topics: list[str], llm_fn) -> list[dict]:
    """Use LLM as trend oracle when pytrends fails."""
    avoid = ", ".join(used_topics[-15:]) if used_topics else "none"
    prompt = f"""You are a Tamil YouTube content strategist for "துளிர்" — a biographical storytelling channel.

Today's date: {datetime.utcnow().strftime("%B %d, %Y")}

Generate 10 trending biographical story topics that would perform well on Tamil YouTube right now.
Focus on: Indian entrepreneurs, historical figures, scientists, business failures/comebacks.

Requirements:
- Each must be a REAL person or company with Wikipedia article
- Must have: specific failure + specific turning point + specific achievement
- Must be currently relevant or timeless (not outdated)
- Tamil audience connects with: Indian origin, struggle story, specific numbers
- Already used (avoid these): {avoid}

Return JSON array:
[{{
  "name": "Person/Company name",
  "wikipedia_subject": "Exact English Wikipedia article title",
  "why_trending": "Why this is relevant now",
  "hook": "One sentence dramatic hook in Tamil",
  "story_signal": "The key dramatic moment",
  "tamil_relevance": "Why Tamil audience will connect"
}}]"""

    try:
        raw = llm_fn(prompt, max_tokens=2000)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        log.warning("LLM trend oracle failed: %s", e)
    return []


class TrendEngine:
    """Discovers trending story topics via Google Trends + Wikipedia validation."""

    def __init__(self, history_path: Path) -> None:
        self._history_path = history_path
        self._used: set[str] = self._load_used()

    def _load_used(self) -> set[str]:
        try:
            data = json.loads(self._history_path.read_text())
            return {item.get("protagonist", "") for item in data if item.get("protagonist")}
        except Exception:
            return set()

    def discover(self, llm_fn=None, count: int = 1) -> list[dict]:
        """Return count validated trending topics not yet used."""
        candidates = []

        # 1. Google Trends
        log.info("Fetching Google Trends India...")
        trends = _fetch_google_trends_india()
        time.sleep(1)

        # 2. Wikipedia pageviews as supplement
        log.info("Fetching Wikipedia trending...")
        wiki_trending = _fetch_wikipedia_pageviews_trending()

        all_terms = trends + wiki_trending
        log.info("Total raw candidates: %d", len(all_terms))

        # 3. Filter, validate, score
        seen = set()
        for term in all_terms:
            if term in seen or not _is_story_worthy(term):
                continue
            # Skip already used
            if any(u.lower() in term.lower() or term.lower() in u.lower()
                   for u in self._used):
                log.info("Skipping already used: %s", term)
                continue
            seen.add(term)

            wiki_title = _has_wikipedia(term)
            if not wiki_title:
                continue

            # Get extract for scoring
            try:
                encoded = urllib.parse.quote(wiki_title.replace(" ", "_"))
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
                req = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                extract = data.get("extract", "")
            except Exception:
                extract = ""

            score = _score_topic_fit(term, extract)
            if score >= 6.5:
                candidates.append({
                    "name": term,
                    "wikipedia_subject": wiki_title,
                    "score": score,
                    "extract": extract[:300],
                })
                log.info("Candidate: %s (score=%.1f)", term, score)

            time.sleep(0.3)  # rate limit Wikipedia
            if len(candidates) >= count * 3:
                break

        # 4. Fallback to LLM oracle if not enough
        if len(candidates) < count and llm_fn:
            log.info("Not enough from trends — using LLM oracle")
            llm_topics = _llm_trend_oracle(list(self._used), llm_fn)
            for t in llm_topics:
                wiki = t.get("wikipedia_subject", "")
                if wiki and not any(u.lower() in wiki.lower() for u in self._used):
                    candidates.append({
                        "name": t.get("name", wiki),
                        "wikipedia_subject": wiki,
                        "score": 8.0,
                        "hook": t.get("hook", ""),
                        "why_trending": t.get("why_trending", ""),
                    })

        # Sort by score, return top N
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:count]
