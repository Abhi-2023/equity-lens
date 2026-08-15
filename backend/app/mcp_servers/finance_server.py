"""Custom Finance MCP server (Section 3 / 9 of the spec).

Exposes live price, valuation ratios, and recent fundamentals as MCP tools,
backed by yfinance. Runs as a standalone stdio process — the Market agent
connects to it as an MCP client (see `finance_client.py`), matching "Market
agent — calling get_stock_fundamentals via MCP..." from Section 2.2.

Run directly for manual testing:
    python -m app.mcp_servers.finance_server
"""
from __future__ import annotations

import yfinance as yf
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("equitylens-finance")


@mcp.tool()
def get_stock_price(ticker: str) -> dict:
    """Get the latest price, day change, and volume for a ticker."""
    info = yf.Ticker(ticker).fast_info
    last_price = info.get("lastPrice")
    previous_close = info.get("previousClose")
    return {
        "ticker": ticker.upper(),
        "last_price": last_price,
        "previous_close": previous_close,
        "day_change_pct": (
            round((last_price / previous_close - 1) * 100, 2)
            if last_price and previous_close
            else None
        ),
        "market_cap": info.get("marketCap"),
        "currency": info.get("currency"),
    }


@mcp.tool()
def get_stock_fundamentals(ticker: str) -> dict:
    """Get key fundamentals: revenue, earnings, margins, and sector for a ticker."""
    t = yf.Ticker(ticker)
    info = t.info
    return {
        "ticker": ticker.upper(),
        "short_name": info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "total_revenue": info.get("totalRevenue"),
        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "net_income": info.get("netIncomeToCommon"),
        "trailing_eps": info.get("trailingEps"),
        "revenue_growth_yoy": info.get("revenueGrowth"),
    }


@mcp.tool()
def get_valuation_ratios(ticker: str) -> dict:
    """Get valuation ratios (P/E, P/B, EV/EBITDA, etc.) for a ticker, vs. sector where available."""
    info = yf.Ticker(ticker).info
    return {
        "ticker": ticker.upper(),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_book": info.get("priceToBook"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "peg_ratio": info.get("trailingPegRatio"),
        "dividend_yield": info.get("dividendYield"),
        "sector": info.get("sector"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
