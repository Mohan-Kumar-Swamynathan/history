"""Robust JSON extraction from LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, List


def extract_json_array(raw: str) -> List[dict]:
    cleaned = _strip_markdown_fences(raw)
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    payload = match.group()
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        payload = re.sub(r",\s*]", "]", payload)
        payload = re.sub(r",\s*}", "}", payload)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _strip_markdown_fences(raw: str) -> str:
    cleaned = raw.strip()
    if "```" not in cleaned:
        return cleaned
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    return cleaned.replace("```json", "").replace("```", "").strip()
