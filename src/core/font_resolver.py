"""Cross-platform Tamil and Latin font resolution."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

log = logging.getLogger(__name__)

TAMIL_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tamil MN.ttc",
    "/System/Library/Fonts/Supplemental/Tamil Sangam MN.ttc",
    "/System/Library/Fonts/ZitherTamil.otf",
    "/Library/Fonts/NotoSansTamil-Black.ttf",
]

LATIN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]


@lru_cache(maxsize=1)
def get_tamil_font_path() -> str:
    return _resolve_first_existing(TAMIL_FONT_CANDIDATES, "Tamil")


@lru_cache(maxsize=1)
def get_latin_font_path() -> str:
    return _resolve_first_existing(LATIN_FONT_CANDIDATES, "Latin")


def load_font(size: int, script: str = "ta") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = get_tamil_font_path() if script in {"ta", "ta_reg"} else get_latin_font_path()
    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        log.error("Font load failed for %s size %d: %s", path, size, exc)
        return ImageFont.load_default()


def _resolve_first_existing(candidates: list[str], label: str) -> str:
    for candidate in candidates:
        if Path(candidate).exists():
            log.debug("Using %s font: %s", label, candidate)
            return candidate
    from src.core.config_loader import load_platform_config

    platform = load_platform_config()
    config_key = "ta_black" if label == "Tamil" else "en_black"
    configured = platform.get("fonts", {}).get(config_key, "")
    if configured and Path(configured).exists():
        return configured
    raise FileNotFoundError(
        f"No {label} font found. Install Noto Tamil fonts or set config/platform.yml fonts.{config_key}"
    )
