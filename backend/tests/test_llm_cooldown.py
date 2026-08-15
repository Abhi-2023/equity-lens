import pytest

from app.llm.cooldown import clear_cooldown, is_cooling_down, set_cooldown


@pytest.mark.asyncio
async def test_cooldown_round_trip():
    await clear_cooldown(0, "test-model-cooldown")
    assert await is_cooling_down(0, "test-model-cooldown") is False

    await set_cooldown(0, "test-model-cooldown", 30)
    assert await is_cooling_down(0, "test-model-cooldown") is True

    await clear_cooldown(0, "test-model-cooldown")
    assert await is_cooling_down(0, "test-model-cooldown") is False


@pytest.mark.asyncio
async def test_cooldown_is_scoped_per_account_and_model():
    await clear_cooldown(0, "scope-test-model")
    await clear_cooldown(1, "scope-test-model")

    await set_cooldown(0, "scope-test-model", 30)

    assert await is_cooling_down(0, "scope-test-model") is True
    assert await is_cooling_down(1, "scope-test-model") is False

    await clear_cooldown(0, "scope-test-model")
