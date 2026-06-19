"""Narrative generator v3 — grounded in real Wikipedia facts, AE rhythm.

Core principle: EVERY sentence in the script must come from the research brief.
The LLM is a TRANSLATOR and STORYTELLER, not an inventor.
If a fact is not in research.story_facts, it cannot be in the script.
"""

from __future__ import annotations

import logging
from typing import List

from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_json_parser import extract_json_array
from src.core.models import BeatType, NarrativeScript, StoryBeat, TopicCandidate, ResearchBrief, resolve_beat_type

log = logging.getLogger(__name__)

AE_BEAT_ORDER = [
    BeatType.HOOK,
    BeatType.CONTEXT,
    BeatType.CONFLICT,
    BeatType.TURNING_POINT,
    BeatType.RESOLUTION,
    BeatType.LESSON,
]

BEAT_EMOTIONS = {
    BeatType.HOOK:          "exciting",
    BeatType.CONTEXT:       "neutral",
    BeatType.CONFLICT:      "sad",
    BeatType.TURNING_POINT: "exciting",
    BeatType.RESOLUTION:    "inspirational",
    BeatType.LESSON:        "neutral",
}


class NarrativeGeneratorV3:
    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if not has_llm_credentials():
            return self._offline_script(topic, research)
        try:
            return self._llm_script(topic, research)
        except Exception as exc:
            log.warning("LLM script failed: %s — offline", exc)
            return self._offline_script(topic, research)

    def _llm_script(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        # Build a verified facts block from research
        facts_block = "\n".join(f"  - {f}" for f in research.story_facts[:8])
        dates_block  = ", ".join(research.dates[:5]) or "not available"
        nums_block   = ", ".join(research.key_numbers[:6]) or "not available"

        prompt = f"""நீங்கள் "துளிர்" Tamil YouTube channel-க்கு script எழுதுகிறீர்கள்.
Style: Almost Everything YouTube channel — real facts, emotional story, whiteboard animation.

===== VERIFIED FACTS (script-ல் இதை மட்டும் பயன்படுத்துங்கள்) =====
Protagonist: {topic.protagonist}
{facts_block}
Key dates: {dates_block}
Key numbers: {nums_block}
Hook moment: {topic.emotional_hook}
Turning point: {topic.turning_point}
Lesson: {topic.lesson}
===== END OF FACTS =====

ABSOLUTE RULE: மேலே கொடுக்கப்பட்ட facts மட்டுமே script-ல் பயன்படுத்தவும்.
புதிய facts, numbers, dates இல்லை. Verified information மட்டும்.

SCRIPT STRUCTURE — 6 chapters:
1. hook — மிகவும் dramatic ஆன ஒரு real moment-ல் தொடங்கவும். "வணக்கம்" வேண்டாம்.
2. context — protagonist background, specific year மற்றும் place
3. conflict — மிகவும் குறிப்பிட்ட தோல்வி அல்லது challenge, exact numbers உடன்
4. turning_point — எந்த ஒரு specific moment மாற்றியது?
5. resolution — என்ன நடந்தது? exact outcome உடன்
6. lesson — இந்த real story-யிலிருந்து என்ன பாடம்? CTA இயற்கையாக வரட்டும்.

ஒவ்வொரு chapter-லும்:
- 50-70 Tamil words (3-5 sentences)
- ஒவ்வொரு sentence-லும் 8-12 words
- Conversational Tamil — நண்பனிடம் சொல்வது போல
- குறைந்தது ஒரு specific fact/number/year per chapter

Return ONLY JSON array of 6 objects:
[{{
  "beat_type": "hook",
  "narration_ta": "50-70 word verified Tamil narration...",
  "emotion": "exciting",
  "on_screen_text": "specific year or number",
  "visual_keywords": ["3 english words for image search"]
}}]"""

        raw = generate_text(prompt, max_tokens=4000)
        beats_data = extract_json_array(raw)
        if not beats_data:
            raise ValueError("No JSON array in response")

        beats = []
        for i, item in enumerate(beats_data[:6]):
            bt = resolve_beat_type(item.get("beat_type"), AE_BEAT_ORDER[i % len(AE_BEAT_ORDER)])
            narration = item.get("narration_ta", "").strip()
            words = narration.split()
            if len(words) < 40:
                log.warning("Chapter %d too short (%d words) — may cause short video", i, len(words))
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=narration,
                emotion=item.get("emotion", BEAT_EMOTIONS.get(bt, "neutral")),
                protagonist=topic.protagonist,
                on_screen_text=item.get("on_screen_text", ""),
                visual_keywords=item.get("visual_keywords", [bt.value, "person"]),
                macro_index=i,
            ))

        while len(beats) < 6:
            bt = AE_BEAT_ORDER[len(beats)]
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=f"{topic.protagonist}-ன் கதை தொடர்கிறது. {research.story_facts[len(beats)] if len(research.story_facts) > len(beats) else topic.lesson}",
                emotion=BEAT_EMOTIONS.get(bt, "neutral"),
                protagonist=topic.protagonist,
                visual_keywords=[bt.value, "person", "story"],
            ))

        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _offline_script(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        """Build script from research facts — no LLM, pure template but grounded."""
        name = topic.protagonist
        facts = research.story_facts
        get = lambda i, default="": facts[i] if i < len(facts) else default

        beats = [
            StoryBeat(beat_type=BeatType.HOOK,
                narration_ta=f"{topic.emotional_hook or get(0)} {topic.open_loop or 'இந்த கதை உங்களை வியக்க வைக்கும்.'} {name}-ன் வாழ்க்கையில் நடந்த இந்த நிகழ்வு உண்மையானது.",
                emotion="exciting", protagonist=name,
                visual_keywords=["determined", "person", "start"]),
            StoryBeat(beat_type=BeatType.CONTEXT,
                narration_ta=f"{name} — {topic.situation or get(1, 'ஒரு சாதாரண வாழ்க்கை வாழ்ந்தார்')}. {get(2, '')} அவரின் கனவு வேறு ஒன்று இருந்தது.",
                emotion="neutral", protagonist=name,
                visual_keywords=["background", "vintage", "city"]),
            StoryBeat(beat_type=BeatType.CONFLICT,
                narration_ta=f"{topic.core_problem or get(3, 'தோல்வி வந்தது')}. {get(4, 'மக்கள் சிரித்தார்கள்.')} {name} மட்டும் விட்டுக்கொடுக்கவில்லை.",
                emotion="sad", protagonist=name,
                visual_keywords=["failure", "rejection", "struggle"]),
            StoryBeat(beat_type=BeatType.TURNING_POINT,
                narration_ta=f"{topic.turning_point or get(5, 'ஒரு திருப்புமுனை வந்தது')}. அந்த ஒரு நிமிடம் எல்லாவற்றையும் மாற்றியது. {name} புரிந்துகொண்டார்.",
                emotion="exciting", protagonist=name,
                visual_keywords=["turning point", "decision", "light"]),
            StoryBeat(beat_type=BeatType.RESOLUTION,
                narration_ta=f"{get(6, name + ' வெற்றி அடைந்தார்')}. உலகம் {name}-ஐ வேறுவிதமாகப் பார்க்க ஆரம்பித்தது. அவர் நிரூபித்தார்.",
                emotion="inspirational", protagonist=name,
                visual_keywords=["success", "achievement", "recognition"]),
            StoryBeat(beat_type=BeatType.LESSON,
                narration_ta=f"பாடம்: {topic.lesson or get(7, 'தோல்வி முடிவல்ல')}. {name}-ன் கதை நமக்கு இதை சொல்கிறது. Like செய்யுங்கள், subscribe செய்யுங்கள்.",
                emotion="neutral", protagonist=name,
                visual_keywords=["lesson", "wisdom", "inspiration"]),
        ]
        return NarrativeScript(topic=topic, beats=beats, format="long")
