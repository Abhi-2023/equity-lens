"""Report job routes (Section 4 steps 1-2, Section 8).

POST /reports kicks off a report job and streams status over SSE while the
LangGraph pipeline (see `app/services/report_pipeline.py`) runs in the
background.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.db import JobStatus, Report, ReportJob, session_scope
from app.events import stream_job_events
from app.schemas import (
    CreateReportRequest,
    CreateReportResponse,
    RecentReportSummary,
    ReportJobStatusResponse,
    ReportResponse,
)
from app.services.report_pipeline import create_report_job, run_report_job

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=CreateReportResponse)
async def create_report(
    request: CreateReportRequest, background_tasks: BackgroundTasks
) -> CreateReportResponse:
    job_id = await create_report_job(request.company, request.depth.value)
    background_tasks.add_task(run_report_job, job_id, request.company, None, request.depth.value)

    return CreateReportResponse(
        job_id=job_id, status=JobStatus.running, stream_url=f"/reports/{job_id}/stream"
    )


@router.get("", response_model=list[RecentReportSummary])
async def list_recent_reports(limit: int = 5) -> list[RecentReportSummary]:
    """Recent reports list for the Search screen (Section 2.1)."""
    async with session_scope() as session:
        result = await session.execute(select(Report).order_by(Report.created_at.desc()).limit(limit))
        reports = result.scalars().all()
        return [
            RecentReportSummary(
                id=r.id,
                job_id=r.job_id,
                company=r.company,
                ticker=r.ticker,
                version=r.version,
                flagged_sections=sum(1 for s in r.sections.values() if s.get("groundedness") == "flagged"),
                created_at=r.created_at,
            )
            for r in reports
        ]


@router.get("/by-id/{report_id}", response_model=ReportResponse)
async def get_report_by_id(report_id: str) -> ReportResponse:
    """Fetch a report directly by its own id (as opposed to its job id) —
    used by the Watchlist/History views, which only know report ids."""
    async with session_scope() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return ReportResponse(
            id=report.id,
            job_id=report.job_id,
            company=report.company,
            ticker=report.ticker,
            version=report.version,
            sections=report.sections,
            created_at=report.created_at,
        )


@router.get("/{job_id}/stream")
async def stream_report(job_id: str):
    async def event_generator():
        async for event in stream_job_events(job_id):
            # sse_starlette serializes dict `data` with str() (Python repr,
            # single-quoted) rather than JSON — encode explicitly so clients
            # can just JSON.parse() the event.
            yield {"event": "status", "data": json.dumps(event, default=str)}

    return EventSourceResponse(event_generator())


@router.get("/{job_id}/status", response_model=ReportJobStatusResponse)
async def get_report_status(job_id: str) -> ReportJobStatusResponse:
    async with session_scope() as session:
        job = await session.get(ReportJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return ReportJobStatusResponse(
            job_id=job.id,
            company_input=job.company_input,
            ticker=job.ticker,
            depth=job.depth,
            status=job.status,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


@router.get("/{job_id}", response_model=ReportResponse)
async def get_report(job_id: str) -> ReportResponse:
    async with session_scope() as session:
        result = await session.execute(select(Report).where(Report.job_id == job_id))
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found (job may still be running)")
        return ReportResponse(
            id=report.id,
            job_id=report.job_id,
            company=report.company,
            ticker=report.ticker,
            version=report.version,
            sections=report.sections,
            created_at=report.created_at,
        )
