"""Shared Qdrant client factory — used by filings retrieval
(app/rag/vectorstore.py) and the LLM semantic cache (app/llm/semantic_cache.py),
so both go through the same connection logic and embedding model."""
from __future__ import annotations

import os
from functools import lru_cache

# Must be set before fastembed/huggingface_hub download anything: on Windows,
# without admin rights or Developer Mode, HF's symlink-based cache silently
# produces broken model snapshots (missing config.json) — copying the files
# instead avoids that.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

from qdrant_client import QdrantClient

from app.config import settings

EMBEDDING_MODEL = "BAAI/bge-small-en"


@lru_cache
def get_qdrant_client() -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    if settings.qdrant_allow_embedded:
        return QdrantClient(path=settings.qdrant_path)
    raise RuntimeError(
        "QDRANT_URL is not set. Run `docker-compose up qdrant` (or point QDRANT_URL at an "
        "existing instance); set QDRANT_ALLOW_EMBEDDED=true only for offline local dev."
    )
