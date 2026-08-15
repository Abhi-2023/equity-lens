"""Evidence assembly step (Section 4 step 5).

Merges outputs from the three parallel agents into a single evidence bundle,
re-numbering citation ids so they're unique across the whole bundle, and
drops news items that just restate something already in the filings
(cheap word-overlap heuristic — good enough to catch "company confirms
Q3 revenue of $X" showing up in both a press release and the 10-K).
"""
from __future__ import annotations

from langsmith import traceable

from app.graph.state import EvidenceItem, ResearchState

_DEDUP_OVERLAP_THRESHOLD = 0.6


def _word_set(text: str) -> set[str]:
    return {w.lower() for w in text.split() if len(w) > 4}


def _is_near_duplicate(candidate: EvidenceItem, existing: list[EvidenceItem]) -> bool:
    candidate_words = _word_set(candidate["text"])
    if not candidate_words:
        return False
    for item in existing:
        other_words = _word_set(item["text"])
        if not other_words:
            continue
        overlap = len(candidate_words & other_words) / min(len(candidate_words), len(other_words))
        if overlap >= _DEDUP_OVERLAP_THRESHOLD:
            return True
    return False


@traceable(name="evidence_assembly", run_type="chain")
async def evidence_assembly_node(state: ResearchState) -> dict:
    filings = state.get("filings_evidence", [])
    market = state.get("market_evidence", [])
    news = state.get("news_evidence", [])

    kept_news = [n for n in news if not _is_near_duplicate(n, filings)]

    bundle: list[EvidenceItem] = []
    for i, item in enumerate(filings + market + kept_news, start=1):
        bundle.append({**item, "id": f"E{i}"})

    return {"evidence_bundle": bundle}
