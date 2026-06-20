"""Fast Shorts pipeline — derives from long video assets.

Strategy:
  - Takes hook beat (first 45s) from long video
  - Re-renders at 1080x1920 (portrait/vertical) 
  - Adds Shorts-specific overlay (big hook text + subscribe CTA)
  - No new LLM calls — reuses script, audio, images from long video
  - Target: 30-50 seconds
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

log = logging.getLogger(__name__)

SW, SH = 1080, 1920   # Shorts portrait dimensions

try:
    from src.renderer.brand import PRIMARY, DARK, ACCENT, CREAM, INK, LIGHT, BG
except ImportError:
    PRIMARY=(29,48,16); DARK=(29,51,11); ACCENT=(212,175,55)
    CREAM=(244,235,191); INK=(26,46,8); BG=(250,250,240); LIGHT=(237,247,224)

_FC: dict = {}
_TA = ["/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
       "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"]
_EN = ["/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
       "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"]

def _font(sc, sz):
    k=(sc,sz)
    if k not in _FC:
        for p in (_TA if sc=="ta" else _EN):
            if os.path.exists(p):
                try: _FC[k]=ImageFont.truetype(p,sz); break
                except: pass
        if k not in _FC: _FC[k]=ImageFont.load_default()
    return _FC[k]

def _sc(t):
    ta=sum(1 for c in t if 0x0B80<=ord(c)<=0x0BFF)
    return "ta" if ta>len(t)*0.3 else "en"

def _draw_text_shadow(draw, text, x, y, size, fill=(255,255,255)):
    sc=_sc(text); f=_font(sc,size)
    draw.text((x+3,y+3),text,font=f,fill=(0,0,0))
    draw.text((x,y),text,font=f,fill=fill)
    return draw.textbbox((0,0),text,font=f)[2]

def _wrap(draw, text, size, max_w):
    words=text.split(); lines=[]; cur=[]
    for w in words:
        test=" ".join(cur+[w])
        sc=_sc(test); f=_font(sc,size)
        if draw.textbbox((0,0),test,font=f)[2]<=max_w or not cur:
            cur.append(w)
        else:
            lines.append(cur); cur=[w]
    if cur: lines.append(cur)
    return lines


def render_shorts_frame(
    hook_text: str,
    scene_image: Image.Image,
    progress: float,
    protagonist: str,
    show_cta: bool = False,
) -> np.ndarray:
    """Render one Shorts frame — portrait 1080×1920."""
    frame = Image.new("RGB", (SW, SH), BG)
    draw  = ImageDraw.Draw(frame)

    # ── Background: scene image fills top 60% ──────────────────────
    img_h = int(SH * 0.62)
    panel = scene_image.resize((SW, img_h), Image.LANCZOS)
    frame.paste(panel, (0, 0))

    # ── Brand gradient strip over image (bottom of image) ──────────
    for y in range(img_h - 120, img_h):
        t = (y-(img_h-120))/120
        r=int(BG[0]*(1-t)+PRIMARY[0]*t*0.7+BG[0]*t*0.3)
        g=int(BG[1]*(1-t)+PRIMARY[1]*t*0.7+BG[1]*t*0.3)
        b=int(BG[2]*(1-t)+PRIMARY[2]*t*0.7+BG[2]*t*0.3)
        draw.line([(0,y),(SW,y)],fill=(r,g,b))

    # ── Text area — bottom 40% on cream background ──────────────────
    text_y_start = img_h
    draw.rectangle([0, text_y_start, SW, SH], fill=BG)

    # Progress bar at very top
    pct_w = int(SW * progress)
    draw.rectangle([0, 0, pct_w, 8], fill=ACCENT)

    # Channel name top left
    ch_f = _font("ta", 36)
    draw.text((20, 16), "துளிர்", font=ch_f, fill=ACCENT)

    # Hook text — big, bold, Tamil
    y = text_y_start + 40
    lines = _wrap(draw, hook_text, 68, SW - 60)
    for line_words in lines[:4]:
        line = " ".join(line_words)
        sc   = _sc(line); f=_font(sc, 68)
        bbox = draw.textbbox((0,0),line,font=f)
        lw   = bbox[2]-bbox[0]
        x    = max(30,(SW-lw)//2)
        # Shadow
        draw.text((x+2,y+2),line,font=f,fill=(0,0,0))
        draw.text((x,y),line,font=f,fill=INK)
        y += (bbox[3]-bbox[1]) + 16
        if y > SH - 200: break

    # CTA strip at bottom
    if show_cta:
        cta_y = SH - 130
        draw.rectangle([0, cta_y, SW, SH], fill=PRIMARY)
        cta_f = _font("ta", 44)
        cta   = "லைக் | சப்ஸ்கிரைப் | பெல் 🔔"
        cta_b = draw.textbbox((0,0),cta,font=cta_f)
        cta_x = (SW-(cta_b[2]-cta_b[0]))//2
        draw.text((cta_x, cta_y+28), cta, font=cta_f, fill=CREAM)
    else:
        # Protagonist name badge bottom
        name_f = _font("en" if protagonist.isascii() else "ta", 36)
        name_b = draw.textbbox((0,0),protagonist,font=name_f)
        name_x = (SW-(name_b[2]-name_b[0]))//2
        draw.rectangle([0, SH-70, SW, SH], fill=DARK)
        draw.text((name_x, SH-55), protagonist, font=name_f, fill=CREAM)

    return np.array(frame.convert("RGB"))


def generate_shorts(
    hook_narration: str,
    hook_audio_path: Path,
    hook_image: Image.Image,
    protagonist: str,
    output_path: Path,
    duration_s: float = 45.0,
) -> Path:
    """Render and encode a Shorts video from hook beat assets."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = 12
    total_frames = int(duration_s * fps)

    # Determine text lines from hook narration
    words = hook_narration.split()
    # Show first 2 lines as hook text
    hook_text = " ".join(words[:12]) if len(words) > 12 else hook_narration

    # Encode
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{SW}x{SH}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "pipe:0",
        "-i", str(hook_audio_path),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    prev_h, prev_b = None, None
    for fi in range(total_frames):
        progress  = fi / max(total_frames-1, 1)
        show_cta  = progress > 0.80
        frame     = render_shorts_frame(hook_text, hook_image, progress,
                                        protagonist, show_cta)
        h = frame[::16,::16].tobytes()
        if h == prev_h and prev_b:
            proc.stdin.write(prev_b)
        else:
            raw = frame.tobytes()
            proc.stdin.write(raw)
            prev_h, prev_b = h, raw

    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Shorts encoding failed")
    log.info("✅ Shorts encoded: %s", output_path)
    return output_path
