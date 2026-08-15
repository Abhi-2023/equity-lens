"""MCP client wrapper for the News/web-search server — used by the News agent node."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

_NEWS_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "news_server.py")


def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "news": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [_NEWS_SERVER_SCRIPT],
            }
        }
    )


async def get_news_tools() -> list[BaseTool]:
    return await _client().get_tools()


async def search_news(query: str, max_results: int = 8, timelimit: str = "m") -> list[dict]:
    """Returns parsed article dicts: [{title, snippet, url, source, date}, ...]."""
    tools = await get_news_tools()
    tool_by_name = {t.name: t for t in tools}
    raw = await tool_by_name["search_news"].ainvoke(
        {"query": query, "max_results": max_results, "timelimit": timelimit}
    )
    # FastMCP returns one content block per list item, each a JSON-encoded article.
    articles = []
    for block in raw:
        text = block["text"] if isinstance(block, dict) else block
        try:
            articles.append(json.loads(text))
        except (TypeError, json.JSONDecodeError):
            continue
    return articles
