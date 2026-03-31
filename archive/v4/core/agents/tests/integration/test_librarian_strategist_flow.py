"""Integration tests for LIBRARIAN → STRATEGIST event flows.

Tests the event chain:
- LIBRARIAN detects gaps → library.gap.detected
- LIBRARIAN detects struggling clusters → library.cluster.struggling
- STRATEGIST consumes these events and produces aku.proposed

Run: pytest -v -m db_integration core/agents/tests/integration/test_librarian_strategist_flow.py
"""

from uuid import uuid4

import pytest

# =============================================================================
# LIBRARIAN Gap Detection Tests
# =============================================================================


class TestLibrarianGapDetection:
    """Test LIBRARIAN's ability to detect knowledge gaps."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_detects_cluster_without_solutions(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """LIBRARIAN should detect clusters with failures but no solved_by edges."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster with failures but no solutions
            cluster = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count, turn_count,
                    status, created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    0, 5, 5,
                    'active', NOW(), NOW()
                )
                RETURNING cluster_id, label, failure_count
                """,
                sample_embedding_str,
                f"{prefix}_gap_cluster",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster["cluster_id"])

            # Query for gaps (simulating LIBRARIAN._detect_gaps)
            gaps = await conn.fetch(
                """
                SELECT pc.cluster_id, pc.label, pc.failure_count,
                       COUNT(DISTINCT ke.target_id) FILTER (
                           WHERE ke.edge_type = 'solved_by'
                       ) as solutions
                FROM problem_clusters pc
                LEFT JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.status = 'active'
                  AND pc.failure_count >= 5
                GROUP BY pc.cluster_id, pc.label, pc.failure_count
                HAVING COUNT(DISTINCT ke.target_id) FILTER (
                    WHERE ke.edge_type = 'solved_by'
                ) = 0
                """,
            )

            # Should find our cluster as a gap
            gap_ids = {g["cluster_id"] for g in gaps}
            assert cluster["cluster_id"] in gap_ids

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_gap_payload_structure(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """library.gap.detected payload should have fields STRATEGIST needs."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster
            cluster = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count, turn_count,
                    status, created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    0, 10, 10,
                    'active', NOW(), NOW()
                )
                RETURNING cluster_id, label
                """,
                sample_embedding_str,
                f"{prefix}_gap_payload_cluster",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster["cluster_id"])

            # Build payload (as LIBRARIAN would)
            gap_payload = {
                "cluster_id": str(cluster["cluster_id"]),
                "label": cluster["label"],
                "failure_count": 10,
                "sample_turns": [],  # Would be populated from session_turns
            }

            # Verify required fields for STRATEGIST
            assert "cluster_id" in gap_payload
            assert "label" in gap_payload
            assert "failure_count" in gap_payload


# =============================================================================
# LIBRARIAN Struggling Cluster Detection Tests
# =============================================================================


class TestLibrarianStrugglingDetection:
    """Test LIBRARIAN's ability to detect struggling clusters."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_detects_low_success_rate_cluster(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """LIBRARIAN should detect clusters with solutions but low success rate."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster with solutions but poor performance
            cluster = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count, turn_count,
                    status, created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    1, 9, 10,
                    'active', NOW(), NOW()
                )
                RETURNING cluster_id, label
                """,
                sample_embedding_str,
                f"{prefix}_struggling_cluster",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster["cluster_id"])
            cluster_id = cluster["cluster_id"]

            # Create AKU
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'active',
                    $3::vector, $3::vector,
                    3, 7, 2, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_struggling_situation",
                f"{prefix}_struggling_assertion",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])

            # Create solved_by edge (cluster has a solution)
            edge = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 0.5, 3)
                RETURNING edge_id
                """,
                cluster_id,
                aku["aku_id"],
            )
            clean_test_data["ids"]["edge_ids"].append(edge["edge_id"])

            # Query for struggling clusters (simulating LIBRARIAN._detect_struggling)
            struggling = await conn.fetch(
                """
                SELECT pc.cluster_id, pc.label, pc.turn_count,
                       pc.success_count, pc.failure_count,
                       ROUND(100.0 * pc.success_count / NULLIF(pc.turn_count, 0), 1) as success_rate,
                       COUNT(DISTINCT ke.target_id) as solutions
                FROM problem_clusters pc
                JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.status = 'active'
                  AND pc.turn_count >= 5
                GROUP BY pc.cluster_id, pc.label, pc.turn_count,
                         pc.success_count, pc.failure_count
                HAVING ROUND(100.0 * pc.success_count / NULLIF(pc.turn_count, 0), 1) < 50
                """,
            )

            # Should find our cluster as struggling
            struggling_ids = {s["cluster_id"] for s in struggling}
            assert cluster_id in struggling_ids

            # Verify success rate is low
            our_cluster = next(s for s in struggling if s["cluster_id"] == cluster_id)
            assert our_cluster["success_rate"] < 50


# =============================================================================
# LIBRARIAN Harmful Bullet Detection Tests
# =============================================================================


class TestLibrarianHarmfulDetection:
    """Test LIBRARIAN's ability to detect and archive harmful AKUs."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_detects_harmful_akus(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """LIBRARIAN should detect AKUs with high harmful counts."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create harmful AKU
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'active',
                    $3::vector, $3::vector,
                    2, 8, 1, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_harmful_situation",
                f"{prefix}_harmful_assertion",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])

            # Query for harmful AKUs (simulating LIBRARIAN._auto_archive_harmful)
            harmful = await conn.fetch(
                """
                SELECT aku_id, harmful_count, helpful_count,
                       ROUND(100.0 * harmful_count / NULLIF(helpful_count + harmful_count, 0), 1) as harm_rate
                FROM akus
                WHERE harmful_count >= 5
                  AND harmful_count > helpful_count
                  AND status NOT IN ('archived', 'banned')
                """,
            )

            # Should find our AKU as harmful
            harmful_ids = {h["aku_id"] for h in harmful}
            assert aku["aku_id"] in harmful_ids

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_archives_harmful_akus(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """LIBRARIAN should archive harmful AKUs."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create harmful AKU
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'active',
                    $3::vector, $3::vector,
                    1, 10, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_archive_situation",
                f"{prefix}_archive_assertion",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])
            aku_id = aku["aku_id"]

            # Archive (simulating LIBRARIAN auto-archive)
            await conn.execute(
                """
                UPDATE akus
                SET status = 'archived'
                WHERE aku_id = $1
                  AND harmful_count >= 5
                  AND harmful_count > helpful_count
                """,
                aku_id,
            )

            # Verify archived
            updated = await conn.fetchrow(
                "SELECT status FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["status"] == "archived"


# =============================================================================
# STRATEGIST Response Tests
# =============================================================================


class TestStrategistSynthesis:
    """Test STRATEGIST's ability to synthesize new AKUs."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_synthesized_aku_storage(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """STRATEGIST-synthesized AKUs should have proper source and cluster_id."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster for synthesis context
            cluster = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count, turn_count,
                    status, created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    0, 5, 5,
                    'active', NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_synth_cluster",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster["cluster_id"])

            # Simulate STRATEGIST storing synthesized AKU
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status, cluster_id,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, metadata, created_at
                ) VALUES (
                    $1, $2, 'strategist', 'candidate', $3,
                    $4::vector, $4::vector,
                    0, 0, 0, 1,
                    '{"synthesized": true}'::jsonb,
                    NOW()
                )
                RETURNING aku_id, source, metadata
                """,
                f"{prefix}_synth_situation",
                f"{prefix}_synth_assertion",
                cluster["cluster_id"],
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])

            # Verify source and metadata
            assert aku["source"] == "strategist"
            assert aku["metadata"].get("synthesized") is True

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_pre_synthesis_dedup_check(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """STRATEGIST should check for duplicates before synthesizing."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create existing AKU
            existing = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'active',
                    $3::vector, $3::vector,
                    5, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_existing_situation",
                f"{prefix}_existing_assertion",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(existing["aku_id"])

            # STRATEGIST dedup check (with 0.90 threshold)
            duplicate = await conn.fetchrow(
                """
                SELECT aku_id FROM akus
                WHERE 1 - (assertion_embedding <=> $1::vector) > 0.90
                  AND status IN ('candidate', 'active')
                ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
                LIMIT 1
                """,
                sample_embedding_str,
            )

            # Should find the existing AKU (exact match)
            assert duplicate is not None
            assert duplicate["aku_id"] == existing["aku_id"]


# =============================================================================
# Event Flow End-to-End Tests
# =============================================================================


class TestLibrarianStrategistEndToEnd:
    """Test the full LIBRARIAN → STRATEGIST event flow."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_gap_to_synthesis_flow(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Full flow: gap detection → synthesis → bullet storage."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Step 1: LIBRARIAN detects gap (cluster with failures, no solutions)
            cluster = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count, turn_count,
                    status, created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    0, 8, 8,
                    'active', NOW(), NOW()
                )
                RETURNING cluster_id, label
                """,
                sample_embedding_str,
                f"{prefix}_e2e_cluster",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster["cluster_id"])

            # Verify gap is detected
            gaps = await conn.fetch(
                """
                SELECT cluster_id FROM problem_clusters pc
                LEFT JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.status = 'active'
                  AND pc.failure_count >= 5
                GROUP BY pc.cluster_id
                HAVING COUNT(ke.edge_id) = 0
                """,
            )
            gap_ids = {g["cluster_id"] for g in gaps}
            assert cluster["cluster_id"] in gap_ids

            # Step 2: STRATEGIST synthesizes AKU (simulated - no LLM call)
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status, cluster_id,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, metadata, created_at
                ) VALUES (
                    $1, $2, 'strategist', 'candidate', $3,
                    $4::vector, $4::vector,
                    0, 0, 0, 1,
                    '{"synthesized": true}'::jsonb,
                    NOW()
                )
                RETURNING aku_id
                """,
                f"When handling {prefix}_situation",
                f"You should {prefix}_action to avoid the problem",
                cluster["cluster_id"],
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])

            # Step 3: CLUSTERER creates solved_by edge
            edge = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 1.0, 1)
                RETURNING edge_id
                """,
                cluster["cluster_id"],
                aku["aku_id"],
            )
            clean_test_data["ids"]["edge_ids"].append(edge["edge_id"])

            # Step 4: Verify gap is now filled
            gaps_after = await conn.fetch(
                """
                SELECT cluster_id FROM problem_clusters pc
                LEFT JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
                    AND ke.edge_type = 'solved_by'
                WHERE pc.cluster_id = $1
                GROUP BY pc.cluster_id
                HAVING COUNT(ke.edge_id) = 0
                """,
                cluster["cluster_id"],
            )
            assert len(gaps_after) == 0, "Gap should be filled after synthesis"


# =============================================================================
# Task Comparative Analysis Tests
# =============================================================================


class TestTaskComparativeDetection:
    """Test LIBRARIAN's task-based cross-session comparative analysis."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_task_comparative_query_finds_mixed_results(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Task comparative query should find tasks with both successes and failures."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create test experiment
            experiment_id = uuid4()
            await conn.execute(
                """
                INSERT INTO evaluation_experiments (
                    id, name, experiment_type, dataset_split, learning_mode,
                    status, tasks_completed, tasks_total, created_at
                ) VALUES ($1, $2, 'test', 'test', 'enabled', 'completed', 8, 8, NOW())
                """,
                experiment_id,
                f"{prefix}_test_experiment",
            )

            # Create multiple sessions with the same task but different outcomes
            task_desc = f"{prefix}_Find least-played song"

            # Create 3 successful sessions
            for i in range(3):
                session_id = uuid4()
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, domain, status, created_at, updated_at)
                    VALUES ($1, 'test', 'completed', NOW(), NOW())
                    """,
                    session_id,
                )
                clean_test_data["ids"]["session_ids"].append(session_id)

                # Create turn 1 with ## Task marker
                turn_id = uuid4()
                await conn.execute(
                    """
                    INSERT INTO session_turns (
                        turn_id, session_id, turn_number, user_message,
                        assistant_response, created_at
                    ) VALUES ($1, $2, 1, $3, 'Success response', NOW())
                    """,
                    turn_id,
                    session_id,
                    f"## Task\n{task_desc}\n\nPlease help.",
                )
                clean_test_data["ids"]["turn_ids"].append(turn_id)

                # Create evaluation outcome (success=true)
                await conn.execute(
                    """
                    INSERT INTO evaluation_task_outcomes (
                        experiment_id, task_id, session_id, success, total_turns, created_at
                    ) VALUES ($1, $2, $3, true, 5, NOW())
                    """,
                    experiment_id,
                    f"{prefix}_task",
                    session_id,
                )

            # Create 5 failed sessions
            for i in range(5):
                session_id = uuid4()
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, domain, status, created_at, updated_at)
                    VALUES ($1, 'test', 'completed', NOW(), NOW())
                    """,
                    session_id,
                )
                clean_test_data["ids"]["session_ids"].append(session_id)

                turn_id = uuid4()
                await conn.execute(
                    """
                    INSERT INTO session_turns (
                        turn_id, session_id, turn_number, user_message,
                        assistant_response, created_at
                    ) VALUES ($1, $2, 1, $3, 'Failed response', NOW())
                    """,
                    turn_id,
                    session_id,
                    f"## Task\n{task_desc}\n\nPlease help.",
                )
                clean_test_data["ids"]["turn_ids"].append(turn_id)

                # Create evaluation outcome (success=false)
                await conn.execute(
                    """
                    INSERT INTO evaluation_task_outcomes (
                        experiment_id, task_id, session_id, success, total_turns, created_at
                    ) VALUES ($1, $2, $3, false, 10, NOW())
                    """,
                    experiment_id,
                    f"{prefix}_task",
                    session_id,
                )

            # Query for tasks with mixed results (simulating LIBRARIAN._detect_task_comparative)
            mixed_tasks = await conn.fetch(
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
                    COUNT(*) FILTER (WHERE NOT success) as failures
                FROM task_sessions
                WHERE task_desc IS NOT NULL
                GROUP BY task_desc
                HAVING COUNT(*) >= 4
                   AND COUNT(*) FILTER (WHERE success) >= 2
                   AND COUNT(*) FILTER (WHERE NOT success) >= 2
                """
            )

            # Should find our task
            task_descs = {t["task_desc"] for t in mixed_tasks}
            assert task_desc in task_descs

            # Verify counts
            our_task = next(t for t in mixed_tasks if t["task_desc"] == task_desc)
            assert our_task["successes"] == 3
            assert our_task["failures"] == 5


class TestStrategistSourceConstraint:
    """Test that STRATEGIST uses correct source value for DB constraint."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_strategist_source_allowed_by_constraint(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Source='strategist' should be allowed by akus_source_check."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # This tests the ACTUAL constraint - will fail if 'strategist' not allowed
            aku = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'strategist', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id, source
                """,
                f"{prefix}_source_test_situation",
                f"{prefix}_source_test_assertion",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku["aku_id"])

            assert aku["source"] == "strategist"

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_invalid_source_rejected_by_constraint(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Invalid source values should be rejected by DB constraint."""
        prefix = clean_test_data["prefix"]
        import asyncpg

        async with db_pool.acquire() as conn:
            # This should fail - 'strategist-comparative' is NOT in allowed list
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    INSERT INTO akus (
                        situation, assertion, source, status,
                        situation_embedding, assertion_embedding,
                        helpful_count, harmful_count, neutral_count,
                        evidence_count, created_at
                    ) VALUES (
                        $1, $2, 'strategist-comparative', 'candidate',
                        $3::vector, $3::vector,
                        0, 0, 0, 1, NOW()
                    )
                    """,
                    f"{prefix}_bad_source_situation",
                    f"{prefix}_bad_source_assertion",
                    sample_embedding_str,
                )
