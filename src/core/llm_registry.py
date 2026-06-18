"""Session-level LLM provider health and execution planning."""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Set

log = logging.getLogger(__name__)

_EXHAUSTED_PROVIDERS: Set[str] = set()


def mark_provider_exhausted(provider_name: str) -> None:
    _EXHAUSTED_PROVIDERS.add(provider_name.lower())
    log.info("LLM provider marked unavailable for this run: %s", provider_name)


def is_provider_available(provider_name: str) -> bool:
    normalized = provider_name.lower()
    if normalized in _EXHAUSTED_PROVIDERS:
        return False
    skip_list = {
        item.strip().lower()
        for item in os.environ.get("LLM_SKIP_PROVIDERS", "").split(",")
        if item.strip()
    }
    return normalized not in skip_list


def reset_provider_registry() -> None:
    _EXHAUSTED_PROVIDERS.clear()


def has_provider_credential(provider_name: str) -> bool:
    normalized = provider_name.lower()
    if normalized == "gemini":
        return bool(os.environ.get("GEMINI_KEY"))
    if normalized == "groq":
        return bool(os.environ.get("GROQ_API_KEY"))
    if normalized == "github":
        return bool(os.environ.get("GITHUB_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    return False


def resolve_ci_strategy() -> str:
    configured = os.environ.get("LLM_CI_STRATEGY", "").lower().strip()
    if configured:
        return configured
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "github_first"
    return "full_chain"


def resolve_provider_order(preferred: Optional[str] = None) -> List[str]:
    strategy = resolve_ci_strategy()
    if strategy == "offline":
        return []

    if strategy == "github_first":
        base_order = ["github", "gemini", "groq"]
    elif strategy == "gemini_first":
        base_order = ["gemini", "groq", "github"]
    else:
        base_order = ["gemini", "groq", "github"]

    available_order = [
        provider
        for provider in base_order
        if has_provider_credential(provider) and is_provider_available(provider)
    ]

    if preferred and preferred in available_order:
        return [preferred] + [provider for provider in available_order if provider != preferred]
    return available_order


def preferred_provider() -> Optional[str]:
    order = resolve_provider_order()
    return order[0] if order else None


def log_execution_plan(llm_mode: str, llm_stages: List[str]) -> None:
    order = resolve_provider_order()
    exhausted = sorted(_EXHAUSTED_PROVIDERS)
    log.info(
        "LLM execution plan — mode=%s strategy=%s stages=%s provider_order=%s exhausted=%s",
        llm_mode,
        resolve_ci_strategy(),
        llm_stages or ["none"],
        order or ["offline"],
        exhausted or ["none"],
    )
