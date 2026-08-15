"""Watchlist auto-refresh scheduler (Section 2.4/7).

Stands in for "Cloud Scheduler triggers a Cloud Run job on a cadence to
refresh watchlisted companies through the same pipeline" (Section 8) —
same idea, running as an in-process APScheduler job instead of a separate
GCP-managed cron, since this app is self-hosted via docker-compose.

Every tick, checks each WatchlistEntry against its own
`refresh_cadence_days` and kicks off a full report regeneration (the exact
same pipeline a manual `POST /reports` triggers) for any that are due.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.db import ReportDepth, WatchlistEntry, session_scope
from app.services.report_pipeline import create_report_job, run_report_job

logger = logging.getLogger("equitylens")

_CHECK_INTERVAL_MINUTES = 60
_scheduler: AsyncIOScheduler | None = None


def _is_due(entry: WatchlistEntry, now: datetime.datetime) -> bool:
    if entry.last_refreshed_at is None:
        return True
    age = now - entry.last_refreshed_at
    return age >= datetime.timedelta(days=entry.refresh_cadence_days)


async def _refresh_entry(entry_id: str, company_input: str) -> None:
    job_id = await create_report_job(company_input, ReportDepth.standard.value)
    logger.info("Watchlist auto-refresh: %s -> job %s", company_input, job_id)
    await run_report_job(job_id, company_input, None, ReportDepth.standard.value)

    async with session_scope() as session:
        entry = await session.get(WatchlistEntry, entry_id)
        if entry:
            entry.last_refreshed_at = datetime.datetime.now(datetime.timezone.utc)


async def check_and_refresh_due_entries() -> int:
    """Returns the number of refreshes kicked off — used directly by tests
    and by the periodic job below."""
    now = datetime.datetime.now(datetime.timezone.utc)
    async with session_scope() as session:
        result = await session.execute(select(WatchlistEntry))
        due = [e for e in result.scalars().all() if _is_due(e, now)]

    for entry in due:
        asyncio.create_task(_refresh_entry(entry.id, entry.company))
    return len(due)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_and_refresh_due_entries,
        trigger=IntervalTrigger(minutes=_CHECK_INTERVAL_MINUTES),
        id="watchlist_refresh",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Watchlist refresh scheduler started (checking every %sm)", _CHECK_INTERVAL_MINUTES)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
