"""History routes (Section 2.5).

Every generated report is stored and browsable, with a diff view showing
what changed since the last version for the same company.
"""
from __future__ import annotations

import difflib

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db import Report, session_scope
from app.schemas import ReportDiffResponse, ReportSummary, SectionDiff

router = APIRouter(tags=["history"])


def _summarize(report: Report) -> ReportSummary:
    flagged = sum(1 for s in report.sections.values() if s.get("groundedness") == "flagged")
    return ReportSummary(
        id=report.id,
        job_id=report.job_id,
        version=report.version,
        flagged_sections=flagged,
        created_at=report.created_at,
    )


@router.get("/companies/{ticker}/history", response_model=list[ReportSummary])
async def get_company_history(ticker: str) -> list[ReportSummary]:
    async with session_scope() as session:
        result = await session.execute(
            select(Report).where(Report.ticker == ticker.upper()).order_by(Report.version.desc())
        )
        reports = result.scalars().all()
        return [_summarize(r) for r in reports]


@router.get("/reports/{report_id}/diff/{other_report_id}", response_model=ReportDiffResponse)
async def diff_reports(report_id: str, other_report_id: str) -> ReportDiffResponse:
    async with session_scope() as session:
        from_report = await session.get(Report, other_report_id)  # older, by convention
        to_report = await session.get(Report, report_id)  # newer

        if from_report is None or to_report is None:
            raise HTTPException(status_code=404, detail="One or both reports not found")
        if from_report.ticker != to_report.ticker:
            raise HTTPException(status_code=400, detail="Reports are for different companies")

        section_names = set(from_report.sections) | set(to_report.sections)
        sections: dict[str, SectionDiff] = {}
        for name in section_names:
            old_text = from_report.sections.get(name, {}).get("content", "")
            new_text = to_report.sections.get(name, {}).get("content", "")
            if old_text == new_text:
                sections[name] = SectionDiff(changed=False)
                continue
            diff_lines = list(
                difflib.unified_diff(
                    old_text.split(". "),
                    new_text.split(". "),
                    fromfile=f"v{from_report.version}",
                    tofile=f"v{to_report.version}",
                    lineterm="",
                )
            )
            sections[name] = SectionDiff(changed=True, diff_lines=diff_lines)

        return ReportDiffResponse(
            ticker=to_report.ticker,
            from_report=_summarize(from_report),
            to_report=_summarize(to_report),
            sections=sections,
        )
