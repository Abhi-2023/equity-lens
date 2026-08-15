# EquityLens

Agentic market & company research analyst. Takes a company name or ticker and
produces a grounded, cited equity-research-style brief via a LangGraph
multi-agent pipeline (Planner → Filings/Market/News agents in parallel →
Synthesizer → Fact-checker), streamed live to the client over SSE.

Full product spec: `EquityLens_Application_Workflow.docx` (see task breakdown
in project history — P1-P7 are implemented; P8 eval harness and P9
Secret Manager/CI-CD are not).

## What's implemented

- **Backend API** (FastAPI): app setup in [backend/app/main.py](backend/app/main.py),
  routes in [backend/app/api/](backend/app/api/) (reports, watchlist, history/diff,
  SSE status stream), background pipeline orchestration in
  [backend/app/services/report_pipeline.py](backend/app/services/report_pipeline.py)
- **Frontend** (React + Vite, plain JS): Search screen, live agent trace
  panel, report view, watchlist dashboard, and history/diff view — all under
  [frontend/src/](frontend/src/)
- **Data layer**: Postgres via async SQLAlchemy + `asyncpg` — no SQLite/local
  fallback — [backend/app/db.py](backend/app/db.py)
- **Cache**: Redis, used for ticker resolution and Finance/News MCP tool
  results — [backend/app/cache.py](backend/app/cache.py)
- **RAG**: SEC EDGAR 10-K ingestion + chunking, hybrid dense (Qdrant) +
  keyword (BM25) retrieval, reranked by Cohere —
  [backend/app/rag/](backend/app/rag/)
- **MCP tool servers**: a custom Finance server (yfinance-backed) and a
  News/web-search server (DuckDuckGo-backed), each a real stdio MCP server
  with a LangChain client wrapper — [backend/app/mcp_servers/](backend/app/mcp_servers/)
- **Agent graph** (LangGraph): planner → {filings, market, news} (parallel)
  → evidence assembly → synthesizer → fact-checker, with a bounded
  correction loop back to the synthesizer — [backend/app/graph/](backend/app/graph/)
  Every node is `@traceable`, so a full run shows up as one nested trace in
  LangSmith (set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`).
- **LLM gateway with fallback** ([backend/app/llm/](backend/app/llm/)): every
  graph node calls the gateway instead of a single fixed Groq client. It
  routes across multiple Groq accounts (`GROQ_API_KEYS`, comma-separated —
  each with its own daily token budget) and, within each account, a model
  chain per task complexity — SIMPLE tasks (planner, fact-checker) prefer a
  small/fast model, COMPLEX tasks (synthesizer) prefer the larger model for
  quality. On a rate limit it puts that (account, model) into cooldown and
  falls to the next candidate; on an auth failure it skips the rest of that
  account's chain; transient errors get one retry. A semantic response cache
  (`llm_semantic_cache_enabled`) skips the LLM entirely on a near-duplicate
  request, scoped per-ticker to avoid cross-company collisions, and disabled
  for the fact-checker's correction-pass calls (a revision prompt is close
  enough to the original draft that the cache would otherwise silently hand
  back the unrevised draft).
- **Watchlist auto-refresh** (Section 2.4/7): an in-process APScheduler job
  (stands in for Cloud Scheduler + Cloud Run) that re-runs the pipeline for
  each watchlisted company on its own cadence —
  [backend/app/services/watchlist_scheduler.py](backend/app/services/watchlist_scheduler.py)
- **Infra**: Postgres, Redis, and Qdrant all run as real services — via
  `docker-compose.yml`, not embedded/local-file modes. Frontend and backend
  are both containerized with multi-stage Dockerfiles.

Everything above except the LLM- and Cohere-dependent steps has been
exercised end-to-end against live SEC EDGAR, Yahoo Finance, and DuckDuckGo
data. The LLM calls go through the gateway above and require `GROQ_API_KEYS`
(comma-separated; `GROQ_API_KEY` singular still works for a one-account
setup); retrieval reranking uses `COHERE_API_KEY` (retrieval still works
without it — falls back to the un-reranked RRF order).

## Running with Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env   # fill in GROQ_API_KEY, optionally COHERE_API_KEY / LangSmith
docker-compose up --build
```

This builds both the backend and frontend from multi-stage Dockerfiles and
brings them up alongside Postgres, Redis, and Qdrant as containers, wired
together by service name (see `docker-compose.yml`) — nothing running on the
host.

- Frontend: `http://localhost:8081`
- Backend API: `http://localhost:8002`

(Postgres/Redis/Qdrant are similarly remapped to 5433/6380/6335 on the host,
and the frontend/backend to 8081/8002 instead of the usual 80/8000 — see the
comments in `docker-compose.yml` — only because another project's stack on
this machine already holds the standard ports; adjust freely.)

`backend/.env` is read via `env_file` by both the `backend` and `postgres`
services (the same file used for host-direct runs, below); `DATABASE_URL`/
`REDIS_URL`/`QDRANT_URL` are injected directly by compose and always point
at the container hostnames, regardless of what's in `.env`. The frontend's
API base URL is baked in at *build* time (`VITE_API_BASE_URL` build arg —
browser JS can't resolve container-network hostnames, so it has to point at
the backend's host-mapped port).

## Running directly on the host (no Docker for app code)

Still requires Postgres/Redis/Qdrant as real services:

```bash
docker-compose up postgres redis qdrant   # infra only

cd backend
pip install -r requirements.txt
cp .env.example .env   # then fill in GROQ_API_KEY (URLs already default to localhost)
python -m uvicorn app.main:app --reload --port 8002
```

```bash
cd frontend
cp .env.example .env
npm install
npm run dev   # http://localhost:5173
```

Try the API directly:

```bash
curl -X POST http://127.0.0.1:8002/reports \
  -H "Content-Type: application/json" \
  -d '{"company": "AAPL", "depth": "quick"}'

# then, using the returned job_id:
curl -N http://127.0.0.1:8002/reports/<job_id>/stream   # live agent trace
curl http://127.0.0.1:8002/reports/<job_id>              # finished report
```

## Tests

Backend tests require Postgres reachable at `DATABASE_URL`
(`docker-compose up postgres`):

```bash
cd backend
pytest
```

## Evaluation (P8)

Two scripts, run inside the backend container so they share its
GROQ_*/LANGCHAIN_* env and installed deps:

```bash
docker exec equitylens_backend python scripts/build_golden_dataset.py  # (re)builds the golden dataset
docker exec equitylens_backend python scripts/run_eval.py              # runs the eval, uploads to LangSmith
```

- **`build_golden_dataset.py`** — pushes a LangSmith dataset
  (`equitylens-golden-v1`) with one example per company across a spread of
  sectors/market caps. The reference output for each isn't a hand-typed
  fact — it's the exact SEC 10-K filing-chunk `source` strings
  (`"{TICKER} 10-K ({date}) — {item}"`) the real ingestion pipeline
  ([backend/app/rag/ingest.py](backend/app/rag/ingest.py)) produces for
  that company's Item 1 / Item 1A, so the eval's ground truth can't drift
  out of sync with the primary source the pipeline actually reads.
- **`run_eval.py`** — runs each golden example through the *real* graph
  (`build_graph().ainvoke(...)`, the same code path as a live
  `POST /reports`) and scores it with three evaluators via
  `langsmith.aevaluate`:
  - `ticker_correctness` — deterministic, did ticker resolution land on
    the expected symbol.
  - `citation_coverage` — deterministic, did the evidence bundle actually
    include a chunk from each required filing item (catches retrieval
    misses — e.g. it caught the filings agent citing Item 16 instead of
    Item 1A for a risk-factors query on one company during testing).
  - `llm_judge_groundedness` — **LLM-as-judge**: an independent grading
    pass, deliberately *not* the pipeline's own fact-checker — a fresh,
    uncached call with its own skeptical prompt — that re-reads each
    section against only its cited evidence text and scores 1-5 how well
    the claims are actually supported.

Results land in LangSmith as an experiment against the `equitylens-golden-v1`
dataset, alongside the per-run traces from `LANGCHAIN_TRACING_V2=true`.

## Not yet built

- P9 — Secret Manager, CI/CD to Cloud Run (Dockerization is done)
