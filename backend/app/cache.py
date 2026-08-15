"""Redis-backed async cache for expensive/rate-limited external calls.

Caches ticker resolution (yfinance search) and MCP tool results (Finance,
News) so repeated requests for the same ticker within the TTL window skip
the round-trip entirely — most valuable for the watchlist auto-refresh
(Section 2.4/7) where the same tickers get re-queried on a cadence, and for
demo/interview traffic that tends to hit the same handful of companies.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any, Awaitable, Callable

import redis.asyncio as redis

from app.config import settings

_KEY_PREFIX = "equitylens"


@lru_cache
def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _make_key(namespace: str, *parts: Any) -> str:
    raw = ":".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"{_KEY_PREFIX}:{namespace}:{digest}"


async def cache_get(namespace: str, *parts: Any) -> Any | None:
    value = await get_redis().get(_make_key(namespace, *parts))
    if value is None:
        return None
    return json.loads(value)


async def cache_set(namespace: str, *parts: Any, value: Any, ttl_seconds: int) -> None:
    await get_redis().set(_make_key(namespace, *parts), json.dumps(value), ex=ttl_seconds)


async def cached_call(
    namespace: str,
    key_parts: tuple[Any, ...],
    ttl_seconds: int,
    fetch: Callable[[], Awaitable[Any]],
) -> Any:
    """Cache-aside helper: return the cached value if present, otherwise call
    `fetch`, cache the result, and return it."""
    hit = await cache_get(namespace, *key_parts)
    if hit is not None:
        return hit
    result = await fetch()
    await cache_set(namespace, *key_parts, value=result, ttl_seconds=ttl_seconds)
    return result
