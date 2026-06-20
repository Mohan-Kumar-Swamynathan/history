"""Stop-motion & kinetic effects engine for Thulir whiteboard videos.

Achieves hand-made, physical paper feeling through:
  1. Frame jitter        — ±3px random xy shift every N frames (stop-motion heartbeat)
  2. Paper grain         — per-frame gaussian noise (organic texture)
  3. Camera micro-shake  — ±4px slow drift (handheld feel)
  4. Ink bleed           — new word blurs inward over 3 frames (pen on paper)
  5. Flip-book transition — vertical page-peel between scenes
  6. Chalk dust exit     — scene-end radial blur (eraser smear)
  7. Vignette            — subtle dark corners (physical photo feel)

All effects are deterministic given frame_index + scene_index for reproducibility.
Performance: all numpy/PIL, no external libs, <2ms per frame on CI.
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter


# ── Tuneable constants ────────────────────────────────────────────────
JITTER_PX          = 2      # reduced for CI speed
JITTER_EVERY_N     = 4      # less frequent for CI speed
GRAIN_STRENGTH     = 0.0    # DISABLED on CI — most expensive effect
SHAKE_MAX_PX       = 3      # reduced for CI speed
SHAKE_SPEED        = 0.7
INK_BLEED_FRAMES   = 3
INK_BLUR_RADIUS    = 1.5    # lighter blur for CI speed
VIGNETTE_STRENGTH  = 0.12   # lighter vignette for CI speed
CHALK_BLUR_FRAMES  = 4

# CI mode: disable grain (numpy random per-frame is slow at 2100 frames)
import os as _os
_CI_MODE = _os.environ.get("GITHUB_ACTIONS", "false") == "true"
if _CI_MODE:
    GRAIN_STRENGTH = 0.0   # disable grain on CI


# ── Vignette (precomputed once) ───────────────────────────────────────
_VIGNETTE_CACHE: Optional[np.ndarray] = None

def _get_vignette(h: int, w: int) -> np.ndarray:
    global _VIGNETTE_CACHE
    if _VIGNETTE_CACHE is not None and _VIGNETTE_CACHE.shape[:2] == (h, w):
        return _VIGNETTE_CACHE
    # Radial gradient — dark corners, bright centre
    cy, cx = h / 2, w / 2
    Y, X   = np.ogrid[:h, :w]
    dist   = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    mask   = np.clip(dist - 0.55, 0, 0.7) / 0.7   # feather from 55%
    vignette = (1.0 - mask * VIGNETTE_STRENGTH)
    _VIGNETTE_CACHE = vignette[:, :, np.newaxis].astype(np.float32)
    return _VIGNETTE_CACHE


# ── 1. Frame jitter ───────────────────────────────────────────────────
def apply_jitter(frame: np.ndarray, frame_index: int, scene_index: int) -> np.ndarray:
    """Shift entire frame ±JITTER_PX randomly — stop-motion heartbeat."""
    if frame_index % JITTER_EVERY_N != 0:
        return frame
    rng = random.Random(scene_index * 10000 + frame_index)
    dx = rng.randint(-JITTER_PX, JITTER_PX)
    dy = rng.randint(-JITTER_PX, JITTER_PX)
    if dx == 0 and dy == 0:
        return frame
    return np.roll(np.roll(frame, dy, axis=0), dx, axis=1)


# ── 2. Paper grain ────────────────────────────────────────────────────
def apply_grain(frame: np.ndarray, frame_index: int, strength: float = GRAIN_STRENGTH) -> np.ndarray:
    """Add per-frame gaussian noise simulating paper texture."""
    rng = np.random.default_rng(frame_index * 7 + 13)
    noise = rng.normal(0, strength, frame.shape).astype(np.float32)
    result = frame.astype(np.float32) + noise
    return np.clip(result, 0, 255).astype(np.uint8)


# ── 3. Camera micro-shake ─────────────────────────────────────────────
def apply_micro_shake(
    frame: np.ndarray,
    frame_index: int,
    scene_index: int,
    scene_progress: float,
) -> np.ndarray:
    """Slow organic camera drift — different from jitter (smooth, not random)."""
    # Lissajous-style smooth path — organic feel
    t     = scene_progress * 2 * np.pi * SHAKE_SPEED
    seed  = scene_index * 17
    amp_x = SHAKE_MAX_PX * np.sin(t * 1.3 + seed)
    amp_y = SHAKE_MAX_PX * np.cos(t * 0.9 + seed + 1.1)
    dx    = int(amp_x * 0.6)   # reduced — subtle
    dy    = int(amp_y * 0.4)
    if dx == 0 and dy == 0:
        return frame
    h, w = frame.shape[:2]
    canvas = frame.copy()
    # Crop and shift — no roll (avoids wrap-around artifacts)
    sx = max(0, dx); ex = w + min(0, dx)
    sy = max(0, dy); ey = h + min(0, dy)
    src_sx = max(0, -dx); src_ex = w - max(0, dx)
    src_sy = max(0, -dy); src_ey = h - max(0, dy)
    if ex > sx and ey > sy:
        canvas[sy:ey, sx:ex] = frame[src_sy:src_ey, src_sx:src_ex]
    return canvas


# ── 4. Ink bleed (new word entry) ─────────────────────────────────────
def apply_ink_bleed(
    frame: np.ndarray,
    word_bbox: Optional[Tuple[int, int, int, int]],
    word_age_frames: int,
) -> np.ndarray:
    """Blur the newest word region for first INK_BLEED_FRAMES frames.

    word_bbox: (x1, y1, x2, y2) in pixels
    word_age_frames: how many frames since word appeared (0 = just appeared)
    """
    if word_bbox is None or word_age_frames >= INK_BLEED_FRAMES:
        return frame
    # Blur strength decreases as word ages
    strength = INK_BLUR_RADIUS * (1.0 - word_age_frames / INK_BLEED_FRAMES)
    if strength < 0.3:
        return frame

    x1, y1, x2, y2 = word_bbox
    # Clamp to frame bounds
    h, w = frame.shape[:2]
    x1 = max(0, x1 - 8); y1 = max(0, y1 - 8)
    x2 = min(w, x2 + 8); y2 = min(h, y2 + 8)
    if x2 <= x1 or y2 <= y1:
        return frame

    pil  = Image.fromarray(frame)
    region = pil.crop((x1, y1, x2, y2))
    # Expand + blur + contract (cheap ink spread simulation)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=strength))
    pil.paste(blurred, (x1, y1))
    return np.array(pil)


# ── 5. Flip-book page-turn transition ────────────────────────────────
def apply_flipbook_transition(
    frame_a: np.ndarray,
    frame_b: np.ndarray,
    progress: float,   # 0.0 → 1.0
) -> np.ndarray:
    """Vertical page-peel — top of next scene peels down over current scene.

    More physical than crossfade — like flipping a whiteboard notepad.
    """
    h, w = frame_a.shape[:2]
    split_y = int(h * progress)

    if split_y <= 0:
        return frame_a
    if split_y >= h:
        return frame_b

    result = frame_a.copy()

    # Top portion: frame_b (new scene revealed)
    result[:split_y, :] = frame_b[:split_y, :]

    # Shadow line at the fold — dark horizontal stripe
    shadow_h = min(8, h - split_y)
    if shadow_h > 0:
        shadow_strength = np.linspace(0.45, 0.0, shadow_h)[:, np.newaxis, np.newaxis]
        result[split_y:split_y + shadow_h, :] = (
            result[split_y:split_y + shadow_h, :].astype(np.float32)
            * (1.0 - shadow_strength)
        ).astype(np.uint8)

    # Slight curl effect — bottom of revealed section slightly lighter
    curl_h = min(12, split_y)
    if curl_h > 0:
        curl_strength = np.linspace(0.12, 0.0, curl_h)[:, np.newaxis, np.newaxis]
        result[split_y - curl_h:split_y, :] = np.clip(
            result[split_y - curl_h:split_y, :].astype(np.float32)
            + 255 * curl_strength,
            0, 255
        ).astype(np.uint8)

    return result


# ── 6. Chalk-dust exit smear ──────────────────────────────────────────
def apply_chalk_exit(frame: np.ndarray, exit_progress: float) -> np.ndarray:
    """Radial blur outward as scene ends — like erasing a whiteboard.

    exit_progress: 0.0 (just started) → 1.0 (fully erased)
    """
    if exit_progress <= 0 or exit_progress >= 1.0:
        return frame

    pil = Image.fromarray(frame)

    # Progressive blur
    blur_r = exit_progress * 4.0
    blurred = pil.filter(ImageFilter.GaussianBlur(radius=blur_r))

    # Blend towards brand cream background
    try:
        from src.renderer.brand import CREAM
    except ImportError:
        CREAM = (244, 235, 191)

    white_overlay = Image.new("RGB", pil.size, CREAM)
    result = Image.blend(blurred, white_overlay, exit_progress * 0.35)
    return np.array(result)


# ── 7. Vignette ───────────────────────────────────────────────────────
def apply_vignette(frame: np.ndarray) -> np.ndarray:
    """Subtle dark corners — physical photo / film feel."""
    h, w = frame.shape[:2]
    vig  = _get_vignette(h, w)
    result = (frame.astype(np.float32) * vig).clip(0, 255).astype(np.uint8)
    return result


# ── Composer — apply all effects in order ────────────────────────────
def apply_stop_motion_effects(
    frame:              np.ndarray,
    frame_index:        int,
    scene_index:        int,
    scene_progress:     float,
    word_just_appeared: bool = False,
    word_bbox:          Optional[Tuple[int, int, int, int]] = None,
    word_age_frames:    int  = 999,
    exit_progress:      float = 0.0,
    enable_grain:       bool  = True,
    enable_jitter:      bool  = True,
    enable_shake:       bool  = True,
    enable_ink_bleed:   bool  = True,
    enable_vignette:    bool  = True,
    enable_chalk_exit:  bool  = False,
) -> np.ndarray:
    """Apply the full stop-motion effect stack to a frame.

    Call this AFTER render_frame() and BEFORE encoding.
    Order matters — jitter last to avoid blurring the shift.
    """
    # 1. Chalk exit (early — before blur)
    if enable_chalk_exit and exit_progress > 0:
        frame = apply_chalk_exit(frame, exit_progress)

    # 2. Grain (paper texture) — skip if disabled
    if enable_grain and GRAIN_STRENGTH > 0:
        frame = apply_grain(frame, frame_index)

    # 3. Ink bleed on new words
    if enable_ink_bleed and word_bbox is not None:
        frame = apply_ink_bleed(frame, word_bbox, word_age_frames)

    # 4. Micro-shake (smooth organic drift)
    if enable_shake:
        frame = apply_micro_shake(frame, frame_index, scene_index, scene_progress)

    # 5. Vignette (subtle, before jitter so it stays anchored)
    if enable_vignette:
        frame = apply_vignette(frame)

    # 6. Frame jitter LAST (so it shifts the final composed frame)
    if enable_jitter:
        frame = apply_jitter(frame, frame_index, scene_index)

    return frame
