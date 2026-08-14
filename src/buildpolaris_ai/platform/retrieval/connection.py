"""Shared asyncpg connection management for retrieval infrastructure.

This is the single seam for opening a correctly configured AI database
connection. It registers pgvector and loads Apache AGE exactly once per
connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from pgvector.asyncpg import register_vector

from buildpolaris_ai.platform.config import get_settings


async def configure_ai_connection(conn: asyncpg.Connection) -> None:
    """Configure an asyncpg connection for pgvector + Apache AGE."""
    await register_vector(conn)
    await conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')


async def create_ai_connection() -> asyncpg.Connection:
    """Create and configure a new asyncpg connection."""
    settings = get_settings()
    conn = await asyncpg.connect(**settings.database.connect_kwargs())

    try:
        await configure_ai_connection(conn)
        return conn
    except Exception:
        await conn.close()
        raise


@asynccontextmanager
async def ai_connection() -> AsyncIterator[asyncpg.Connection]:
    """Async context manager for a configured AI DB connection."""
    conn = await create_ai_connection()
    try:
        yield conn
    finally:
        await conn.close()


async def get_ai_db_conn() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency that yields a configured AI DB connection."""
    async with ai_connection() as conn:
        yield conn
