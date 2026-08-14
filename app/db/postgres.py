"""Postgres connection pool â€” the single seam for opening a correctly
configured connection against buildpolaris_ai's Postgres (pgvector +
Apache AGE). Every connection registers the vector codec and loads AGE
exactly once, on pool init, via `asyncpg.Pool`'s `setup` hook.
"""
from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from app.config import get_settings

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None


async def _configure_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)
    await conn.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings().database
    _pool = await asyncpg.create_pool(
        min_size=2,
        max_size=10,
        setup=_configure_connection,
        **settings.connect_kwargs(),
    )
    logger.info("postgres_pool_initialized", host=settings.host, database=settings.name)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("postgres_pool_closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Postgres pool not initialized â€” call init_pool() during app startup"
        )
    return _pool
