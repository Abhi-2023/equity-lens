"""LLM Gateway: (account x model) fallback with cooldown-aware routing.

Drop-in replacement for the old single-model `get_llm()` in app/graph/llm.py
(now removed) — call sites still do
`gateway.with_structured_output(Schema, task).ainvoke(messages)`, just via
`get_llm_gateway()` instead of a single fixed ChatGroq client.

Candidate order: fully exhaust account 1's model chain before trying account
2 — predictable and easy to reason about, versus interleaving. Within an
account, SIMPLE tasks (planner, fact-checker) try the small/fast model
first; COMPLEX tasks (synthesizer) try the large model first and only fall
to the small one as a last resort, since writing quality matters more there
than speed.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from langchain_groq import ChatGroq
from langsmith import traceable
from pydantic import BaseModel

from app.config import settings
from app.llm.cooldown import is_cooling_down, set_cooldown
from app.llm.errors import ErrorClass, classify_error, parse_retry_after_seconds
from app.llm.semantic_cache import get_cached, store_cached
from app.llm.types import TaskComplexity

logger = logging.getLogger("equitylens")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class Candidate:
    account_index: int
    api_key: str
    model: str

    @property
    def label(self) -> str:
        return f"account{self.account_index}:{self.model}"


class AllProvidersExhaustedError(RuntimeError):
    def __init__(self, attempts: list[str]):
        self.attempts = attempts
        super().__init__(
            "Every Groq (account, model) candidate failed or was cooling down: " + "; ".join(attempts)
        )


class _SkipAccountError(Exception):
    """Auth failure — every model under this account shares the same key, so
    the rest of this account's chain is skipped, not just the one model."""

    def __init__(self, account_index: int, exc: Exception):
        self.account_index = account_index
        self.exc = exc


@lru_cache
def _chat_client(api_key: str, model: str) -> ChatGroq:
    return ChatGroq(model=model, api_key=api_key, temperature=0.0, max_tokens=4096)


def _build_candidates(task: TaskComplexity) -> list[Candidate]:
    if not settings.groq_api_keys:
        raise RuntimeError(
            "No Groq API keys configured. Set GROQ_API_KEYS (comma-separated, one per account) "
            "or GROQ_API_KEY in backend/.env before running the agent graph."
        )
    models = (
        settings.groq_model_chain_simple
        if task is TaskComplexity.SIMPLE
        else settings.groq_model_chain_complex
    )
    return [
        Candidate(account_index=account_index, api_key=api_key, model=model)
        for account_index, api_key in enumerate(settings.groq_api_keys)
        for model in models
    ]


@traceable(name="llm_gateway_attempt", run_type="llm")
async def _traced_invoke(candidate_label: str, llm, messages: list[tuple[str, str]]):
    return await llm.ainvoke(messages)


class BoundGateway:
    """Returned by `LLMGateway.with_structured_output()` — what node code
    actually calls `.ainvoke()` on. Tracks which model ultimately served the
    request so callers can surface that in status messages if they want."""

    def __init__(self, schema: type[SchemaT], task: TaskComplexity, cache_scope: str, use_cache: bool):
        self._schema = schema
        self._task = task
        self._cache_scope = cache_scope
        self._use_cache = use_cache
        self.last_model_used: str | None = None
        self.fell_back: bool = False
        self.cache_hit: bool = False

    async def ainvoke(self, messages: list[tuple[str, str]]) -> SchemaT:
        if settings.llm_semantic_cache_enabled and self._use_cache:
            cached = await get_cached(self._schema, self._task, self._cache_scope, messages)
            if cached is not None:
                self.last_model_used = None
                self.fell_back = False
                self.cache_hit = True
                return cached

        candidates = _build_candidates(self._task)
        attempts: list[str] = []
        broken_accounts: set[int] = set()

        for index, candidate in enumerate(candidates):
            if candidate.account_index in broken_accounts:
                continue
            if await is_cooling_down(candidate.account_index, candidate.model):
                attempts.append(f"{candidate.label} (cooling down)")
                continue

            try:
                result = await self._try_candidate(candidate, messages, attempts)
            except _SkipAccountError as skip:
                attempts.append(f"account{skip.account_index} (auth failed: {skip.exc})")
                broken_accounts.add(skip.account_index)
                continue

            if result is not None:
                self.last_model_used = candidate.label
                self.fell_back = index > 0
                self.cache_hit = False
                if settings.llm_semantic_cache_enabled and self._use_cache:
                    await store_cached(self._schema, self._task, self._cache_scope, messages, result)
                return result

        raise AllProvidersExhaustedError(attempts)

    async def _try_candidate(
        self, candidate: Candidate, messages: list[tuple[str, str]], attempts: list[str]
    ) -> SchemaT | None:
        llm = _chat_client(candidate.api_key, candidate.model).with_structured_output(self._schema)
        max_attempts = 1 + settings.llm_gateway_max_retries_per_model

        for attempt_num in range(1, max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    _traced_invoke(candidate.label, llm, messages),
                    timeout=settings.llm_gateway_timeout_seconds,
                )
            except Exception as exc:
                error_class = classify_error(exc)
                attempts.append(f"{candidate.label} ({error_class.value}: {exc})")

                if error_class is ErrorClass.RATE_LIMIT:
                    retry_after = parse_retry_after_seconds(exc) or settings.llm_gateway_cooldown_seconds
                    await set_cooldown(candidate.account_index, candidate.model, retry_after)
                    return None

                if error_class is ErrorClass.AUTH:
                    raise _SkipAccountError(candidate.account_index, exc) from exc

                if error_class in (ErrorClass.TRANSIENT, ErrorClass.UNKNOWN) and attempt_num < max_attempts:
                    logger.warning(
                        "LLM candidate %s failed (%s), retrying once", candidate.label, error_class.value
                    )
                    continue

                return None  # exhausted retries, or non-retryable (e.g. context length) — try next candidate

        return None


class LLMGateway:
    def with_structured_output(
        self,
        schema: type[SchemaT],
        task: TaskComplexity = TaskComplexity.COMPLEX,
        *,
        cache_scope: str,
        use_cache: bool = True,
    ) -> BoundGateway:
        """`cache_scope` (typically the ticker) is required and exact-match
        filtered in the semantic cache — see semantic_cache.py's docstring
        for the cross-company collision this prevents.

        `use_cache=False` for correction-pass calls: a revision prompt
        ("fix this specific flagged section") is textually near-identical to
        the original draft prompt it's revising, so the cache would happily
        return the *original, unrevised* draft — silently defeating the
        fact-checker's correction loop. Caught live: a flagged section
        stayed flagged after a "successful" revision because the revision
        never actually ran."""
        return BoundGateway(schema, task, cache_scope, use_cache)


def get_llm_gateway() -> LLMGateway:
    return LLMGateway()
