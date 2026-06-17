#!/usr/bin/env python3
"""
துளிர் Enterprise Bot — Almost Everything style whiteboard animation.
Free stack: Gemini/Groq LLM · edge-tts · cairosvg · Pillow · FFmpeg
"""
import os, sys, re, json, time, hashlib, asyncio, subprocess, random, logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S", handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ── Dirs ─────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent
THULIR_DIR  = BASE / "thulir_enterprise"
SCRIPTS_DIR = THULIR_DIR / "scripts"
AUDIO_DIR   = THULIR_DIR / "audio"
VIDEO_DIR   = THULIR_DIR / "videos"
THUMB_DIR   = THULIR_DIR / "thumbnails"
CACHE_DIR   = THULIR_DIR / "cache"
BGM_DIR     = THULIR_DIR / "bgm"
FRAME_DIR   = THULIR_DIR / "frames"
for d in [SCRIPTS_DIR,AUDIO_DIR,VIDEO_DIR,THUMB_DIR,CACHE_DIR,BGM_DIR,FRAME_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Scene config (8 scenes) ──────────────────────────────────────────
SCENE_CONFIG = [
    ("Hook",       "🎯", (212, 45,  32),  "question_mark"),
    ("பிரச்சனை",  "😟", (180, 70,  40),  "anxious_face"),
    ("ஏன்?",      "💡", (200,140,  20),  "lightbulb"),
    ("படி 1",     "✅", ( 34,139,  34),  "checkmark"),
    ("படி 2",     "✅", ( 34,139,  34),  "ladder"),
    ("படி 3",     "🌟", ( 45,106,  79),  "arrow_up"),
    ("கதை",       "📖", ( 45,106,  79),  "person"),
    ("முடிவு",    "💚", ( 45,106,  79),  "subscribe"),
]

# ── LLM (same llm_client.py as history bot) ──────────────────────────
def _llm(prompt: str, max_tokens: int = 3000) -> str:
    from llm_client import generate_text
    return generate_text(prompt, max_tokens=max_tokens)

# ── Topic bank ───────────────────────────────────────────────────────
TOPIC_BANK = [
    {"topic":"No சொல்ல தெரியாதவர்களுக்கு",    "hook":"ஒரே வார்த்தை வாழ்க்கையை மாற்றும்",  "icon":"no_sign"},
    {"topic":"First Salary Guide",             "hook":"முதல் சம்பளத்தில் 90% பேர் செய்யும் தவறு","icon":"rupee"},
    {"topic":"தினமும் படிக்கும் பழக்கம்",       "hook":"20 நிமிடம் ஒரு நாளில் போதும்",        "icon":"brain"},
    {"topic":"Toxic நண்பர்கள்",                "hook":"இந்த 5 signs இருந்தால் கவலைப்படு",     "icon":"two_people"},
    {"topic":"Anxiety handle பண்றது",          "hook":"மனசு ஓயாம ஓடுதா?",                   "icon":"anxious_face"},
    {"topic":"Time management",                "hook":"24 மணி நேரம் — சரியா use பண்றாயா?",    "icon":"clock"},
    {"topic":"Comparison trap",                "hook":"அவங்க வாழ்க்கை பார்த்து ஏன் வலிக்குது?","icon":"balance_scale"},
    {"topic":"SIP investment guide",           "hook":"₹500-ல் investment ஆரம்பிக்கலாம்",     "icon":"coins_stack"},
    {"topic":"Parents-கிட்ட Career பேசுவது",   "hook":"இந்த conversation வாழ்க்கை மாற்றும்",   "icon":"family"},
    {"topic":"Self awareness",                 "hook":"உன்னை பத்தி உனக்கே தெரியுமா?",         "icon":"brain"},
]

STATE_FILE = THULIR_DIR / "state.json"

def pick_topic() -> Dict:
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"used":[]}
    used  = state["used"][-15:]
    available = [t for t in TOPIC_BANK if t["topic"] not in used]
    if not available: available = TOPIC_BANK
    t = random.choice(available)
    state["used"] = (used + [t["topic"]])[-20:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return t

# ── Script generation ────────────────────────────────────────────────
SCRIPT_PROMPT = """நீங்கள் "துளிர்" YouTube சேனலுக்கு whiteboard animation script எழுதுகிறீர்கள்.
Almost Everything channel style — spoken Tamil, conversational, warm big-sibling tone.

Topic: {topic}
Hook: {hook}

EXACTLY 8 sections separated by [SCENE_END]:

Section 1 — HOOK: Start mid-situation. Shocking fact or direct question. No greetings. 3-4 sentences.
Section 2 — PROBLEM: Why this happens. One relatable example with Tamil name. 3-4 sentences.
Section 3 — WHY IT MATTERS: Consequences if not fixed. Be direct. 3-4 sentences.
Section 4 — SOLUTION 1: First actionable step. Simple, specific. 3-4 sentences.
Section 5 — SOLUTION 2: Second step. Real example. 3-4 sentences.
Section 6 — SOLUTION 3: Most important step. 3-4 sentences.
Section 7 — REAL STORY: Tamil person's story. Before→After clearly. 4-5 sentences.
Section 8 — CLOSING + CTA: Powerful closing. "comment பண்ணு 👇". "subscribe பண்ணு 🔔". 3-4 sentences.

RULES: Tamil only. No headers, bullets, markdown. Each section 3-5 sentences max. [SCENE_END] as separator.

Write section 1 first:"""

def generate_script(topic_info: Dict) -> List[str]:
    slug  = hashlib.md5(topic_info["topic"].encode()).hexdigest()[:8]
    cache = CACHE_DIR / f"script_{slug}.json"
    if cache.exists():
        log.info("Script cache hit")
        return json.loads(cache.read_text())

    log.info(f"Generating script: {topic_info['topic']}")
    raw = _llm(SCRIPT_PROMPT.format(**topic_info), max_tokens=3000)

    # Parse scenes
    scenes = [s.strip() for s in raw.split("[SCENE_END]") if s.strip() and len(s.strip()) > 20]
    scenes = [re.sub(r'\[PAUSE_\w+\]|^\s*Section\s*\d[^:]*:\s*', '', s, flags=re.MULTILINE).strip() for s in scenes]
    scenes = [s for s in scenes if len(s) > 20]

    if len(scenes) < 4:
        log.warning(f"Only {len(scenes)} scenes — paragraph split fallback")
        scenes = [p.strip() for p in raw.split("\n\n") if len(p.strip()) > 30][:8]

    if len(scenes) < 4:
        log.warning("Retry with simpler prompt")
        retry = (
            f"Write 8 short Tamil paragraphs about: {topic_info['topic']}\n"
            "Separate each with [SCENE_END]\n"
            "Each paragraph: 3-4 conversational Tamil sentences.\n"
            "Paragraph topics: Hook / Problem / Why / Step1 / Step2 / Step3 / Story / Conclusion\n"
        )
        raw2 = _llm(retry, max_tokens=2500)
        scenes2 = [s.strip() for s in raw2.split("[SCENE_END]") if len(s.strip()) > 20]
        if len(scenes2) >= 4:
            scenes = scenes2

    log.info(f"Script: {len(scenes)} scenes, {sum(len(s.split()) for s in scenes)} words")
    cache.write_text(json.dumps(scenes, ensure_ascii=False, indent=2))
    return scenes

# ── TTS + word timings ────────────────────────────────────────────────
VOICE = "ta-IN-PallaviNeural"
RATE  = "-10%"
PITCH = "+2Hz"

async def _tts_stream(text: str, out_mp3: Path) -> List[dict]:
    import edge_tts
    timings = []
    c = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary")
    with open(out_mp3, "wb") as f:
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 10_000_000
                d = chunk["duration"] / 10_000_000
                timings.append({"word": chunk["text"], "start": s, "end": s+d})
    return timings

def synthesise_audio(scene_text: str, idx: int, slug: str) -> Tuple[Path, float, List[dict]]:
    raw  = AUDIO_DIR / f"{slug}_{idx:02d}_raw.mp3"
    eq   = AUDIO_DIR / f"{slug}_{idx:02d}.mp3"
    tcache = CACHE_DIR / f"timing_{slug}_{idx:02d}.json"

    if eq.exists() and tcache.exists() and eq.stat().st_size > 500:
        dur = _dur(eq)
        return eq, dur, json.loads(tcache.read_text())

    clean = re.sub(r'[*_#>`\[\]]', '', scene_text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    # Add natural prosody pauses before TTS
    from whiteboard_engine import markers_to_silence
    clean = markers_to_silence(clean)

    try:
        timings = asyncio.run(_tts_stream(clean, raw))
        log.info(f"  TTS scene {idx}: {len(timings)} words")
    except Exception as e:
        log.warning(f"  TTS failed ({e}) — silence fallback")
        words = clean.split()
        dur_each = max(0.5, 10.0 / max(len(words),1))
        timings = [{"word":w,"start":i*dur_each,"end":(i+1)*dur_each} for i,w in enumerate(words)]
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                        f"anullsrc=r=44100:cl=mono","-t",
                        str(len(words)*dur_each), str(raw)], capture_output=True)

    # EQ
    eq_chain = (
        "highpass=f=80,equalizer=f=200:t=q:w=0.9:g=1.5,"
        "equalizer=f=800:t=q:w=0.8:g=2,equalizer=f=3000:t=q:w=0.8:g=2.5,"
        "equalizer=f=6000:t=q:w=1:g=-2,aecho=0.75:0.62:26:0.05,"
        "acompressor=threshold=-20dB:ratio=1.7:attack=10:release=250:makeup=2.5,"
        "atempo=0.98,loudnorm=I=-14:TP=-1.5:LRA=11"
    )
    subprocess.run(["ffmpeg","-y","-i",str(raw),"-af",eq_chain,
                    "-ar","48000","-b:a","192k",str(eq)], capture_output=True)
    if not eq.exists(): import shutil; shutil.copy(raw, eq)
    tcache.write_text(json.dumps(timings, ensure_ascii=False))
    return eq, _dur(eq), timings

def _dur(p: Path) -> float:
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                            "-of","default=noprint_wrappers=1:nokey=1",str(p)],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except: return 10.0

# ── BGM ───────────────────────────────────────────────────────────────
def ensure_bgm(dur: int = 660) -> Path:
    bgm = BGM_DIR / "thulir_bgm.mp3"
    if bgm.exists() and bgm.stat().st_size > 50_000: return bgm
    log.info("Generating BGM...")
    fc = (
        "[0]volume=0.10,aecho=0.7:0.65:90:0.30[s1];"
        "[1]volume=0.07,aecho=0.6:0.55:140:0.20[s2];"
        "[2]volume=0.06[s3];"
        "[s1][s2][s3]amix=inputs=3:duration=longest[mix];"
        "[mix]equalizer=f=200:t=q:w=1:g=+4,equalizer=f=4000:t=q:w=1:g=-6,"
        f"afade=t=in:d=4,afade=t=out:st={max(0,dur-6)}:d=6,"
        "loudnorm=I=-24:TP=-3:LRA=8[out]"
    )
    r = subprocess.run([
        "ffmpeg","-y",
        "-f","lavfi","-i",f"sine=frequency=261:duration={dur}",
        "-f","lavfi","-i",f"sine=frequency=329:duration={dur}",
        "-f","lavfi","-i",f"sine=frequency=392:duration={dur}",
        "-filter_complex",fc,"-map","[out]","-ar","44100","-b:a","128k",str(bgm)
    ], capture_output=True)
    if r.returncode != 0:
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"sine=frequency=261:duration={dur}",
                        "-af","volume=0.06,loudnorm=I=-24",str(bgm)], capture_output=True)
    log.info(f"BGM: {bgm.stat().st_size//1024}KB")
    return bgm

# ── Thumbnail ─────────────────────────────────────────────────────────
def make_thumbnail(topic: str, hook: str, slug: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    out = THUMB_DIR / f"{slug}.jpg"
    if out.exists(): return out
    img  = Image.new("RGB", (1280,720), (252,252,248))
    draw = ImageDraw.Draw(img)
    BRAND = (45,106,79); BLACK=(28,28,28); WHITE=(255,255,255)
    GREY=(218,218,212)
    _fn_map = {'black':'Black','bold':'Bold','semi':'SemiBold','regular':'Regular'}
    def f(k,s):
        try: return ImageFont.truetype(f"/usr/share/fonts/truetype/noto/NotoSansTamil-{_fn_map[k]}.ttf",s)
        except: return ImageFont.load_default()
    draw.rectangle([0,0,10,720], fill=BRAND)
    draw.rectangle([0,0,1280,8], fill=BRAND)
    draw.rounded_rectangle([28,24,220,68], radius=8, fill=BRAND)
    draw.text((44,46), "🌱 துளிர்", font=f("bold",28), fill=WHITE, anchor="lm")
    fxl = f("black",88); flg = f("bold",64)
    words = hook.split(); lines=[]; cur=""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textbbox((0,0),t,font=fxl)[2] <= 1200: cur=t
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    y=100
    for i,line in enumerate(lines[:3]):
        fnt=fxl if i==0 else flg; col=BLACK if i==0 else (50,50,50)
        draw.text((32+2,y+2),line,font=fnt,fill=GREY,anchor="lt")
        draw.text((30,y),line,font=fnt,fill=col,anchor="lt")
        y+=draw.textbbox((0,0),line,font=fnt)[3]+12
    draw.rectangle([28,y+18,1250,y+22], fill=BRAND)
    draw.text((30,y+34), topic, font=f("semi",36), fill=BRAND, anchor="lt")
    draw.rectangle([0,660,1280,720], fill=BRAND)
    draw.text((34,690), "Subscribe பண்ணி notification bell அடிக்கவும் 🔔",
              font=f("bold",28), fill=WHITE, anchor="lm")
    img.save(str(out), "JPEG", quality=95)
    return out

# ── Metadata ──────────────────────────────────────────────────────────
META_PROMPT = """துளிர் YouTube channel video metadata தரவும்.
Topic: {topic}  |  Hook: {hook}  |  Preview: {preview}

Return ONLY valid JSON (no markdown):
{{"title":"<Tamil title 65 chars>","description":"<400 word Tamil description — hook 2 lines + 3 takeaways + timestamps + CTA + hashtags>","tags":["வாழ்க்கை திறன்கள்","self improvement Tamil","motivation Tamil","thuliR","life skills Tamil","personal growth Tamil"],"pinned_comment":"<two-choice Tamil question>"}}"""

def generate_metadata(topic_info: Dict, scenes: List[str]) -> Dict:
    slug  = hashlib.md5(topic_info["topic"].encode()).hexdigest()[:8]
    cache = CACHE_DIR / f"meta_{slug}.json"
    if cache.exists(): return json.loads(cache.read_text())
    preview = " ".join(scenes[:2])[:400]
    raw = _llm(META_PROMPT.format(topic=topic_info["topic"],hook=topic_info["hook"],preview=preview), 2000)
    raw = re.sub(r"```json|```","",raw).strip()
    try:
        meta = json.loads(raw)
    except:
        meta = {"title":topic_info["topic"],"description":preview,
                "tags":["துளிர்","Tamil motivation","life skills Tamil"],
                "pinned_comment":"இது உதவியதா? Comment பண்ணுங்கள் 👇"}
    cache.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta

# ── Final assembly ────────────────────────────────────────────────────
def assemble_final(slug: str, scene_videos: List[Path], bgm: Path) -> Path:
    out = VIDEO_DIR / f"{slug}.mp4"
    if out.exists(): return out
    concat = CACHE_DIR / f"concat_{slug}.txt"
    with open(concat,"w") as f:
        for v in scene_videos:
            f.write(f"file '{v.resolve()}'\n")
    raw = CACHE_DIR / f"raw_{slug}.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0",
                    "-i",str(concat),"-c","copy",str(raw)],
                   capture_output=True, check=True)
    total = _dur(raw)
    log.info(f"Total video: {total:.1f}s")
    fc = (
        "[0:a]volume=1.0[v];"
        f"[1:a]volume=0.07,aloop=loop=-1:size=2e+09,atrim=0:{total:.2f}[bgm];"
        "[v][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    r = subprocess.run([
        "ffmpeg","-y","-i",str(raw),"-i",str(bgm),
        "-filter_complex",fc,"-map","0:v","-map","[aout]",
        "-c:v","libx264","-preset","veryfast","-crf","22",
        "-c:a","aac","-b:a","192k","-pix_fmt","yuv420p",str(out)
    ], capture_output=True, text=True, timeout=max(600,int(total*3)))
    raw.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"Final assembly failed: {r.stderr[-300:]}")
    log.info(f"✅ Final: {out} ({out.stat().st_size//1024//1024}MB)")
    return out

# ── Auto icon selection ───────────────────────────────────────────────
def pick_icon(scene_text: str, scene_idx: int, topic_icon: str) -> str:
    from icon_library import pick_icon_for_text, ICONS
    # Try keyword match first
    detected = pick_icon_for_text(scene_text)
    if detected: return detected
    # Scene index defaults
    defaults = ["question_mark","sad_face","lightbulb","checkmark",
                "ladder","arrow_up","person","subscribe"]
    if scene_idx < len(defaults): return defaults[scene_idx]
    return topic_icon if topic_icon in ICONS else "sprout"

# ── Main pipeline ─────────────────────────────────────────────────────
def run(topic_info: Optional[Dict] = None, skip_upload: bool = True) -> Dict:
    from whiteboard_engine import render_scene_video

    if topic_info is None:
        topic_info = pick_topic()

    topic = topic_info["topic"]
    slug  = hashlib.md5(topic.encode()).hexdigest()[:10]
    topic_icon = topic_info.get("icon","sprout")

    log.info(f"\n{'='*60}")
    log.info(f"🌱 THULIR ENTERPRISE")
    log.info(f"   Topic: {topic}")
    log.info(f"   Hook:  {topic_info['hook']}")
    log.info(f"{'='*60}")

    # 1. Script
    log.info("📝 Script...")
    scenes = generate_script(topic_info)
    log.info(f"   {len(scenes)} scenes")

    # 2. Metadata
    log.info("🔍 Metadata...")
    meta  = generate_metadata(topic_info, scenes)
    title = meta.get("title", topic)
    log.info(f"   Title: {title[:60]}")

    # 3. BGM
    bgm = ensure_bgm()

    # 4. Per-scene: TTS + animated whiteboard video
    scene_videos = []
    for i, scene_text in enumerate(scenes):
        cfg   = SCENE_CONFIG[i % len(SCENE_CONFIG)]
        label, emoji, color, _ = cfg
        icon  = pick_icon(scene_text, i, topic_icon)
        log.info(f"\n  Scene {i+1}/{len(scenes)} — {label} [{icon}]")

        # TTS
        audio, dur, timings = synthesise_audio(scene_text, i, slug)

        # Animated video clip
        vid = render_scene_video(
            scene_text   = scene_text,
            scene_idx    = i,
            total_scenes = len(scenes),
            slug         = slug,
            topic        = topic,
            audio_path   = audio,
            word_timings = timings,
            duration     = dur,
            scene_label  = label,
            scene_emoji  = emoji,
            label_color  = color,
            icon_name    = icon,
            out_dir      = FRAME_DIR,
        )
        scene_videos.append(vid)

    # 5. Thumbnail
    log.info("\n🖼️  Thumbnail...")
    thumb = make_thumbnail(topic, topic_info["hook"], slug)

    # 6. Final
    log.info("🎬 Final assembly...")
    video = assemble_final(slug, scene_videos, bgm)

    pkg = {"topic":topic,"slug":slug,"title":title,
           "video":str(video),"thumbnail":str(thumb),
           "metadata":meta,"scenes":len(scenes),
           "generated":time.strftime("%Y-%m-%d %H:%M UTC")}
    (THULIR_DIR/f"{slug}_package.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2))
    (SCRIPTS_DIR/f"{slug}.txt").write_text(
        "\n\n---SCENE---\n\n".join(scenes))

    log.info(f"\n{'='*60}")
    log.info(f"✅ DONE: {video}")
    log.info(f"   Thumbnail: {thumb}")
    log.info(f"{'='*60}")
    return pkg


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--topic-idx",  type=int, default=None)
    p.add_argument("--skip-upload",action="store_true", default=True)
    p.add_argument("--upload",     action="store_true", default=False)
    p.add_argument("--list",       action="store_true")
    args = p.parse_args()

    if args.list:
        for i,t in enumerate(TOPIC_BANK):
            print(f"[{i}] {t['topic']}")
        sys.exit(0)

    ti = None
    if args.topic_idx is not None:
        ti = TOPIC_BANK[args.topic_idx % len(TOPIC_BANK)].copy()

    run(ti, skip_upload=not args.upload)
