"""Finalize node (Section 4 step 8).

Saves the verified report to the DB, marks the job completed, and sends the
completion event over SSE with the final payload — this is what lets the
frontend swap the trace panel for the Report View (Section 2.3/2.9).
"""
from __future__ import annotations

from langsmith import traceable
from sqlalchemy import func, select

from app.db import JobStatus, Report, ReportJob, session_scope
from app.events import bus
from app.graph.state import ResearchState


def _build_sections(state: ResearchState) -> dict:
    evidence_by_id = {item["id"]: item for item in state["evidence_bundle"]}
    verdict_by_section = {v["section"]: v for v in state.get("verification_results", [])}

    sections = {}
    for name, draft in state["draft_report"].items():
        citations = [
            {"id": cid, "source": evidence_by_id[cid]["source"], "url": evidence_by_id[cid]["url"]}
            for cid in draft["citation_ids"]
            if cid in evidence_by_id
        ]
        verdict = verdict_by_section.get(name)
        groundedness = "verified"
        if verdict and verdict["status"] == "flagged":
            groundedness = "flagged"
        elif not verdict:
            groundedness = "unverified"
        sections[name] = {"content": draft["content"], "citations": citations, "groundedness": groundedness}
    return sections


@traceable(name="finalize", run_type="chain")
async def finalize_node(state: ResearchState) -> dict:
    sections = _build_sections(state)
    flagged = sum(1 for s in sections.values() if s["groundedness"] == "flagged")

    async with session_scope() as session:
        job = await session.get(ReportJob, state["job_id"])
        job.status = JobStatus.completed
        job.groundedness_score = round(1 - flagged / max(len(sections), 1), 2)

        prior_count = await session.scalar(
            select(func.count()).select_from(Report).where(Report.ticker == state["ticker"])
        )

        report = Report(
            job_id=state["job_id"],
            company=state["company_input"],
            ticker=state["ticker"],
            version=(prior_count or 0) + 1,
            sections=sections,
        )
        session.add(report)

    await bus.publish(
        state["job_id"],
        {
            "node": "finalize",
            "status": "completed",
            "message": (
                "All claims verified" if flagged == 0 else f"{flagged} section(s) flagged — review"
            ),
        },
    )
    await bus.close(state["job_id"])

    return {"final_report": sections}
