#!/usr/bin/env python3
"""
Documentary Main v2 — Full automation pipeline.
- LLM topic discovery (no fixed bank)
- Video (16:9) + Shorts (9:16) rendered separately
- Proper error handling with fallbacks at every step
- Production-grade SEO metadata
- YouTube upload with retry logic
"""
import sys, os, json, time, hashlib, asyncio, subprocess, argparse, re, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import *
from storyboard_generator import build_storyboard
from visual_renderer import render_scene

# ── Dirs ──────────────────────────────────────────────────────────────
for d in [ASSET_DIR, FRAME_DIR, AUDIO_DIR, VIDEO_DIR, CACHE_DIR, SCRIPT_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)

STATE_FILE  = Path(__file__).parent / "documentary_state.json"
LOG_FILE    = Path(__file__).parent / "upload_log.json"

# ── Logging ────────────────────────────────────────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("documentary")

# ── LLM ───────────────────────────────────────────────────────────────
try:
    from llm_client import generate_text as _llm
except ImportError:
    def _llm(prompt, max_tokens=3000):
        raise RuntimeError("llm_client not found")

# ══════════════════════════════════════════════════════════════════════
# STEP 1 — LLM TOPIC DISCOVERY
# ══════════════════════════════════════════════════════════════════════
TOPIC_DISCOVERY_PROMPT = """You are a Tamil YouTube documentary channel strategist for "வரலாறு விழிப்பு" (History Awakening).

Your task: Discover ONE fresh, viral Tamil history topic for today's video.

Previously covered topics (DO NOT repeat):
{used_topics}

Today's date context: {date}

Select a topic that is:
1. A real historical event/person from Indian, Tamil, or world history
2. Has emotional storytelling potential (sacrifice, betrayal, victory, tragedy)
3. Has specific numbers, dates, locations — not vague
4. Appeals to Tamil audience 18-45 years
5. Has good search volume potential in Tamil YouTube
6. NOT in the previously covered list above

Categories to rotate through:
- Tamil history heroes (Chola, Pandya, Pallava era)
- Indian freedom fighters  
- World history turning points
- Ancient civilizations
- Forgotten warriors and queens
- Scientific/cultural discoveries

Return ONLY valid JSON (no markdown, no explanation):
{{
  "topic_ta": "<Tamil topic name — specific person/event/era>",
  "topic_en": "<English equivalent for SEO>",
  "hook": "<One shocking fact or question in Tamil — under 15 words>",
  "era": "<Time period e.g. 1200-1300 CE>",
  "category": "<one of: tamil_history|indian_history|world_history|ancient|modern>",
  "search_intent": "<What Tamil viewers search for related to this topic>",
  "emotional_angle": "<Core emotional hook: sacrifice|betrayal|victory|tragedy|discovery>"
}}"""

FALLBACK_TOPICS = [
    {"topic_ta":"வீர பாண்டிய கட்டபொம்மன் — ஆங்கிலேயரை நடுங்க வைத்த வீரன்",
     "topic_en":"Veerapandiya Kattabomman Tamil Hero",
     "hook":"தூக்கிலிடப்படுவதற்கு முன் அவன் சொன்ன கடைசி வார்த்தைகள் என்ன?",
     "era":"1760-1799 CE","category":"tamil_history","emotional_angle":"sacrifice"},
    {"topic_ta":"ராணி வேலு நாச்சியார் — இந்தியாவின் முதல் ஆங்கிலேய எதிர்ப்பு ராணி",
     "topic_en":"Rani Velu Nachiyar First Queen to Fight British",
     "hook":"கணவன் கொல்லப்பட்டாள், பின் அவள் என்ன செய்தாள்?",
     "era":"1730-1796 CE","category":"tamil_history","emotional_angle":"victory"},
    {"topic_ta":"சந்திரகுப்த மௌரியர் — 16 வயதில் பேரரசை உருவாக்கியவன்",
     "topic_en":"Chandragupta Maurya Founded Empire at 16",
     "hook":"16 வயது சிறுவன் எப்படி இந்தியாவையே ஆண்டான்?",
     "era":"340-298 BCE","category":"indian_history","emotional_angle":"victory"},
    {"topic_ta":"திப்பு சுல்தான் — ஆங்கிலேயரை அதிர்ச்சியில் ஆழ்த்திய கடைசி போர்",
     "topic_en":"Tipu Sultan Last Battle Against British",
     "hook":"இறந்தாலும் சரண் அடைய மறுத்த சுல்தான்",
     "era":"1750-1799 CE","category":"indian_history","emotional_angle":"sacrifice"},
    {"topic_ta":"தமிழ் சோழர்கள் — கடலை ஆண்ட பேரரசு 1000 ஆண்டு கதை",
     "topic_en":"Chola Empire Ruled the Seas 1000 Years",
     "hook":"1000 ஆண்டுகள் கடலை ஆண்ட தமிழர்கள் யார்?",
     "era":"300 BCE - 1279 CE","category":"tamil_history","emotional_angle":"victory"},
]


def load_state() -> dict:
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {"used_topics":[], "total_runs":0, "last_run":None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def discover_topic() -> dict:
    """Use LLM to discover a fresh topic. Falls back to curated list."""
    state = load_state()
    used  = state.get("used_topics", [])[-20:]

    # Check cached today's topic
    today = time.strftime("%Y-%m-%d")
    if state.get("today_topic") and state.get("today_date") == today:
        log.info(f"Using cached today topic: {state['today_topic']['topic_ta'][:50]}")
        return state["today_topic"]

    log.info("🔍 Discovering topic via LLM...")
    used_str = "\n".join(f"- {t}" for t in used) if used else "None yet"

    try:
        raw = _llm(
            TOPIC_DISCOVERY_PROMPT.format(
                used_topics=used_str,
                date=time.strftime("%Y-%m-%d, %A")
            ), max_tokens=500
        )
        raw = re.sub(r"```json|```","",raw).strip()
        m   = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if m: raw = m.group()
        topic = json.loads(raw)

        required = ["topic_ta","topic_en","hook","category","emotional_angle"]
        if not all(k in topic for k in required):
            raise ValueError(f"Missing fields: {[k for k in required if k not in topic]}")

        log.info(f"✅ Topic discovered: {topic['topic_ta'][:60]}")

    except Exception as e:
        log.warning(f"LLM topic discovery failed ({e}) — using fallback")
        available = [t for t in FALLBACK_TOPICS if t["topic_ta"] not in used]
        topic = random.choice(available if available else FALLBACK_TOPICS)
        log.info(f"Fallback topic: {topic['topic_ta'][:60]}")

    # Save state
    used.append(topic["topic_ta"])
    state["used_topics"]  = used[-30:]
    state["today_topic"]  = topic
    state["today_date"]   = today
    state["total_runs"]   = state.get("total_runs", 0) + 1
    state["last_run"]     = time.strftime("%Y-%m-%d %H:%M UTC")
    save_state(state)
    return topic


# ══════════════════════════════════════════════════════════════════════
# STEP 2 — SCRIPT GENERATION
# ══════════════════════════════════════════════════════════════════════
SCRIPT_PROMPT = """நீங்கள் "வரலாறு விழிப்பு" Tamil educational YouTube documentary எழுதுகிறீர்கள்.
Topic: {topic_ta}
Era: {era}
Emotional angle: {emotional_angle}
Hook: {hook}

DOCUMENTARY STRUCTURE — 8 sections, use [SCENE_BREAK] between each:

Section 1 — HOOK (15 seconds):
{hook} — இந்த ஒரு கேள்வியுடன் தொடங்கு. NO greetings.
Shocking specific fact. Viewer must say "என்ன இது?!"

Section 2 — CONTEXT:
காலகட்டம், இடம், சமூக நிலை — specific dates and places.
Who was the protagonist? Their background. Make them human.

Section 3 — RISING ACTION:
சவால் என்ன? எதிரி யார்? Numbers: எத்தனை படை, எவ்வளவு நிலம்?

Section 4 — THE CRISIS:
முக்கியமான தருணம் — specific date, specific decision.
What were the odds? What was at stake?

Section 5 — CLIMAX:
மிக முக்கியமான நிகழ்வு — battle/betrayal/discovery/sacrifice.
Specific numbers, dates, names. Drama peak.

Section 6 — AFTERMATH:
Result. Numbers (casualties, land, duration). Legacy.
How did it change history?

Section 7 — LESSON FOR TODAY:
3 specific actionable lessons. How this applies to modern Tamil youth.
Connect history to 2025 reality.

Section 8 — CTA:
"இந்த கதை உங்களுக்கு என்ன சொல்கிறது?" — emotional closing.
Subscribe CTA. Share angle. Comment trigger question.

RULES:
- Tamil மட்டும் (proper nouns OK)
- Every section: minimum 1 specific date, 1 specific number, 1 specific place
- No vague statements — "பல வீரர்கள்" ❌ → "12,000 வீரர்கள்" ✅
- Maximum 3-4 sentences per section (voice-over timing)
- [SCENE_BREAK] on its own line between sections"""

SHORTS_SCRIPT_PROMPT = """Create a 60-second Tamil YouTube Shorts script based on this topic.
Topic: {topic_ta}
Hook: {hook}

SHORTS FORMAT (60 seconds = ~150 words):

[HOOK - 5 seconds]
Most shocking fact. Start MID-ACTION. No greeting.

[REVEAL - 20 seconds]  
The key story. 2-3 sentences. Specific numbers.

[PEAK - 20 seconds]
The most dramatic moment. What happened?

[LESSON - 10 seconds]
One powerful takeaway sentence.

[CTA - 5 seconds]
"இதை பார்க்க → channel-ஐ follow பண்ணுங்கள்"

RULES: Tamil only. Max 150 words total. Every sentence must create curiosity for the next."""


def generate_script(topic: dict, script_type: str = "long") -> list:
    slug  = hashlib.md5((topic["topic_ta"]+script_type).encode()).hexdigest()[:8]
    cache = Path(CACHE_DIR) / f"script_{slug}.json"
    if cache.exists():
        log.info(f"Script cache hit: {slug}")
        return json.loads(cache.read_text())

    log.info(f"📝 Generating {script_type} script...")
    prompt = (SCRIPT_PROMPT if script_type=="long" else SHORTS_SCRIPT_PROMPT)
    raw    = _llm(prompt.format(**topic), max_tokens=3500 if script_type=="long" else 800)

    separator = "[SCENE_BREAK]" if script_type=="long" else "\n\n"
    sections  = [s.strip() for s in raw.split(separator) if s.strip() and len(s.strip())>20]
    sections  = [re.sub(r'^\s*(Section\s*\d[^:\n]*:?)\s*', '', s, flags=re.MULTILINE).strip()
                 for s in sections]
    sections  = [s for s in sections if len(s.strip())>20]

    if len(sections) < 3:
        log.warning(f"Only {len(sections)} sections — paragraph fallback")
        sections = [p.strip() for p in raw.split("\n\n") if len(p.strip())>30][:8]

    if not sections:
        raise RuntimeError("Script generation returned empty content")

    log.info(f"✅ Script: {len(sections)} sections, {sum(len(s.split()) for s in sections)} words")
    cache.write_text(json.dumps(sections, ensure_ascii=False, indent=2))
    return sections


# ══════════════════════════════════════════════════════════════════════
# STEP 3 — SEO METADATA (production grade)
# ══════════════════════════════════════════════════════════════════════
SEO_PROMPT = """You are a Tamil YouTube SEO expert. Generate production-grade metadata for a history documentary.

Topic (Tamil): {topic_ta}
Topic (English): {topic_en}
Hook: {hook}
Era: {era}
Category: {category}
Search intent: {search_intent}
Script preview (first 300 chars): {preview}

YouTube SEO rules applied:
- Title: curiosity + keyword, under 60 chars
- Description: hook in first 2 lines (shown before "more"), timestamps, keywords, CTA
- Tags: mix of high-volume Tamil + English + long-tail
- Pinned comment: forces engagement

Return ONLY valid JSON:
{{
  "title_ta": "<Tamil title, 55-60 chars, emotional + keyword>",
  "title_ta_alt": ["<alt title 1>", "<alt title 2>"],
  "description": "<Tamil YouTube description, 500 chars. Line 1-2: emotional hook. Line 3: 'இந்த video-ல்:'. Then 3 bullet points with timestamps like 00:00 Hook | 01:30 வரலாறு. Then search keywords embedded naturally. End with: subscribe CTA + hashtags #வரலாறு #TamilHistory #வரலாறுவிழிப்பு>",
  "tags": [
    "வரலாறு விழிப்பு", "Tamil history", "{topic_en}", "Tamil documentary",
    "history Tamil", "வரலாறு", "Tamil motivation", "Indian history Tamil",
    "educational Tamil", "Tamil stories", "history facts Tamil",
    "<topic specific tag 1>", "<topic specific tag 2>", "<topic specific tag 3>",
    "<era specific tag>", "<emotional angle tag>", "Tamil YouTube",
    "motivational Tamil", "true story Tamil", "real history Tamil",
    "Tamil facts", "amazing facts Tamil", "untold history Tamil"
  ],
  "pinned_comment": "<Two-choice Tamil question — forces comment. Max 150 chars. Example: 'இந்த கதையில் யார் உங்களை அதிகம் தொட்டது — X-வா Y-வா? 👇'>",
  "community_post": "<Short Tamil teaser for community tab, 200 chars, creates FOMO>",
  "thumbnail_text_primary": "<3-4 Tamil words, shocking, fits on thumbnail>",
  "thumbnail_text_secondary": "<2-3 words, subtext>",
  "chapter_timestamps": [
    {{"time": "00:00", "title": "Hook"}},
    {{"time": "00:30", "title": "வரலாறு பின்னணி"}},
    {{"time": "01:30", "title": "சவால்"}},
    {{"time": "02:30", "title": "முக்கிய தருணம்"}},
    {{"time": "03:30", "title": "விளைவு"}},
    {{"time": "04:30", "title": "இன்றைய பாடம்"}}
  ]
}}"""

SHORTS_SEO_PROMPT = """Generate YouTube Shorts metadata for Tamil history content.

Topic (Tamil): {topic_ta}
Hook: {hook}

Return ONLY valid JSON:
{{
  "title": "<Tamil Shorts title #Shorts, 55 chars, shocking hook>",
  "description": "<150 char Tamil description — hook + topic + hashtags #Shorts #TamilHistory #வரலாறு #facts>",
  "tags": ["Shorts","Tamil history","வரலாறு","facts Tamil","history shorts","Tamil shorts","amazing facts","untold history Tamil","<topic specific>","<era specific>"],
  "pinned_comment": "<Short Tamil question, max 100 chars>"
}}"""


def generate_seo(topic: dict, sections: list, video_type: str = "long") -> dict:
    slug  = hashlib.md5((topic["topic_ta"]+video_type+"seo").encode()).hexdigest()[:8]
    cache = Path(CACHE_DIR) / f"seo_{slug}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    log.info(f"🔍 Generating {video_type} SEO metadata...")
    preview = " ".join(sections[:2])[:300] if sections else ""
    prompt  = SEO_PROMPT if video_type=="long" else SHORTS_SEO_PROMPT

    try:
        raw = _llm(prompt.format(**topic, preview=preview), max_tokens=1500)
        raw = re.sub(r"```json|```","",raw).strip()
        m   = re.search(r'\{.*\}', raw, re.DOTALL)
        if m: raw = m.group()
        seo = json.loads(raw)
    except Exception as e:
        log.warning(f"SEO generation failed ({e}) — using fallback")
        seo = _fallback_seo(topic, video_type)

    # Validate required fields
    required_long  = ["title_ta","description","tags","pinned_comment"]
    required_short = ["title","description","tags","pinned_comment"]
    required = required_long if video_type=="long" else required_short
    for k in required:
        if k not in seo:
            log.warning(f"SEO missing field: {k}")
            seo[k] = _fallback_seo(topic, video_type).get(k,"")

    # Ensure tags has minimum count and includes channel tag
    if "tags" not in seo or len(seo["tags"]) < 10:
        seo["tags"] = _fallback_seo(topic, video_type)["tags"]
    if "வரலாறு விழிப்பு" not in seo["tags"]:
        seo["tags"].insert(0, "வரலாறு விழிப்பு")

    cache.write_text(json.dumps(seo, ensure_ascii=False, indent=2))
    log.info(f"✅ SEO: title={seo.get('title_ta',seo.get('title','?'))[:50]}")
    return seo


def _fallback_seo(topic: dict, video_type: str) -> dict:
    if video_type == "long":
        return {
            "title_ta"    : topic["topic_ta"][:58],
            "title_ta_alt": [topic["topic_ta"][:55], topic["topic_en"][:55]],
            "description" : f"{topic['hook']}\n\nவரலாறு விழிப்பு சேனலில் {topic['topic_ta']} பற்றிய தொகுப்பு.\n\n#வரலாறு #TamilHistory #வரலாறுவிழிப்பு",
            "tags"        : ["வரலாறு விழிப்பு","Tamil history","வரலாறு","Tamil documentary",
                            "history Tamil","educational Tamil","motivation Tamil",
                            topic["topic_en"][:30],topic["category"],topic["era"][:20]],
            "pinned_comment":"இந்த கதை உங்களை எவ்வாறு தொட்டது? கீழே சொல்லுங்கள் 👇",
            "community_post":f"{topic['hook']} — இன்றைய video பாருங்கள்! 🔥",
            "thumbnail_text_primary":topic["hook"].split("?")[0][:30],
            "thumbnail_text_secondary":topic["era"][:20],
            "chapter_timestamps":[{"time":"00:00","title":"Hook"},{"time":"01:00","title":"வரலாறு"}]
        }
    else:
        return {
            "title"        : f"{topic['hook'][:50]} #Shorts",
            "description"  : f"{topic['hook']} #Shorts #TamilHistory #வரலாறு #facts",
            "tags"         : ["Shorts","Tamil history","வரலாறு","facts Tamil","history shorts",
                             "Tamil shorts","amazing facts","untold history Tamil"],
            "pinned_comment":"இது உங்களுக்கு தெரியுமா? 👇"
        }


# ══════════════════════════════════════════════════════════════════════
# STEP 4 — TTS
# ══════════════════════════════════════════════════════════════════════
def generate_tts(text: str, out_path: str, voice: str = "ta-IN-PallaviNeural",
                 rate: str = "-10%", pitch: str = "+2Hz") -> str:
    """Generate Tamil TTS. Raises on failure."""
    import edge_tts

    # Clean text
    clean = re.sub(r'\[SCENE_BREAK\]','', text)
    clean = re.sub(r'([.!?।])\s+', r'\1 ', clean)
    clean = re.sub(r'\s{2,}',' ', clean).strip()

    if not clean:
        raise ValueError("Empty TTS text after cleaning")

    async def _tts():
        c = edge_tts.Communicate(clean, voice, rate=rate, pitch=pitch)
        await c.save(out_path)

    asyncio.run(_tts())

    if not Path(out_path).exists() or Path(out_path).stat().st_size < 1000:
        raise RuntimeError(f"TTS output missing or too small: {out_path}")

    # Apply EQ
    eq_out = out_path.replace(".mp3","_eq.mp3")
    eq = ("highpass=f=80,equalizer=f=200:t=q:w=0.9:g=1.5,"
          "equalizer=f=3000:t=q:w=0.8:g=2,aecho=0.75:0.62:26:0.05,"
          "acompressor=threshold=-20dB:ratio=1.7:attack=10:release=250:makeup=2.5,"
          "loudnorm=I=-14:TP=-1.5:LRA=11")
    r = subprocess.run(
        ["ffmpeg","-y","-loglevel","error","-i",out_path,"-af",eq,eq_out],
        capture_output=True
    )
    if r.returncode == 0 and Path(eq_out).exists():
        import shutil; shutil.move(eq_out, out_path)

    log.info(f"✅ TTS: {Path(out_path).stat().st_size//1024}KB")
    return out_path


# ══════════════════════════════════════════════════════════════════════
# STEP 5 — BGM
# ══════════════════════════════════════════════════════════════════════
def generate_bgm(duration: int = 660, emotional_angle: str = "victory") -> str:
    out = Path(AUDIO_DIR) / f"bgm_{emotional_angle}.mp3"
    if out.exists() and out.stat().st_size > 50_000:
        return str(out)

    # Tone mapping by emotion
    tones = {
        "victory"   : (220, 277, 330),   # A major feel
        "tragedy"   : (196, 233, 294),   # G minor feel
        "sacrifice" : (165, 196, 247),   # E minor feel
        "betrayal"  : (185, 220, 277),   # F# diminished feel
        "discovery" : (261, 329, 392),   # C major feel
    }
    freqs = tones.get(emotional_angle, (220, 277, 330))

    fc = (
        f"[0]volume=0.12,aecho=0.7:0.65:90:0.28[s1];"
        f"[1]volume=0.08,aecho=0.6:0.55:140:0.18[s2];"
        f"[2]volume=0.06,aecho=0.5:0.45:200:0.12[s3];"
        "[s1][s2][s3]amix=inputs=3:duration=longest[mix];"
        "[mix]equalizer=f=150:t=q:w=1:g=+5,"
        "equalizer=f=3000:t=q:w=1:g=-8,"
        f"afade=t=in:d=5,afade=t=out:st={max(0,duration-6)}:d=6,"
        "loudnorm=I=-24:TP=-3:LRA=8[out]"
    )
    r = subprocess.run([
        "ffmpeg","-y","-loglevel","error",
        "-f","lavfi","-i",f"sine=frequency={freqs[0]}:duration={duration}",
        "-f","lavfi","-i",f"sine=frequency={freqs[1]}:duration={duration}",
        "-f","lavfi","-i",f"sine=frequency={freqs[2]}:duration={duration}",
        "-filter_complex",fc,"-map","[out]","-ar","44100","-b:a","128k",str(out)
    ], capture_output=True)

    if r.returncode != 0 or not out.exists():
        # Simple fallback
        subprocess.run([
            "ffmpeg","-y","-loglevel","error","-f","lavfi",
            "-i",f"sine=frequency={freqs[0]}:duration={duration}",
            "-af","volume=0.06,loudnorm=I=-24",str(out)
        ], capture_output=True)

    log.info(f"✅ BGM: {out.stat().st_size//1024}KB ({emotional_angle})")
    return str(out)


# ══════════════════════════════════════════════════════════════════════
# STEP 6 — VIDEO RENDER
# ══════════════════════════════════════════════════════════════════════
def render_video(storyboard: list, narration: str, bgm: str,
                 out_path: str, is_shorts: bool = False) -> str:
    from renderer import render_full_video
    return render_full_video(
        storyboard      = storyboard,
        narration_audio = narration,
        bgm_audio       = bgm,
        out_video       = out_path,
    )


def create_shorts_storyboard(long_storyboard: list, shorts_sections: list) -> list:
    """Create a compressed storyboard for 60-second Shorts."""
    # Take first 4 scenes but compress duration to fit 60s
    scenes = long_storyboard[:4] if len(long_storyboard) >= 4 else long_storyboard
    total  = sum(s["duration"] for s in scenes)
    scale  = min(1.0, 58.0 / total)  # compress to 58s
    for s in scenes:
        s = s.copy()
        s["duration"] = s["duration"] * scale
    return scenes


# ══════════════════════════════════════════════════════════════════════
# STEP 7 — YOUTUBE UPLOAD
# ══════════════════════════════════════════════════════════════════════
def upload_to_youtube(video_path: str, seo: dict, is_shorts: bool = False,
                      max_retries: int = 3) -> str:
    """Upload with retry logic. Returns video_id or raises."""
    from youtube_uploader import upload_video

    title = seo.get("title") if is_shorts else seo.get("title_ta", seo.get("title",""))
    if not title:
        raise ValueError("No title in SEO metadata")

    # Add chapter timestamps to description (long form only)
    description = seo.get("description","")
    if not is_shorts and "chapter_timestamps" in seo:
        chapters = "\n".join(
            f"{ch['time']} {ch['title']}"
            for ch in seo["chapter_timestamps"]
        )
        description = f"{description}\n\n{chapters}"

    tags = seo.get("tags", [])[:30]  # YouTube max 30 tags

    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"  Upload attempt {attempt}/{max_retries}...")
            video_id = upload_video(
                video_path  = video_path,
                title       = title,
                description = description,
                tags        = tags,
                category_id = "27",       # Education
                privacy     = "public",
            )
            if video_id:
                log.info(f"  ✅ Uploaded: https://youtu.be/{video_id}")
                # Post pinned comment
                try:
                    from youtube_uploader import post_comment
                    comment = seo.get("pinned_comment","")
                    if comment:
                        post_comment(video_id, comment)
                        log.info(f"  ✅ Pinned comment posted")
                except Exception as ce:
                    log.warning(f"  Pinned comment failed: {ce}")
                return video_id
        except Exception as e:
            log.error(f"  Upload attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(30 * attempt)  # backoff
    raise RuntimeError(f"Upload failed after {max_retries} attempts")


def save_upload_log(entry: dict):
    records = []
    if LOG_FILE.exists():
        try: records = json.loads(LOG_FILE.read_text())
        except: records = []
    records.append({**entry, "logged_at": time.strftime("%Y-%m-%d %H:%M UTC")})
    LOG_FILE.write_text(json.dumps(records[-100:], ensure_ascii=False, indent=2))


# ══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════
def run(topic_override: str = "", upload: bool = True):
    """
    Full pipeline with separate video + shorts tracks.
    Error handling: each step logs failure and continues where possible.
    """
    results = {"video": None, "shorts": None, "errors": []}

    # ── Step 1: Topic ────────────────────────────────────────────────
    try:
        if topic_override.strip():
            topic = {
                "topic_ta"       : topic_override,
                "topic_en"       : topic_override,
                "hook"           : "",
                "era"            : "Unknown",
                "category"       : "history",
                "search_intent"  : topic_override,
                "emotional_angle": "victory"
            }
            log.info(f"Manual topic: {topic_override}")
        else:
            topic = discover_topic()

        slug = hashlib.md5(topic["topic_ta"].encode()).hexdigest()[:10]
        log.info(f"\n{'='*60}")
        log.info(f"TOPIC: {topic['topic_ta']}")
        log.info(f"HOOK:  {topic.get('hook','')}")
        log.info(f"ANGLE: {topic.get('emotional_angle','')}")
        log.info(f"{'='*60}\n")
    except Exception as e:
        log.error(f"Topic step failed: {e}")
        results["errors"].append(f"topic: {e}")
        return results

    # ── Step 2: Scripts ───────────────────────────────────────────────
    try:
        log.info("📝 Long-form script...")
        long_sections = generate_script(topic, "long")
    except Exception as e:
        log.error(f"Long script failed: {e}")
        results["errors"].append(f"long_script: {e}")
        return results

    try:
        log.info("📝 Shorts script...")
        short_sections = generate_script(topic, "short")
    except Exception as e:
        log.warning(f"Shorts script failed ({e}) — using long script condensed")
        short_sections = long_sections[:2]

    # ── Step 3: SEO ───────────────────────────────────────────────────
    try:
        log.info("🔍 Long SEO...")
        long_seo = generate_seo(topic, long_sections, "long")
    except Exception as e:
        log.warning(f"Long SEO failed ({e}) — fallback")
        long_seo  = _fallback_seo(topic, "long")

    try:
        log.info("🔍 Shorts SEO...")
        short_seo = generate_seo(topic, short_sections, "short")
    except Exception as e:
        log.warning(f"Short SEO failed ({e}) — fallback")
        short_seo = _fallback_seo(topic, "short")

    # ── Step 4: TTS ───────────────────────────────────────────────────
    long_narration = Path(AUDIO_DIR) / f"{slug}_long.mp3"
    short_narration= Path(AUDIO_DIR) / f"{slug}_short.mp3"

    try:
        if not long_narration.exists():
            log.info("🔊 Long narration TTS...")
            generate_tts(" ".join(long_sections), str(long_narration))
        else:
            log.info("🔊 Long narration: cache hit")
    except Exception as e:
        log.error(f"Long TTS failed: {e}")
        results["errors"].append(f"long_tts: {e}")
        # Can still try shorts

    try:
        if not short_narration.exists():
            log.info("🔊 Shorts narration TTS...")
            generate_tts(" ".join(short_sections[:3]), str(short_narration))
        else:
            log.info("🔊 Shorts narration: cache hit")
    except Exception as e:
        log.warning(f"Shorts TTS failed ({e}) — will skip shorts")
        short_narration = None

    # ── Step 5: Storyboard ────────────────────────────────────────────
    try:
        log.info("🎬 Building storyboard...")
        full_script   = " ".join(long_sections)
        long_storyboard = build_storyboard(full_script, topic["topic_ta"])
        log.info(f"  {len(long_storyboard)} scenes for long-form")
    except Exception as e:
        log.error(f"Storyboard failed: {e}")
        results["errors"].append(f"storyboard: {e}")
        return results

    # ── Step 6: BGM ───────────────────────────────────────────────────
    try:
        total_dur = sum(s["duration"] for s in long_storyboard)
        bgm = generate_bgm(int(total_dur)+30, topic.get("emotional_angle","victory"))
    except Exception as e:
        log.warning(f"BGM failed ({e}) — silent BGM")
        bgm = None

    # ── Step 7: Render Long-form ──────────────────────────────────────
    long_video = Path(VIDEO_DIR) / f"{slug}_long.mp4"
    if long_narration.exists() and not long_video.exists():
        try:
            log.info("🎬 Rendering long-form video...")
            render_video(long_storyboard, str(long_narration), bgm, str(long_video))
            results["video"] = str(long_video)
            log.info(f"✅ Long video: {long_video.stat().st_size//1024//1024}MB, {total_dur:.0f}s")
        except Exception as e:
            log.error(f"Long render failed: {e}")
            results["errors"].append(f"long_render: {e}")
    elif long_video.exists():
        results["video"] = str(long_video)
        log.info(f"✅ Long video: cache hit")

    # ── Step 8: Render Shorts ─────────────────────────────────────────
    shorts_video = Path(VIDEO_DIR) / f"{slug}_shorts.mp4"
    if short_narration and Path(str(short_narration)).exists() and not shorts_video.exists():
        try:
            log.info("🎬 Rendering Shorts...")
            shorts_storyboard = create_shorts_storyboard(long_storyboard, short_sections)
            render_video(shorts_storyboard, str(short_narration), bgm, str(shorts_video), is_shorts=True)
            results["shorts"] = str(shorts_video)
            log.info(f"✅ Shorts video: {shorts_video.stat().st_size//1024}KB")
        except Exception as e:
            log.warning(f"Shorts render failed ({e}) — skipping")
            results["errors"].append(f"shorts_render: {e}")
    elif shorts_video.exists():
        results["shorts"] = str(shorts_video)

    # ── Step 9: Upload ────────────────────────────────────────────────
    if upload:
        if results.get("video") and Path(results["video"]).exists():
            try:
                log.info("\n📤 Uploading long-form to YouTube...")
                video_id = upload_to_youtube(results["video"], long_seo, is_shorts=False)
                results["video_id"] = video_id
                save_upload_log({
                    "type"    : "long",
                    "topic"   : topic["topic_ta"],
                    "slug"    : slug,
                    "video_id": video_id,
                    "title"   : long_seo.get("title_ta",""),
                    "url"     : f"https://youtu.be/{video_id}",
                })
            except Exception as e:
                log.error(f"Long upload failed: {e}")
                results["errors"].append(f"long_upload: {e}")

        if results.get("shorts") and Path(results["shorts"]).exists():
            try:
                log.info("\n📤 Uploading Shorts to YouTube...")
                time.sleep(10)  # brief pause between uploads
                shorts_id = upload_to_youtube(results["shorts"], short_seo, is_shorts=True)
                results["shorts_id"] = shorts_id
                save_upload_log({
                    "type"    : "shorts",
                    "topic"   : topic["topic_ta"],
                    "slug"    : slug,
                    "video_id": shorts_id,
                    "title"   : short_seo.get("title",""),
                    "url"     : f"https://youtu.be/{shorts_id}",
                })
            except Exception as e:
                log.warning(f"Shorts upload failed ({e}) — continuing")
                results["errors"].append(f"shorts_upload: {e}")
    else:
        log.info("\n⏭  Upload skipped (--no-upload flag)")

    # ── Summary ───────────────────────────────────────────────────────
    log.info(f"\n{'='*60}")
    log.info("PIPELINE COMPLETE")
    log.info(f"  Long video : {results.get('video','❌ failed')}")
    log.info(f"  Shorts     : {results.get('shorts','❌ failed')}")
    log.info(f"  Video ID   : {results.get('video_id','not uploaded')}")
    log.info(f"  Shorts ID  : {results.get('shorts_id','not uploaded')}")
    if results["errors"]:
        log.warning(f"  Errors     : {results['errors']}")
    log.info(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tamil History Documentary Pipeline v2")
    ap.add_argument("--topic",     default="", help="Custom topic (blank=LLM auto-discover)")
    ap.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    ap.add_argument("--list",      action="store_true", help="List recent uploads and exit")
    args = ap.parse_args()

    if args.list:
        if LOG_FILE.exists():
            logs = json.loads(LOG_FILE.read_text())
            for entry in logs[-10:]:
                print(f"  {entry.get('logged_at','')} | {entry.get('type','?'):6} | {entry.get('url','')} | {entry.get('title','')[:50]}")
        else:
            print("No upload log found")
        sys.exit(0)

    run(topic_override=args.topic, upload=not args.no_upload)
