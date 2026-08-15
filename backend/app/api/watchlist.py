"""Watchlist routes (Section 2.4).

Grid of saved companies with last-updated timestamp and a headline metric
(price change, key risk flag). Entries here are what the scheduler in
`app/services/watchlist_scheduler.py` (Section 2.4/7) auto-refreshes.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.cache import cached_call
from app.config import settings
from app.db import Report, WatchlistEntry, session_scope
from app.graph.ticker_resolution import resolve_ticker
from app.mcp_servers.finance_client import call_finance_tool
from app.schemas import AddWatchlistRequest, WatchlistEntryResponse

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _tool_text(result) -> str:
    if isinstance(result, list) and result and isinstance(result[0], dict) and "text" in result[0]:
        return result[0]["text"]
    return json.dumps(result)


async def _live_price(ticker: str) -> tuple[float | None, float | None]:
    async def fetch() -> str:
        result = await call_finance_tool("get_stock_price", ticker=ticker)
        return _tool_text(result)

    try:
        text = await cached_call(
            "finance_mcp:get_stock_price", (ticker,), settings.cache_ttl_market_seconds, fetch
        )
        data = json.loads(text)
        return data.get("last_price"), data.get("day_change_pct")
    except Exception:
        return None, None


async def _latest_report_summary(session, ticker: str) -> tuple[str | None, int | None]:
    result = await session.execute(
        select(Report).where(Report.ticker == ticker).order_by(Report.created_at.desc()).limit(1)
    )
    report = result.scalar_one_or_none()
    if report is None:
        return None, None
    flagged = sum(1 for s in report.sections.values() if s.get("groundedness") == "flagged")
    return report.id, flagged


async def _to_response(session, entry: WatchlistEntry) -> WatchlistEntryResponse:
    last_price, day_change_pct = await _live_price(entry.ticker)
    latest_report_id, flagged = await _latest_report_summary(session, entry.ticker)
    return WatchlistEntryResponse(
        id=entry.id,
        ticker=entry.ticker,
        company=entry.company,
        added_at=entry.added_at,
        last_refreshed_at=entry.last_refreshed_at,
        refresh_cadence_days=entry.refresh_cadence_days,
        last_price=last_price,
        day_change_pct=day_change_pct,
        flagged_sections=flagged,
        latest_report_id=latest_report_id,
    )


@router.get("", response_model=list[WatchlistEntryResponse])
async def list_watchlist() -> list[WatchlistEntryResponse]:
    async with session_scope() as session:
        result = await session.execute(select(WatchlistEntry).order_by(WatchlistEntry.added_at.desc()))
        entries = result.scalars().all()
        return [await _to_response(session, entry) for entry in entries]


@router.post("", response_model=WatchlistEntryResponse)
async def add_to_watchlist(request: AddWatchlistRequest) -> WatchlistEntryResponse:
    ticker, display_name = await resolve_ticker(request.company)

    async with session_scope() as session:
        existing = await session.execute(select(WatchlistEntry).where(WatchlistEntry.ticker == ticker))
        entry = existing.scalar_one_or_none()
        if entry is None:
            entry = WatchlistEntry(
                ticker=ticker, company=display_name, refresh_cadence_days=request.refresh_cadence_days
            )
            session.add(entry)
            try:
                await session.flush()
            except IntegrityError:
                # Lost a race with a concurrent add for the same ticker (e.g. a
                # double-click) — the other request's insert already committed,
                # so fall back to fetching it instead of erroring.
                await session.rollback()
                existing = await session.execute(select(WatchlistEntry).where(WatchlistEntry.ticker == ticker))
                entry = existing.scalar_one()
        return await _to_response(session, entry)


@router.delete("/{entry_id}", status_code=204)
async def remove_from_watchlist(entry_id: str) -> None:
    async with session_scope() as session:
        entry = await session.get(WatchlistEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Watchlist entry not found")
        await session.delete(entry)
