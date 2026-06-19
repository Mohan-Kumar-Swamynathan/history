"""Almost Everything renderer v3 — clean rebuild.

Design principles (from studying AE videos):
  - Pure white/cream background
  - Sketch image fills RIGHT 55% of frame, draws in progressively
  - LEFT 45%: current sentence ONLY, large bold text, black
  - NO progress bars, NO beat badges, NO sparkles, NO paper lines
  - Text clears fully between beats
  - Word-by-word reveal with current word in RED
  - PIL only — zero cairosvg per frame (fast)
  - Camera: very slow Ken Burns zoom (1.00 → 1.04 over scene)
"""

from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080

# Layout constants
TEXT_X      = 60          # left margin for text
TEXT_MAX_W  = 820         # max text column width (left 43%)
TEXT_TOP    = 80          # top of text area
IMAGE_X     = 940         # image panel starts here
IMAGE_W     = W - IMAGE_X - 30   # 950px wide
IMAGE_H     = H - 80      # full height minus padding
IMAGE_Y     = 40

# Colors
BG          = (252, 250, 244)   # warm cream
INK         = (18,  16,  14)    # near-black
RED         = (205, 35,  25)    # AE accent red
GREY        = (160, 155, 148)   # spoken/faded word color
DIVIDER     = (220, 215, 205)   # thin vertical divider

# Tamil font sizes — AE uses big, confident text
FONT_SIZES  = [130, 108, 90, 76, 64, 54]

_FONT_CACHE: dict = {}


def _font(script: str, size: int) -> ImageFont.FreeTypeFont:
    key = (script, size)
    if key not in _FONT_CACHE:
        paths = {
            "ta": "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
            "en": "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
        }
        try:
            _FONT_CACHE[key] = ImageFont.truetype(paths.get(script, paths["en"]), size)
        except Exception:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def _script(ch: str) -> str:
    cp = ord(ch)
    return "ta" if (0x0B80 <= cp <= 0x0BFF) else "en"


def _word_script(word: str) -> str:
    ta = sum(1 for c in word if 0x0B80 <= ord(c) <= 0x0BFF)
    return "ta" if ta > len(word) / 2 else "en"


def _text_width(draw: ImageDraw.ImageDraw, text: str, size: int) -> int:
    sc = _word_script(text)
    return draw.textbbox((0, 0), text, font=_font(sc, size))[2]


def _draw_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
               size: int, color: tuple) -> int:
    sc = _word_script(text)
    f  = _font(sc, size)
    draw.text((x, y), text, font=f, fill=color)
    return x + draw.textbbox((0, 0), text, font=f)[2]


def _wrap_words(words: List[str], size: int, max_w: int,
                draw: ImageDraw.ImageDraw) -> List[List[str]]:
    lines: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        test = " ".join(cur + [w])
        if _text_width(draw, test, size) <= max_w or not cur:
            cur.append(w)
        else:
            lines.append(cur)
            cur = [w]
    if cur:
        lines.append(cur)
    return lines


def _pick_font_size(words: List[str], max_w: int, max_h: int,
                    draw: ImageDraw.ImageDraw) -> int:
    for sz in FONT_SIZES:
        lines = _wrap_words(words, sz, max_w, draw)
        lh = draw.textbbox((0, 0), "ம", font=_font("ta", sz))[3] + 18
        if len(lines) * lh <= max_h:
            return sz
    return FONT_SIZES[-1]


def _apply_ken_burns(img: Image.Image, progress: float,
                     max_zoom: float = 1.04) -> Image.Image:
    """Slow zoom in over the scene — Ken Burns effect."""
    zoom = 1.0 + (max_zoom - 1.0) * progress
    if zoom <= 1.001:
        return img
    nw = int(img.width  / zoom)
    nh = int(img.height / zoom)
    ox = (img.width  - nw) // 2
    oy = (img.height - nh) // 2
    cropped = img.crop((ox, oy, ox + nw, oy + nh))
    return cropped.resize((img.width, img.height), Image.LANCZOS)


def _reveal_image(panel: Image.Image, progress: float) -> Image.Image:
    """Reveal image left-to-right like being drawn with a pen."""
    if progress >= 0.99:
        return panel
    reveal_w = max(1, int(panel.width * min(progress * 1.3, 1.0)))
    # Create revealed version: right part fades in
    out = Image.new("RGB", panel.size, BG)
    if reveal_w > 0:
        revealed_part = panel.crop((0, 0, reveal_w, panel.height))
        out.paste(revealed_part, (0, 0))
    return out


def render_frame(
    all_words:        List[str],
    visible:          int,
    image_panel:      Image.Image,
    image_progress:   float,     # 0→1: how much of image is revealed
    scene_progress:   float,     # 0→1: overall scene progress
    word_pop_frame:   int,       # frames since last new word (for bounce)
) -> Image.Image:
    """Render one frame. Pure PIL, no external deps."""

    # ── Base frame ────────────────────────────────────────────────────
    frame = Image.new("RGB", (W, H), BG)
    draw  = ImageDraw.Draw(frame)

    # ── Thin vertical divider ─────────────────────────────────────────
    draw.line([(IMAGE_X - 20, 40), (IMAGE_X - 20, H - 40)], fill=DIVIDER, width=2)

    # ── Right: sketch image, revealed progressively ───────────────────
    panel_resized = image_panel.resize((IMAGE_W, IMAGE_H), Image.LANCZOS)
    revealed      = _reveal_image(panel_resized, image_progress)
    # Soft feather right edge of reveal
    frame.paste(revealed, (IMAGE_X, IMAGE_Y))

    # Pencil cursor dot at reveal frontier
    if 0.02 < image_progress < 0.97:
        cx = IMAGE_X + int(IMAGE_W * min(image_progress * 1.3, 1.0))
        cy = IMAGE_Y + IMAGE_H // 2
        cx = min(cx, IMAGE_X + IMAGE_W - 4)
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(80, 70, 60))

    # ── Left: word-by-word text ───────────────────────────────────────
    if not all_words:
        return _apply_ken_burns(frame, scene_progress)

    words_to_show = all_words[:visible]
    max_h = H - TEXT_TOP - 120
    sz = _pick_font_size(all_words, TEXT_MAX_W, max_h, draw)
    lines = _wrap_words(words_to_show, sz, TEXT_MAX_W, draw)

    lh = draw.textbbox((0, 0), "ம", font=_font("ta", sz))[3] + 22
    total_h = len(lines) * lh
    y_start = TEXT_TOP + max(0, (max_h - total_h) // 3)  # slight top-bias

    wi = 0
    for line_words in lines:
        x = TEXT_X
        for word in line_words:
            is_current = (wi == visible - 1) and (visible < len(all_words))
            is_done    = (wi < visible - 1)
            is_last    = (wi == visible - 1) and (visible >= len(all_words))

            if is_current:
                # Word pop: slight bounce on entry
                pop_offset = 0
                if word_pop_frame < 8:
                    pop_offset = -int(math.sin(word_pop_frame / 8 * math.pi) * 10)
                col = RED
                y   = y_start + pop_offset
                # Underline current word
                ww = _text_width(draw, word, sz)
                draw.line([(x, y_start + lh - 8), (x + ww, y_start + lh - 8)],
                          fill=RED, width=4)
            elif is_last:
                col = GREY
                y   = y_start
            else:
                col = INK
                y   = y_start

            x = _draw_text(draw, word + " ", x, y, sz, col)
            wi += 1

        y_start += lh
        if y_start > H - 80:
            break

    # Blinking cursor after last visible word
    if visible < len(all_words):
        if (word_pop_frame // 12) % 2 == 0:
            ch_h = draw.textbbox((0, 0), "ம", font=_font("ta", sz))[3]
            draw.rectangle([x + 4, y_start - lh,
                            x + 10, y_start - lh + ch_h], fill=INK)

    # ── Ken Burns zoom ────────────────────────────────────────────────
    return _apply_ken_burns(frame, scene_progress)


def render_scene_frames(
    beat_narration:  str,
    image_panel:     Image.Image,
    duration_s:      float,
    word_timings:    list,        # List[WordTiming]
    fps:             int = 12,
) -> List[np.ndarray]:
    """Render all frames for one scene. Returns list of numpy arrays."""
    words        = beat_narration.split()
    total_frames = max(int(duration_s * fps), fps * 2)
    frames: List[np.ndarray] = []
    prev_visible = 0
    word_pop_frame = 999

    for fi in range(total_frames):
        current_ms    = int(fi / fps * 1000)
        progress      = fi / max(total_frames - 1, 1)
        image_progress = min(1.0, progress * 1.5)   # image reveals in first 2/3

        # Word visibility from timing
        if word_timings:
            visible = sum(1 for t in word_timings if t.start_ms <= current_ms)
            visible = max(1, min(visible, len(words)))
        else:
            visible = max(1, min(len(words), int(current_ms / 350) + 1))

        if visible > prev_visible:
            word_pop_frame = 0
        else:
            word_pop_frame += 1
        prev_visible = visible

        pil = render_frame(
            all_words      = words,
            visible        = visible,
            image_panel    = image_panel,
            image_progress = image_progress,
            scene_progress = progress,
            word_pop_frame = word_pop_frame,
        )
        frames.append(np.array(pil.convert("RGB")))

    return frames


def render_transition(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    t:       float,
    style:   str = "cut",
) -> np.ndarray:
    """Transition between scenes. AE uses hard cuts or quick wipes."""
    if style == "cut" or t >= 0.5:
        return frame_b
    if style == "wipe":
        w = frame_a.shape[1]
        split = int(w * t * 2)
        out = frame_a.copy()
        out[:, :split] = frame_b[:, :split]
        return out
    # Fast dissolve (0.3s)
    return (frame_a * (1 - t * 2) + frame_b * (t * 2)).clip(0, 255).astype(np.uint8)
