"""BuildPolaris AI â€” migration runner.

Not full Alembic autogenerate machinery: this schema is small and every
change is hand-authored and reviewed the same way a MariaDB migration
would be (ERD v2.1 Â§7). This runner applies the numbered .sql files in
migrations/versions/ in order, tracking applied versions in the
`schema_migrations` table created by 0001, so re-running is always safe.

Usage:
    python -m migrations.env
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


async def _ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def _applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def run_migrations() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(**settings.database.connect_kwargs())
    try:
        await _ensure_tracking_table(conn)
        applied = await _applied_versions(conn)

        sql_files = sorted(VERSIONS_DIR.glob("*.sql"))
        for path in sql_files:
            version = path.stem
            if version in applied:
                print(f"[migrations] {version} already applied, skipping")
                continue

            print(f"[migrations] applying {version} ...")
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1) "
                    "ON CONFLICT (version) DO NOTHING",
                    version,
                )
            print(f"[migrations] {version} applied")

        print("[migrations] up to date")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
