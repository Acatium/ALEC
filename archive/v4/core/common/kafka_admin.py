"""Kafka topic administration.

Provides topic pre-creation to avoid race conditions at startup.
"""

import asyncio
from typing import Optional

from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from core.common.observability import setup_logging

logger = setup_logging("kafka-admin")

# All topics used by ALEC services
REQUIRED_TOPICS = [
    # SESSION emits
    "session.created",
    "bullets.requested",
    "llm.response.received",
    "session.ended",
    # REFLECTOR/STRATEGIST emit
    "aku.proposed",
    # CURATOR emits
    "bullet.accepted",
    "bullet.merged",
    # REFLECTOR emits
    "attribution.resolved",
    # LIBRARIAN emits
    "library.gap.detected",
    "library.cluster.struggling",
]

# Topic configuration
DEFAULT_NUM_PARTITIONS = 3
DEFAULT_REPLICATION_FACTOR = 1  # Single broker in dev


class KafkaTopicManager:
    """Manages Kafka topic creation and verification."""

    def __init__(self, bootstrap_servers: str):
        """Initialize topic manager.

        Args:
            bootstrap_servers: Kafka bootstrap servers (e.g., 'kafka:9092')
        """
        self.bootstrap_servers = bootstrap_servers
        self._admin_client: Optional[AIOKafkaAdminClient] = None

    async def _get_client(self) -> AIOKafkaAdminClient:
        """Get or create admin client."""
        if self._admin_client is None:
            self._admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers
            )
            await self._admin_client.start()
        return self._admin_client

    async def close(self) -> None:
        """Close admin client."""
        if self._admin_client:
            await self._admin_client.close()
            self._admin_client = None

    async def ensure_topics_exist(
        self,
        topics: Optional[list[str]] = None,
        num_partitions: int = DEFAULT_NUM_PARTITIONS,
        replication_factor: int = DEFAULT_REPLICATION_FACTOR,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> list[str]:
        """Ensure all required topics exist, creating them if needed.

        Args:
            topics: List of topics to ensure (defaults to REQUIRED_TOPICS)
            num_partitions: Number of partitions for new topics
            replication_factor: Replication factor for new topics
            max_retries: Max retries for topic creation
            retry_delay: Delay between retries in seconds

        Returns:
            List of topics that were created (empty if all existed)

        Raises:
            RuntimeError: If topics cannot be created after retries
        """
        topics = topics or REQUIRED_TOPICS
        created: list[str] = []

        for attempt in range(max_retries):
            try:
                client = await self._get_client()

                # Get existing topics
                existing = await client.list_topics()
                existing_set = set(existing)

                # Find missing topics
                missing = [t for t in topics if t not in existing_set]

                if not missing:
                    logger.info(
                        "all_topics_exist",
                        topic_count=len(topics),
                    )
                    return created

                # Create missing topics
                new_topics = [
                    NewTopic(
                        name=topic,
                        num_partitions=num_partitions,
                        replication_factor=replication_factor,
                    )
                    for topic in missing
                ]

                await client.create_topics(new_topics)

                logger.info(
                    "topics_created",
                    topics=missing,
                    count=len(missing),
                )

                created.extend(missing)
                return created

            except Exception as e:
                logger.warning(
                    "topic_creation_failed",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    raise RuntimeError(
                        f"Failed to create topics after {max_retries} attempts: {e}"
                    ) from e

        return created

    async def verify_topics_exist(
        self,
        topics: Optional[list[str]] = None,
    ) -> tuple[list[str], list[str]]:
        """Verify which topics exist and which are missing.

        Args:
            topics: List of topics to check (defaults to REQUIRED_TOPICS)

        Returns:
            Tuple of (existing_topics, missing_topics)
        """
        topics = topics or REQUIRED_TOPICS

        try:
            client = await self._get_client()
            existing = await client.list_topics()
            existing_set = set(existing)

            found = [t for t in topics if t in existing_set]
            missing = [t for t in topics if t not in existing_set]

            return found, missing

        except Exception as e:
            logger.error("topic_verification_failed", error=str(e))
            return [], topics


async def ensure_topics(
    bootstrap_servers: str,
    topics: Optional[list[str]] = None,
) -> list[str]:
    """Convenience function to ensure topics exist.

    Args:
        bootstrap_servers: Kafka bootstrap servers
        topics: Topics to ensure (defaults to REQUIRED_TOPICS)

    Returns:
        List of newly created topics
    """
    manager = KafkaTopicManager(bootstrap_servers)
    try:
        return await manager.ensure_topics_exist(topics)
    finally:
        await manager.close()
