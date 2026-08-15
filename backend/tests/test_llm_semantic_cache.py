"""Regression coverage for a real bug caught in live testing: the semantic
cache's embedding-similarity check alone let a Microsoft-scoped plan/verdict
get served for an NVIDIA request, because both companies' prompts are
dominated by near-identical boilerplate. `cache_scope` must be an exact-match
filter, not just another similarity signal — these tests assert that."""
import pytest
from pydantic import BaseModel

from app.llm.semantic_cache import get_cached, store_cached
from app.llm.types import TaskComplexity


class _FakeSchema(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_cache_hit_within_same_scope():
    messages = [("system", "You are a planner."), ("human", "Company: Acme Corp (ACME)\nProduce the plan.")]
    result = _FakeSchema(answer="acme-plan")

    await store_cached(_FakeSchema, TaskComplexity.SIMPLE, "ACME", messages, result)
    cached = await get_cached(_FakeSchema, TaskComplexity.SIMPLE, "ACME", messages)

    assert cached is not None
    assert cached.answer == "acme-plan"


@pytest.mark.asyncio
async def test_no_cross_company_collision_even_with_near_identical_prompts():
    """This is the exact shape of the bug: two companies' prompts differ
    only in the company name, which similarity alone doesn't reliably
    distinguish for short/boilerplate-heavy prompts."""
    msft_messages = [
        ("system", "You are a planner."),
        ("human", "Company: Microsoft Corporation (MSFT)\nReport depth: quick\nProduce the research plan."),
    ]
    nvda_messages = [
        ("system", "You are a planner."),
        ("human", "Company: NVIDIA Corporation (NVDA)\nReport depth: quick\nProduce the research plan."),
    ]

    await store_cached(
        _FakeSchema, TaskComplexity.SIMPLE, "MSFT", msft_messages, _FakeSchema(answer="msft-plan")
    )

    result = await get_cached(_FakeSchema, TaskComplexity.SIMPLE, "NVDA", nvda_messages)

    assert result is None, "NVDA lookup must never return MSFT's cached plan, regardless of prompt similarity"


@pytest.mark.asyncio
async def test_no_hit_for_unseen_scope():
    messages = [("system", "sys"), ("human", "totally new request never cached before")]
    result = await get_cached(_FakeSchema, TaskComplexity.COMPLEX, "ZZZZ", messages)
    assert result is None
