"""STRATEGIST service - Strategic synthesis of new bullets.

Responsibilities:
1. Consume library events (gap.detected, cluster.struggling)
2. Synthesize solutions via LLM
3. Pre-synthesis dedup check (don't synthesize duplicates)
4. Emit aku.proposed for CURATOR to process

Consumes: library.gap.detected, library.cluster.struggling
Emits: aku.proposed
"""

import os
import time
from dataclasses import dataclass
from typing import Optional

from core.agents.strategist.prompts import (
    SYNTHESIS_COMPARATIVE_SYSTEM,
    SYNTHESIS_COMPARATIVE_USER,
    SYNTHESIS_GAP_USER,
    SYNTHESIS_STRUGGLING_USER,
    SYNTHESIS_SYSTEM,
)
from core.common import AKUS_TOTAL, LLM_CALLS, LLM_DURATION, BaseService
from core.common.embedding_client import EmbeddingClient
from core.common.kafka_client import Event
from core.learning_loop.shared.llm_client import LLMClient
from core.learning_loop.shared.text_parser import parse_aku

# Configuration
BUFFER_SECONDS = int(os.getenv("STRATEGIST_BUFFER_SECONDS", "3"))
DEDUP_THRESHOLD = float(os.getenv("ALEC_DEDUP_THRESHOLD_HIGH", "0.90"))

# Synthesis retry configuration
SUCCESS_COOLDOWN = int(os.getenv("STRATEGIST_SUCCESS_COOLDOWN", "1800"))  # 30 min
FAILURE_COOLDOWN = int(os.getenv("STRATEGIST_FAILURE_COOLDOWN", "600"))   # 10 min
RETRY_THRESHOLD = int(os.getenv("STRATEGIST_RETRY_THRESHOLD", "50"))      # failures


@dataclass
class SynthesisAttempt:
    """Track synthesis attempt for a cluster."""
    timestamp: float
    success: bool
    failure_count_at_attempt: int


def _embedding_to_str(embedding) -> str:
    """Convert embedding to pgvector string format."""
    if isinstance(embedding, str):
        return embedding
    return "[" + ",".join(str(x) for x in embedding) + "]"


class StrategistService(BaseService):
    """STRATEGIST - Strategic synthesis of new bullets."""

    def __init__(self):
        super().__init__("strategist")
        self._llm_client: Optional[LLMClient] = None
        self._embedding_client: Optional[EmbeddingClient] = None
        # Track synthesis attempts with metadata for smart retry
        self._synthesis_attempts: dict[str, SynthesisAttempt] = {}

    def _get_topics(self) -> list[str]:
        return ["library.gap.detected", "library.cluster.struggling", "library.task.comparative"]

    async def start(self) -> None:
        """Start the service with LLM client."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()

        self._llm_client = LLMClient(agent_name="strategist")
        await self._llm_client.start()

        self._embedding_client = EmbeddingClient()
        await self._embedding_client.start()

        await self._require_kafka().start_consumer(
            topics=self._get_topics(),
            handler=self._handle_event_wrapper,
            group_id=f"{self.service_name}-events",
        )
        self.logger.info("service_started")

    async def _handle_event(self, event: Event) -> None:
        """Route events to handlers."""
        if event.event_type == "library.gap.detected":
            await self._handle_gap(event)
        elif event.event_type == "library.cluster.struggling":
            await self._handle_struggling(event)
        elif event.event_type == "library.task.comparative":
            await self._handle_comparative(event)

    async def _should_synthesize(self, cluster_id: str) -> bool:
        """Determine if synthesis is needed based on hypothesis state.

        Relaxed check: Only skip if there's a RECENT untested hypothesis (< 2 hours old).
        Old untested bullets that haven't been retrieved are dead weight - don't wait for them.
        CURATOR handles dedup, so redundant synthesis is caught downstream.
        """
        cluster_id_short = cluster_id[:8] if cluster_id else "unknown"

        try:
            # Only check for RECENT untested hypotheses (created < 2 hours ago)
            # Old bullets that haven't been tested are effectively abandoned
            recent_untested = await self._require_pool().fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM playbook_bullets pb
                    JOIN knowledge_edges ke ON ke.target_id = pb.bullet_id
                        AND ke.edge_type = 'solved_by'
                    WHERE ke.source_id = $1::uuid
                      AND pb.status = 'candidate'
                      AND pb.helpful_count = 0
                      AND pb.created_at > NOW() - INTERVAL '2 hours'
                )
                """,
                cluster_id,
            )

            if recent_untested:
                self.logger.debug(
                    "synthesis_skipped_recent_untested",
                    cluster_id=cluster_id_short,
                )
                return False

            return True
        except Exception as e:
            self.logger.warning(
                "hypothesis_check_failed",
                cluster_id=cluster_id_short,
                error=str(e),
            )
            # On error, allow synthesis to avoid blocking the loop
            return True

    def _record_attempt(self, cluster_id: str, success: bool, failure_count: int) -> None:
        """Record synthesis attempt outcome."""
        self._synthesis_attempts[cluster_id] = SynthesisAttempt(
            timestamp=time.time(),
            success=success,
            failure_count_at_attempt=failure_count,
        )

        # Cleanup old entries (keep last 200)
        if len(self._synthesis_attempts) > 200:
            sorted_attempts = sorted(
                self._synthesis_attempts.items(),
                key=lambda x: x[1].timestamp,
            )
            self._synthesis_attempts = dict(sorted_attempts[-100:])

    async def _handle_gap(self, event: Event) -> None:
        """Synthesize solution for knowledge gap."""
        payload = event.payload
        cluster_id: str | None = payload.get("cluster_id")
        cluster_label = payload.get("cluster_label", "Unknown")
        domain = payload.get("domain")
        failure_count = payload.get("failure_count", 0)

        if not cluster_id:
            self._record_event_drop(event.event_type, "missing_cluster_id")
            return

        # Information-based synthesis: skip if untested hypothesis exists
        if not await self._should_synthesize(cluster_id):
            self._record_event_drop(event.event_type, "untested_hypothesis_exists", cluster_id)
            return

        # Format sample turns
        sample_turns = payload.get("sample_turns", [])
        turns_text = self._format_turns(sample_turns)

        # Build prompt
        user_prompt = SYNTHESIS_GAP_USER.format(
            cluster_label=cluster_label,
            failure_count=failure_count,
            sample_turns=turns_text,
        )

        # Synthesize
        aku = await self._synthesize(user_prompt)

        # Record attempt AFTER synthesis (with outcome)
        self._record_attempt(cluster_id, success=(aku is not None), failure_count=failure_count)

        if not aku:
            self._record_event_drop(event.event_type, "synthesis_failed", cluster_id or "unknown")
            return

        # Pre-synthesis dedup: check if similar assertion already exists
        if await self._check_duplicate(aku.get("assertion", "")):
            self._record_event_drop(event.event_type, "duplicate_detected", cluster_id or "unknown")
            return

        # Emit aku.proposed
        await self._emit_aku(aku, cluster_id, domain, event.correlation_id)

    async def _handle_struggling(self, event: Event) -> None:
        """Synthesize alternative solution for struggling cluster."""
        payload = event.payload
        cluster_id: str | None = payload.get("cluster_id")
        cluster_label = payload.get("cluster_label", "Unknown")
        domain = payload.get("domain")
        # Use turn_count as proxy for failure tracking in struggling clusters
        turn_count = payload.get("turn_count", 0)

        if not cluster_id:
            self._record_event_drop(event.event_type, "missing_cluster_id")
            return

        # Information-based synthesis: skip if untested hypothesis exists
        if not await self._should_synthesize(cluster_id):
            self._record_event_drop(event.event_type, "untested_hypothesis_exists", cluster_id)
            return

        # Format existing solutions
        solutions = payload.get("existing_solutions", [])
        solutions_text = "\n".join(
            f"- {s.get('assertion', '')[:100]}" for s in solutions
        ) or "None documented"

        # Format sample failures
        failures = payload.get("sample_failures", [])
        failures_text = self._format_turns(failures)

        # Build prompt
        user_prompt = SYNTHESIS_STRUGGLING_USER.format(
            cluster_label=cluster_label,
            success_rate=payload.get("success_rate", 0),
            existing_solutions=solutions_text,
            sample_failures=failures_text,
        )

        # Synthesize
        aku = await self._synthesize(user_prompt)

        # Record attempt AFTER synthesis (with outcome)
        self._record_attempt(cluster_id, success=(aku is not None), failure_count=turn_count)

        if not aku:
            self._record_event_drop(event.event_type, "synthesis_failed", cluster_id or "unknown")
            return

        # Pre-synthesis dedup: check if similar assertion already exists
        if await self._check_duplicate(aku.get("assertion", "")):
            self._record_event_drop(event.event_type, "duplicate_detected", cluster_id or "unknown")
            return

        # Emit aku.proposed
        await self._emit_aku(aku, cluster_id, domain, event.correlation_id)

    async def _handle_comparative(self, event: Event) -> None:
        """Synthesize clarifying AKU from cross-session comparative analysis.

        This handler receives task-level comparison data from LIBRARIAN:
        - Same exact task with mixed success/failure outcomes
        - Success breakthrough snippet
        - Failure stuck snippet
        - Differential bullets (appear more in failures than successes)

        Goal: Identify semantic distinctions that explain why some sessions succeed.
        """
        payload = event.payload
        task_desc = payload.get("task_description", "")
        success_rate = payload.get("success_rate", 0)
        successes = payload.get("successes", 0)
        total = payload.get("total_sessions", 0)
        success_snippet = payload.get("success_snippet", "Not available")
        failure_snippet = payload.get("failure_snippet", "Not available")
        differential_bullets = payload.get("differential_bullets", [])

        if not task_desc:
            self._record_event_drop(event.event_type, "missing_task_description")
            return

        # Format differential bullets for prompt
        if differential_bullets:
            bullets_text = "\n".join(
                f"- [{b.get('bullet_id', 'unknown')[:8]}] (failures: {b.get('in_failures', 0)}, "
                f"successes: {b.get('in_successes', 0)}): {b.get('content', '')[:150]}"
                for b in differential_bullets
            )
        else:
            bullets_text = "No differential bullets identified"

        # Build prompt
        user_prompt = SYNTHESIS_COMPARATIVE_USER.format(
            task_description=task_desc,
            success_rate=success_rate,
            successes=successes,
            total=total,
            success_snippet=success_snippet or "Not available",
            failure_snippet=failure_snippet or "Not available",
            differential_bullets=bullets_text,
        )

        # Synthesize with comparative system prompt
        aku = await self._synthesize_comparative(user_prompt)

        if not aku:
            self._record_event_drop(event.event_type, "synthesis_failed", task_desc[:30])
            return

        # Pre-synthesis dedup
        if await self._check_duplicate(aku.get("assertion", "")):
            self._record_event_drop(event.event_type, "duplicate_detected", task_desc[:30])
            return

        # Emit aku.proposed (no cluster_id for task-based analysis)
        await self._require_kafka().publish_event(
            topic="aku.proposed",
            event_type="aku.proposed",
            payload={
                "aku": aku,
                "source": "strategist",
                "session_id": f"comparative-{hash(task_desc) % 10000}",
                "domain": "general",
                "task_description": task_desc,  # Track origin
            },
            correlation_id=event.correlation_id,
        )

        AKUS_TOTAL.labels(source="strategist", status="proposed").inc()

        self.logger.info(
            "comparative_aku_synthesized",
            task=task_desc[:50],
            success_rate=success_rate,
            situation=aku.get("situation", "")[:50],
        )

    async def _synthesize_comparative(self, user_prompt: str) -> Optional[dict]:
        """Call LLM with comparative analysis prompt."""
        if not self._llm_client:
            self.logger.error("llm_client_not_initialized")
            return None

        start_time = time.time()

        try:
            response = await self._llm_client.chat(
                messages=[
                    {"role": "system", "content": SYNTHESIS_COMPARATIVE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )
            LLM_CALLS.labels(service="strategist", status="success").inc()
        except Exception as e:
            LLM_CALLS.labels(service="strategist", status="error").inc()
            self.logger.error("comparative_synthesis_failed", error=str(e))
            return None
        finally:
            LLM_DURATION.labels(service="strategist").observe(time.time() - start_time)

        # Parse response - look for AKU or MISLEADING marker
        aku = parse_aku(response)

        if aku and self._validate_aku(aku):
            return aku

        # TODO: Handle MISLEADING marker to flag bullets for review
        if "---MISLEADING---" in response:
            self.logger.info(
                "misleading_bullet_detected",
                response=response[:500],
            )

        self.logger.debug("comparative_no_aku", response=response[:200])
        return None

    async def _synthesize(self, user_prompt: str) -> Optional[dict]:
        """Call LLM to synthesize an AKU."""
        if not self._llm_client:
            self.logger.error("llm_client_not_initialized")
            return None

        start_time = time.time()

        try:
            response = await self._llm_client.chat(
                messages=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )
            LLM_CALLS.labels(service="strategist", status="success").inc()
        except Exception as e:
            LLM_CALLS.labels(service="strategist", status="error").inc()
            self.logger.error("synthesis_llm_failed", error=str(e))
            return None
        finally:
            LLM_DURATION.labels(service="strategist").observe(time.time() - start_time)

        # Parse response using text parser
        aku = parse_aku(response)

        if aku and self._validate_aku(aku):
            return aku

        self.logger.debug("synthesis_no_aku", response=response[:200])
        return None

    def _validate_aku(self, aku: dict) -> bool:
        """Validate synthesized AKU (v4 format).

        v4 constraints:
        - situation: 10-60 characters
        - assertion: 20-100 characters
        - No modality/polarity (removed in v4 simplification)
        """
        situation = aku.get("situation", "")
        assertion = aku.get("assertion", "")

        # Minimum length constraints
        if len(situation) < 10 or len(assertion) < 20:
            return False

        # Maximum length constraints (v4)
        if len(situation) > 60 or len(assertion) > 100:
            self.logger.warning(
                "aku_exceeds_length",
                situation_len=len(situation),
                assertion_len=len(assertion),
            )
            return False

        return True

    async def _check_duplicate(self, assertion: str) -> bool:
        """Check if similar assertion already exists."""
        if not self._embedding_client or not self.pool:
            self.logger.warning("dedup_check_skipped", reason="not_initialized")
            return False

        try:
            embedding = self._embedding_client.embed(assertion)

            result = await self.pool.fetchrow(
                """
                SELECT bullet_id FROM playbook_bullets
                WHERE 1 - (assertion_embedding <=> $1::vector) > $2
                  AND status IN ('candidate', 'active')
                LIMIT 1
                """,
                _embedding_to_str(embedding),
                DEDUP_THRESHOLD,
            )

            return result is not None

        except Exception as e:
            self.logger.warning("dedup_check_failed", error=str(e))
            return False

    async def _emit_aku(
        self,
        aku: dict,
        cluster_id: str,
        domain: Optional[str],
        correlation_id: str,
    ) -> None:
        """Emit aku.proposed event.

        Includes target_cluster_id so CLUSTERER can link the bullet
        directly to the gap it was synthesized for.
        """
        if not self.kafka:
            self.logger.error("kafka_not_initialized")
            return

        await self.kafka.publish_event(
            topic="aku.proposed",
            event_type="aku.proposed",
            payload={
                "aku": aku,
                "source": "strategist",
                "session_id": f"synthetic-{cluster_id}",
                "domain": domain,
                "target_cluster_id": cluster_id,  # Close the dialogue loop
            },
            correlation_id=correlation_id,
        )

        AKUS_TOTAL.labels(source="strategist", status="proposed").inc()

        self.logger.info(
            "aku_synthesized",
            cluster_id=cluster_id,
            situation=aku.get("situation", "")[:50],
        )

    def _format_turns(self, turns: list[dict]) -> str:
        """Format turns for prompt."""
        if not turns:
            return "No sample turns available"

        formatted = []
        for t in turns[:3]:
            text = f"""Turn: {t.get('sub_task', 'Unknown task')}
Outcome: {t.get('micro_outcome', 'unknown')}
User: {(t.get('user_message') or '')[:2000]}
Assistant: {(t.get('assistant_response') or '')[:3000]}
"""
            formatted.append(text)

        return "\n---\n".join(formatted)
