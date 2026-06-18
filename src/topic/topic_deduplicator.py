"""Cross-run topic deduplication — avoid repeating stories."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Set

from src.core.config_loader import CONFIG_DIR, get_output_dir, load_topics_config
from src.core.models import TopicCandidate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACKED_HISTORY = PROJECT_ROOT / "data" / "topic_history.json"
RUNTIME_HISTORY = get_output_dir() / "state" / "topic_history.json"
UPLOAD_STATE = PROJECT_ROOT / "upload_state.json"


class TopicDeduplicator:
    def load_used_titles(self) -> List[str]:
        return sorted(self._collect_used_titles())

    def load_used_protagonists(self) -> List[str]:
        return sorted(self._collect_used_protagonists())

    def is_duplicate(self, candidate: TopicCandidate) -> bool:
        used_titles = {title.lower() for title in self._collect_used_titles()}
        used_protagonists = {name.lower() for name in self._collect_used_protagonists()}

        if candidate.title_ta.lower() in used_titles:
            return True

        protagonist_key = candidate.protagonist.strip().lower()
        if protagonist_key and protagonist_key in used_protagonists:
            return True

        fingerprint = self._fingerprint(candidate.title_ta)
        if fingerprint in self._collect_fingerprints():
            return True

        return False

    def record_topic(self, topic: TopicCandidate) -> None:
        entry = {
            "title_ta": topic.title_ta,
            "protagonist": topic.protagonist,
            "content_bucket": topic.content_bucket.value,
            "fingerprint": self._fingerprint(topic.title_ta),
        }
        history = self._read_history_file(TRACKED_HISTORY)
        history.append(entry)
        history = self._trim_history(history)
        TRACKED_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        TRACKED_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

        RUNTIME_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def recent_avoid_list(self, limit: int = 20) -> str:
        titles = self.load_used_titles()[-limit:]
        protagonists = self.load_used_protagonists()[-limit:]
        lines = [f"- {title}" for title in titles]
        lines += [f"- protagonist: {name}" for name in protagonists if name]
        return "\n".join(lines) if lines else "(none yet)"

    def _collect_used_titles(self) -> Set[str]:
        titles: Set[str] = set()
        for history in (self._read_history_file(TRACKED_HISTORY), self._read_history_file(RUNTIME_HISTORY)):
            for entry in history:
                if entry.get("title_ta"):
                    titles.add(entry["title_ta"])
        if UPLOAD_STATE.exists():
            state = json.loads(UPLOAD_STATE.read_text(encoding="utf-8"))
            for upload in state.get("uploads", []):
                if upload.get("topic"):
                    titles.add(upload["topic"])
                if upload.get("title"):
                    titles.add(upload["title"])
        return titles

    def _collect_used_protagonists(self) -> Set[str]:
        names: Set[str] = set()
        for history in (self._read_history_file(TRACKED_HISTORY), self._read_history_file(RUNTIME_HISTORY)):
            for entry in history:
                if entry.get("protagonist"):
                    names.add(entry["protagonist"])
        return names

    def _collect_fingerprints(self) -> Set[str]:
        fingerprints: Set[str] = set()
        for history in (self._read_history_file(TRACKED_HISTORY), self._read_history_file(RUNTIME_HISTORY)):
            for entry in history:
                if entry.get("fingerprint"):
                    fingerprints.add(entry["fingerprint"])
                elif entry.get("title_ta"):
                    fingerprints.add(self._fingerprint(entry["title_ta"]))
        return fingerprints

    def _read_history_file(self, path: Path) -> List[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _trim_history(self, history: List[dict]) -> List[dict]:
        dedup_days = int(load_topics_config().get("dedup_days", 30))
        return history[-dedup_days * 2 :]

    def _fingerprint(self, title: str) -> str:
        normalized = re.sub(r"\s+", " ", title.lower())
        normalized = re.sub(r"[^\w\s]", "", normalized)
        words = normalized.split()[:6]
        return " ".join(words)
