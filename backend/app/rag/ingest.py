"""SEC filings ingestion & chunking pipeline (Section 3 / 4 step 4 of the spec).

Pulls the latest 10-K for a ticker straight from SEC EDGAR (no API key required —
EDGAR only asks for a descriptive User-Agent), strips it to plain text, splits it
into Item-tagged sections (Item 1, Item 1A, ...), and chunks each section for
retrieval. Output feeds `rag/vectorstore.py`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser

import requests

SEC_HEADERS = {"User-Agent": "EquityLens research-tool contact@equitylens.dev"}
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"

_ITEM_HEADER_RE = re.compile(
    r"^\s*(Item\s+\d+[A-Z]?\.?)\s*[-–—\.]?\s*(.{0,80})", re.IGNORECASE
)

_ticker_cik_cache: dict[str, int] | None = None


class _TextExtractor(HTMLParser):
    """Minimal HTML -> text stripper (avoids a bs4 dependency for a simple job)."""

    _SKIP_TAGS = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in ("p", "div", "tr", "br", "li"):
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.chunks.append(data)

    def text(self) -> str:
        return "".join(self.chunks)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    raw = parser.text()
    lines = [line.strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _load_ticker_cik_map() -> dict[str, int]:
    global _ticker_cik_cache
    if _ticker_cik_cache is not None:
        return _ticker_cik_cache
    resp = requests.get(_TICKER_MAP_URL, headers=SEC_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _ticker_cik_cache = {row["ticker"].upper(): row["cik_str"] for row in data.values()}
    return _ticker_cik_cache


def resolve_cik(ticker: str) -> int | None:
    return _load_ticker_cik_map().get(ticker.upper())


@dataclass
class FilingRef:
    cik: int
    accession_number: str
    primary_document: str
    filing_date: str
    form: str

    @property
    def url(self) -> str:
        accession_nodash = self.accession_number.replace("-", "")
        return _ARCHIVES_BASE.format(
            cik=self.cik, accession_nodash=accession_nodash, document=self.primary_document
        )


def find_latest_10k(cik: int, form: str = "10-K") -> FilingRef | None:
    resp = requests.get(_SUBMISSIONS_URL.format(cik=cik), headers=SEC_HEADERS, timeout=15)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]
    for i, filed_form in enumerate(recent["form"]):
        if filed_form == form:
            return FilingRef(
                cik=cik,
                accession_number=recent["accessionNumber"][i],
                primary_document=recent["primaryDocument"][i],
                filing_date=recent["filingDate"][i],
                form=filed_form,
            )
    return None


def fetch_filing_text(filing: FilingRef) -> str:
    time.sleep(0.15)  # be polite to EDGAR's rate limit
    resp = requests.get(filing.url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return html_to_text(resp.text)


def split_into_items(text: str) -> dict[str, str]:
    """Best-effort split of a 10-K body into {'Item 1': '...', 'Item 1A': '...'}."""
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current = "Preamble"
    sections[current] = []
    for line in lines:
        match = _ITEM_HEADER_RE.match(line)
        if match and len(line) < 120:
            current = match.group(1).rstrip(".").replace(" ", " ").title().replace(" ", "")
            current = re.sub(r"(Item)(\d)", r"\1 \2", current)
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def ingest_company_filings(
    ticker: str, wanted_items: list[str] | None = None
) -> list[dict]:
    """Returns a list of chunk dicts: {text, source, item, url, ticker, filing_date}."""
    cik = resolve_cik(ticker)
    if cik is None:
        raise ValueError(f"No SEC CIK found for ticker '{ticker}'")
    filing = find_latest_10k(cik)
    if filing is None:
        raise ValueError(f"No 10-K found for {ticker} (CIK {cik})")

    text = fetch_filing_text(filing)
    items = split_into_items(text)
    if wanted_items:
        items = {k: v for k, v in items.items() if any(w.lower() in k.lower() for w in wanted_items)}

    out: list[dict] = []
    for item_name, item_text in items.items():
        for chunk in chunk_text(item_text):
            out.append(
                {
                    "text": chunk,
                    "source": f"{ticker.upper()} 10-K ({filing.filing_date}) — {item_name}",
                    "item": item_name,
                    "url": filing.url,
                    "ticker": ticker.upper(),
                    "filing_date": filing.filing_date,
                }
            )
    return out
