"""Thin client for Ollama's HTTP API (model discovery + capabilities)."""

import asyncio

import httpx

from config import settings

# Capabilities rarely change, so the (fairly chatty) lookup is cached per key.
_cache: dict[str, list[dict]] = {}


async def _capabilities(http: httpx.AsyncClient, headers: dict, base: str, name: str) -> list[str]:
    try:
        r = await http.post(base + "/api/show", headers=headers, json={"model": name})
        r.raise_for_status()
        return r.json().get("capabilities") or []
    except Exception:  # noqa: BLE001 - a model we can't introspect is simply untagged
        return []


async def list_models(api_key: str | None) -> list[dict]:
    """Every model on the Ollama server as {name, reasoning} (reasoning = supports thinking)."""
    cache_key = api_key or ""
    if cache_key in _cache:
        return _cache[cache_key]

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(base + "/api/tags", headers=headers)
        r.raise_for_status()
        names = sorted(m["name"] for m in r.json().get("models", []))
        caps = await asyncio.gather(*(_capabilities(http, headers, base, n) for n in names))

    models = [{"name": n, "reasoning": "thinking" in c} for n, c in zip(names, caps)]
    _cache[cache_key] = models
    return models
