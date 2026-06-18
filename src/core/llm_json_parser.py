"""Robust JSON extraction from LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, List


def extract_json_array(raw: str) -> List[dict]:
    cleaned = _strip_markdown_fences(raw)
    for payload in _candidate_payloads(cleaned):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            repaired = _repair_json(payload)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                continue
        items = _coerce_to_dict_list(parsed)
        if items:
            return items

    scanned = _scan_json_objects(cleaned)
    if scanned:
        return scanned
    return []


def extract_json_object(raw: str) -> dict | None:
    cleaned = _strip_markdown_fences(raw)
    for payload in _candidate_payloads(cleaned):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            repaired = _repair_json(payload)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
    objects = _scan_json_objects(cleaned)
    return objects[0] if objects else None


def _coerce_to_dict_list(parsed: Any) -> List[dict]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("topics", "candidates", "items", "results", "data"):
            nested = parsed.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        if _looks_like_topic_object(parsed):
            return [parsed]
    return []


def _looks_like_topic_object(data: dict) -> bool:
    return bool(data.get("title_ta") or data.get("story_title") or data.get("protagonist"))


def _candidate_payloads(cleaned: str) -> List[str]:
    payloads: List[str] = []
    payloads.append(cleaned.strip())

    array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if array_match:
        payloads.append(array_match.group())

    object_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if object_match:
        payloads.append(object_match.group())

    return list(dict.fromkeys(payloads))


def _repair_json(payload: str) -> str:
    repaired = payload.strip()
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
    repaired = repaired.replace("'", '"')
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    return repaired


def _scan_json_objects(text: str) -> List[dict]:
    decoder = json.JSONDecoder()
    objects: List[dict] = []
    index = 0
    while index < len(text):
        start_array = text.find("[", index)
        start_object = text.find("{", index)
        if start_array == -1 and start_object == -1:
            break
        if start_array != -1 and (start_object == -1 or start_array < start_object):
            start = start_array
        else:
            start = start_object
        try:
            parsed, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        objects.extend(_coerce_to_dict_list(parsed))
        index = end
    return objects


def _strip_markdown_fences(raw: str) -> str:
    cleaned = raw.strip()
    if "```" not in cleaned:
        return cleaned
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return cleaned.replace("```json", "").replace("```", "").strip()
