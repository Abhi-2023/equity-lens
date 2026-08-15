import pytest
from sqlalchemy import select

from app.db import Report, ReportJob, session_scope


@pytest.mark.asyncio
async def test_create_job_and_report_round_trip(db):
    async with session_scope() as session:
        job = ReportJob(company_input="Tesla", depth="standard")
        session.add(job)
        await session.flush()
        job_id = job.id

    async with session_scope() as session:
        fetched_job = await session.get(ReportJob, job_id)
        assert fetched_job.company_input == "Tesla"
        assert fetched_job.status.value == "running"

        report = Report(
            job_id=job_id,
            company="Tesla",
            ticker="TSLA",
            sections={"company_snapshot": {"content": "x", "citations": [], "groundedness": "verified"}},
        )
        session.add(report)

    async with session_scope() as session:
        result = await session.execute(select(Report).where(Report.job_id == job_id))
        fetched_report = result.scalar_one()
        assert fetched_report.ticker == "TSLA"
        assert fetched_report.sections["company_snapshot"]["groundedness"] == "verified"
