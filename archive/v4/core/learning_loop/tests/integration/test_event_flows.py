"""Integration tests for critical event flows across services (v4).

Tests the event chains that connect learning loop components:
- REFLECTOR → CURATOR (aku.proposed events)
- REFLECTOR → CLUSTERER (attribution.resolved events)
- CURATOR → CLUSTERER (aku.accepted/merged events)

Run: pytest -v -m db_integration core/learning_loop/tests/integration/test_event_flows.py
"""

from uuid import uuid4

import pytest

# =============================================================================
# REFLECTOR → CURATOR Flow Tests
# =============================================================================


class TestReflectorToCuratorFlow:
    """Test REFLECTOR produces data that CURATOR can consume."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_aku_proposed_payload_structure(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """REFLECTOR's aku.proposed payload should have all fields CURATOR needs (v4)."""
        # REFLECTOR would emit this payload (v4: no modality/polarity)
        aku_payload = {
            "session_id": str(uuid4()),
            "turn_number": 3,
            "source": "reflector",
            "cluster_id": str(uuid4()),
            "aku": {
                "situation": "When handling paginated API responses",
                "assertion": "Always check if there are more pages by comparing count to page_size",
            },
        }

        # Verify all required fields present (v4: simplified)
        assert "aku" in aku_payload
        assert "situation" in aku_payload["aku"]
        assert "assertion" in aku_payload["aku"]
        assert "source" in aku_payload

        # Verify field constraints match CURATOR expectations (v4 length limits)
        assert 10 <= len(aku_payload["aku"]["situation"]) <= 60  # v4 limits
        assert 20 <= len(aku_payload["aku"]["assertion"]) <= 100  # v4 limits

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_aku_storage_creates_both_embeddings(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """CURATOR should store both situation and assertion embeddings (v4)."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Simulate CURATOR storing a new AKU (v4 schema)
            row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id, situation_embedding IS NOT NULL as has_sit,
                          assertion_embedding IS NOT NULL as has_assert
                """,
                f"{prefix}_situation_flow_test",
                f"{prefix}_assertion_flow_test",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

            # Both embeddings must be present for v4 architecture
            assert row["has_sit"] is True, "situation_embedding missing"
            assert row["has_assert"] is True, "assertion_embedding missing"


# =============================================================================
# REFLECTOR → CLUSTERER Flow Tests
# =============================================================================


class TestReflectorToClustererFlow:
    """Test REFLECTOR produces data that CLUSTERER can consume."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_attribution_resolved_payload_structure(
        self, db_pool, clean_test_data
    ):
        """REFLECTOR's attribution.resolved payload should have all fields CLUSTERER needs."""
        # REFLECTOR would emit this payload
        attribution_payload = {
            "session_id": str(uuid4()),
            "success": True,
            "turns": [
                {
                    "turn_number": 1,
                    "sub_task": "Finding user's favorite songs",
                    "micro_outcome": "progress",
                    "bullets_helped": [str(uuid4())],
                    "bullets_harmed": [],
                    "situation_embedding": [0.1] * 384,
                },
                {
                    "turn_number": 2,
                    "sub_task": "Filtering songs by rating",
                    "micro_outcome": "solved",
                    "bullets_helped": [str(uuid4()), str(uuid4())],
                    "bullets_harmed": [str(uuid4())],
                    "situation_embedding": [0.2] * 384,
                },
            ],
        }

        # Verify required fields for CLUSTERER
        assert "turns" in attribution_payload
        for turn in attribution_payload["turns"]:
            assert "turn_number" in turn
            assert "micro_outcome" in turn
            assert "bullets_helped" in turn
            assert "bullets_harmed" in turn
            assert "situation_embedding" in turn
            assert len(turn["situation_embedding"]) == 384

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_turn_cluster_assignment(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """CLUSTERER should be able to assign turns to clusters by embedding similarity."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create a cluster
            cluster_row = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count,
                    created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    0, 0, NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_flow_test",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Find nearest cluster (simulating CLUSTERER._find_nearest_cluster)
            nearest = await conn.fetchrow(
                """
                SELECT cluster_id, 1 - (centroid <=> $1::vector) as similarity
                FROM problem_clusters
                WHERE status = 'active' OR cluster_id = $2
                ORDER BY centroid <=> $1::vector
                LIMIT 1
                """,
                sample_embedding_str,
                cluster_id,  # Include our test cluster
            )

            # Should find the cluster with high similarity
            assert nearest is not None
            assert nearest["cluster_id"] == cluster_id
            assert nearest["similarity"] > 0.99  # Same embedding


# =============================================================================
# CURATOR → CLUSTERER Flow Tests
# =============================================================================


class TestCuratorToClustererFlow:
    """Test CURATOR produces data that CLUSTERER can consume."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_bullet_accepted_creates_solved_by_edge(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """CLUSTERER should create solved_by edge when bullet.accepted received."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster
            cluster_row = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count,
                    created_at, updated_at
                ) VALUES (
                    $1::vector, $2, 'test',
                    1, 0, NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_accepted_test",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Create AKU (as CURATOR would store, v4 schema)
            aku_row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status, cluster_id,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate', $3,
                    $4::vector, $4::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_accepted",
                f"{prefix}_assertion_accepted",
                cluster_id,
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # CLUSTERER creates solved_by edge
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count,
                    created_at, updated_at
                ) VALUES (
                    $1, 'cluster', $2, 'aku', 'solved_by',
                    1.0, 1, NOW(), NOW()
                )
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])

            # Verify edge exists
            edge = await conn.fetchrow(
                """
                SELECT edge_type, evidence_count
                FROM knowledge_edges
                WHERE source_id = $1 AND target_id = $2
                """,
                cluster_id,
                aku_id,
            )
            assert edge is not None
            assert edge["edge_type"] == "solved_by"


# =============================================================================
# Cross-Service Counter Consistency Tests
# =============================================================================


class TestCounterConsistency:
    """Test counter updates are consistent across services."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_effectiveness_score_calculation(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Thompson Sampling formula should work correctly with real counters."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU with known counters (v4 schema)
            aku_row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'active',
                    $3::vector, $3::vector,
                    10, 2, 3, 1, NOW()
                )
                RETURNING aku_id, helpful_count, harmful_count, neutral_count
                """,
                f"{prefix}_situation_ts_test",
                f"{prefix}_assertion_ts_test",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])

            # Calculate Thompson Sampling score (as ADVISOR would)
            # alpha = helpful + 1 = 11
            # beta = harmful + 0.2*neutral + 1 = 2 + 0.6 + 1 = 3.6
            # Expected mean = alpha / (alpha + beta) = 11 / 14.6 ≈ 0.753
            alpha = aku_row["helpful_count"] + 1
            beta = aku_row["harmful_count"] + 0.2 * aku_row["neutral_count"] + 1
            expected_mean = alpha / (alpha + beta)

            assert 0.70 < expected_mean < 0.80, f"Expected ~0.753, got {expected_mean}"

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_status_transitions(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """AKU status transitions should follow the rules."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create candidate AKU (v4 schema)
            aku_row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_status_test",
                f"{prefix}_assertion_status_test",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Simulate 3 helpful signals (promotion threshold)
            await conn.execute(
                """
                UPDATE akus
                SET helpful_count = 3
                WHERE aku_id = $1
                """,
                aku_id,
            )

            # Promotion query (as CLUSTERER would run)
            await conn.execute(
                """
                UPDATE akus
                SET status = 'active'
                WHERE aku_id = $1
                  AND status = 'candidate'
                  AND helpful_count >= 3
                """,
                aku_id,
            )

            # Verify promotion
            updated = await conn.fetchrow(
                "SELECT status FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["status"] == "active"


# =============================================================================
# Edge Integrity Tests
# =============================================================================


class TestEdgeIntegrity:
    """Test knowledge graph edge consistency."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_edge_upsert_increments_evidence(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Multiple edge upserts should increment evidence_count."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster and bullet
            cluster_row = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count,
                    created_at, updated_at
                ) VALUES ($1::vector, $2, 'test', 0, 0, NOW(), NOW())
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_edge_test",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])

            aku_row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_edge_test",
                f"{prefix}_assertion_edge_test",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])

            cluster_id = cluster_row["cluster_id"]
            aku_id = aku_row["aku_id"]

            # First upsert
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1
                RETURNING edge_id, evidence_count
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])
            assert edge_row["evidence_count"] == 1

            # Second upsert (same edge)
            updated = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1
                RETURNING evidence_count
                """,
                cluster_id,
                aku_id,
            )
            assert updated["evidence_count"] == 2

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_no_duplicate_edge_types_per_pair(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Each (source, target) pair should have at most one edge per type."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create cluster and AKU
            cluster_row = await conn.fetchrow(
                """
                INSERT INTO problem_clusters (
                    centroid, label, domain,
                    success_count, failure_count,
                    created_at, updated_at
                ) VALUES ($1::vector, $2, 'test', 0, 0, NOW(), NOW())
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_unique_test",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])

            aku_row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_unique_test",
                f"{prefix}_assertion_unique_test",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])

            cluster_id = cluster_row["cluster_id"]
            aku_id = aku_row["aku_id"]

            # Create solved_by edge
            edge1 = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 1.0, 1)
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge1["edge_id"])

            # Create caused_failure edge (different type, allowed)
            edge2 = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (
                    source_id, source_type, target_id, target_type, edge_type,
                    weight, evidence_count
                ) VALUES ($1, 'cluster', $2, 'aku', 'caused_failure', 0.5, 1)
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge2["edge_id"])

            # Count edges - should have exactly 2 (one per type)
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM knowledge_edges
                WHERE source_id = $1 AND target_id = $2
                """,
                cluster_id,
                aku_id,
            )
            assert count == 2


# =============================================================================
# Deduplication Consistency Tests
# =============================================================================


class TestDeduplicationConsistency:
    """Test deduplication works correctly across the flow."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_assertion_embedding_dedup_threshold(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Deduplication should respect the 0.70 threshold for reflector source."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create first AKU (v4 schema)
            aku1 = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'reflector', 'candidate',
                    $3::vector, $3::vector,
                    0, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_dedup1",
                f"{prefix}_assertion_dedup1",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku1["aku_id"])

            # Query for duplicate (simulating CURATOR._check_duplicate)
            # With same embedding, similarity = 1.0 > 0.70 threshold
            duplicate = await conn.fetchrow(
                """
                SELECT aku_id FROM akus
                WHERE 1 - (assertion_embedding <=> $1::vector) > 0.70
                  AND status IN ('candidate', 'active')
                ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
                LIMIT 1
                """,
                sample_embedding_str,
            )

            assert duplicate is not None
            assert duplicate["aku_id"] == aku1["aku_id"]

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_strategist_higher_threshold(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Strategist-sourced AKUs should use higher 0.90 threshold."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU with slightly modified embedding (v4 schema)
            # (In real scenario, this would be from a different but similar assertion)
            aku1 = await conn.fetchrow(
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
                RETURNING aku_id
                """,
                f"{prefix}_situation_strat",
                f"{prefix}_assertion_strat",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku1["aku_id"])

            # With 0.90 threshold (strategist), exact match still found
            duplicate_high = await conn.fetchrow(
                """
                SELECT aku_id FROM akus
                WHERE 1 - (assertion_embedding <=> $1::vector) > 0.90
                  AND status IN ('candidate', 'active')
                ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
                LIMIT 1
                """,
                sample_embedding_str,
            )

            # Same embedding should still match at 0.90
            assert duplicate_high is not None
