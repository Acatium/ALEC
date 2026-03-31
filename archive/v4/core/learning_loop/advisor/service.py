"""ADVISOR service - AKU retrieval and selection.

v4 Simplified Schema (gap-aku-001):
- Uses akus table (not playbook_bullets)
- Uses aku_id (not bullet_id)
- Removed modality/polarity/domain from SELECT queries
- Simplified return structure

Responsibilities:
1. Normalize task to "When [X]..." format via LLM (turn 1 only)
2. Vector search on situation_embedding
3. Cluster solutions via solved_by edges
4. Filter via caused_failure edges
5. Thompson Sampling with age decay
6. Write AKUs to Redis
7. Return cluster_id for SESSION to use next turn
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from core.common import BULLETS_RETRIEVED, BaseService
from core.common.embedding_client import EmbeddingClient
from core.common.kafka_client import Event
from core.learning_loop.advisor.prompts import (
    TASK_TO_SITUATION_SYSTEM,
    TASK_TO_SITUATION_USER,
)
from core.learning_loop.shared.llm_client import LLMClient


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
# Note: all-MiniLM-L6-v2 gives lower cosine similarity than expected even for
# semantically related concepts. 0.35 allows relevant AKUs to surface while
# Thompson Sampling handles quality filtering.
VECTOR_THRESHOLD = float(os.getenv("ALEC_VECTOR_THRESHOLD", "0.35"))
CLUSTER_THRESHOLD = float(os.getenv("ALEC_CLUSTER_THRESHOLD", "0.65"))
MAX_AKUS = int(os.getenv("ALEC_MAX_BULLETS", "8"))  # Keep env var name for compat
THOMPSON_FLOOR = float(os.getenv("ALEC_TS_FLOOR", "0.40"))
AGE_DECAY_RATE = float(os.getenv("ALEC_AGE_DECAY_RATE", "0.995"))
AGE_DECAY_MIN = float(os.getenv("ALEC_AGE_DECAY_MIN", "0.50"))


class AdvisorService(BaseService):
    """ADVISOR - AKU retrieval and Thompson Sampling selection."""

    def __init__(self):
        super().__init__("advisor")
        self._embedding_client: Optional[EmbeddingClient] = None
        self._llm_client: Optional[LLMClient] = None

    def _get_topics(self) -> list[str]:
        # Note: Event name will be renamed to akus.requested in gap-aku-002
        return ["bullets.requested"]

    async def start(self) -> None:
        """Start the service with Redis, embedding client, and LLM client."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()
        await self._init_redis()

        self._embedding_client = EmbeddingClient()
        await self._embedding_client.start()

        # LLM client for task normalization
        self._llm_client = LLMClient(agent_name="advisor")
        await self._llm_client.start()

        await self._require_kafka().start_consumer(
            topics=self._get_topics(),
            handler=self._handle_event_wrapper,
            group_id=f"{self.service_name}-events",
        )
        self.logger.info("service_started")

    async def _handle_event(self, event: Event) -> None:
        """Handle bullets.requested events."""
        if event.event_type == "bullets.requested":
            await self._handle_akus_requested(event)

    async def _handle_akus_requested(self, event: Event) -> None:
        """Select AKUs and write to Redis."""
        payload = event.payload
        session_id = payload.get("session_id")
        turn_number = payload.get("turn_number", 0)
        user_input = payload.get("problem_context", "")
        cluster_id = payload.get("cluster_id")  # Optional, from previous turn
        exclude = payload.get("bullets_already_shown", [])  # Will be renamed in gap-aku-002

        if not session_id:
            self._record_event_drop(event.event_type, "missing_session_id")
            return

        # Get situation embedding - cached from turn 1 or create new
        query_embedding = await self._get_situation_embedding(
            session_id, turn_number, user_input
        )
        if not query_embedding:
            self._record_event_drop(event.event_type, "embedding_failed", session_id)
            await self._write_empty_result(session_id, turn_number)
            return

        # Find cluster if not provided (first turn)
        if not cluster_id:
            cluster_id = await self._find_nearest_cluster(query_embedding)

        # Select AKUs with two-layer exclusion
        akus = await self._select_akus(
            embedding=query_embedding,
            exclude=exclude,
            cluster_id=cluster_id,
        )

        # Write to Redis WITH cluster_id for SESSION to use next turn
        await self._write_to_redis(
            session_id=session_id,
            turn_number=turn_number,
            akus=akus,
            cluster_id=cluster_id,
        )

        BULLETS_RETRIEVED.inc(len(akus))

        self.logger.info(
            "akus_selected",
            session_id=session_id,
            turn_number=turn_number,
            aku_count=len(akus),
            cluster_id=cluster_id,
        )

    async def _get_situation_embedding(
        self, session_id: str, turn_number: int, user_input: str
    ) -> Optional[list]:
        """Get situation embedding - use cached turn 1 embedding or create new.

        Turn 1 contains the task description which defines the situation.
        We normalize it to "When [X]..." format via LLM to match AKU format.
        Both the text and embedding are cached for REFLECTOR to compare later.
        """
        cache_key = f"session:{session_id}:initial_situation"

        # Try to get cached embedding (turns 2+)
        if turn_number > 1:
            try:
                cached = await self._require_redis().get(cache_key)
                if cached:
                    data = json.loads(cached)
                    emb: list[float] | None = data.get("embedding")
                    return emb
            except Exception as e:
                self.logger.warning("situation_cache_read_failed", error=str(e))

        # Turn 1 or cache miss: extract and normalize task
        task_text = self._extract_task(user_input)
        if not task_text:
            return None

        # Normalize task to "When [X]..." format via LLM
        situation = await self._normalize_task_to_situation(task_text)
        if not situation:
            # Fallback: use raw task if LLM fails
            situation = task_text

        # Embed normalized situation
        embedding = await self._build_embedding(situation)
        if not embedding:
            return None

        # Cache BOTH text and embedding for REFLECTOR to compare later
        if turn_number == 1:
            try:
                cache_data = {
                    "text": situation,
                    "embedding": embedding,
                }
                await self._require_redis().set(cache_key, json.dumps(cache_data), ex=86400)
                self.logger.info(
                    "initial_situation_cached",
                    session_id=session_id,
                    situation=situation[:80],
                )
            except Exception as e:
                self.logger.warning("situation_cache_write_failed", error=str(e))

        return embedding

    async def _normalize_task_to_situation(self, task_text: str) -> Optional[str]:
        """Convert task to 'When [X]...' format via LLM.

        This normalizes raw task descriptions to match the format of AKU
        situations, improving semantic similarity and vector search results.
        """
        if not self._llm_client:
            return None

        try:
            response = await self._llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": TASK_TO_SITUATION_USER.format(task_text=task_text),
                }],
                system_prompt=TASK_TO_SITUATION_SYSTEM,
                max_tokens=100,
            )

            # Clean response - extract just the "When..." part
            situation = response.strip()

            # Ensure it starts with "When"
            if not situation.lower().startswith("when"):
                situation = f"When {situation}"

            self.logger.info(
                "task_normalized",
                task=task_text[:50],
                situation=situation[:80],
            )
            return situation
        except Exception as e:
            self.logger.warning("task_normalization_failed", error=str(e))
            return None

    def _extract_task(self, user_input: str) -> Optional[str]:
        """Extract task description from turn 1 user input.

        Turn 1 format:
        '''
        You are an AI agent that completes tasks by writing Python code.

        ## Task
        Reset friends on venmo to be the same as my friends in my phone.

        ## User Information
        ...
        '''

        We extract the ## Task section for embedding.
        """
        if not user_input or len(user_input.strip()) < 10:
            return None

        # Try to extract ## Task section
        if "## Task" in user_input:
            start = user_input.find("## Task")
            # Find next section or end
            rest = user_input[start + 7:]  # Skip "## Task"
            end_markers = ["## User", "## Available", "## Instructions", "\n\n##"]
            end = len(rest)
            for marker in end_markers:
                idx = rest.find(marker)
                if idx != -1 and idx < end:
                    end = idx
            task = rest[:end].strip()
            if len(task) >= 10:
                return task

        # Fallback: use first 500 chars (likely contains task context)
        return user_input[:500]

    async def _build_embedding(self, text: str) -> Optional[list[float]]:
        """Build embedding from problem context."""
        if not text or len(text.strip()) < 10 or not self._embedding_client:
            return None

        try:
            return self._embedding_client.embed(text)
        except Exception as e:
            self.logger.warning("embedding_failed", error=str(e))
            return None

    async def _find_nearest_cluster(self, embedding: list[float]) -> Optional[str]:
        """Find nearest cluster for the query."""
        try:
            result = await self._require_pool().fetchrow(
                """
                SELECT cluster_id, 1 - (centroid <=> $1::vector) as similarity
                FROM problem_clusters
                WHERE 1 - (centroid <=> $1::vector) > $2
                ORDER BY similarity DESC
                LIMIT 1
                """,
                _embedding_to_str(embedding),
                CLUSTER_THRESHOLD,
            )
            return str(result["cluster_id"]) if result else None
        except Exception as e:
            self.logger.warning("cluster_search_failed", error=str(e))
            return None

    async def _select_akus(
        self,
        embedding: list[float],
        exclude: list[str],
        cluster_id: Optional[str],
    ) -> list[dict]:
        """Select AKUs with hypothesis-first, two-layer exclusion, and cold start fallback."""
        # 0. HYPOTHESIS-FIRST: Check for untested AKUs targeting this cluster
        #    These are directed hypotheses from STRATEGIST - test them BEFORE Thompson ranking
        hypotheses = []
        if cluster_id:
            hypotheses = await self._get_cluster_hypotheses(cluster_id, exclude)
            if hypotheses:
                self.logger.info(
                    "hypothesis_prioritized",
                    cluster_id=cluster_id[:8] if cluster_id else "none",
                    count=len(hypotheses),
                )

        # 1. Get candidates via vector search
        candidates = await self._vector_search(embedding, exclude)

        # 2. Add cluster solutions via solved_by edges
        if cluster_id:
            cluster_solutions = await self._get_cluster_solutions(cluster_id, exclude)
            candidates = self._merge_unique(candidates, cluster_solutions)

        # 3. COLD START FALLBACK: If no candidates from semantic search,
        #    try random untested AKUs to explore
        if not candidates and not hypotheses:
            candidates = await self._get_cold_start_candidates(exclude)
            self.logger.info(
                "cold_start_fallback",
                candidate_count=len(candidates),
            )

        # 4. Filter AKUs with caused_failure edges for this cluster
        if cluster_id:
            harmful_ids = await self._get_harmful_for_cluster(cluster_id)
            candidates = [c for c in candidates if str(c["aku_id"]) not in harmful_ids]

        # 5. Remove hypotheses from candidates to avoid duplication
        hypothesis_ids = {str(h["aku_id"]) for h in hypotheses}
        candidates = [c for c in candidates if str(c["aku_id"]) not in hypothesis_ids]

        # 6. Thompson Sampling rank (includes floor filter)
        ranked = self._thompson_rank(candidates)

        # 7. Hypotheses FIRST, then Thompson-ranked candidates
        final = hypotheses + ranked
        return final[:MAX_AKUS]

    async def _vector_search(
        self,
        embedding: list[float],
        exclude: list[str],
    ) -> list[dict]:
        """Search by SITUATION embedding.

        v4: Uses akus table, removed modality/polarity/domain from SELECT.
        """
        try:
            # Build exclude array for query
            exclude_uuids = [e for e in exclude if e]

            rows = await self._require_pool().fetch(
                """
                SELECT
                    a.aku_id, a.situation, a.assertion,
                    a.helpful_count, a.harmful_count, a.neutral_count,
                    a.created_at,
                    1 - (a.situation_embedding <=> $1::vector) as similarity
                FROM akus a
                WHERE a.status IN ('candidate', 'active')
                  AND NOT (a.aku_id = ANY($2::uuid[]))
                  AND 1 - (a.situation_embedding <=> $1::vector) > $3
                ORDER BY similarity DESC
                LIMIT 50
                """,
                _embedding_to_str(embedding),
                exclude_uuids if exclude_uuids else [],
                VECTOR_THRESHOLD,
            )

            return [dict(r) for r in rows]
        except Exception as e:
            self.logger.warning("vector_search_failed", error=str(e))
            return []

    async def _get_cluster_solutions(
        self, cluster_id: str, exclude: list[str]
    ) -> list[dict]:
        """Fetch AKUs linked via solved_by edges."""
        try:
            rows = await self._require_pool().fetch(
                """
                SELECT
                    a.aku_id, a.situation, a.assertion,
                    a.helpful_count, a.harmful_count, a.neutral_count,
                    a.created_at,
                    ke.weight as edge_weight
                FROM akus a
                JOIN knowledge_edges ke ON ke.target_id = a.aku_id
                WHERE ke.source_id = $1
                  AND ke.edge_type = 'solved_by'
                  AND a.status = 'active'
                  AND NOT (a.aku_id = ANY($2::uuid[]))
                """,
                cluster_id,
                exclude if exclude else [],
            )

            # Add similarity based on edge weight
            return [
                {**dict(r), "similarity": r.get("edge_weight", 0.7)}
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("cluster_solutions_failed", error=str(e))
            return []

    async def _get_harmful_for_cluster(self, cluster_id: str) -> set[str]:
        """Get AKUs with caused_failure edges to this cluster."""
        try:
            rows = await self._require_pool().fetch(
                """
                SELECT target_id FROM knowledge_edges
                WHERE source_id = $1 AND edge_type = 'caused_failure'
                """,
                cluster_id,
            )
            return {str(r["target_id"]) for r in rows}
        except Exception as e:
            self.logger.warning("harmful_lookup_failed", error=str(e))
            return set()

    async def _get_cold_start_candidates(self, exclude: list[str]) -> list[dict]:
        """Get untested AKUs for cold start exploration.

        When no AKUs match via vector search, we still need to try something
        so Thompson Sampling can learn. Prioritize AKUs with few trials.
        """
        try:
            exclude_uuids = [e for e in exclude if e]

            rows = await self._require_pool().fetch(
                """
                SELECT
                    a.aku_id, a.situation, a.assertion,
                    a.helpful_count, a.harmful_count, a.neutral_count,
                    a.created_at,
                    0.5 as similarity
                FROM akus a
                WHERE a.status IN ('candidate', 'active')
                  AND NOT (a.aku_id = ANY($1::uuid[]))
                ORDER BY (a.helpful_count + a.harmful_count + a.neutral_count) ASC,
                         RANDOM()
                LIMIT 20
                """,
                exclude_uuids if exclude_uuids else [],
            )

            return [dict(r) for r in rows]
        except Exception as e:
            self.logger.warning("cold_start_fetch_failed", error=str(e))
            return []

    async def _get_cluster_hypotheses(
        self, cluster_id: str, exclude: list[str]
    ) -> list[dict]:
        """Get untested AKUs linked to this cluster via solved_by edges.

        These are directed hypotheses - STRATEGIST analyzed this cluster's
        failures and synthesized solutions. They should be tested FIRST
        before falling back to Thompson Sampling.

        IMPORTANT: Linkage is via knowledge_edges, not a.cluster_id column.
        CLUSTERER creates solved_by edges when accepting AKUs from CURATOR.
        """
        try:
            exclude_uuids = [e for e in exclude if e]

            rows = await self._require_pool().fetch(
                """
                SELECT
                    a.aku_id, a.situation, a.assertion,
                    a.helpful_count, a.harmful_count, a.neutral_count,
                    a.created_at,
                    1.0 as similarity
                FROM akus a
                JOIN knowledge_edges ke ON ke.target_id = a.aku_id
                    AND ke.edge_type = 'solved_by'
                WHERE ke.source_id = $2::uuid
                  AND a.status = 'candidate'
                  AND (a.helpful_count + a.harmful_count + a.neutral_count) < 5
                  AND NOT (a.aku_id = ANY($1::uuid[]))
                ORDER BY a.created_at DESC
                LIMIT 3
                """,
                exclude_uuids if exclude_uuids else [],
                cluster_id,
            )

            return [dict(r) for r in rows]
        except Exception as e:
            self.logger.warning("hypothesis_fetch_failed", error=str(e))
            return []

    def _merge_unique(
        self, candidates: list[dict], additions: list[dict]
    ) -> list[dict]:
        """Merge two lists, avoiding duplicates by id."""
        seen_ids = {str(c["aku_id"]) for c in candidates}
        merged = candidates.copy()

        for a in additions:
            if str(a["aku_id"]) not in seen_ids:
                merged.append(a)
                seen_ids.add(str(a["aku_id"]))

        return merged

    def _thompson_rank(self, candidates: list[dict]) -> list[dict]:
        """Rank candidates by Thompson Sampling with age decay.

        v4: Removed modality/polarity from return structure.
        """
        scored = []
        now = datetime.now(timezone.utc)

        for c in candidates:
            # Thompson sample from Beta distribution
            alpha = c.get("helpful_count", 0) + 1
            beta_param = c.get("harmful_count", 0) + 0.2 * c.get("neutral_count", 0) + 1
            ts_sample = np.random.beta(alpha, beta_param)

            # Floor filter (skip proven-bad AKUs)
            if ts_sample < THOMPSON_FLOOR:
                continue

            # Age decay using created_at
            created_at = c.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_days = (now - created_at).days
            else:
                age_days = 0

            age_decay = max(AGE_DECAY_MIN, AGE_DECAY_RATE ** age_days)

            # Combined score (convert Decimal to float for pgvector results)
            similarity = float(c.get("similarity", 0.5))
            score = similarity * ts_sample * age_decay

            scored.append({
                "id": str(c["aku_id"]),
                "situation": c["situation"],
                "assertion": c["assertion"],
                "score": score,
                "similarity": similarity,
                "ts_sample": ts_sample,
            })

        return sorted(scored, key=lambda x: x["score"], reverse=True)

    async def _write_to_redis(
        self,
        session_id: str,
        turn_number: int,
        akus: list[dict],
        cluster_id: Optional[str],
    ) -> None:
        """Write AKUs to Redis with fallback caching.

        Note: Redis key names will be renamed in gap-aku-002.
        """
        key = f"session:{session_id}:turn:{turn_number}:bullets"  # Renamed in gap-aku-002
        cache_key = f"session:{session_id}:bullets_cache"
        ready_key = f"session:{session_id}:turn:{turn_number}:bullets_ready"

        # Convert non-JSON-serializable objects to strings
        serializable_akus = []
        for aku in akus:
            sa = {}
            for k, v in aku.items():
                if hasattr(v, 'hex'):  # UUID
                    sa[k] = str(v)
                elif hasattr(v, 'isoformat'):  # datetime
                    sa[k] = v.isoformat()
                elif isinstance(v, (int, float, str, bool, type(None), list, dict)):
                    sa[k] = v
                else:
                    sa[k] = str(v)  # Fallback for any other type
            serializable_akus.append(sa)

        data = {
            "bullets": serializable_akus,  # Key name kept for SESSION compat (gap-aku-002)
            "cluster_id": str(cluster_id) if cluster_id else None,
        }

        try:
            # Write turn-specific and cache
            redis = self._require_redis()
            await redis.set(key, json.dumps(data), ex=3600)
            await redis.set(cache_key, json.dumps(data), ex=86400)  # 24h fallback
            await redis.set(ready_key, "1", ex=3600)

            self.logger.debug(
                "redis_write_success",
                session_id=session_id,
                turn_number=turn_number,
                aku_count=len(akus),
            )
        except Exception as e:
            self.logger.error(
                "redis_write_failed",
                session_id=session_id,
                error=str(e),
            )

    async def _write_empty_result(self, session_id: str, turn_number: int) -> None:
        """Write empty result to Redis."""
        await self._write_to_redis(session_id, turn_number, [], None)
