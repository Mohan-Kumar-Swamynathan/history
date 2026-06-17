#!/usr/bin/env python3
"""
துளிர் v2 — Almost Everything style
Story-driven narration of REAL incidents + character drawn on screen
2 long videos + 2 Shorts per day, fully automated
"""
import os, sys, re, json, time, hashlib, asyncio, subprocess, random, logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import cairosvg, io
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).parent))

# Import ae_engine AFTER sys.path is set
from ae_engine import render_frame as _ae_render_frame, pick_background
logging.basicConfig(level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S", handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("thulir")

# ── Dirs ──────────────────────────────────────────────────────────────
BASE   = Path(__file__).parent
OUT    = BASE / "thulir_v2"
for d in ["scripts","audio","video","thumbnails","cache","frames","shorts"]:
    (OUT/d).mkdir(parents=True, exist_ok=True)

STATE = OUT / "state.json"
LOG   = BASE / "thulir_upload_log.json"

# ── LLM ───────────────────────────────────────────────────────────────
try:
    from llm_client import generate_text as _llm
except:
    def _llm(p, **k): raise RuntimeError("no llm_client")

# ══════════════════════════════════════════════════════════════════════
# STEP 1 — TOPIC DISCOVERY (real incidents, not generic tips)
# ══════════════════════════════════════════════════════════════════════
TOPIC_PROMPT = """You write topics for "துளிர்" — a Tamil motivational YouTube channel in the style of "Almost Everything".

Almost Everything format:
- Real story of a NAMED person (fictional name but based on real scenario)
- Emotional journey: problem → struggle → turning point → result
- 3rd person narration like a story: "Arjun was 24. He earned ₹35,000. But..."
- Topics: real life struggles Tamil youth face (salary, parents, career fear, relationships, failure)
- NOT generic tips — REAL STORIES with specific details

Previously covered topics (don't repeat):
{used}

Generate ONE fresh story topic with a real incident angle.

Return ONLY valid JSON:
{{
  "story_title": "<Tamil title — emotional, specific>",
  "protagonist": "<Tamil name — Arjun/Priya/Karthik/Divya/Ravi/Meena etc>",
  "protagonist_age": "<age 22-32>",
  "situation": "<specific situation — ₹28000 salary, software job, Coimbatore, etc>",
  "core_problem": "<the real struggle — single line>",
  "emotional_hook": "<the most emotional moment in the story>",
  "turning_point": "<what changed everything>",
  "lesson": "<the ONE thing the story teaches>",
  "hook_question": "<opening question in Tamil — makes viewer say 'yes that's me'>",
  "story_category": "<salary|career|family|anxiety|relationships|failure|self_doubt|comparison>"
}}"""

FALLBACK_TOPICS = [
    {"story_title":"₹28,000 சம்பளத்தில் அப்பாவை நம்பிக்கை வைக்க முடியாத மகன்",
     "protagonist":"அர்ஜுன்","protagonist_age":"24","situation":"Coimbatore IT job ₹28,000",
     "core_problem":"அப்பா எதிர்பார்ப்புக்கும் தன் தகுதிக்கும் இடையில் சிக்கினான்",
     "emotional_hook":"அப்பா கேட்டார் — மகனே உன்னால் சம்பாரிக்க முடியாதா?",
     "turning_point":"அவன் ஒரு தவறிலிருந்து ஒரு மிகப்பெரிய பாடம் கற்றான்",
     "lesson":"தோல்வி ஒரு முடிவு அல்ல — ஒரு திருப்புமுனை",
     "hook_question":"உன் சம்பளம் பற்றி யாராவது கேட்கும்போது நீ என்ன சொல்வாய்?",
     "story_category":"salary"},
    {"story_title":"Campus placement-ல் reject ஆன பிறகு Priya என்ன செய்தாள்?",
     "protagonist":"பிரியா","protagonist_age":"22","situation":"Chennai college, 3 company rejections",
     "core_problem":"எல்லாரும் placed ஆனார்கள் — அவள் மட்டும் இல்லை",
     "emotional_hook":"தனிமையில் அழுதவள் — ஆனால் யாரிடமும் சொல்லவில்லை",
     "turning_point":"ஒரு rejection letter அவளை ஒரு different path காட்டியது",
     "lesson":"உன் plan B தான் சில நேரம் உன் best plan",
     "hook_question":"Reject ஆகும்போது நீ முதலில் என்ன feel ஆவாய்?",
     "story_category":"career"},
    {"story_title":"ஒவ்வொரு Sunday-யும் anxiety வந்த Karthik-கின் கதை",
     "protagonist":"கார்த்திக்","protagonist_age":"27","situation":"Bangalore MNC, Sunday evening dread",
     "core_problem":"வாரம் முழுக்க உழைத்தான் — ஆனால் Sunday-ல் மட்டும் பயமாக இருந்தது",
     "emotional_hook":"Sunday இரவு தூக்கமே வரவில்லை — Monday பயம்",
     "turning_point":"ஒரு நண்பனின் ஒரு வார்த்தை அவனை மாற்றியது",
     "lesson":"நீ உணரும் பயம் உனக்கு மட்டும் இல்லை",
     "hook_question":"Sunday evening-ல் உனக்கும் இப்படி ஆகுதா?",
     "story_category":"anxiety"},
]

def load_state():
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except: pass
    return {"used":[], "runs":0}

def save_state(s): STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))

def discover_topic():
    state = load_state()
    used  = state["used"][-15:]
    today = time.strftime("%Y-%m-%d")
    if state.get("today") == today and state.get("topic"):
        return state["topic"]
    try:
        raw  = _llm(TOPIC_PROMPT.format(used="\n".join(f"- {t}" for t in used) or "none"), max_tokens=600)
        raw  = re.sub(r"```json|```","",raw).strip()
        m    = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if m: raw = m.group()
        topic = json.loads(raw)
        assert all(k in topic for k in ["story_title","protagonist","core_problem","hook_question"])
        log.info(f"Topic: {topic['story_title'][:60]}")
    except Exception as e:
        log.warning(f"LLM topic failed ({e}) — fallback")
        avail = [t for t in FALLBACK_TOPICS if t["story_title"] not in used]
        topic = random.choice(avail or FALLBACK_TOPICS)
    used.append(topic["story_title"])
    state.update({"used": used[-25:], "today": today, "topic": topic,
                  "runs": state["runs"]+1})
    save_state(state)
    return topic

# ══════════════════════════════════════════════════════════════════════
# STEP 2 — SCRIPT (story-driven, 3rd person, Almost Everything style)
# ══════════════════════════════════════════════════════════════════════
LONG_SCRIPT_PROMPT = """நீங்கள் "துளிர்" YouTube channel-க்கு script எழுதுகிறீர்கள்.
Style: Almost Everything Tamil channel — real story, 3rd person narration, emotional journey.

CHARACTER: {protagonist} (வயது {protagonist_age})
SITUATION: {situation}
PROBLEM: {core_problem}
EMOTIONAL HOOK: {emotional_hook}
TURNING POINT: {turning_point}
LESSON: {lesson}
OPENING QUESTION: {hook_question}

SCRIPT FORMAT — 8 scenes separated by [SCENE_BREAK]:

Scene 1 — HOOK (15 seconds):
"{hook_question}" — இந்த கேள்வியுடன் தொடங்கு.
{protagonist}-ஐ introduce பண்ணு — வயது, இடம், ஒரு specific detail.
Viewer feel: "இது என்னோட கதை"

Scene 2 — THE SETUP:
{protagonist}-ன் daily life. Specific numbers (சம்பளம்/marks/situation).
எல்லாரும் என்ன நினைக்கிறார்கள் vs அவன்/அவள் என்ன feel ஆகிறார்கள்.

Scene 3 — THE PROBLEM DEEPENS:
The moment everything felt worst.
உள்ளே என்ன நடந்தது — thoughts, feelings, specific scene.
யாரோ என்ன சொன்னார்கள் (dialogue style).

Scene 4 — THE STRUGGLE:
அவன்/அவள் என்ன try பண்ணார்கள். What failed first.
A specific incident that made it worse.
One moment of complete doubt.

Scene 5 — THE TURNING POINT:
{turning_point} — exactly what happened.
A specific conversation / realization / incident.
The moment the mindset shifted.

Scene 6 — THE CHANGE:
What {protagonist} did differently after that.
Specific steps — not advice, but what THIS PERSON did.
One month later, what changed?

Scene 7 — THE RESULT:
6 months later — specific outcome (number/achievement/relationship).
How family/friends reacted.
What {protagonist} learned.

Scene 8 — THE LESSON + CTA:
"{lesson}" — say this as a closing truth.
Connect to the viewer: "உன் கதையும் இப்படியே தொடங்கலாம்."
"இந்த story-ல் உன்னை எந்த moment-ல் பார்த்தாய்? Comment-ல் சொல்லு 👇"
"துளிர் channel-ஐ subscribe பண்ணு 🔔"

RULES:
- 3rd person throughout: "{protagonist} நினைத்தான்/நினைத்தாள்"
- Specific details always: ₹28,000 not "குறைவான சம்பளம்"
- Emotional, conversational Tamil
- [SCENE_BREAK] between scenes only
- 4-6 sentences per scene"""

SHORTS_SCRIPT_PROMPT = """60-second Tamil YouTube Shorts script — Almost Everything style.
Story: {protagonist} ({protagonist_age}) — {core_problem}
Hook: {hook_question}

FORMAT (150 words max, [SCENE_BREAK] between 4 parts):

Part 1 — HOOK (10s): {hook_question} + {protagonist}-ஐ introduce.
Part 2 — THE LOW (20s): Worst moment. Specific. Emotional.
Part 3 — THE TURN (20s): {turning_point} — what changed.
Part 4 — LESSON + CTA (10s): "{lesson}" + subscribe.

3rd person narration. Tamil only. Conversational. Max 4 sentences per part."""

def generate_script(topic, script_type="long"):
    slug  = hashlib.md5((topic["story_title"]+script_type).encode()).hexdigest()[:8]
    cache = OUT/"cache"/f"script_{slug}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    prompt = LONG_SCRIPT_PROMPT if script_type=="long" else SHORTS_SCRIPT_PROMPT
    raw    = _llm(prompt.format(**topic), max_tokens=3000 if script_type=="long" else 700)
    scenes = [s.strip() for s in raw.split("[SCENE_BREAK]") if s.strip() and len(s.strip())>15]
    scenes = [re.sub(r'^Scene\s*\d[^:]*:\s*','',s,flags=re.MULTILINE).strip() for s in scenes]
    scenes = [s for s in scenes if len(s)>15]
    if len(scenes)<3:
        scenes = [p.strip() for p in raw.split("\n\n") if len(p.strip())>20][:8]
    cache.write_text(json.dumps(scenes,ensure_ascii=False,indent=2))
    log.info(f"{script_type} script: {len(scenes)} scenes, {sum(len(s.split()) for s in scenes)} words")
    return scenes

# ══════════════════════════════════════════════════════════════════════
# STEP 3 — VISUAL ENGINE (character + text, AE style)
# ══════════════════════════════════════════════════════════════════════
W, H = 1920, 1080
PURE_WHITE = (255,255,255)
INK        = (22, 22, 22)
RED        = (210, 40, 30)
GREEN_DONE = (34, 120, 60)
GREY_SH    = (210, 210, 205)

FONTS = {
    "ta_black"  : "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "ta_bold"   : "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "ta_reg"    : "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "en_black"  : "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "en_bold"   : "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
}
_FC = {}
def _f(k,s):
    if (k,s) not in _FC:
        try: _FC[(k,s)] = ImageFont.truetype(FONTS[k],s)
        except: _FC[(k,s)] = ImageFont.load_default()
    return _FC[(k,s)]

def _segs(text):
    out,cur,ct=[],""  ,None
    for ch in text:
        cp=ord(ch)
        t="ta" if(0x0B80<=cp<=0x0BFF or ch in ' .,!?₹%-:;')else"en"
        if t!=ct and cur:out.append((cur,ct));cur=""
        cur+=ch;ct=t
    if cur:out.append((cur,ct))
    return out

def _tw(draw,text,sz):
    w=0
    for seg,t in _segs(text):
        f=_f("ta_black"if t=="ta"else"en_black",sz)
        w+=draw.textbbox((0,0),seg,font=f)[2]
    return w

def _dt(draw,text,x,y,sz,col,shadow=True):
    cx=x
    for seg,t in _segs(text):
        f=_f("ta_black"if t=="ta"else"en_black",sz)
        if shadow:draw.text((cx+3,y+3),seg,font=f,fill=GREY_SH,anchor="lt")
        draw.text((cx,y),seg,font=f,fill=col,anchor="lt")
        cx+=draw.textbbox((0,0),seg,font=f)[2]
    return cx

def _wrap(words,sz,maxw,draw):
    lines,cur=[],[]
    for w in words:
        test=" ".join(cur+[w])
        ta=_f("ta_black",sz);en=_f("en_black",sz)
        if _tw(draw,test,sz)<=maxw or not cur:cur.append(w)
        else:lines.append(cur);cur=[w]
    if cur:lines.append(cur)
    return lines

# ── Stick figure SVG paths (the character) ──────────────────────────
def _stick_figure_svg(emotion:str, progress:float, size:int=300, color:str="#161616") -> Image.Image:
    """
    Draw a stick figure that expresses emotion.
    progress: 0→1 draws the figure stroke by stroke.
    emotion: neutral|sad|happy|thinking|walking|celebrating
    """
    FIGURES = {
        "neutral": [
            ("M 60 20 A 20 20 0 1 0 60 60 A 20 20 0 1 0 60 20",4),  # head
            ("M 60 60 L 60 110",4),      # body
            ("M 60 75 L 35 95",3.5),     # left arm
            ("M 60 75 L 85 95",3.5),     # right arm
            ("M 60 110 L 40 140",4),     # left leg
            ("M 60 110 L 80 140",4),     # right leg
        ],
        "sad": [
            ("M 60 18 A 20 20 0 1 0 60 58 A 20 20 0 1 0 60 18",4),
            ("M 60 58 L 60 105 Q 58 115 56 118",4),
            ("M 60 72 L 38 90",3.5),
            ("M 60 72 L 82 90",3.5),
            ("M 60 105 L 42 138",4),
            ("M 60 105 L 78 138",4),
            ("M 50 45 Q 52 50 54 45",2),  # sad mouth
        ],
        "happy": [
            ("M 60 18 A 20 20 0 1 0 60 58 A 20 20 0 1 0 60 18",4),
            ("M 60 58 L 60 108",4),
            ("M 60 72 L 35 88",3.5),     # left arm up (celebrating)
            ("M 60 72 L 85 88",3.5),
            ("M 60 108 L 42 140",4),
            ("M 60 108 L 78 140",4),
            ("M 50 43 Q 60 52 70 43",2.5),  # smile
        ],
        "thinking": [
            ("M 60 18 A 20 20 0 1 0 60 58 A 20 20 0 1 0 60 18",4),
            ("M 60 58 L 60 108",4),
            ("M 60 72 L 38 88 L 38 75",3.5),  # hand to chin
            ("M 60 72 L 82 90",3.5),
            ("M 60 108 L 42 140",4),
            ("M 60 108 L 78 140",4),
            ("M 75 28 L 80 22 M 80 22 L 85 28 M 85 28 L 90 22",2),  # thought dots
        ],
        "celebrating": [
            ("M 60 18 A 20 20 0 1 0 60 58 A 20 20 0 1 0 60 18",4),
            ("M 60 58 L 60 108",4),
            ("M 60 72 L 30 55",3.5),     # both arms raised
            ("M 60 72 L 90 55",3.5),
            ("M 60 108 L 45 140",4),
            ("M 60 108 L 75 140",4),
            ("M 50 43 Q 60 55 70 43",3),  # big smile
            ("M 28 48 L 25 42 M 95 45 L 98 40",2),  # stars near hands
        ],
        "walking": [
            ("M 60 18 A 20 20 0 1 0 60 58 A 20 20 0 1 0 60 18",4),
            ("M 60 58 L 62 108",4),
            ("M 62 72 L 40 92",3.5),
            ("M 62 72 L 88 84",3.5),
            ("M 62 108 L 38 142",4),     # stride
            ("M 62 108 L 82 132",4),
        ],
    }
    paths = FIGURES.get(emotion, FIGURES["neutral"])
    n     = len(paths)
    drawn = progress * n
    parts = []
    for i,(d,sw) in enumerate(paths):
        length = max(60.0, len(re.findall(r'-?[\d.]+',d))//2*14.0)
        lp     = min(1.0, max(0.0, drawn-i))
        dash   = length*lp; gap = length-dash+1
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw*2.2:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{gap:.1f}"/>'
        )
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 120 160" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')
    return Image.open(io.BytesIO(
        cairosvg.svg2png(bytestring=svg.encode(),output_width=size,output_height=size)
    )).convert("RGBA")

# ── Pencil cursor ────────────────────────────────────────────────────
_PENCIL = None
def _get_pencil(size=65):
    global _PENCIL
    if _PENCIL is None:
        svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
<g transform="rotate(-35 30 30)">
<rect x="26" y="8" width="8" height="36" rx="2" fill="#F5C518" stroke="#8B6914" stroke-width="1.2"/>
<polygon points="26,44 34,44 30,52" fill="#F0A020" stroke="#8B6914" stroke-width="1"/>
<polygon points="28,49 32,49 30,52" fill="#555"/>
<rect x="26" y="6" width="8" height="5" rx="1.5" fill="#E88080" stroke="#8B6914" stroke-width="1"/>
</g></svg>'''
        _PENCIL = Image.open(io.BytesIO(
            cairosvg.svg2png(bytestring=svg.encode(),output_width=size,output_height=size)
        )).convert("RGBA")
    return _PENCIL

# ── Emotion detector from scene text ────────────────────────────────
def _detect_emotion(text:str, scene_idx:int) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["வெற்றி","மகிழ்","subscribe","கிடைத்","promotion","happy","achieve"]):
        return "celebrating"
    if any(w in text_lower for w in ["அழு","வலி","தோல்வி","reject","failed","sad","கஷ்ட","பயம்"]):
        return "sad"
    if any(w in text_lower for w in ["யோசி","சிந்தி","thinking","wonder","கேள்வி","புரிய"]):
        return "thinking"
    if any(w in text_lower for w in ["நட","walk","போ","வா","move","change","turn"]):
        return "walking"
    if any(w in text_lower for w in ["சிரி","laugh","happy","good","நல்ல","மகிழ்"]):
        return "happy"
    # default by scene position
    defaults = ["neutral","sad","sad","thinking","thinking","walking","happy","celebrating"]
    return defaults[scene_idx % len(defaults)]

# ── Main frame renderer ─────────────────────────────────────────────
def render_frame(
    all_words   : list,
    visible     : int,
    figure_progress: float,
    emotion     : str,
    protagonist : str,
    scene_num   : int,
    total_scenes: int,
    is_shorts   : bool = False,
) -> Image.Image:
    img  = Image.new("RGB",(W,H),PURE_WHITE)
    draw = ImageDraw.Draw(img)

    # ── Stick figure (right 35% of screen) ───────────────────────────
    FIG_SIZE = 420 if not is_shorts else 320
    FIG_X    = W - FIG_SIZE - 60
    FIG_Y    = (H - FIG_SIZE) // 2 - 20

    if figure_progress > 0.02:
        fig = _stick_figure_svg(emotion, figure_progress, FIG_SIZE, "#1A1A1A")
        img.paste(fig, (FIG_X, FIG_Y), fig)

        # Pencil cursor at current stroke tip while drawing
        if 0.02 < figure_progress < 0.92:
            pencil = _get_pencil()
            # Approximate tip position based on figure bounding box
            tip_x = FIG_X + int(FIG_SIZE * 0.55)
            tip_y = FIG_Y + int(FIG_SIZE * figure_progress * 0.9)
            img.paste(pencil, (min(W-80, tip_x), max(0, tip_y-60)), pencil)

        # Character name label below figure
        if figure_progress > 0.7:
            name_sz = 32
            nw = _tw(draw, protagonist, name_sz)
            _dt(draw, protagonist, FIG_X+(FIG_SIZE-nw)//2,
                FIG_Y+FIG_SIZE+10, name_sz, (120,120,120), shadow=False)

    # ── Main text (left 60%) ─────────────────────────────────────────
    TEXT_X   = 60
    TEXT_Y   = 80
    TEXT_W   = FIG_X - 100  # leave gap before figure

    words_vis = all_words[:visible]

    # Dynamic font: bigger when fewer words
    total_words = len(all_words)
    for sz in [120, 100, 86, 74, 64, 54]:
        lines = _wrap(words_vis, sz, TEXT_W, draw)
        lh    = draw.textbbox((0,0),"A",font=_f("ta_black",sz))[3] + 22
        if TEXT_Y + len(lines)*lh < H-100:
            break

    y, wi = TEXT_Y, 0
    last_x = TEXT_X
    for li, lw in enumerate(lines):
        x   = TEXT_X
        fnt = sz if li==0 else max(54, sz-12)
        for word in lw:
            is_curr  = (wi==visible-1) and (visible<total_words)
            is_final = (wi==visible-1) and (visible==total_words)
            col = RED if is_curr else (GREEN_DONE if is_final else INK)
            last_x = _dt(draw, word+" ", x, y, fnt, col, shadow=False)
            x=last_x; wi+=1
        lh_val = draw.textbbox((0,0),"A",font=_f("ta_black",fnt))[3]+22
        y += lh_val
        if y > H-120: break

    # Blinking cursor
    if visible < total_words:
        ch = draw.textbbox((0,0),"A",font=_f("ta_black",sz))[3]
        draw.rectangle([last_x+4, y-lh_val, last_x+9, y-lh_val+ch], fill=INK)

    return img


# ══════════════════════════════════════════════════════════════════════
# STEP 4 — SCENE VIDEO (word-by-word + figure drawing simultaneously)
# ══════════════════════════════════════════════════════════════════════
def render_scene_video(
    scene_text:str, scene_idx:int, total_scenes:int,
    slug:str, protagonist:str, audio:Path,
    word_timings:list, duration:float,
    out_dir:Path, is_shorts:bool=False,
) -> Path:
    out = out_dir / f"{slug}_s{scene_idx:02d}.mp4"
    if out.exists() and out.exists() and out.stat().st_size>10000:
        return out

    words   = scene_text.split()
    emotion = _detect_emotion(scene_text, scene_idx)
    FIG_END = duration * 0.45   # figure finishes drawing by 45% of scene

    # Build events timeline
    events = {0.0, duration}
    for wt in word_timings:
        events.add(wt["start"])
    STEPS = 14
    for s in range(STEPS+1):
        events.add(s/STEPS*FIG_END)
    events = sorted(events)

    frame_dir = out_dir / f"fd_{slug}_{scene_idx:02d}"
    frame_dir.mkdir(parents=True, exist_ok=True)

    segs, prev_state, prev_frame, last_t, unique = [], None, None, 0.0, 0
    log.info(f"  Scene {scene_idx}: {emotion}, {len(words)} words, {duration:.1f}s")

    for t in events:
        t = min(t, duration)
        vis    = max(1, min(sum(1 for wt in word_timings if wt["start"]<=t), len(words)))
        fig_p  = round(min(1.0, t/max(FIG_END,0.1))*STEPS)/STEPS
        state  = (vis, fig_p)

        if state != prev_state:
            fp = frame_dir / f"kf_{unique:04d}.png"
            bg_fn = pick_background(scene_text, scene_idx)
            img = _ae_render_frame(
                all_words=words, visible=vis,
                figure_progress=fig_p, bg_progress=fig_p,
                emotion=emotion, protagonist=protagonist,
                bg_draw_fn=bg_fn,
                scene_num=scene_idx, total_scenes=total_scenes,
                is_shorts=is_shorts,
            )
            img.save(str(fp),"PNG",optimize=True)
            prev_state=state; prev_frame=fp; unique+=1

        seg_dur = t-last_t
        if seg_dur>0.001 and prev_frame:
            segs.append((prev_frame, seg_dur))
        last_t = t

    log.info(f"  {unique} keyframes → encoding")

    cfile = frame_dir/"frames.txt"
    with open(cfile,"w") as f:
        for fp,sd in segs:
            f.write(f"file '{fp.resolve()}'\nduration {sd:.4f}\n")
        if segs: f.write(f"file '{segs[-1][0].resolve()}'\n")

    r = subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(cfile),
        "-i",str(audio),
        "-c:v","libx264","-preset","veryfast","-crf","21",
        "-c:a","aac","-b:a","128k","-pix_fmt","yuv420p","-shortest",
        str(out)
    ], capture_output=True, text=True, timeout=600)

    import shutil; shutil.rmtree(str(frame_dir),ignore_errors=True)
    if r.returncode!=0: raise RuntimeError(f"Scene encode failed: {r.stderr[-200:]}")
    log.info(f"  ✅ Scene {scene_idx}: {out.stat().st_size//1024}KB")
    return out


# ══════════════════════════════════════════════════════════════════════
# STEP 5 — TTS
# ══════════════════════════════════════════════════════════════════════
VOICE="ta-IN-PallaviNeural"; RATE="-10%"; PITCH="+2Hz"

async def _tts_stream(text, out):
    import edge_tts
    timings=[]
    c=edge_tts.Communicate(text,VOICE,rate=RATE,pitch=PITCH,boundary="WordBoundary")
    with open(out,"wb") as f:
        async for chunk in c.stream():
            if chunk["type"]=="audio": f.write(chunk["data"])
            elif chunk["type"]=="WordBoundary":
                s=chunk["offset"]/10_000_000; d=chunk["duration"]/10_000_000
                timings.append({"word":chunk["text"],"start":s,"end":s+d})
    return timings

def synthesise(text, idx, slug, subdir="audio"):
    raw = OUT/subdir/f"{slug}_{idx:02d}_raw.mp3"
    eq  = OUT/subdir/f"{slug}_{idx:02d}.mp3"
    tc  = OUT/"cache"/f"t_{slug}_{idx:02d}.json"
    if eq.exists() and tc.exists() and eq.stat().st_size>500:
        return eq, _dur(eq), json.loads(tc.read_text())
    clean = re.sub(r'[*_#>`\[\]]','',text)
    clean = re.sub(r'\s+',' ',clean).strip()
    try:
        timings = asyncio.run(_tts_stream(clean, str(raw)))
    except Exception as e:
        log.warning(f"TTS failed ({e}) — silence")
        words = clean.split(); dp=0.4
        timings=[{"word":w,"start":i*dp,"end":(i+1)*dp} for i,w in enumerate(words)]
        # Use WAV for silence (mp3 needs valid headers)
        raw = Path(str(raw).replace(".mp3",".wav"))
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                        f"anullsrc=r=48000:cl=stereo","-t",
                        str(len(words)*dp),str(raw)],capture_output=True)
    eq_chain=("highpass=f=80,equalizer=f=200:t=q:w=0.9:g=1.5,"
              "equalizer=f=800:t=q:w=0.8:g=2,equalizer=f=3000:t=q:w=0.8:g=2.5,"
              "aecho=0.75:0.62:26:0.05,acompressor=threshold=-20dB:ratio=1.7:"
              "attack=10:release=250:makeup=2.5,atempo=0.98,"
              "loudnorm=I=-14:TP=-1.5:LRA=11")
    subprocess.run(["ffmpeg","-y","-i",str(raw),"-af",eq_chain,
                    "-ar","48000","-b:a","192k",str(eq)],capture_output=True)
    if not eq.exists():
        import shutil
        if raw.exists(): shutil.copy(raw,eq)
        else:
            subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                           "anullsrc=r=48000:cl=stereo","-t","5",str(eq)],
                           capture_output=True)
    tc.write_text(json.dumps(timings,ensure_ascii=False))
    return eq, _dur(eq), timings

def _dur(p):
    try:
        r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=noprint_wrappers=1:nokey=1",str(p)],
                         capture_output=True,text=True)
        return float(r.stdout.strip())
    except: return 10.0


# ══════════════════════════════════════════════════════════════════════
# STEP 6 — BGM
# ══════════════════════════════════════════════════════════════════════
def ensure_bgm(dur=660, category="motivation"):
    out = OUT/"audio"/f"bgm_{category}.mp3"
    if out.exists() and out.stat().st_size>50000: return str(out)
    tones={"motivation":(220,277,330),"sad":(196,233,294),"anxiety":(185,220,277),"salary":(261,329,392)}
    f1,f2,f3=tones.get(category,(220,277,330))
    fc=(f"[0]volume=0.10,aecho=0.7:0.65:90:0.28[s1];"
        f"[1]volume=0.07,aecho=0.6:0.55:140:0.18[s2];"
        f"[2]volume=0.05[s3];[s1][s2][s3]amix=inputs=3:duration=longest[mix];"
        "[mix]equalizer=f=200:t=q:w=1:g=+4,equalizer=f=4000:t=q:w=1:g=-6,"
        f"afade=t=in:d=4,afade=t=out:st={max(0,dur-6)}:d=6,"
        "loudnorm=I=-24:TP=-3:LRA=8[out]")
    subprocess.run(["ffmpeg","-y","-loglevel","error",
                    "-f","lavfi","-i",f"sine=frequency={f1}:duration={dur}",
                    "-f","lavfi","-i",f"sine=frequency={f2}:duration={dur}",
                    "-f","lavfi","-i",f"sine=frequency={f3}:duration={dur}",
                    "-filter_complex",fc,"-map","[out]","-ar","44100","-b:a","128k",str(out)],
                   capture_output=True)
    return str(out)


# ══════════════════════════════════════════════════════════════════════
# STEP 7 — SEO
# ══════════════════════════════════════════════════════════════════════
SEO_PROMPT = """Thulir YouTube channel Tamil motivational video metadata.
Almost Everything style — real story content.

Story: {story_title}
Character: {protagonist} (age {protagonist_age})
Hook: {hook_question}
Lesson: {lesson}
Category: {story_category}
Script preview: {preview}

Return ONLY valid JSON:
{{"title_ta":"<Tamil title 58 chars max — emotional + real story angle>",
"description":"<500 char Tamil — hook line 1-2 + 3 story moments + what viewer learns + hashtags #துளிர் #TamilMotivation #RealStory>",
"tags":["துளிர்","Tamil motivation","real story Tamil","motivational Tamil","life skills Tamil","Tamil YouTube","inspiring Tamil","true story Tamil","Tamil short film style","{story_category} Tamil","{protagonist} story","{lesson}"],
"pinned_comment":"<Two choice Tamil question about the story — forces comment>",
"thumbnail_text":"<5 Tamil words — emotional, story-hook>"}}"""

def generate_seo(topic, scenes, video_type="long"):
    slug  = hashlib.md5((topic["story_title"]+video_type+"seo").encode()).hexdigest()[:8]
    cache = OUT/"cache"/f"seo_{slug}.json"
    if cache.exists(): return json.loads(cache.read_text())
    preview = " ".join(scenes[:2])[:300] if scenes else ""
    try:
        raw = _llm(SEO_PROMPT.format(**topic,preview=preview), max_tokens=1000)
        raw = re.sub(r"```json|```","",raw).strip()
        m   = re.search(r'\{.*\}',raw,re.DOTALL)
        if m: raw=m.group()
        seo = json.loads(raw)
    except Exception as e:
        log.warning(f"SEO failed ({e})")
        seo={"title_ta":topic["story_title"][:58],
             "description":f"{topic['hook_question']}\n\nதுளிர் channel-ல் {topic['protagonist']}-ன் real story.\n#துளிர் #TamilMotivation",
             "tags":["துளிர்","Tamil motivation","real story Tamil","motivational Tamil"],
             "pinned_comment":"இந்த கதையில் உன்னை எந்த moment-ல் பார்த்தாய்? 👇",
             "thumbnail_text":topic["hook_question"][:40]}
    if "துளிர்" not in seo.get("tags",[]): seo["tags"].insert(0,"துளிர்")
    cache.write_text(json.dumps(seo,ensure_ascii=False,indent=2))
    return seo


# ══════════════════════════════════════════════════════════════════════
# STEP 8 — FINAL ASSEMBLY
# ══════════════════════════════════════════════════════════════════════
def assemble(slug, scene_videos, bgm, out_path):
    concat = OUT/"cache"/f"concat_{slug}.txt"
    with open(concat,"w") as f:
        for v in scene_videos:
            f.write(f"file '{Path(v).resolve()}'\n")
    raw = OUT/"cache"/f"raw_{slug}.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                    "-c","copy",str(raw)],capture_output=True,check=True)
    total=_dur(raw)
    fc=(f"[0:a]volume=1.0[v];[1:a]volume=0.07,aloop=loop=-1:size=2e+09,atrim=0:{total:.2f}[bgm];"
        "[v][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
    r=subprocess.run(["ffmpeg","-y","-i",str(raw),"-i",bgm,
                      "-filter_complex",fc,"-map","0:v","-map","[aout]",
                      "-c:v","libx264","-preset","veryfast","-crf","21",
                      "-c:a","aac","-b:a","192k","-pix_fmt","yuv420p",str(out_path)],
                     capture_output=True,text=True,timeout=900)
    raw.unlink(missing_ok=True)
    if r.returncode!=0: raise RuntimeError(f"Assembly failed: {r.stderr[-200:]}")
    log.info(f"✅ {out_path} ({Path(out_path).stat().st_size//1024//1024}MB)")


# ══════════════════════════════════════════════════════════════════════
# STEP 9 — UPLOAD
# ══════════════════════════════════════════════════════════════════════
def upload(video_path, seo, is_shorts=False, retries=3):
    from youtube_uploader import upload_video
    title = seo.get("title_ta","")
    if is_shorts: title = title[:50]+" #Shorts"
    desc = seo.get("description","")
    tags = seo.get("tags",[])[:30]
    for attempt in range(1,retries+1):
        try:
            vid_id = upload_video(video_path=video_path,title=title,
                                  description=desc,tags=tags,
                                  category_id="27",privacy="public")
            if vid_id:
                log.info(f"✅ https://youtu.be/{vid_id}")
                try:
                    from youtube_uploader import post_comment
                    post_comment(vid_id, seo.get("pinned_comment",""))
                except: pass
                return vid_id
        except Exception as e:
            log.error(f"Upload attempt {attempt} failed: {e}")
            if attempt<retries: time.sleep(30*attempt)
    raise RuntimeError("Upload failed")

def save_log(entry):
    records=json.loads(LOG.read_text()) if LOG.exists() else []
    records.append({**entry,"at":time.strftime("%Y-%m-%d %H:%M UTC")})
    LOG.write_text(json.dumps(records[-100:],ensure_ascii=False,indent=2))


# ══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════
def run(topic_override="", do_upload=True):
    results={"long":None,"long_id":None,"shorts":None,"shorts_id":None,"errors":[]}
    errors=results["errors"]

    # 1. Topic
    try:
        if topic_override.strip():
            topic={"story_title":topic_override,"protagonist":"அர்ஜுன்",
                   "protagonist_age":"25","situation":topic_override,
                   "core_problem":topic_override,"emotional_hook":"",
                   "turning_point":"","lesson":"","hook_question":"",
                   "story_category":"motivation"}
        else:
            topic=discover_topic()
        slug=hashlib.md5(topic["story_title"].encode()).hexdigest()[:10]
        log.info(f"\n{'='*60}\nSTORY: {topic['story_title']}\nCHAR: {topic['protagonist']} ({topic['protagonist_age']})\n{'='*60}\n")
    except Exception as e:
        errors.append(f"topic:{e}"); log.error(e); return results

    # 2. Scripts
    try:    long_scenes  = generate_script(topic,"long")
    except Exception as e: errors.append(f"long_script:{e}"); log.error(e); return results
    try:    short_scenes = generate_script(topic,"short")
    except: short_scenes = long_scenes[:3]

    # 3. SEO
    long_seo  = generate_seo(topic,long_scenes,"long")
    short_seo = generate_seo(topic,short_scenes,"short")

    # 4. BGM
    bgm = ensure_bgm(660, topic.get("story_category","motivation"))

    # 5. Long-form render
    long_out = OUT/"video"/f"{slug}_long.mp4"
    if not long_out.exists():
        try:
            scene_vids=[]
            for i,scene in enumerate(long_scenes):
                log.info(f"Long scene {i+1}/{len(long_scenes)}")
                audio,dur,timings = synthesise(scene,i,slug,"audio")
                vid = render_scene_video(scene,i,len(long_scenes),slug,
                                        topic["protagonist"],audio,timings,dur,
                                        OUT/"frames",is_shorts=False)
                scene_vids.append(vid)
            assemble(slug+"_long",scene_vids,bgm,str(long_out))
            results["long"]=str(long_out)
        except Exception as e:
            errors.append(f"long_render:{e}"); log.error(e)
    else:
        results["long"]=str(long_out); log.info("Long: cache hit")

    # 6. Shorts render
    shorts_out = OUT/"shorts"/f"{slug}_shorts.mp4"
    if not shorts_out.exists():
        try:
            s_slug=slug+"s"
            short_vids=[]
            for i,scene in enumerate(short_scenes[:4]):
                log.info(f"Shorts scene {i+1}/{len(short_scenes[:4])}")
                audio,dur,timings = synthesise(scene,i,s_slug,"audio")
                # Compress to fit 60s
                target_dur = 58.0/len(short_scenes[:4])
                vid = render_scene_video(scene,i,len(short_scenes[:4]),s_slug,
                                        topic["protagonist"],audio,timings,
                                        min(dur,target_dur),OUT/"frames",is_shorts=True)
                short_vids.append(vid)
            assemble(slug+"_shorts",short_vids,bgm,str(shorts_out))
            results["shorts"]=str(shorts_out)
        except Exception as e:
            errors.append(f"shorts_render:{e}"); log.warning(e)
    else:
        results["shorts"]=str(shorts_out); log.info("Shorts: cache hit")

    # 7. Upload
    if do_upload:
        if results["long"] and Path(results["long"]).exists():
            try:
                vid_id=upload(results["long"],long_seo,is_shorts=False)
                results["long_id"]=vid_id
                save_log({"type":"long","title":long_seo.get("title_ta",""),
                          "video_id":vid_id,"topic":topic["story_title"]})
            except Exception as e: errors.append(f"long_upload:{e}")

        if results["shorts"] and Path(results["shorts"]).exists():
            try:
                time.sleep(10)
                s_id=upload(results["shorts"],short_seo,is_shorts=True)
                results["shorts_id"]=s_id
                save_log({"type":"shorts","title":short_seo.get("title_ta","")+"#Shorts",
                          "video_id":s_id,"topic":topic["story_title"]})
            except Exception as e: errors.append(f"shorts_upload:{e}")

    log.info(f"\n{'='*60}")
    log.info(f"DONE | Long: {results.get('long_id','not uploaded')} | Shorts: {results.get('shorts_id','not uploaded')}")
    if errors: log.warning(f"Errors: {errors}")
    log.info(f"{'='*60}\n")
    # Exit non-zero if no video was generated
    if not results.get('long') and not results.get('shorts'):
        log.error('❌ No video generated — check errors above')
        sys.exit(1)
    return results


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--topic",default="")
    ap.add_argument("--no-upload",action="store_true")
    ap.add_argument("--list",action="store_true")
    args=ap.parse_args()
    if args.list:
        if LOG.exists():
            for e in json.loads(LOG.read_text())[-10:]:
                print(f"  {e.get('at','')} | {e.get('type','')} | {e.get('video_id','')} | {e.get('title','')[:50]}")
        sys.exit(0)
    run(args.topic, do_upload=not args.no_upload)
