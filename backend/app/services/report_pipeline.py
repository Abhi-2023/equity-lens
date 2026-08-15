"""Orchestrates a report job's background run (Section 4 steps 2-8).

Kicked off by the `/reports` route as a FastAPI BackgroundTask — lives
outside `app/api/` because it's pipeline/business logic, not routing.
"""
from __future__ import annotations

import logging

from app.db import JobStatus, ReportJob, session_scope
from app.events import bus
from app.graph.graph import build_graph

logger = logging.getLogger("equitylens")


async def create_report_job(company_input: str, depth: str) -> str:
    """Creates the ReportJob row and returns its id. Callers (the /reports
    route, the watchlist scheduler) are responsible for actually running the
    pipeline via `run_report_job` — kept separate so the route can return
    immediately while the pipeline runs as a background task."""
    async with session_scope() as session:
        job = ReportJob(company_input=company_input, depth=depth)
        session.add(job)
        await session.flush()
        return job.id


async def run_report_job(job_id: str, company_input: str, ticker: str | None, depth: str) -> None:
    graph = build_graph()
    try:
        await graph.ainvoke(
            {
                "job_id": job_id,
                "company_input": company_input,
                "ticker": ticker,
                "depth": depth,
                "correction_passes": 0,
            },
            config={
                # Groups every @traceable node call below into one LangSmith trace
                # per report job, tagged so runs are filterable by depth/company.
                "run_name": "equitylens_report",
                "tags": ["equitylens", depth],
                "metadata": {"job_id": job_id, "company_input": company_input, "depth": depth},
            },
        )
    except Exception as exc:  # pragma: no cover - defensive, surfaced to the client via job status
        logger.exception("Report job %s failed", job_id)
        async with session_scope() as session:
            job = await session.get(ReportJob, job_id)
            if job:
                job.status = JobStatus.failed
                job.error = str(exc)
        await bus.publish(job_id, {"node": "pipeline", "status": "error", "message": str(exc)})
        await bus.close(job_id)
