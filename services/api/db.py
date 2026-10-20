"""Shared asyncpg pool (used by main.py and the offers router)."""

from typing import Optional

import asyncpg
from fastapi import HTTPException

_pool: Optional[asyncpg.Pool] = None


async def init(database_url: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)


async def close() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(status_code=503, detail="db pool not ready")
    return _pool
