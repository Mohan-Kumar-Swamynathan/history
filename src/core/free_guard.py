"""Enforce free-only pipeline — no paid API dependencies."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# Pexels is allowed — it has a free tier and key is already in secrets
BLOCKED_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ELEVENLABS_API_KEY",
    "STABILITY_API_KEY",
    "REPLICATE_API_TOKEN",
)

def validate_free_only_mode() -> None:
    from src.core.config_loader import load_platform_config
    platform = load_platform_config()
    if not platform.get("free_only", True):
        return
    for key in BLOCKED_ENV_KEYS:
        if os.environ.get(key):
            raise RuntimeError(
                f"free_only mode: remove {key} from environment."
            )
    log.info("free_guard: validated")
