"""
Keyword extractor — scans narration and returns structured data:
  locations, dates, numbers, figures, and visual keywords.
"""
import re
from typing import Dict, List, Tuple

# ── Visual keyword → icon/visual type ────────────────────────────────
KEYWORD_VISUALS = {
    # War & Conflict
    "war":"sword","battle":"sword","army":"soldier","soldier":"soldier",
    "weapon":"sword","fight":"sword","attack":"sword","siege":"sword",
    "revolution":"fire","rebellion":"fire","uprising":"fire",
    # People & Power
    "king":"crown","queen":"crown","emperor":"crown","emperor":"crown",
    "leader":"crown","general":"soldier","chief":"crown",
    "president":"crown","minister":"crown",
    # Geography
    "india":"map_pin","china":"map_pin","rome":"map_pin",
    "britain":"map_pin","france":"map_pin","russia":"map_pin",
    "egypt":"map_pin","america":"map_pin","europe":"map_pin",
    "city":"map_pin","country":"map_pin","capital":"map_pin",
    "fort":"castle","castle":"castle","palace":"castle","temple":"temple",
    # Economy
    "gold":"coins","silver":"coins","trade":"coins","money":"coins",
    "tax":"coins","wealth":"coins","rich":"coins","poor":"coins",
    # Nature & Disaster
    "fire":"fire","flood":"wave","earthquake":"wave","volcano":"fire",
    "drought":"sun","storm":"wave","disease":"skull","plague":"skull",
    # Religion & Culture
    "religion":"star","temple":"star","church":"star","mosque":"star",
    "god":"star","worship":"star","festival":"star",
    # Ships & Exploration
    "ship":"ship","fleet":"ship","navy":"ship","ocean":"ship",
    "sea":"ship","voyage":"ship","explorer":"compass","discovery":"compass",
    # Death & Victory
    "death":"skull","killed":"skull","died":"skull","massacre":"skull",
    "victory":"trophy","won":"trophy","defeat":"skull","lost":"skull",
    # Numbers (handled separately)
}

# Tamil keyword map
TAMIL_KEYWORDS = {
    "யுத்தம்":"sword","போர்":"sword","படை":"soldier","அரசன்":"crown",
    "ராணி":"crown","பேரரசர்":"crown","தங்கம்":"coins","பணம்":"coins",
    "கோட்டை":"castle","கோயில்":"temple","மரணம்":"skull","வெற்றி":"trophy",
    "கப்பல்":"ship","தீ":"fire","வெள்ளம்":"wave","நிலம்":"map_pin",
}

LOCATION_PATTERNS = [
    r'\b(India|China|Rome|Britain|France|Russia|Egypt|America|Europe|Africa|Asia)\b',
    r'\b(Delhi|Mumbai|Chennai|Kolkata|Madurai|Thanjavur|Mysore|Vijayanagara)\b',
    r'\b(London|Paris|Moscow|Beijing|Tokyo|Cairo|Baghdad|Constantinople)\b',
    r'\bதமிழ்நாடு\b|\bஆந்திரா\b|\bகேரளா\b|\bகர்நாடகா\b',
    r'\bதஞ்சாவூர்\b|\bமதுரை\b|\bகாஞ்சி\b|\bதில்லி\b',
]

DATE_PATTERNS = [
    r'\b(\d{1,4})\s*(BC|AD|CE|BCE)\b',
    r'\b(1[0-9]{3}|20[0-2][0-9])\b',  # years 1000-2029
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b',
    r'\b\d{1,2}\s+(ஜனவரி|பிப்ரவரி|மார்ச்|ஏப்ரல்|மே|ஜூன்|ஜூலை|ஆகஸ்ட்|செப்டம்பர்|அக்டோபர்|நவம்பர்|டிசம்பர்)\b',
]

NUMBER_PATTERNS = [
    r'\b(\d[\d,]*)\s*(soldiers?|ships?|people|deaths?|armies|troops|millions?|thousands?|crores?|lakhs?)\b',
    r'\b(\d[\d,]*)\s*(soldiers?|ships?|people|deaths?)\b',
    r'\b([\d.]+)\s*(million|billion|trillion|crore|lakh|thousand)\b',
]


def extract(text: str) -> Dict:
    """Return structured extraction from narration text."""
    words = text.lower().split()
    result = {
        "keywords"  : [],   # [(word, icon_type)]
        "locations" : [],   # [place_name]
        "dates"     : [],   # [date_string]
        "numbers"   : [],   # [(number, unit)]
        "visual_cues": [],  # ordered list for storyboard
    }

    # Keywords
    for word in words:
        clean = re.sub(r'[^a-zஃ-்]', '', word)
        if clean in KEYWORD_VISUALS:
            result["keywords"].append((word, KEYWORD_VISUALS[clean]))
        if clean in TAMIL_KEYWORDS:
            result["keywords"].append((word, TAMIL_KEYWORDS[clean]))

    # Locations
    for pat in LOCATION_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            loc = m.group().strip()
            if loc not in result["locations"]:
                result["locations"].append(loc)

    # Dates
    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            d = m.group().strip()
            if d not in result["dates"]:
                result["dates"].append(d)

    # Numbers
    for pat in NUMBER_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            result["numbers"].append((m.group(1), m.group(2) if m.lastindex>=2 else ""))

    # Build visual_cues (ordered)
    cues = []
    if result["locations"]: cues.append({"type":"map",      "value":result["locations"][0]})
    if result["dates"]:     cues.append({"type":"timeline",  "value":result["dates"][0]})
    if result["numbers"]:   cues.append({"type":"stat",      "value":result["numbers"][0]})
    for kw, icon in result["keywords"][:3]:
        cues.append({"type":"icon","value":icon,"word":kw})
    result["visual_cues"] = cues
    return result
