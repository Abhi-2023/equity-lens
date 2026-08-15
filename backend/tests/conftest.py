import pytest

from app.db import init_db


@pytest.fixture
async def db():
    """Requires a real Postgres instance at DATABASE_URL — see docker-compose.yml
    (`docker-compose up postgres`) or backend/.env.example for local Postgres.
    Only requested by tests that actually touch the database, so pure-function
    tests don't need Postgres running to pass."""
    await init_db()
