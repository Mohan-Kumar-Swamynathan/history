"""Daily content scheduling — 2 long + 2 shorts per day."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from src.core.config_loader import get_output_dir

log = logging.getLogger(__name__)

STATE_FILE = get_output_dir() / "state" / "daily_schedule.json"


class DailySlot(str, Enum):
    MORNING_LONG = "morning_long"
    MORNING_SHORT = "morning_short"
    EVENING_LONG = "evening_long"
    EVENING_SHORT = "evening_short"


class ContentScheduler:
    def mark_slot_complete(self, slot: DailySlot, run_id: str) -> None:
        state = self._load_state()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if state.get("date") != today:
            state = {"date": today, "slots": {}}
        state["slots"][slot.value] = {"run_id": run_id, "completed_at": datetime.utcnow().isoformat()}
        self._save_state(state)

    def is_slot_complete(self, slot: DailySlot) -> bool:
        state = self._load_state()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return state.get("date") == today and slot.value in state.get("slots", {})

    def next_pending_slot(self) -> Optional[DailySlot]:
        for slot in DailySlot:
            if not self.is_slot_complete(slot):
                return slot
        return None

    def slots_for_format(self, video_format: str) -> list[DailySlot]:
        if video_format == "short":
            return [DailySlot.MORNING_SHORT, DailySlot.EVENING_SHORT]
        return [DailySlot.MORNING_LONG, DailySlot.EVENING_LONG]

    def _load_state(self) -> dict:
        if not STATE_FILE.exists():
            return {}
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    def _save_state(self, state: dict) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
