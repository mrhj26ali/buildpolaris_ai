import asyncpg
import pytest

from buildpolaris_ai.platform.config import get_settings


@pytest.mark.asyncio
async def test_config_driven_database_connection():
    """Prove the centralized config produces a working DB connection end-to-end."""
    settings = get_settings()
    try:
        conn = await asyncpg.connect(**settings.database.connect_kwargs())
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")

    try:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
    finally:
        await conn.close()