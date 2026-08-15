"""Synthesizer agent node (Section 4 step 6, Section 5).

Writes the structured report strictly from the evidence bundle, inserting
inline citation markers ([E3], [E7], ...) back to each source chunk/tool
result. Instructed not to introduce facts absent from the evidence. On a
second pass (after the Fact-checker flags something) it only revises the
flagged sections, keeping verified ones untouched.
"""
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from app.graph.llm import get_llm
from app.graph.state import ResearchState
from app.graph.status import node_status

SECTION_NAMES = ["company_snapshot", "financial_health", "recent_developments", "key_risks", "outlook_notes"]

_SYNTH_SYSTEM_PROMPT = """You are the synthesizer agent for EquityLens, an equity-research \
assistant. Write a structured report using ONLY the provided evidence bundle. Every factual \
sentence must end with one or more citation markers like [E3] or [E1][E7] referencing the \
evidence id(s) it came from. Do not introduce any fact, figure, or claim that is not present \
in the evidence bundle. If the evidence is insufficient for a section, say so plainly rather \
than speculating.

Sections to produce:
- company_snapshot: name, ticker, sector, one-paragraph business description
- financial_health: revenue/earnings trend, key ratios, valuation vs. sector
- recent_developments: notable news from the last 30-90 days, summarized
- key_risks: top risk factors as disclosed by the company itself
- outlook_notes: neutral, evidence-based observations — explicitly NOT investment advice

This is a research/summarization tool, not an advisory service. Never phrase outlook_notes as \
a recommendation to buy, sell, or hold."""


class SectionSchema(BaseModel):
    content: str = Field(description="The section text, with inline [Eid] citation markers")
    citation_ids: list[str] = Field(description="Evidence ids cited in this section, e.g. ['E1', 'E3']")


class ReportSchema(BaseModel):
    company_snapshot: SectionSchema
    financial_health: SectionSchema
    recent_developments: SectionSchema
    key_risks: SectionSchema
    outlook_notes: SectionSchema


def _format_evidence(bundle: list[dict]) -> str:
    return "\n\n".join(f"[{item['id']}] ({item['source']})\n{item['text']}" for item in bundle)


@traceable(name="synthesizer", run_type="chain")
async def synthesizer_node(state: ResearchState) -> dict:
    async with node_status(state["job_id"], "synthesizer", "Drafting report from evidence bundle...") as status:
        evidence_text = _format_evidence(state["evidence_bundle"])
        plan = state["plan"]

        human_parts = [
            f"Company: {state['company_input']} ({state['ticker']})",
            f"Report emphasis: {plan['emphasis']}",
            f"Evidence bundle:\n{evidence_text}",
        ]

        verification = state.get("verification_results")
        if verification:
            flagged = [v for v in verification if v["status"] == "flagged"]
            if flagged:
                notes = "\n".join(f"- {v['section']}: {v['notes']}" for v in flagged)
                human_parts.append(
                    "The fact-checker flagged these sections in your previous draft — revise ONLY "
                    f"these sections to fix the issue, keep the rest as-is:\n{notes}"
                )
                await status.message(f"Revising {len(flagged)} flagged section(s) after fact-check")

        llm = get_llm().with_structured_output(ReportSchema)
        report: ReportSchema = await llm.ainvoke(
            [("system", _SYNTH_SYSTEM_PROMPT), ("human", "\n\n".join(human_parts))]
        )

        draft = {name: getattr(report, name).model_dump() for name in SECTION_NAMES}
        return {"draft_report": draft}
