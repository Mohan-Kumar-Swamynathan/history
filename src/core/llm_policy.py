"""LLM usage policy — efficient hybrid mode with minimal redundant calls."""

from __future__ import annotations

import os

from src.core.llm_registry import log_execution_plan, preferred_provider

STAGE_TOPIC = "topic"
STAGE_RESEARCH = "research"
STAGE_LONG_SCRIPT = "long_script"
STAGE_SHORTS_SCRIPT = "shorts_script"
STAGE_METADATA = "metadata"

# hybrid: topic + long script only (shorts derived from long — no extra LLM call)
HYBRID_LLM_STAGES = frozenset({STAGE_TOPIC, STAGE_LONG_SCRIPT})

STAGE_MAX_TOKENS = {
    STAGE_TOPIC: 1500,
    STAGE_RESEARCH: 800,
    STAGE_LONG_SCRIPT: 8000,
    STAGE_SHORTS_SCRIPT: 1200,
    STAGE_METADATA: 1000,
}


def resolve_llm_mode() -> str:
    mode = os.environ.get("LLM_MODE", "auto").lower()
    if mode in {"offline", "minimal", "hybrid", "full", "auto"}:
        return mode
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "hybrid"
    return "auto"


def should_use_llm(stage: str) -> bool:
    mode = resolve_llm_mode()
    if mode in {"offline", "minimal"}:
        return False
    if mode == "hybrid":
        return stage in HYBRID_LLM_STAGES
    return True


def should_derive_shorts_from_long() -> bool:
    """In hybrid mode, compress long-script beats instead of a separate LLM call."""
    return resolve_llm_mode() == "hybrid"


def topic_candidate_count(default: int = 20) -> int:
    mode = resolve_llm_mode()
    if mode in {"minimal", "offline"}:
        return 0
    if mode == "hybrid":
        return 5
    if mode == "auto":
        return min(default, 8)
    return default


def max_tokens_for_stage(stage: str, fallback: int = 4096) -> int:
    return STAGE_MAX_TOKENS.get(stage, fallback)


def active_llm_stages() -> list[str]:
    stage_order = [STAGE_TOPIC, STAGE_LONG_SCRIPT]
    return [stage for stage in stage_order if should_use_llm(stage)]


def preferred_provider_for_stage(stage: str) -> str | None:
    if not should_use_llm(stage):
        return None
    return preferred_provider()


def log_pipeline_llm_plan() -> None:
    log_execution_plan(resolve_llm_mode(), active_llm_stages())
