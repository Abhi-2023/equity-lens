"""MCP client wrapper for the Finance server — used by the Market agent node.

Uses LangChain's MCP client integration (`langchain-mcp-adapters`), matching
Section 6: "Tool calls (Finance MCP, Search MCP) are invoked from inside the
respective agent nodes using LangChain's MCP client integration."
"""
from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

_FINANCE_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "finance_server.py")


def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "finance": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [_FINANCE_SERVER_SCRIPT],
            }
        }
    )


async def get_finance_tools() -> list[BaseTool]:
    """Returns the Finance MCP server's tools as LangChain-invocable tools."""
    return await _client().get_tools()


async def call_finance_tool(name: str, **kwargs) -> dict:
    """Direct single-tool call, e.g. `await call_finance_tool('get_stock_price', ticker='AAPL')`."""
    tools = await get_finance_tools()
    tool_by_name = {t.name: t for t in tools}
    if name not in tool_by_name:
        raise ValueError(f"Unknown finance tool '{name}'. Available: {list(tool_by_name)}")
    return await tool_by_name[name].ainvoke(kwargs)
