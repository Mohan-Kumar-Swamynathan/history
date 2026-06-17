#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     வரலாறு விழிப்பு — Tamil History YouTube Bot v2.0            ║
║  Script → BGM → Voice → Video → Thumbnail → YouTube Upload      ║
║  With: BGM generation, daily scheduler, topic rotation          ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, re, time, hashlib, logging, subprocess, urllib.request, asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ── Dirs ─────────────────────────────────────────────────────────
BASE      = Path(__file__).parent
SCRIPTS   = BASE / "scripts"
AUDIO     = BASE / "audio"
VIDEOS    = BASE / "videos"
THUMBS    = BASE / "thumbnails"
CACHE     = BASE / "cache"
BGM_DIR   = BASE / "bgm"
for d in [SCRIPTS, AUDIO, VIDEOS, THUMBS, CACHE, BGM_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Config ───────────────────────────────────────────────────────
from llm_client import generate_text
from pexels_client import fetch_stock_clips
from youtube_uploader import upload_video

# ── Voice Profiles ───────────────────────────────────────────────
VOICE_PROFILES = {
    "male_warm": {
        "voice" : "ta-IN-ValluvarNeural",
        "rate"  : "-10%",   # slightly slower = storytelling cadence
        "pitch" : "+1Hz",   # tiny lift removes flat robotic quality
        "volume": "+8%",
        "desc"  : "Warm Tamil male storyteller",
    },
    "female_emotional": {
        "voice" : "ta-IN-PallaviNeural",
        "rate"  : "-10%",   # PallaviNeural sounds most natural at -10%
        "pitch" : "+2Hz",   # female voice benefits from slight lift
        "volume": "+8%",
        "desc"  : "Expressive Tamil female narrator",
    },
}
DEFAULT_VOICE = "male_warm"

PAUSE_MAP = {
    "[PAUSE_LONG]"  : 1800,
    "[PAUSE_MED]"   : 900,
    "[PAUSE_SHORT]" : 400,
    "[BREATH]"      : 250,
}

# ─────────────────────────────────────────────────────────────────
# BGM — generate Tamil ambient instrumental (no samples needed)
# ─────────────────────────────────────────────────────────────────
BGM_FILE = BGM_DIR / "tamil_instrumental.mp3"

def ensure_bgm(duration_s: int = 600) -> Path:
    """Generate BGM if not present. Uses FFmpeg sine synthesis."""
    if BGM_FILE.exists() and BGM_FILE.stat().st_size > 100_000:
        log.info(f"BGM exists: {BGM_FILE}")
        return BGM_FILE

    log.info("Generating Tamil ambient BGM (first-time setup, ~30s)…")
    d = duration_s

    # Pentatonic arpeggio: C(261) E(329) G(392) A(440) - Tamil-flavoured
    # Layer 1: Sa drone (261 Hz tanpura)
    # Layer 2: Pa (392 Hz)
    # Layer 3: Melody shimmer (329 Hz)
    # Layer 4: Bass pulse (130 Hz tabla-like)
    filter_cx = (
        "[0]volume=0.16,aecho=0.65:0.65:80:0.35[sa];"
        "[1]volume=0.10,aecho=0.60:0.60:120:0.25[pa];"
        "[2]volume=0.09,aecho=0.55:0.55:200:0.20[mel];"
        "[3]volume=0.08[bass];"
        "[sa][pa][mel][bass]amix=inputs=4:duration=longest:dropout_transition=3[mix];"
        "[mix]"
        "acompressor=threshold=-22dB:ratio=2.5:attack=20:release=200:makeup=3,"
        "equalizer=f=180:t=q:w=1.0:g=+3.5,"
        "equalizer=f=1200:t=q:w=1.0:g=-1,"
        "equalizer=f=5000:t=q:w=1.0:g=-5,"
        f"afade=t=in:d=5,afade=t=out:st={max(0,d-6)}:d=6,"
        "loudnorm=I=-22:TP=-3:LRA=12[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f","lavfi","-i",f"sine=frequency=261:duration={d}",
        "-f","lavfi","-i",f"sine=frequency=392:duration={d}",
        "-f","lavfi","-i",f"sine=frequency=329:duration={d}",
        "-f","lavfi","-i",f"sine=frequency=130:duration={d}",
        "-filter_complex", filter_cx,
        "-map","[out]","-ar","44100","-b:a","128k","-ac","2",
        str(BGM_FILE)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning("BGM multi-layer failed, using simple drone fallback…")
        cmd2 = [
            "ffmpeg","-y","-f","lavfi",
            "-i",f"sine=frequency=261:duration={d}",
            "-af",(f"volume=0.12,aecho=0.7:0.7:100:0.3,"
                   f"afade=t=in:d=4,afade=t=out:st={max(0,d-5)}:d=5,"
                   "loudnorm=I=-22:TP=-3"),
            "-ar","44100","-b:a","128k",str(BGM_FILE)
        ]
        subprocess.run(cmd2, capture_output=True, check=True)

    log.info(f"BGM ready: {BGM_FILE}  ({BGM_FILE.stat().st_size//1024} KB)")
    return BGM_FILE

# ─────────────────────────────────────────────────────────────────
# SCRIPT PROMPT
# ─────────────────────────────────────────────────────────────────
SCRIPT_PROMPT = """நீங்கள் "வரலாறு விழிப்பு" YouTube சேனலுக்காக Tamil History motivational storytelling script எழுதுகிறீர்கள்.

விஷயம்: {topic}
காலகட்டம்: {era}
Hook Style: {hook}
Target audience: 15-45 வயது தமிழர்கள் — students, professionals, entrepreneurs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎭 NARRATOR PERSONA:
நீங்கள் ஒரு தமிழ் தாத்தா போல் பேசுகிறீர்கள் — அக்கறையுடன், உணர்ச்சியுடன், ஆழமான அறிவுடன்.
ஒவ்வொரு வரலாற்று உண்மையும் ஒரு உயிரோட்டமான கதையாக மாறவேண்டும்.
கேட்பவர் "இது என் வாழ்க்கைக்கும் பொருந்துகிறது" என்று உணரவேண்டும்.
பேச்சு வழக்கு தமிழ் — எளிய, இனிமையான, உணர்ச்சிமிக்க வார்த்தைகள்.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 LENGTH: சரியாக 6 பிரிவுகள், ஒவ்வொன்றும் 7-9 வாக்கியங்கள் = 7-9 நிமிட video.
மொத்தம் 1400-1800 வார்த்தைகள்.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
பிரிவு 1 — HOOK (சஸ்பென்ஸ் தொடக்கம்):
❌ BANNED: "நமஸ்காரம் நண்பர்களே", "இன்று நாம் பார்க்கப் போவது", "வணக்கம்"
✅ தொடங்கு: கதையின் மிகவும் intense moment-ல் — போர்க்களத்தில், சிறையில், தோல்வியின் விளிம்பில்
அல்லது: "ஒரே ஒரு கேள்வி..." / அதிர்ச்சி தரும் வரலாற்று உண்மை
[PAUSE_LONG] hook-க்கு பிறகு கட்டாயம்.

பிரிவு 2 — கால பின்னணி & கதாபாத்திரம் (Background):
குறிப்பிட்ட ஆண்டு, ஊர், கோட்டை, ஆறு, பிரதேசம் பெயர் சேர்க்கவும்.
கதாநாயகன்/நாயகி: உண்மையான தமிழ் / வரலாற்று பெயர், குடும்ப பின்னணி, சவால்.
ஒரு சாதாரண மனிதன் கண்ணோட்டத்தில் — viewer அவருடன் identify ஆகவேண்டும்.
[PAUSE_MED] ஒவ்வொரு 2-3 வாக்கியங்களுக்கும்.

பிரிவு 3 — திருப்புமுனை / உண்மை வெளிப்பாடு (The Turn):
"இதை எத்தனை பேருக்கு தெரியும்?" என்று ஒரு இடத்தில் மட்டும்.
உண்மையான தேதிகள், போர்கள், கோட்டை பெயர்கள், key decisions சேர்க்கவும்.
அந்த தருணத்தில் அவர் என்ன சிந்தித்திருப்பார் என்று emotional depth தரவும்.
[PAUSE_SHORT] fact-களுக்கு பிறகு. [PAUSE_LONG] section முடியும்போது.

பிரிவு 4 — உணர்ச்சி உச்சம் / Legacy (Climax):
இழப்பு அல்லது வெற்றி — மிகவும் powerful moment.
இந்த நிகழ்வு இன்றைக்கும் நமது வாழ்க்கையை எப்படி தாக்குகிறது?
[BREATH] உணர்ச்சி மாறும் இடங்களில். [PAUSE_MED] emotional beat-களுக்கு பிறகு.

பிரிவு 5 — வாழ்க்கை படிப்பினைகள் (Life Lessons — MOST IMPORTANT SECTION):
இந்த வரலாற்று நிகழ்வில் இருந்து 3 குறிப்பிட்ட, actionable படிப்பினைகள்:

படிப்பினை 1: [தலைப்பு — உதாரணம்: "தோல்வியை ஏற்றுக்கொள்ளும் தைரியம்"]
இன்றைய வாழ்க்கையில் இது எப்படி apply ஆகும்? ஒரு modern example கொடுக்கவும்.
[PAUSE_SHORT]

படிப்பினை 2: [தலைப்பு — உதாரணம்: "நோக்கம் தெளிவாக இருந்தால் வழி தெரியும்"]
Student-க்கும் entrepreneur-க்கும் professional-க்கும் இது எப்படி பொருந்தும்?
[PAUSE_SHORT]

படிப்பினை 3: [தலைப்பு — உதாரணம்: "ஒற்றுமையின் சக்தி"]
இன்றைய சவால்களை எதிர்கொள்ள இந்த பாடம் எப்படி உதவும்?
[PAUSE_MED]

பிரிவு 6 — CLOSING + VIRAL CTA:
"நண்பர்களே, {topic}-இன் கதை நமக்கு ஒரு விஷயத்தை சொல்கிறது..." என்று தொடங்கவும்.
சிந்திக்க வைக்கும் இறுதி கேள்வி: "உங்கள் வாழ்க்கையில் எந்த சவாலை இந்த பாடம் எதிர்கொள்ள உதவும்?"
[PAUSE_LONG]
VIRAL TRIGGER: "இந்த கதையில் உங்களுக்கு மிகவும் பிடித்த படிப்பினை எது? கீழே comment பண்ணுங்கள் 👇"
WhatsApp share angle: "இந்த video-ஐ உங்கள் நண்பர்களுடன் பகிருங்கள் — ஒருவேளை இது அவர்களுக்கு தேவையான motivation-ஆக இருக்கலாம்."
கடைசி வரி: "வரலாறு விழிப்பு சேனலை subscribe பண்ணி மணி அடிக்கவும் 🔔 — தினமும் ஒரு வரலாற்று படிப்பினை."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ HARD RULES:
1. தமிழ் மட்டும் (proper nouns, dates, English terms மட்டும் OK)
2. Headers, bullets, numbers, markdown — கூடாது. தொடர் பேச்சு மட்டும்.
3. [PAUSE_LONG] min 4 | [PAUSE_MED] min 8 | [PAUSE_SHORT] min 8 | [BREATH] min 5
4. உண்மையான வரலாற்று தகவல்கள் மட்டும் — தேதிகள், பெயர்கள், இடங்கள் accurate-ஆக இருக்கவேண்டும்
5. Life lessons பிரிவு: abstract இல்லாமல் — concrete, actionable, modern life-க்கு relevant
6. Tone: educational + inspiring + emotional — ஒரே நேரத்தில் மூன்றும்

இப்போது பிரிவு 1 முதல் எழுத தொடங்குங்கள்:
"""

METADATA_PROMPT = """Tamil history + motivation YouTube video-க்கு monetisation-ready metadata தரவும்.
தலைப்பு: {topic}
Script preview: {preview}

TITLE RULES — இந்த formats-ல் ஒன்று:
- Emotion: "X-ன் தியாகம் — இன்றும் கண்ணீர் வருகிறது"
- Curiosity: "X செய்த ஒரு தவறு — வரலாறு மாறிப்போனது"
- Lesson: "X-இடம் இருந்து கற்றுக்கொள்ள வேண்டிய 3 பாடங்கள்"
- Suspense: "X-ன் இரகசியம் — 300 ஆண்டுகளாக யாருக்கும் தெரியாது"

TAG STRATEGY — 3 tiers:
Tier 1 (high volume): Tamil history, வரலாறு, தமிழ் வரலாறு, motivation Tamil, Tamil inspiration
Tier 2 (lesson-based): தலைமை பண்பு, வெற்றி ரகசியம், வரலாற்று படிப்பினை, courage Tamil, perseverance Tamil
Tier 3 (specific): topic-specific names, places, events

JSON மட்டும் (markdown வேண்டாம்):
{{"titles":["emotion title <65 chars","curiosity title <65 chars","lesson title <65 chars"],
"description":"400-500 word Tamil YT description. Line 1-2: emotional hook matching video opening. Line 3: 'இந்த video-ல் நீங்கள் கற்றுக்கொள்வது:'. Then 3 specific lessons from the story. Then timestamps. Then: 'இந்த கதை உங்களுக்கு உதவியதா? Comment பண்ணுங்கள் 👇'. Subscribe CTA. Hashtags at end.",
"tags":["30 tags — Tamil+English mix, include: வரலாறு விழிப்பு, Tamil history, motivation Tamil, தலைமை, வெற்றி, தைரியம், perseverance, leadership, success lessons Tamil, historical facts Tamil"],
"thumbnail_text":["4-5 Tamil words — emotional/powerful, no full sentences"],
"thumbnail_text_b":["alternative 4-5 words — curiosity angle"],
"pinned_comment":"Two-choice question from the lessons. Example: 'இந்த கதையில் உங்களை அதிகம் தொட்டது — X-ன் தைரியமா, இல்லை Y-ன் தியாகமா? 👇'",
"community_post":"Short promo with the most surprising fact from the story + CTA. Under 200 chars."}}"""

# ─────────────────────────────────────────────────────────────────
# SCRIPT
# ─────────────────────────────────────────────────────────────────
def generate_script(topic_info: Dict, llm_preferred: Optional[str] = None) -> str:
    slug  = hashlib.md5(topic_info["topic"].encode()).hexdigest()[:8]
    cache = CACHE / f"script_{slug}.txt"
    if cache.exists():
        log.info("Script cache hit")
        return cache.read_text("utf-8")
    log.info(f"Generating script: {topic_info['topic']}")
    script = generate_text(SCRIPT_PROMPT.format(**topic_info), preferred=llm_preferred)
    cache.write_text(script, "utf-8")
    return script

# ─────────────────────────────────────────────────────────────────
# METADATA
# ─────────────────────────────────────────────────────────────────
def generate_metadata(topic: str, script: str, llm_preferred: Optional[str] = None) -> Dict:
    slug  = hashlib.md5(topic.encode()).hexdigest()[:8]
    cache = CACHE / f"meta_{slug}.json"
    if cache.exists():
        return json.loads(cache.read_text("utf-8"))
    log.info("Generating metadata…")
    raw = generate_text(METADATA_PROMPT.format(topic=topic, preview=script[:600]), max_tokens=2048, preferred=llm_preferred)
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        meta = json.loads(raw)
    except Exception:
        meta = {"titles":[topic],"description":script[:400],"tags":["Tamil history","வரலாறு"],
                "thumbnail_text":[topic[:30]],"pinned_comment":"உங்கள் கருத்து 👇",
                "community_post":f"புதிய video: {topic}"}
    cache.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    return meta

# ─────────────────────────────────────────────────────────────────
# TTS — human-voice pipeline
# ─────────────────────────────────────────────────────────────────
def _build_ssml(script: str, profile: Dict) -> str:
    """Convert pause markers → SSML breaks for natural human-like delivery."""
    text = script
    for marker, ms in PAUSE_MAP.items():
        text = text.replace(marker, f'<break time="{ms}ms"/>')

    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="ta-IN">\n'
        f'<voice name="{profile["voice"]}">\n'
        f'<prosody rate="{profile["rate"]}" pitch="{profile["pitch"]}" volume="{profile["volume"]}">\n'
        f'{text}\n'
        '</prosody></voice></speak>'
    )

async def _tts_ssml(ssml: str, out: Path, voice: str, rate: str, pitch: str):
    import edge_tts
    c = edge_tts.Communicate(ssml, voice, rate=rate, pitch=pitch)
    await c.save(str(out))

def synthesise_voice(script: str, slug: str, voice_key: str = DEFAULT_VOICE) -> Path:
    profile   = VOICE_PROFILES[voice_key]
    raw_mp3   = AUDIO / f"{slug}_raw.mp3"
    final_mp3 = AUDIO / f"{slug}_narration.mp3"
    ssml_file = AUDIO / f"{slug}.ssml"

    if final_mp3.exists():
        log.info("Voice cache hit")
        return final_mp3

    # Rewrite script for natural spoken Tamil before TTS
    from llm_client import generate_text as _llm
    SSML_REWRITE_TA = """You are a world-class Tamil speech writer specializing in Microsoft Azure Neural TTS.
Rewrite the following Tamil text into highly natural, human-like spoken Tamil.

Requirements:
- Preserve meaning exactly — do not add or remove information
- Use natural, grammatically correct spoken Tamil
- Break long sentences into shorter natural speech units
- Improve flow for realistic Tamil storytelling cadence
- Make speech sound warm, emotional, and engaging
- Avoid machine-like or literal wording
- Return ONLY the rewritten plain text — no SSML, no markdown, no explanation

Input Text:
{text}"""
    try:
        rewritten = _llm(SSML_REWRITE_TA.format(text=script[:4000]), max_tokens=6000)
        if rewritten and len(rewritten.strip()) > 200:
            # Re-add pause markers that LLM may have removed
            import re as _re
            if "[PAUSE" not in rewritten:
                rewritten = _re.sub(r'([.!?])\s+', r' [PAUSE_SHORT] ', rewritten)
                rewritten = _re.sub(r'([.!?])\s+([A-Zஆஈஊஏஐஒஓ])', r' [PAUSE_MED] ', rewritten)
            script = rewritten.strip()
            log.info(f"Script rewritten for natural Tamil cadence: {len(script)} chars")
    except Exception as _e:
        log.warning(f"LLM rewrite failed ({_e}) — using original script")

    # Build SSML
    ssml = _build_ssml(script, profile)
    ssml_file.write_text(ssml, "utf-8")

    log.info(f"TTS: {profile['voice']} ({profile['desc']})")
    try:
        asyncio.run(_tts_ssml(ssml, raw_mp3, profile["voice"], profile["rate"], profile["pitch"]))
    except Exception as e:
        log.warning(f"SSML TTS failed ({e}), plain text fallback…")
        plain = re.sub(r"<[^>]+>", " ", ssml)
        plain = re.sub(r"\s+", " ", plain).strip()
        async def _plain():
            import edge_tts
            c = edge_tts.Communicate(plain, profile["voice"], rate=profile["rate"], pitch=profile["pitch"])
            await c.save(str(raw_mp3))
        asyncio.run(_plain())

    # ── Broadcast EQ chain ────────────────────────────────────────
    # Goal: warm newsreader → emotional storyteller
    # highpass      : kill rumble below 80 Hz
    # 300 Hz boost  : chest warmth
    # 1 kHz boost   : presence / intelligibility
    # 3 kHz boost   : consonant clarity (key for Tamil letters)
    # 7 kHz cut     : de-harsh sibilants (ஸ, ஷ)
    # compressor    : even dynamics, no loud/quiet swings
    # loudnorm      : YouTube -14 LUFS target
    eq = (
        "highpass=f=80,"
        "equalizer=f=200:t=q:w=0.9:g=+1.5,"   # body warmth
        "equalizer=f=800:t=q:w=0.8:g=+2.0,"   # presence
        "equalizer=f=3000:t=q:w=0.8:g=+2.5,"  # Tamil consonant clarity
        "equalizer=f=6000:t=q:w=1.0:g=-2.0,"  # de-harsh sibilants
        "equalizer=f=10000:t=q:w=1.2:g=-1.5," # cut digital edge
        "aecho=0.75:0.62:26:0.05,"             # small room — natural storytelling space
        "acompressor=threshold=-20dB:ratio=1.7:attack=10:release=250:makeup=2.5,"
        "atempo=0.98,"                           # 2% slow — removes TTS rush
        "loudnorm=I=-14:TP=-1.5:LRA=11"        # LRA=11 preserves emotional dynamics
    )
    subprocess.run(
        ["ffmpeg","-y","-i",str(raw_mp3),"-af",eq,"-ar","48000","-b:a","192k",str(final_mp3)],
        capture_output=True, check=True
    )
    raw_mp3.unlink(missing_ok=True)
    log.info(f"Voice ready: {final_mp3}")
    return final_mp3

# ─────────────────────────────────────────────────────────────────
# THUMBNAIL
# ─────────────────────────────────────────────────────────────────
def create_thumbnail(topic: str, thumb_text: str, slug: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    out = THUMBS / f"{slug}.jpg"
    if out.exists():
        return out

    W, H = 1280, 720
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Deep maroon → dark indigo gradient (Tamil temple night sky)
    for y in range(H):
        t = y / H
        r = int(80  + t * 30)
        g = int(5   + t * 15)
        b = int(30  + t * 50)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    gold = (210, 170, 50)
    # Double border
    for i in range(3):
        draw.rectangle([12+i*4, 12+i*4, W-12-i*4, H-12-i*4], outline=gold)

    # Corner ornaments
    for cx, cy in [(55,55),(W-55,55),(55,H-55),(W-55,H-55)]:
        draw.ellipse([cx-22,cy-22,cx+22,cy+22], fill=gold)
        draw.ellipse([cx-14,cy-14,cx+14,cy+14], fill=(30,10,40))
        draw.ellipse([cx-6, cy-6, cx+6, cy+6],  fill=gold)

    fl  = _font(64)
    fm  = _font(38)
    fs  = _font(26)

    # Channel name top
    _text_c(draw, "வரலாறு விழிப்பு", W//2, 72, fs, (220,185,70))
    draw.line([(110,108),(W-110,108)], fill=gold, width=2)

    # Main text
    lines = _wrap(thumb_text, 16)
    y0 = 230 - (len(lines)-1)*40
    for line in lines:
        # shadow
        _text_c(draw, line, W//2+3, y0+3, fl, (20,5,20))
        _text_c(draw, line, W//2,   y0,   fl, (255,248,220))
        y0 += 90

    # Bottom bar
    draw.rectangle([0, H-85, W, H], fill=(15,5,25))
    draw.line([(0, H-85),(W, H-85)], fill=gold, width=1)
    label = topic[:50] + ("…" if len(topic) > 50 else "")
    _text_c(draw, "📜 " + label, W//2, H-52, fs, (185,150,45))

    img.save(str(out), "JPEG", quality=95)
    log.info(f"Thumbnail: {out}")
    return out

def _font(size):
    from PIL import ImageFont
    for p in [
        "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansTamil-Regular.otf",
    ]:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except: pass
    from PIL import ImageFont
    return ImageFont.load_default()

def _text_c(draw, text, x, y, font, color):
    try:
        b = draw.textbbox((0,0), text, font=font)
        draw.text((x-(b[2]-b[0])//2, y), text, font=font, fill=color)
    except:
        draw.text((x, y), text, font=font, fill=color)

def _wrap(text, max_c=16):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur)+len(w)+1 <= max_c: cur = (cur+" "+w).strip()
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines[:3]

# ─────────────────────────────────────────────────────────────────
# VIDEO ASSEMBLY — narration + BGM mixed
# ─────────────────────────────────────────────────────────────────
def _build_concat_list(clips: List[Path], target_duration: float) -> Path:
    """Build ffmpeg concat demuxer list, repeating clips to fill target duration."""
    concat_file = CACHE / f"concat_{hashlib.md5(str(clips).encode()).hexdigest()[:8]}.txt"
    entries = []
    total = 0.0
    idx = 0
    while total < target_duration and clips:
        clip = clips[idx % len(clips)]
        clip_dur = _duration(clip)
        entries.append(f"file '{clip.resolve()}'")
        total += clip_dur
        idx += 1
    concat_file.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return concat_file


def _assemble_static_video(thumb: Path, narration: Path, bgm: Path, slug: str, title: str, out: Path) -> Path:
    dur = _duration(narration)
    fade_start = max(0, dur - 4)
    # Input indices: 0=thumbnail(video), 1=narration(audio), 2=bgm(audio)
    filter_cx = (
        f"[2:a]volume=0.10,"
        f"afade=t=out:st={fade_start:.1f}:d=4[bgm];"
        "[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    safe_title = re.sub(r"[:'\\]", "", title)[:55]
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(thumb),
        "-i", str(narration),
        "-i", str(bgm),
        "-filter_complex", filter_cx,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest",
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
            f"drawtext=text='{safe_title}':"
            "fontsize=34:fontcolor=white@0.9:"
            "x=(w-text_w)/2:y=h-55:"
            "box=1:boxcolor=black@0.55:boxborderw=12"
        ),
        str(out),
    ]
    encode_timeout = max(300, int(dur * 2.5))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=encode_timeout)
    if result.returncode != 0:
        log.error(f"FFmpeg error: {result.stderr[-400:]}")
        raise RuntimeError("Video assembly failed")
    return out


def _assemble_pexels_video(clips: List[Path], narration: Path, bgm: Path, slug: str, title: str, out: Path) -> Path:
    dur = _duration(narration)
    concat_list = _build_concat_list(clips, dur)
    safe_title = re.sub(r"[:'\\]", "", title)[:55]
    filter_cx = (
        f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        f"trim=duration={dur},setpts=PTS-STARTPTS,"
        f"drawtext=text='{safe_title}':fontsize=34:fontcolor=white@0.9:"
        f"x=(w-text_w)/2:y=h-55:box=1:boxcolor=black@0.55:boxborderw=12[vout];"
        "[1:a]volume=1.0[narr];[2:a]volume=0.10[bgm];[narr][bgm]amix=inputs=2:duration=first[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-i", str(narration),
        "-i", str(bgm),
        "-filter_complex", filter_cx,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(dur),
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        log.warning(f"Pexels assembly failed: {result.stderr[-300:]}")
        raise RuntimeError("Pexels video assembly failed")
    return out


def assemble_video(thumb: Path, narration: Path, bgm: Path, slug: str, title: str, stock_clips: Optional[List[Path]] = None) -> Path:
    out = VIDEOS / f"{slug}.mp4"
    if out.exists():
        log.info("Video cache hit")
        return out

    if stock_clips:
        log.info(f"Assembling video with {len(stock_clips)} Pexels clips…")
        try:
            _assemble_pexels_video(stock_clips, narration, bgm, slug, title, out)
            log.info(f"Video ready: {out}")
            return out
        except Exception as exc:
            log.warning(f"Pexels assembly error: {exc}")

    log.info("Assembling video (static thumbnail + narration + BGM)…")
    _assemble_static_video(thumb, narration, bgm, slug, title, out)
    log.info(f"Video ready: {out}")
    return out

def _duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1",str(path)],
            capture_output=True, text=True, check=True
        )
        return float(r.stdout.strip())
    except:
        return 300.0

# ─────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────
def run_pipeline(
    topic_info: Dict,
    voice_key: str = DEFAULT_VOICE,
    skip_video: bool = False,
    skip_upload: bool = False,
    llm_preferred: Optional[str] = None,
) -> Dict:
    topic = topic_info["topic"]
    topic_source = topic_info.get("source", "unknown")
    slug  = hashlib.md5(topic.encode()).hexdigest()[:10]
    log.info(f"\n{'='*60}\n▶ Pipeline: {topic}\n▶ Source: {topic_source}\n{'='*60}")

    # 1 Script
    script = generate_script(topic_info, llm_preferred=llm_preferred)
    words  = len(script.split())
    log.info(f"Script: {words} words")

    # 2 Metadata
    meta        = generate_metadata(topic, script, llm_preferred=llm_preferred)
    best_title  = meta.get("titles", [topic])[0]
    thumb_text  = meta.get("thumbnail_text", [topic[:20]])[0]

    # 3 BGM (generate once, reuse always)
    bgm = ensure_bgm(duration_s=660)

    # 4 Voice
    narration = synthesise_voice(script, slug, voice_key)

    # 5 Thumbnail
    thumb = create_thumbnail(topic, thumb_text, slug)

    # 6 Stock footage
    stock_clips = fetch_stock_clips(topic_info)

    # 7 Video
    if not skip_video:
        video = assemble_video(thumb, narration, bgm, slug, best_title, stock_clips=stock_clips or None)
    else:
        video = VIDEOS / f"{slug}_placeholder.mp4"
        log.info("Skipped video render (--skip-video flag)")

    # 8 YouTube upload
    youtube_result = None
    if not skip_upload and not skip_video:
        try:
            youtube_result = upload_video(video, thumb, meta, topic, slug)
            log.info(f"Published: {youtube_result['youtube_url']}")
        except Exception as exc:
            log.error(f"YouTube upload failed: {exc}")

    # 9 Save package
    pkg = {
        "topic": topic, "slug": slug, "topic_source": topic_source,
        "script_file": str(SCRIPTS/f"{slug}_script.txt"),
        "narration": str(narration), "video": str(video), "thumbnail": str(thumb),
        "metadata": meta, "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "youtube_url": youtube_result.get("youtube_url") if youtube_result else None,
        "youtube_video_id": youtube_result.get("video_id") if youtube_result else None,
    }
    (SCRIPTS/f"{slug}_script.txt").write_text(script, "utf-8")
    (BASE/f"{slug}_package.json").write_text(json.dumps(pkg,ensure_ascii=False,indent=2),"utf-8")

    _print_upload_guide(meta, pkg)
    return pkg

def _print_upload_guide(meta, pkg):
    print("\n" + "═"*60)
    print("📤  YOUTUBE UPLOAD GUIDE")
    print("═"*60)
    print(f"🎬 VIDEO      : {pkg['video']}")
    if pkg.get("youtube_url"):
        print(f"📺 YOUTUBE    : {pkg['youtube_url']}")
    print(f"🖼  THUMBNAIL  : {pkg['thumbnail']}")
    print(f"\n📌 TITLES:")
    for i,t in enumerate(meta.get("titles",[]),1): print(f"   {i}. {t}")
    print(f"\n🏷  TAGS: {', '.join(meta.get('tags',[])[:8])}…")
    print(f"\n📌 PINNED COMMENT:\n   {meta.get('pinned_comment','')}")
    print(f"\n📣 COMMUNITY POST:\n   {meta.get('community_post','')}")
    print("\n" + "═"*60)

# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    from scheduler import get_todays_topic, get_discovered_topic, get_static_topic, find_optimal_schedule, FULL_TOPIC_BANK

    parser = argparse.ArgumentParser(description="Tamil History YouTube Bot v2")
    parser.add_argument("--topic",      type=int,  default=None,          help="Topic index from bank (overrides discovery)")
    parser.add_argument("--static",     action="store_true",              help="Use hardcoded 30-topic bank instead of trending discovery")
    parser.add_argument("--voice",      type=str,  default=DEFAULT_VOICE, help="male_warm / female_emotional")
    parser.add_argument("--skip-video", action="store_true",              help="Script + audio only, skip FFmpeg render")
    parser.add_argument("--skip-upload", action="store_true",             help="Generate video but skip YouTube upload")
    parser.add_argument("--llm",        type=str,  default=None,          help="Preferred LLM: gemini / github / groq")
    parser.add_argument("--gen-bgm",    action="store_true",              help="Regenerate BGM and exit")
    parser.add_argument("--schedule",   action="store_true",              help="Show optimal schedule and exit")
    parser.add_argument("--list",       action="store_true",              help="List all topics")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable Topics:")
        for i,t in enumerate(FULL_TOPIC_BANK):
            print(f"  [{i:2d}] {t['topic']}  ({t['era']})")
        sys.exit(0)

    if args.schedule:
        from scheduler import print_schedule_report
        print_schedule_report(find_optimal_schedule())
        sys.exit(0)

    if args.gen_bgm:
        BGM_FILE.unlink(missing_ok=True)
        ensure_bgm()
        sys.exit(0)

    # Pick topic
    if args.topic is not None:
        topic_info = FULL_TOPIC_BANK[args.topic % len(FULL_TOPIC_BANK)]
        topic_info = topic_info.copy()
        topic_info["source"] = "manual_bank"
        log.info(f"Manual topic selected: {topic_info['topic']}")
    elif args.static:
        topic_info = get_static_topic()
        log.info(f"Static bank topic: {topic_info['topic']}")
    else:
        topic_info = get_discovered_topic()
        log.info(f"Discovered trending topic: {topic_info['topic']} (source: {topic_info.get('source')})")

    run_pipeline(topic_info, voice_key=args.voice, skip_video=args.skip_video,
                 skip_upload=args.skip_upload, llm_preferred=args.llm)
