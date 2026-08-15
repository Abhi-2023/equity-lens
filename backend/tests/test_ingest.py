"""Pure-function tests for the filings ingestion/chunking pipeline — no network calls."""
from app.rag.ingest import chunk_text, html_to_text, split_into_items


def test_html_to_text_strips_tags_and_scripts():
    html = "<html><head><style>.x{}</style></head><body><p>Hello</p><script>evil()</script><p>World</p></body></html>"
    text = html_to_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "evil" not in text


def test_split_into_items_groups_by_item_header():
    text = "Some preamble text\nItem 1. Business\nWe make widgets.\nItem 1A. Risk Factors\nWidgets may break."
    sections = split_into_items(text)
    assert any(k.startswith("Item1") or k == "Item 1" for k in sections)
    joined = " ".join(sections.values())
    assert "widgets" in joined.lower()


def test_chunk_text_respects_size_and_overlap():
    text = "word " * 1000
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_text_short_text_returns_single_chunk():
    assert chunk_text("short text", chunk_size=1200) == ["short text"]


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("", chunk_size=1200) == []
