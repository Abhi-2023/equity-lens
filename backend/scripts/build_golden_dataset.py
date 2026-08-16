"""Golden eval dataset builder (P8).

Builds a LangSmith dataset of (company input) -> reference SEC-filing
citations, anchored to the exact 10-K chunks the filings_agent would
retrieve for that company. Ground truth is deliberately *not* hand-typed
facts (which drift out of sync with the filing and risk becoming opinions
dressed up as truth) — it's the literal `source` strings
(f"{TICKER} 10-K ({filing_date}) - {item}") the pipeline's own RAG chunker
produces, so a scorer can check "did the report's Company snapshot / Key
risks sections actually cite something from Item 1 / Item 1A" against the
same primary source the fact-checker grades against.

This only builds and uploads the dataset; a separate scorer (LangSmith
`evaluate()` target) that runs each example's `inputs` through the real
report pipeline and checks the output against `outputs` is the rest of P8.

Usage (inside the backend container, where GROQ_*/LANGCHAIN_* env + deps
live):
    docker exec equitylens_backend python scripts/build_golden_dataset.py
"""
from __future__ import annotations

import json
from pathlib import Path

from langsmith import Client

from app.rag.ingest import ingest_company_filings
from app.rag.vectorstore import add_documents, has_documents

DATASET_NAME = "equitylens-golden-v1"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "golden_dataset.json"

# Deliberately spread across sector + market cap rather than repeating
# whatever's already been demoed through the app, so the eval set actually
# exercises the filings agent/RAG chunker against varied 10-K structures.
COMPANIES = [
    "AAPL",  # tech / hardware
    "MSFT",  # tech / cloud
    "NVDA",  # tech / semis
    "TSLA",  # consumer discretionary / auto
    "JPM",   # financials
    "JNJ",   # healthcare
    "CVX",   # energy
    "WMT",   # consumer staples / retail
    "KO",    # consumer staples
    "BA",    # industrials
]

WANTED_ITEMS = ["Item 1", "Item 1A", "Item 7", "Item 7A"]


def build_entry(ticker: str) -> dict:
    # ingest_company_filings only hits SEC EDGAR — it doesn't touch Qdrant —
    # so re-fetching to get source metadata even when already indexed is safe.
    chunks = ingest_company_filings(ticker, wanted_items=WANTED_ITEMS)
    if not chunks:
        raise RuntimeError(f"No filing chunks found for {ticker}")
    if not has_documents(ticker):
        add_documents(ticker, chunks)

    by_item: dict[str, list[dict]] = {}
    for c in chunks:
        by_item.setdefault(c["item"], []).append(c)

    filing_date = chunks[0]["filing_date"]
    required_sources = sorted({c["source"] for c in chunks if c["item"] in ("Item 1", "Item 1A")})

    return {
        "inputs": {"company": ticker, "depth": "quick"},
        "outputs": {
            "ticker": ticker,
            "filing_date": filing_date,
            "required_citation_sources": required_sources,
            "has_item_1a_risk_factors": "Item 1A" in by_item,
        },
        "metadata": {"chunk_count": len(chunks), "items_present": sorted(by_item)},
    }


def main() -> None:
    entries = []
    for ticker in COMPANIES:
        print(f"Building entry for {ticker}...")
        try:
            entries.append(build_entry(ticker))
        except Exception as exc:
            print(f"  skipped {ticker}: {exc}")

    if not entries:
        raise SystemExit("No entries built — nothing to upload.")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {OUT_PATH}")

    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Dataset '{DATASET_NAME}' already exists ({dataset.id}) — replacing its examples")
        existing_ids = [ex.id for ex in client.list_examples(dataset_id=dataset.id)]
        if existing_ids:
            client.delete_examples(existing_ids)
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description=(
                "Golden set for EquityLens report generation. One example per company; "
                "the reference output pins the exact SEC 10-K filing chunk sources "
                "(Item 1 / Item 1A) the filings agent should retrieve and the "
                "fact-checker's citations should trace back to — ground truth is "
                "primary-source-derived, not hand-typed, so it can't drift out of sync "
                "with the actual filing text the pipeline reads."
            ),
        )
        print(f"Created dataset '{DATASET_NAME}' ({dataset.id})")

    client.create_examples(dataset_id=dataset.id, examples=entries)
    print(f"Uploaded {len(entries)} examples to LangSmith dataset '{DATASET_NAME}'")


if __name__ == "__main__":
    main()
