"""Research collection — Wikipedia + LLM + offline fallback."""

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


class ResearchCollector:
    def collect(self, topic: TopicCandidate) -> ResearchBrief:
        if topic.story_mode == StoryMode.BIOGRAPHICAL and topic.wikipedia_subject:
            wiki_brief = self._fetch_wikipedia_brief(topic.wikipedia_subject)
            if wiki_brief:
                return wiki_brief

        if has_llm_credentials() and should_use_llm(STAGE_RESEARCH):
            try:
                return self._collect_with_llm(topic)
            except Exception as exc:
                log.warning("LLM research failed: %s — using offline brief", exc)
        return self._offline_brief(topic)

    def _fetch_wikipedia_brief(self, subject: str) -> ResearchBrief | None:
        try:
            encoded = urllib.parse.quote(subject.replace(" ", "_"))
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            request = urllib.request.Request(url, headers={"User-Agent": "ThulirBot/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            log.warning("Wikipedia fetch failed for %s: %s", subject, exc)
            return None

        extract = data.get("extract", "")
        if not extract:
            return None

        dates = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", extract)
        numbers = re.findall(r"\b\d{1,4}(?:,\d{3})*\b", extract)
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", extract) if sentence.strip()]

        return ResearchBrief(
            topic=subject,
            facts=sentences[:5],
            story_facts=sentences[:8],
            dates=list(dict.fromkeys(dates))[:6],
            locations=[],
            figures=[subject],
            timeline=dates[:4],
            key_numbers=numbers[:6],
            sources=[data.get("content_urls", {}).get("desktop", {}).get("page", "wikipedia.org")],
        )

    def _collect_with_llm(self, topic: TopicCandidate) -> ResearchBrief:
        prompt = f"""Story research for Tamil YouTube storytelling video.

Title: {topic.title_ta}
Protagonist: {topic.protagonist}
Situation: {topic.situation}
Problem: {topic.core_problem}
Mode: {topic.story_mode.value}

Return JSON with story facts (NOT generic tips):
{{"facts":["5 Tamil story facts"],"story_facts":["8 detailed facts for script"],
"dates":["years"],"locations":["places"],"figures":["{topic.protagonist}"],
"timeline":["event order"],"key_numbers":["specific numbers"],"sources":["source"]}}"""
        raw = generate_text(prompt, max_tokens=1200)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
        return ResearchBrief(topic=topic.title_ta, **data)

    def _offline_brief(self, topic: TopicCandidate) -> ResearchBrief:
        facts: List[str] = [
            topic.situation or f"{topic.protagonist} ஒரு உண்மையான கதாபாத்திரம்.",
            topic.core_problem or "அவர் ஒரு பெரிய சவாலை எதிர்கொண்டார்.",
            topic.emotional_hook or "ஒரு உணர்ச்சி நிறைந்த தருணம் அவரை மாற்றியது.",
            topic.turning_point or "ஒரு திருப்புமுனை வந்தது.",
            topic.lesson or "இந்த கதை ஒரு முக்கிய பாடத்தை கற்பிக்கிறது.",
        ]
        numbers = re.findall(r"\d+", f"{topic.situation} {topic.title_ta}")
        return ResearchBrief(
            topic=topic.title_ta,
            facts=facts,
            story_facts=facts,
            figures=[topic.protagonist],
            key_numbers=numbers,
            sources=["offline_template"],
        )
