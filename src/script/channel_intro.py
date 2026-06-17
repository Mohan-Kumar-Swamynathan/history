"""Channel greeting and outro CTAs for Thulir."""

from __future__ import annotations

CHANNEL_GREETING_TA = (
    "வணக்கம்! துளிர் channel-க்கு உங்களை அன்புடன் வரவேற்கிறோம். "
    "இன்று நாம் ஒரு உண்மையான கதையைப் பார்க்கப் போகிறோம்."
)

CHANNEL_OUTRO_TA = (
    "இந்த கதை உங்களுக்குப் பிடித்திருந்தால் like செய்யுங்கள், "
    "உங்கள் நண்பர்களுடன் share செய்யுங்கள், "
    "மற்றும் துளிர் channel-க்கு subscribe செய்து bell icon-ஐ அழுத்துங்கள். "
    "அடுத்த கதையில் சந்திப்போம். நன்றி!"
)

SHORTS_GREETING_TA = "வணக்கம்! துளிர் — இன்றைய கதை."

SHORTS_OUTRO_TA = (
    "Like, share, subscribe செய்யுங்கள்! துளிர் channel-க்கு bell அழுத்துங்கள். நன்றி!"
)


def prepend_greeting(narration: str, is_shorts: bool = False) -> str:
    greeting = SHORTS_GREETING_TA if is_shorts else CHANNEL_GREETING_TA
    if greeting[:20] in narration:
        return narration
    return f"{greeting} {narration}"


def append_outro_cta(narration: str, is_shorts: bool = False) -> str:
    outro = SHORTS_OUTRO_TA if is_shorts else CHANNEL_OUTRO_TA
    if "subscribe" in narration.lower() and "share" in narration.lower():
        return narration
    return f"{narration} {outro}"
