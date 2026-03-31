"""SESSION service lifecycle management (v3).

Manages PostgreSQL, Redis, Kafka connections with structured logging
and Prometheus metrics.
"""

import asyncio
import os
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from prometheus_client import start_http_server

from core.common.kafka_client import KafkaClient
from core.common.observability import setup_logging

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://alec:alec-dev-password@postgres:5432/alec"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "180"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "30"))


class SessionService:
    """SESSION orchestration service (v3)."""

    def __init__(self):
        """Initialize service with None connections."""
        self.pool: Optional[asyncpg.Pool] = None
        self.redis: Optional[aioredis.Redis] = None
        self.kafka: Optional[KafkaClient] = None
        self.logger = setup_logging("session")
        self._metrics_started = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

    async def start(self) -> None:
        """Initialize all connections."""
        self.logger.info("service_starting")

        # Start metrics server
        if not self._metrics_started:
            try:
                start_http_server(METRICS_PORT)
                self._metrics_started = True
                self.logger.info("metrics_server_started", port=METRICS_PORT)
            except OSError:
                self.logger.warning("metrics_server_already_running", port=METRICS_PORT)

        # PostgreSQL connection pool (with JSONB codec)
        from core.common.postgres import create_pool
        self.pool = await create_pool(
            dsn=DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        self.logger.info("postgres_connected")

        # Redis connection
        self.redis = await aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
        )
        self.logger.info("redis_connected")

        # Kafka producer only (SESSION doesn't consume)
        self.kafka = KafkaClient(service_name="session")
        await self.kafka.start_producer()
        self.logger.info("kafka_producer_started")

        # Start background cleanup task for stale sessions
        self._shutdown = False
        self._cleanup_task = asyncio.create_task(self._run_cleanup_loop())
        self.logger.info("cleanup_task_started", interval=CLEANUP_INTERVAL_SECONDS)

        self.logger.info("service_started")

    async def stop(self) -> None:
        """Graceful shutdown of all connections."""
        self.logger.info("service_stopping")

        # Stop cleanup task
        self._shutdown = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self.logger.info("cleanup_task_stopped")

        if self.kafka:
            await self.kafka.close()
            self.logger.info("kafka_closed")

        if self.redis:
            await self.redis.close()
            self.logger.info("redis_closed")

        if self.pool:
            await self.pool.close()
            self.logger.info("postgres_closed")

        self.logger.info("service_stopped")

    async def health_check(self) -> dict:
        """Check health of all dependencies.

        Returns:
            dict: Health status for each dependency.
        """
        checks = {}

        # PostgreSQL
        try:
            if self.pool:
                async with self.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                checks["postgres"] = "ok"
            else:
                checks["postgres"] = "not_connected"
        except Exception as e:
            checks["postgres"] = f"error: {str(e)}"

        # Redis
        try:
            if self.redis:
                await self.redis.ping()
                checks["redis"] = "ok"
            else:
                checks["redis"] = "not_connected"
        except Exception as e:
            checks["redis"] = f"error: {str(e)}"

        # Kafka (producer health check)
        try:
            if self.kafka and self.kafka._producer:
                checks["kafka"] = "ok"
            else:
                checks["kafka"] = "not_connected"
        except Exception as e:
            checks["kafka"] = f"error: {str(e)}"

        # Overall status
        all_ok = all(v == "ok" for v in checks.values())
        checks["status"] = "healthy" if all_ok else "degraded"

        return checks

    async def _run_cleanup_loop(self) -> None:
        """Background loop to clean up stale sessions."""
        while not self._shutdown:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                if not self._shutdown:
                    await self._cleanup_stale_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("cleanup_loop_error", error=str(e))

    async def _cleanup_stale_sessions(self) -> None:
        """Find and end sessions that have been inactive for too long."""
        if not self.pool or not self.kafka:
            return

        try:
            # Find active sessions with no recent activity
            stale_sessions = await self.pool.fetch(
                """
                SELECT s.session_id, s.domain, s.message_count,
                       EXTRACT(EPOCH FROM (NOW() - COALESCE(
                           (SELECT MAX(created_at) FROM session_turns WHERE session_id = s.session_id),
                           s.created_at
                       ))) as inactive_seconds
                FROM sessions s
                WHERE s.status = 'active'
                  AND EXTRACT(EPOCH FROM (NOW() - COALESCE(
                      (SELECT MAX(created_at) FROM session_turns WHERE session_id = s.session_id),
                      s.created_at
                  ))) > $1
                """,
                SESSION_TIMEOUT_SECONDS,
            )

            for session in stale_sessions:
                session_id = str(session["session_id"])
                inactive_seconds = session["inactive_seconds"]

                # Update session status to completed
                await self.pool.execute(
                    """
                    UPDATE sessions
                    SET status = 'completed', updated_at = NOW()
                    WHERE session_id = $1
                    """,
                    session["session_id"],
                )

                # Emit session.ended event
                await self.kafka.publish_event(
                    topic="session.ended",
                    event_type="session.ended",
                    payload={
                        "session_id": session_id,
                        "success": False,
                        "domain": session["domain"] or "general",  # Required for REFLECTOR
                        "reason": f"timeout_after_{int(inactive_seconds)}s",
                        "message_count": session["message_count"] or 0,
                    },
                )

                self.logger.info(
                    "stale_session_ended",
                    session_id=session_id,
                    inactive_seconds=int(inactive_seconds),
                    message_count=session["message_count"] or 0,
                )

            if stale_sessions:
                self.logger.info(
                    "cleanup_completed",
                    sessions_ended=len(stale_sessions),
                )

        except Exception as e:
            self.logger.error("cleanup_stale_sessions_failed", error=str(e))
