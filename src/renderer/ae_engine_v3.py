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

try:
    from src.renderer.effects_engine import (
        apply_stop_motion_effects,
        apply_flipbook_transition,
    )
    _EFFECTS_AVAILABLE = True
except ImportError:
    _EFFECTS_AVAILABLE = False

W, H = 1920, 1080

# Layout constants
TEXT_X      = 60
TEXT_MAX_W  = 820
TEXT_TOP    = 80
IMAGE_X     = 940
IMAGE_W     = W - IMAGE_X - 30
IMAGE_H     = H - 80
IMAGE_Y     = 40

# Brand colors — imported from brand.py, fallback inline
try:
    from src.renderer.brand import BG, INK, PRIMARY, SECONDARY, GREY, ACCENT, LIGHT
    RED     = ACCENT     # use brand gold as highlight word color
    DIVIDER = LIGHT      # use light green as divider
except ImportError:
    BG      = (250, 255, 248)   # off-white with green tint
    INK     = (18,  35,  26)    # near-black with green tint
    PRIMARY = (45, 106,  79)    # brand green
    SECONDARY=(149,213, 178)    # light mint
    GREY    = (107, 143, 113)   # muted green-grey
    ACCENT  = (255, 183,   3)   # warm gold highlight
    LIGHT   = (216, 243, 220)   # very light green
    RED     = ACCENT
    DIVIDER = LIGHT

# Tamil font sizes — AE uses big, confident text
FONT_SIZES  = [130, 108, 90, 76, 64, 54]

_FONT_CACHE: dict = {}

# Tamil Unicode range
_TA_START, _TA_END = 0x0B80, 0x0BFF

TAMIL_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
]
LATIN_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def _resolve_font_path(paths: list) -> str:
    import os
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]  # let truetype raise the real error

def _font(script: str, size: int) -> ImageFont.FreeTypeFont:
    key = (script, size)
    if key not in _FONT_CACHE:
        path = _resolve_font_path(TAMIL_FONT_PATHS if script == "ta" else LATIN_FONT_PATHS)
        try:
            _FONT_CACHE[key] = ImageFont.truetype(path, size)
        except Exception:
            try:
                # Last resort: any available font
                import subprocess
                result = subprocess.run(["fc-list", "--format=%{file}\n", ":lang=ta"],
                                        capture_output=True, text=True)
                fallback = result.stdout.strip().splitlines()
                if fallback and script == "ta":
                    _FONT_CACHE[key] = ImageFont.truetype(fallback[0], size)
                else:
                    _FONT_CACHE[key] = ImageFont.load_default()
            except Exception:
                _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def _is_tamil(ch: str) -> bool:
    return _TA_START <= ord(ch) <= _TA_END


def _segment_text(text: str) -> list[tuple[str, str]]:
    """Split text into (segment, script) pairs for character-accurate rendering.
    e.g. "Rathina-கிடைத்தது" → [("Rathina-", "en"), ("கிடைத்தது", "ta")]
    """
    if not text:
        return []
    segments = []
    cur = ""
    cur_script = "ta" if _is_tamil(text[0]) else "en"
    for ch in text:
        ch_script = "ta" if _is_tamil(ch) else "en"
        if ch_script != cur_script:
            if cur:
                segments.append((cur, cur_script))
            cur = ch
            cur_script = ch_script
        else:
            cur += ch
    if cur:
        segments.append((cur, cur_script))
    return segments


def _text_width(draw: ImageDraw.ImageDraw, text: str, size: int) -> int:
    """Measure text width with per-segment font switching."""
    total = 0
    for seg, sc in _segment_text(text):
        total += draw.textbbox((0, 0), seg, font=_font(sc, size))[2]
    return total


def _draw_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
               size: int, color: tuple) -> int:
    """Draw text with per-character font switching — no more boxes."""
    cx = x
    for seg, sc in _segment_text(text):
        f = _font(sc, size)
        draw.text((cx, y), seg, font=f, fill=color)
        cx += draw.textbbox((0, 0), seg, font=f)[2]
    return cx


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
        # Apply subtle green brand tint
    try:
        from src.renderer.intro_renderer import apply_green_tint
        frame = apply_green_tint(frame, strength=0.04)
    except ImportError:
        pass
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
    scene_idx:       int = 0,
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
        frame_arr = np.array(pil.convert("RGB"))

        # Stop-motion effects stack
        if _EFFECTS_AVAILABLE:
            frame_arr = apply_stop_motion_effects(
                frame          = frame_arr,
                frame_index    = fi,
                scene_index    = scene_idx,
                scene_progress = progress,
                word_just_appeared = (visible > prev_visible),
                word_age_frames    = word_pop_frame,
                # Chalk exit in last 8% of scene
                exit_progress  = max(0.0, (progress - 0.92) / 0.08),
                enable_chalk_exit = (progress > 0.92),
            )
        frames.append(frame_arr)

    return frames


def render_transition(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    t:       float,
    style:   str = "flipbook",
) -> np.ndarray:
    """Transitions between scenes.
    flipbook: vertical page-peel (default) — most physical/real feel
    wipe:     horizontal sweep
    cut:      instant
    dissolve: crossfade
    """
    if style == "cut" or t >= 1.0:
        return frame_b
    if style == "flipbook" and _EFFECTS_AVAILABLE:
        return apply_flipbook_transition(frame_a, frame_b, t)
    if style == "wipe":
        w = frame_a.shape[1]
        split = int(w * t)
        out = frame_a.copy()
        out[:, :split] = frame_b[:, :split]
        return out
    # Dissolve
    return (frame_a * (1 - t) + frame_b * t).clip(0, 255).astype(np.uint8)
