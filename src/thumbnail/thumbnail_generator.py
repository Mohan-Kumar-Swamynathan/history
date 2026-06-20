"""Thumbnail generator — CTR-optimised, brand-matched.

Strategy (content bible):
  - One focal subject: real Pexels portrait matching story emotion
  - Bold 2-4 Tamil words (the hook number or phrase)
  - Brand green gradient bottom strip
  - High contrast, emotion-driven color grading
  - Output: 1280×720 JPG (YouTube spec)

Layout:
  ┌─────────────────────────────────────────┐
  │  [Pexels portrait — full bleed]         │
  │  Dark vignette on left 40%              │
  │                                         │
  │  ┌─ HOOK TEXT ─────────────────────┐    │
  │  │  1009 முறை    (huge, white+shadow)│  │
  │  │  தோற்றார்...  (subtitle, gold)  │    │
  │  └───────────────────────────────────┘  │
  │  [brand green strip bottom]             │
  └─────────────────────────────────────────┘
"""

from __future__ import annotations

import io
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

log = logging.getLogger(__name__)

W, H = 1280, 720

try:
    from src.renderer.brand import PRIMARY, DARK, ACCENT, CREAM, INK, LIGHT, BG
except ImportError:
    PRIMARY = (29, 48, 16); DARK = (29, 51, 11); ACCENT = (212, 175, 55)
    CREAM = (244, 235, 191); INK = (26, 46, 8); LIGHT = (237, 247, 224)
    BG = (250, 250, 240)

_TA_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
]
_EN_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
_FC: dict = {}

def _font(sc, sz):
    k = (sc, sz)
    if k not in _FC:
        for p in (_TA_FONTS if sc == "ta" else _EN_FONTS):
            if os.path.exists(p):
                try: _FC[k] = ImageFont.truetype(p, sz); break
                except: pass
        if k not in _FC: _FC[k] = ImageFont.load_default()
    return _FC[k]

def _sc(text):
    ta = sum(1 for c in text if 0x0B80 <= ord(c) <= 0x0BFF)
    return "ta" if ta > len(text) * 0.3 else "en"

def _draw_text_outlined(draw, text, x, y, size, fill, outline=(0,0,0), outline_w=4):
    """Draw text with thick outline for readability on any background."""
    sc = _sc(text)
    f  = _font(sc, size)
    for dx in range(-outline_w, outline_w+1, 2):
        for dy in range(-outline_w, outline_w+1, 2):
            if dx*dx + dy*dy <= outline_w*outline_w:
                draw.text((x+dx, y+dy), text, font=f, fill=outline)
    draw.text((x, y), text, font=f, fill=fill)
    return draw.textbbox((0,0), text, font=f)[2]

def _fetch_portrait(query: str) -> Optional[Image.Image]:
    """Fetch emotion portrait from Pexels."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return None
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.pexels.com/v1/search?query={encoded}&per_page=3&orientation=portrait&size=medium"
        req = urllib.request.Request(url, headers={
            "Authorization": key, "User-Agent": "ThulirBot/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            import json
            data = json.loads(r.read())
        photos = data.get("photos", [])
        if not photos:
            return None
        photo = photos[len(photos) // 2]  # pick middle for variety
        img_url = photo["src"]["large"]
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "ThulirBot/1.0"})
        with urllib.request.urlopen(req2, timeout=20) as r2:
            return Image.open(io.BytesIO(r2.read())).convert("RGB")
    except Exception as e:
        log.warning("Pexels portrait fetch failed: %s", e)
        return None

def _emotion_portrait_query(emotion_trigger: str, protagonist: str) -> str:
    """Build Pexels query for a thumbnail-worthy portrait."""
    query_map = {
        "surprise":     "shocked surprised person face closeup",
        "shock":        "shocked disbelief person dramatic face",
        "hope":         "determined hopeful person looking up",
        "triumph":      "success celebration person fist victory",
        "failure":      "disappointed frustrated business person",
        "excitement":   "excited motivated person entrepreneur",
        "mystery":      "mysterious thinking person dramatic light",
        "fear":         "worried concerned anxious person face",
    }
    base = query_map.get(emotion_trigger, "determined focused person portrait")
    # Add protagonist context if it's a person (not company)
    if protagonist and protagonist[0].isupper() and len(protagonist.split()) <= 3:
        words = [w for w in protagonist.split() if w.isalpha()]
        if words:
            return f"{words[0]} {base}"
    return base

def _make_gradient_bg(w, h, top_color, bottom_color) -> Image.Image:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        t = y / h
        for c in range(3):
            arr[y,:,c] = int(top_color[c]*(1-t) + bottom_color[c]*t)
    return Image.fromarray(arr)

def _apply_cinematic_grade(img: Image.Image, emotion: str) -> Image.Image:
    """Color grade the portrait for cinematic look."""
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Color(img).enhance(1.15)  # PIL uses Color not Saturation
    img = ImageEnhance.Brightness(img).enhance(0.88)
    # Slight green tint for brand consistency
    arr = np.array(img, dtype=np.float32)
    arr[:,:,1] = np.clip(arr[:,:,1] * 1.04, 0, 255)  # boost green channel
    return Image.fromarray(arr.clip(0,255).astype(np.uint8))

def _apply_vignette(img: Image.Image) -> Image.Image:
    """Dark left-side vignette for text readability."""
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    # Left-heavy vignette
    for x in range(w):
        t = max(0, (w*0.55 - x) / (w*0.55))
        arr[:,x] *= (1 - t*0.75)
    return Image.fromarray(arr.clip(0,255).astype(np.uint8))


class ThumbnailGenerator:
    def generate(
        self,
        topic,
        output_path: Path,
        hook_frame: Optional[np.ndarray] = None,
        thumbnail_text: str = "",
        emotion_trigger: str = "surprise",
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        protagonist = getattr(topic, "protagonist", "")
        title_ta    = getattr(topic, "title_ta", thumbnail_text or "")

        # ── 1. Background: Pexels portrait ───────────────────────
        portrait_query = _emotion_portrait_query(emotion_trigger, protagonist)
        portrait = _fetch_portrait(portrait_query)

        if portrait:
            log.info("✅ Thumbnail portrait: %s", portrait_query)
            # Crop to landscape 16:9
            pw, ph = portrait.size
            target_ratio = W / H
            if pw/ph > target_ratio:
                new_w = int(ph * target_ratio)
                ox = (pw - new_w) // 2
                portrait = portrait.crop((ox, 0, ox+new_w, ph))
            else:
                new_h = int(pw / target_ratio)
                oy = max(0, (ph - new_h) // 3)  # face usually upper 1/3
                portrait = portrait.crop((0, oy, pw, oy+new_h))
            bg = portrait.resize((W, H), Image.LANCZOS)
            bg = _apply_cinematic_grade(bg, emotion_trigger)
        elif hook_frame is not None:
            bg = Image.fromarray(hook_frame).resize((W, H), Image.LANCZOS)
            bg = ImageEnhance.Contrast(bg).enhance(1.25)
        else:
            bg = _make_gradient_bg(W, H, DARK, (60, 90, 30))

        bg = _apply_vignette(bg)

        # ── 2. Brand gradient strip bottom 22% ───────────────────
        draw = ImageDraw.Draw(bg)
        strip_h = int(H * 0.22)
        for y in range(H - strip_h, H):
            t = (y - (H - strip_h)) / strip_h
            r = int(PRIMARY[0]*(1-t) + DARK[0]*t)
            g = int(PRIMARY[1]*(1-t) + DARK[1]*t)
            b = int(PRIMARY[2]*(1-t) + DARK[2]*t)
            alpha = int(200 + 55*t)  # increasingly opaque toward bottom
            draw.line([(0,y),(W,y)], fill=(r,g,b))

        # ── 3. Hook text — big number or phrase ─────────────────
        hook_text = thumbnail_text or _extract_hook_text(title_ta)
        lines     = _split_hook_lines(hook_text)

        y = int(H * 0.10)
        for i, line in enumerate(lines[:3]):
            sz = 140 if i == 0 else 90
            f  = _font(_sc(line), sz)
            bbox = draw.textbbox((0,0), line, font=f)
            lw   = bbox[2] - bbox[0]
            x    = max(30, min(60, int(W*0.05)))
            col  = (255, 255, 255) if i == 0 else ACCENT
            _draw_text_outlined(draw, line, x, y, sz, col,
                                outline=(0,0,0), outline_w=5 if i==0 else 3)
            y += sz + 18

        # ── 4. Channel name bottom right ─────────────────────────
        ch_font = _font("ta", 36)
        ch_text = "துளிர்"
        ch_bbox = draw.textbbox((0,0), ch_text, font=ch_font)
        ch_x = W - (ch_bbox[2]-ch_bbox[0]) - 30
        ch_y = H - 52
        draw.text((ch_x, ch_y), ch_text, font=ch_font, fill=CREAM)

        # ── 5. Gold accent bar left edge ─────────────────────────
        draw.rectangle([0, 0, 7, H], fill=ACCENT)

        bg.save(output_path, "JPEG", quality=95)
        log.info("Thumbnail saved: %s", output_path)
        return output_path

    def generate_variants(self, topic, output_dir: Path,
                          hook_frame=None, emotion_trigger="surprise") -> list[Path]:
        """Generate 3 thumbnail variants for A/B testing."""
        output_dir.mkdir(parents=True, exist_ok=True)
        title_ta = getattr(topic, "title_ta", "")
        variants  = []
        texts = _get_title_variants(title_ta)[:3]
        for i, text in enumerate(texts):
            path = output_dir / f"thumbnail_v{i+1}.jpg"
            self.generate(topic, path,
                          hook_frame=hook_frame,
                          thumbnail_text=text,
                          emotion_trigger=emotion_trigger)
            variants.append(path)
            time.sleep(0.3)
        return variants


def _extract_hook_text(title_ta: str) -> str:
    """Extract 2-4 word hook from title."""
    import re
    # Find numbers first
    nums = re.findall(r'\d+', title_ta)
    if nums:
        n = nums[0]
        # Find words around the number
        idx = title_ta.find(n)
        window = title_ta[max(0,idx-5):idx+len(n)+15].strip()
        return window[:25]
    # Fallback: first 3 words
    words = title_ta.split()
    return " ".join(words[:3]) if words else title_ta[:20]

def _split_hook_lines(text: str) -> list[str]:
    """Split hook text into 2-3 short lines."""
    words = text.split()
    if len(words) <= 2: return [text]
    if len(words) <= 4:
        mid = len(words)//2
        return [" ".join(words[:mid]), " ".join(words[mid:])]
    return [" ".join(words[:2]), " ".join(words[2:4]), " ".join(words[4:6])]

def _get_title_variants(title_ta: str) -> list[str]:
    """Extract different hook angle variants from title."""
    import re
    nums = re.findall(r'\d+\s*\S{0,6}', title_ta)
    variants = []
    if nums: variants.append(nums[0][:20])
    words = title_ta.split()
    if len(words) >= 2: variants.append(" ".join(words[:3]))
    if len(words) >= 4: variants.append(" ".join(words[-3:]))
    return variants or [title_ta[:20]]
