"""Offline story expansion from topic schema — compact (12) or full (24) beats."""

from __future__ import annotations

from src.core.config_loader import load_topics_config
from src.core.models import BeatType, NarrativeScript, ResearchBrief, StoryBeat, TopicCandidate
from src.script.channel_intro import append_outro_cta, prepend_greeting

COMPACT_BEAT_ORDER = [
    BeatType.HOOK,
    BeatType.HOOK,
    BeatType.CONTEXT,
    BeatType.CONTEXT,
    BeatType.CONFLICT,
    BeatType.CONFLICT,
    BeatType.ESCALATION,
    BeatType.TURNING_POINT,
    BeatType.TURNING_POINT,
    BeatType.RESOLUTION,
    BeatType.LESSON,
    BeatType.CTA,
]

FULL_BEAT_ORDER = [
    BeatType.HOOK,
    BeatType.HOOK,
    BeatType.HOOK,
    BeatType.CONTEXT,
    BeatType.CONTEXT,
    BeatType.CONTEXT,
    BeatType.CONFLICT,
    BeatType.CONFLICT,
    BeatType.CONFLICT,
    BeatType.ESCALATION,
    BeatType.ESCALATION,
    BeatType.ESCALATION,
    BeatType.TURNING_POINT,
    BeatType.TURNING_POINT,
    BeatType.TURNING_POINT,
    BeatType.RESOLUTION,
    BeatType.RESOLUTION,
    BeatType.RESOLUTION,
    BeatType.LESSON,
    BeatType.LESSON,
    BeatType.LESSON,
    BeatType.CTA,
    BeatType.CTA,
    BeatType.CTA,
]

BEAT_ORDER = COMPACT_BEAT_ORDER

BEAT_EMOTIONS = {
    BeatType.HOOK: "exciting",
    BeatType.CONTEXT: "neutral",
    BeatType.CONFLICT: "sad",
    BeatType.ESCALATION: "sad",
    BeatType.TURNING_POINT: "thinking",
    BeatType.RESOLUTION: "hope",
    BeatType.LESSON: "inspirational",
    BeatType.CTA: "exciting",
}

RETENTION_HOOKS = ["question", "surprise", "conflict", "reveal", "twist", "emotion"]

PAD_SENTENCES = [
    "அந்த நாட்கள் மிகவும் கடினமாக இருந்தன.",
    "அவர் வெளியில் சாதாரணமாக இருந்தார் — உள்ளே மட்டும் போர் நடந்தது.",
    "யாரும் அவரின் உண்மையான உணர்வை புரிந்து கொள்ளவில்லை.",
    "ஒவ்வொரு நாளும் ஒரே கேள்வி மனதில் எழுந்தது — நான் இதை சமாளிப்பேனா?",
    "அந்த தருணம் இன்றும் நினைவில் இருக்கிறது.",
    "Viewer இப்போது நினைக்க வேண்டும் — அடுத்து என்ன நடக்கும்?",
    "இது வெறும் பேச்சு அல்ல — உண்மையான வாழ்க்கையில் நடந்த நிகழ்வு.",
    "அவரைச் சுற்றி உலகம் சாதாரணமாகத் தொடர்ந்தது — ஆனால் அவருக்குள் எல்லாம் மாறியது.",
]


def _expand_narration(base: str, min_words: int = 45) -> str:
    import re
    words = re.findall(r"\S+", base)
    padding_index = 0
    expanded = base
    while len(words) < min_words:
        expanded = f"{expanded} {PAD_SENTENCES[padding_index % len(PAD_SENTENCES)]}"
        words = re.findall(r"\S+", expanded)
        padding_index += 1
    return expanded


def resolve_long_beat_order() -> list[BeatType]:
    beat_count = int(load_topics_config().get("script_targets", {}).get("long_beat_count", 12))
    if beat_count <= len(COMPACT_BEAT_ORDER):
        return COMPACT_BEAT_ORDER[:beat_count]
    return FULL_BEAT_ORDER[:beat_count]


def _min_words_per_beat() -> int:
    targets = load_topics_config().get("script_targets", {})
    beat_count = max(1, int(targets.get("long_beat_count", 12)))
    target_words = int(targets.get("long_target_words", 750))
    configured_min = int(targets.get("long_min_words_per_beat", 25))
    return max(configured_min, target_words // beat_count)


def build_offline_long_script(topic: TopicCandidate, research: ResearchBrief) -> NarrativeScript:
    protagonist = topic.protagonist
    templates = _build_templates(topic, research)
    beat_order = resolve_long_beat_order()
    min_words = _min_words_per_beat()
    beats: list[StoryBeat] = []
    macro_index = 0
    last_macro = None

    for index, beat_type in enumerate(beat_order):
        if beat_type != last_macro:
            macro_index += 1
            last_macro = beat_type
        template_index = index % len(templates.get(beat_type, [""]))
        narration = _expand_narration(
            templates[beat_type][template_index % len(templates[beat_type])],
            min_words=min_words,
        )
        if index == 0:
            narration = prepend_greeting(narration, is_shorts=False)
        if beat_type == BeatType.CTA and index == len(beat_order) - 1:
            narration = append_outro_cta(narration, is_shorts=False)
        beats.append(
            StoryBeat(
                beat_type=beat_type,
                narration_ta=narration,
                emotion=BEAT_EMOTIONS[beat_type],
                protagonist=protagonist,
                on_screen_text=_on_screen_text(beat_type, topic, index),
                visual_keywords=_visual_keywords(beat_type, topic),
                retention_hook=RETENTION_HOOKS[index % len(RETENTION_HOOKS)],
                open_loop=topic.open_loop if beat_type == BeatType.HOOK and index == 1 else "",
                macro_index=macro_index,
            )
        )
    return NarrativeScript(topic=topic, beats=beats, format="long")


def _on_screen_text(beat_type: BeatType, topic: TopicCandidate, index: int) -> str:
    if beat_type == BeatType.HOOK and index == 0:
        return topic.protagonist_age or "?"
    if beat_type == BeatType.TURNING_POINT:
        return "திருப்புமுனை"
    if beat_type == BeatType.LESSON:
        return "பாடம்"
    return ""


def _visual_keywords(beat_type: BeatType, topic: TopicCandidate) -> list[str]:
    base = ["street", "office", "home"]
    if beat_type in {BeatType.CONFLICT, BeatType.ESCALATION}:
        return ["sad", "rain", "empty_room"]
    if beat_type == BeatType.TURNING_POINT:
        return ["lightbulb", "path_up", "sunrise"]
    if beat_type == BeatType.RESOLUTION:
        return ["trophy", "graph_up", "celebration"]
    return base


def _build_templates(topic: TopicCandidate, research: ResearchBrief) -> dict:
    p = topic.protagonist
    fact = research.story_facts[0] if research.story_facts else topic.situation
    return {
        BeatType.HOOK: [
            f"{topic.hook_question} இந்த கேள்வி ஒருவரின் வாழ்க்கையை முற்றிலும் மாற்றியது. {p}-ன் கதை இன்று நாம் பார்க்கப் போவது.",
            f"{topic.open_loop or 'ஆனால் அடுத்து நடந்தது யாரும் எதிர்பார்க்கவில்லை.'} Viewer இப்போது நினைக்க வேண்டும் — அடுத்து என்ன நடக்கும்?",
            f"{topic.emotional_hook} அந்த தருணம் இன்னும் அவரை தொடர்ந்து வருகிறது. இது வெறும் motivation அல்ல — உண்மையான கதை.",
        ],
        BeatType.CONTEXT: [
            f"{p} {topic.situation or 'ஒரு சாதாரண வாழ்க்கை வாழ்ந்தார்'}. {fact}",
            f"வெளியில் எல்லாம் சரியாக இருந்தது. ஆனால் உள்ளே {topic.core_problem or 'ஒரு பெரிய பிரச்சனை'} அவரை அழுத்தியது.",
            f"அவரின் குடும்பமும், நண்பர்களும் அவரை வேறுவிதமாகப் பார்த்தனர். {p} தனக்குள் மட்டும் தன் உண்மையான உணர்வை வைத்திருந்தார்.",
        ],
        BeatType.CONFLICT: [
            f"ஒரு நாள் {topic.core_problem} முன்னேறி வந்தது. {p} தயாராக இல்லை. அந்த நாள் அவரின் வாழ்க்கையின் மிகக் கடினமான நாளாக இருந்தது.",
            f"யாரோ ஒருவர் அவரிடம் கேட்டார் — நீ இதை சமாளிக்க முடியுமா? {p} பதில் சொல்ல முடியவில்லை. அந்த மௌனம் தான் மிகப்பெரிய தோல்வி.",
            f"அவர் முயற்சித்தார். முதல் முயற்சி தோல்வி. இரண்டாவது முயற்சியும் தோல்வி. ஒவ்வொரு தோல்வியும் அவரை உள்ளே இன்னும் ஆழமாக இழுத்தது.",
        ],
        BeatType.ESCALATION: [
            f"பிரச்சனை பெரிதாகிக் கொண்டே போனது. {p} தன்னைத் தானே குற்றப்படுத்தினார். நான் போதாதவன் என்று நினைத்தார்.",
            f"அந்த வாரம் அவர் தூங்கவில்லை. ஒவ்வொரு காலையும் ஒரே கேள்வி — இது எப்போது முடிவடையும்? யாரும் அவரின் உணர்வை புரிந்து கொள்ளவில்லை.",
            f"ஒரு குறிப்பிட்ட தருணம் வந்தது. {topic.emotional_hook} அந்த நொடி அவரை முற்றிலும் உடைத்தது. அவர் நம்பிக்கையை கிட்டத்தட்ட இழந்தார்.",
        ],
        BeatType.TURNING_POINT: [
            f"ஆனால் {topic.turning_point or 'ஒரு திருப்புமுனை வந்தது'}. இது வெறும் luck அல்ல — ஒரு முடிவு எடுக்கப்பட்டது.",
            f"{p} அன்று ஒரு வித்தியாசமான தேர்வு எடுத்தார். யாரும் எதிர்பார்க்காத ஒரு பாதை. அது சிறியதாகத் தோன்றியது — ஆனால் எல்லாவற்றையும் மாற்றியது.",
            f"அந்த திருப்புமுனைக்குப் பிறகு அவர் வேறு மனிதனாக மாறினார். Viewer இப்போது நினைக்க வேண்டும் — இதுதான் உண்மையான மாற்றமா?",
        ],
        BeatType.RESOLUTION: [
            f"மாற்றம் உடனடியாக வரவில்லை. ஆனால் ஒவ்வொரு நாளும் சிறிய முன்னேற்றம். {p} மீண்டும் நம்பிக்கை கண்டார்.",
            f"முதலில் யாரும் கவனிக்கவில்லை. பிறகு ஒருவர். பிறகு பலர். {p}-ன் கதை பரவத் தொடங்கியது — ஏனெனில் அது உண்மையானது.",
            f"இன்று அவர் அந்த கடந்த காலத்தை நினைவு கூர்ந்தால் சிரிக்கிறார். ஏனெனில் அந்த தோல்விகள் இல்லாவிட்டால் இந்த வெற்றி இருக்காது.",
        ],
        BeatType.LESSON: [
            f"இந்த கதையின் பாடம்: {topic.lesson or 'தோல்வி ஒரு முடிவு அல்ல'}. இது lecture அல்ல — கதையிலிருந்து வந்த பாடம்.",
            f"{p}-ன் அனுபவம் நமக்கு சொல்கிறது — உங்கள் வாழ்க்கையில் நீங்கள் எங்கு இருந்தாலும் மாற்றம் சாத்தியம். ஆனால் முதல் படி உங்களிடமிருந்து தொடங்க வேண்டும்.",
            f"Lesson preach செய்யப்படவில்லை. நீங்கள் கதையை கேட்டு உங்கள் வாழ்க்கையுடன் இணைத்துக் கொள்ளுங்கள். அதுதான் துளிர் channel-ன் நோக்கம்.",
        ],
        BeatType.CTA: [
            f"இந்த கதை உங்களுக்கு எப்படி உணர்த்தியது? கமெண்ட் செய்து சொல்லுங்கள். உங்கள் கதையும் யாருக்காவது inspiration ஆகலாம்.",
            f"துளிர் channel-க்கு subscribe செய்து இன்னும் உண்மையான கதைகளை கேளுங்கள். அடுத்த வீடியோவில் இன்னும் ஒரு திருப்புமுனை காத்திருக்கிறது.",
            f"இன்று ஒரு சிறிய முடிவு எடுங்கள். {topic.lesson} — like செய்யுங்கள், share செய்யுங்கள், subscribe செய்யுங்கள்.",
        ],
    }
