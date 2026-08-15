"""Redis-backed circuit breaker for (account, model) pairs.

When a candidate gets rate-limited, every subsequent gateway call — across
every report job, not just the one that discovered the limit — should skip
straight past it instead of re-discovering the same 429 from scratch. That's
the actual fix for repeatedly burning latency (and a request against the
daily quota) on a pool we already know is exhausted.
"""
from __future__ import annotations

from app.cache import get_redis

_KEY_PREFIX = "equitylens:llm_cooldown"


def _key(account_index: int, model: str) -> str:
    return f"{_KEY_PREFIX}:{account_index}:{model}"


async def is_cooling_down(account_index: int, model: str) -> bool:
    return bool(await get_redis().exists(_key(account_index, model)))


async def set_cooldown(account_index: int, model: str, seconds: float) -> None:
    seconds = max(1, int(seconds))
    await get_redis().set(_key(account_index, model), "1", ex=seconds)


async def clear_cooldown(account_index: int, model: str) -> None:
    await get_redis().delete(_key(account_index, model))
