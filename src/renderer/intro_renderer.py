"""Thulir channel intro renderer.

Renders a 3.5s branded intro card before every video:

Layout:
  - Full frame: BRAND_WHITE background with subtle green gradient bottom edge
  - Center: Channel name "துளிர்" in large Tamil font, BRAND_PRIMARY green
  - Below: Tagline in smaller font, BRAND_GREY
  - Bottom strip: BRAND_PRIMARY green bar with channel handle "@thulir"
  - Animation: text fades + slides up over 1s, holds 2s, fades out 0.5s

Also renders a lower-third name card for first 4 seconds of each beat
showing who is being talked about.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080

# Import brand colors — fallback inline if brand module not found yet
try:
    from src.renderer.brand import (
        BG, INK, PRIMARY, SECONDARY, DARK, LIGHT, ACCENT, GREY, WHITE,
        INTRO_FRAMES, INTRO_FPS, LOWER_THIRD_H,
    )
except ImportError:
    BG        = (250, 255, 248)
    INK       = (18,  35,  26)
    PRIMARY   = (45, 106, 79)
    SECONDARY = (149, 213, 178)
    DARK      = (27,  67,  50)
    LIGHT     = (216, 243, 220)
    ACCENT    = (255, 183,  3)
    GREY      = (107, 143, 113)
    WHITE     = (255, 255, 255)
    INTRO_FRAMES = 42
    INTRO_FPS    = 12
    LOWER_THIRD_H = 80

_FC: dict = {}
_TA_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
]
_EN_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]

def _font(script: str, size: int) -> ImageFont.FreeTypeFont:
    import os
    k = (script, size)
    if k not in _FC:
        paths = _TA_PATHS if script == "ta" else _EN_PATHS
        for p in paths:
            if os.path.exists(p):
                try:
                    _FC[k] = ImageFont.truetype(p, size)
                    break
                except Exception:
                    continue
        if k not in _FC:
            _FC[k] = ImageFont.load_default()
    return _FC[k]


def _ease_out(t: float) -> float:
    """Ease-out cubic."""
    return 1 - (1 - t) ** 3


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


# ── Intro card ────────────────────────────────────────────────────────

def render_intro_frames(
    channel_name_ta: str = "துளிர்",
    tagline_ta: str = "உண்மையான கதைகள். உண்மையான பாடங்கள்.",
    handle: str = "@thulir",
    topic_ta: str = "",
) -> List[np.ndarray]:
    """Render branded 3.5s intro. Returns list of numpy frames."""
    frames = []

    for fi in range(INTRO_FRAMES):
        progress = fi / max(INTRO_FRAMES - 1, 1)

        # Animation phases
        # 0.0–0.25: fade + slide in
        # 0.25–0.80: hold
        # 0.80–1.0: fade out
        if progress < 0.25:
            alpha = _ease_out(progress / 0.25)
            slide_y = int((1 - _ease_out(progress / 0.25)) * 60)
        elif progress < 0.80:
            alpha = 1.0
            slide_y = 0
        else:
            alpha = 1.0 - _ease_in_out((progress - 0.80) / 0.20)
            slide_y = 0

        frame = _draw_intro_frame(
            channel_name_ta, tagline_ta, handle, topic_ta,
            alpha=alpha, slide_y=slide_y
        )
        frames.append(np.array(frame.convert("RGB")))

    return frames


def _draw_intro_frame(
    channel_name_ta: str,
    tagline_ta: str,
    handle: str,
    topic_ta: str,
    alpha: float,
    slide_y: int,
) -> Image.Image:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Green gradient wash at bottom ──────────────────────────────
    for y in range(H - 200, H):
        t = (y - (H - 200)) / 200
        r = int(BG[0] * (1 - t) + LIGHT[0] * t)
        g = int(BG[1] * (1 - t) + LIGHT[1] * t)
        b = int(BG[2] * (1 - t) + LIGHT[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── Thin green top accent line ──────────────────────────────────
    for i in range(6):
        shade = tuple(max(0, c - i * 8) for c in PRIMARY)
        draw.line([(0, i), (W, i)], fill=shade)

    # ── Decorative green circle (left) ─────────────────────────────
    circle_x = W // 4
    circle_y = H // 2 + slide_y
    circle_r = 320
    for dr in range(circle_r, circle_r - 12, -1):
        t = (circle_r - dr) / 12
        col = tuple(int(LIGHT[c] + (BG[c] - LIGHT[c]) * t) for c in range(3))
        draw.ellipse([circle_x - dr, circle_y - dr, circle_x + dr, circle_y + dr],
                     fill=col)

    # ── Vertical green accent bar (left edge of text zone) ─────────
    bar_x = W // 2 - 20
    draw.rectangle([bar_x, H // 2 - 160 + slide_y,
                    bar_x + 8, H // 2 + 120 + slide_y], fill=PRIMARY)

    # ── Channel name ────────────────────────────────────────────────
    name_size = 180
    name_font = _font("ta", name_size)
    name_bbox = draw.textbbox((0, 0), channel_name_ta, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_x = (W - name_w) // 2
    name_y = H // 2 - 180 + slide_y

    # Shadow
    if alpha > 0.1:
        shadow_col = tuple(max(0, c - 30) for c in LIGHT)
        draw.text((name_x + 4, name_y + 4), channel_name_ta, font=name_font, fill=shadow_col)
    # Main text
    col = _alpha_blend(PRIMARY, BG, alpha)
    draw.text((name_x, name_y), channel_name_ta, font=name_font, fill=col)

    # ── Tagline ─────────────────────────────────────────────────────
    tag_size = 52
    tag_font = _font("ta", tag_size)
    tag_bbox = draw.textbbox((0, 0), tagline_ta, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_x = (W - tag_w) // 2
    tag_y = name_y + name_bbox[3] - name_bbox[1] + 24 + slide_y
    col_tag = _alpha_blend(GREY, BG, alpha)
    draw.text((tag_x, tag_y), tagline_ta, font=tag_font, fill=col_tag)

    # ── Topic teaser (if provided) ──────────────────────────────────
    if topic_ta:
        tease_size = 44
        tease_font = _font("ta", tease_size)
        tease_text = f"இன்றைய கதை: {topic_ta[:40]}"
        tease_bbox = draw.textbbox((0, 0), tease_text, font=tease_font)
        tease_w = tease_bbox[2] - tease_bbox[0]
        tease_x = (W - tease_w) // 2
        tease_y = tag_y + 80 + slide_y
        col_tease = _alpha_blend(DARK, BG, alpha * 0.85)
        draw.text((tease_x, tease_y), tease_text, font=tease_font, fill=col_tease)

    # ── Bottom strip ─────────────────────────────────────────────────
    strip_y = H - 80
    strip_alpha = _alpha_blend(PRIMARY, BG, alpha)
    draw.rectangle([0, strip_y, W, H], fill=strip_alpha)

    # Handle text in strip
    handle_font = _font("en", 38)
    handle_bbox = draw.textbbox((0, 0), handle, font=handle_font)
    handle_w = handle_bbox[2] - handle_bbox[0]
    draw.text(
        ((W - handle_w) // 2, strip_y + 20),
        handle, font=handle_font, fill=WHITE
    )

    # ── Green dot pattern (subtle texture) ─────────────────────────
    import random
    rng = random.Random(42)
    for _ in range(20):
        dx = rng.randint(50, W - 50)
        dy = rng.randint(50, H - 150)
        dr = rng.randint(3, 8)
        dot_col = _alpha_blend(SECONDARY, BG, alpha * 0.3)
        draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=dot_col)

    return img


def _alpha_blend(fg: tuple, bg: tuple, alpha: float) -> tuple:
    return tuple(int(bg[i] + (fg[i] - bg[i]) * alpha) for i in range(3))


# ── Lower third name card ─────────────────────────────────────────────

def render_lower_third(
    frame: Image.Image,
    protagonist: str,
    subtitle: str,
    beat_frame: int,
    total_beat_frames: int,
    fps: int = 12,
) -> Image.Image:
    """Overlay a branded lower-third onto an existing frame.

    Shows for first 4 seconds of each beat (except hook — shown longer).
    Slides up from bottom, fades out after 3s.
    """
    visible_frames = min(fps * 4, total_beat_frames - fps)
    if beat_frame > visible_frames or not protagonist:
        return frame

    # Animation
    if beat_frame < fps * 0.4:
        t = beat_frame / (fps * 0.4)
        alpha = _ease_out(t)
        slide = int((1 - _ease_out(t)) * 40)
    elif beat_frame < visible_frames - fps * 0.5:
        alpha = 1.0
        slide = 0
    else:
        remain = visible_frames - beat_frame
        alpha = remain / (fps * 0.5)
        slide = 0

    if alpha < 0.05:
        return frame

    overlay = frame.copy()
    draw = ImageDraw.Draw(overlay)

    # Strip background
    strip_y = H - LOWER_THIRD_H - 20 + slide
    strip_col = _alpha_blend(PRIMARY, (0, 0, 0), 0.88)
    draw.rectangle([0, strip_y, W, strip_y + LOWER_THIRD_H], fill=strip_col)

    # Left accent bar
    draw.rectangle([0, strip_y, 6, strip_y + LOWER_THIRD_H], fill=ACCENT)

    # Protagonist name
    name_font = _font("en" if protagonist.isascii() else "ta", 42)
    draw.text((30, strip_y + 10), protagonist, font=name_font, fill=WHITE)

    # Subtitle (role/context)
    if subtitle:
        sub_font = _font("en" if subtitle.isascii() else "ta", 30)
        sub_bbox = draw.textbbox((0, 0), protagonist, font=name_font)
        sub_x = 30 + sub_bbox[2] + 20
        draw.text((sub_x, strip_y + 22), f"• {subtitle}", font=sub_font,
                  fill=_alpha_blend(SECONDARY, PRIMARY, 0.8))

    # Blend with original
    blended = Image.blend(frame, overlay, alpha)
    return blended


# ── Green theme frame tint ────────────────────────────────────────────

def apply_green_tint(frame: Image.Image, strength: float = 0.04) -> Image.Image:
    """Apply a very subtle green tint to every frame for visual consistency."""
    if strength <= 0:
        return frame
    overlay = Image.new("RGB", frame.size, LIGHT)
    return Image.blend(frame, overlay, strength)
