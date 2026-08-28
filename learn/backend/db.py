from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

import settings

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    _pool = AsyncConnectionPool(
        settings.DATABASE_URL,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await _pool.open(wait=True, timeout=15)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection():
    if _pool is None:
        raise RuntimeError("Connection pool is not open")
    async with _pool.connection() as conn:
        yield conn


async def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    async with connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall()


async def fetch_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    async with connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchone()


async def execute(sql: str, params: tuple = ()) -> None:
    async with connection() as conn:
        await conn.execute(sql, params)
