"""Central app configuration, loaded from environment variables (.env in dev)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env")

DATA_DIR = BACKEND_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    # LLM gateway (Section: "LLM Gateway with fallback"). GROQ_API_KEYS is a
    # comma-separated list — one entry per Groq account, tried in order, each
    # with its own independent daily token budget. GROQ_API_KEY (singular) is
    # kept as a fallback for a single-account setup.
    groq_api_keys: list[str] = _split_csv(os.getenv("GROQ_API_KEYS")) or _split_csv(
        os.getenv("GROQ_API_KEY")
    )

    # Two model chains, tried in order within each account before moving to
    # the next account. SIMPLE is used for structured/classification-style
    # node work (planner, fact-checker); COMPLEX for open-ended writing
    # (synthesizer), where quality matters more than speed/cost.
    groq_model_chain_simple: list[str] = _split_csv(os.getenv("GROQ_MODEL_CHAIN_SIMPLE")) or [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
    ]
    groq_model_chain_complex: list[str] = _split_csv(os.getenv("GROQ_MODEL_CHAIN_COMPLEX")) or [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
    ]

    llm_gateway_cooldown_seconds: int = int(os.getenv("LLM_GATEWAY_COOLDOWN_SECONDS", "600"))
    llm_gateway_max_retries_per_model: int = int(os.getenv("LLM_GATEWAY_MAX_RETRIES_PER_MODEL", "1"))
    llm_gateway_timeout_seconds: int = int(os.getenv("LLM_GATEWAY_TIMEOUT_SECONDS", "60"))

    # Semantic response cache — skips the LLM entirely on a near-duplicate
    # request (same evidence bundle re-synthesized, a watchlist refresh where
    # nothing changed, an accidental double-submit).
    llm_semantic_cache_enabled: bool = os.getenv("LLM_SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
    llm_semantic_cache_similarity_threshold: float = float(
        os.getenv("LLM_SEMANTIC_CACHE_SIMILARITY_THRESHOLD", "0.97")
    )
    llm_semantic_cache_ttl_seconds: int = int(
        os.getenv("LLM_SEMANTIC_CACHE_TTL_SECONDS", str(60 * 60 * 24 * 3))
    )

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
