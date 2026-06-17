"""Enforce free-only pipeline — no paid API dependencies."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

BLOCKED_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ELEVENLABS_API_KEY",
    "STABILITY_API_KEY",
    "REPLICATE_API_TOKEN",
    "PEXELS_API_KEY",
)

BLOCKED_IMPORTS = (
    "openai",
    "elevenlabs",
    "stability_sdk",
)


def validate_free_only_mode() -> None:
    """Raise if paid API keys are set while free_only is enabled."""
    from src.core.config_loader import load_platform_config

    platform = load_platform_config()
    if not platform.get("free_only", True):
        log.warning("free_only is disabled — paid APIs may be used")
        return

    for key in BLOCKED_ENV_KEYS:
        if os.environ.get(key):
            raise RuntimeError(
                f"free_only mode: remove {key} from environment. "
                "This platform uses only free tools (Edge TTS, procedural visuals)."
            )

    log.info("free_guard: validated free-only mode")
