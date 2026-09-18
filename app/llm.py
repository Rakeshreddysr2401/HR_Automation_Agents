"""Local open-source models, behind one small provider-agnostic surface.

The important property of this module is that everything in it is optional. The
agent's decisions are carried by deterministic scoring; the model sharpens
margins and writes the human-readable rationale. If no model server is
reachable, every function here degrades to a documented fallback and the
migration still completes - it simply escalates a little more, which is the
correct direction to fail in.

Two providers are supported, and chat and embeddings are configured separately
because in practice they run on different machines:

    ollama   native /api/embeddings and /api/generate
    openai   OpenAI-compatible /embeddings and /chat/completions, which covers
             llama.cpp, vLLM and LM Studio

The model also never sees a record. It sees a redacted column profile and
returns a decision about the *column*; Python applies that decision to every
row. One call covers fifty rows or fifty thousand.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading

import httpx

from app.settings import get_settings

log = logging.getLogger(__name__)

_embed_cache: dict[str, list[float]] = {}
_lock = threading.Lock()
_health: dict[str, bool | None] = {"embedding": None, "reasoning": None}


def reset_health() -> None:
    """Re-probe on next use (used by tests and the /health endpoint)."""
    _health["embedding"] = None
    _health["reasoning"] = None
    with _lock:
        _embed_cache.clear()


def _probe(provider: str, base_url: str, timeout: float = 3.0) -> bool:
    url = f"{base_url.rstrip('/')}/api/tags" if provider == "ollama" else f"{base_url.rstrip('/')}/models"
    try:
        return httpx.get(url, timeout=timeout).status_code == 200
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        log.info("Model server at %s unavailable (%s); falling back", base_url, exc)
        return False


def available(kind: str = "embedding") -> bool:
    """Is the named model server reachable? Probed once, then remembered."""
    settings = get_settings()
    if not settings.llm_enabled:
        return False
    if _health[kind] is not None:
        return bool(_health[kind])
    provider = settings.embedding_provider if kind == "embedding" else settings.reasoning_provider
    base_url = settings.embedding_base_url if kind == "embedding" else settings.reasoning_base_url
    _health[kind] = _probe(provider, base_url)
    return bool(_health[kind])


def status() -> dict[str, object]:
    """What the UI shows about model availability."""
    settings = get_settings()
    return {
        "enabled": settings.llm_enabled,
        "embedding": {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "base_url": settings.embedding_base_url,
            "reachable": available("embedding"),
        },
        "reasoning": {
            "provider": settings.reasoning_provider,
            "model": settings.reasoning_model,
            "base_url": settings.reasoning_base_url,
            "reachable": available("reasoning"),
        },
    }


def embed(text: str) -> list[float] | None:
    """Embed one string. None when the model server is unavailable."""
    if not text or not available("embedding"):
        return None
    with _lock:
        hit = _embed_cache.get(text)
    if hit is not None:
        return hit

    settings = get_settings()
    base = settings.embedding_base_url.rstrip("/")
    try:
        if settings.embedding_provider == "ollama":
            resp = httpx.post(
                f"{base}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            vector = resp.json().get("embedding")
        else:
            resp = httpx.post(
                f"{base}/embeddings",
                json={"model": settings.embedding_model, "input": text},
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            payload = resp.json()
            vector = (payload.get("data") or [{}])[0].get("embedding")
    except Exception as exc:  # noqa: BLE001
        log.warning("Embedding failed (%s); continuing without semantic scoring", exc)
        _health["embedding"] = False
        return None

    if not vector:
        return None
    with _lock:
        _embed_cache[text] = vector
    return vector


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    # Cosine runs [-1, 1]; clamp to [0, 1] so it composes with the fuzzy score.
    return max(0.0, min(1.0, dot / (na * nb)))


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def ask_json(prompt: str, *, temperature: float = 0.0) -> dict | None:
    """Ask the reasoning model for a JSON object. None on any failure.

    Callers must treat None as "no opinion" and fall back to their deterministic
    path. Nothing in the pipeline blocks on this succeeding.
    """
    if not available("reasoning"):
        return None
    settings = get_settings()
    base = settings.reasoning_base_url.rstrip("/")
    try:
        if settings.reasoning_provider == "ollama":
            resp = httpx.post(
                f"{base}/api/generate",
                json={
                    "model": settings.reasoning_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature},
                },
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            body = resp.json().get("response", "")
        else:
            resp = httpx.post(
                f"{base}/chat/completions",
                json={
                    "model": settings.reasoning_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {settings.reasoning_api_key}"},
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
            choices = resp.json().get("choices") or [{}]
            body = (choices[0].get("message") or {}).get("content", "")
    except Exception as exc:  # noqa: BLE001
        log.warning("Reasoning model call failed (%s); using deterministic path", exc)
        return None

    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # Smaller models wrap JSON in prose even when asked not to.
        match = _JSON_BLOCK.search(body)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
