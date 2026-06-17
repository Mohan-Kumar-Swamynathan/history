"""LLM usage policy — reduce calls and rate-limit pressure in CI."""

from __future__ import annotations

import os

LLM_MODE = os.environ.get("LLM_MODE", "auto").lower()

# Stages that may call an LLM
STAGE_TOPIC = "topic"
STAGE_RESEARCH = "research"
STAGE_LONG_SCRIPT = "long_script"
STAGE_SHORTS_SCRIPT = "shorts_script"
STAGE_METADATA = "metadata"

_MINIMAL_OFFLINE_STAGES = frozenset({
    STAGE_TOPIC,
    STAGE_RESEARCH,
    STAGE_SHORTS_SCRIPT,
    STAGE_METADATA,
})


def resolve_llm_mode() -> str:
    if LLM_MODE in {"offline", "minimal", "full"}:
        return LLM_MODE
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "minimal"
    return "auto"


def should_use_llm(stage: str) -> bool:
    mode = resolve_llm_mode()
    if mode == "offline":
        return False
    if mode == "minimal":
        return stage == STAGE_LONG_SCRIPT
    return True


def topic_candidate_count(default: int = 20) -> int:
    mode = resolve_llm_mode()
    if mode in {"minimal", "offline"}:
        return 0
    if mode == "auto":
        return min(default, 8)
    return default
