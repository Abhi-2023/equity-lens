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
- **Watchlist auto-refresh** (Section 2.4/7): an in-process APScheduler job
  (stands in for Cloud Scheduler + Cloud Run) that re-runs the pipeline for
  each watchlisted company on its own cadence —
  [backend/app/services/watchlist_scheduler.py](backend/app/services/watchlist_scheduler.py)
- **Infra**: Postgres, Redis, and Qdrant all run as real services — via
  `docker-compose.yml`, not embedded/local-file modes. Frontend and backend
  are both containerized with multi-stage Dockerfiles.

Everything above except the LLM- and Cohere-dependent steps has been
exercised end-to-end against live SEC EDGAR, Yahoo Finance, and DuckDuckGo
data. The LLM calls use Groq-hosted open-source models (default: Llama 3.3
70B) and require `GROQ_API_KEY`; retrieval reranking uses `COHERE_API_KEY`
(retrieval still works without it — falls back to the un-reranked RRF order).

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

## Not yet built

- P8 — golden eval dataset + scorers (LangSmith tracing itself is wired; the
  offline eval harness is not)
- P9 — Secret Manager, CI/CD to Cloud Run (Dockerization is done)
