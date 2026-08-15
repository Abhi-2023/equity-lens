"""Web-search MCP server for the News agent (Section 3 / 9 of the spec).

The spec calls for "a web-search MCP server" without mandating a specific
vendor — this implements one against DuckDuckGo's free news search (no API
key required) behind the same MCP tool-call boundary, so swapping in a paid
provider (Tavily, Brave, Bing) later only means changing this file, not the
agent that calls it.

Run directly for manual testing:
    python -m app.mcp_servers.news_server
"""
from __future__ import annotations

from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("equitylens-news")


@mcp.tool()
def search_news(query: str, max_results: int = 8, timelimit: str = "m") -> list[dict]:
    """Search recent news articles. timelimit: 'd' (day), 'w' (week), 'm' (month)."""
    with DDGS() as ddgs:
        results = ddgs.news(query=query, timelimit=timelimit, max_results=max_results)
    return [
        {
            "title": r.get("title"),
            "snippet": r.get("body"),
            "url": r.get("url"),
            "source": r.get("source"),
            "date": r.get("date"),
        }
        for r in results
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
