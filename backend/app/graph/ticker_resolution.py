"""Resolve a free-text company name or ticker (Search-screen input, Section 2.1)
to a concrete US-exchange ticker symbol, so downstream nodes always work off a
symbol rather than guessing at company names."""
from __future__ import annotations

import asyncio

import yfinance as yf

from app.cache import cached_call
from app.config import settings


def _resolve_ticker_sync(company_input: str) -> tuple[str, str]:
    candidate = company_input.strip().upper()
    if len(candidate) <= 5 and candidate.isalpha():
        try:
            info = yf.Ticker(candidate).fast_info
            if info.get("lastPrice") is not None:
                name = yf.Ticker(candidate).info.get("shortName", candidate)
                return candidate, name
        except Exception:
            pass

    results = yf.Search(company_input, max_results=5).quotes
    equities = [r for r in results if r.get("quoteType") == "EQUITY" and r.get("symbol")]
    if not equities:
        raise ValueError(f"Could not resolve a ticker for '{company_input}'")
    best = equities[0]
    return best["symbol"], best.get("longname") or best.get("shortname") or best["symbol"]


async def resolve_ticker(company_input: str) -> tuple[str, str]:
    """Returns (ticker, display_name). Raises ValueError if nothing plausible is found.
    Cached in Redis — ticker <-> company-name mappings barely ever change."""

    async def fetch() -> list[str]:
        ticker, name = await asyncio.to_thread(_resolve_ticker_sync, company_input)
        return [ticker, name]

    ticker, name = await cached_call(
        "ticker_resolution",
        (company_input.strip().lower(),),
        settings.cache_ttl_ticker_seconds,
        fetch,
    )
    return ticker, name
