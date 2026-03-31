"""PostgreSQL connection utilities with proper JSONB handling.

This module provides a centralized way to create asyncpg connection pools
with JSONB codec registration, enabling transparent dict<->JSONB conversion.

Usage:
    from core.common.postgres import create_pool

    pool = await create_pool()  # Uses env vars for connection
    pool = await create_pool(dsn="postgresql://...")  # Explicit DSN
"""

import json
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


async def init_connection(conn: asyncpg.Connection) -> None:
    """Register JSONB codec for transparent dict<->JSONB conversion.

    This enables passing Python dicts directly to JSONB columns without
    manual json.dumps() calls. Called automatically for each new connection
    in pools created with create_pool().

    Args:
        conn: asyncpg connection to configure.
    """
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )


async def create_pool(
    dsn: Optional[str] = None,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: int = 30,
    **kwargs
) -> asyncpg.Pool:
    """Create asyncpg pool with JSONB codec registered.

    All connections in the pool will have the JSONB codec registered,
    allowing transparent serialization/deserialization of Python dicts
    to/from PostgreSQL JSONB columns.

    Args:
        dsn: Database connection string. If None, constructs from env vars:
            - POSTGRES_USER (default: alec)
            - POSTGRES_PASSWORD (default: alec-dev-password)
            - POSTGRES_HOST (default: postgres)
            - POSTGRES_PORT (default: 5432)
            - POSTGRES_DB (default: alec)
        min_size: Minimum pool connections.
        max_size: Maximum pool connections.
        command_timeout: Query timeout in seconds.
        **kwargs: Additional asyncpg.create_pool arguments.

    Returns:
        Configured asyncpg connection pool with JSONB codec.

    Example:
        pool = await create_pool()
        async with pool.acquire() as conn:
            # Can pass dicts directly to JSONB columns
            await conn.execute(
                "INSERT INTO mytable (data) VALUES ($1)",
                {"key": "value"}  # No json.dumps() needed!
            )
    """
    if dsn is None:
        # Check if using default dev credentials
        using_default_password = os.getenv('POSTGRES_PASSWORD') is None
        if using_default_password:
            logger.warning(
                "Using default dev credentials for PostgreSQL. "
                "Set POSTGRES_PASSWORD environment variable for production."
            )

        dsn = (
            f"postgresql://{os.getenv('POSTGRES_USER', 'alec')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'alec-dev-password')}@"
            f"{os.getenv('POSTGRES_HOST', 'postgres')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'alec')}"
        )

    return await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
        init=init_connection,
        **kwargs
    )
