"""Зберігання результатів аналізу для поллінгу gateway (Redis у Docker)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        url = get_settings().redis_url
        _client = redis.from_url(url, decode_responses=True)
    return _client


async def save(job_id: str, payload: dict[str, Any]) -> None:
    r = _get_client()
    key = f"analysis:result:{job_id}"
    await r.set(key, json.dumps(payload, ensure_ascii=False), ex=86400)


async def get(job_id: str) -> Optional[dict[str, Any]]:
    r = _get_client()
    key = f"analysis:result:{job_id}"
    raw = await r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Corrupt JSON in Redis for %s", job_id)
        return None


async def close_connection() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
