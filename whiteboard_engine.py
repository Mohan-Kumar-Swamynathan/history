"""
Whiteboard animation engine v3 — Almost Everything style.
- Pure white background, zero UI chrome
- Full-screen large text, fills canvas
- Dual-font Tamil+Latin (NotoSansTamil + NotoSans)
- Icon per keyword, multiple icons per scene, continuous drawing
- Hand pencil cursor at drawing tip
- Marker-style thick strokes on icons
"""
from __future__ import annotations
import re, subprocess, io, math, random
from pathlib import Path
from typing import List, Tuple, Optional
import cairosvg
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H        = 1920, 1080
FPS         = 24
ICON_STEPS  = 16
PURE_WHITE  = (255, 255, 255)
INK         = (22,  22,  22)    # near-black marker ink
RED_ACCENT  = (210,  40,  30)   # last-word highlight
GREEN_FINAL = (34,  120,  60)   # completed-word colour
GREY_SHADOW = (200, 200, 195)

# ── Fonts ─────────────────────────────────────────────────────────────
_FP = {
    "ta_black"  : "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "ta_bold"   : "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "ta_regular": "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "en_black"  : "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "en_bold"   : "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "en_regular": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
}
_FC = {}
def _font(k, s):
    if (k,s) not in _FC:
        try: _FC[(k,s)] = ImageFont.truetype(_FP[k], s)
        except: _FC[(k,s)] = ImageFont.load_default()
    return _FC[(k,s)]

# ── Tamil/Latin segmentation ──────────────────────────────────────────
def _segs(text):
    out, cur, ct = [], "", None
    for ch in text:
        cp = ord(ch)
        t = "ta" if (0x0B80 <= cp <= 0x0BFF or ch in ' .,!?₹%-:;') else "en"
        if t != ct and cur:
            out.append((cur, ct))
            cur = ""
        cur += ch; ct = t
    if cur: out.append((cur, ct))
    return out

def _seg_width(draw, text, sz):
    w = 0
    for seg, t in _segs(text):
        f = _font("ta_black" if t=="ta" else "en_black", sz)
        w += draw.textbbox((0,0), seg, font=f)[2]
    return w

def _draw_seg(draw, text, x, y, sz, col, shadow_col=None):
    cx = x
    for seg, t in _segs(text):
        f = _font("ta_black" if t=="ta" else "en_black", sz)
        if shadow_col:
            draw.text((cx+3, y+3), seg, font=f, fill=shadow_col, anchor="lt")
        draw.text((cx, y), seg, font=f, fill=col, anchor="lt")
        cx += draw.textbbox((0,0), seg, font=f)[2]
    return cx

def _word_w(draw, word, sz):
    return _seg_width(draw, word+" ", sz)

def _wrap(words, sz, maxw, draw):
    lines, cur, cw = [], [], 0
    for w in words:
        ww = _word_w(draw, w+" ", sz)
        if cw + ww <= maxw or not cur:
            cur.append(w); cw += ww
        else:
            lines.append(cur); cur=[w]; cw=ww
    if cur: lines.append(cur)
    return lines

# ── Icon keyword map (word → icon name) ───────────────────────────────
WORD_ICONS = {
    # Tamil
    "கேள்வி":"question_mark","வேண்டாம்":"no_sign","இல்லை":"no_sign",
    "பணம்":"rupee","சம்பளம்":"rupee","முதலீடு":"coins_stack",
    "நேரம்":"clock","கடிகாரம்":"clock","நாள்":"calendar",
    "மூளை":"brain","யோசி":"brain","சிந்தி":"brain",
    "நண்பன்":"two_people","நண்பி":"two_people","உறவு":"heart",
    "குடும்பம்":"family","அம்மா":"family","அப்பா":"family",
    "வெற்றி":"arrow_up","முன்னேற்றம்":"graph_up","வளர்ச்சி":"sprout",
    "subscribe":"subscribe","சேனல்":"subscribe","பயிற்சி":"ladder",
    "வீடு":"house","கதை":"person","மனசு":"lightbulb",
    "திருமணம்":"heart","அன்பு":"heart","பயம்":"anxious_face",
    "மகிழ்ச்சி":"happy_face","சோகம்":"sad_face",
    # English
    "credit":"wallet","card":"wallet","salary":"rupee","money":"rupee",
    "investment":"coins_stack","sip":"graph_up","emi":"rupee",
    "time":"clock","morning":"clock","anxiety":"anxious_face",
    "stress":"anxious_face","toxic":"no_sign","boundary":"boundary_wall",
    "no":"no_sign","yes":"checkmark","phone":"phone","social":"phone",
    "brain":"brain","mind":"brain","habit":"ladder","goal":"arrow_up",
    "subscribe":"subscribe","like":"thumbs_up","share":"speech_bubble",
    "family":"family","friend":"two_people","love":"heart",
    "work":"briefcase","job":"briefcase","career":"ladder",
    "money":"rupee","save":"piggy_bank","spend":"wallet",
}

def icons_for_scene(words: List[str], default_icon: str) -> List[Tuple[int,str]]:
    """Return list of (word_index, icon_name) for words that have icons."""
    seen = set()
    result = []
    for i, w in enumerate(words):
        wl = w.lower().strip(".,!?:")
        icon = WORD_ICONS.get(wl) or WORD_ICONS.get(w)
        if icon and icon not in seen:
            result.append((i, icon))
            seen.add(icon)
    # Always include default icon at word 0 if no match found early
    if not result or result[0][0] > 3:
        if default_icon not in seen:
            result.insert(0, (0, default_icon))
    return result[:4]  # max 4 icons per scene

# ── Icon renderer ─────────────────────────────────────────────────────
def _path_len(d):
    return max(60.0, len(re.findall(r'-?[\d.]+', d)) // 2 * 14.0)

def render_icon_img(icon_paths, progress, size=220, color="#161616", stroke_scale=1.3):
    """Render icon with marker-thick strokes."""
    n = len(icon_paths)
    drawn = progress * n
    parts = []
    for i,(d,sw) in enumerate(icon_paths):
        length = _path_len(d)
        lp     = min(1.0, max(0.0, drawn - i))
        dash   = length * lp
        gap    = length - dash + 1
        # Thicker strokes for marker feel
        thick  = sw * stroke_scale
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{thick:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{gap:.1f}"/>'
        )
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 120 120" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')
    return Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    )).convert("RGBA")

# ── Pencil hand cursor ────────────────────────────────────────────────
def _pencil_cursor(size=70) -> Image.Image:
    svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
  <g transform="rotate(-35 30 30)">
    <rect x="26" y="8" width="8" height="36" rx="2" fill="#F5C518" stroke="#8B6914" stroke-width="1.2"/>
    <polygon points="26,44 34,44 30,52" fill="#F0A020" stroke="#8B6914" stroke-width="1"/>
    <polygon points="28,49 32,49 30,52" fill="#555"/>
    <rect x="26" y="6" width="8" height="5" rx="1.5" fill="#E88080" stroke="#8B6914" stroke-width="1"/>
  </g>
</svg>'''
    return Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    )).convert("RGBA")

_PENCIL_IMG = None
def get_pencil():
    global _PENCIL_IMG
    if _PENCIL_IMG is None:
        _PENCIL_IMG = _pencil_cursor(70)
    return _PENCIL_IMG

# ── Main frame renderer ───────────────────────────────────────────────
def render_frame(
    all_words       : List[str],
    visible         : int,
    active_icons    : List[Tuple[str,float,int,int]],  # (name,progress,cx,cy)
    scene_num       : int,
    total_scenes    : int,
    topic           : str,
) -> Image.Image:
    img  = Image.new("RGB", (W, H), PURE_WHITE)
    draw = ImageDraw.Draw(img)

    # ── Scene progress dots — minimal, bottom centre ──────────────────
    DOT_Y = H - 32
    for i in range(total_scenes):
        cx = W//2 - (total_scenes//2 - i) * 28
        r  = 7 if i == scene_num else 4
        col = INK if i == scene_num else (200,200,200)
        draw.ellipse([cx-r, DOT_Y-r, cx+r, DOT_Y+r], fill=col)

    # ── Icons — right side, stacked or spread ────────────────────────
    ICON_AREA_X = 1260
    ICON_SIZE   = 200
    pencil = get_pencil()

    for slot, (iname, iprog, trigger_word_idx, _) in enumerate(active_icons):
        if iprog <= 0.01:
            continue
        from icon_library import get_icon_paths
        icon_paths = get_icon_paths(iname)
        # Stack icons vertically: first at top, subsequent below
        iy = 80 + slot * (ICON_SIZE + 30)
        if iy + ICON_SIZE > H - 60:
            break

        ico = render_icon_img(icon_paths, iprog, ICON_SIZE)
        img.paste(ico, (ICON_AREA_X, iy), ico)

        # Pencil cursor at current stroke tip
        if 0.02 < iprog < 0.96:
            si = min(int(iprog * len(icon_paths)), len(icon_paths)-1)
            nums = re.findall(r'-?[\d.]+', icon_paths[si][0])
            if len(nums) >= 2:
                scale = ICON_SIZE / 120.0
                tx = int(ICON_AREA_X + float(nums[-2]) * scale) - 10
                ty = int(iy + float(nums[-1]) * scale) - 60
                tx = max(ICON_AREA_X-10, min(W-80, tx))
                ty = max(0, min(H-80, ty))
                img.paste(pencil, (tx, ty), pencil)

    # ── Main text — full screen left area ────────────────────────────
    TEXT_X    = 52
    TEXT_Y    = 68
    TEXT_MAXW = 1180  # leave 740px for icons

    # Dynamic font size: start big, shrink if too many lines
    words_visible = all_words[:visible]

    # Pick font size so text fills ~80% of height
    # Aim for 3-5 lines ideally
    for sz in [118, 100, 86, 74, 64]:
        lines = _wrap(all_words, sz, TEXT_MAXW, draw)
        line_h = draw.textbbox((0,0),"A",font=_font("ta_black",sz))[3] + 20
        if TEXT_Y + len(lines)*line_h < H - 80:
            break

    # Visible lines
    lines_visible = _wrap(words_visible, sz, TEXT_MAXW, draw)

    y  = TEXT_Y
    wi = 0
    last_x, last_y = TEXT_X, TEXT_Y

    for li, lw in enumerate(lines_visible):
        x = TEXT_X
        for word in lw:
            is_curr  = (wi == visible-1) and (visible < len(all_words))
            is_done  = (wi == visible-1) and (visible == len(all_words))
            col = RED_ACCENT if is_curr else (GREEN_FINAL if is_done else INK)
            # Subtle ink shadow
            last_x = _draw_seg(draw, word+" ", x, y, sz, col,
                               shadow_col=(230,230,228) if not is_curr else None)
            x = last_x; wi += 1
        line_h = draw.textbbox((0,0),"A",font=_font("ta_black",sz))[3] + 20
        last_y = y
        y += line_h
        if y > H - 80: break

    # Blinking cursor after last visible word
    if visible < len(all_words):
        cursor_h = draw.textbbox((0,0),"A",font=_font("ta_black",sz))[3]
        draw.rectangle([last_x+4, last_y, last_x+9, last_y+cursor_h], fill=INK)

    return img


# ── Scene video builder ───────────────────────────────────────────────
def render_scene_video(
    scene_text, scene_idx, total_scenes, slug, topic,
    audio_path, word_timings, duration,
    scene_label, scene_emoji, label_color, icon_name, out_dir
):
    from icon_library import get_icon_paths

    out_video = out_dir / f"{slug}_scene_{scene_idx:02d}.mp4"
    if out_video.exists() and out_video.stat().st_size > 10_000:
        return out_video

    words = scene_text.split()

    # Build icon schedule: which icons appear at which word
    icon_schedule = icons_for_scene(words, icon_name)
    # icon_schedule = [(word_idx, icon_name), ...]
    # Each icon draws itself over the duration of ~3-5 words

    ICON_DRAW_WORDS = max(3, len(words) // max(len(icon_schedule),1))
    WORD_DUR = duration / max(len(words), 1)
    ICON_DRAW_DUR = ICON_DRAW_WORDS * WORD_DUR  # time to draw each icon

    frame_dir = out_dir / f"f_{slug}_{scene_idx:02d}"
    frame_dir.mkdir(parents=True, exist_ok=True)

    # Build event timestamps
    events = {0.0, duration}
    for wt in word_timings:
        events.add(wt["start"])
    # Add icon keyframe events
    for (widx, _) in icon_schedule:
        t_start = widx * WORD_DUR
        for step in range(ICON_STEPS+1):
            events.add(t_start + step/ICON_STEPS * ICON_DRAW_DUR)
    events = sorted(events)

    segments = []
    prev_state = None
    prev_frame = None
    last_t = 0.0
    unique = 0

    print(f"    Scene {scene_idx}: {len(words)} words, {len(icon_schedule)} icons, {duration:.1f}s", flush=True)

    for t in events:
        t = min(t, duration)
        vis  = max(1, min(sum(1 for wt in word_timings if wt["start"] <= t), len(words)))

        # Compute progress for each icon
        active_icons = []
        for slot, (widx, iname) in enumerate(icon_schedule):
            t_start = widx * WORD_DUR
            t_end   = t_start + ICON_DRAW_DUR
            if t < t_start:
                prog = 0.0
            elif t >= t_end:
                prog = 1.0
            else:
                prog = (t - t_start) / ICON_DRAW_DUR
            prog_q = round(prog * ICON_STEPS) / ICON_STEPS
            active_icons.append((iname, prog_q, widx, slot))

        state = (vis, tuple(p for _,p,_,_ in active_icons))

        if state != prev_state:
            fp = frame_dir / f"kf_{unique:04d}.png"
            img = render_frame(
                all_words=words, visible=vis,
                active_icons=active_icons,
                scene_num=scene_idx, total_scenes=total_scenes,
                topic=topic,
            )
            img.save(str(fp), "PNG", optimize=True)
            prev_state = state
            prev_frame = fp
            unique += 1

        seg_dur = t - last_t
        if seg_dur > 0.001 and prev_frame:
            segments.append((prev_frame, seg_dur))
        last_t = t

    print(f"    {unique} keyframes → encoding...", flush=True)

    concat_file = frame_dir / "frames.txt"
    with open(concat_file,"w") as f:
        for fp, sd in segments:
            f.write(f"file '{fp.resolve()}'\n")
            f.write(f"duration {sd:.4f}\n")
        if segments:
            f.write(f"file '{segments[-1][0].resolve()}'\n")

    r = subprocess.run([
        "ffmpeg","-y",
        "-f","concat","-safe","0","-i",str(concat_file),
        "-i",str(audio_path),
        "-c:v","libx264","-preset","veryfast","-crf","21",
        "-c:a","aac","-b:a","128k",
        "-pix_fmt","yuv420p","-shortest",
        str(out_video)
    ], capture_output=True, text=True, timeout=600)

    import shutil
    shutil.rmtree(str(frame_dir), ignore_errors=True)

    if r.returncode != 0:
        raise RuntimeError(f"Encode failed: {r.stderr[-300:]}")

    print(f"    ✅ {out_video.stat().st_size//1024}KB")
    return out_video


def markers_to_silence(text):
    """Convert [PAUSE_X] markers to natural ellipsis for edge-tts pacing."""
    import re
    text = re.sub(r'\[PAUSE_LONG\]',  ' ... ', text)
    text = re.sub(r'\[PAUSE_MED\]',   ' .. ',  text)
    text = re.sub(r'\[PAUSE_SHORT\]', ' . ',   text)
    text = re.sub(r'([.!?।])\s+', r'\1 ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()
