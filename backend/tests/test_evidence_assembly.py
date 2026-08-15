import pytest

from app.graph.nodes.evidence import evidence_assembly_node


def _item(id_, text, origin):
    return {"id": id_, "text": text, "source": f"src-{id_}", "origin": origin, "url": None}


@pytest.mark.asyncio
async def test_merges_all_three_sources_and_renumbers_ids():
    state = {
        "filings_evidence": [_item("F1", "Apple reported strong iPhone sales this quarter", "filings")],
        "market_evidence": [_item("M1", "Trailing PE ratio of 34.9", "market")],
        "news_evidence": [_item("N1", "Completely unrelated article about tariffs", "news")],
    }
    result = await evidence_assembly_node(state)
    bundle = result["evidence_bundle"]
    assert len(bundle) == 3
    assert [item["id"] for item in bundle] == ["E1", "E2", "E3"]


@pytest.mark.asyncio
async def test_drops_near_duplicate_news_against_filings():
    filings_text = "Apple reported record revenue growth driven by iPhone and Services momentum"
    state = {
        "filings_evidence": [_item("F1", filings_text, "filings")],
        "market_evidence": [],
        "news_evidence": [
            _item("N1", filings_text, "news"),  # near-identical -> should be dropped
            _item("N2", "Completely different topic about factory construction in Texas", "news"),
        ],
    }
    result = await evidence_assembly_node(state)
    origins = [item["origin"] for item in result["evidence_bundle"]]
    assert origins.count("news") == 1
    assert origins.count("filings") == 1
