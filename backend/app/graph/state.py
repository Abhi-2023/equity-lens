"""Shared LangGraph state object (Section 6 of the spec).

Carries: request, plan, evidence bundle (list of {text, source, url}), draft
report, verification results — passed between every node in the graph.
"""
from __future__ import annotations

from typing import Any, TypedDict


class EvidenceItem(TypedDict):
    id: str  # short citation key, e.g. "F1", "M2", "N3"
    text: str
    source: str  # human-readable source, e.g. "10-K Item 1A (Risk Factors)"
    origin: str  # "filings" | "market" | "news"
    url: str | None


class ResearchPlan(TypedDict):
    pull_filings: bool
    filing_sections: list[str]  # e.g. ["Item 1", "Item 1A"]
    needs_live_market_data: bool
    needs_news: bool
    emphasis: str  # e.g. "pre-earnings outlook", "standard"
    rationale: str


class SectionDraft(TypedDict):
    content: str
    citation_ids: list[str]


class VerificationResult(TypedDict):
    section: str
    status: str  # "verified" | "flagged"
    notes: str


class ResearchState(TypedDict, total=False):
    # request
    job_id: str
    company_input: str
    ticker: str | None
    depth: str  # "quick" | "standard" | "deep"

    # planner output
    plan: ResearchPlan

    # parallel agent outputs
    filings_evidence: list[EvidenceItem]
    market_evidence: list[EvidenceItem]
    news_evidence: list[EvidenceItem]

    # merged
    evidence_bundle: list[EvidenceItem]

    # synthesizer output: section name -> draft
    draft_report: dict[str, SectionDraft]

    # fact-checker output
    verification_results: list[VerificationResult]
    correction_passes: int

    # final
    final_report: dict[str, Any]
    tokens_used: int
    tool_call_count: int
