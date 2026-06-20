"""Image engine — fetch relevant photo from Pexels, convert to sketch style.

Each story beat gets one image:
  1. Build a search query from beat keywords + topic
  2. Fetch best match from Pexels (free, already has API key in secrets)
  3. Apply PIL sketch filter: grayscale → edge enhance → high contrast
  4. Result looks like a hand-drawn whiteboard illustration

Falls back to a clean gradient placeholder if Pexels fails.
"""

from __future__ import annotations

import io
import logging
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

log = logging.getLogger(__name__)

PEXELS_API = "https://api.pixabay.com/api/"  # pixabay is free no-key
PEXELS_BASE = "https://api.pexels.com/v1/search"

# Fallback: pixabay has a free tier with no key for low-res
PIXABAY_BASE = "https://pixabay.com/api/"
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")

PANEL_W = 860
PANEL_H = 660
_CACHE: dict[str, Image.Image] = {}


def _pexels_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def _fetch_pexels(query: str, orientation: str = "landscape") -> Optional[bytes]:
    key = _pexels_key()
    if not key:
        return None
    try:
        encoded = urllib.parse.quote(query)
        url = f"{PEXELS_BASE}?query={encoded}&per_page=3&orientation={orientation}&size=medium"
        req = urllib.request.Request(url, headers={
            "Authorization": key,
            "User-Agent": "ThulirBot/1.0",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            import json
            data = json.loads(r.read())
        photos = data.get("photos", [])
        if not photos:
            return None
        # Pick middle result for more variety
        photo = photos[min(1, len(photos) - 1)]
        img_url = photo["src"]["medium"]
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "ThulirBot/1.0"})
        with urllib.request.urlopen(req2, timeout=20) as r2:
            return r2.read()
    except Exception as exc:
        log.warning("Pexels fetch failed for '%s': %s", query, exc)
        return None


def _build_query(beat_keywords: list[str], topic_title: str, beat_type: str) -> str:
    """Build a focused Pexels search query from story context."""
    # Priority: specific visual keywords from the beat
    kw_map = {
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

    for kw in beat_keywords:
        kl = kw.lower()
        for key, query in kw_map.items():
            if key in kl:
                return query

    # Fallback: use topic protagonist + beat type emotion
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
    base = beat_emotion_query.get(beat_type, "person story moment")

    # Use protagonist name if ASCII and meaningful (not No.1, Ltd, vs, etc.)
    _SKIP = {"no.1","no1","ltd","inc","pvt","vs","the","and","for","with",
              "from","into","that","this","your","their","about","more"}
    title_words = [
        w for w in topic_title.split()
        if w.isascii() and len(w) > 3 and w.lower().strip(".,!?") not in _SKIP
        and not w.replace(".","").replace("-","").isdigit()
    ]
    if title_words:
        return f"{title_words[0]} {base}"
    return base


def _to_sketch(img: Image.Image, panel_w: int = PANEL_W, panel_h: int = PANEL_H) -> Image.Image:
    """Convert photo to whiteboard sketch style."""
    # 1. Resize to panel with letterboxing
    img = ImageOps.fit(img, (panel_w, panel_h), Image.LANCZOS)

    # 2. Grayscale
    img = img.convert("L")

    # 3. Invert for pencil-on-paper look
    inverted = ImageOps.invert(img)

    # 4. Gaussian blur the inverted
    blurred = inverted.filter(ImageFilter.GaussianBlur(radius=14))

    # 5. Dodge blend: img / (1 - blurred) — classic sketch effect
    import numpy as np
    arr_img = np.array(img, dtype=np.float32)
    arr_blur = np.array(blurred, dtype=np.float32)
    # Avoid division by zero
    divisor = 255.0 - arr_blur
    divisor = np.clip(divisor, 1.0, 255.0)
    sketch = np.clip((arr_img * 255.0) / divisor, 0, 255).astype(np.uint8)
    sketch_img = Image.fromarray(sketch, mode="L")

    # 6. Increase contrast for bolder lines
    sketch_img = ImageEnhance.Contrast(sketch_img).enhance(2.2)

    # 7. Slightly darken lines (sketch on paper = dark lines, light bg)
    sketch_img = ImageEnhance.Brightness(sketch_img).enhance(1.1)

    # 8. Convert back to RGB (cream paper background tint)
    rgb = Image.new("RGB", (panel_w, panel_h), (252, 250, 244))
    # Paste sketch as dark lines (where sketch is dark, show ink)
    mask_arr = np.array(sketch_img)
    # Lines are dark in sketch → use as alpha for dark ink overlay
    ink_alpha = np.clip(255 - mask_arr, 0, 255).astype(np.uint8)
    ink_layer = Image.new("RGBA", (panel_w, panel_h), (25, 20, 15, 0))
    ink_layer.putalpha(Image.fromarray(ink_alpha))
    rgb.paste(Image.new("RGB", (panel_w, panel_h), (25, 20, 15)), mask=Image.fromarray(ink_alpha))

    return rgb


def _placeholder(panel_w: int = PANEL_W, panel_h: int = PANEL_H,
                 beat_type: str = "neutral") -> Image.Image:
    """Clean gradient placeholder when no image available."""
    COLORS = {
        "hook":          [(252, 248, 235), (245, 238, 215)],
        "conflict":      [(245, 240, 250), (235, 228, 245)],
        "escalation":    [(250, 240, 235), (242, 228, 220)],
        "turning_point": [(235, 248, 240), (220, 240, 230)],
        "resolution":    [(240, 250, 240), (220, 242, 220)],
        "lesson":        [(248, 248, 235), (238, 238, 215)],
    }
    top, bot = COLORS.get(beat_type, [(252, 250, 244), (244, 242, 232)])
    img = Image.new("RGB", (panel_w, panel_h), top)
    # Simple vertical gradient
    import numpy as np
    arr = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
    for y in range(panel_h):
        t = y / panel_h
        for c in range(3):
            arr[y, :, c] = int(top[c] * (1 - t) + bot[c] * t)
    return Image.fromarray(arr)


class ImageEngine:
    """Fetch and sketch-convert one image per story beat."""

    def __init__(self) -> None:
        self._cache: dict[str, Image.Image] = {}

    def get_beat_image(
        self,
        beat_keywords: list[str],
        topic_title: str,
        beat_type: str,
        cache_key: str,
        panel_w: int = PANEL_W,
        panel_h: int = PANEL_H,
    ) -> Image.Image:
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = _build_query(beat_keywords, topic_title, beat_type)
        log.info("Image search: '%s' (beat=%s)", query, beat_type)

        raw = _fetch_pexels(query)
        if raw:
            try:
                photo = Image.open(io.BytesIO(raw)).convert("RGB")
                sketch = _to_sketch(photo, panel_w, panel_h)
                self._cache[cache_key] = sketch
                log.info("✅ Sketch image ready for beat '%s'", beat_type)
                return sketch
            except Exception as exc:
                log.warning("Sketch conversion failed: %s", exc)

        # Fallback
        fallback = _placeholder(panel_w, panel_h, beat_type)
        self._cache[cache_key] = fallback
        return fallback

    def prefetch_all(
        self,
        beats: list,
        topic_title: str,
    ) -> dict[int, Image.Image]:
        """Fetch all beat images upfront (before render loop) to avoid CI latency."""
        results: dict[int, Image.Image] = {}
        for i, beat in enumerate(beats):
            key = f"beat_{i}_{beat.beat_type.value}"
            img = self.get_beat_image(
                beat_keywords=beat.visual_keywords,
                topic_title=topic_title,
                beat_type=beat.beat_type.value,
                cache_key=key,
            )
            results[i] = img
            time.sleep(0.3)  # gentle rate limit
        return results
