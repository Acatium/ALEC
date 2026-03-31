"""REFLECTOR service - Owns the entire feedback loop.

Responsibilities:
1. Turn analysis (classify micro-outcomes via LLM)
2. Attribution (determine helped/harmed/neutral per bullet)
3. Counter updates (direct DB writes)
4. Edge creation (caused_failure for harmed bullets)
5. AKU extraction (stuck→recovery patterns)
6. Emit aku.proposed and attribution.resolved
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from core.common import AKUS_TOTAL, LLM_CALLS, LLM_DURATION, BaseService
from core.common.embedding_client import EmbeddingClient
from core.common.kafka_client import Event
from core.learning_loop.reflector.prompts_v2 import (
    AKU_EXTRACTION_SYSTEM,
    AKU_EXTRACTION_USER,
    TURN_ANALYSIS_SYSTEM,
    TURN_ANALYSIS_USER,
)
from core.learning_loop.shared.llm_client import LLMClient
from core.learning_loop.shared.text_parser import parse_aku, parse_turn_analysis

# Configuration
BUFFER_TTL_SECONDS = int(os.getenv("REFLECTOR_BUFFER_TTL_SECONDS", "3600"))
MAX_TURNS = int(os.getenv("REFLECTOR_MAX_TURNS", "100"))
CLUSTER_THRESHOLD = float(os.getenv("ALEC_CLUSTER_THRESHOLD", "0.65"))
BRIDGE_THRESHOLD = float(os.getenv("ALEC_BRIDGE_THRESHOLD", "0.70"))  # If similarity below, create bridge


def _embedding_to_str(embedding) -> str:
    """Convert embedding to pgvector string format.

    Handles both Python lists (from embedding client) and strings (from DB).
    """
    if isinstance(embedding, str):
        return embedding
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _extract_aku_id(aku: Any) -> Optional[str]:
    """Extract AKU ID from either a dict or string/UUID.

    SESSION sends akus_used as list[dict] with full AKU objects.
    This helper extracts the UUID string regardless of input format.

    Handles both old field names (bullet_id) and new (aku_id) for compatibility.
    """
    if isinstance(aku, dict):
        aku_id = aku.get("id") or aku.get("aku_id") or aku.get("bullet_id")
        return str(aku_id) if aku_id else None
    elif aku:
        return str(aku)
    return None


class ReflectorService(BaseService):
    """REFLECTOR - Turn analysis, attribution, and AKU extraction."""

    def __init__(self):
        super().__init__("reflector")
        self._buffers: dict[str, list[dict]] = {}  # session_id -> turns
        self._buffer_timestamps: dict[str, datetime] = {}
        self._llm_client: Optional[LLMClient] = None
        self._embedding_client: Optional[EmbeddingClient] = None

    def _get_topics(self) -> list[str]:
        return ["llm.response.received", "session.ended"]

    async def start(self) -> None:
        """Start the service with LLM client and Redis."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()
        await self._init_redis()  # For reading ADVISOR's initial_situation

        # Initialize clients
        self._llm_client = LLMClient()
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
        # Clean old buffers periodically
        self._cleanup_old_buffers()

        if event.event_type == "llm.response.received":
            await self._handle_llm_response(event)
        elif event.event_type == "session.ended":
            await self._handle_session_ended(event)

    async def _handle_llm_response(self, event: Event) -> None:
        """Buffer turn data for later analysis."""
        session_id = event.payload.get("session_id")
        if not session_id:
            self._record_event_drop(event.event_type, "missing_session_id")
            return

        turn_data = {
            "turn_number": event.payload.get("turn_number", 0),
            "user_message": event.payload.get("user_message", ""),
            "assistant_response": event.payload.get("assistant_response", ""),
            "bullets_shown": event.payload.get("bullets_used", []),
            "error_trace": event.payload.get("error_trace"),
        }

        if session_id not in self._buffers:
            self._buffers[session_id] = []
            self._buffer_timestamps[session_id] = datetime.now(timezone.utc)

        self._buffers[session_id].append(turn_data)

        # Truncate if too many turns
        if len(self._buffers[session_id]) > MAX_TURNS:
            self._buffers[session_id] = self._buffers[session_id][-MAX_TURNS:]

        self.logger.debug(
            "turn_buffered",
            session_id=session_id,
            turn_number=turn_data["turn_number"],
            buffer_size=len(self._buffers[session_id]),
        )

    async def _handle_session_ended(self, event: Event) -> None:
        """Analyze session turns and emit events."""
        session_id = event.payload.get("session_id")
        domain = event.payload.get("domain") or "general"  # Consistent with database defaults
        session_success = event.payload.get("success", False)

        if not session_id:
            self._record_event_drop(event.event_type, "missing_session_id")
            return

        turns = self._buffers.pop(session_id, [])
        self._buffer_timestamps.pop(session_id, None)

        if not turns:
            self._record_event_drop(event.event_type, "no_buffer_found", session_id)
            return

        # Collect all AKUs shown across turns (extract UUIDs from dicts)
        all_akus_shown = set()
        for turn in turns:
            for aku in turn.get("bullets_shown", []):
                aku_id = _extract_aku_id(aku)
                if aku_id:
                    all_akus_shown.add(aku_id)

        # 1. Analyze turns (LLM call to classify micro-outcomes)
        situation, resolved_turns = await self._analyze_turns(
            turns, list(all_akus_shown), session_success
        )

        # 1.5. Reconcile outcomes: if session succeeded but no 'solved', force last
        self._reconcile_outcomes(resolved_turns, session_success)

        # 2. Attribution: update counters + create edges
        for turn in resolved_turns:
            cluster_id = await self._find_cluster_for_turn(turn)

            for aku in turn.get("bullets_shown", []):
                aku_id = _extract_aku_id(aku)
                if not aku_id:
                    continue
                outcome = self._determine_outcome(aku_id, turn)
                await self._update_counter(aku_id, outcome)

                # Create caused_failure edge if harmed
                if outcome == "harmed" and cluster_id:
                    await self._upsert_edge(cluster_id, aku_id, "caused_failure")

        # 3. Extraction: detect stuck→recovery, emit AKUs
        for i, turn in enumerate(resolved_turns):
            if self._is_recovery(turn, resolved_turns, i):
                aku = await self._extract_learning(turns, resolved_turns, i)
                if aku:
                    await self._require_kafka().publish_event(
                        topic="aku.proposed",
                        event_type="aku.proposed",
                        payload={
                            "aku": aku,
                            "source": "reflector",
                            "session_id": session_id,
                            "domain": domain,
                            "evidence_turns": [i - 1, i],
                        },
                        correlation_id=event.correlation_id,
                    )
                    AKUS_TOTAL.labels(source="reflector", status="proposed").inc()
                    self.logger.info(
                        "aku_extracted",
                        session_id=session_id,
                        situation=aku.get("situation", "")[:50],
                    )

        # 4. Get ADVISOR's initial understanding and compare with resolved
        initial_situation = await self._get_initial_situation(session_id)

        # Compute similarity between initial and resolved situations
        similarity = 1.0  # Default: assume same if missing data
        resolved_embedding = None
        if situation and self._embedding_client:
            resolved_embedding = self._embedding_client.embed(situation)

        if initial_situation and resolved_embedding:
            initial_emb = initial_situation.get("embedding")
            if initial_emb:
                similarity = self._cosine_similarity(initial_emb, resolved_embedding)
                self.logger.info(
                    "situation_similarity_computed",
                    session_id=session_id,
                    initial=initial_situation.get("text", "")[:50],
                    resolved=situation[:50] if situation else "",
                    similarity=round(similarity, 3),
                )

        # Collect all helped/harmed bullets for bridge creation
        # Apply same policy as _determine_outcome: only trust harm on 'error' turns
        all_bullets_helped = set()
        all_bullets_harmed = set()
        for turn in resolved_turns:
            all_bullets_helped.update(turn.get("bullets_helped", []))
            # Only include harm from error turns (consistent with counter policy)
            if turn.get("micro_outcome") == "error":
                all_bullets_harmed.update(turn.get("bullets_harmed", []))

        # 5. Emit attribution.resolved for CLUSTERER
        await self._require_kafka().publish_event(
            topic="attribution.resolved",
            event_type="attribution.resolved",
            payload={
                "session_id": session_id,
                "domain": domain,
                "session_success": session_success,
                "situation": situation,  # REFLECTOR's resolved situation
                "resolved_embedding": resolved_embedding,
                # Semantic bridge data for CLUSTERER
                "initial_situation": initial_situation.get("text") if initial_situation else None,
                "initial_embedding": initial_situation.get("embedding") if initial_situation else None,
                "similarity": similarity,
                "bullets_helped": list(all_bullets_helped),
                "bullets_harmed": list(all_bullets_harmed),
                "resolved_turns": resolved_turns,
            },
            correlation_id=event.correlation_id,
        )

        # Log bridge opportunity
        if similarity < BRIDGE_THRESHOLD and initial_situation:
            self.logger.info(
                "semantic_bridge_opportunity",
                session_id=session_id,
                similarity=round(similarity, 3),
                initial=initial_situation.get("text", "")[:50],
                resolved=situation[:50] if situation else "",
            )

        self.logger.info(
            "session_analyzed",
            session_id=session_id,
            turn_count=len(resolved_turns),
            domain=domain,
            session_success=session_success,
            situation_similarity=round(similarity, 3),
        )

    async def _analyze_turns(
        self,
        turns: list[dict],
        akus_shown: list[str],
        session_success: bool,
    ) -> tuple[Optional[str], list[dict]]:
        """Analyze turns via LLM to classify micro-outcomes.

        Returns:
            Tuple of (situation, resolved_turns) where situation is the
            session-level problem description for clustering.
        """
        if not turns:
            return None, []

        # Fetch AKU content for context
        akus_info = await self._fetch_akus_info(akus_shown)

        # Build prompt with per-turn AKU info
        turns_json = json.dumps(
            [
                {
                    "turn_number": t["turn_number"],
                    "user_message": t.get("user_message", "")[:2000],
                    "assistant_response": t.get("assistant_response", "")[:4000],
                    "error_trace": t.get("error_trace", "")[:1500] if t.get("error_trace") else None,
                    "akus_shown": [_extract_aku_id(a) for a in t.get("bullets_shown", []) if _extract_aku_id(a)],
                }
                for t in turns
            ],
            indent=2,
        )

        akus_json = json.dumps(akus_info, indent=2)

        user_prompt = TURN_ANALYSIS_USER.format(
            akus_json=akus_json,
            turns_json=turns_json,
            session_success="SUCCESS" if session_success else "FAILURE",
        )

        # LLM call
        import time
        start_time = time.time()

        if not self._llm_client:
            self.logger.error("llm_client_not_initialized")
            return None, []

        try:
            response = await self._llm_client.chat(
                messages=[
                    {"role": "system", "content": TURN_ANALYSIS_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )
            LLM_CALLS.labels(service="reflector", status="success").inc()
        except Exception as e:
            LLM_CALLS.labels(service="reflector", status="error").inc()
            self.logger.error("llm_analysis_failed", error=str(e))
            # Fallback: return turns without analysis
            return None, [
                {
                    "turn_number": t["turn_number"],
                    "sub_task": "",
                    "micro_outcome": "progress",
                    "bullets_shown": t.get("bullets_shown", []),
                    "bullets_helped": [],
                    "bullets_harmed": [],
                    "user_message": t.get("user_message", ""),
                    "assistant_response": t.get("assistant_response", ""),
                }
                for t in turns
            ]
        finally:
            LLM_DURATION.labels(service="reflector").observe(time.time() - start_time)

        # Parse response using text parser
        situation, analyzed = parse_turn_analysis(response)
        if not analyzed:
            self.logger.warning("llm_response_parse_failed", response=response[:200])

        # Merge analysis with original turn data
        resolved = []
        for turn in turns:
            turn_num = turn["turn_number"]
            analysis = next(
                (a for a in analyzed if a.get("turn_number") == turn_num),
                {},
            )

            resolved.append({
                "turn_number": turn_num,
                "sub_task": analysis.get("sub_task", ""),
                "micro_outcome": analysis.get("micro_outcome", "progress"),
                "bullets_shown": turn.get("bullets_shown", []),
                "bullets_helped": analysis.get("bullets_helped", []),
                "bullets_harmed": analysis.get("bullets_harmed", []),
                "user_message": turn.get("user_message", ""),
                "assistant_response": turn.get("assistant_response", ""),
            })

        return situation, resolved

    async def _fetch_akus_info(self, aku_ids: list[str]) -> list[dict]:
        """Fetch AKU content for LLM context."""
        if not aku_ids:
            return []

        try:
            rows = await self._require_pool().fetch(
                """
                SELECT aku_id, situation, assertion
                FROM akus
                WHERE aku_id = ANY($1::uuid[])
                """,
                aku_ids,
            )
            return [
                {
                    "id": str(r["aku_id"]),
                    "situation": r["situation"],
                    "assertion": r["assertion"],
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("fetch_akus_failed", error=str(e))
            return []

    async def _find_cluster_for_turn(self, turn: dict) -> Optional[str]:
        """Find cluster by sub_task embedding."""
        sub_task = turn.get("sub_task")
        if not sub_task or not self._embedding_client:
            return None

        try:
            sub_task_emb = self._embedding_client.embed(sub_task)

            result = await self._require_pool().fetchrow(
                """
                SELECT cluster_id FROM problem_clusters
                WHERE 1 - (centroid <=> $1::vector) > $2
                ORDER BY 1 - (centroid <=> $1::vector) DESC
                LIMIT 1
                """,
                _embedding_to_str(sub_task_emb),
                CLUSTER_THRESHOLD,
            )

            return str(result["cluster_id"]) if result else None
        except Exception as e:
            self.logger.warning("find_cluster_failed", error=str(e))
            return None

    def _determine_outcome(self, aku_id: str, turn: dict) -> str:
        """Determine AKU outcome from turn analysis.

        Policy: Only trust harm attribution on 'error' turns.
        - 'error' turns have clear causal signal (API/env failure)
        - 'stuck' and 'progress' turns are too ambiguous (1.1:1 help:harm ratio)

        Note: Turn data still uses 'bullets_helped'/'bullets_harmed' field names
        for compatibility with prompts and CLUSTERER. These contain AKU IDs.
        """
        micro_outcome = turn.get("micro_outcome")

        if aku_id in turn.get("bullets_helped", []):
            return "helped"
        elif aku_id in turn.get("bullets_harmed", []):
            # Only trust harm on error turns - clear causal signal
            if micro_outcome == "error":
                return "harmed"
            else:
                return "neutral"  # stuck/progress turns are too ambiguous
        else:
            return "neutral"

    def _reconcile_outcomes(
        self, resolved_turns: list[dict], session_success: bool
    ) -> None:
        """Reconcile outcomes when session succeeded but no turns marked 'solved'.

        When external success signal (session completed task) disagrees with LLM
        classification (no 'solved' turns), trust the external signal and force
        the final turn to 'solved'.

        This ensures positive signal flows to Thompson Sampling even when the
        LLM under-classifies successful outcomes.

        Args:
            resolved_turns: List of turns with micro_outcome classifications.
                           Modified in-place.
            session_success: Whether the session successfully completed its task.
        """
        if not session_success or not resolved_turns:
            return

        has_solved = any(
            t.get("micro_outcome") == "solved" for t in resolved_turns
        )

        if not has_solved:
            original = resolved_turns[-1].get("micro_outcome", "unknown")
            resolved_turns[-1]["micro_outcome"] = "solved"
            self.logger.info(
                "outcome_reconciled",
                original=original,
                reconciled_to="solved",
            )

    async def _update_counter(self, aku_id: str, outcome: str) -> None:
        """Update AKU counter directly.

        v4 Simplified: Removed last_validated_at and updated_at columns.
        """
        column_map = {
            "helped": "helpful_count",
            "harmed": "harmful_count",
            "neutral": "neutral_count",
        }
        column = column_map.get(outcome, "neutral_count")

        try:
            pool = self._require_pool()
            await pool.execute(
                f"""
                UPDATE akus
                SET {column} = {column} + 1
                WHERE aku_id = $1
                """,
                aku_id,
            )
        except Exception as e:
            self.logger.warning(
                "counter_update_failed",
                aku_id=aku_id,
                outcome=outcome,
                error=str(e),
            )

    async def _upsert_edge(
        self, cluster_id: str, aku_id: str, edge_type: str
    ) -> None:
        """Create or strengthen edge.

        Note: target_type='aku' (v4 schema, was 'solution' or 'bullet').
        """
        try:
            await self._require_pool().execute(
                """
                INSERT INTO knowledge_edges (
                    source_type, source_id, target_type, target_id,
                    edge_type, weight, evidence_count
                )
                VALUES ('cluster', $1, 'aku', $2, $3, 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1,
                    weight = 1.0 - (1.0 / (knowledge_edges.evidence_count + 2)),
                    updated_at = NOW()
                """,
                cluster_id,
                aku_id,
                edge_type,
            )
        except Exception as e:
            self.logger.warning(
                "edge_upsert_failed",
                cluster_id=cluster_id,
                aku_id=aku_id,
                edge_type=edge_type,
                error=str(e),
            )

    def _is_recovery(self, turn: dict, all_turns: list[dict], index: int) -> bool:
        """Detect stuck/error → progress/solved transition."""
        if index == 0:
            return False

        prev = all_turns[index - 1].get("micro_outcome")
        curr = turn.get("micro_outcome")

        return prev in ("stuck", "error") and curr in ("progress", "solved")

    async def _extract_learning(
        self,
        raw_turns: list[dict],
        resolved_turns: list[dict],
        recovery_index: int,
    ) -> Optional[dict]:
        """Extract AKU from stuck→recovery transition."""
        if recovery_index < 1:
            return None

        stuck_turn = resolved_turns[recovery_index - 1]
        recovery_turn = resolved_turns[recovery_index]

        # Get raw turn content for more context
        raw_stuck = raw_turns[recovery_index - 1] if recovery_index - 1 < len(raw_turns) else {}
        raw_recovery = raw_turns[recovery_index] if recovery_index < len(raw_turns) else {}

        stuck_text = f"""Turn {stuck_turn['turn_number']}:
Sub-task: {stuck_turn.get('sub_task', 'Unknown')}
Outcome: {stuck_turn.get('micro_outcome', 'unknown')}
User: {raw_stuck.get('user_message', '')[:2000]}
Assistant: {raw_stuck.get('assistant_response', '')[:4000]}
Error: {raw_stuck.get('error_trace', '')[:1500] if raw_stuck.get('error_trace') else 'None'}"""

        recovery_text = f"""Turn {recovery_turn['turn_number']}:
Sub-task: {recovery_turn.get('sub_task', 'Unknown')}
Outcome: {recovery_turn.get('micro_outcome', 'unknown')}
User: {raw_recovery.get('user_message', '')[:2000]}
Assistant: {raw_recovery.get('assistant_response', '')[:4000]}"""

        user_prompt = AKU_EXTRACTION_USER.format(
            stuck_turn=stuck_text,
            recovery_turn=recovery_text,
        )

        if not self._llm_client:
            return None

        try:
            response = await self._llm_client.chat(
                messages=[
                    {"role": "system", "content": AKU_EXTRACTION_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )

            aku = parse_aku(response)

            if aku and self._validate_aku(aku):
                return aku

            return None

        except Exception as e:
            self.logger.warning("aku_extraction_failed", error=str(e))
            return None

    def _validate_aku(self, aku: dict) -> bool:
        """Validate AKU has required fields with sufficient content.

        v4 Simplified: Only length validation, no modality/polarity.
        Length constraints: situation ≤60, assertion ≤100 chars.
        """
        situation = aku.get("situation", "")
        assertion = aku.get("assertion", "")

        # Minimum length validation
        if len(situation) < 10 or len(assertion) < 20:
            return False

        # Maximum length validation (v4 constraints)
        if len(situation) > 60 or len(assertion) > 100:
            return False

        return True

    def _cleanup_old_buffers(self) -> None:
        """Remove buffers older than TTL."""
        now = datetime.now(timezone.utc)
        expired = []

        for session_id, timestamp in self._buffer_timestamps.items():
            age = (now - timestamp).total_seconds()
            if age > BUFFER_TTL_SECONDS:
                expired.append(session_id)

        for session_id in expired:
            self._buffers.pop(session_id, None)
            self._buffer_timestamps.pop(session_id, None)
            self.logger.debug("buffer_expired", session_id=session_id)

    async def _get_initial_situation(self, session_id: str) -> Optional[dict[Any, Any]]:
        """Read ADVISOR's cached initial situation from Redis.

        Returns dict with 'text' and 'embedding' if found.
        """
        try:
            cache_key = f"session:{session_id}:initial_situation"
            data = await self._require_redis().get(cache_key)
            if data:
                result: dict[Any, Any] = json.loads(data)
                return result
        except Exception as e:
            self.logger.warning("initial_situation_read_failed", session_id=session_id, error=str(e))
        return None

    def _cosine_similarity(self, emb1: list[float], emb2: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not emb1 or not emb2 or len(emb1) != len(emb2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = sum(a * a for a in emb1) ** 0.5
        norm2 = sum(b * b for b in emb2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))
