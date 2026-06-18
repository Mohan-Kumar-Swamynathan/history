"""LLM client — planned provider chain with session health tracking."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

from src.core.llm_registry import (
    is_provider_available,
    mark_provider_exhausted,
    resolve_provider_order,
)

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
GITHUB_MODEL = "openai/gpt-4.1"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 2


def has_llm_credentials() -> bool:
    return bool(
        os.environ.get("GEMINI_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GITHUB_MODELS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
    )


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"HTTP Error {exc.code}: {detail or exc.reason}") from exc


def _is_rate_or_auth_error(exc: Exception) -> bool:
    message = str(exc)
    return any(code in message for code in ("429", "403", "401", "Too Many Requests", "Forbidden", "1010"))


def _call_gemini(prompt: str, max_tokens: int) -> str:
    gemini_key = os.environ.get("GEMINI_KEY", "")
    if not gemini_key:
        raise RuntimeError("GEMINI_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={gemini_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.8},
    }
    data = _http_post_json(url, payload, {"Content-Type": "application/json"})
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_github_models(prompt: str, max_tokens: int) -> str:
    github_token = os.environ.get("GITHUB_MODELS_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
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
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = _http_post_json(url, payload, headers)
    return data["choices"][0]["message"]["content"]


def _call_groq(prompt: str, max_tokens: int) -> str:
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
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
        "Authorization": f"Bearer {groq_key}",
    }
    data = _http_post_json(url, payload, headers)
    return data["choices"][0]["message"]["content"]


_PROVIDER_CALLERS = {
    "gemini": _call_gemini,
    "groq": _call_groq,
    "github": _call_github_models,
}


def _retry_provider(name: str, call_fn: Callable[[], str]) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            result = call_fn()
            log.info("LLM response from %s", name)
            return result
        except Exception as exc:
            last_error = exc
            if _is_rate_or_auth_error(exc):
                mark_provider_exhausted(name)
                log.warning("%s unavailable (%s) — skipping for rest of run", name, exc)
                raise RuntimeError(f"{name}: {exc}") from exc
            log.warning("%s attempt %d/%d: %s", name, attempt + 1, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(1 + attempt)
    raise RuntimeError(f"{name} failed after {MAX_RETRIES} attempts: {last_error}")


def generate_text(prompt: str, max_tokens: int = 4096, preferred: Optional[str] = None) -> str:
    chain_names = resolve_provider_order(preferred)
    if not chain_names:
        raise RuntimeError("No LLM providers configured or all providers exhausted")

    errors: List[str] = []
    for name in chain_names:
        if not is_provider_available(name):
            continue
        provider_fn = _PROVIDER_CALLERS.get(name)
        if provider_fn is None:
            continue
        try:
            return _retry_provider(name, lambda fn=provider_fn: fn(prompt, max_tokens))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            log.warning("Provider %s failed, trying next available...", name)

    raise RuntimeError("All LLM providers failed:\n" + "\n".join(errors))
