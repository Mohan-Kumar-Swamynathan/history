"""
Visual renderer — generates actual frames for each scene type.
Every scene has MOTION. Nothing is static.

Scene types:
  - image    : Ken Burns zoom/pan on a background image
  - stat     : Animated counter / large typography
  - map      : Highlighted world map with pin/arrow
  - timeline : Horizontal timeline with animated dot
  - icon     : Large SVG icon drawing itself
  - caption  : Full-screen caption moment (pattern interrupt)
"""
import numpy as np, cv2, subprocess, io, re, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cairosvg
from config import W, H, FPS, FONTS, FRAME_DIR, KB_ZOOM_MIN, KB_ZOOM_MAX

_FC = {}
def _font(k, s):
    if (k,s) not in _FC:
        try: _FC[(k,s)] = ImageFont.truetype(FONTS[k], s)
        except: _FC[(k,s)] = ImageFont.load_default()
    return _FC[(k,s)]

# ── Tamil/Latin dual-font draw ────────────────────────────────────────
def _segs(text):
    out, cur, ct = [], "", None
    for ch in text:
        cp = ord(ch)
        t = "ta" if (0x0B80<=cp<=0x0BFF or ch in ' .,!?₹%-') else "en"
        if t!=ct and cur: out.append((cur,ct)); cur=""
        cur+=ch; ct=t
    if cur: out.append((cur,ct))
    return out

def _draw_text(draw, text, x, y, sz, col, shadow=True):
    cx = x
    for seg,t in _segs(text):
        f = _font("ta_black" if t=="ta" else "en_black", sz)
        if shadow: draw.text((cx+3,y+3),seg,font=f,fill=(0,0,0,80),anchor="lt")
        draw.text((cx,y),seg,font=f,fill=col,anchor="lt")
        cx += draw.textbbox((0,0),seg,font=f)[2]
    return cx

def _text_w(draw, text, sz):
    w=0
    for seg,t in _segs(text):
        f=_font("ta_black" if t=="ta" else "en_black",sz)
        w+=draw.textbbox((0,0),seg,font=f)[2]
    return w

# ── Ken Burns effect ──────────────────────────────────────────────────
def ken_burns_frames(bg_img: np.ndarray, n_frames: int,
                     motion: str = "zoom_in") -> list:
    """Apply Ken Burns (zoom/pan) motion to an image over n_frames."""
    h, w = bg_img.shape[:2]
    frames = []
    for i in range(n_frames):
        t = i / max(n_frames-1, 1)  # 0→1

        if motion == "zoom_in":
            scale = KB_ZOOM_MIN + (KB_ZOOM_MAX - KB_ZOOM_MIN) * t
            ox = (w - w/scale) / 2
            oy = (h - h/scale) / 2
        elif motion == "zoom_out":
            scale = KB_ZOOM_MAX - (KB_ZOOM_MAX - KB_ZOOM_MIN) * t
            ox = (w - w/scale) / 2
            oy = (h - h/scale) / 2
        elif motion == "pan_right":
            scale = 1.08
            max_pan = w * (scale-1) / scale
            ox = max_pan * t
            oy = (h - h/scale) / 2
        elif motion == "pan_left":
            scale = 1.08
            max_pan = w * (scale-1) / scale
            ox = max_pan * (1-t)
            oy = (h - h/scale) / 2
        elif motion == "pan_up":
            scale = 1.08
            max_pan = h * (scale-1) / scale
            ox = (w - w/scale) / 2
            oy = max_pan * t
        else:  # static_slow_zoom
            scale = 1.0 + 0.04 * t
            ox = (w - w/scale) / 2
            oy = (h - h/scale) / 2

        # Crop region
        crop_w = int(w / scale)
        crop_h = int(h / scale)
        x1 = int(ox); y1 = int(oy)
        x1 = max(0, min(w-crop_w, x1))
        y1 = max(0, min(h-crop_h, y1))
        cropped = bg_img[y1:y1+crop_h, x1:x1+crop_w]
        resized = cv2.resize(cropped, (W, H), interpolation=cv2.INTER_LANCZOS4)
        frames.append(resized)
    return frames


def _make_bg(color=(15,15,20)) -> np.ndarray:
    """Default dark background when no image available."""
    bg = np.zeros((H, W, 3), dtype=np.uint8)
    bg[:] = color
    return bg


def _pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def _cv_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


# ── STAT scene ────────────────────────────────────────────────────────
def render_stat_frames(number: str, unit: str, n_frames: int,
                       bg_color=(8,8,15)) -> list:
    """Animated counter: counts up to the number over n_frames."""
    # Parse number
    clean = number.replace(",","")
    try: target = int(float(clean))
    except: target = 0

    frames = []
    for i in range(n_frames):
        t = i / max(n_frames-1, 1)
        # Ease-out: fast at start, slow at end
        ease = 1 - (1-t)**3
        current = int(target * ease)

        img = Image.new("RGB",(W,H),bg_color)
        draw = ImageDraw.Draw(img)

        # Large counter number
        num_str = f"{current:,}"
        sz = 220
        nw = _text_w(draw, num_str, sz)
        _draw_text(draw, num_str, (W-nw)//2, H//2 - 160, sz, (255,220,50), shadow=True)

        # Unit below
        unit_sz = 90
        uw = _text_w(draw, unit.upper(), unit_sz)
        _draw_text(draw, unit.upper(), (W-uw)//2, H//2+100, unit_sz, (200,200,200))

        # Progress bar
        bar_w = int((W-200) * ease)
        draw.rectangle([100, H-80, 100+bar_w, H-50], fill=(255,200,30))
        draw.rectangle([100, H-80, W-100, H-50], outline=(80,80,80), width=2)

        frames.append(_pil_to_cv(img))
    return frames


# ── MAP scene ─────────────────────────────────────────────────────────
# Predefined country approximate coords on a 1920x1080 equirectangular map
COUNTRY_COORDS = {
    "India":       (1320, 420), "China":      (1450, 340), "Russia":    (1350, 220),
    "France":      (940, 290),  "Britain":    (910, 260),  "Egypt":     (1060, 390),
    "America":     (450, 330),  "Rome":       (990, 310),  "Europe":    (960, 280),
    "Japan":       (1580, 340), "Africa":     (1020, 470), "Delhi":     (1295, 405),
    "Mumbai":      (1270, 440), "Chennai":    (1310, 470), "Madurai":   (1310, 480),
    "Thanjavur":   (1315, 475), "Mysore":     (1290, 468), "Vijayanagara":(1285,460),
    "தமிழ்நாடு":  (1310, 475), "ஆந்திரா":   (1310, 460), "கர்நாடகா": (1288,462),
    "தஞ்சாவூர்":  (1315, 475), "மதுரை":     (1310, 480),
}

def render_map_frames(location: str, n_frames: int) -> list:
    """Generate map frames with animated pin dropping and zoom."""
    # Load a world map silhouette (generate simple one if unavailable)
    map_img = _generate_simple_map()

    coords = COUNTRY_COORDS.get(location, (960, 400))
    cx, cy = coords
    frames = []

    for i in range(n_frames):
        t = i / max(n_frames-1, 1)

        # Zoom toward location over first half
        if t < 0.5:
            # Zoom in
            zoom = 1.0 + t * 0.4
            frame = _zoom_toward(map_img.copy(), cx, cy, zoom)
        else:
            # Hold at zoom level, pulse pin
            zoom = 1.2
            frame = _zoom_toward(map_img.copy(), cx, cy, zoom)

        pil = _cv_to_pil(frame)
        draw = ImageDraw.Draw(pil)

        # Animated pin drop
        pin_visible = t > 0.15
        if pin_visible:
            pin_t = min(1.0, (t - 0.15) / 0.25)  # 0→1 as pin drops
            # Map coords to frame coords after zoom
            mx, my = _map_to_frame(cx, cy, cx, cy, zoom, W, H)
            pin_y = int(my - 80 + 80 * (1 - pin_t))  # drops from above

            # Draw pin
            draw.ellipse([mx-20, pin_y+50, mx+20, pin_y+90], fill=(220,40,40))
            draw.polygon([(mx,pin_y+50),(mx-15,pin_y+20),(mx+15,pin_y+20)], fill=(220,40,40))
            draw.ellipse([mx-8, pin_y+58, mx+8, pin_y+74], fill=(255,180,180))

            # Pulse ring
            if t > 0.4:
                pulse = ((t-0.4) % 0.3) / 0.3
                r = int(30 + 60 * pulse)
                alpha = int(255 * (1-pulse))
                draw.ellipse([mx-r,my+70-r,mx+r,my+70+r],
                             outline=(220,40,40), width=3)

        # Location label
        if t > 0.5:
            sz = 72
            lw = _text_w(draw, location, sz)
            _draw_text(draw, location, (W-lw)//2, H-140, sz, (255,255,255))

        frames.append(_pil_to_cv(pil))
    return frames


def _generate_simple_map() -> np.ndarray:
    """Generate a minimal world silhouette map."""
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (12, 20, 45)  # deep blue ocean

    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    # Simple continent blobs (rough)
    continents = [
        # North America
        [(200,150),(550,150),(600,350),(550,500),(300,500),(180,350)],
        # South America
        [(350,520),(520,520),(530,750),(400,850),(320,750)],
        # Europe
        [(870,180),(1060,180),(1080,350),(940,380),(870,300)],
        # Africa
        [(960,380),(1130,380),(1140,680),(1040,780),(920,680),(900,480)],
        # Asia
        [(1080,140),(1700,140),(1720,550),(1500,600),(1200,560),(1060,400)],
        # Australia
        [(1480,650),(1680,650),(1700,800),(1560,850),(1440,780)],
    ]
    for cont in continents:
        draw.polygon(cont, fill=(45,90,45), outline=(60,110,60))

    return _pil_to_cv(pil)


def _zoom_toward(frame_bgr, cx, cy, zoom):
    h, w = frame_bgr.shape[:2]
    crop_w = int(w / zoom); crop_h = int(h / zoom)
    x1 = max(0, min(w-crop_w, cx - crop_w//2))
    y1 = max(0, min(h-crop_h, cy - crop_h//2))
    cropped = frame_bgr[y1:y1+crop_h, x1:x1+crop_w]
    return cv2.resize(cropped, (W,H), interpolation=cv2.INTER_LINEAR)

def _map_to_frame(px, py, cx, cy, zoom, fw, fh):
    # After zooming toward cx,cy: where does (px,py) appear?
    scale = fw / (fw/zoom)
    dx = (px - cx + fw/(2*zoom)) * zoom
    dy = (py - cy + fh/(2*zoom)) * zoom
    return int(dx), int(dy)


# ── TIMELINE scene ────────────────────────────────────────────────────
def render_timeline_frames(date: str, all_dates: list, n_frames: int) -> list:
    """Animated horizontal timeline highlighting the current date."""
    # Use up to 6 dates for the timeline
    dates_to_show = sorted(set(all_dates))[:6]
    if date not in dates_to_show:
        dates_to_show.append(date)
        dates_to_show.sort()
    if not dates_to_show:
        dates_to_show = [date]

    n = len(dates_to_show)
    frames = []
    LINE_Y = H // 2
    LINE_X1 = 200; LINE_X2 = W - 200
    STEP = (LINE_X2 - LINE_X1) // max(n-1,1)

    for i in range(n_frames):
        t = i / max(n_frames-1,1)

        img = Image.new("RGB",(W,H),(12,12,20))
        draw = ImageDraw.Draw(img)

        # Draw timeline line (animated)
        line_end = LINE_X1 + int((LINE_X2-LINE_X1)*min(1.0,t*2))
        draw.line([(LINE_X1,LINE_Y),(line_end,LINE_Y)], fill=(80,80,100), width=4)

        for j, d in enumerate(dates_to_show):
            dx = LINE_X1 + j*STEP
            is_current = (d == date)
            if dx > line_end: break  # not drawn yet

            dot_t = min(1.0, (t*2 - j*0.3))
            if dot_t <= 0: continue

            dot_r  = 16 if is_current else 10
            dot_col = (255,200,50) if is_current else (100,150,200)

            # Pulse for current
            if is_current and t > 0.5:
                pulse = ((t-0.5)*4 % 1.0)
                pr = int(dot_r + 25*pulse)
                draw.ellipse([dx-pr,LINE_Y-pr,dx+pr,LINE_Y+pr],
                             outline=(255,200,50,100), width=2)

            draw.ellipse([dx-dot_r,LINE_Y-dot_r,dx+dot_r,LINE_Y+dot_r], fill=dot_col)

            # Date label
            sz = 52 if is_current else 38
            col = (255,220,50) if is_current else (180,180,200)
            dw = _text_w(draw, d, sz)
            _draw_text(draw, d, dx-dw//2, LINE_Y-90 if j%2==0 else LINE_Y+45, sz, col, shadow=False)

        # "Timeline" label
        f_lbl = _font("en_bold", 36)
        draw.text((LINE_X1, LINE_Y-140), "TIMELINE", font=f_lbl, fill=(80,80,100))

        frames.append(_pil_to_cv(img))
    return frames


# ── CAPTION INTERRUPT scene ───────────────────────────────────────────
def render_caption_frames(words: list, n_frames: int, color=(255,220,30)) -> list:
    """Full-screen bold caption — pattern interrupt."""
    frames = []
    # Show each word chunk for equal time
    chunk_frames = max(1, n_frames // max(len(words),1))

    for i in range(n_frames):
        chunk_idx = min(i // chunk_frames, len(words)-1)
        word = words[chunk_idx].upper()
        t_in_chunk = (i % chunk_frames) / chunk_frames

        img = Image.new("RGB",(W,H),(8,8,8))
        draw = ImageDraw.Draw(img)

        # Scale word to fill width
        for sz in [280,240,200,160,120,90]:
            ww = _text_w(draw, word, sz)
            if ww < W-120: break

        # Animate: scale in
        scale_t = min(1.0, t_in_chunk*8)
        cur_sz = max(40, int(sz * (0.7 + 0.3*scale_t)))
        ww = _text_w(draw, word, cur_sz)
        _draw_text(draw, word, (W-ww)//2, H//2 - cur_sz//2, cur_sz, color)

        frames.append(_pil_to_cv(img))
    return frames


# ── ICON scene ────────────────────────────────────────────────────────
def _get_icon_svg(icon_type: str) -> str:
    """Return SVG paths for an icon type."""
    ICONS = {
        "sword": [("M 20 95 L 80 20 M 75 18 L 85 25 M 80 20 L 90 15 L 88 25 L 80 20",4),
                  ("M 18 90 L 28 98 L 95 15 L 85 8",3)],
        "crown": [("M 10 80 L 20 40 L 40 65 L 60 20 L 80 65 L 100 40 L 110 80 Z",3.5),
                  ("M 10 80 L 110 80",4),("M 30 80 A 8 8 0 1 0 30 81",2.5),
                  ("M 60 80 A 8 8 0 1 0 60 81",2.5),("M 90 80 A 8 8 0 1 0 90 81",2.5)],
        "coins": [("M 30 70 A 25 10 0 1 0 90 70 A 25 10 0 1 0 30 70 Z",3),
                  ("M 30 70 L 30 80 A 25 10 0 1 0 90 80 L 90 70",3),
                  ("M 30 55 A 25 10 0 1 0 90 55 A 25 10 0 1 0 30 55 Z",3),
                  ("M 30 55 L 30 65 A 25 10 0 1 0 90 65 L 90 55",3)],
        "soldier":[("M 55 15 A 12 12 0 1 0 55 39",3),("M 55 39 L 55 68",3.5),
                   ("M 35 52 L 55 46 L 75 52",3.5),("M 55 68 L 38 92",3.5),
                   ("M 55 68 L 72 92",3.5),("M 30 25 L 55 20 L 80 28 L 75 38 L 35 35 Z",2.5)],
        "castle": [("M 20 90 L 20 40 L 35 40 L 35 30 L 45 30 L 45 40 L 55 40 L 55 30 L 65 30 L 65 40 L 75 40 L 75 30 L 85 30 L 85 40 L 100 40 L 100 90 Z",3.5),
                   ("M 20 90 L 100 90",4),("M 50 90 L 50 65 L 70 65 L 70 90",3)],
        "ship":   [("M 20 70 Q 60 50 100 70",3.5),("M 60 70 L 60 25",3),
                   ("M 60 25 L 95 50 L 60 50",2.5),("M 20 70 L 20 82 Q 60 90 100 82 L 100 70",3)],
        "fire":   [("M 60 90 C 30 80 20 60 35 45 C 40 38 45 42 40 50 C 45 35 55 25 60 15 C 65 25 75 35 80 50 C 75 42 80 38 85 45 C 100 60 90 80 60 90 Z",3.5),
                   ("M 60 80 C 45 72 40 60 50 52 C 55 58 60 50 60 40 C 65 50 70 58 70 68 C 65 72 62 78 60 80 Z",2.5)],
        "map_pin":[("M 60 15 A 28 28 0 1 0 60 71 A 28 28 0 1 0 60 15",3.5),
                   ("M 60 71 Q 45 82 60 100 Q 75 82 60 71",3.5),
                   ("M 60 35 A 8 8 0 1 0 60 51 A 8 8 0 1 0 60 35",2.5)],
        "skull":  [("M 30 60 A 30 35 0 1 1 90 60 L 90 75 L 30 75 Z",3.5),
                   ("M 40 78 L 40 95 M 60 78 L 60 95 M 80 78 L 80 95",3),
                   ("M 45 48 A 8 8 0 1 0 45 49",3),("M 75 48 A 8 8 0 1 0 75 49",3)],
        "trophy": [("M 30 20 L 90 20 L 85 60 Q 80 80 60 85 Q 40 80 35 60 Z",3.5),
                   ("M 25 20 Q 15 20 15 35 Q 15 55 35 60",3),
                   ("M 95 20 Q 105 20 105 35 Q 105 55 85 60",3),
                   ("M 45 85 L 45 100 L 75 100 L 75 85",3),("M 35 100 L 85 100",4)],
        "compass":[("M 60 15 A 45 45 0 1 0 60 105 A 45 45 0 1 0 60 15",3),
                   ("M 60 25 L 60 35 M 60 85 L 60 95 M 25 60 L 35 60 M 85 60 L 95 60",2.5),
                   ("M 45 45 L 60 75 L 75 45 L 60 60 Z",3.5)],
        "wave":   [("M 10 55 Q 25 35 40 55 Q 55 75 70 55 Q 85 35 100 55 Q 115 75 130 55",3.5),
                   ("M 10 75 Q 25 55 40 75 Q 55 95 70 75 Q 85 55 100 75",3)],
        "sun":    [("M 60 25 A 35 35 0 1 0 60 95 A 35 35 0 1 0 60 25",3.5),
                   ("M 60 8 L 60 18 M 60 102 L 60 112 M 18 60 L 28 60 M 92 60 L 102 60",3),
                   ("M 28 28 L 35 35 M 85 85 L 92 92 M 92 28 L 85 35 M 35 85 L 28 92",2.5)],
        "star":   [("M 60 12 L 72 48 L 110 48 L 80 68 L 92 105 L 60 82 L 28 105 L 40 68 L 10 48 L 48 48 Z",3.5)],
    }
    paths = ICONS.get(icon_type, ICONS["map_pin"])
    n = len(paths)
    parts = []
    for i,(d,sw) in enumerate(paths):
        length = max(60.0, len(re.findall(r'-?[\d.]+',d))//2*14.0)
        parts.append(f'<path d="{d}" fill="none" stroke="#F5C518" stroke-width="{sw*1.5:.1f}" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="{length:.0f}" stroke-dashoffset="{length:.0f}"><animate attributeName="stroke-dashoffset" from="{length:.0f}" to="0" dur="{1.5/n:.2f}s" begin="{i*1.5/n:.2f}s" fill="freeze"/></path>')
    return f'<svg width="300" height="300" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" style="background:#08080F">{"".join(parts)}</svg>'


def render_icon_scene_frames(icon_type: str, word: str, n_frames: int) -> list:
    """Icon draws itself over n_frames on dark background."""
    from icon_library import ICONS as LIB_ICONS, get_icon_paths
    import cairosvg

    try:
        icon_paths = get_icon_paths(icon_type)
    except:
        # fallback to local definition
        icon_paths = [(d,sw) for d,sw in [("M 20 20 L 100 100 M 100 20 L 20 100",4)]]

    ICON_SIZE = 480
    frames = []
    n_paths = len(icon_paths)

    for i in range(n_frames):
        t = i / max(n_frames-1,1)
        drawn = t * n_paths
        parts = []
        for pi,(d,sw) in enumerate(icon_paths):
            length = max(60.0, len(re.findall(r'-?[\d.]+',d))//2*14.0)
            lp = min(1.0, max(0.0, drawn-pi))
            dash = length*lp; gap = length-dash+1
            parts.append(f'<path d="{d}" fill="none" stroke="#F5C518" stroke-width="{sw*1.8:.1f}" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="{length:.0f}" stroke-dashoffset="{gap:.1f}"/>')

        svg = f'<svg width="{ICON_SIZE}" height="{ICON_SIZE}" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'
        ico = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(),output_width=ICON_SIZE,output_height=ICON_SIZE))).convert("RGBA")

        img = Image.new("RGB",(W,H),(8,8,15))
        draw = ImageDraw.Draw(img)
        ix = (W-ICON_SIZE)//2; iy = (H-ICON_SIZE-100)//2
        img.paste(ico,(ix,iy),ico)

        # Word label
        sz=90; ww=_text_w(draw,word.upper(),sz)
        _draw_text(draw,word.upper(),(W-ww)//2,H-130,sz,(255,200,50),shadow=True)

        frames.append(_pil_to_cv(img))
    return frames


# ── Render a complete scene to list of BGR frames ─────────────────────
def render_scene(scene: dict, bg_image_path: str = None) -> list:
    """
    Render all frames for one storyboard scene.
    Returns list of BGR numpy arrays.
    """
    dur = scene["duration"]
    n_frames = max(int(dur * FPS), 1)
    v = scene["visual"]
    vtype = v.get("type","image")
    motion = v.get("motion","zoom_in")

    if vtype == "stat" and scene.get("numbers"):
        n, u = scene["numbers"][0]
        frames = render_stat_frames(n, u, n_frames)

    elif vtype == "map" and v.get("location"):
        frames = render_map_frames(v["location"], n_frames)

    elif vtype == "timeline":
        frames = render_timeline_frames(
            v.get("date","?"), v.get("all_dates",[]), n_frames)

    elif vtype == "icon" and v.get("icon"):
        frames = render_icon_scene_frames(v["icon"], v.get("word",""), n_frames)

    elif vtype == "caption":
        frames = render_caption_frames(scene.get("caption_lines",[""]), n_frames)

    else:
        # Default: Ken Burns on background image or gradient
        if bg_image_path and Path(bg_image_path).exists():
            pil = Image.open(bg_image_path).convert("RGB").resize((W,H),Image.LANCZOS)
            bg = _pil_to_cv(pil)
        else:
            # Gradient dark background
            bg = _make_gradient_bg(scene.get("scene_id",1))
        frames = ken_burns_frames(bg, n_frames, motion)

    # Add caption overlay to all frames
    frames = _overlay_captions(frames, scene)

    # Pattern interrupt: if flagged, add 4-frame flash cut
    if scene.get("pattern_interrupt") and len(frames) > 8:
        flash = _make_flash_frames(4)
        frames = flash + frames[4:]

    return frames


def _make_gradient_bg(scene_id: int) -> np.ndarray:
    """Generate a unique dark gradient background per scene."""
    palettes = [
        [(8,8,20),(30,15,50)],   # deep purple
        [(5,15,5),(10,50,20)],   # dark green
        [(20,5,5),(60,15,10)],   # dark red
        [(5,15,25),(10,30,60)],  # dark blue
        [(20,15,5),(55,40,10)],  # dark amber
    ]
    c1,c2 = palettes[scene_id % len(palettes)]
    img = np.zeros((H,W,3),dtype=np.uint8)
    for y in range(H):
        t = y/H
        r = int(c1[0]*(1-t)+c2[0]*t)
        g = int(c1[1]*(1-t)+c2[1]*t)
        b = int(c1[2]*(1-t)+c2[2]*t)
        img[y,:] = [b,g,r]  # BGR
    return img


def _overlay_captions(frames: list, scene: dict) -> list:
    """Overlay word-by-word captions at bottom of frames."""
    caption_lines = scene.get("caption_lines",[])
    if not caption_lines: return frames

    total = len(frames)
    frames_per_line = max(1, total // max(len(caption_lines),1))

    result = []
    for i, frame in enumerate(frames):
        line_idx = min(i // frames_per_line, len(caption_lines)-1)
        caption = caption_lines[line_idx]
        t_in_line = (i % frames_per_line) / frames_per_line

        pil = _cv_to_pil(frame)
        draw = ImageDraw.Draw(pil)

        sz = 62
        # Semi-transparent bar
        bar_h = 100
        overlay = Image.new("RGBA",(W,bar_h),(0,0,0,160))
        pil.paste(overlay,(0,H-bar_h),overlay)

        # Caption text — fade in
        alpha_t = min(1.0, t_in_line*6)
        cw = _text_w(draw, caption.upper(), sz)
        _draw_text(draw, caption.upper(), (W-cw)//2, H-bar_h+18, sz,
                   (255,220,50), shadow=False)

        result.append(_pil_to_cv(pil))
    return result


def _make_flash_frames(n: int) -> list:
    """Bright white flash frames for pattern interrupt."""
    frames = []
    for i in range(n):
        t = i/n
        v = int(255*(1-t**0.5))
        frame = np.full((H,W,3),v,dtype=np.uint8)
        frames.append(frame)
    return frames
