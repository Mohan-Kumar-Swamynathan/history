"""
Almost Everything style engine — Enhanced v2.

Key improvements over v1:
1. Progress bar strip at bottom (like AE) — visible story momentum
2. Scene emotion colour-wash on background (faint tint per emotion)
3. Word-pop animation: new word bounces in 6px up then settles
4. Handwritten underline sweeps under key words (red highlight)
5. Sparkle particles on celebrating / turning-point scenes
6. Pencil cursor stays visible longer during background drawing
7. Chapter label badge (HOOK / CONFLICT / LESSON) — 3s then fades
8. Figure emotion now maps to all 6 states correctly
9. Layout alternates left/right every other scene for variety
10. Clean paper texture line spacing stays whiteboard feel
"""
import re, io, math, random
from pathlib import Path
from typing import List, Tuple, Optional
import cairosvg
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W, H = 1920, 1080
WHITE = (255, 255, 255)
INK   = (20,  20,  20)
RED   = (205, 35,  25)
GREY  = (170, 170, 165)
FAINT = (238, 236, 230)

# Emotion washes (RGBA background tint)
EMOTION_WASH = {
    "sad":           (220, 235, 250, 18),   # cool blue wash
    "hope":          (220, 248, 228, 18),   # soft green
    "exciting":      (255, 248, 215, 20),   # warm amber
    "inspirational": (255, 248, 215, 20),
    "thinking":      (235, 228, 250, 16),   # light purple
    "celebrating":   (255, 244, 210, 22),   # golden
    "neutral":       (248, 248, 244, 12),
}

# Beat type labels shown briefly at scene start
BEAT_LABELS = {
    "hook":          ("HOOK 🎯",          (205,  35,  25)),
    "context":       ("SETUP 📖",         ( 45, 106,  79)),
    "conflict":      ("PROBLEM 😟",       (180,  70,  40)),
    "escalation":    ("STRUGGLE ⚡",      (180,  70,  40)),
    "turning_point": ("TURNING POINT 🔥", (205,  35,  25)),
    "resolution":    ("CHANGE ✅",        ( 34, 139,  34)),
    "lesson":        ("LESSON 💡",        ( 45, 106,  79)),
    "cta":           ("SUBSCRIBE 🔔",     ( 45, 106,  79)),
}

FONT_PATHS = {
    "ta":     "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "en":     "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "ta_reg": "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "en_reg": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
}
_FC = {}

def _f(k, s):
    if (k, s) not in _FC:
        try:
            from src.core.font_resolver import load_font
            script = "ta" if k in ("ta", "ta_reg") else "en"
            _FC[(k, s)] = load_font(s, script=script)
        except Exception:
            try:
                _FC[(k, s)] = ImageFont.truetype(FONT_PATHS.get(k, FONT_PATHS["ta"]), s)
            except Exception:
                _FC[(k, s)] = ImageFont.load_default()
    return _FC[(k, s)]

def _segs(text):
    out, cur, ct = [], "", None
    for ch in text:
        cp = ord(ch)
        t = "ta" if (0x0B80 <= cp <= 0x0BFF or ch in " .,!?₹%-:;'\"") else "en"
        if t != ct and cur: out.append((cur, ct)); cur = ""
        cur += ch; ct = t
    if cur: out.append((cur, ct))
    return out

def _tw(draw, text, sz):
    w = 0
    for seg, t in _segs(text):
        f = _f("ta" if t == "ta" else "en", sz)
        w += draw.textbbox((0,0), seg, font=f)[2]
    return w

def _dt(draw, text, x, y, sz, col, shadow: bool = False):
    cx = x
    if shadow:
        for seg, t in _segs(text):
            f = _f("ta" if t == "ta" else "en", sz)
            draw.text((cx+2, y+2), seg, font=f, fill=FAINT, anchor="lt")
            cx += draw.textbbox((0,0), seg, font=f)[2]
        cx = x
    for seg, t in _segs(text):
        f = _f("ta" if t == "ta" else "en", sz)
        draw.text((cx, y), seg, font=f, fill=col, anchor="lt")
        cx += draw.textbbox((0,0), seg, font=f)[2]
    return cx

def _wrap(words, sz, maxw, draw):
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if _tw(draw, test, sz) <= maxw or not cur:
            cur.append(w)
        else:
            lines.append(cur); cur = [w]
    if cur: lines.append(cur)
    return lines

def _apply_paper_wash(draw, width: int, height: int) -> None:
    for row in range(0, height, 56):
        draw.line([(0, row), (width, row)], fill=FAINT, width=1)
    draw.rectangle([0, 0, width, height], outline=(240, 238, 232), width=2)

def _apply_emotion_wash(img: Image.Image, emotion: str) -> Image.Image:
    """Faint tint overlay matching scene emotion."""
    wash = EMOTION_WASH.get(emotion, EMOTION_WASH["neutral"])
    overlay = Image.new("RGBA", img.size, wash)
    base = img.convert("RGBA")
    merged = Image.alpha_composite(base, overlay)
    return merged.convert("RGB")

# ── Sparkle particles ────────────────────────────────────────────────
def _draw_sparkles(draw, progress: float, emotion: str, rng_seed: int) -> None:
    """Draw small ✦ sparkles for celebrating/turning_point scenes."""
    if emotion not in ("celebrating", "exciting", "inspirational"):
        return
    rng = random.Random(rng_seed)
    count = int(6 + progress * 8)
    for _ in range(count):
        x = rng.randint(60, W - 200)
        y = rng.randint(60, H - 120)
        phase = (progress + rng.random()) % 1.0
        alpha = int(180 * math.sin(phase * math.pi))
        size = int(6 + rng.random() * 12)
        col = (255, 200 + rng.randint(0,55), rng.randint(30, 100))
        # 4-pointed star
        cx, cy = x, y
        for angle in [0, 90, 180, 270]:
            rad = math.radians(angle)
            ex = cx + int(math.cos(rad) * size)
            ey = cy + int(math.sin(rad) * size)
            draw.line([(cx, cy), (ex, ey)], fill=col, width=2)

# ── Progress bar ─────────────────────────────────────────────────────
def _draw_progress_bar(draw, scene_num: int, total_scenes: int, emotion: str) -> None:
    """Thin progress strip at very bottom — shows story momentum."""
    pct = (scene_num + 1) / max(total_scenes, 1)
    bar_y = H - 8
    # Background track
    draw.rectangle([0, bar_y, W, H], fill=(230, 228, 222))
    # Filled portion
    bar_color = {
        "sad": (100, 140, 200),
        "celebrating": (255, 160, 30),
        "exciting": (220, 60, 30),
        "inspirational": (50, 160, 80),
    }.get(emotion, (45, 106, 79))
    draw.rectangle([0, bar_y, int(W * pct), H], fill=bar_color)

# ── Beat label badge ─────────────────────────────────────────────────
def _draw_beat_badge(draw, beat_type: str, frame_index: int, fps: int = 24) -> None:
    """Show beat-type label for first 2.5 seconds of a scene."""
    visible_frames = int(fps * 2.5)
    if frame_index > visible_frames:
        return
    fade_in  = min(1.0, frame_index / max(fps * 0.3, 1))
    fade_out = 1.0 if frame_index < visible_frames - fps * 0.4 else max(0.0, (visible_frames - frame_index) / (fps * 0.4))
    alpha = fade_in * fade_out
    if alpha < 0.05:
        return
    label, color = BEAT_LABELS.get(beat_type, ("", (80, 80, 80)))
    if not label:
        return
    sz = 34
    tw = _tw(draw, label, sz) + 36
    x, y = 52, 22
    # Semi-transparent pill
    r, g, b = color
    a = int(220 * alpha)
    overlay_img = Image.new("RGBA", (tw + 4, 52), (r, g, b, a))
    # We can only draw on the draw object — approximate with solid color
    # (full alpha compositing would need PIL Image, done in render_frame)
    draw.rounded_rectangle([x, y, x + tw, y + 50], radius=10, fill=color)
    _dt(draw, label, x + 18, y + 8, sz, WHITE)

# ── Underline sweep on current word ─────────────────────────────────
def _draw_word_underline(draw, x: int, y: int, word_width: int, font_sz: int, progress: float) -> None:
    """Animated underline that sweeps left→right under current word."""
    uy = y + font_sz + 4
    sweep = min(1.0, progress * 3.0)
    end_x = x + int(word_width * sweep)
    if end_x > x:
        draw.line([(x, uy), (end_x, uy)], fill=RED, width=4)


# ══════════════════════════════════════════════════════════════════════
# SCENE BACKGROUNDS
# ══════════════════════════════════════════════════════════════════════
def _svg_office(color="#161616") -> str:
    c = color
    return f"""
    <rect x="80" y="320" width="440" height="20" rx="4" fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <line x1="100" y1="340" x2="100" y2="420" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <line x1="500" y1="340" x2="500" y2="420" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <rect x="230" y="200" width="160" height="110" rx="8" fill="none" stroke="{c}" stroke-width="4"/>
    <line x1="310" y1="310" x2="310" y2="320" stroke="{c}" stroke-width="4"/>
    <line x1="280" y1="320" x2="340" y2="320" stroke="{c}" stroke-width="3"/>
    <line x1="250" y1="230" x2="370" y2="230" stroke="{c}" stroke-width="2" opacity="0.4"/>
    <line x1="250" y1="248" x2="340" y2="248" stroke="{c}" stroke-width="2" opacity="0.4"/>
    <line x1="250" y1="266" x2="355" y2="266" stroke="{c}" stroke-width="2" opacity="0.4"/>
    <path d="M480 290 Q480 270 500 270 Q520 270 520 290 L515 320 L485 320 Z" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    <path d="M520 280 Q535 280 535 295 Q535 310 520 308" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    """

def _svg_money(color="#161616") -> str:
    c = color
    return f"""
    <ellipse cx="200" cy="380" rx="80" ry="22" fill="none" stroke="{c}" stroke-width="4"/>
    <line x1="120" y1="380" x2="120" y2="340" stroke="{c}" stroke-width="4"/>
    <line x1="280" y1="380" x2="280" y2="340" stroke="{c}" stroke-width="4"/>
    <ellipse cx="200" cy="340" rx="80" ry="22" fill="none" stroke="{c}" stroke-width="4"/>
    <line x1="120" y1="340" x2="120" y2="300" stroke="{c}" stroke-width="4"/>
    <line x1="280" y1="340" x2="280" y2="300" stroke="{c}" stroke-width="4"/>
    <ellipse cx="200" cy="300" rx="80" ry="22" fill="none" stroke="{c}" stroke-width="4"/>
    <text x="175" y="310" font-size="28" font-weight="900" fill="none" stroke="{c}" stroke-width="2">₹</text>
    <line x1="400" y1="400" x2="400" y2="220" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <line x1="380" y1="255" x2="400" y2="220" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <line x1="420" y1="255" x2="400" y2="220" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <line x1="350" y1="400" x2="460" y2="400" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    """

def _svg_phone(color="#161616") -> str:
    c = color
    return f"""
    <rect x="180" y="160" width="120" height="220" rx="18" fill="none" stroke="{c}" stroke-width="5"/>
    <rect x="192" y="175" width="96" height="165" rx="4" fill="none" stroke="{c}" stroke-width="2.5"/>
    <circle cx="240" cy="360" r="10" fill="none" stroke="{c}" stroke-width="3"/>
    <circle cx="340" cy="180" r="18" fill="none" stroke="{c}" stroke-width="3"/>
    <text x="334" y="188" font-size="18" font-weight="900" fill="none" stroke="{c}" stroke-width="1.5">3</text>
    <line x1="320" y1="175" x2="310" y2="165" stroke="{c}" stroke-width="2.5"/>
    <line x1="205" y1="200" x2="275" y2="200" stroke="{c}" stroke-width="2" opacity="0.5"/>
    <line x1="205" y1="215" x2="260" y2="215" stroke="{c}" stroke-width="2" opacity="0.5"/>
    <line x1="205" y1="230" x2="268" y2="230" stroke="{c}" stroke-width="2" opacity="0.5"/>
    <path d="M350 240 Q380 270 350 300" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    <line x1="340" y1="290" x2="350" y2="300" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    <line x1="360" y1="290" x2="350" y2="300" stroke="{c}" stroke-width="3" stroke-linecap="round"/>
    """

def _svg_home(color="#161616") -> str:
    c = color
    return f"""
    <line x1="130" y1="280" x2="300" y2="160" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <line x1="300" y1="160" x2="470" y2="280" stroke="{c}" stroke-width="5" stroke-linecap="round"/>
    <rect x="150" y="280" width="300" height="160" rx="4" fill="none" stroke="{c}" stroke-width="5"/>
    <rect x="265" y="360" width="70" height="80" rx="4" fill="none" stroke="{c}" stroke-width="4"/>
    <circle cx="325" cy="402" r="6" fill="none" stroke="{c}" stroke-width="3"/>
    <rect x="170" y="310" width="60" height="55" rx="4" fill="none" stroke="{c}" stroke-width="3.5"/>
    <line x1="200" y1="310" x2="200" y2="365" stroke="{c}" stroke-width="2"/>
    <line x1="170" y1="337" x2="230" y2="337" stroke="{c}" stroke-width="2"/>
    <rect x="360" y="195" width="36" height="60" fill="none" stroke="{c}" stroke-width="4"/>
    """

def _svg_think_bubble(color="#161616") -> str:
    c = color
    return f"""
    <circle cx="380" cy="140" r="65" fill="none" stroke="{c}" stroke-width="4"/>
    <circle cx="330" cy="220" r="18" fill="none" stroke="{c}" stroke-width="3"/>
    <circle cx="305" cy="252" r="11" fill="none" stroke="{c}" stroke-width="3"/>
    <circle cx="290" cy="275" r="6"  fill="none" stroke="{c}" stroke-width="2.5"/>
    <text x="354" y="158" font-size="72" font-weight="900" fill="none" stroke="{c}" stroke-width="3.5" stroke-linecap="round">?</text>
    """

def _svg_path_up(color="#161616") -> str:
    c = color
    return f"""
    <path d="M 100 440 Q 200 380 300 360 Q 380 345 420 280 Q 460 215 500 180"
          fill="none" stroke="{c}" stroke-width="6" stroke-linecap="round" stroke-dasharray="18 10"/>
    <circle cx="200" cy="390" r="12" fill="none" stroke="{c}" stroke-width="3.5"/>
    <line x1="200" y1="378" x2="200" y2="355" stroke="{c}" stroke-width="3"/>
    <circle cx="360" cy="348" r="12" fill="none" stroke="{c}" stroke-width="3.5"/>
    <line x1="360" y1="336" x2="360" y2="313" stroke="{c}" stroke-width="3"/>
    <polygon points="500,150 508,175 535,175 514,190 522,215 500,200 478,215 486,190 465,175 492,175"
             fill="none" stroke="{c}" stroke-width="3.5" stroke-linejoin="round"/>
    """

def _svg_heart_break(color="#161616") -> str:
    c = color
    return f"""
    <path d="M 280 220 C 230 180 150 190 150 260 C 150 310 200 350 280 400
             C 360 350 410 310 410 260 C 410 190 330 180 280 220 Z"
          fill="none" stroke="{c}" stroke-width="5" stroke-linejoin="round"/>
    <polyline points="280,220 265,290 290,330 270,400"
              fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    <ellipse cx="200" cy="430" rx="8" ry="12" fill="none" stroke="{c}" stroke-width="3"/>
    <ellipse cx="360" cy="440" rx="8" ry="12" fill="none" stroke="{c}" stroke-width="3"/>
    """

def _svg_trophy(color="#161616") -> str:
    c = color
    return f"""
    <path d="M 200 160 L 380 160 L 360 300 Q 350 360 290 370 Q 230 360 220 300 Z"
          fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M 200 180 Q 150 180 150 230 Q 150 280 220 285"
          fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <path d="M 380 180 Q 430 180 430 230 Q 430 280 360 285"
          fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <line x1="260" y1="370" x2="260" y2="410" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <rect x="200" y="410" width="180" height="24" rx="6" fill="none" stroke="{c}" stroke-width="4"/>
    <polygon points="290,128 295,145 313,145 299,155 304,172 290,162 276,172 281,155 267,145 285,145"
             fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>
    """

def _svg_graph(color="#161616") -> str:
    c = color
    return f"""
    <line x1="80" y1="420" x2="80" y2="120" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <line x1="80" y1="420" x2="520" y2="420" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <polyline points="100,380 180,320 250,340 320,240 400,180 490,120"
              fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="490" cy="120" r="10" fill="none" stroke="{c}" stroke-width="4"/>
    <line x1="480" y1="108" x2="490" y2="120" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    <line x1="500" y1="108" x2="490" y2="120" stroke="{c}" stroke-width="4" stroke-linecap="round"/>
    """

SCENE_BACKGROUNDS = {
    0: None,
    1: _svg_office,
    2: _svg_heart_break,
    3: _svg_think_bubble,
    4: _svg_path_up,
    5: _svg_home,
    6: _svg_trophy,
    7: None,
}

KEYWORD_BACKGROUNDS = {
    "சம்பளம்": _svg_money, "salary": _svg_money, "₹": _svg_money, "money": _svg_money,
    "அலுவலக": _svg_office, "office": _svg_office, "job": _svg_office, "வேலை": _svg_office,
    "mobile": _svg_phone, "phone": _svg_phone, "மொபைல்": _svg_phone, "social": _svg_phone,
    "வீட்": _svg_home, "home": _svg_home, "house": _svg_home,
    "யோசி": _svg_think_bubble, "think": _svg_think_bubble, "confused": _svg_think_bubble,
    "trophy": _svg_trophy, "வெற்றி": _svg_trophy, "success": _svg_trophy,
    "growth": _svg_graph, "வளர்ச்சி": _svg_graph, "graph": _svg_graph,
}

def pick_background(scene_text: str, scene_idx: int):
    tl = scene_text.lower()
    for kw, fn in KEYWORD_BACKGROUNDS.items():
        if kw in tl:
            return fn
    return SCENE_BACKGROUNDS.get(scene_idx % len(SCENE_BACKGROUNDS))


# ══════════════════════════════════════════════════════════════════════
# STICK FIGURE
# ══════════════════════════════════════════════════════════════════════
FIGURE_EMOTIONS = {
    "neutral": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 60 51 L 60 105",  5),
        ("M 60 70 L 32 92",   4),
        ("M 60 70 L 88 92",   4),
        ("M 60 105 L 38 145", 5),
        ("M 60 105 L 82 145", 5),
    ],
    "sad": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 60 51 L 58 106", 5),
        ("M 58 70 L 30 100", 4),
        ("M 58 70 L 84 98",  4),
        ("M 58 106 L 36 148", 5),
        ("M 58 106 L 80 148", 5),
        ("M 48 40 Q 60 48 72 40", 3),
    ],
    "happy": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 60 51 L 60 104", 5),
        ("M 60 68 L 32 88",  4),
        ("M 60 68 L 88 88",  4),
        ("M 60 104 L 40 144", 5),
        ("M 60 104 L 80 144", 5),
        ("M 47 40 Q 60 52 73 40", 3.5),
    ],
    "thinking": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 60 51 L 60 105", 5),
        ("M 60 68 L 32 84 L 34 68", 4),
        ("M 60 68 L 88 90",  4),
        ("M 60 105 L 38 145", 5),
        ("M 60 105 L 82 145", 5),
        ("M 80 22 L 84 16 M 88 24 L 93 18 M 92 32 L 98 28", 2.5),
    ],
    "celebrating": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 60 51 L 60 105", 5),
        ("M 60 68 L 26 44",  4.5),
        ("M 60 68 L 94 44",  4.5),
        ("M 60 105 L 42 148", 5),
        ("M 60 105 L 78 148", 5),
        ("M 47 38 Q 60 52 73 38", 4),
        ("M 24 36 L 20 28 M 18 40 L 12 36", 2.5),
        ("M 96 36 L 100 28 M 102 40 L 108 36", 2.5),
    ],
    "walking": [
        ("M 60 15 A 18 18 0 1 0 60 51 A 18 18 0 1 0 60 15", 5),
        ("M 62 51 L 64 106", 5),
        ("M 64 70 L 36 90",  4),
        ("M 64 70 L 90 80",  4),
        ("M 64 106 L 36 150",  5),
        ("M 64 106 L 85 138", 5),
    ],
}

def render_figure_svg(emotion: str, progress: float, size: int = 360, color: str = "#141414") -> Image.Image:
    paths  = FIGURE_EMOTIONS.get(emotion, FIGURE_EMOTIONS["neutral"])
    n      = len(paths)
    drawn  = progress * n
    parts  = []
    for i, (d, sw) in enumerate(paths):
        length = max(60.0, len(re.findall(r'-?[\d.]+', d)) // 2 * 15.0)
        lp     = min(1.0, max(0.0, drawn - i))
        dash   = length * lp
        gap    = length - dash + 1
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="{sw * 2.4:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{gap:.1f}"/>'
        )
    svg = (
        f'<svg width="{size}" height="{size}" viewBox="0 0 120 160" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(parts)}</svg>'
    )
    return Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    )).convert("RGBA")


def render_background_svg(draw_fn, progress: float, size_w: int = 620, size_h: int = 520,
                           color: str = "#141414") -> Image.Image:
    if draw_fn is None:
        return Image.new("RGBA", (size_w, size_h), (255, 255, 255, 0))
    inner = draw_fn(color)
    reveal = min(1.0, progress * 1.8)
    clip_width = int(size_w * reveal)
    svg = (
        f'<svg width="{size_w}" height="{size_h}" viewBox="0 0 600 500" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<defs><clipPath id="reveal">'
        f'<rect x="0" y="0" width="{clip_width}" height="{size_h}"/>'
        f'</clipPath></defs>'
        f'<g clip-path="url(#reveal)" opacity="{min(1.0, progress * 2.0):.2f}">'
        f'{inner}'
        f'</g></svg>'
    )
    return Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(), output_width=size_w, output_height=size_h)
    )).convert("RGBA")


# ══════════════════════════════════════════════════════════════════════
# PENCIL CURSOR
# ══════════════════════════════════════════════════════════════════════
_PENCIL_CACHE = {}

def get_pencil(size=72) -> Image.Image:
    if size not in _PENCIL_CACHE:
        svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
  <g transform="rotate(-38 30 30)">
    <rect x="25" y="6" width="10" height="38" rx="2.5" fill="#F5C518" stroke="#8B6914" stroke-width="1.3"/>
    <polygon points="25,44 35,44 30,54" fill="#F0A020" stroke="#8B6914" stroke-width="1.2"/>
    <polygon points="27.5,50 32.5,50 30,54" fill="#555"/>
    <rect x="25" y="4" width="10" height="6" rx="2" fill="#E08080" stroke="#8B6914" stroke-width="1"/>
  </g>
</svg>'''
        _PENCIL_CACHE[size] = Image.open(io.BytesIO(
            cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
        )).convert("RGBA")
    return _PENCIL_CACHE[size]


# ══════════════════════════════════════════════════════════════════════
# MAIN FRAME RENDERER
# ══════════════════════════════════════════════════════════════════════
def render_frame(
    all_words       : List[str],
    visible         : int,
    figure_progress : float,
    bg_progress     : float,
    emotion         : str,
    protagonist     : str,
    bg_draw_fn,
    scene_num       : int,
    total_scenes    : int,
    is_shorts       : bool = False,
    figure_offset_x : int = 0,
    figure_offset_y : int = 0,
    bg_offset_x     : int = 0,
    bg_offset_y     : int = 0,
    text_drift_y    : int = 0,
    word_pop        : float = 0.0,
    on_screen_text  : str = "",
    layout_mirror   : bool = False,
    figure_scale    : float = 1.0,
    beat_type       : str = "",
    frame_index     : int = 0,
    fps             : int = 24,
) -> Image.Image:

    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    _apply_paper_wash(draw, W, H)

    if is_shorts:
        img = _apply_emotion_wash(img, emotion)
        draw = ImageDraw.Draw(img)
        return _render_shorts_frame(
            draw=draw, img=img, all_words=all_words, visible=visible,
            figure_progress=figure_progress, bg_progress=bg_progress,
            emotion=emotion, protagonist=protagonist, bg_draw_fn=bg_draw_fn,
            on_screen_text=on_screen_text, figure_offset_x=figure_offset_x,
            figure_offset_y=figure_offset_y, bg_offset_x=bg_offset_x,
            bg_offset_y=bg_offset_y, text_drift_y=text_drift_y, word_pop=word_pop,
            layout_mirror=layout_mirror, figure_scale=figure_scale,
            beat_type=beat_type, frame_index=frame_index, fps=fps,
        )

    # ── Layout ────────────────────────────────────────────────────────
    FIG_SIZE = int(400 * figure_scale)
    BG_W, BG_H = 580, 500

    if layout_mirror:
        FIG_X = 50 + figure_offset_x
        FIG_Y = H - FIG_SIZE - 80 + figure_offset_y
        BG_X  = FIG_X + FIG_SIZE + 24 + bg_offset_x
        BG_Y  = 80 + bg_offset_y
        TEXT_X = BG_X + BG_W + 40
        TEXT_W = W - TEXT_X - 50
    else:
        FIG_X = W - FIG_SIZE - 50 + figure_offset_x
        FIG_Y = H - FIG_SIZE - 80 + figure_offset_y
        BG_X  = FIG_X - 30 + bg_offset_x
        BG_Y  = 80 + bg_offset_y
        TEXT_X = 55
        TEXT_W = FIG_X - 90

    # ── Emotion wash ──────────────────────────────────────────────────
    img = _apply_emotion_wash(img, emotion)
    draw = ImageDraw.Draw(img)
    _apply_paper_wash(draw, W, H)

    # ── 1. Scene background ───────────────────────────────────────────
    if bg_draw_fn is not None and bg_progress > 0.02:
        bg_img = render_background_svg(bg_draw_fn, bg_progress, BG_W, BG_H)
        img.paste(bg_img, (BG_X, BG_Y), bg_img)
        if 0.04 < bg_progress < 0.95:
            pencil = get_pencil(64)
            tip_x = BG_X + int(BG_W * min(0.85, bg_progress * 0.9))
            tip_y = BG_Y + int(BG_H * min(0.75, bg_progress * 0.7))
            img.paste(pencil, (max(0, tip_x - 50), max(0, tip_y - 55)), pencil)

    # ── 2. Stick figure ───────────────────────────────────────────────
    if figure_progress > 0.02:
        fig = render_figure_svg(emotion, figure_progress, FIG_SIZE)
        img.paste(fig, (FIG_X, FIG_Y), fig)

        if 0.04 < figure_progress < 0.92:
            pencil = get_pencil(72)
            tip_x = FIG_X + int(FIG_SIZE * 0.58)
            tip_y = FIG_Y + int(FIG_SIZE * figure_progress * 0.80)
            px = max(0, min(W-80, tip_x))
            py = max(0, min(H-80, tip_y - 65))
            img.paste(pencil, (px, py), pencil)

        if figure_progress > 0.65:
            nw = _tw(draw, protagonist, 30)
            _dt(draw, protagonist, FIG_X + (FIG_SIZE - nw) // 2, FIG_Y + FIG_SIZE + 8, 30, GREY)

    # ── 3. Beat badge ─────────────────────────────────────────────────
    if on_screen_text:
        badge_text = on_screen_text[:40]
        badge_w = _tw(draw, badge_text, 48) + 40
        draw.rounded_rectangle([55, 20, 55 + badge_w, 80], radius=12, fill=(205, 35, 25))
        _dt(draw, badge_text, 75, 28, 48, (255, 255, 255))

    if beat_type:
        _draw_beat_badge(draw, beat_type, frame_index, fps)

    # ── 4. Word-by-word text ──────────────────────────────────────────
    TEXT_Y = 72 + text_drift_y
    words_vis = all_words[:visible]
    total_w   = len(all_words)

    for sz in [130, 108, 90, 78, 66, 56]:
        lines = _wrap(words_vis, sz, TEXT_W, draw)
        lh    = draw.textbbox((0,0), "A", font=_f("ta", sz))[3] + 24
        if TEXT_Y + len(lines) * lh < H - 80:
            break

    y, wi = TEXT_Y, 0
    last_x, last_y_end = TEXT_X, TEXT_Y
    lh_px = 0

    for li, lw in enumerate(lines):
        x   = TEXT_X
        fsz = sz if li == 0 else max(54, sz - 14)
        for word in lw:
            is_curr  = (wi == visible - 1) and (visible < total_w)
            is_final = (wi == visible - 1) and (visible == total_w)
            col = RED if is_curr else (GREY if is_final else INK)
            draw_y = y
            if is_curr and word_pop > 0:
                draw_y = y - int((1.0 - word_pop) * 22)
            last_x = _dt(draw, word + " ", x, draw_y, fsz, col, shadow=is_curr)
            if is_curr:
                ww = last_x - x
                _draw_word_underline(draw, x, draw_y, ww, fsz, word_pop)
            x = last_x; wi += 1
        lh_px = draw.textbbox((0,0), "A", font=_f("ta", fsz))[3] + 24
        last_y_end = y + lh_px
        y += lh_px
        if y > H - 90: break

    # Cursor blink
    if visible < total_w:
        ch_h = draw.textbbox((0, 0), "A", font=_f("ta", sz))[3]
        draw.rectangle([last_x + 4, last_y_end - lh_px, last_x + 9, last_y_end - lh_px + ch_h], fill=INK)

    # ── 5. Sparkles ───────────────────────────────────────────────────
    progress = visible / max(total_w, 1)
    _draw_sparkles(draw, progress, emotion, scene_num * 31 + frame_index // 12)

    # ── 6. Progress bar ───────────────────────────────────────────────
    _draw_progress_bar(draw, scene_num, total_scenes, emotion)

    return img


def _render_shorts_frame(
    draw, img, all_words, visible, figure_progress, bg_progress,
    emotion, protagonist, bg_draw_fn, on_screen_text,
    figure_offset_x, figure_offset_y, bg_offset_x, bg_offset_y,
    text_drift_y, word_pop, layout_mirror=False, figure_scale=1.0,
    beat_type="", frame_index=0, fps=24,
) -> Image.Image:
    FIG_SIZE = int(260 * figure_scale)
    BG_W, BG_H = 360, 300
    TEXT_X = 50
    TEXT_W = W - 100
    HEADLINE_Y = 48 + text_drift_y
    TEXT_Y = 200 + text_drift_y

    headline = (on_screen_text or "").strip()
    if not headline and all_words:
        headline = all_words[0]
    if headline:
        badge_sz = 52
        badge_text = headline[:28]
        badge_w = _tw(draw, badge_text, badge_sz) + 48
        badge_x = max(40, (W - badge_w) // 2)
        draw.rounded_rectangle([badge_x, HEADLINE_Y, badge_x + badge_w, HEADLINE_Y + 72], radius=16, fill=RED)
        _dt(draw, badge_text, badge_x + 24, HEADLINE_Y + 10, badge_sz, WHITE)

    if beat_type:
        _draw_beat_badge(draw, beat_type, frame_index, fps)

    visual_center_x = W // 2
    BG_X = visual_center_x - BG_W // 2 + bg_offset_x
    BG_Y = int(H * 0.52) + bg_offset_y
    FIG_X = visual_center_x - FIG_SIZE // 2 + 120 + figure_offset_x
    if layout_mirror:
        FIG_X = visual_center_x - FIG_SIZE - 80 + figure_offset_x
    FIG_Y = BG_Y + BG_H - 40 + figure_offset_y

    if bg_draw_fn is not None and bg_progress > 0.02:
        bg_img = render_background_svg(bg_draw_fn, bg_progress, BG_W, BG_H)
        img.paste(bg_img, (BG_X, BG_Y), bg_img)

    if figure_progress > 0.02:
        fig = render_figure_svg(emotion, figure_progress, FIG_SIZE)
        img.paste(fig, (FIG_X, FIG_Y), fig)
        if figure_progress > 0.65:
            name_w = _tw(draw, protagonist, 28)
            _dt(draw, protagonist, FIG_X + (FIG_SIZE - name_w) // 2, FIG_Y + FIG_SIZE + 6, 28, GREY)

    words_vis = all_words[: max(visible, 1)]
    total_w = len(all_words)

    for sz in [88, 76, 64, 56, 48]:
        lines = _wrap(words_vis, sz, TEXT_W, draw)
        lh = draw.textbbox((0, 0), "A", font=_f("ta", sz))[3] + 20
        if TEXT_Y + len(lines) * lh < int(H * 0.48):
            break

    y, wi = TEXT_Y, 0
    last_x = TEXT_X
    lh_px  = 0
    for li, lw in enumerate(lines):
        x = TEXT_X
        fsz = sz if li == 0 else max(42, sz - 12)
        for word in lw:
            is_curr  = (wi == visible - 1) and (visible < total_w)
            is_final = (wi == visible - 1) and (visible == total_w)
            col = RED if is_curr else (GREY if is_final else INK)
            draw_y = y
            if is_curr and word_pop > 0:
                draw_y = y - int((1.0 - word_pop) * 18)
            last_x = _dt(draw, word + " ", x, draw_y, fsz, col, shadow=is_curr)
            x = last_x; wi += 1
        lh_px = draw.textbbox((0, 0), "A", font=_f("ta", fsz))[3] + 20
        y += lh_px
        if y > int(H * 0.48): break

    if visible < total_w:
        ch_h = draw.textbbox((0, 0), "A", font=_f("ta", sz))[3]
        draw.rectangle([last_x + 4, y - lh_px, last_x + 9, y - lh_px + ch_h], fill=INK)

    progress = visible / max(total_w, 1)
    _draw_sparkles(draw, progress, emotion, frame_index // 12)
    return img


# ══════════════════════════════════════════════════════════════════════
# CROSSFADE
# ══════════════════════════════════════════════════════════════════════
def crossfade(frame_a: Image.Image, frame_b: Image.Image, t: float) -> Image.Image:
    a = np.array(frame_a, dtype=np.float32)
    b = np.array(frame_b, dtype=np.float32)
    blended = (a * (1 - t) + b * t).astype(np.uint8)
    return Image.fromarray(blended)
