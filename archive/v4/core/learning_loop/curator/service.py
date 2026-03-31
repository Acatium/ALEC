"""CURATOR service - Single quality gate for all AKU sources.

v4 Simplified Schema (gap-aku-001):
- Removed modality/polarity/category
- Added length validation (situation ≤60, assertion ≤100)
- Renamed bullet → aku terminology
- Uses akus table (not playbook_bullets)

Responsibilities:
1. Quality gate (length constraints, situation specificity)
2. Deduplication on assertion embedding
3. Store AKUs with BOTH embeddings (situation + assertion)
4. Emit aku.accepted or aku.merged
"""

import os
import re
from typing import Optional
from uuid import uuid4

from core.common import AKUS_TOTAL, BaseService
from core.common.embedding_client import EmbeddingClient
from core.common.kafka_client import Event


def _embedding_to_str(embedding) -> str:
    """Convert embedding to pgvector string format.

    Handles both Python lists (from embedding client) and strings (from DB).
    """
    if isinstance(embedding, str):
        # Already a pgvector string from database
        return embedding
    # Python list from embedding client
    return "[" + ",".join(str(x) for x in embedding) + "]"


# Configuration
DEDUP_THRESHOLD = float(os.getenv("ALEC_DEDUP_THRESHOLD", "0.70"))
DEDUP_THRESHOLD_HIGH = float(os.getenv("ALEC_DEDUP_THRESHOLD_HIGH", "0.90"))

# Length constraints (v4 simplification)
MAX_SITUATION_LENGTH = 60
MAX_ASSERTION_LENGTH = 100
MIN_ASSERTION_LENGTH = int(os.getenv("CURATOR_MIN_ASSERTION_LENGTH", "20"))
MIN_SITUATION_LENGTH = 10

# Patterns that indicate low-quality situations
LOW_QUALITY_PATTERNS = [
    r"task[_\s]*id",  # Contains task ID
    r"[a-f0-9]{8}-[a-f0-9]{4}",  # UUID-like pattern
    r"^\s*when\s+(using|calling|working)\s*$",  # Too generic
]


class CuratorService(BaseService):
    """CURATOR - Quality gate and deduplication for AKUs."""

    def __init__(self):
        super().__init__("curator")
        self._embedding_client: Optional[EmbeddingClient] = None

    def _get_topics(self) -> list[str]:
        return ["aku.proposed"]

    async def start(self) -> None:
        """Start the service with embedding client."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()

        self._embedding_client = EmbeddingClient()
        await self._embedding_client.start()

        await self._require_kafka().start_consumer(
            topics=self._get_topics(),
            handler=self._handle_event_wrapper,
            group_id=f"{self.service_name}-events",
        )
        self.logger.info("service_started")

    async def _handle_event(self, event: Event) -> None:
        """Handle aku.proposed events."""
        if event.event_type == "aku.proposed":
            await self._handle_aku_proposed(event)

    async def _handle_aku_proposed(self, event: Event) -> None:
        """Process proposed AKU through quality gate and dedup."""
        payload = event.payload
        aku = payload.get("aku")
        source = payload.get("source", "reflector")
        session_id = payload.get("session_id", "unknown")
        target_cluster_id = payload.get("target_cluster_id")  # From STRATEGIST

        if not aku:
            self.logger.warning("aku_missing", session_id=session_id)
            return

        # 1. Quality gate (v4: length validation, no modality/polarity)
        rejection_reason = self._quality_check(aku)
        if rejection_reason:
            AKUS_TOTAL.labels(source=source, status="rejected").inc()
            self.logger.info(
                "aku_rejected",
                session_id=session_id,
                source=source,
                reason=rejection_reason,
            )
            return

        # 2. Generate BOTH embeddings
        situation = aku["situation"]
        assertion = aku["assertion"]

        if not self._embedding_client:
            self.logger.error("embedding_client_not_initialized")
            return

        try:
            situation_emb = self._embedding_client.embed(situation)
            assertion_emb = self._embedding_client.embed(assertion)
        except Exception as e:
            self.logger.error("embedding_failed", error=str(e))
            return

        # 3. Dedup check on ASSERTION (allows same situation, different solutions)
        threshold = self._get_threshold_for_source(source)
        existing_id = await self._check_duplicate_by_assertion(assertion_emb, threshold)

        if existing_id:
            # Increment evidence on existing AKU
            await self._increment_evidence(existing_id)
            AKUS_TOTAL.labels(source=source, status="merged").inc()

            await self._require_kafka().publish_event(
                topic="aku.merged",
                event_type="aku.merged",
                payload={
                    "aku_id": existing_id,
                    "session_id": session_id,
                },
                correlation_id=event.correlation_id,
            )

            self.logger.info(
                "aku_merged",
                session_id=session_id,
                aku_id=existing_id,
                source=source,
            )
            return

        # 4. Store new AKU with BOTH embeddings (v4 simplified schema)
        aku_id = await self._store_aku(
            aku=aku,
            situation_emb=situation_emb,
            assertion_emb=assertion_emb,
            source=source,
            cluster_id=target_cluster_id,
        )

        AKUS_TOTAL.labels(source=source, status="accepted").inc()

        await self._require_kafka().publish_event(
            topic="aku.accepted",
            event_type="aku.accepted",
            payload={
                "aku_id": aku_id,
                "session_id": session_id,
                "situation": situation,
                "target_cluster_id": target_cluster_id,  # Pass through for CLUSTERER
            },
            correlation_id=event.correlation_id,
        )

        self.logger.info(
            "aku_accepted",
            session_id=session_id,
            aku_id=aku_id,
            source=source,
        )

    def _quality_check(self, aku: dict) -> Optional[str]:
        """Quality gate for AKUs. Returns rejection reason or None.

        v4 Simplified:
        - Length constraints (situation ≤60, assertion ≤100)
        - No modality/polarity validation (removed in v4)
        """
        situation = aku.get("situation", "")
        assertion = aku.get("assertion", "")

        # Check assertion length (min and max)
        if len(assertion) < MIN_ASSERTION_LENGTH:
            return f"assertion_too_short:{len(assertion)}<{MIN_ASSERTION_LENGTH}"

        if len(assertion) > MAX_ASSERTION_LENGTH:
            return f"assertion_too_long:{len(assertion)}>{MAX_ASSERTION_LENGTH}"

        # Check situation length (min and max)
        if len(situation) < MIN_SITUATION_LENGTH:
            return f"situation_too_short:{len(situation)}<{MIN_SITUATION_LENGTH}"

        if len(situation) > MAX_SITUATION_LENGTH:
            return f"situation_too_long:{len(situation)}>{MAX_SITUATION_LENGTH}"

        # Check for low-quality patterns
        for pattern in LOW_QUALITY_PATTERNS:
            if re.search(pattern, situation, re.IGNORECASE):
                return f"low_quality_situation:{pattern}"

        return None

    def _get_threshold_for_source(self, source: str) -> float:
        """Get dedup threshold based on source."""
        thresholds = {
            "reflector": DEDUP_THRESHOLD,      # 0.70
            "strategist": DEDUP_THRESHOLD_HIGH,  # 0.90 (more strict)
            "manual": 0.80,
        }
        return thresholds.get(source, DEDUP_THRESHOLD)

    async def _check_duplicate_by_assertion(
        self, assertion_emb: list[float], threshold: float
    ) -> Optional[str]:
        """Check for duplicate by ASSERTION embedding."""
        try:
            result = await self._require_pool().fetchrow(
                """
                SELECT aku_id FROM akus
                WHERE 1 - (assertion_embedding <=> $1::vector) > $2
                  AND status IN ('candidate', 'active')
                ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
                LIMIT 1
                """,
                _embedding_to_str(assertion_emb),
                threshold,
            )
            return str(result["aku_id"]) if result else None
        except Exception as e:
            self.logger.warning("dedup_check_failed", error=str(e))
            return None

    async def _increment_evidence(self, aku_id: str) -> None:
        """Increment evidence count when duplicate AKU extracted."""
        try:
            await self._require_pool().execute(
                """
                UPDATE akus
                SET evidence_count = evidence_count + 1
                WHERE aku_id = $1
                """,
                aku_id,
            )
        except Exception as e:
            self.logger.warning("evidence_increment_failed", error=str(e))

    async def _store_aku(
        self,
        aku: dict,
        situation_emb: list[float],
        assertion_emb: list[float],
        source: str,
        cluster_id: Optional[str] = None,
    ) -> str:
        """Store new AKU with both embeddings.

        v4 Simplified Schema (14 fields):
        - aku_id, situation, assertion
        - situation_embedding, assertion_embedding
        - helpful_count, harmful_count, neutral_count, evidence_count
        - status, cluster_id, source, created_at, metadata
        """
        aku_id = str(uuid4())

        try:
            await self._require_pool().execute(
                """
                INSERT INTO akus (
                    aku_id, situation, assertion,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count, evidence_count,
                    status, cluster_id, source, created_at, metadata
                ) VALUES (
                    $1, $2, $3,
                    $4::vector, $5::vector,
                    0, 0, 0, 1,
                    'candidate', $6, $7, NOW(), '{}'
                )
                """,
                aku_id,
                aku["situation"],
                aku["assertion"],
                _embedding_to_str(situation_emb),
                _embedding_to_str(assertion_emb),
                cluster_id,
                source,
            )
            return aku_id
        except Exception as e:
            self.logger.error("aku_store_failed", error=str(e))
            raise
