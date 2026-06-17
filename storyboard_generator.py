"""
Storyboard generator — converts script into micro-scenes (3-5s each).
Every scene has: narration chunk, visual type, motion effect, duration.
"""
import re, json
from typing import List, Dict
from keyword_extractor import extract

MOTION_EFFECTS = [
    "zoom_in","zoom_out","pan_right","pan_left",
    "zoom_in_slow","pan_up","pan_down","static_slow_zoom",
]

TRANSITION_TYPES = ["cut","fade","wipe_right","zoom_cut"]

def split_into_sentences(text: str) -> List[str]:
    """Split script into sentences — each becomes a micro-scene."""
    # Split on sentence-ending punctuation
    raw = re.split(r'(?<=[.!?।])\s+', text.strip())
    # Further split long sentences at natural pauses (commas, em-dashes)
    out = []
    for sent in raw:
        if len(sent.split()) > 20:
            # Split at comma or dash
            parts = re.split(r',\s+|—\s*|\s+–\s+', sent)
            out.extend([p.strip() for p in parts if p.strip()])
        else:
            if sent.strip():
                out.append(sent.strip())
    return out


def estimate_duration(text: str, wpm: int = 130) -> float:
    """Estimate TTS narration duration in seconds."""
    words = len(text.split())
    return max(2.5, (words / wpm) * 60)


def assign_visual(scene_text: str, scene_idx: int, keywords: Dict, all_dates: List) -> Dict:
    """Assign the best visual type for a scene."""
    cues = keywords.get("visual_cues", [])

    # Priority: stat > map > timeline > icon > image
    visual = {"type": "image", "motion": MOTION_EFFECTS[scene_idx % len(MOTION_EFFECTS)]}

    for cue in cues:
        if cue["type"] == "stat":
            visual = {"type":"stat", "value":cue["value"],
                      "motion":"zoom_in_slow"}
            break
        elif cue["type"] == "map" and cue["value"]:
            visual = {"type":"map", "location":cue["value"],
                      "motion":"pan_right"}
            break
        elif cue["type"] == "timeline" and cue["value"]:
            visual = {"type":"timeline", "date":cue["value"],
                      "all_dates":all_dates,
                      "motion":"zoom_out"}
            break
        elif cue["type"] == "icon":
            visual = {"type":"icon", "icon":cue["value"],
                      "word":cue.get("word",""),
                      "motion":"zoom_in"}
            break

    # Override: always show stat when numbers present
    if keywords.get("numbers") and visual["type"]=="image":
        n, u = keywords["numbers"][0]
        visual = {"type":"stat","value":(n,u),"motion":"zoom_in_slow"}

    # Ensure motion is set
    if "motion" not in visual:
        visual["motion"] = MOTION_EFFECTS[scene_idx % len(MOTION_EFFECTS)]

    visual["transition"] = TRANSITION_TYPES[scene_idx % len(TRANSITION_TYPES)]
    return visual


def build_storyboard(script: str, topic: str) -> List[Dict]:
    """Convert full script into storyboard scenes."""
    sentences = split_into_sentences(script)

    # Extract all dates for timeline context
    full_extract = extract(script)
    all_dates = full_extract.get("dates", [])

    storyboard = []
    cumulative_t = 0.0

    for i, sent in enumerate(sentences):
        kw      = extract(sent)
        dur     = estimate_duration(sent)
        visual  = assign_visual(sent, i, kw, all_dates)

        # Caption: break into ≤4 word chunks
        words   = sent.split()
        caption_lines = []
        chunk = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 4:
                caption_lines.append(" ".join(chunk))
                chunk = []
        if chunk:
            caption_lines.append(" ".join(chunk))

        scene = {
            "scene_id"    : i + 1,
            "timestamp"   : f"{int(cumulative_t//60):02d}:{int(cumulative_t%60):02d}",
            "narration"   : sent,
            "duration"    : round(dur, 2),
            "visual"      : visual,
            "keywords"    : [k[0] for k in kw["keywords"]],
            "locations"   : kw["locations"],
            "dates"       : kw["dates"],
            "numbers"     : kw["numbers"],
            "caption_lines": caption_lines,
            "pattern_interrupt": i % 3 == 0,  # every 3rd scene = hard cut
        }
        storyboard.append(scene)
        cumulative_t += dur

    return storyboard
