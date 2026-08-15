"""Market agent node (Section 4 step 4).

Calls the custom Finance MCP server for live price, valuation ratios, and
recent fundamentals. Skipped when the Planner decides live data isn't needed.
Each tool result is cached in Redis for a few minutes — cheap insurance
against hammering the upstream data provider when the same ticker is
requested repeatedly (e.g. watchlist refresh, demo traffic).
"""
from __future__ import annotations

import json

from langsmith import traceable

from app.cache import cached_call
from app.config import settings
from app.graph.state import EvidenceItem, ResearchState
from app.graph.status import node_status
from app.mcp_servers.finance_client import get_finance_tools

_TOOL_TO_LABEL = {
    "get_stock_price": "Live price & volume",
    "get_stock_fundamentals": "Fundamentals",
    "get_valuation_ratios": "Valuation ratios",
}


def _tool_text(result) -> str:
    # langchain tool results from MCP come back as a list of content blocks
    if isinstance(result, list) and result and isinstance(result[0], dict) and "text" in result[0]:
        return result[0]["text"]
    return json.dumps(result)


@traceable(name="market_agent", run_type="chain")
async def market_agent_node(state: ResearchState) -> dict:
    if not state["plan"]["needs_live_market_data"]:
        return {"market_evidence": []}

    ticker = state["ticker"]
    async with node_status(state["job_id"], "market_agent", f"Calling Finance MCP for {ticker}...") as status:
        tools = await get_finance_tools()
        tool_by_name = {t.name: t for t in tools}

        evidence: list[EvidenceItem] = []
        for i, (tool_name, label) in enumerate(_TOOL_TO_LABEL.items(), start=1):
            await status.message(f"{label} — calling {tool_name} via MCP...")

            async def fetch(tool_name=tool_name) -> str:
                result = await tool_by_name[tool_name].ainvoke({"ticker": ticker})
                return _tool_text(result)

            text = await cached_call(
                f"finance_mcp:{tool_name}", (ticker,), settings.cache_ttl_market_seconds, fetch
            )
            evidence.append(
                EvidenceItem(
                    id=f"M{i}",
                    text=text,
                    source=f"{label} (via Finance MCP, cached ≤{settings.cache_ttl_market_seconds}s)",
                    origin="market",
                    url=None,
                )
            )

        return {"market_evidence": evidence}
