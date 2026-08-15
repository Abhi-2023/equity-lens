"""API-shape smoke tests. Doesn't require GROQ_API_KEY — the background
report job is expected to fail fast without one, but job creation, status
polling, and 404 handling should all work regardless. Requires Postgres
(the `db` fixture) — see conftest.py.

Uses httpx.AsyncClient with ASGITransport rather than FastAPI's TestClient:
TestClient runs the app on its own separate event-loop thread, which
conflicts with the async SQLAlchemy engine the `db` fixture awaits directly
on pytest-asyncio's loop ("Future attached to a different loop"). Driving
everything through one async client on one loop avoids that entirely.
"""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_report_returns_job_id_and_stream_url(db, client):
    resp = await client.post("/reports", json={"company": "MSFT", "depth": "quick"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["stream_url"] == f"/reports/{body['job_id']}/stream"


@pytest.mark.asyncio
async def test_report_status_transitions_and_unknown_job_404s(db, client):
    resp = await client.post("/reports", json={"company": "MSFT", "depth": "quick"})
    job_id = resp.json()["job_id"]

    for _ in range(20):
        status_resp = await client.get(f"/reports/{job_id}/status")
        assert status_resp.status_code == 200
        if status_resp.json()["status"] != "running":
            break
        await asyncio.sleep(0.5)

    assert (await client.get("/reports/does-not-exist/status")).status_code == 404
    assert (await client.get("/reports/does-not-exist")).status_code == 404
