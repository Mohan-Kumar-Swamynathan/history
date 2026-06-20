"""Thulir intro renderer — matches exact channel branding.

Banner aesthetic:
  - Warm cream/golden sky background (like the banner)
  - Deep forest green brush stroke on left (like banner)
  - "துளிர்" in dark forest green, same weight as banner lettering
  - Leaf/sprout SVG on right (like banner)
  - Tagline in mid-green
  - Bottom dark green strip with @thulir handle
"""

from __future__ import annotations
import math, os
from typing import List
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080

try:
    from src.renderer.brand import (
        PRIMARY, DARK, MID, LEAF, CREAM, LIGHT, BG, ACCENT,
        INK, GREY, WHITE, INTRO_FRAMES, INTRO_FPS, LOWER_THIRD_H,
    )
except ImportError:
    PRIMARY = (29, 48, 16); DARK = (29, 51, 11); MID = (81, 117, 18)
    LEAF = (114, 140, 15); CREAM = (244, 235, 191); LIGHT = (237, 247, 224)
    BG = (250, 250, 240); ACCENT = (212, 175, 55); INK = (26, 46, 8)
    GREY = (107, 124, 74); WHITE = (255, 255, 255)
    INTRO_FRAMES = 42; INTRO_FPS = 12; LOWER_THIRD_H = 80

_FC = {}
_TA = ["/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
       "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"]
_EN = ["/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
       "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"]

def _font(sc, sz):
    k = (sc, sz)
    if k not in _FC:
        for p in (_TA if sc=="ta" else _EN):
            if os.path.exists(p):
                try: _FC[k] = ImageFont.truetype(p, sz); break
                except: pass
        if k not in _FC: _FC[k] = ImageFont.load_default()
    return _FC[k]

def _segs(text):
    """Split text into (segment, script) for per-character font switching."""
    out, cur, ct = [], "", None
    for ch in text:
        t = "ta" if (0x0B80 <= ord(ch) <= 0x0BFF) else "en"
        if t != ct and cur:
            out.append((cur, ct)); cur = ""
        cur += ch; ct = t
    if cur: out.append((cur, ct))
    return out

def _draw_mixed(draw, text, x, y, sz, col, shadow_col=None):
    """Draw mixed Tamil+English text with correct font per segment — no boxes."""
    cx = x
    for seg, sc in _segs(text):
        f = _font(sc, sz)
        if shadow_col:
            draw.text((cx+2, y+2), seg, font=f, fill=shadow_col)
        draw.text((cx, y), seg, font=f, fill=col)
        cx += draw.textbbox((0,0), seg, font=f)[2]
    return cx

def _measure_mixed(draw, text, sz):
    """Measure width of mixed Tamil+English text."""
    w = 0
    for seg, sc in _segs(text):
        w += draw.textbbox((0,0), seg, font=_font(sc, sz))[2]
    return w

def _ab(fg, bg, a): return tuple(int(bg[i]+(fg[i]-bg[i])*a) for i in range(3))
def _eo(t): return 1-(1-t)**3
def _eio(t): return t*t*(3-2*t)


def _draw_brush_stroke(draw, alpha):
    """Replicate the dark green brush stroke from the banner left side."""
    # Jagged brush stroke shape — left portion
    pts = [(0,0),(320,0),(380,80),(300,180),(360,280),(280,380),
           (340,480),(260,580),(320,680),(240,780),(300,880),(220,980),(0,1080)]
    col = _ab(PRIMARY, BG, alpha)
    draw.polygon(pts, fill=col)
    # Inner lighter green layer
    pts2 = [(0,0),(200,0),(240,100),(180,200),(220,320),(160,440),
            (200,560),(140,680),(180,800),(120,920),(160,1080),(0,1080)]
    inner = _ab(DARK, BG, alpha*0.7)
    draw.polygon(pts2, fill=inner)


def _draw_leaf_sprout(draw, x, y, size, alpha):
    """Draw the leaf sprout motif from the channel branding."""
    # Stem
    col_stem = _ab(MID, BG, alpha)
    draw.line([(x, y+size), (x, y+size//3)], fill=col_stem, width=max(3, size//18))
    # Left leaf
    col_leaf = _ab(LEAF, BG, alpha)
    lx, ly = x - size//3, y + size//4
    draw.ellipse([lx-size//3, ly-size//2, lx+size//6, ly+size//6],
                 fill=col_leaf, outline=_ab(MID, BG, alpha*0.8), width=2)
    # Right leaf (bigger, like the banner)
    rx, ry = x + size//6, y
    draw.ellipse([rx-size//6, ry-size//2, rx+size//2, ry+size//3],
                 fill=col_leaf, outline=_ab(MID, BG, alpha*0.8), width=2)
    # Tip bud
    draw.ellipse([x-size//8, y-size//4, x+size//8, y+size//8],
                 fill=_ab(MID, BG, alpha))


def render_intro_frames(
    channel_name_ta="துளிர்",
    tagline_ta="துளிர் இன்று… வளர்ச்சி நாளை.",
    handle="@thulir",
    topic_ta="",
) -> List[np.ndarray]:
    frames = []
    for fi in range(INTRO_FRAMES):
        p = fi / max(INTRO_FRAMES-1, 1)
        if p < 0.25:
            alpha = _eo(p/0.25); slide = int((1-_eo(p/0.25))*70)
        elif p < 0.82:
            alpha = 1.0; slide = 0
        else:
            alpha = 1.0-_eio((p-0.82)/0.18); slide = 0
        frames.append(np.array(_draw_intro(
            channel_name_ta, tagline_ta, handle, topic_ta, alpha, slide
        ).convert("RGB")))
    return frames


def _draw_intro(name_ta, tagline_ta, handle, topic_ta, alpha, slide):
    img = Image.new("RGB", (W, H), BG)

    # ── Warm cream gradient background (like banner sky) ─────────
    import numpy as np_
    arr = np_.array(img, dtype=np_.float32)
    for y in range(H):
        t = y/H
        # Blend from warm cream at top to light green tint at bottom
        top = np_.array(CREAM, dtype=np_.float32)
        bot = np_.array(LIGHT, dtype=np_.float32)
        arr[y] = top*(1-t) + bot*t
    img = Image.fromarray(arr.clip(0,255).astype(np_.uint8))

    draw = ImageDraw.Draw(img)

    # ── Dark green brush stroke LEFT ──────────────────────────────
    _draw_brush_stroke(draw, alpha)

    # ── Leaf sprout TOP RIGHT ─────────────────────────────────────
    sprout_x = int(W * 0.82)
    sprout_y = int(H * 0.15) + slide
    _draw_leaf_sprout(draw, sprout_x, sprout_y, 220, alpha)

    # ── Thin horizontal rule ──────────────────────────────────────
    rule_y = H//2 + 120 + slide
    rule_col = _ab(MID, CREAM, alpha*0.4)
    draw.line([(420, rule_y), (W-120, rule_y)], fill=rule_col, width=3)

    # ── Channel name "துளிர்" ─────────────────────────────────────
    name_sz = 200
    nf = _font("ta", name_sz)
    nw = _measure_mixed(draw, name_ta, name_sz)
    nb = [0, 0, nw, name_sz+10]  # approximate
    nx = 420
    ny = H//2 - 190 + slide
    # Shadow
    shadow = _ab(DARK, CREAM, alpha*0.25)
    _draw_mixed(draw, name_ta, nx, ny, name_sz, _ab(DARK, CREAM, alpha), shadow_col=_ab(DARK, CREAM, alpha*0.2))

    # ── Tagline ───────────────────────────────────────────────────
    tag_sz = 54
    tf = _font("ta", tag_sz)
    tw = _measure_mixed(draw, tagline_ta, tag_sz)
    ty = ny + (nb[3]-nb[1]) + 28 + slide
    _draw_mixed(draw, tagline_ta, nx, ty, tag_sz, _ab(MID, CREAM, alpha))

    # ── Topic teaser ──────────────────────────────────────────────
    if topic_ta:
        tease_sz = 42
        tease_f = _font("ta", tease_sz)
        tease = f"இன்றைய கதை: {topic_ta[:38]}"
        t2y = ty + (tb[3]-tb[1]) + 30 + slide
        _draw_mixed(draw, tease, nx, t2y, tease_sz, _ab(INK, CREAM, alpha*0.75))

    # ── Bottom strip (dark green like banner left) ────────────────
    strip_y = H - 88
    strip_col = _ab(PRIMARY, BG, alpha)
    draw.rectangle([0, strip_y, W, H], fill=strip_col)
    # Gold left accent bar
    draw.rectangle([0, strip_y, 8, H], fill=_ab(ACCENT, PRIMARY, alpha))
    # Handle text
    hf = _font("en", 40)
    hb = draw.textbbox((0,0), handle, font=hf)
    hx = (W - (hb[2]-hb[0])) // 2
    col_h = _ab(WHITE, PRIMARY, alpha)
    draw.text((hx, strip_y+22), handle, font=hf, fill=col_h)

    # Soft vignette blur on edges
    img = img.filter(ImageFilter.SMOOTH_MORE)
    return img


# ── Lower-third name card ─────────────────────────────────────────────

def render_lower_third(frame, protagonist, subtitle, beat_frame,
                       total_beat_frames, fps=12):
    # Only show for first 3s of beat — skip early for speed
    visible = min(fps*3, total_beat_frames//2)
    if beat_frame > visible or not protagonist:
        return frame  # fast path — no PIL operations
    if beat_frame < fps*0.4:
        a = _eo(beat_frame/(fps*0.4)); slide=int((1-_eo(beat_frame/(fps*0.4)))*35)
    elif beat_frame < visible - fps*0.5:
        a = 1.0; slide=0
    else:
        a = max(0,(visible-beat_frame)/(fps*0.5)); slide=0
    if a < 0.05: return frame
    ov = frame.copy(); draw = ImageDraw.Draw(ov)
    sy = H - LOWER_THIRD_H - 20 + slide
    # Strip
    sc = _ab(PRIMARY, (0,0,0), 0.92)
    draw.rectangle([0, sy, W, sy+LOWER_THIRD_H], fill=sc)
    # Gold bar
    draw.rectangle([0, sy, 7, sy+LOWER_THIRD_H], fill=ACCENT)
    # Name
    sc2 = "en" if protagonist.isascii() else "ta"
    nf2 = _font(sc2, 44)
    draw.text((28, sy+10), protagonist, font=nf2, fill=WHITE)
    # Subtitle
    if subtitle:
        sf = _font("en" if subtitle.isascii() else "ta", 30)
        sb = draw.textbbox((0,0), protagonist, font=nf2)
        sx2 = 28+(sb[2]-sb[0])+18
        draw.text((sx2, sy+22), f"• {subtitle}", font=sf,
                  fill=_ab(LEAF, PRIMARY, 0.9))
    from PIL import Image as PILImage
    return PILImage.blend(frame, ov, a)


def apply_green_tint(frame, strength=0.035):
    """Subtle warm-cream tint matching brand background."""
    ov = Image.new("RGB", frame.size, CREAM)
    return Image.blend(frame, ov, strength)
