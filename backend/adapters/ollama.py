"""Thin client for Ollama's HTTP API (model discovery + capabilities)."""

import asyncio
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

LOCAL_OLLAMA_BASE_URLS = frozenset(
    {
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    }
)
OLLAMA_CLOUD_BASE_URL = "https://ollama.com"

# Capabilities rarely change, so the (fairly chatty) lookup is cached per key.
_cache: dict[str, list[dict]] = {}


def effective_base_url(api_key: str | None) -> str:
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    if api_key and base in LOCAL_OLLAMA_BASE_URLS:
        return OLLAMA_CLOUD_BASE_URL
    return settings.OLLAMA_BASE_URL


async def _capabilities(http: httpx.AsyncClient, headers: dict, base: str, name: str) -> list[str]:
    try:
        r = await http.post(base + "/api/show", headers=headers, json={"model": name})
        r.raise_for_status()
        return r.json().get("capabilities") or []
    except Exception:  # noqa: BLE001 - a model we can't introspect is simply untagged
        return []


async def fetch_models_from_ollama(api_key: str | None) -> list[dict]:
    """Fetch every model from Ollama with metadata suitable for DB storage."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    base = effective_base_url(api_key).rstrip("/")
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(base + "/api/tags", headers=headers)
        r.raise_for_status()
        raw_models = r.json().get("models", [])

        names = sorted(m["name"] for m in raw_models if m.get("name"))
        caps = await asyncio.gather(*(_capabilities(http, headers, base, n) for n in names))
        caps_by_name = dict(zip(names, caps))
        by_name = {m["name"]: m for m in raw_models if m.get("name")}

    models: list[dict] = []
    for name in names:
        raw = by_name[name]
        details = raw.get("details") or {}
        models.append(
            {
                "name": name,
                "reasoning": "thinking" in caps_by_name.get(name, []),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
                "size": raw.get("size"),
                "modified_at": raw.get("modified_at"),
            }
        )
    return models


async def list_models(api_key: str | None) -> list[dict]:
    """Every model on the Ollama server as {name, reasoning} (cached in-memory)."""
    cache_key = api_key or ""
    if cache_key in _cache:
        return _cache[cache_key]

    models = await fetch_models_from_ollama(api_key)
    slim = [{"name": m["name"], "reasoning": m["reasoning"]} for m in models]
    _cache[cache_key] = slim
    return slim


async def sync_models_to_db(session, api_key: str | None) -> list[dict]:
    """Pull models from Ollama and upsert them into the database."""
    from database.ollama_models import upsert_models

    try:
        models = await fetch_models_from_ollama(api_key)
    except Exception as exc:
        logger.warning("Ollama model sync failed: %s", exc)
        raise

    rows = upsert_models(session, models)
    _cache[api_key or ""] = [{"name": r.name, "reasoning": r.reasoning} for r in rows]
    logger.info("Synced %d Ollama models to database", len(rows))
    return [{"name": r.name, "reasoning": r.reasoning} for r in rows]
