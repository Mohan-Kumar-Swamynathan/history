#!/usr/bin/env python3
"""
Scheduler — Tamil History YouTube Channel
Finds the OPTIMAL daily upload time based on:
  1. Tamil Nadu / Tamil diaspora audience timezone analysis
  2. YouTube algorithm peak engagement windows
  3. Competitor channel upload pattern analysis
  4. Day-of-week multiplier (weekend vs weekday)

Outputs a cron schedule + GitHub Actions schedule expression.
Also rotates topics so no repeat within 30 days.
"""

import json, datetime, random, hashlib
from pathlib import Path
from typing import Dict, List, Tuple

# ─────────────────────────────────────────────────────────────────
# AUDIENCE TIMEZONE MAP — Tamil viewers
# Primary: IST (UTC+5:30)  — Tamil Nadu, Sri Lanka
# Secondary: SGT (UTC+8)   — Singapore Tamil diaspora
# Tertiary:  GMT (UTC+0)   — UK Tamil diaspora
# Quaternary: EST (UTC-5)  — USA/Canada Tamil diaspora
# ─────────────────────────────────────────────────────────────────
AUDIENCE_SEGMENTS = {
    "Tamil Nadu (IST)":      {"tz_offset": 5.5,  "weight": 0.55},
    "Sri Lanka (IST)":       {"tz_offset": 5.5,  "weight": 0.12},
    "Singapore (SGT)":       {"tz_offset": 8.0,  "weight": 0.10},
    "UK Tamil (GMT/BST)":    {"tz_offset": 1.0,  "weight": 0.10},
    "Malaysia Tamil":        {"tz_offset": 8.0,  "weight": 0.07},
    "USA/Canada Tamil":      {"tz_offset": -4.5, "weight": 0.06},
}

# ─────────────────────────────────────────────────────────────────
# PEAK VIEWING WINDOWS (local time, 24h)
# Based on YouTube India analytics patterns for devotional/history content
# ─────────────────────────────────────────────────────────────────
PEAK_WINDOWS = [
    {"name": "Morning commute",    "start": 7.0,  "end": 9.0,  "score": 0.85},
    {"name": "Lunch break",        "start": 12.0, "end": 14.0, "score": 0.72},
    {"name": "Evening prime",      "start": 19.0, "end": 21.5, "score": 1.00},  # best
    {"name": "Night wind-down",    "start": 21.5, "end": 23.5, "score": 0.78},
    {"name": "Late night students","start": 22.0, "end": 24.0, "score": 0.60},
]

# ─────────────────────────────────────────────────────────────────
# DAY-OF-WEEK MULTIPLIERS (0=Mon … 6=Sun)
# Weekends: higher watch time, lower upload competition
# ─────────────────────────────────────────────────────────────────
DOW_MULTIPLIER = {
    0: 0.80,  # Monday    — post-weekend slump
    1: 0.85,  # Tuesday
    2: 0.88,  # Wednesday
    3: 0.90,  # Thursday
    4: 0.92,  # Friday    — weekend start energy
    5: 1.00,  # Saturday  — peak
    6: 0.95,  # Sunday    — high but algo prefers Sat
}
DOW_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# Upload 30 minutes BEFORE peak so YouTube indexes it in time
INDEX_LEAD_MINUTES = 30

STATE_FILE = Path(__file__).parent / "scheduler_state.json"
TOPICS_FILE = Path(__file__).parent / "topic_rotation.json"


def score_upload_hour(utc_hour: float) -> float:
    """
    For a given UTC hour, compute weighted score across all audience segments
    by checking if that UTC time falls in a peak viewing window locally.
    """
    total_score = 0.0
    for segment, info in AUDIENCE_SEGMENTS.items():
        local_hour = (utc_hour + info["tz_offset"]) % 24
        seg_score  = 0.0
        for window in PEAK_WINDOWS:
            # Handle windows that cross midnight
            s, e = window["start"], window["end"]
            if s <= local_hour < e:
                # Higher score if near the middle of the window
                mid        = (s + e) / 2
                proximity  = 1.0 - abs(local_hour - mid) / ((e - s) / 2)
                seg_score  = max(seg_score, window["score"] * proximity)
        total_score += seg_score * info["weight"]
    return total_score


def find_optimal_schedule() -> Dict:
    """
    Score every 15-minute UTC slot and return the best upload time
    plus a 7-day schedule with day-specific adjustments.
    """
    best_score = 0.0
    best_utc   = 14.5  # fallback: 14:30 UTC = 20:00 IST

    scores = {}
    for slot in range(0, 96):   # 96 x 15-min slots = 24 hours
        utc_h = slot * 0.25
        s     = score_upload_hour(utc_h)
        scores[utc_h] = s
        if s > best_score:
            best_score = s
            best_utc   = utc_h

    # Convert to IST for display
    best_ist    = (best_utc + 5.5) % 24
    upload_utc  = best_utc - (INDEX_LEAD_MINUTES / 60)  # 30 min early
    if upload_utc < 0:
        upload_utc += 24

    # Build 7-day schedule (slight time variation per day for algo diversity)
    weekly = []
    for dow in range(7):
        # On high-multiplier days, stay at prime time; low days shift 15 min earlier
        adj        = (1.0 - DOW_MULTIPLIER[dow]) * (-0.5)   # -0 to -0.1 hours
        day_utc    = (upload_utc + adj) % 24
        day_ist    = (day_utc + 5.5) % 24
        h, m       = int(day_ist), int((day_ist % 1) * 60)
        hu, mu     = int(day_utc), int((day_utc % 1) * 60)
        weekly.append({
            "day"         : DOW_NAMES[dow],
            "dow"         : dow,
            "multiplier"  : DOW_MULTIPLIER[dow],
            "upload_ist"  : f"{h:02d}:{m:02d}",
            "upload_utc"  : f"{hu:02d}:{mu:02d}",
            "cron_utc"    : f"{mu} {hu} * * {dow}",
        })

    # Best day for a "hero" upload
    best_day = max(weekly, key=lambda x: x["multiplier"])

    return {
        "optimal_utc"     : f"{int(upload_utc):02d}:{int((upload_utc%1)*60):02d}",
        "optimal_ist"     : f"{int(best_ist):02d}:{int((best_ist%1)*60):02d}",
        "peak_score"      : round(best_score, 3),
        "weekly_schedule" : weekly,
        "best_day"        : best_day["day"],
        "github_cron"     : best_day["cron_utc"],   # best single day cron
        "daily_cron"      : f"{int((upload_utc%1)*60)} {int(upload_utc)} * * *",
        "analysis"        : {
            "primary_audience" : "Tamil Nadu IST viewers (55%)",
            "peak_window"      : "19:00–21:30 IST",
            "index_lead"       : f"{INDEX_LEAD_MINUTES} min before peak",
            "recommendation"   : f"Upload daily at {int(best_ist):02d}:{int((best_ist%1)*60):02d} IST = {int(upload_utc):02d}:{int((upload_utc%1)*60):02d} UTC",
        }
    }


# ─────────────────────────────────────────────────────────────────
# TOPIC ROTATION — prevents repeating topics within 30 days
# ─────────────────────────────────────────────────────────────────
FULL_TOPIC_BANK = [
    {"topic": "சோழர்களின் கடல் பயணங்கள்",           "era": "சோழர் காலம்",       "hook": "mystery"},
    {"topic": "பல்லவர்களின் மாமல்லபுரம் கட்டிடக்கலை","era": "பல்லவர் காலம்",     "hook": "architecture"},
    {"topic": "வேலூர் சிப்பாய் கலகம் 1806",           "era": "ஆங்கிலேயர் காலம்",  "hook": "rebellion"},
    {"topic": "கம்பராமாயணம் எழுதப்பட்ட கதை",          "era": "இடைக்காலம்",        "hook": "literature"},
    {"topic": "சங்க காலத் தமிழ் வணிகம்",              "era": "சங்க காலம்",        "hook": "trade"},
    {"topic": "மதுரை மீனாட்சி அம்மன் கோயில் வரலாறு",  "era": "பாண்டிய காலம்",     "hook": "temple"},
    {"topic": "ஒல்லாந்தர் தமிழ்நாட்டில்",             "era": "காலனி காலம்",       "hook": "conflict"},
    {"topic": "திருவள்ளுவர் யார்?",                   "era": "சங்க காலம்",        "hook": "mystery"},
    {"topic": "விஜயநகர பேரரசும் தமிழகமும்",           "era": "விஜயநகர காலம்",    "hook": "empire"},
    {"topic": "1943 வங்காள பஞ்சமும் தமிழர்களும்",     "era": "ஆங்கிலேயர் காலம்", "hook": "tragedy"},
    {"topic": "தமிழ் சிலப்பதிகாரம் — கண்ணகி கதை",    "era": "சங்க காலம்",        "hook": "emotion"},
    {"topic": "மராட்டியர் தமிழ்நாட்டில் ஆட்சி",       "era": "மராட்டிய காலம்",    "hook": "empire"},
    {"topic": "போர்ச்சுகீசியர் மற்றும் தமிழர்கள்",   "era": "காலனி காலம்",       "hook": "conflict"},
    {"topic": "திருநெல்வேலி பாளையக்காரர் கதைகள்",     "era": "ஆங்கிலேயர் காலம்", "hook": "rebellion"},
    {"topic": "கரிகால் சோழனின் காவிரி கட்டுமானம்",    "era": "சோழர் காலம்",       "hook": "engineering"},
    {"topic": "சேர மன்னர்களும் கேரளமும்",              "era": "சங்க காலம்",        "hook": "mystery"},
    {"topic": "தமிழ் நாவலர்கள் வரலாறு",               "era": "நவீன காலம்",        "hook": "literature"},
    {"topic": "பாண்டிய மன்னன் நெடுஞ்செழியன்",         "era": "சங்க காலம்",        "hook": "empire"},
    {"topic": "ஆழ்வார்கள் வாழ்க்கை வரலாறு",           "era": "பக்தி இயக்க காலம்", "hook": "emotion"},
    {"topic": "1857 சிப்பாய் கலகமும் தமிழரும்",       "era": "ஆங்கிலேயர் காலம்", "hook": "rebellion"},
    {"topic": "தஞ்சாவூர் பிரகதீஸ்வரர் கோயில் ரகசியம்","era": "சோழர் காலம்",      "hook": "mystery"},
    {"topic": "திரிகூட மலை பிள்ளையார் கோயில் கதை",    "era": "பல்லவர் காலம்",     "hook": "temple"},
    {"topic": "ஊர்வசி — தெய்வீக நடனத்தின் வரலாறு",   "era": "பண்டைய காலம்",     "hook": "culture"},
    {"topic": "மைசூர் படை தமிழ் நாட்டை ஆண்ட காலம்",  "era": "மைசூர் காலம்",     "hook": "conflict"},
    {"topic": "தமிழ் எழுத்தின் தோற்றம்",              "era": "பண்டைய காலம்",     "hook": "mystery"},
    {"topic": "நாயக்கர் காலத்து மதுரை",               "era": "நாயக்கர் காலம்",    "hook": "empire"},
    {"topic": "சுப்பிரமணிய பாரதியின் வாழ்க்கை",      "era": "நவீன காலம்",        "hook": "emotion"},
    {"topic": "கப்பல் ஓட்டிய தமிழர்கள்",              "era": "சோழர் காலம்",       "hook": "trade"},
    {"topic": "ஆங்கில ஆட்சியில் தமிழ் உணவுப் பஞ்சம்", "era": "ஆங்கிலேயர் காலம்", "hook": "tragedy"},
    {"topic": "வரலாற்று பூம்புகார் நகரம்",             "era": "சங்க காலம்",        "hook": "mystery"},
]


def load_rotation_state() -> Dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text("utf-8"))
    return {"used_indices": [], "used_topics": [], "last_run": None, "total_runs": 0}


def save_rotation_state(state: Dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def get_static_topic() -> Dict:
    """Pick from hardcoded bank — never repeats within 30 days."""
    state = load_rotation_state()
    used  = state.get("used_indices", [])

    if len(used) >= len(FULL_TOPIC_BANK):
        used = []

    available = [i for i in range(len(FULL_TOPIC_BANK)) if i not in used[-30:]]
    if not available:
        available = list(range(len(FULL_TOPIC_BANK)))

    recent  = set(used[-7:])
    weights = [0.2 if i in recent else 1.0 for i in available]
    total_w = sum(weights)
    probs   = [w / total_w for w in weights]

    r     = random.random()
    cumul = 0.0
    idx   = available[0]
    for i, (av_i, p) in enumerate(zip(available, probs)):
        cumul += p
        if r <= cumul:
            idx = av_i
            break

    topic = FULL_TOPIC_BANK[idx].copy()
    topic["_rotation_idx"] = idx
    topic["source"] = "static_bank"

    state["used_indices"].append(idx)
    state.setdefault("used_topics", []).append(topic["topic"])
    state["used_topics"] = state["used_topics"][-30:]
    state["last_topic"] = topic["topic"]
    state["last_topic_source"] = "static_bank"
    state["last_run"] = datetime.datetime.utcnow().isoformat()
    state["total_runs"] = state.get("total_runs", 0) + 1
    save_rotation_state(state)
    return topic


def get_discovered_topic() -> Dict:
    """Discover today's trending Tamil history topic from Wikipedia, news, and LLM."""
    from topic_discovery import pick_trending_topic

    state = load_rotation_state()
    used_topics = state.get("used_topics", [])[-30:]
    topic = pick_trending_topic(used_topics)

    state.setdefault("used_topics", []).append(topic["topic"])
    state["used_topics"] = state["used_topics"][-30:]
    state["last_topic"] = topic["topic"]
    state["last_topic_source"] = topic.get("source", "llm_generated")
    state["last_run"] = datetime.datetime.utcnow().isoformat()
    state["total_runs"] = state.get("total_runs", 0) + 1
    save_rotation_state(state)
    return topic


def get_todays_topic(use_static: bool = False) -> Dict:
    """Default: discover trending topic. Pass use_static=True for hardcoded bank rotation."""
    if use_static:
        return get_static_topic()
    return get_discovered_topic()


def print_schedule_report(schedule: Dict):
    print("\n" + "═"*60)
    print("📅  OPTIMAL UPLOAD SCHEDULE — Tamil History Channel")
    print("═"*60)
    print(f"\n🎯  Best upload time : {schedule['optimal_ist']} IST  ({schedule['optimal_utc']} UTC)")
    print(f"📊  Audience score   : {schedule['peak_score']}")
    print(f"⭐  Best day         : {schedule['best_day']}")
    print(f"\n🕐  IST Peak Window  : {schedule['analysis']['peak_window']}")
    print(f"💡  Strategy         : {schedule['analysis']['recommendation']}")
    print(f"\n⏰  GitHub Actions cron (daily): {schedule['daily_cron']}")
    print(f"\n📆  Weekly Schedule:")
    for d in schedule["weekly_schedule"]:
        bar = "█" * int(d["multiplier"] * 10)
        print(f"   {d['day']:<12} {d['upload_ist']} IST  {bar}")
    print("\n" + "═"*60)


if __name__ == "__main__":
    schedule = find_optimal_schedule()
    print_schedule_report(schedule)
    # Save schedule for bot to read
    out = Path(__file__).parent / "optimal_schedule.json"
    out.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), "utf-8")
    print(f"\nSchedule saved: {out}")

    topic = get_discovered_topic()
    print(f"\nToday's topic: {topic['topic']}  (source: {topic.get('source', 'unknown')})")
