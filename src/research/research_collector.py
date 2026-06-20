"""Research collection — deep Wikipedia extraction + fact synthesis.

Strategy:
  1. Fetch Wikipedia full article (not just summary)
  2. Extract specific: dates, numbers, quotes, turning points, failures
  3. LLM synthesizes story facts ONLY from Wikipedia text — no invention
  4. Result: every fact in the script is real and verifiable
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import List

from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_policy import STAGE_RESEARCH, should_use_llm
from src.core.models import ResearchBrief, StoryMode, TopicCandidate

log = logging.getLogger(__name__)

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKI_EXTRACT_API = "https://en.wikipedia.org/w/api.php?action=query&titles={}&prop=extracts&exintro=0&explaintext=1&format=json"



def _transliterate_for_script(text: str) -> str:
    """Transliterate common English proper nouns to Tamil phonetics
    so the LLM script uses Tamil versions naturally."""
    import re
    replacements = [
        (r"\bIIT Kharagpur\b", "ஐஐடி கரக்பூர்"),
        (r"\bIIT\b", "ஐஐடி"), (r"\bStanford\b", "ஸ்டான்போர்டு"),
        (r"\bHarvard\b", "ஹார்வர்டு"), (r"\bYale\b", "யேல்"),
        (r"\bGoogle\b", "கூகுள்"), (r"\bApple\b", "ஆப்பிள்"),
        (r"\bMicrosoft\b", "மைக்ரோசாஃப்ட்"), (r"\bAmazon\b", "அமேசான்"),
        (r"\bNokia\b", "நோக்கியா"), (r"\bKodak\b", "கோடாக்"),
        (r"\bMBA\b", "எம்பிஏ"), (r"\bCEO\b", "தலைமை நிர்வாகி"),
        (r"\bscholarship\b", "உதவித்தொகை"),
        (r"\bKentucky\b", "கென்டக்கி"), (r"\bFinland\b", "ஃபின்லாந்து"),
        (r"\bGujarat\b", "குஜராத்"), (r"\bChennai\b", "சென்னை"),
        (r"\bMumbai\b", "மும்பை"), (r"\bDelhi\b", "தில்லி"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def _fetch_wiki_text(subject: str) -> str:
    """Fetch full Wikipedia article text (not just intro)."""
    try:
        encoded = urllib.parse.quote(subject.replace(" ", "_"))
        url = WIKI_EXTRACT_API.format(encoded)
        req = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0 Tamil storytelling"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            text = page.get("extract", "")
            if text and len(text) > 200:
                return text[:8000]  # first 8000 chars is enough
    except Exception as exc:
        log.warning("Wikipedia full text failed for %s: %s", subject, exc)

    # Fallback: summary API
    try:
        encoded = urllib.parse.quote(subject.replace(" ", "_"))
        url = WIKI_SUMMARY_API.format(encoded)
        req = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("extract", "")
    except Exception as exc:
        log.warning("Wikipedia summary also failed: %s", exc)
        return ""


def _extract_facts_from_text(text: str, subject: str) -> dict:
    """Extract structured facts directly from Wikipedia text."""
    dates    = list(dict.fromkeys(re.findall(r"\b(1[89]\d{2}|20\d{2})\b", text)))[:8]
    numbers  = list(dict.fromkeys(re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", text)))[:10]
    # Extract sentences with strong story signals
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]
    # Score sentences for story value
    story_keywords = ["failed", "rejected", "left", "founded", "started", "died", "born",
                      "million", "billion", "first", "only", "despite", "although",
                      "however", "eventually", "finally", "decided", "refused"]
    scored = []
    for s in sentences:
        score = sum(1 for kw in story_keywords if kw.lower() in s.lower())
        scored.append((score, s))
    scored.sort(reverse=True)
    story_facts = [s for _, s in scored[:10]]
    return {
        "facts": sentences[:5],
        "story_facts": story_facts,
        "dates": dates,
        "numbers": numbers,
    }


def _llm_synthesize_from_wiki(
    wiki_text: str,
    topic: TopicCandidate,
) -> ResearchBrief:
    """Use LLM to extract story-relevant facts from Wikipedia text.
    CRITICAL: LLM must only use facts present in the Wikipedia text.
    """
    prompt = f"""You are extracting story facts for a Tamil YouTube storytelling video.
Wikipedia article text (USE ONLY THIS — do not invent):
---
{wiki_text[:4000]}
---

Subject: {topic.protagonist}

Extract ONLY facts present in the text above. Do not add, invent, or assume anything.
Return JSON:
{{
  "story_facts": [
    "8 specific sentences from the Wikipedia text that are most story-relevant",
    "Include: exact years, exact numbers, specific failures, specific turning points",
    "Each fact must be directly verifiable from the text above"
  ],
  "dates": ["list of important years from the text"],
  "locations": ["specific places mentioned"],
  "key_numbers": ["specific numbers: ages, amounts, counts"],
  "hook_moment": "The single most dramatic/surprising fact from this text",
  "failure_moment": "The biggest failure or setback mentioned",
  "turning_point": "The moment things changed",
  "achievement": "The main achievement or legacy"
}}

Return ONLY JSON. No markdown."""

    raw = generate_text(prompt, max_tokens=1500)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    data = json.loads(match.group())
    return ResearchBrief(
        topic=topic.protagonist,
        facts=data.get("story_facts", [])[:5],
        story_facts=data.get("story_facts", []),
        dates=data.get("dates", []),
        locations=data.get("locations", []),
        figures=[topic.protagonist],
        timeline=data.get("dates", []),
        key_numbers=data.get("key_numbers", []),
        sources=["Wikipedia: " + topic.wikipedia_subject],
    )


class ResearchCollector:
    def collect(self, topic: TopicCandidate) -> ResearchBrief:
        wiki_subject = topic.wikipedia_subject or topic.protagonist

        # Always try Wikipedia for biographical stories
        if topic.story_mode == StoryMode.BIOGRAPHICAL or wiki_subject:
            wiki_text = _fetch_wiki_text(wiki_subject)
            if wiki_text and len(wiki_text) > 300:
                log.info("Wikipedia text fetched: %d chars for %s", len(wiki_text), wiki_subject)

                # Extract facts directly from text
                raw_facts = _extract_facts_from_text(wiki_text, wiki_subject)

                # Use LLM to synthesize story-relevant facts from Wikipedia
                if has_llm_credentials() and should_use_llm(STAGE_RESEARCH):
                    try:
                        brief = _llm_synthesize_from_wiki(wiki_text, topic)
                        if brief:
                            log.info("Research ready: %d story facts from Wikipedia", len(brief.story_facts))
                            return brief
                    except Exception as exc:
                        log.warning("LLM synthesis failed: %s — using raw extraction", exc)

                # Fallback: use raw extracted facts
                return ResearchBrief(
                    topic=wiki_subject,
                    facts=raw_facts["facts"],
                    story_facts=raw_facts["story_facts"],
                    dates=raw_facts["dates"],
                    figures=[wiki_subject],
                    key_numbers=raw_facts["numbers"],
                    sources=["Wikipedia: " + wiki_subject],
                )

        # Composite stories: LLM research based on topic metadata
        if has_llm_credentials() and should_use_llm(STAGE_RESEARCH):
            try:
                return self._composite_research(topic)
            except Exception as exc:
                log.warning("Composite research failed: %s", exc)

        return self._offline_brief(topic)

    def _composite_research(self, topic: TopicCandidate) -> ResearchBrief:
        """For composite fictional stories, gather real context facts."""
        prompt = f"""Research for Tamil storytelling video.
Protagonist: {topic.protagonist} (fictional character)
Situation: {topic.situation}
Core problem: {topic.core_problem}

Provide REAL contextual facts (not fictional) that ground this story:
- Real statistics about this type of situation in India
- Real average numbers (salary, age, percentages)
- Real psychological/social context

Return JSON:
{{"story_facts": ["5 real facts grounding this story"],
"dates": [], "locations": ["{topic.situation}"],
"key_numbers": ["real relevant numbers"],
"sources": ["source of each fact"]}}"""

        raw = generate_text(prompt, max_tokens=800)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
        return ResearchBrief(
            topic=topic.title_ta,
            facts=data.get("story_facts", [topic.situation]),
            story_facts=data.get("story_facts", [topic.situation, topic.core_problem]),
            key_numbers=data.get("key_numbers", []),
            sources=data.get("sources", ["llm_research"]),
        )

    def _offline_brief(self, topic: TopicCandidate) -> ResearchBrief:
        """Build research brief from topic metadata when Wikipedia unavailable."""
        # Use all available topic fields as story facts
        story_facts = [f for f in [
            topic.emotional_hook,
            topic.situation,
            topic.core_problem,
            topic.turning_point,
            topic.lesson,
            topic.open_loop,
            topic.hook_question,
        ] if f and len(f) > 10]

        # Extract years and numbers from topic fields
        import re
        all_text = " ".join(story_facts)
        dates   = list(dict.fromkeys(re.findall(r"\b(1[89]\d{2}|20\d{2})\b", all_text)))[:5]
        numbers = list(dict.fromkeys(re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", all_text)))[:8]

        return ResearchBrief(
            topic       = topic.title_ta,
            facts       = story_facts[:5],
            story_facts = story_facts,
            dates       = dates,
            figures     = [topic.protagonist],
            key_numbers = numbers,
            sources     = ["topic_metadata"],
        )
