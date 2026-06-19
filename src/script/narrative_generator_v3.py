"""Narrative generator v3 — AE rhythm, 6 chapters, 50-70 words each.

AE structure (corrected):
  - 6 chapters: hook, rise, conflict, turning_point, resolution, lesson
  - Each chapter = 3-5 short Tamil sentences = 50-70 words
  - Short sentences (8-12 words each) separated by periods
  - One Pexels image per chapter
  - Total ~360-420 words = ~4.5-5 min at Tamil speech pace
  - Specific: exact year, age, place, number in every chapter
"""

from __future__ import annotations

import logging
from typing import List

from src.core.config_loader import load_topics_config
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

MAX_ATTEMPTS = 2


class NarrativeGeneratorV3:
    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if not has_llm_credentials():
            return self._offline_script(topic)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                script = self._llm_script(topic, research)
                log.info("Script: %d beats, total words: %d",
                    len(script.beats),
                    sum(len(b.narration_ta.split()) for b in script.beats))
                return script
            except Exception as exc:
                log.warning("LLM attempt %d failed: %s", attempt, exc)
        return self._offline_script(topic)

    def _llm_script(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        facts   = research.story_facts[:8]
        dates   = research.dates[:4]
        numbers = research.key_numbers[:5]

        prompt = f"""நீங்கள் "துளிர்" Tamil YouTube channel-க்கு script எழுதுகிறீர்கள்.
Style: Almost Everything YouTube channel — real story, whiteboard animation.

TOPIC: {topic.title_ta}
Protagonist: {topic.protagonist} (age: {topic.protagonist_age})
Core problem: {topic.core_problem}
Turning point: {topic.turning_point}
Lesson: {topic.lesson}
Key facts: {facts}
Key dates: {dates}
Key numbers: {numbers}

STRUCTURE: Exactly 6 chapters in order: hook, context, conflict, turning_point, resolution, lesson

RULES FOR EACH CHAPTER:
1. narration_ta: Write 3-5 short Tamil sentences. Total 50-70 Tamil words per chapter.
   - Each sentence: 8-12 words maximum
   - Short, punchy, conversational Tamil (NOT formal essay)
   - Include specific: year OR age OR place OR exact number in every chapter
   - Sentences flow naturally, one building on the next
2. HOOK chapter: Start mid-scene. Drop viewer INTO the story with a specific moment.
   BAD: "வணக்கம்! இன்று ஒரு சுவாரஸ்யமான கதை பார்க்கப் போகிறோம்."
   GOOD: "1980. கென்டக்கியில் ஒரு 66 வயது முதியவர். கையில் ஒரே ஒரு recipe. 1009 கடைகள் அவரை நிராகரித்தன. ஆனால் அவர் விட்டுக்கொடுக்கவில்லை."
3. LESSON chapter: End with natural CTA — like, subscribe, bell — but woven into the lesson, not forced.
4. visual_keywords: 3 English words for image search (specific to that chapter's moment)
5. on_screen_text: 1-4 words shown on screen as callout (number, year, or key phrase)

Target: Total 360-420 Tamil words across all 6 chapters combined.

Return ONLY a JSON array of exactly 6 objects:
[
  {{
    "beat_type": "hook",
    "narration_ta": "50-70 word Tamil narration here with 3-5 sentences...",
    "emotion": "exciting",
    "on_screen_text": "66 வயது",
    "visual_keywords": ["old man", "kitchen", "recipe"]
  }}
]

No markdown. No explanation. JSON array only."""

        raw = generate_text(prompt, max_tokens=4000)
        beats_data = extract_json_array(raw)
        if not beats_data:
            raise ValueError("No JSON array in response")

        beats = []
        for i, item in enumerate(beats_data[:6]):
            bt = resolve_beat_type(item.get("beat_type"), AE_BEAT_ORDER[i % len(AE_BEAT_ORDER)])
            narration = item.get("narration_ta", "").strip()
            words = narration.split()
            # Must have at least 40 words — if LLM was stingy, flag it
            if len(words) < 40:
                log.warning("Beat %d too short: %d words", i, len(words))
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=narration,
                emotion=item.get("emotion", BEAT_EMOTIONS.get(bt, "neutral")),
                protagonist=topic.protagonist,
                on_screen_text=item.get("on_screen_text", ""),
                visual_keywords=item.get("visual_keywords", [bt.value]),
                macro_index=i,
            ))

        while len(beats) < 6:
            bt = AE_BEAT_ORDER[len(beats)]
            beats.append(StoryBeat(
                beat_type=bt,
                narration_ta=f"{topic.protagonist}-ன் கதை தொடர்கிறது. அவர் ஒவ்வொரு நாளும் தன் கனவை நோக்கி நடந்தார்.",
                emotion=BEAT_EMOTIONS.get(bt, "neutral"),
                protagonist=topic.protagonist,
                visual_keywords=[bt.value, "person", "journey"],
            ))

        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _offline_script(self, topic: TopicCandidate) -> NarrativeScript:
        name = topic.protagonist or "அவர்"
        beats = [
            StoryBeat(beat_type=BeatType.HOOK,
                narration_ta=f"இது {name}-ன் கதை. அவர் எல்லாவற்றையும் இழந்தார். ஆனால் அவர் விட்டுக்கொடுக்கவில்லை. இந்த கதை உங்களை வியக்க வைக்கும். கவனமாகக் கேளுங்கள்.",
                emotion="exciting", protagonist=name, visual_keywords=["person", "determined", "start"]),
            StoryBeat(beat_type=BeatType.CONTEXT,
                narration_ta=f"{name} ஒரு சாதாரண குடும்பத்தில் பிறந்தார். வாழ்க்கை எளிதாக இல்லை. ஆனால் அவருக்கு ஒரு கனவு இருந்தது. அந்த கனவை யாரும் புரிந்துகொள்ளவில்லை.",
                emotion="neutral", protagonist=name, visual_keywords=["family", "childhood", "humble"]),
            StoryBeat(beat_type=BeatType.CONFLICT,
                narration_ta=f"தோல்வி மீது தோல்வி வந்தது. மக்கள் சிரித்தார்கள். சிலர் 'விட்டுவிடு' என்று சொன்னார்கள். {name} ஒவ்வொரு நாளும் மீண்டும் எழுந்தார்.",
                emotion="sad", protagonist=name, visual_keywords=["failure", "rejection", "struggle"]),
            StoryBeat(beat_type=BeatType.TURNING_POINT,
                narration_ta=f"ஒரு நாள் எல்லாம் மாறியது. ஒரு சிறிய முடிவு பெரிய வித்தியாசத்தை ஏற்படுத்தியது. {name} புரிந்துகொண்டார் — இனி திரும்பிப் பார்க்க மாட்டார்.",
                emotion="exciting", protagonist=name, visual_keywords=["turning point", "decision", "light"]),
            StoryBeat(beat_type=BeatType.RESOLUTION,
                narration_ta=f"வெற்றி வந்தது. உலகம் {name}-ஐ மதிக்க ஆரம்பித்தது. அவர் நிரூபித்தார் — கனவுகள் பொய்யாவதில்லை.",
                emotion="inspirational", protagonist=name, visual_keywords=["success", "achievement", "celebration"]),
            StoryBeat(beat_type=BeatType.LESSON,
                narration_ta=f"பாடம் என்ன? தோல்வி முடிவல்ல, ஒரு படி மட்டுமே. {name}-ன் கதை நமக்கு இதை சொல்கிறது. இந்த வீடியோ உங்களுக்கு பயனுள்ளதாக இருந்தால் like செய்யுங்கள், subscribe செய்யுங்கள்.",
                emotion="neutral", protagonist=name, visual_keywords=["lesson", "wisdom", "inspiration"]),
        ]
        return NarrativeScript(topic=topic, beats=beats, format="long")
