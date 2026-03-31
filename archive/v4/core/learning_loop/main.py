"""Learning Loop Main Entry Point (v3).

Starts all 4 services concurrently in the same process:
- REFLECTOR: Turn analysis, attribution, counter updates, AKU extraction
- CURATOR: Quality gate and deduplication for AKUs
- CLUSTERER: Cluster management and solved_by edges
- ADVISOR: Bullet retrieval with Thompson Sampling

Event flow:
- SESSION → llm.response.received → REFLECTOR (buffers)
- SESSION → session.ended → REFLECTOR → attribution.resolved + aku.proposed
- aku.proposed → CURATOR → bullet.accepted/merged
- attribution.resolved → CLUSTERER (cluster assignment)
- bullet.accepted → CLUSTERER (solved_by edges)
- bullets.requested → ADVISOR → Redis
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from core.learning_loop.advisor import AdvisorService
from core.learning_loop.clusterer import ClustererService
from core.learning_loop.curator import CuratorService
from core.learning_loop.reflector import ReflectorService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class LearningLoop:
    """Main learning loop coordinator (v3).

    Manages all 4 services and their lifecycle.
    """

    def __init__(self):
        """Initialize learning loop."""
        self.reflector = ReflectorService()
        self.curator = CuratorService()
        self.clusterer = ClustererService()
        self.advisor = AdvisorService()

        self._shutdown_event: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all services."""
        logger.info("=" * 60)
        logger.info("Starting ALEC Learning Loop v3")
        logger.info("=" * 60)
        logger.info("REFLECTOR: Turn analysis, attribution, AKU extraction")
        logger.info("CURATOR: Quality gate, deduplication")
        logger.info("CLUSTERER: Cluster management, solved_by edges")
        logger.info("ADVISOR: Bullet retrieval, Thompson Sampling")
        logger.info("=" * 60)

        # Pre-load embedding model ONCE for all services (singleton)
        from core.common.embedding_client import EmbeddingClient
        logger.info("Pre-loading embedding model...")
        EmbeddingClient.preload()

        self._shutdown_event = asyncio.Event()

        # Start each service as a separate task
        self._tasks = [
            asyncio.create_task(self._run_service("REFLECTOR", self.reflector.start)),
            asyncio.create_task(self._run_service("CURATOR", self.curator.start)),
            asyncio.create_task(self._run_service("CLUSTERER", self.clusterer.start)),
            asyncio.create_task(self._run_service("ADVISOR", self.advisor.start)),
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
        logger.info("Stopping Learning Loop...")

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
        await self.reflector.stop()
        await self.curator.stop()
        await self.clusterer.stop()
        await self.advisor.stop()

        logger.info("Learning Loop stopped")

    def handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        if self._shutdown_event:
            self._shutdown_event.set()


async def main() -> None:
    """Main entry point."""
    loop = LearningLoop()

    # Setup signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            lambda s=sig: loop.handle_signal(s),
        )

    try:
        await loop.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await loop.stop()


if __name__ == "__main__":
    asyncio.run(main())
