"""Optimal upload schedule for Tamil storytelling audience."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class UploadSlot:
    name: str
    cron_utc: str
    ist_label: str
    format: str
    daily_slot: str
    upload: bool = True


AUDIENCE_SEGMENTS = {
    "Tamil Nadu (IST)": {"tz_offset": 5.5, "weight": 0.55},
    "Sri Lanka (IST)": {"tz_offset": 5.5, "weight": 0.12},
    "Singapore (SGT)": {"tz_offset": 8.0, "weight": 0.10},
    "UK Tamil (GMT/BST)": {"tz_offset": 1.0, "weight": 0.10},
    "Malaysia Tamil": {"tz_offset": 8.0, "weight": 0.07},
    "USA/Canada Tamil": {"tz_offset": -4.5, "weight": 0.06},
}

PEAK_WINDOWS = [
    {"start": 7.0, "end": 9.0, "score": 0.85},
    {"start": 12.0, "end": 14.0, "score": 0.72},
    {"start": 19.0, "end": 21.5, "score": 1.00},
    {"start": 21.5, "end": 23.5, "score": 0.78},
]

INDEX_LEAD_MINUTES = 30


def score_upload_hour(utc_hour: float) -> float:
    total_score = 0.0
    for info in AUDIENCE_SEGMENTS.values():
        local_hour = (utc_hour + info["tz_offset"]) % 24
        segment_score = 0.0
        for window in PEAK_WINDOWS:
            start_hour, end_hour = window["start"], window["end"]
            if start_hour <= local_hour < end_hour:
                midpoint = (start_hour + end_hour) / 2
                proximity = 1.0 - abs(local_hour - midpoint) / ((end_hour - start_hour) / 2)
                segment_score = max(segment_score, window["score"] * proximity)
        total_score += segment_score * info["weight"]
    return total_score


def find_optimal_upload_utc() -> Dict[str, str]:
    best_score = 0.0
    best_utc = 14.5
    for slot in range(96):
        utc_hour = slot * 0.25
        slot_score = score_upload_hour(utc_hour)
        if slot_score > best_score:
            best_score = slot_score
            best_utc = utc_hour

    upload_utc = best_utc - (INDEX_LEAD_MINUTES / 60)
    if upload_utc < 0:
        upload_utc += 24

    best_ist = (best_utc + 5.5) % 24
    return {
        "optimal_utc": f"{int(upload_utc):02d}:{int((upload_utc % 1) * 60):02d}",
        "optimal_ist": f"{int(best_ist):02d}:{int((best_ist % 1) * 60):02d}",
        "daily_cron": f"{int((upload_utc % 1) * 60)} {int(upload_utc)} * * *",
        "peak_score": str(round(best_score, 3)),
    }


def build_daily_slots() -> List[UploadSlot]:
    """Morning + evening peaks for 2 long + 2 shorts per day (IST)."""
    return [
        UploadSlot("morning_long", "30 3 * * *", "09:00 IST", "long", "morning_long"),
        UploadSlot("morning_short", "0 4 * * *", "09:30 IST", "short", "morning_short"),
        UploadSlot("evening_long", "0 13 * * *", "18:30 IST", "long", "evening_long", upload=True),
        UploadSlot("evening_short", "30 13 * * *", "19:00 IST", "short", "evening_short"),
    ]


def get_primary_evening_cron() -> str:
    schedule = find_optimal_upload_utc()
    return schedule["daily_cron"]
