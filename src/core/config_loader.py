"""Load YAML configuration files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


@lru_cache(maxsize=1)
def load_platform_config() -> Dict[str, Any]:
    return _load_yaml("platform.yml")


@lru_cache(maxsize=1)
def load_topics_config() -> Dict[str, Any]:
    return _load_yaml("topics.yml")


@lru_cache(maxsize=1)
def load_emotions_config() -> Dict[str, Any]:
    return _load_yaml("emotions.yml")


@lru_cache(maxsize=1)
def load_voice_config() -> Dict[str, Any]:
    return _load_yaml("voice.yml")


@lru_cache(maxsize=1)
def load_scenes_config() -> Dict[str, Any]:
    return _load_yaml("scenes.yml")


def get_output_dir() -> Path:
    platform = load_platform_config()
    output_dir = PROJECT_ROOT / platform.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def resolve_font_path(font_key: str) -> str:
    from src.core.font_resolver import get_latin_font_path, get_tamil_font_path

    if font_key.startswith("ta"):
        try:
            return get_tamil_font_path()
        except FileNotFoundError:
            pass
    else:
        try:
            return get_latin_font_path()
        except FileNotFoundError:
            pass

    platform = load_platform_config()
    fonts = platform.get("fonts", {})
    candidates = [
        fonts.get(font_key, ""),
        fonts.get(f"linux_{font_key}", ""),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _load_yaml(filename: str) -> Dict[str, Any]:
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
