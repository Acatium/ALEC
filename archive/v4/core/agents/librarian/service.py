"""LIBRARIAN service - Library intelligence and hygiene.

Responsibilities:
1. Gap detection: clusters with failures but no solved_by edges
2. Struggling detection: clusters with solutions but poor success rate
3. Harmful bullet detection: bullets with high harm rate
4. Auto-archive: archive consistently harmful bullets
5. Task comparative analysis: cross-session learning for same-task patterns

Consumes: attribution.resolved (triggers periodic analysis)
Emits: library.gap.detected, library.cluster.struggling, library.task.comparative
"""

import os
from datetime import datetime, timezone
from typing import Optional

from core.common import BaseService
from core.common.kafka_client import Event

# Configuration
COOLDOWN_SECONDS = int(os.getenv("LIBRARIAN_COOLDOWN_SECONDS", "60"))
GAP_MIN_FAILURES = int(os.getenv("LIBRARIAN_GAP_MIN_FAILURES", "3"))
HARMFUL_THRESHOLD = int(os.getenv("LIBRARIAN_HARMFUL_THRESHOLD", "5"))
STRUGGLING_THRESHOLD = float(os.getenv("LIBRARIAN_STRUGGLING_THRESHOLD", "0.50"))

# Task comparative analysis config
TASK_MIN_SESSIONS = int(os.getenv("LIBRARIAN_TASK_MIN_SESSIONS", "4"))  # Min sessions for comparison
TASK_MIN_SUCCESSES = int(os.getenv("LIBRARIAN_TASK_MIN_SUCCESSES", "2"))  # Need successes to compare
TASK_MIN_FAILURES = int(os.getenv("LIBRARIAN_TASK_MIN_FAILURES", "2"))  # Need failures to compare


class LibrarianService(BaseService):
    """LIBRARIAN - Library intelligence and hygiene."""

    def __init__(self):
        super().__init__("librarian")
        self._last_analysis: Optional[datetime] = None

    def _get_topics(self) -> list[str]:
        return ["attribution.resolved"]

    async def _handle_event(self, event: Event) -> None:
        """Handle attribution.resolved - trigger periodic analysis."""
        if event.event_type == "attribution.resolved":
            await self._maybe_run_analysis(event)

    async def _maybe_run_analysis(self, event: Event) -> None:
        """Run analysis if cooldown has passed."""
        now = datetime.now(timezone.utc)

        if self._last_analysis:
            elapsed = (now - self._last_analysis).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                self.logger.debug(
                    "analysis_skipped_cooldown",
                    elapsed=elapsed,
                    cooldown=COOLDOWN_SECONDS,
                )
                return

        self._last_analysis = now

        # Run all analysis types
        await self._detect_gaps(event)
        await self._detect_struggling(event)
        await self._detect_task_comparative(event)
        await self._auto_archive_harmful()

        self.logger.info("librarian_analysis_completed")

    async def _detect_gaps(self, event: Event) -> None:
        """Find clusters with failures but no solutions."""
        domain = event.payload.get("domain")

        try:
            # No domain filter - detect gaps across all clusters
            gaps = await self._require_pool().fetch(
                """
                SELECT
                    pc.cluster_id,
                    pc.label,
                    pc.failure_count,
                    pc.success_count,
                    pc.domain
                FROM problem_clusters pc
                LEFT JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.failure_count >= $1
                GROUP BY pc.cluster_id
                HAVING COUNT(ke.edge_id) = 0
                ORDER BY pc.failure_count DESC
                LIMIT 10
                """,
                GAP_MIN_FAILURES,
            )

            for gap in gaps:
                # Get sample failed turns for context
                sample_turns = await self._get_sample_turns(
                    str(gap["cluster_id"]), limit=3
                )

                await self._require_kafka().publish_event(
                    topic="library.gap.detected",
                    event_type="library.gap.detected",
                    payload={
                        "cluster_id": str(gap["cluster_id"]),
                        "cluster_label": gap["label"],
                        "domain": gap.get("domain") or domain,
                        "failure_count": gap["failure_count"],
                        "success_count": gap["success_count"],
                        "sample_turns": sample_turns,
                    },
                    correlation_id=event.correlation_id,
                )

                self.logger.info(
                    "gap_detected",
                    cluster_id=str(gap["cluster_id"]),
                    failure_count=gap["failure_count"],
                )

        except Exception as e:
            self.logger.error("gap_detection_failed", error=str(e))

    async def _detect_struggling(self, event: Event) -> None:
        """Find clusters with solutions but poor success rate."""
        domain = event.payload.get("domain")

        try:
            struggling = await self._require_pool().fetch(
                """
                SELECT
                    pc.cluster_id,
                    pc.label,
                    pc.success_count,
                    pc.failure_count,
                    pc.success_count::float / NULLIF(pc.success_count + pc.failure_count, 0) as success_rate
                FROM problem_clusters pc
                JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.success_count + pc.failure_count >= 5
                  AND ($1::varchar IS NULL OR pc.domain = $1)
                GROUP BY pc.cluster_id
                HAVING pc.success_count::float / NULLIF(pc.success_count + pc.failure_count, 0) < $2
                ORDER BY success_rate ASC
                LIMIT 10
                """,
                domain,
                STRUGGLING_THRESHOLD,
            )

            for cluster in struggling:
                # Get existing solutions
                solutions = await self._get_cluster_solutions(str(cluster["cluster_id"]))
                # Get failed turns: 'error' OR 'stuck' (both indicate failure)
                sample_failures = await self._get_failure_turns(
                    str(cluster["cluster_id"]), limit=3
                )

                await self._require_kafka().publish_event(
                    topic="library.cluster.struggling",
                    event_type="library.cluster.struggling",
                    payload={
                        "cluster_id": str(cluster["cluster_id"]),
                        "cluster_label": cluster["label"],
                        "domain": domain,
                        "success_rate": cluster["success_rate"],
                        "turn_count": cluster["success_count"] + cluster["failure_count"],
                        "existing_solutions": solutions,
                        "sample_failures": sample_failures,
                    },
                    correlation_id=event.correlation_id,
                )

                self.logger.info(
                    "struggling_cluster",
                    cluster_id=str(cluster["cluster_id"]),
                    success_rate=cluster["success_rate"],
                )

        except Exception as e:
            self.logger.error("struggling_detection_failed", error=str(e))

    async def _auto_archive_harmful(self) -> None:
        """Archive bullets with consistently high harm rate.

        Requires sufficient sample size (10+) before archiving to avoid
        premature removal based on sparse data.
        """
        try:
            result = await self._require_pool().execute(
                """
                UPDATE playbook_bullets
                SET status = 'archived',
                    updated_at = NOW(),
                    metadata = jsonb_set(COALESCE(metadata, '{}'), '{archive_reason}', '"high_harm_rate_auto"')
                WHERE harmful_count >= $1
                  AND (helpful_count + harmful_count) >= 10
                  AND harmful_count > helpful_count
                  AND status NOT IN ('archived')
                """,
                HARMFUL_THRESHOLD,
            )

            if result and "UPDATE" in result:
                count = int(result.split(" ")[1])
                if count > 0:
                    self.logger.info("harmful_bullets_archived", count=count)

        except Exception as e:
            self.logger.error("auto_archive_failed", error=str(e))

    async def _get_sample_turns(
        self,
        cluster_id: str,
        outcome: Optional[str] = None,
        limit: int = 3,
    ) -> list[dict]:
        """Get sample turns for a cluster."""
        try:
            params: list = [cluster_id]
            param_idx = 2

            query = """
                SELECT
                    turn_id, session_id, turn_number,
                    sub_task, micro_outcome,
                    user_message, assistant_response
                FROM session_turns
                WHERE cluster_id = $1
            """

            if outcome:
                query += f" AND micro_outcome = ${param_idx}"
                params.append(outcome)
                param_idx += 1

            query += f" ORDER BY created_at DESC LIMIT ${param_idx}"
            params.append(limit)

            rows = await self._require_pool().fetch(query, *params)

            return [
                {
                    "turn_id": str(r["turn_id"]),
                    "session_id": str(r["session_id"]),
                    "sub_task": r["sub_task"],
                    "micro_outcome": r["micro_outcome"],
                    "user_message": r["user_message"][:2000] if r["user_message"] else None,
                    "assistant_response": r["assistant_response"][:3000] if r["assistant_response"] else None,
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("sample_turns_failed", error=str(e))
            return []

    async def _get_failure_turns(
        self,
        cluster_id: str,
        limit: int = 3,
    ) -> list[dict]:
        """Get sample failure turns (error OR stuck) for a cluster."""
        try:
            rows = await self._require_pool().fetch(
                """
                SELECT
                    turn_id, session_id, turn_number,
                    sub_task, micro_outcome,
                    user_message, assistant_response
                FROM session_turns
                WHERE cluster_id = $1
                  AND micro_outcome IN ('error', 'stuck')
                ORDER BY
                    CASE micro_outcome WHEN 'error' THEN 0 ELSE 1 END,
                    created_at DESC
                LIMIT $2
                """,
                cluster_id,
                limit,
            )

            return [
                {
                    "turn_id": str(r["turn_id"]),
                    "session_id": str(r["session_id"]),
                    "sub_task": r["sub_task"],
                    "micro_outcome": r["micro_outcome"],
                    "user_message": r["user_message"][:2000] if r["user_message"] else None,
                    "assistant_response": r["assistant_response"][:3000] if r["assistant_response"] else None,
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("failure_turns_failed", error=str(e))
            return []

    async def _get_cluster_solutions(self, cluster_id: str) -> list[dict]:
        """Get existing solutions for a cluster."""
        try:
            rows = await self._require_pool().fetch(
                """
                SELECT pb.bullet_id, pb.situation, pb.assertion
                FROM playbook_bullets pb
                JOIN knowledge_edges ke ON ke.target_id = pb.bullet_id
                WHERE ke.source_id = $1
                  AND ke.edge_type = 'solved_by'
                  AND pb.status = 'active'
                LIMIT 5
                """,
                cluster_id,
            )

            return [
                {
                    "bullet_id": str(r["bullet_id"]),
                    "situation": r["situation"],
                    "assertion": r["assertion"][:200],
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("cluster_solutions_failed", error=str(e))
            return []

    async def _detect_task_comparative(self, event: Event) -> None:
        """Cross-session learning: compare success vs failure for same tasks.

        Uses exact task description matching (from ## Task marker) to ensure
        we're comparing apples to apples. For tasks with mixed results,
        computes differential bullets and approach snippets for STRATEGIST.
        """
        try:
            # Find tasks with mixed success/failure (enough data for comparison)
            tasks_with_mixed_results = await self._require_pool().fetch(
                """
                WITH task_sessions AS (
                    SELECT
                        SUBSTRING(st.user_message FROM '## Task\n([^\n]+)') as task_desc,
                        st.session_id,
                        eto.success
                    FROM session_turns st
                    JOIN evaluation_task_outcomes eto ON st.session_id = eto.session_id
                    WHERE st.turn_number = 1
                      AND st.user_message LIKE '%## Task%'
                )
                SELECT
                    task_desc,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE success) as successes,
                    COUNT(*) FILTER (WHERE NOT success) as failures,
                    ROUND(100.0 * COUNT(*) FILTER (WHERE success) / COUNT(*), 1) as success_rate
                FROM task_sessions
                WHERE task_desc IS NOT NULL
                GROUP BY task_desc
                HAVING COUNT(*) >= $1
                   AND COUNT(*) FILTER (WHERE success) >= $2
                   AND COUNT(*) FILTER (WHERE NOT success) >= $3
                ORDER BY failures DESC
                LIMIT 5
                """,
                TASK_MIN_SESSIONS,
                TASK_MIN_SUCCESSES,
                TASK_MIN_FAILURES,
            )

            for task in tasks_with_mixed_results:
                task_desc = task["task_desc"]

                # Get differential bullets (appear in failures but not/rarely in successes)
                differential_bullets = await self._get_differential_bullets(task_desc)

                # Get success breakthrough snippet
                success_snippet = await self._get_success_snippet(task_desc)

                # Get failure stuck snippet
                failure_snippet = await self._get_failure_snippet(task_desc)

                # Only emit if we have meaningful differential signal
                if not differential_bullets and not (success_snippet and failure_snippet):
                    continue

                await self._require_kafka().publish_event(
                    topic="library.task.comparative",
                    event_type="library.task.comparative",
                    payload={
                        "task_description": task_desc,
                        "total_sessions": task["total"],
                        "successes": task["successes"],
                        "failures": task["failures"],
                        "success_rate": float(task["success_rate"]),
                        "success_snippet": success_snippet,
                        "failure_snippet": failure_snippet,
                        "differential_bullets": differential_bullets,
                    },
                    correlation_id=event.correlation_id,
                )

                self.logger.info(
                    "task_comparative_detected",
                    task=task_desc[:50],
                    success_rate=task["success_rate"],
                    differential_bullets=len(differential_bullets),
                )

        except Exception as e:
            self.logger.error("task_comparative_detection_failed", error=str(e))

    async def _get_differential_bullets(self, task_desc: str) -> list[dict]:
        """Get bullets that appear more in failures than successes for a task."""
        try:
            rows = await self._require_pool().fetch(
                """
                WITH task_sessions AS (
                    SELECT
                        st.session_id,
                        eto.success
                    FROM session_turns st
                    JOIN evaluation_task_outcomes eto ON st.session_id = eto.session_id
                    WHERE st.turn_number = 1
                      AND SUBSTRING(st.user_message FROM '## Task\n([^\n]+)') = $1
                ),
                session_bullets AS (
                    SELECT DISTINCT
                        ts.session_id,
                        ts.success,
                        unnest(st.bullets_shown)::text as bullet_id
                    FROM task_sessions ts
                    JOIN session_turns st ON st.session_id = ts.session_id
                    WHERE st.bullets_shown IS NOT NULL
                      AND array_length(st.bullets_shown, 1) > 0
                ),
                bullet_stats AS (
                    SELECT
                        bullet_id,
                        COUNT(DISTINCT session_id) FILTER (WHERE success) as in_successes,
                        COUNT(DISTINCT session_id) FILTER (WHERE NOT success) as in_failures
                    FROM session_bullets
                    GROUP BY bullet_id
                )
                SELECT
                    bs.bullet_id,
                    bs.in_successes,
                    bs.in_failures,
                    pb.content,
                    pb.situation
                FROM bullet_stats bs
                JOIN playbook_bullets pb ON pb.bullet_id::text = bs.bullet_id
                WHERE bs.in_failures > bs.in_successes
                ORDER BY (bs.in_failures - bs.in_successes) DESC, bs.in_failures DESC
                LIMIT 5
                """,
                task_desc,
            )

            return [
                {
                    "bullet_id": r["bullet_id"],
                    "in_successes": r["in_successes"],
                    "in_failures": r["in_failures"],
                    "content": r["content"][:200] if r["content"] else None,
                    "situation": r["situation"][:100] if r["situation"] else None,
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.warning("differential_bullets_failed", error=str(e))
            return []

    async def _get_success_snippet(self, task_desc: str) -> Optional[str]:
        """Get the breakthrough moment from a successful session."""
        try:
            row = await self._require_pool().fetchrow(
                """
                WITH task_sessions AS (
                    SELECT st.session_id
                    FROM session_turns st
                    JOIN evaluation_task_outcomes eto ON st.session_id = eto.session_id
                    WHERE st.turn_number = 1
                      AND SUBSTRING(st.user_message FROM '## Task\n([^\n]+)') = $1
                      AND eto.success = true
                )
                SELECT st.assistant_response
                FROM session_turns st
                JOIN task_sessions ts ON st.session_id = ts.session_id
                WHERE st.micro_outcome = 'solved'
                ORDER BY st.turn_number DESC
                LIMIT 1
                """,
                task_desc,
            )

            if row and row["assistant_response"]:
                return row["assistant_response"][:800]
            return None
        except Exception as e:
            self.logger.warning("success_snippet_failed", error=str(e))
            return None

    async def _get_failure_snippet(self, task_desc: str) -> Optional[str]:
        """Get the stuck point from a failed session."""
        try:
            row = await self._require_pool().fetchrow(
                """
                WITH task_sessions AS (
                    SELECT st.session_id
                    FROM session_turns st
                    JOIN evaluation_task_outcomes eto ON st.session_id = eto.session_id
                    WHERE st.turn_number = 1
                      AND SUBSTRING(st.user_message FROM '## Task\n([^\n]+)') = $1
                      AND eto.success = false
                )
                SELECT st.assistant_response
                FROM session_turns st
                JOIN task_sessions ts ON st.session_id = ts.session_id
                WHERE st.micro_outcome IN ('stuck', 'error')
                  AND st.turn_number >= 5
                ORDER BY st.turn_number DESC
                LIMIT 1
                """,
                task_desc,
            )

            if row and row["assistant_response"]:
                return row["assistant_response"][:800]
            return None
        except Exception as e:
            self.logger.warning("failure_snippet_failed", error=str(e))
            return None
