"""Channel hooks and outro CTAs for Thulir.

v2 — mid-story openers (Almost Everything style).

The old opener was:
  "வணக்கம்! துளிர் channel-க்கு உங்களை அன்புடன் வரவேற்கிறோம்.
   இன்று நாம் ஒரு உண்மையான கதையைப் பார்க்கப் போகிறோம்."

Problem: YouTube drops viewers in the first 15 seconds. A greeting/welcome
opener loses ~30% of viewers before the story begins.

Almost Everything's formula: start IN the story. The channel name appears
only in the thumbnail and end-screen — never as the first words.

New approach:
- CHANNEL_GREETING is now an open-loop hook injected BEFORE the first beat,
  replacing the welcome message. It teases the core tension without
  revealing the answer.
- The protagonist's name and a specific number anchor it immediately.
- 6 hook templates rotate so consecutive videos feel fresh.
"""

from __future__ import annotations

import random

# ── Mid-story hook templates ─────────────────────────────────────────
# {protagonist} and {hook_detail} are filled at call time.
# These are designed to drop the viewer into the scene.
_HOOK_TEMPLATES = [
    # Failure + question
    "{protagonist} 1009 முறை தோற்றார். ஆனால் 1010-வது முறை என்ன நடந்தது?",
    # Age + disbelief
    "{protagonist} வயது {protagonist_age}. எல்லோரும் சொன்னார்கள் — இனி முடியாது. அவர் என்ன செய்தார்?",
    # Single moment pivot
    "ஒரே ஒரு நிமிடம். அந்த நிமிடம் {protagonist}-ன் வாழ்க்கையை மாற்றியது.",
    # Contrast open
    "{protagonist} — உலகம் அவரை மறந்தது. ஆனால் வரலாறு மறக்கவில்லை.",
    # Mid-action drop
    "அன்று இரவு {protagonist} கையில் வெறும் ₹{hook_detail} இருந்தது. நாளை என்ன நடக்கும் என்று தெரியாது.",
    # Direct question to viewer
    "நீங்கள் என்ன செய்வீர்கள் — எல்லாம் இழந்த பிறகும் மீண்டும் தொடங்க முடியுமா? {protagonist} தொடங்கினார்.",
]

_SHORTS_HOOKS = [
    "{protagonist}-ன் கதை — 60 வினாடியில்.",
    "இந்த ஒரு தவறு {protagonist}-ன் எல்லாவற்றையும் மாற்றியது.",
    "{protagonist} சொன்னார்: தோல்வி முடிவு அல்ல.",
]

# ── Outro CTAs ────────────────────────────────────────────────────────
CHANNEL_OUTRO_TA = (
    "இந்த கதை உங்களுக்குப் பிடித்திருந்தால் like செய்யுங்கள், "
    "உங்கள் நண்பர்களுடன் share செய்யுங்கள், "
    "மற்றும் துளிர் channel-க்கு subscribe செய்து bell icon-ஐ அழுத்துங்கள். "
    "அடுத்த கதையில் சந்திப்போம். நன்றி!"
)

SHORTS_OUTRO_TA = (
    "Like, share, subscribe செய்யுங்கள்! துளிர் channel-க்கு bell அழுத்துங்கள். நன்றி!"
)


def _pick_hook(protagonist: str, protagonist_age: str = "", hook_detail: str = "100") -> str:
    """Pick a random hook template and fill in the protagonist details."""
    template = random.choice(_HOOK_TEMPLATES)
    return (
        template
        .replace("{protagonist}", protagonist)
        .replace("{protagonist_age}", protagonist_age or "")
        .replace("{hook_detail}", hook_detail)
        .strip()
    )


def prepend_greeting(
    narration: str,
    is_shorts: bool = False,
    protagonist: str = "",
    protagonist_age: str = "",
    hook_detail: str = "100",
) -> str:
    """Prepend an engaging mid-story hook instead of a welcome message.

    The hook is skipped if the narration already opens with a question
    or a number (meaning the LLM already wrote a strong hook).
    """
    if is_shorts:
        if not protagonist:
            return narration
        hook = random.choice(_SHORTS_HOOKS).replace("{protagonist}", protagonist)
        if hook[:15] in narration:
            return narration
        return f"{hook} {narration}"

    # If LLM wrote a good hook already (starts with Tamil question or digit),
    # don't override it — just return as-is.
    stripped = narration.strip()
    has_strong_open = (
        stripped[:1].isdigit()
        or "?" in stripped[:40]
        or stripped.startswith("அன்று")
        or stripped.startswith("ஒரு")
        or stripped.startswith("அவர்")
    )
    if has_strong_open:
        return narration

    if not protagonist:
        return narration

    hook = _pick_hook(protagonist, protagonist_age, hook_detail)
    if hook[:20] in narration:
        return narration
    return f"{hook} {narration}"


def append_outro_cta(narration: str, is_shorts: bool = False) -> str:
    outro = SHORTS_OUTRO_TA if is_shorts else CHANNEL_OUTRO_TA
    if "subscribe" in narration.lower() and "share" in narration.lower():
        return narration
    return f"{narration} {outro}"
