"""Planner agent node (Section 4 step 3, Section 6).

Reads the request and produces a research plan: which filings to pull,
whether live price/fundamentals are needed, whether recent news should be
checked, and what the final report should emphasize (e.g. a pre-earnings
company gets an earnings-outlook section).
"""
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from app.graph.llm import get_llm
from app.graph.state import ResearchState
from app.graph.status import node_status
from app.graph.ticker_resolution import resolve_ticker

_DEPTH_TO_ITEM_COUNT = {"quick": 1, "standard": 2, "deep": 4}

_PLANNER_SYSTEM_PROMPT = """You are the planning agent for EquityLens, an equity-research \
assistant. Given a company and a requested report depth, decide the research plan: which \
SEC 10-K Item sections matter most (e.g. "Item 1" business description, "Item 1A" risk \
factors, "Item 7" MD&A), whether live market data is needed, whether recent news should be \
checked, and what the report should emphasize. Micro-caps and companies with thin analyst \
coverage should skip speculative "market outlook" framing; pre-earnings companies should \
emphasize an earnings-outlook angle."""


class PlanSchema(BaseModel):
    filing_sections: list[str] = Field(description="SEC 10-K Item labels to retrieve, e.g. ['Item 1', 'Item 1A']")
    needs_live_market_data: bool = Field(description="Whether to call the Finance MCP tools")
    needs_news: bool = Field(description="Whether to search recent news")
    emphasis: str = Field(description="One short phrase describing what the report should emphasize")
    rationale: str = Field(description="One or two sentences explaining the plan")


@traceable(name="planner", run_type="chain")
async def planner_node(state: ResearchState) -> dict:
    async with node_status(state["job_id"], "planner", "Reading request and drafting research plan...") as status:
        ticker, display_name = await resolve_ticker(state["company_input"])
        await status.message(f"Resolved '{state['company_input']}' -> {ticker} ({display_name})")

        depth = state.get("depth", "standard")
        llm = get_llm().with_structured_output(PlanSchema)
        plan: PlanSchema = await llm.ainvoke(
            [
                ("system", _PLANNER_SYSTEM_PROMPT),
                (
                    "human",
                    f"Company: {display_name} ({ticker})\n"
                    f"Report depth: {depth} (roughly {_DEPTH_TO_ITEM_COUNT[depth]} filing sections)\n"
                    "Produce the research plan.",
                ),
            ]
        )

        return {
            "ticker": ticker,
            "plan": {
                "pull_filings": True,
                "filing_sections": plan.filing_sections or ["Item 1", "Item 1A"],
                "needs_live_market_data": plan.needs_live_market_data,
                "needs_news": plan.needs_news,
                "emphasis": plan.emphasis,
                "rationale": plan.rationale,
            },
        }
