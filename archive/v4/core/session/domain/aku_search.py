"""AKU Search Tool for LLM-based knowledge retrieval.

Provides a tool that allows Haiku to search the knowledge base directly
during reasoning, bypassing ADVISOR's LLM normalization step.
"""

import math
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

import asyncpg

from core.common.observability import setup_logging

logger = setup_logging("aku-search")

# Configuration from environment
SIMILARITY_THRESHOLD = float(os.getenv("AKU_SIMILARITY_THRESHOLD", "0.35"))
MAX_RESULTS = int(os.getenv("AKU_MAX_RESULTS", "8"))
TS_FLOOR = float(os.getenv("AKU_TS_FLOOR", "0.25"))
AGE_DECAY_RATE = float(os.getenv("AKU_AGE_DECAY_RATE", "0.005"))


# Tool definition for Anthropic API
SEARCH_KNOWLEDGE_TOOL = {
    "name": "search_knowledge",
    "description": """Search the knowledge base for constraints and patterns.

Use this when:
- About to call an unfamiliar API
- Encountering an unexpected error
- Want to verify your approach

Returns constraints (#C), solutions (#S), and reference (#R) with effectiveness scores.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What you're trying to do. Be specific."
            }
        },
        "required": ["query"]
    }
}


@dataclass
class SearchResult:
    """Result from a knowledge search."""

    bullet_id: UUID
    situation: str
    assertion: str
    polarity: str
    category: str
    similarity: float
    effectiveness: float
    confidence: str  # "PROVEN", "TESTED", "UNTESTED"
    helpful_count: int
    harmful_count: int


@dataclass
class AKUSearchResult:
    """Full result from AKU search."""

    bullets: list[SearchResult] = field(default_factory=list)
    cluster_id: Optional[str] = None
    formatted: str = ""


class AKUSearchTool:
    """Tool for searching AKUs directly from PostgreSQL.

    Replaces ADVISOR's pre-computed bullet selection with
    on-demand search during LLM reasoning.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize the search tool.

        Args:
            pool: asyncpg connection pool.
        """
        self.pool = pool
        self._embedding_client = None
        self.logger = logger

    def _get_embedding_client(self):
        """Lazy load embedding client (avoids import at module level)."""
        if self._embedding_client is None:
            from core.common.embedding_client import EmbeddingClient
            self._embedding_client = EmbeddingClient.get_instance()
        return self._embedding_client

    async def search(
        self,
        query: str,
        cluster_id: Optional[str] = None,
        max_results: int = MAX_RESULTS,
    ) -> AKUSearchResult:
        """Search for relevant AKUs.

        Args:
            query: Natural language query (Haiku's search terms).
            cluster_id: Optional cluster ID for filtering caused_failure edges.
            max_results: Maximum results to return.

        Returns:
            AKUSearchResult with bullets, cluster_id, and formatted text.
        """
        self.logger.info(
            "search_started",
            query=query[:100],
            cluster_id=cluster_id,
        )

        # 1. Embed the query (no LLM normalization!)
        embedding_client = self._get_embedding_client()
        embedding = embedding_client.embed(query)

        # 2. Find nearest cluster if not provided
        if not cluster_id:
            cluster_id = await self._find_nearest_cluster(embedding)

        # 3. Get excluded bullets (caused_failure edges for this cluster)
        excluded_ids = await self._get_cluster_exclusions(cluster_id) if cluster_id else set()

        # 4. Vector search with Thompson Sampling ranking
        results = await self._vector_search(
            embedding=embedding,
            excluded_ids=excluded_ids,
            max_results=max_results,
        )

        # 5. Format for LLM
        formatted = self._format_for_llm(results)

        self.logger.info(
            "search_completed",
            query=query[:100],
            results_count=len(results),
            cluster_id=cluster_id,
        )

        return AKUSearchResult(
            bullets=results,
            cluster_id=cluster_id,
            formatted=formatted,
        )

    def _embedding_to_str(self, embedding: list[float]) -> str:
        """Convert embedding list to pgvector string format.

        Args:
            embedding: Embedding as Python list.

        Returns:
            String format for pgvector: '[0.1, 0.2, ...]'
        """
        return "[" + ",".join(str(v) for v in embedding) + "]"

    async def _find_nearest_cluster(self, embedding: list[float]) -> Optional[str]:
        """Find the nearest problem cluster for a query embedding.

        Args:
            embedding: Query embedding vector.

        Returns:
            Cluster ID string or None.
        """
        embedding_str = self._embedding_to_str(embedding)
        row = await self.pool.fetchrow(
            """
            SELECT cluster_id::text,
                   1 - (centroid <=> $1::vector) as similarity
            FROM problem_clusters
            WHERE status = 'active'
              AND centroid IS NOT NULL
            ORDER BY centroid <=> $1::vector
            LIMIT 1
            """,
            embedding_str,
        )

        if row and row["similarity"] > 0.3:
            return str(row["cluster_id"])
        return None

    async def _get_cluster_exclusions(self, cluster_id: str) -> set[UUID]:
        """Get bullets that caused failures for this cluster.

        Args:
            cluster_id: Cluster ID string.

        Returns:
            Set of bullet UUIDs to exclude.
        """
        try:
            cluster_uuid = UUID(cluster_id)
        except ValueError:
            return set()

        rows = await self.pool.fetch(
            """
            SELECT target_id
            FROM knowledge_edges
            WHERE source_id = $1
              AND source_type = 'cluster'
              AND edge_type = 'caused_failure'
            """,
            cluster_uuid,
        )

        return {row["target_id"] for row in rows}

    async def _vector_search(
        self,
        embedding: list[float],
        excluded_ids: set[UUID],
        max_results: int,
    ) -> list[SearchResult]:
        """Execute vector search with Thompson Sampling ranking.

        Args:
            embedding: Query embedding vector.
            excluded_ids: Bullet IDs to exclude.
            max_results: Maximum results.

        Returns:
            List of SearchResult objects.
        """
        # Convert excluded_ids to list for SQL
        excluded_list = list(excluded_ids) if excluded_ids else []

        # Convert embedding to pgvector string format
        embedding_str = self._embedding_to_str(embedding)

        rows = await self.pool.fetch(
            """
            SELECT bullet_id, situation, assertion, polarity, category,
                   1 - (situation_embedding <=> $1::vector) as similarity,
                   helpful_count, harmful_count, neutral_count,
                   created_at
            FROM playbook_bullets
            WHERE status IN ('candidate', 'active')
              AND situation_embedding IS NOT NULL
              AND 1 - (situation_embedding <=> $1::vector) > $2
              AND NOT (bullet_id = ANY($3::uuid[]))
            ORDER BY 1 - (situation_embedding <=> $1::vector) DESC
            LIMIT $4
            """,
            embedding_str,
            SIMILARITY_THRESHOLD,
            excluded_list,
            max_results * 3,  # Get more candidates for TS ranking
        )

        # Apply Thompson Sampling and age decay
        results: list[SearchResult] = []
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        def _get_days_old(created_at) -> int:
            """Calculate days old, handling timezone-naive datetimes."""
            if not created_at:
                return 0
            # If created_at is timezone-naive, assume UTC
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return (now - created_at).days

        for row in rows:
            helpful = row["helpful_count"] or 0
            harmful = row["harmful_count"] or 0
            neutral = row["neutral_count"] or 0

            # Thompson Sampling score
            alpha = helpful + 1
            beta = harmful + 0.2 * neutral + 1
            ts_score = alpha / (alpha + beta)

            # Skip if below TS floor
            if ts_score < TS_FLOOR:
                continue

            # Age decay
            days_old = _get_days_old(row["created_at"])
            age_decay = math.exp(-days_old * AGE_DECAY_RATE)

            # Final score (used for sorting later)
            _ = row["similarity"] * ts_score * age_decay  # Computed for reference

            # Determine confidence level
            total_trials = helpful + harmful
            if total_trials < 5:
                confidence = "UNTESTED"
            elif helpful / (helpful + harmful + 0.001) >= 0.8:
                confidence = "PROVEN"
            else:
                confidence = "TESTED"

            results.append(SearchResult(
                bullet_id=row["bullet_id"],
                situation=row["situation"],
                assertion=row["assertion"],
                polarity=row["polarity"],
                category=row["category"],
                similarity=row["similarity"],
                effectiveness=ts_score,
                confidence=confidence,
                helpful_count=helpful,
                harmful_count=harmful,
            ))

        # Sort by final score and limit
        results.sort(key=lambda r: r.similarity * r.effectiveness, reverse=True)
        return results[:max_results]

    def _format_for_llm(self, results: list[SearchResult]) -> str:
        """Format search results for LLM consumption.

        Args:
            results: List of SearchResult objects.

        Returns:
            Formatted string for LLM.
        """
        if not results:
            return "No relevant knowledge found."

        lines = ["## Relevant Knowledge\n"]

        # Group by category
        by_category: dict[str, list[SearchResult]] = {}
        for r in results:
            cat = r.category or "other"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(r)

        # Category code mapping
        category_codes = {
            "constraints": "#C",
            "solutions": "#S",
            "cheat_sheets": "#R",
            "reference": "#R",
            "examples": "#E",
            "meta_prompts": "#G",
            "guidance": "#G",
        }

        idx = 1
        for category, bullets in by_category.items():
            code = category_codes.get(category, "#K")
            for b in bullets:
                # Include confidence tag
                confidence_tag = f"[{b.confidence}]" if b.confidence != "TESTED" else ""

                # Format polarity
                polarity_prefix = ""
                if b.polarity == "dont":
                    polarity_prefix = "DON'T: "
                elif b.polarity == "know":
                    polarity_prefix = "NOTE: "

                lines.append(
                    f"[{idx}] {code} {confidence_tag} "
                    f"When {b.situation}: {polarity_prefix}{b.assertion}"
                )
                idx += 1

        return "\n".join(lines)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the tool definition for Anthropic API.

        Returns:
            Tool definition dict.
        """
        return SEARCH_KNOWLEDGE_TOOL
