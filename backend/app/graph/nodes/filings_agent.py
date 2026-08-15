"""Filings agent node (Section 4 step 4).

Hybrid retrieval (dense + keyword) over the chunked SEC filings for this
company. Ingests+indexes the company's latest 10-K on first request, then
runs a small set of targeted queries derived from the research plan.
"""
from __future__ import annotations

from langsmith import traceable

from app.graph.state import EvidenceItem, ResearchState
from app.graph.status import node_status
from app.rag.ingest import ingest_company_filings
from app.rag.vectorstore import add_documents, has_documents, hybrid_search

_ITEM_QUERIES = {
    "Item 1": "business description, products, segments, and markets served",
    "Item 1A": "key risk factors that could adversely affect the business",
    "Item 7": "management discussion and analysis of financial condition and results",
    "Item 7A": "quantitative and qualitative disclosures about market risk",
}


@traceable(name="filings_agent", run_type="chain")
async def filings_agent_node(state: ResearchState) -> dict:
    ticker = state["ticker"]
    plan = state["plan"]

    async with node_status(state["job_id"], "filings_agent", f"Retrieving SEC filings for {ticker}...") as status:
        if not has_documents(ticker):
            await status.message(f"No cached filing found — pulling latest 10-K for {ticker} from SEC EDGAR")
            chunks = ingest_company_filings(ticker, wanted_items=plan["filing_sections"])
            add_documents(ticker, chunks)
            await status.message(f"Indexed {len(chunks)} filing chunks")

        evidence: list[EvidenceItem] = []
        counter = 0
        for item in plan["filing_sections"]:
            query = _ITEM_QUERIES.get(item, item)
            await status.message(f"Searching filings for: {query}")
            hits = hybrid_search(ticker, query, k=4)
            for hit in hits:
                counter += 1
                evidence.append(
                    EvidenceItem(
                        id=f"F{counter}",
                        text=hit["text"],
                        source=hit["source"],
                        origin="filings",
                        url=hit.get("url") or None,
                    )
                )

        return {"filings_evidence": evidence}
