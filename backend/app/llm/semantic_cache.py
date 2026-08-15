"""Semantic response cache for LLM gateway calls.

Embeds the prompt and searches a dedicated Qdrant collection for a
near-duplicate past request, returning the previously-generated structured
result without calling the LLM at all on a high-confidence hit.

`cache_scope` (the ticker) is a REQUIRED, exact-match filter — not just an
embedding similarity signal. This was added after live testing caught a real
cross-company collision: the planner's prompt is mostly boilerplate ("Company:
X (TICKER)\\nReport depth: quick...\\nProduce the research plan."), and the
fact-checker/synthesizer's "insufficient evidence" boilerplate is nearly
identical across *every* company when the evidence bundle is thin. Embedding
similarity alone hit 0.97+ between two different companies' prompts and
served Microsoft's cached plan/verdict for an NVIDIA request. Scoping by
ticker first makes that structurally impossible regardless of how similar
two different companies' boilerplate text happens to be — similarity is only
used to find near-duplicates *within* one company's own cached entries.

Runs on the same Qdrant instance/FastEmbed model already used for filings
retrieval (app/rag/vectorstore.py) via app/qdrant_client.py.
"""
from __future__ import annotations

import time

from langsmith import traceable
from pydantic import BaseModel, TypeAdapter
from qdrant_client import models

from app.config import settings
from app.qdrant_client import EMBEDDING_MODEL, get_qdrant_client
from app.llm.types import TaskComplexity

_COLLECTION = "llm_semantic_cache"


def _ensure_collection() -> None:
    client = get_qdrant_client()
    if client.collection_exists(_COLLECTION):
        return
    dim = client.get_embedding_size(EMBEDDING_MODEL)
    client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )


def _cache_text(
    schema: type[BaseModel], task: TaskComplexity, cache_scope: str, messages: list[tuple[str, str]]
) -> str:
    joined = "\n".join(f"{role}:{content}" for role, content in messages)
    return f"{task.value}::{schema.__name__}::{cache_scope}::{joined}"


def _point_id(
    schema: type[BaseModel], task: TaskComplexity, cache_scope: str, messages: list[tuple[str, str]]
) -> int:
    return abs(hash(_cache_text(schema, task, cache_scope, messages))) % (2**62)


@traceable(name="llm_semantic_cache_lookup", run_type="retriever")
async def get_cached(
    schema: type[BaseModel],
    task: TaskComplexity,
    cache_scope: str,
    messages: list[tuple[str, str]],
) -> BaseModel | None:
    _ensure_collection()
    client = get_qdrant_client()
    if client.count(_COLLECTION).count == 0:
        return None

    results = client.query_points(
        collection_name=_COLLECTION,
        query=models.Document(text=_cache_text(schema, task, cache_scope, messages), model=EMBEDDING_MODEL),
        query_filter=models.Filter(
            must=[
                models.FieldCondition(key="schema", match=models.MatchValue(value=schema.__name__)),
                models.FieldCondition(key="task", match=models.MatchValue(value=task.value)),
                # Exact match, not similarity — see module docstring for why.
                models.FieldCondition(key="cache_scope", match=models.MatchValue(value=cache_scope)),
            ]
        ),
        limit=1,
        with_payload=True,
    ).points

    if not results:
        return None

    point = results[0]
    if point.score < settings.llm_semantic_cache_similarity_threshold:
        return None

    age_seconds = time.time() - point.payload["cached_at"]
    if age_seconds > settings.llm_semantic_cache_ttl_seconds:
        return None

    return TypeAdapter(schema).validate_json(point.payload["response_json"])


async def store_cached(
    schema: type[BaseModel],
    task: TaskComplexity,
    cache_scope: str,
    messages: list[tuple[str, str]],
    result: BaseModel,
) -> None:
    _ensure_collection()
    client = get_qdrant_client()
    point_id = _point_id(schema, task, cache_scope, messages)
    client.upsert(
        collection_name=_COLLECTION,
        points=[
            models.PointStruct(
                id=point_id,
                vector=models.Document(
                    text=_cache_text(schema, task, cache_scope, messages), model=EMBEDDING_MODEL
                ),
                payload={
                    "schema": schema.__name__,
                    "task": task.value,
                    "cache_scope": cache_scope,
                    "response_json": result.model_dump_json(),
                    "cached_at": time.time(),
                },
            )
        ],
    )
