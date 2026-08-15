"""Pydantic request/response models for the public API."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, Field

from app.db import JobStatus, ReportDepth


class CreateReportRequest(BaseModel):
    company: str = Field(..., description="Company name or ticker, e.g. 'AAPL' or 'Tesla'")
    depth: ReportDepth = ReportDepth.standard


class CreateReportResponse(BaseModel):
    job_id: str
    status: JobStatus
    stream_url: str


class ReportJobStatusResponse(BaseModel):
    job_id: str
    company_input: str
    ticker: str | None
    depth: ReportDepth
    status: JobStatus
    error: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ReportSection(BaseModel):
    content: str
    citations: list[dict] = Field(default_factory=list)
    groundedness: str = "unverified"  # "verified" | "flagged" | "unverified"


class ReportResponse(BaseModel):
    id: str
    job_id: str
    company: str
    ticker: str | None
    version: int
    sections: dict[str, ReportSection]
    created_at: datetime.datetime


class ReportSummary(BaseModel):
    """One row in a company's report history (Section 2.5)."""

    id: str
    job_id: str
    version: int
    flagged_sections: int
    created_at: datetime.datetime


class RecentReportSummary(BaseModel):
    """One row in the Search screen's recent-reports list (Section 2.1)."""

    id: str
    job_id: str
    company: str
    ticker: str | None
    version: int
    flagged_sections: int
    created_at: datetime.datetime


class SectionDiff(BaseModel):
    changed: bool
    diff_lines: list[str] = Field(default_factory=list)


class ReportDiffResponse(BaseModel):
    ticker: str
    from_report: ReportSummary
    to_report: ReportSummary
    sections: dict[str, SectionDiff]


class AddWatchlistRequest(BaseModel):
    company: str = Field(..., description="Company name or ticker, e.g. 'AAPL' or 'Tesla'")
    refresh_cadence_days: int = 7


class WatchlistEntryResponse(BaseModel):
    id: str
    ticker: str
    company: str
    added_at: datetime.datetime
    last_refreshed_at: datetime.datetime | None
    refresh_cadence_days: int
    last_price: float | None = None
    day_change_pct: float | None = None
    flagged_sections: int | None = None
    latest_report_id: str | None = None
