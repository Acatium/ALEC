"""Agents Service Main Entry Point (v3).

Starts both LIBRARIAN and STRATEGIST services concurrently.
Each service runs in its own asyncio task but shares the same process.

LIBRARIAN: Library intelligence - gap detection, struggling clusters, auto-archive
STRATEGIST: Strategic synthesis - creates new bullets via LLM for knowledge gaps
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from core.agents.librarian import LibrarianService
from core.agents.strategist import StrategistService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class AgentsService:
    """Main agents service coordinator (v3).

    Manages both services and their lifecycle:
    - LIBRARIAN: Library analysis, gap detection, auto-archive
    - STRATEGIST: LLM synthesis for knowledge gaps
    """

    def __init__(self):
        """Initialize agents service."""
        self.librarian = LibrarianService()
        self.strategist = StrategistService()

        self._shutdown_event: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all services."""
        logger.info("=" * 60)
        logger.info("Starting ALEC Agents Service v3")
        logger.info("=" * 60)
        logger.info("LIBRARIAN: Gap detection, struggling clusters, auto-archive")
        logger.info("STRATEGIST: LLM synthesis for knowledge gaps")
        logger.info("=" * 60)

        # Preload embedding model
        logger.info("Pre-loading embedding model...")
        from core.common.embedding_client import EmbeddingClient
        EmbeddingClient.preload()
        logger.info("Embedding model ready")

        self._shutdown_event = asyncio.Event()

        # Start each service as a separate task
        self._tasks = [
            asyncio.create_task(self._run_service("LIBRARIAN", self.librarian.start)),
            asyncio.create_task(self._run_service("STRATEGIST", self.strategist.start)),
        ]

        # Wait for shutdown signal or any task to complete
        done, pending = await asyncio.wait(
            self._tasks + [asyncio.create_task(self._shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If a service failed, log it
        for task in done:
            if task.exception():
                logger.error(f"Service task failed: {task.exception()}")

    async def _run_service(self, name: str, start_func) -> None:
        """Run a service with error handling."""
        try:
            logger.info(f"Starting {name} service...")
            await start_func()
        except asyncio.CancelledError:
            logger.info(f"{name} service cancelled")
        except Exception as e:
            logger.error(f"{name} service error: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop all services."""
        logger.info("Stopping Agents Service...")

        # Signal shutdown
        if self._shutdown_event:
            self._shutdown_event.set()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop services
        await self.librarian.stop()
        await self.strategist.stop()

        logger.info("Agents Service stopped")

    def handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        if self._shutdown_event:
            self._shutdown_event.set()


async def main() -> None:
    """Main entry point."""
    service = AgentsService()

    # Setup signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            lambda s=sig: service.handle_signal(s),
        )

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
