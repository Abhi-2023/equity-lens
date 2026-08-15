"""P8 eval harness: runs the real report pipeline against the golden dataset
(`equitylens-golden-v1`, built by scripts/build_golden_dataset.py) and scores
it in LangSmith with three evaluators:

  - ticker_correctness   deterministic: did ticker resolution land on the
                          expected symbol.
  - citation_coverage     deterministic: did the evidence bundle actually
                          include a chunk from each filing item
                          (Item 1 / Item 1A) the golden example requires.
  - llm_judge_groundedness  LLM-as-judge: an independent grading pass (NOT
                          the pipeline's own fact-checker — a fresh
                          uncached call with its own skeptical prompt) that
                          re-reads each section against only its cited
                          evidence text and scores how well the claims are
                          actually supported.

Usage (inside the backend container, where GROQ_*/LANGCHAIN_* env + deps
live):
    docker exec equitylens_backend python scripts/run_eval.py
"""
from __future__ import annotations

import asyncio

from langsmith import aevaluate
from pydantic import BaseModel, Field

from app.graph.graph import build_graph
from app.llm.gateway import get_llm_gateway
from app.llm.types import TaskComplexity
from app.services.report_pipeline import create_report_job

DATASET_NAME = "equitylens-golden-v1"

_JUDGE_SYSTEM_PROMPT = """You are an independent grading judge for an equity-research report \
generator. You did NOT write this report — you are auditing it after the fact, so do not give it \
the benefit of the doubt. For each section below, compare its prose against ONLY the cited \
evidence text given for that section (ignore any outside knowledge you have about the company). \
Score how well-grounded the section is:
5 = every factual claim is directly traceable to the cited evidence
3 = mostly supported, but has minor unsupported embellishment or an unverifiable figure
1 = fabricated, or contradicts the cited evidence
If a section explicitly states the evidence was insufficient and makes no concrete factual claims, \
score it 5 — honest abstention is not a grounding failure, fabrication is."""


class JudgeSectionVerdict(BaseModel):
    section: str
    score: int = Field(description="1 (fabricated/unsupported) to 5 (fully grounded)")
    reasoning: str


class JudgeReportVerdict(BaseModel):
    verdicts: list[JudgeSectionVerdict]


async def judge_report(ticker: str, sections: dict) -> dict[str, dict]:
    parts = []
    for name, s in sections.items():
        evidence = s["cited_evidence_text"] or "(no cited evidence)"
        parts.append(f"### {name}\n{s['content']}\n\nCited evidence:\n{evidence}")
    draft_text = "\n\n".join(parts)

    llm = get_llm_gateway().with_structured_output(
        JudgeReportVerdict, task=TaskComplexity.SIMPLE, cache_scope=f"eval:{ticker}", use_cache=False
    )
    result: JudgeReportVerdict = await llm.ainvoke(
        [("system", _JUDGE_SYSTEM_PROMPT), ("human", draft_text)]
    )
    return {v.section: v.model_dump() for v in result.verdicts}


async def target(inputs: dict) -> dict:
    """Runs one golden-dataset example through the real graph — same code
    path as a live `POST /reports` — and returns the pieces the evaluators
    below need."""
    company = inputs["company"]
    depth = inputs.get("depth", "quick")

    job_id = await create_report_job(company, depth)
    graph = build_graph()
    final_state = await graph.ainvoke(
        {
            "job_id": job_id,
            "company_input": company,
            "ticker": None,
            "depth": depth,
            "correction_passes": 0,
        },
        config={
            "run_name": "equitylens_eval_report",
            "tags": ["equitylens", "eval", depth],
            "metadata": {"job_id": job_id, "company_input": company, "depth": depth, "eval": True},
        },
    )

    evidence_by_id = {e["id"]: e for e in final_state["evidence_bundle"]}
    sections_out = {}
    for name, section in final_state["final_report"].items():
        cited_ids = [c["id"] for c in section["citations"]]
        cited_text = "\n".join(
            f"[{cid}] {evidence_by_id[cid]['text']}" for cid in cited_ids if cid in evidence_by_id
        )
        sections_out[name] = {
            "content": section["content"],
            "groundedness": section["groundedness"],
            "citation_sources": [c["source"] for c in section["citations"]],
            "cited_evidence_text": cited_text,
        }

    return {
        "ticker": final_state.get("ticker"),
        "sections": sections_out,
        "all_evidence_sources": sorted({e["source"] for e in final_state["evidence_bundle"]}),
    }


def ticker_correctness(outputs: dict, reference_outputs: dict) -> dict:
    expected = reference_outputs.get("ticker")
    actual = outputs.get("ticker")
    return {
        "key": "ticker_correctness",
        "score": 1.0 if actual == expected else 0.0,
        "comment": f"expected {expected}, resolved {actual}",
    }


def citation_coverage(outputs: dict, reference_outputs: dict) -> dict:
    """Checks by filing *item* (Item 1 / Item 1A), not the exact source
    string, since a new 10-K could get filed between golden-dataset build
    time and eval time — the filing date in `required_citation_sources`
    would then legitimately differ from what the pipeline retrieves today."""
    required = reference_outputs.get("required_citation_sources", [])
    if not required:
        return {"key": "citation_coverage", "score": 1.0, "comment": "no required sources"}

    required_items = {src.rsplit("—", 1)[-1].strip() for src in required}
    actual_sources = outputs.get("all_evidence_sources", [])
    covered = {item for item in required_items if any(item in src for src in actual_sources)}
    missing = required_items - covered

    return {
        "key": "citation_coverage",
        "score": len(covered) / len(required_items),
        "comment": "all covered" if not missing else f"missing evidence for: {sorted(missing)}",
    }


async def llm_judge_groundedness(inputs: dict, outputs: dict) -> dict:
    sections = outputs.get("sections", {})
    if not sections:
        return {"key": "llm_judge_groundedness", "score": 0.0, "comment": "no sections to judge"}

    ticker = outputs.get("ticker") or inputs.get("company")
    verdicts = await judge_report(ticker, sections)
    scores = [v["score"] for v in verdicts.values()]
    if not scores:
        return {"key": "llm_judge_groundedness", "score": 0.0, "comment": "judge returned no verdicts"}

    normalized = (sum(scores) / len(scores) - 1) / 4  # map 1..5 -> 0..1
    low = [f"{name} ({v['score']}/5): {v['reasoning']}" for name, v in verdicts.items() if v["score"] <= 2]
    comment = "; ".join(low) if low else "all sections well-grounded per independent judge"

    return {"key": "llm_judge_groundedness", "score": round(normalized, 2), "comment": comment}


async def main() -> None:
    await aevaluate(
        target,
        data=DATASET_NAME,
        evaluators=[ticker_correctness, citation_coverage, llm_judge_groundedness],
        experiment_prefix="equitylens-eval",
        max_concurrency=3,
        metadata={"harness": "P8-golden-eval"},
    )


if __name__ == "__main__":
    asyncio.run(main())
