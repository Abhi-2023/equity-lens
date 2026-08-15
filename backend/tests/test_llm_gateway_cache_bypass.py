"""Regression coverage for a second real bug caught in live testing: a
correction-pass revision prompt is textually near-identical to the original
draft prompt it's revising, so the semantic cache returned the stale,
*unrevised* draft — silently defeating the fact-checker's correction loop.
`use_cache=False` must skip both the read and the write."""
import pytest
from pydantic import BaseModel

from app.llm import gateway as gateway_module
from app.llm.types import TaskComplexity


class _FakeSchema(BaseModel):
    answer: str


@pytest.fixture(autouse=True)
def _stub_llm_call(monkeypatch):
    """Bypasses the real Groq call chain — one fake candidate that always
    "succeeds" instantly, so these tests exercise only the cache-bypass
    wiring, not network calls or fallback routing (covered elsewhere)."""

    async def fake_is_cooling_down(account_index, model):
        return False

    async def fake_traced_invoke(candidate_label, llm, messages):
        return _FakeSchema(answer="fresh-result")

    monkeypatch.setattr(gateway_module, "is_cooling_down", fake_is_cooling_down)
    monkeypatch.setattr(gateway_module, "_traced_invoke", fake_traced_invoke)
    monkeypatch.setattr(
        gateway_module,
        "_build_candidates",
        lambda task: [gateway_module.Candidate(account_index=0, api_key="fake-key", model="fake-model")],
    )
    class _FakeChatClient:
        def with_structured_output(self, schema):
            return self

    monkeypatch.setattr(gateway_module, "_chat_client", lambda api_key, model: _FakeChatClient())


@pytest.fixture
def _cache_calls(monkeypatch):
    calls = {"get": 0, "store": 0}

    async def fake_get_cached(schema, task, cache_scope, messages):
        calls["get"] += 1
        return None

    async def fake_store_cached(schema, task, cache_scope, messages, result):
        calls["store"] += 1

    monkeypatch.setattr(gateway_module, "get_cached", fake_get_cached)
    monkeypatch.setattr(gateway_module, "store_cached", fake_store_cached)
    return calls


@pytest.mark.asyncio
async def test_use_cache_false_skips_read_and_write(_cache_calls):
    gateway = gateway_module.LLMGateway()
    bound = gateway.with_structured_output(
        _FakeSchema, TaskComplexity.COMPLEX, cache_scope="TEST", use_cache=False
    )
    result = await bound.ainvoke([("human", "revise the flagged section")])

    assert result.answer == "fresh-result"
    assert _cache_calls["get"] == 0, "use_cache=False must not read from the cache"
    assert _cache_calls["store"] == 0, "use_cache=False must not write to the cache"


@pytest.mark.asyncio
async def test_use_cache_true_reads_and_writes(_cache_calls):
    gateway = gateway_module.LLMGateway()
    bound = gateway.with_structured_output(
        _FakeSchema, TaskComplexity.COMPLEX, cache_scope="TEST", use_cache=True
    )
    await bound.ainvoke([("human", "original draft request")])

    assert _cache_calls["get"] == 1
    assert _cache_calls["store"] == 1
