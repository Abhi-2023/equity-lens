"""Fact-checker agent node (Section 4 step 7, Section 6).

Re-reads the draft claim by claim, checks each one against its cited
source in the evidence bundle, and either confirms it or flags it as
unsupported. The graph's conditional edge (see `graph.py`) sends flagged
drafts back to the Synthesizer for up to `MAX_FACT_CHECK_PASSES` passes.
"""
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from app.llm.gateway import get_llm_gateway
from app.llm.types import TaskComplexity
from app.graph.state import ResearchState
from app.graph.status import node_status

_FACT_CHECK_SYSTEM_PROMPT = """You are the fact-checker agent for EquityLens. For each report \
section, verify every citation-bearing sentence against the evidence text under the id(s) it \
cites. Flag a section as "flagged" if: a cited id doesn't support the claim, a claim has no \
citation, or a figure/number doesn't match the evidence. Otherwise mark it "verified". Be \
strict — this report is shown to users as fact-checked."""


class SectionVerdict(BaseModel):
    section: str
    status: str = Field(description="'verified' or 'flagged'")
    notes: str = Field(description="Why flagged, or 'all claims supported' if verified")


class VerificationSchema(BaseModel):
    verdicts: list[SectionVerdict]


def _format_draft_for_check(draft: dict, evidence_by_id: dict) -> str:
    parts = []
    for section, content in draft.items():
        cited = "\n".join(
            f"  [{cid}] {evidence_by_id[cid]['text']}" for cid in content["citation_ids"] if cid in evidence_by_id
        )
        parts.append(f"### {section}\n{content['content']}\n\nCited evidence:\n{cited}")
    return "\n\n".join(parts)


@traceable(name="fact_checker", run_type="chain")
async def fact_checker_node(state: ResearchState) -> dict:
    async with node_status(state["job_id"], "fact_checker", "Verifying claims against sources...") as status:
        evidence_by_id = {item["id"]: item for item in state["evidence_bundle"]}
        draft_text = _format_draft_for_check(state["draft_report"], evidence_by_id)

        # Same reasoning as the synthesizer: re-checking a revised draft must
        # genuinely re-run, not return a stale verdict cached against the
        # original (pre-revision) draft it's now meant to be re-verifying.
        is_first_pass = state.get("correction_passes", 0) == 0
        llm = get_llm_gateway().with_structured_output(
            VerificationSchema, task=TaskComplexity.SIMPLE, cache_scope=state["ticker"], use_cache=is_first_pass
        )
        result: VerificationSchema = await llm.ainvoke(
            [("system", _FACT_CHECK_SYSTEM_PROMPT), ("human", draft_text)]
        )

        verdicts = [v.model_dump() for v in result.verdicts]
        flagged_count = sum(1 for v in verdicts if v["status"] == "flagged")
        note = " (semantic cache)" if llm.cache_hit else f" (used {llm.last_model_used})" if llm.fell_back else ""
        await status.message(f"{len(verdicts) - flagged_count}/{len(verdicts)} sections verified{note}")

        return {
            "verification_results": verdicts,
            "correction_passes": state.get("correction_passes", 0) + 1,
        }
