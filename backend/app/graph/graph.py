"""LangGraph wiring (Section 6 of the spec).

    planner -> {filings_agent, market_agent, news_agent} (parallel)
            -> evidence_assembly -> synthesizer -> fact_checker
            -> [conditional: back to synthesizer, or finalize] -> END

Up to `settings.max_fact_check_passes` correction passes before the report
ships regardless of outstanding flags (bounded loop, per Section 6).
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.graph.nodes.evidence import evidence_assembly_node
from app.graph.nodes.fact_checker import fact_checker_node
from app.graph.nodes.filings_agent import filings_agent_node
from app.graph.nodes.finalize import finalize_node
from app.graph.nodes.market_agent import market_agent_node
from app.graph.nodes.news_agent import news_agent_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.synthesizer import synthesizer_node
from app.graph.state import ResearchState


def _route_after_fact_check(state: ResearchState) -> str:
    flagged = [v for v in state.get("verification_results", []) if v["status"] == "flagged"]
    if flagged and state.get("correction_passes", 0) < settings.max_fact_check_passes:
        return "synthesizer"
    return "finalize"


@lru_cache
def build_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node)
    graph.add_node("filings_agent", filings_agent_node)
    graph.add_node("market_agent", market_agent_node)
    graph.add_node("news_agent", news_agent_node)
    graph.add_node("evidence_assembly", evidence_assembly_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("fact_checker", fact_checker_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "planner")

    # fan out
    graph.add_edge("planner", "filings_agent")
    graph.add_edge("planner", "market_agent")
    graph.add_edge("planner", "news_agent")

    # fan in
    graph.add_edge("filings_agent", "evidence_assembly")
    graph.add_edge("market_agent", "evidence_assembly")
    graph.add_edge("news_agent", "evidence_assembly")

    graph.add_edge("evidence_assembly", "synthesizer")
    graph.add_edge("synthesizer", "fact_checker")

    graph.add_conditional_edges(
        "fact_checker", _route_after_fact_check, {"synthesizer": "synthesizer", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)

    return graph.compile()
