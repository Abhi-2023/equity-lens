"""Hybrid dense + keyword retrieval, reranked by Cohere (Section 3 / 6 / 9).

Dense: Qdrant (a real service — `docker-compose up qdrant` — not the embedded/
local-file mode), using its bundled FastEmbed integration for the first-pass
embedding (no extra API key needed for that part). Point `QDRANT_URL` at any
other Qdrant instance (e.g. the "Qdrant on GCE" deployment in Section 8) to
swap it — every call in this module goes through the same client.

Note: qdrant-client's old `.add()`/`.query()`/`.set_model()` convenience
wrapper was removed in 1.19 — embedding is now done by wrapping text in
`models.Document` and passing it directly to `upsert`/`query_points`, which
is what this module does (verified against a live Qdrant service, not just
read off the changelog).

Keyword: BM25 over the same chunk texts, fused with the dense results via
reciprocal rank fusion (RRF) — cheap, no extra service, and it rescues exact
term matches (ticker symbols, dollar figures) that embeddings often blur.

Rerank: the RRF-fused candidates are then reranked by Cohere's rerank API,
which cross-encodes (query, candidate) pairs directly rather than comparing
independently-computed embeddings — consistently sharper top-k precision
than embedding similarity alone. Requires `COHERE_API_KEY`; retrieval still
works without one (falls back to the RRF order), so this doesn't hard-block
local dev or tests that don't have a Cohere account.
"""
from __future__ import annotations

from functools import lru_cache

import cohere
from langsmith import traceable
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi

from app.config import settings
from app.qdrant_client import EMBEDDING_MODEL, get_qdrant_client as _client

_RRF_K = 60
_RERANK_CANDIDATE_MULTIPLIER = 3  # fetch more than k so reranking has something to work with


@lru_cache
def _cohere_client() -> cohere.ClientV2 | None:
    if not settings.cohere_api_key:
        return None
    return cohere.ClientV2(api_key=settings.cohere_api_key)


def _collection_name(ticker: str) -> str:
    return f"filings_{ticker.upper()}"


def _ensure_collection(client: QdrantClient, collection: str) -> None:
    if client.collection_exists(collection):
        return
    dim = client.get_embedding_size(EMBEDDING_MODEL)
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )


def add_documents(ticker: str, chunks: list[dict]) -> int:
    """chunks: [{text, source, item, url, ticker, filing_date}, ...]"""
    if not chunks:
        return 0
    client = _client()
    collection = _collection_name(ticker)
    _ensure_collection(client, collection)

    points = []
    for i, chunk in enumerate(chunks):
        point_id = abs(hash(f"{ticker.upper()}-{i}-{chunk['text']}")) % (2**62)
        points.append(
            models.PointStruct(
                id=point_id,
                vector=models.Document(text=chunk["text"], model=EMBEDDING_MODEL),
                payload={
                    "document": chunk["text"],
                    "source": chunk["source"],
                    "item": chunk["item"],
                    "url": chunk["url"] or "",
                    "ticker": chunk["ticker"],
                },
            )
        )
    client.upsert(collection_name=collection, points=points)
    return len(chunks)


def has_documents(ticker: str) -> bool:
    client = _client()
    collection = _collection_name(ticker)
    if not client.collection_exists(collection):
        return False
    return client.count(collection).count > 0


def _bm25_rank(query: str, documents: list[str]) -> list[int]:
    tokenized = [doc.lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    return sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)


@traceable(name="hybrid_search_rrf", run_type="retriever")
def _rrf_fuse(client: QdrantClient, collection: str, query: str, fetch_k: int, total: int) -> list[dict]:
    dense = client.query_points(
        collection_name=collection,
        query=models.Document(text=query, model=EMBEDDING_MODEL),
        limit=min(fetch_k, total),
        with_payload=True,
    ).points

    all_records, _ = client.scroll(collection_name=collection, limit=total, with_payload=True)
    all_ids = [r.id for r in all_records]
    all_texts = [r.payload["document"] for r in all_records]
    all_payloads = {r.id: r.payload for r in all_records}

    bm25_order = _bm25_rank(query, all_texts)
    bm25_rank_of_id = {all_ids[pos]: rank for rank, pos in enumerate(bm25_order)}

    fused: dict[int, float] = {}
    for rank, point in enumerate(dense):
        fused[point.id] = fused.get(point.id, 0) + 1 / (_RRF_K + rank)
    for point_id, rank in bm25_rank_of_id.items():
        fused[point_id] = fused.get(point_id, 0) + 1 / (_RRF_K + rank)

    ranked_ids = sorted(fused, key=lambda i: fused[i], reverse=True)
    results = []
    for point_id in ranked_ids:
        payload = all_payloads[point_id]
        results.append(
            {
                "id": str(point_id),
                "score": fused[point_id],
                "text": payload["document"],
                "source": payload.get("source"),
                "item": payload.get("item"),
                "url": payload.get("url") or None,
                "ticker": payload.get("ticker"),
            }
        )
    return results


@traceable(name="cohere_rerank", run_type="retriever")
def _cohere_rerank(query: str, candidates: list[dict], k: int) -> list[dict]:
    client = _cohere_client()
    if client is None or not candidates:
        return candidates[:k]
    response = client.rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=[c["text"] for c in candidates],
        top_n=min(k, len(candidates)),
    )
    reranked = []
    for result in response.results:
        item = {**candidates[result.index], "rerank_score": result.relevance_score}
        reranked.append(item)
    return reranked


@traceable(name="filings_hybrid_search", run_type="retriever")
def hybrid_search(ticker: str, query: str, k: int = 6) -> list[dict]:
    client = _client()
    collection = _collection_name(ticker)
    if not client.collection_exists(collection):
        return []
    total = client.count(collection).count
    if total == 0:
        return []

    fetch_k = k * _RERANK_CANDIDATE_MULTIPLIER if _cohere_client() else k
    candidates = _rrf_fuse(client, collection, query, fetch_k, total)
    return _cohere_rerank(query, candidates, k)
