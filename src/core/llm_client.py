"""LLM client — Gemini primary, Groq secondary, GitHub Models fallback."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_MODELS_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

GEMINI_MODEL = "gemini-2.0-flash"
GITHUB_MODEL = "openai/gpt-4.1"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3


def has_llm_credentials() -> bool:
    return bool(GEMINI_KEY or GITHUB_TOKEN or GROQ_API_KEY)


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _call_gemini(prompt: str, max_tokens: int) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.8},
    }
    data = _http_post_json(url, payload, {"Content-Type": "application/json"})
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_github_models(prompt: str, max_tokens: int) -> str:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set")
    url = "https://models.github.ai/inference/chat/completions"
    payload = {
        "model": GITHUB_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = _http_post_json(url, payload, headers)
    return data["choices"][0]["message"]["content"]


def _call_groq(prompt: str, max_tokens: int) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }
    data = _http_post_json(url, payload, headers)
    return data["choices"][0]["message"]["content"]


def _retry_provider(name: str, call_fn: Callable[[], str]) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            result = call_fn()
            log.info("LLM response from %s", name)
            return result
        except Exception as exc:
            last_error = exc
            log.warning("%s attempt %d/%d: %s", name, attempt + 1, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{name} failed after {MAX_RETRIES} attempts: {last_error}")


def _build_provider_chain(preferred: Optional[str] = None) -> List[Tuple[str, Callable[[str, int], str]]]:
    all_providers = [
        ("gemini", _call_gemini),
        ("groq", _call_groq),
        ("github", _call_github_models),
    ]
    if preferred:
        ordered = [provider for provider in all_providers if provider[0] == preferred]
        ordered += [provider for provider in all_providers if provider[0] != preferred]
        return ordered
    return all_providers


def generate_text(prompt: str, max_tokens: int = 4096, preferred: Optional[str] = None) -> str:
    errors: List[str] = []
    for name, provider_fn in _build_provider_chain(preferred):
        try:
            return _retry_provider(name, lambda fn=provider_fn: fn(prompt, max_tokens))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            log.warning("Provider %s exhausted, trying next...", name)
    raise RuntimeError("All LLM providers failed:\n" + "\n".join(errors))
