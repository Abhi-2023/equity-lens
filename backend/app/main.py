"""FastAPI application entrypoint — app setup and router registration only.
Route handlers live in `app/api/`, pipeline logic in `app/services/`."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, history, reports, watchlist
from app.db import init_db
from app.services.watchlist_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="EquityLens API", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(reports.router)
app.include_router(watchlist.router)
app.include_router(history.router)
