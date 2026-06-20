"""Script generator — implements content bible storytelling rules.

Structure (mandatory):
  HOOK → SETUP → RISING CONFLICT → TURNING POINT → CLIMAX → AFTERMATH → LESSON

Rules from content director:
  - 1500-2500 words total (8-15 min video)
  - Every 20-30s: new info, twist, question, or conflict
  - First 15s hook: curiosity-driven, never "today we learn..."
  - Conversational Tamil — like telling a friend
  - ONLY verified facts from Wikipedia research
  - Emotional drivers: curiosity, suspense, surprise, fear, hope, triumph
  - 7 beats mapped to structure above
"""

from __future__ import annotations

import logging
import re
from typing import List

from src.core.llm_client import generate_text, has_llm_credentials
from src.core.llm_json_parser import extract_json_array
from src.core.models import (
    BeatType, NarrativeScript, ResearchBrief, StoryBeat,
    TopicCandidate, resolve_beat_type,
)

log = logging.getLogger(__name__)

# 7-beat structure matching content bible
STORY_STRUCTURE = [
    BeatType.HOOK,           # First 15s — pure curiosity, no context
    BeatType.CONTEXT,        # Setup — who, where, when (specific)
    BeatType.CONFLICT,       # Rising conflict — the obstacle, failure begins
    BeatType.ESCALATION,     # Worst point — stakes at maximum
    BeatType.TURNING_POINT,  # The exact moment things changed
    BeatType.RESOLUTION,     # Climax + Aftermath
    BeatType.LESSON,         # Lesson + natural CTA
]

BEAT_EMOTIONS = {
    BeatType.HOOK:          "exciting",
    BeatType.CONTEXT:       "neutral",
    BeatType.CONFLICT:      "sad",
    BeatType.ESCALATION:    "sad",
    BeatType.TURNING_POINT: "exciting",
    BeatType.RESOLUTION:    "inspirational",
    BeatType.LESSON:        "neutral",
}

# Words per beat — total 1500-2500 words across 7 beats = ~200-350 per beat
BEAT_WORDS_MIN = 200
BEAT_WORDS_MAX = 350
BEAT_WORDS_TARGET = 250


SCRIPT_PROMPT = """You are the Script Writer for "துளிர்" Tamil storytelling channel.

Style: Almost Everything, MagnatesMedia, Johnny Harris documentary style — in Tamil.

VERIFIED FACTS (use ONLY these — never invent):
{facts_block}
Key dates: {dates}
Key numbers: {numbers}
Hook fact: {emotional_hook}
Turning point: {turning_point}

SCRIPT STRUCTURE (7 beats, mandatory order):
1. HOOK — First 15 seconds. Curiosity-only. Drop viewer into the story mid-moment.
   MUST NOT start with "வணக்கம்", "நண்பர்களே", "இன்று", "இந்த video"
   MUST start with a NUMBER, a SPECIFIC MOMENT, or a SHOCKING FACT.
   Example: "1009 முறை. அந்த வார்த்தையை மட்டும் அவர் மனதில் திரும்பத் திரும்ப சொல்லிக்கொண்டார்."

2. SETUP — Who is this person? Specific background. One striking detail.
   Include: exact year, exact place, exact age. Make it visual.

3. RISING CONFLICT — The obstacle begins. Specific failure moment.
   New information every 30 seconds. Tension builds. Don't resolve yet.

4. WORST POINT — Everything falls apart. Darkest moment. Stakes maximum.
   Viewer must feel: "How will they ever come back from this?"

5. TURNING POINT — ONE specific moment. Not gradual. Sudden.
   "அந்த ஒரு தெரு. அந்த ஒரு நிமிடம்."

6. RESOLUTION + AFTERMATH — What happened next? Specific outcome.
   Contrast with the worst point. Numbers, scale of change.

7. LESSON + CTA — What does this mean for the viewer?
   Conversational. Personal. Then natural CTA (like, subscribe, bell).

WRITING RULES:
- Each beat: {min_words}-{max_words} Tamil words (3-5 short sentences of 8-12 words each)
- Conversational Tamil — பேசும் style, NOT எழுத்து style
- Every beat: at least one SPECIFIC number, year, or place from the facts
- No invented facts. If fact is uncertain, say "சொல்கிறார்கள்" or "கதை போகிறது"
- Every 30 seconds: introduce new information, twist, or question
- Emotional drivers: curiosity → suspense → shock → fear → hope → triumph

Target total: {target_words} Tamil words across all 7 beats.

Return ONLY JSON array of 7 objects:
[{{
  "beat_type": "hook",
  "narration_ta": "{min_words}-{max_words} word Tamil narration...",
  "emotion": "exciting",
  "on_screen_text": "specific year or number callout",
  "visual_keywords": ["3 specific English image search terms for this exact moment"],
  "retention_hook": "open loop question at end of this beat (optional)"
}}]"""


class NarrativeGeneratorV3:
    def generate(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        if not has_llm_credentials():
            return self._offline_script(topic, research)
        try:
            script = self._llm_script(topic, research)
            total  = sum(len(b.narration_ta.split()) for b in script.beats)
            log.info("Script: %d beats, %d words total", len(script.beats), total)
            if total < 800:
                log.warning("Script too short (%d words) — regenerating", total)
                script = self._llm_script(topic, research)
            return script
        except Exception as exc:
            log.warning("LLM script failed: %s — offline", exc)
            return self._offline_script(topic, research)

    def _llm_script(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        facts_block = "\n".join(f"  • {f}" for f in research.story_facts[:10])
        dates       = ", ".join(research.dates[:5]) or "not available"
        numbers     = ", ".join(research.key_numbers[:6]) or "not available"

        prompt = SCRIPT_PROMPT.format(
            facts_block    = facts_block,
            dates          = dates,
            numbers        = numbers,
            emotional_hook = topic.emotional_hook or research.story_facts[0] if research.story_facts else "",
            turning_point  = topic.turning_point or "",
            min_words      = BEAT_WORDS_MIN,
            max_words      = BEAT_WORDS_MAX,
            target_words   = BEAT_WORDS_TARGET * 7,
        )

        raw       = generate_text(prompt, max_tokens=5000)
        beat_data = extract_json_array(raw)
        if not beat_data:
            raise ValueError("No JSON array from LLM")

        beats = []
        for i, item in enumerate(beat_data[:7]):
            bt  = resolve_beat_type(item.get("beat_type"), STORY_STRUCTURE[i % len(STORY_STRUCTURE)])
            nar = item.get("narration_ta", "").strip()
            wc  = len(nar.split())
            if wc < 150:
                log.warning("Beat %d too short: %d words", i, wc)
            beats.append(StoryBeat(
                beat_type       = bt,
                narration_ta    = nar,
                emotion         = item.get("emotion", BEAT_EMOTIONS.get(bt, "neutral")),
                protagonist     = topic.protagonist,
                on_screen_text  = item.get("on_screen_text", ""),
                visual_keywords = item.get("visual_keywords", [bt.value, "person"]),
                retention_hook  = item.get("retention_hook", ""),
                open_loop       = item.get("retention_hook", ""),
                macro_index     = i,
            ))

        # Pad to 7 if LLM returned fewer
        while len(beats) < 7:
            bt = STORY_STRUCTURE[len(beats)]
            facts = research.story_facts
            fi    = len(beats)
            beats.append(StoryBeat(
                beat_type       = bt,
                narration_ta    = facts[fi] if fi < len(facts) else f"{topic.protagonist}: {bt.value}.",
                emotion         = BEAT_EMOTIONS.get(bt, "neutral"),
                protagonist     = topic.protagonist,
                visual_keywords = [bt.value, "person", "story"],
                macro_index     = fi,
            ))

        return NarrativeScript(topic=topic, beats=beats, format="long")

    def _offline_script(self, topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
        """Grounded offline script — uses research facts, no LLM."""
        name  = topic.protagonist
        facts = research.story_facts
        get   = lambda i, d="": facts[i] if i < len(facts) else d
        dates = research.dates

        def beat(bt, ta):
            return StoryBeat(
                beat_type=bt, narration_ta=ta, emotion=BEAT_EMOTIONS[bt],
                protagonist=name, visual_keywords=[bt.value, "person", "story"],
            )

        yr = dates[0] if dates else ""
        yr_txt = f"{yr}-ல் " if yr else ""

        return NarrativeScript(topic=topic, format="long", beats=[
            beat(BeatType.HOOK,
                f"{topic.emotional_hook or get(0)}. {topic.hook_question or 'இந்த கதை உங்களை திரும்பிப் பார்க்க வைக்கும்.'} {topic.open_loop or ''}".strip()),
            beat(BeatType.CONTEXT,
                f"{yr_txt}{name} — {topic.situation or get(1)}. அந்த நாட்களில் யாரும் கற்பனை கூட செய்யவில்லை என்ன நடக்கப் போகிறது என்று. {get(2, '')}".strip()),
            beat(BeatType.CONFLICT,
                f"{topic.core_problem or get(3)}. {get(4, 'தோல்வி மேல் தோல்வி வந்தது.')} யாரும் {name}-ஐ நம்பவில்லை. ஆனால் அவர் விட்டுக்கொடுக்கவில்லை."),
            beat(BeatType.ESCALATION,
                f"{get(5, 'நிலைமை இன்னும் மோசமானது.')} {get(6, '')} இதுதான் மிகவும் இருண்ட தருணம். வெளியே வழி தெரியவில்லை."),
            beat(BeatType.TURNING_POINT,
                f"{topic.turning_point or get(7, 'திடீரென்று ஒரு மாற்றம்')}. அந்த ஒரு நிமிடம் எல்லாவற்றையும் மாற்றியது. {get(8, '')}"),
            beat(BeatType.RESOLUTION,
                f"{get(9, name + ' வெற்றி அடைந்தார்')}. உலகம் அவரை வேறுவிதமாகப் பார்க்க ஆரம்பித்தது. {get(10, '')} இன்று அந்த பெயர் மறக்க முடியாதது."),
            beat(BeatType.LESSON,
                f"பாடம்: {topic.lesson or get(11, 'தோல்வி முடிவல்ல')}. {name}-ன் கதை நமக்கு இதை சொல்கிறது. இந்த video பயனுள்ளதாக இருந்தால் like செய்யுங்கள், subscribe செய்யுங்கள், bell icon அழுத்துங்கள். நன்றி!"),
        ])
