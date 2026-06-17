#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     துளிர் — Tamil Life Skills & Motivation Bot v1.0            ║
║  Whiteboard-style animation + Tamil TTS + BGM                   ║
║  Style inspired by Almost Everything YouTube channel            ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, re, json, time, hashlib, asyncio, subprocess, textwrap, random
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ── Dirs ──────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent
THULIR_DIR = BASE / "thulir"
SCRIPTS_T  = THULIR_DIR / "scripts"
AUDIO_T    = THULIR_DIR / "audio"
FRAMES_T   = THULIR_DIR / "frames"
VIDEOS_T   = THULIR_DIR / "videos"
THUMBS_T   = THULIR_DIR / "thumbnails"
CACHE_T    = THULIR_DIR / "cache"
BGM_T      = THULIR_DIR / "bgm"
for d in [SCRIPTS_T, AUDIO_T, FRAMES_T, VIDEOS_T, THUMBS_T, CACHE_T, BGM_T]:
    d.mkdir(parents=True, exist_ok=True)

# ── Fonts ──────────────────────────────────────────────────────────────
FONT_PATHS = {
    "bold"    : "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "regular" : "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "black"   : "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "semibold": "/usr/share/fonts/truetype/noto/NotoSansTamil-SemiBold.ttf",
}

# ── Colours — clean whiteboard palette ───────────────────────────────
WHITE      = (255, 255, 255)
OFF_WHITE  = (252, 252, 248)   # slightly warm white background
BLACK      = (30,  30,  30)    # soft black — not pure black
ACCENT_1   = (34,  139,  34)   # forest green (thuliR brand)
ACCENT_2   = (220,  53,  69)   # warm red for emphasis
ACCENT_3   = (255, 165,   0)   # amber for highlights
GREY_LIGHT = (230, 230, 230)   # divider lines
GREY_MID   = (150, 150, 150)   # subtext
BRAND_GREEN= (45,  106,  79)   # Thulir deep green

W, H = 1920, 1080

# ── Voice ─────────────────────────────────────────────────────────────
VOICE_ID = "ta-IN-PallaviNeural"
TTS_RATE  = "-10%"
TTS_PITCH = "+2Hz"

# ── LLM ───────────────────────────────────────────────────────────────
sys.path.insert(0, str(BASE))
from llm_client import generate_text

THULIR_STATE = THULIR_DIR / "thulir_state.json"

# ─────────────────────────────────────────────────────────────────────
# TOPIC BANK
# ─────────────────────────────────────────────────────────────────────
TOPIC_BANK = [
    {"topic": "தோல்வியை வெல்வது எப்படி?",       "category": "resilience",    "hook": "உன் மிகப்பெரிய தோல்வி உன்னை என்ன சொல்லித்தந்தது?"},
    {"topic": "காலை நேரத்தை சரியாக பயன்படுத்துவது எப்படி?", "category": "productivity","hook": "உலகின் வெற்றியாளர்கள் எல்லாரும் ஒரு பழக்கம் வைத்திருக்கார்கள்"},
    {"topic": "No சொல்ல தெரியாதவர்களுக்கு",       "category": "boundaries",    "hook": "ஒரே வார்த்தை உன் வாழ்க்கையை மாற்றும்"},
    {"topic": "First Salary-ல் என்ன செய்யணும்?",   "category": "finance",       "hook": "முதல் சம்பளத்தில் 80% பேர் செய்யும் தவறு"},
    {"topic": "Toxic நண்பர்களை எப்படி identify பண்றது?", "category": "relationships","hook": "இந்த 5 signs இருந்தால் உன் நண்பன் toxic"},
    {"topic": "Anxiety-ஐ எப்படி handle பண்றது?",   "category": "mental_health", "hook": "மனசு ஓயாம ஓடுதா? இந்த ஒரு technique try பண்ணு"},
    {"topic": "தினமும் படிக்கும் பழக்கம் எப்படி வரும்?", "category": "habits",      "hook": "ஒரு நாளில் 20 நிமிடம் போதும் — life மாறும்"},
    {"topic": "Social Media addiction-ஐ break பண்றது எப்படி?", "category": "digital","hook": "நீ scroll பண்றது உன் brain-ஐ damage பண்றது"},
    {"topic": "Parents-கிட்ட Career பத்தி எப்படி பேசுவது?", "category": "family",    "hook": "இந்த ஒரு conversation உன் வாழ்க்கையை மாற்றும்"},
    {"topic": "Comparison trap-இல் இருந்து விடுபடுவது எப்படி?", "category": "mindset","hook": "அவங்க வாழ்க்கையை பார்த்து நீ ஏன் வலிக்கிறாய்?"},
    {"topic": "SIP என்றால் என்ன? ₹500-ல் ஆரம்பிக்கலாம்", "category": "finance",    "hook": "20 வயதில் ₹500 போட்டால் 60-ல் என்ன கிடைக்கும்?"},
    {"topic": "தன்னம்பிக்கை எப்படி வரும்?",          "category": "confidence",    "hook": "Self confidence ஒரு skill — பிறக்கும்போது வருவதில்லை"},
    {"topic": "Time management — எளிய Tamil guide",    "category": "productivity", "hook": "24 மணி நேரமும் உனக்கு இருக்கிறது — சரியா பயன்படுத்துகிறாயா?"},
    {"topic": "உன்னை நீயே அறிவது எப்படி? Self awareness", "category": "mindset",   "hook": "உன்னை பத்தி உனக்கே தெரியலன்னா எப்படி grow பண்றது?"},
    {"topic": "Emergency fund ஏன் வேணும்? எப்படி உருவாக்குவது?", "category": "finance","hook": "ஒரு unexpected expense உன் எல்லா savings-ஐயும் அழிக்கலாம்"},
]


# ─────────────────────────────────────────────────────────────────────
# SCRIPT GENERATION
# ─────────────────────────────────────────────────────────────────────
SCRIPT_PROMPT = """நீங்கள் "துளிர்" YouTube சேனலுக்கு Tamil life skills script எழுதுகிறீர்கள்.
இந்த channel Almost Everything போன்று whiteboard animation + voiceover format-ல் இயங்குகிறது.

விஷயம்: {topic}
Category: {category}
Hook: {hook}

TARGET AUDIENCE: 18-32 வயது Tamil youth — students, fresh graduates, young professionals

NARRATOR STYLE:
நீங்கள் ஒரு அக்கா அல்லது அண்ணன் போல் பேசுகிறீர்கள் — warm, direct, practical.
"நீ", "உன்னோட" — second person. Conversational. பேச்சு வழக்கு தமிழ்.
Formal இல்லை. Preachy இல்லை. Real talk மட்டும்.

VIDEO STRUCTURE — சரியாக 8 scenes:

Scene 1 — HOOK (15 seconds):
❌ BANNED: "நமஸ்காரம்", "வணக்கம்", "இன்று நாம் பார்க்கப் போவது"
✅ START with: shocking fact / relatable problem / direct question
ஒரு situation describe பண்ணு — viewer "இது என்னக்காக பேசுகிறது" என்று feel ஆகணும்
[SCENE_END]

Scene 2 — THE PROBLEM (real + relatable):
இந்த பிரச்சனை ஏன் நடக்கிறது? Root cause என்ன?
ஒரு specific relatable example கொடு — character-க்கு Tamil பெயர் கொடு
[SCENE_END]

Scene 3 — WHY IT MATTERS:
இதை fix பண்ணாம விட்டால் என்ன ஆகும்? Consequences be honest
[SCENE_END]

Scene 4 — SOLUTION PART 1 (practical step):
First actionable step — simple, specific, doable today
[SCENE_END]

Scene 5 — SOLUTION PART 2:
Second practical step — with a real example
[SCENE_END]

Scene 6 — SOLUTION PART 3:
Third step — the most important one, save the best for now
[SCENE_END]

Scene 7 — REAL STORY / PROOF:
ஒரு real Tamil person-ன் கதை அல்லது உன்னோட personal experience போல் சொல்
Before → After தெளிவாக சொல்
[SCENE_END]

Scene 8 — CLOSING + CTA:
ஒரு powerful one-liner closing statement
"இதை try பண்ணுட்டு comment-ல் சொல்லு 👇"
Channel subscribe CTA: "துளிர் channel subscribe பண்ணு — வாரம் 2 videos 🔔"
[SCENE_END]

⚠️ RULES:
1. தமிழ் மட்டும் (English terms OK: SIP, toxic, burnout, anxiety)
2. Headers இல்லை, bullets இல்லை, markdown இல்லை
3. ஒவ்வொரு scene-ம் 4-6 வாக்கியங்கள் — short, punchy
4. [SCENE_END] மட்டும் scene boundary marker-ஆக பயன்படுத்து
5. Practical — abstract philosophy வேண்டாம்
6. Numbers, percentages, specific examples — mandatory

இப்போது Scene 1 முதல் எழுது:"""


def load_state() -> Dict:
    if THULIR_STATE.exists():
        return json.loads(THULIR_STATE.read_text("utf-8"))
    return {"used_topics": [], "total_runs": 0}


def save_state(state: Dict):
    THULIR_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def pick_topic() -> Dict:
    state = load_state()
    used  = state.get("used_topics", [])
    available = [t for t in TOPIC_BANK if t["topic"] not in used[-20:]]
    if not available:
        available = TOPIC_BANK
    topic = random.choice(available)
    state["used_topics"] = (used + [topic["topic"]])[-30:]
    state["total_runs"]  = state.get("total_runs", 0) + 1
    save_state(state)
    return topic


def generate_script(topic_info: Dict) -> List[str]:
    """Generate script and split into scenes."""
    slug  = hashlib.md5(topic_info["topic"].encode()).hexdigest()[:8]
    cache = CACHE_T / f"script_{slug}.json"
    if cache.exists():
        log.info("Script cache hit")
        return json.loads(cache.read_text("utf-8"))

    log.info(f"Generating script: {topic_info['topic']}")
    raw = generate_text(SCRIPT_PROMPT.format(**topic_info), max_tokens=3000)

    # Split into scenes — try [SCENE_END] first, then fallback strategies
    scenes = [s.strip() for s in raw.split("[SCENE_END]") if s.strip()]
    scenes = [re.sub(r'\[PAUSE_\w+\]', '', s).strip() for s in scenes]
    scenes = [re.sub(r'^Scene\s*\d+[^\n]*\n', '', s, flags=re.MULTILINE).strip() for s in scenes]
    scenes = [s for s in scenes if len(s) > 20]

    if len(scenes) < 4:
        log.warning(f"Only {len(scenes)} scenes from [SCENE_END] — trying paragraph split")
        # Try splitting by double newline
        paras = [p.strip() for p in raw.split("\n\n") if len(p.strip()) > 40]
        if len(paras) >= 4:
            scenes = paras[:8]
        else:
            # Last resort: split by numbered headings or single newlines
            parts = re.split(r'\n(?=Scene \d|\d+\.)', raw)
            parts = [p.strip() for p in parts if len(p.strip()) > 40]
            scenes = parts[:8] if len(parts) >= 4 else [raw]

    # If still not enough, re-prompt with explicit instructions
    if len(scenes) < 4 and len(raw) > 100:
        log.warning(f"Still only {len(scenes)} scenes — forcing sentence split")
        import textwrap
        sentences = re.split(r'(?<=[.!?])\s+', raw)
        chunk_size = max(1, len(sentences) // 6)
        scenes = [" ".join(sentences[i:i+chunk_size])
                  for i in range(0, len(sentences), chunk_size)][:8]
        scenes = [s for s in scenes if len(s) > 20]

    # If still too few scenes, retry once with explicit format instructions
    if len(scenes) < 4:
        log.warning(f"Only {len(scenes)} scenes after all splitting — retrying with strict format")
        retry_prompt = (
            "Write EXACTLY 6 short paragraphs in Tamil about: " + topic_info["topic"] + "\n"
            "Separate each paragraph with the text [SCENE_END] on its own line.\n"
            "Each paragraph: 3-4 sentences, practical, conversational Tamil.\n"
            "Paragraph 1: Hook question\n"
            "Paragraph 2: The problem\n"
            "Paragraph 3: Why it matters\n"
            "Paragraph 4: Solution step 1\n"
            "Paragraph 5: Solution step 2\n"
            "Paragraph 6: Conclusion + subscribe CTA\n"
        )
        raw2 = generate_text(retry_prompt, max_tokens=2000)
        scenes2 = [s.strip() for s in raw2.split("[SCENE_END]") if s.strip() and len(s.strip()) > 20]
        if len(scenes2) >= 4:
            scenes = scenes2
            log.info(f"Retry succeeded: {len(scenes)} scenes")

    log.info(f"Script: {len(scenes)} scenes, {sum(len(s.split()) for s in scenes)} words")
    cache.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), "utf-8")
    return scenes


# ─────────────────────────────────────────────────────────────────────
# TTS — Tamil voiceover with SSML naturalness
# ─────────────────────────────────────────────────────────────────────
async def _tts_async(text: str, out_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE_ID, rate=TTS_RATE, pitch=TTS_PITCH)
    await communicate.save(str(out_path))


def synthesise_scene_audio(scene_text: str, scene_idx: int, slug: str) -> Tuple[Path, float]:
    """Generate audio for a single scene. Returns (path, duration_seconds)."""
    out = AUDIO_T / f"{slug}_scene_{scene_idx:02d}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        dur = _get_duration(out)
        return out, dur

    # Clean text for TTS
    clean = re.sub(r'[*_#>`\[\]]', '', scene_text)
    clean = re.sub(r'\s+', ' ', clean).strip()

    asyncio.run(_tts_async(clean, out))
    dur = _get_duration(out)
    log.info(f"  Scene {scene_idx}: {dur:.1f}s audio")
    return out, dur



def _get_duration(path: Path) -> float:
    """Get audio/video duration in seconds via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True
        )
        return float(r.stdout.strip())
    except Exception:
        return 30.0


def ensure_bgm(duration: int = 660) -> Path:
    """Generate calm motivational BGM if not already cached."""
    if BGM_T.exists():
        existing = list(BGM_T.glob("*.mp3"))
        if existing and existing[0].stat().st_size > 50_000:
            return existing[0]

    bgm_file = BGM_T / "thulir_bgm.mp3"
    log.info("Generating Thulir BGM...")
    filter_cx = (
        "[0]volume=0.10,aecho=0.7:0.65:90:0.30[s1];"
        "[1]volume=0.07,aecho=0.6:0.55:140:0.20[s2];"
        "[2]volume=0.06[s3];"
        "[s1][s2][s3]amix=inputs=3:duration=longest[mix];"
        "[mix]"
        "equalizer=f=200:t=q:w=1.0:g=+4,"
        "equalizer=f=4000:t=q:w=1.0:g=-6,"
        f"afade=t=in:d=4,afade=t=out:st={max(0, duration-6)}:d=6,"
        "loudnorm=I=-24:TP=-3:LRA=8[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=261:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=329:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=392:duration={duration}",
        "-filter_complex", filter_cx,
        "-map", "[out]", "-ar", "44100", "-b:a", "128k", str(bgm_file)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Simple fallback
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=261:duration={duration}",
            "-af", f"volume=0.06,afade=t=in:d=4,afade=t=out:st={max(0,duration-5)}:d=5,loudnorm=I=-24",
            str(bgm_file)
        ], capture_output=True)
    log.info(f"BGM ready: {bgm_file.stat().st_size // 1024}KB")
    return bgm_file


def apply_voice_eq(raw_mp3: Path, out_mp3: Path) -> Path:
    eq = (
        "highpass=f=80,"
        "equalizer=f=200:t=q:w=0.9:g=1.5,"
        "equalizer=f=800:t=q:w=0.8:g=2.0,"
        "equalizer=f=3000:t=q:w=0.8:g=2.5,"
        "equalizer=f=6000:t=q:w=1.0:g=-2.0,"
        "aecho=0.75:0.62:26:0.05,"
        "acompressor=threshold=-20dB:ratio=1.7:attack=10:release=250:makeup=2.5,"
        "atempo=0.98,"
        "loudnorm=I=-14:TP=-1.5:LRA=11"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_mp3), "-af", eq, "-ar", "48000", "-b:a", "192k", str(out_mp3)],
        capture_output=True
    )
    if result.returncode != 0 or not out_mp3.exists():
        import shutil
        shutil.copy(raw_mp3, out_mp3)
    return out_mp3


# ─────────────────────────────────────────────────────────────────────
# WHITEBOARD FRAME GENERATOR
# ─────────────────────────────────────────────────────────────────────
def _load_font(key: str, size: int):
    from PIL import ImageFont
    path = FONT_PATHS.get(key, FONT_PATHS["regular"])
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> List[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_frame(
    all_words: list, visible: int,
    scene_label: str, scene_icon: str, label_color: tuple,
    scene_num: int, total_scenes: int, topic: str,
) -> "Image":
    """Render one animation frame — words appear one by one, last word highlighted."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (W, H), OFF_WHITE)
    draw = ImageDraw.Draw(img)

    # Top bar
    draw.rectangle([0, 0, W, 70], fill=BRAND_GREEN)
    draw.text((44, 18), "🌱  துளிர்", font=_load_font("bold", 32), fill=WHITE)
    pct = scene_num / max(total_scenes - 1, 1)
    draw.rectangle([0, 66, int(W * pct), 70], fill=(120, 210, 130))
    f_num = _load_font("regular", 24)
    num_txt = f"{scene_num + 1} / {total_scenes}"
    nw = draw.textbbox((0,0), num_txt, font=f_num)[2]
    draw.text((W - nw - 40, 20), num_txt, font=f_num, fill=WHITE)

    # Scene label pill
    f_lbl = _load_font("regular", 30)
    pill  = f"  {scene_icon}  {scene_label}  "
    pw    = draw.textbbox((0,0), pill, font=f_lbl)[2] + 10
    draw.rounded_rectangle([44, 90, 44+pw, 90+50], radius=12, fill=label_color)
    draw.text((54, 99), pill, font=f_lbl, fill=WHITE)

    # Words appearing one by one
    f_big  = _load_font("black",   72)
    f_norm = _load_font("bold",    60)
    MAX_W  = W - 100

    visible_words = all_words[:visible]
    lines = _wrap_words(visible_words, f_big, MAX_W, draw)

    y = 170
    word_idx = 0
    last_x = 52
    for li, line_words in enumerate(lines):
        x = 52
        f = f_big if li == 0 else f_norm
        for word in line_words:
            is_last = (word_idx == visible - 1) and (visible < len(all_words))
            col = ACCENT_2 if is_last else BLACK
            draw.text((x+2, y+2), word + " ", font=f, fill=GREY_LIGHT)
            draw.text((x,   y),   word + " ", font=f, fill=col)
            bbox = draw.textbbox((0,0), word + " ", font=f)
            last_x = x + bbox[2] - bbox[0]
            x = last_x
            word_idx += 1
        bbox_h = draw.textbbox((0,0), "A", font=f)[3]
        y += bbox_h + 16
        if y > H - 180:
            break

    # Blinking cursor after last word
    if visible < len(all_words):
        draw.rectangle([last_x, y - 68, last_x + 4, y + 4], fill=BRAND_GREEN)

    # Bottom bar
    draw.rectangle([44, H-110, W-44, H-107], fill=GREY_LIGHT)
    draw.text((48, H-96), f"📌  {topic[:60]}", font=_load_font("regular", 26), fill=GREY_MID)
    draw.text((W-260, H-96), "youtube.com/@thulir", font=_load_font("regular", 24), fill=GREY_MID)
    return img


def _wrap_words(words: list, font, max_w: int, draw) -> list:
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if draw.textbbox((0,0), test, font=font)[2] <= max_w or not cur:
            cur.append(w)
        else:
            lines.append(cur)
            cur = [w]
    if cur:
        lines.append(cur)
    return lines


async def _tts_with_word_timings(text: str, out_mp3: Path) -> list:
    """TTS + capture per-word timing via WordBoundary events."""
    import edge_tts
    timings = []
    communicate = edge_tts.Communicate(
        text, VOICE_ID, rate=TTS_RATE, pitch=TTS_PITCH, boundary="WordBoundary"
    )
    with open(out_mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_s = chunk["offset"] / 10_000_000
                dur_s   = chunk["duration"] / 10_000_000
                timings.append({"word": chunk["text"], "start": start_s,
                                 "end": start_s + dur_s})
    return timings


def synthesise_scene_audio(scene_text: str, scene_idx: int, slug: str):
    """Generate audio + word timings for one scene."""
    raw_mp3 = AUDIO_T / f"{slug}_scene_{scene_idx:02d}_raw.mp3"
    eq_mp3  = AUDIO_T / f"{slug}_scene_{scene_idx:02d}.mp3"
    timing_json = CACHE_T / f"{slug}_timing_{scene_idx:02d}.json"

    if eq_mp3.exists() and timing_json.exists() and eq_mp3.stat().st_size > 1000:
        dur = _get_duration(eq_mp3)
        timings = json.loads(timing_json.read_text())
        return eq_mp3, dur, timings

    clean = re.sub(r"[*_#>`\[\]]", "", scene_text)
    clean = re.sub(r"\s+", " ", clean).strip()

    try:
        timings = asyncio.run(_tts_with_word_timings(clean, raw_mp3))
    except Exception as e:
        log.warning(f"  TTS failed ({e}) — silence fallback")
        words = clean.split()
        dur_per = max(0.4, 8.0 / max(len(words), 1))
        timings = [{"word": w, "start": i*dur_per, "end": (i+1)*dur_per}
                   for i, w in enumerate(words)]
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                        f"anullsrc=r=44100:cl=mono","-t",
                        str(len(words)*dur_per), str(raw_mp3)],
                       capture_output=True)

    apply_voice_eq(raw_mp3, eq_mp3)
    timing_json.write_text(json.dumps(timings, ensure_ascii=False))

    dur = _get_duration(eq_mp3)
    log.info(f"  Scene {scene_idx}: {dur:.1f}s | {len(timings)} words")
    return eq_mp3, dur, timings


def render_scene_video(
    scene_text: str, scene_idx: int, total_scenes: int,
    slug: str, topic: str, audio: Path, timings: list, duration: float,
    scene_label: str, scene_icon: str, label_color: tuple,
) -> Path:
    """Render full animated video clip for one scene (word-by-word animation)."""
    out = FRAMES_T / f"{slug}_scene_{scene_idx:02d}.mp4"
    if out.exists() and out.stat().st_size > 10000:
        return out

    words       = scene_text.split()
    total_frames = int(duration * VIDEO_FPS) + VIDEO_FPS
    frame_dir   = FRAMES_T / f"{slug}_{scene_idx:02d}"
    frame_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"  Rendering {total_frames} frames (scene {scene_idx})...")
    prev_visible = -1
    last_img     = None

    for fi in range(total_frames):
        t       = fi / VIDEO_FPS
        visible = max(1, min(sum(1 for wt in timings if wt["start"] <= t), len(words)))
        frame_p = frame_dir / f"frame_{fi:05d}.png"

        if visible != prev_visible or last_img is None:
            img = _render_frame(
                all_words=words, visible=visible,
                scene_label=scene_label, scene_icon=scene_icon,
                label_color=label_color,
                scene_num=scene_idx, total_scenes=total_scenes, topic=topic,
            )
            last_img     = img
            prev_visible = visible

        last_img.save(str(frame_p), "PNG", optimize=True)

    # Encode frames → video with audio
    r = subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(VIDEO_FPS),
        "-i", str(frame_dir / "frame_%05d.png"),
        "-i", str(audio),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-shortest",
        str(out)
    ], capture_output=True, text=True, timeout=600)

    if r.returncode != 0:
        raise RuntimeError(f"Scene render failed: {r.stderr[-200:]}")

    # Cleanup frames to save disk
    import shutil
    shutil.rmtree(str(frame_dir), ignore_errors=True)
    log.info(f"  ✅ Scene {scene_idx} video: {out.stat().st_size//1024}KB")
    return out


def create_thumbnail(topic: str, hook: str, slug: str) -> Path:
    from PIL import Image, ImageDraw
    out = THUMBS_T / f"{slug}.jpg"
    if out.exists():
        return out
    W_T, H_T = 1280, 720
    img  = Image.new("RGB", (W_T, H_T), WHITE)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 10, H_T], fill=BRAND_GREEN)
    draw.rectangle([0, 0, W_T, 8], fill=BRAND_GREEN)
    draw.rounded_rectangle([28, 24, 220, 68], radius=8, fill=BRAND_GREEN)
    draw.text((44, 34), "🌱 துளிர்", font=_load_font("bold", 28), fill=WHITE)
    f_xl = _load_font("black", 86)
    f_lg = _load_font("bold",  62)
    words = hook.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textbbox((0,0), test, font=f_xl)[2] <= 1200:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    y = 110
    for i, line in enumerate(lines[:3]):
        f   = f_xl if i == 0 else f_lg
        col = BLACK if i == 0 else (50,50,50)
        draw.text((32+2, y+2), line, font=f, fill=GREY_LIGHT)
        draw.text((30,   y),   line, font=f, fill=col)
        y += draw.textbbox((0,0), line, font=f)[3] + 12
    draw.rectangle([28, y+18, 1250, y+22], fill=BRAND_GREEN)
    draw.text((30, y+32), topic, font=_load_font("semi", 36), fill=BRAND_GREEN)
    draw.rectangle([0, 660, W_T, H_T], fill=BRAND_GREEN)
    draw.text((34, 674), "Subscribe பண்ணி notification bell அடிக்கவும் 🔔",
              font=_load_font("bold", 28), fill=WHITE)
    img.save(str(out), "JPEG", quality=95)
    log.info(f"Thumbnail: {out}")
    return out


VIDEO_FPS = 24


def assemble_final_video(slug: str, scene_videos: list, bgm: Path, title: str) -> Path:
    """Concat all scene videos + mix BGM."""
    out = VIDEOS_T / f"{slug}.mp4"
    if out.exists():
        return out

    concat_file = CACHE_T / f"{slug}_concat.txt"
    with open(concat_file, "w") as f:
        for v in scene_videos:
            f.write(f"file '{v.resolve()}'\n")

    concat_raw = CACHE_T / f"{slug}_raw.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0",
                    "-i",str(concat_file),"-c","copy",str(concat_raw)],
                   capture_output=True, check=True)

    total_dur = _get_duration(concat_raw)
    log.info(f"Total video: {total_dur:.1f}s")

    filter_cx = (
        "[0:a]volume=1.0[voice];"
        f"[1:a]volume=0.07,aloop=loop=-1:size=2e+09,atrim=0:{total_dur:.2f}[bgm];"
        "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    timeout = max(600, int(total_dur * 3))
    r = subprocess.run([
        "ffmpeg","-y",
        "-i",str(concat_raw),
        "-i",str(bgm),
        "-filter_complex",filter_cx,
        "-map","0:v","-map","[aout]",
        "-c:v","libx264","-preset","veryfast","-crf","22",
        "-c:a","aac","-b:a","192k","-pix_fmt","yuv420p",
        str(out)
    ], capture_output=True, text=True, timeout=timeout)

    concat_raw.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"Final assembly failed: {r.stderr[-300:]}")
    log.info(f"✅ Final video: {out} ({out.stat().st_size//1024//1024}MB)")
    return out


META_PROMPT = """துளிர் YouTube channel video-க்கு metadata தரவும்.
Channel: துளிர் — Tamil Life Skills & Self Improvement
Topic: {topic}
Hook: {hook}
Script preview: {preview}

Return ONLY valid JSON (no markdown, no explanation):
{{"title":"<Tamil title under 65 chars — emotional or curiosity angle>",
"description":"<400 word Tamil description — hook first 2 lines, 3 takeaways, timestamps, CTA, hashtags>",
"tags":["வாழ்க்கை திறன்கள்","self improvement Tamil","motivation Tamil","thuliR","life skills Tamil","personal growth Tamil","youth Tamil"],
"pinned_comment":"<two-choice question under 150 chars>",
"thumbnail_hook":"<4-5 Tamil words for thumbnail>"}}"""


def generate_metadata(topic_info: Dict, scenes: List[str]) -> Dict:
    slug  = hashlib.md5(topic_info["topic"].encode()).hexdigest()[:8]
    cache = CACHE_T / f"meta_{slug}.json"
    if cache.exists():
        return json.loads(cache.read_text("utf-8"))
    preview = " ".join(scenes[:2])[:500]
    raw = generate_text(META_PROMPT.format(
        topic=topic_info["topic"],
        hook=topic_info["hook"],
        preview=preview
    ), max_tokens=2000)
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        meta = json.loads(raw)
    except Exception:
        meta = {
            "title": topic_info["topic"],
            "description": preview,
            "tags": ["துளிர்", "Tamil motivation", "life skills Tamil", "self improvement Tamil"],
            "pinned_comment": "இது உங்களுக்கும் helpful-ஆ இருந்துச்சா? Comment பண்ணுங்கள் 👇",
            "thumbnail_hook": topic_info["hook"][:30]
        }
    cache.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    return meta


# ─────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────
def run_pipeline(topic_info: Optional[Dict] = None, skip_upload: bool = True) -> Dict:
    if topic_info is None:
        topic_info = pick_topic()

    topic = topic_info["topic"]
    slug  = hashlib.md5(topic.encode()).hexdigest()[:10]

    log.info(f"\n{'='*60}")
    log.info(f"🌱 THULIR BOT")
    log.info(f"   Topic   : {topic}")
    log.info(f"   Category: {topic_info['category']}")
    log.info(f"   Hook    : {topic_info['hook']}")
    log.info(f"{'='*60}")

    # 1. Script
    log.info("📝 Generating script...")
    scenes = generate_script(topic_info)
    log.info(f"   {len(scenes)} scenes ready")

    # 2. Metadata
    log.info("🔍 Generating metadata...")
    meta = generate_metadata(topic_info, scenes)
    log.info(f"   Title: {meta.get('title','')[:60]}")

    # 3. BGM
    bgm = ensure_bgm()

    # 4. Word-by-word animated scenes (Almost Everything style)
    log.info("🎬 Rendering word-by-word animation scenes...")
    SCENE_META = [
        ("Hook",      "🎯", ACCENT_2),
        ("பிரச்சனை", "😟", ACCENT_2),
        ("ஏன்?",     "💡", ACCENT_3),
        ("படி 1",    "✅", ACCENT_1),
        ("படி 2",    "✅", ACCENT_1),
        ("படி 3",    "🌟", ACCENT_1),
        ("கதை",      "📖", BRAND_GREEN),
        ("முடிவு",   "💚", BRAND_GREEN),
    ]
    scene_videos: List[Path] = []

    for i, scene_text in enumerate(scenes):
        log.info(f"  Scene {i+1}/{len(scenes)}: audio + animation...")
        label, icon, color = SCENE_META[i % len(SCENE_META)]
        audio, dur, timings = synthesise_scene_audio(scene_text, i, slug)
        scene_vid = render_scene_video(
            scene_text=scene_text, scene_idx=i, total_scenes=len(scenes),
            slug=slug, topic=topic, audio=audio, timings=timings, duration=dur,
            scene_label=label, scene_icon=icon, label_color=color,
        )
        scene_videos.append(scene_vid)

        # 5. Thumbnail
    log.info("🖼️  Creating thumbnail...")
    thumb = create_thumbnail(topic, topic_info["hook"], slug)

    # 6. Assemble video
    log.info("🎬 Assembling final video...")
    title = meta.get("title", topic)
    video = assemble_final_video(slug, scene_videos, bgm, title)

    # 7. Save package
    pkg = {
        "topic"    : topic,
        "slug"     : slug,
        "title"    : title,
        "video"    : str(video),
        "thumbnail": str(thumb),
        "metadata" : meta,
        "scenes"   : len(scenes),
        "generated": time.strftime("%Y-%m-%d %H:%M UTC"),
    }
    (THULIR_DIR / f"{slug}_package.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2), "utf-8"
    )
    (SCRIPTS_T / f"{slug}.txt").write_text("\n\n---SCENE---\n\n".join(scenes), "utf-8")

    log.info(f"\n{'='*60}")
    log.info(f"✅ DONE")
    log.info(f"   Video     : {video}")
    log.info(f"   Thumbnail : {thumb}")
    log.info(f"   Title     : {title}")
    log.info(f"{'='*60}")

    return pkg


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Thulir Bot — Tamil Life Skills YouTube Automation")
    parser.add_argument("--topic-idx", type=int, default=None, help="Pick topic by index")
    parser.add_argument("--skip-upload", action="store_true", default=True, help="Skip YouTube upload (default: True)")
    parser.add_argument("--upload", action="store_true", default=False, help="Upload to YouTube")
    parser.add_argument("--list-topics", action="store_true", help="List all topics and exit")
    args = parser.parse_args()

    if args.list_topics:
        for i, t in enumerate(TOPIC_BANK):
            print(f"[{i:2d}] {t['topic']}")
        sys.exit(0)

    topic_info = None
    if args.topic_idx is not None:
        topic_info = TOPIC_BANK[args.topic_idx % len(TOPIC_BANK)].copy()
        log.info(f"Manual topic: {topic_info['topic']}")

    skip = not args.upload
    run_pipeline(topic_info, skip_upload=skip)
