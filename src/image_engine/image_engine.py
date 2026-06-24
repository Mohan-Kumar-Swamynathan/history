"""Image engine — fetch Pexels photos for Ken Burns fallback (no sketch filter)."""

from __future__ import annotations

import io
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image

log = logging.getLogger(__name__)

PEXELS_BASE = "https://api.pexels.com/v1/search"
FALLBACK_IMAGE_WIDTH = 1920
FALLBACK_IMAGE_HEIGHT = 1080


def _pexels_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def _fetch_pexels_photo(query: str, orientation: str = "landscape") -> Optional[bytes]:
    key = _pexels_key()
    if not key:
        return None
    try:
        encoded = urllib.parse.quote(query)
        url = f"{PEXELS_BASE}?query={encoded}&per_page=3&orientation={orientation}&size=large"
        request = urllib.request.Request(
            url,
            headers={"Authorization": key, "User-Agent": "ThulirBot/1.0"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read())
        photos = data.get("photos", [])
        if not photos:
            return None
        photo = photos[min(1, len(photos) - 1)]
        image_url = (
            photo.get("src", {}).get("large2x")
            or photo.get("src", {}).get("large")
            or photo.get("src", {}).get("medium")
        )
        if not image_url:
            return None
        image_request = urllib.request.Request(
            image_url,
            headers={"User-Agent": "ThulirBot/1.0"},
        )
        with urllib.request.urlopen(image_request, timeout=30) as image_response:
            return image_response.read()
    except Exception as exc:
        log.warning("Pexels photo fetch failed for '%s': %s", query, exc)
        return None


def _build_query(beat_keywords: list[str], topic_title: str, beat_type: str) -> str:
    """Build a focused Pexels search query from story context."""
    keyword_map = {
        "rejection": "man rejected paperwork",
        "தோல்வி": "failure disappointment person",
        "வெற்றி": "success celebration achievement",
        "success": "success achievement celebration",
        "office": "office desk professional",
        "அலுவலக": "office desk business",
        "kitchen": "restaurant kitchen cooking",
        "food": "restaurant food cooking",
        "street": "street city urban walking",
        "வீதி": "street city people",
        "factory": "factory workers manufacturing",
        "prison": "bars locked door",
        "mountain": "mountain climb achievement",
        "money": "coins money finance",
        "கடன்": "debt finance worry",
        "family": "family home together",
        "குடும்பம்": "family together home",
        "child": "child learning study",
        "குழந்தை": "child school learning",
        "old": "elderly senior person",
        "book": "reading library books",
        "phone": "smartphone technology person",
        "car": "automobile driving road",
        "hospital": "hospital doctor medical",
        "farm": "farm agriculture crops",
    }

    for keyword in beat_keywords:
        keyword_lower = keyword.lower()
        for key, query in keyword_map.items():
            if key in keyword_lower:
                return query

    beat_emotion_query = {
        "hook": "determined person closeup",
        "conflict": "struggle difficulty person",
        "escalation": "stressed worried person",
        "turning_point": "realization moment person",
        "resolution": "happy success person",
        "lesson": "wisdom thinking person",
        "cta": "motivated inspired person",
        "context": "story background scene",
    }
    base_query = beat_emotion_query.get(beat_type, "person story moment")

    skip_words = {
        "no.1", "no1", "ltd", "inc", "pvt", "vs", "the", "and", "for", "with",
        "from", "into", "that", "this", "your", "their", "about", "more",
    }
    title_words = [
        word for word in topic_title.split()
        if word.isascii() and len(word) > 3 and word.lower().strip(".,!?") not in skip_words
        and not word.replace(".", "").replace("-", "").isdigit()
    ]
    if title_words:
        return f"{title_words[0]} {base_query}"
    return base_query


def _save_fallback_photo(
    photo_bytes: bytes,
    output_path: Path,
    width: int = FALLBACK_IMAGE_WIDTH,
    height: int = FALLBACK_IMAGE_HEIGHT,
) -> Path:
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    photo = photo.resize((width, height), Image.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(output_path, format="JPEG", quality=90)
    return output_path


def _placeholder_photo(output_path: Path, beat_type: str = "neutral") -> Path:
    color_map = {
        "hook": (245, 238, 215),
        "conflict": (235, 228, 245),
        "escalation": (242, 228, 220),
        "turning_point": (220, 240, 230),
        "resolution": (220, 242, 220),
        "lesson": (238, 238, 215),
    }
    fill_color = color_map.get(beat_type, (244, 242, 232))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (FALLBACK_IMAGE_WIDTH, FALLBACK_IMAGE_HEIGHT), fill_color).save(
        output_path,
        format="JPEG",
        quality=90,
    )
    return output_path


class ImageEngine:
    """Fetch raw Pexels photos for Ken Burns fallback when a stock clip is unavailable."""

    def __init__(self) -> None:
        self._cache: dict[str, Path] = {}

    def prefetch_fallback_photos(
        self,
        beats: list,
        topic_title: str,
        output_dir: Path,
    ) -> dict[int, Path]:
        """Download one landscape photo per beat for Ken Burns fallback."""
        output_dir.mkdir(parents=True, exist_ok=True)
        results: dict[int, Path] = {}

        for beat_index, beat in enumerate(beats):
            cache_key = f"beat_{beat_index}_{beat.beat_type.value}"
            if cache_key in self._cache and self._cache[cache_key].exists():
                results[beat_index] = self._cache[cache_key]
                continue

            query = _build_query(
                beat.visual_keywords,
                topic_title,
                beat.beat_type.value,
            )
            output_path = output_dir / f"beat_{beat_index}.jpg"
            log.info("Photo fallback search: '%s' (beat=%s)", query, beat.beat_type.value)

            photo_bytes = _fetch_pexels_photo(query, orientation="landscape")
            if photo_bytes:
                try:
                    saved_path = _save_fallback_photo(photo_bytes, output_path)
                    self._cache[cache_key] = saved_path
                    results[beat_index] = saved_path
                    log.info("Fallback photo ready for beat '%s'", beat.beat_type.value)
                except Exception as exc:
                    log.warning("Fallback photo save failed: %s", exc)

            if beat_index not in results:
                placeholder_path = _placeholder_photo(output_path, beat.beat_type.value)
                self._cache[cache_key] = placeholder_path
                results[beat_index] = placeholder_path

            time.sleep(0.2)

        return results
