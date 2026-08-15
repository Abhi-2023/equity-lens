"""News agent node (Section 4 step 4).

Calls the web-search MCP server, retrieves and summarizes the last N relevant
articles. Cross-referencing against filing content to drop near-duplicates
happens in `evidence.py`, once all three parallel branches have rejoined —
this node runs concurrently with filings_agent/market_agent and can't see
their output yet.
"""
from __future__ import annotations

from langsmith import traceable

from app.cache import cached_call
from app.config import settings
from app.graph.state import EvidenceItem, ResearchState
from app.graph.status import node_status
from app.mcp_servers.news_client import search_news


@traceable(name="news_agent", run_type="chain")
async def news_agent_node(state: ResearchState) -> dict:
    if not state["plan"]["needs_news"]:
        return {"news_evidence": []}

    ticker = state["ticker"]
    company_input = state["company_input"]
    max_results = {"quick": 3, "standard": 5, "deep": 8}.get(state.get("depth", "standard"), 5)
    timelimit = "m" if settings.news_lookback_days <= 31 else "y"

    async with node_status(state["job_id"], "news_agent", f"Searching recent news for {company_input}...") as status:

        async def fetch() -> list[dict]:
            return await search_news(
                query=f"{company_input} ({ticker}) stock", max_results=max_results, timelimit=timelimit
            )

        articles = await cached_call(
            "news_search", (ticker, max_results, timelimit), settings.cache_ttl_news_seconds, fetch
        )
        await status.message(f"Found {len(articles)} recent articles")

        evidence: list[EvidenceItem] = []
        for i, article in enumerate(articles, start=1):
            if not article.get("title") or not article.get("snippet"):
                continue
            evidence.append(
                EvidenceItem(
                    id=f"N{i}",
                    text=f"{article['title']}: {article['snippet']}",
                    source=f"{article.get('source', 'News')} — {article.get('date', 'undated')}",
                    origin="news",
                    url=article.get("url"),
                )
            )

        return {"news_evidence": evidence}
