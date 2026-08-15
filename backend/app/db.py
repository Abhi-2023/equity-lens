"""Async SQLAlchemy models and session management (Postgres via asyncpg).

Postgres is required — see Section 8 of the spec ("Cloud SQL (Postgres)").
Run it via `docker-compose up postgres` (or point DATABASE_URL at any
Postgres instance); there is no SQLite/local-file fallback.
"""
from __future__ import annotations

import datetime
import enum
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


class ReportDepth(str, enum.Enum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


class JobStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class ReportJob(Base):
    """One row per report request — created at Section 4 step 2 of the spec."""

    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_input: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    depth: Mapped[ReportDepth] = mapped_column(Enum(ReportDepth), default=ReportDepth.standard)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.running)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    langsmith_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    groundedness_score: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    report: Mapped["Report | None"] = relationship(back_populates="job", uselist=False)


class Report(Base):
    """The finished, cited report for a job (Section 5 of the spec)."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("report_jobs.id"), unique=True)
    company: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Structured per Section 5: company_snapshot, financial_health, recent_developments,
    # key_risks, outlook_notes — each {"content": str, "citations": [...], "groundedness": str}
    sections: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    job: Mapped[ReportJob] = relationship(back_populates="report")


class WatchlistEntry(Base):
    """Saved companies, auto-refreshed by the Cloud Scheduler job (Section 2.4)."""

    __tablename__ = "watchlist_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str] = mapped_column(String(16), unique=True)
    company: Mapped[str] = mapped_column(String(255))
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_refreshed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_cadence_days: Mapped[int] = mapped_column(Integer, default=7)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Usage: `async with session_scope() as session: ...` — commits on success,
    rolls back on exception, always closes."""
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_session() -> AsyncSession:
    """Raw session for callers that want manual commit/rollback control."""
    return SessionLocal()
