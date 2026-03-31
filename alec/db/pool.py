"""asyncpg connection pool with pgvector codec support."""

from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

logger = structlog.get_logger()


async def create_pool(
    database_url: str,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Create an asyncpg connection pool with pgvector support.

    Args:
        database_url: PostgreSQL connection string.
        min_size: Minimum pool connections.
        max_size: Maximum pool connections.

    Returns:
        Configured asyncpg.Pool with pgvector codecs registered.
    """

    async def _init_connection(conn: asyncpg.Connection) -> None:
        await register_vector(conn)

    pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )
    if pool is None:
        raise RuntimeError("Failed to create database pool")

    logger.info("db.pool.created", min_size=min_size, max_size=max_size)
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close the connection pool."""
    await pool.close()
    logger.info("db.pool.closed")
