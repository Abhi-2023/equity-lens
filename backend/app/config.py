"""Central app configuration, loaded from environment variables (.env in dev)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env")

DATA_DIR = BACKEND_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Postgres via asyncpg — required (Section 8: "Cloud SQL (Postgres)"). Default
    # assumes `docker-compose up postgres` exposed on localhost; the backend
    # container itself gets this overridden to the `postgres` service hostname.
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://equitylens:equitylens@localhost:5432/equitylens"
    )

    # Redis cache — required for the caching layer (ticker resolution, Finance/News
    # MCP tool results). Defaults to `docker-compose up redis` exposed on localhost.
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache_ttl_ticker_seconds: int = int(os.getenv("CACHE_TTL_TICKER_SECONDS", str(60 * 60 * 24)))
    cache_ttl_market_seconds: int = int(os.getenv("CACHE_TTL_MARKET_SECONDS", "300"))
    cache_ttl_news_seconds: int = int(os.getenv("CACHE_TTL_NEWS_SECONDS", "900"))

    # Qdrant — defaults to `docker-compose up qdrant` exposed on localhost; set
    # QDRANT_URL to any other Qdrant instance (e.g. Qdrant on GCE, Section 8).
    # Falls back to embedded/local-file mode only if QDRANT_URL is left empty
    # AND explicitly allowed via QDRANT_ALLOW_EMBEDDED=true (dev convenience).
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")
    qdrant_allow_embedded: bool = os.getenv("QDRANT_ALLOW_EMBEDDED", "false").lower() == "true"
    qdrant_path: str = os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant"))

    # Cohere — reranks hybrid (dense+BM25) retrieval results. Retrieval still
    # works without a key (falls back to the un-reranked RRF order) so tests
    # and local dev don't hard-require a Cohere account.
    cohere_api_key: str | None = os.getenv("COHERE_API_KEY")
    cohere_rerank_model: str = os.getenv("COHERE_RERANK_MODEL", "rerank-v3.5")

    # LangSmith observability. `load_dotenv` above already puts these into
    # os.environ, which is what LangChain's own tracing reads from directly.
    langchain_tracing_v2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    langchain_project: str = os.getenv("LANGCHAIN_PROJECT", "equitylens")

    max_fact_check_passes: int = int(os.getenv("MAX_FACT_CHECK_PASSES", "2"))
    news_lookback_days: int = int(os.getenv("NEWS_LOOKBACK_DAYS", "60"))

    finance_mcp_command: str = os.getenv("FINANCE_MCP_COMMAND", "python")
    finance_mcp_args: list[str] = [str(BACKEND_ROOT / "app" / "mcp_servers" / "finance_server.py")]


settings = Settings()
