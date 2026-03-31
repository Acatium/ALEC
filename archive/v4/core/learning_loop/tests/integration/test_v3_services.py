"""Integration tests for v4 services with real PostgreSQL.

Tests actual service behavior using real database operations,
not mocks. Validates that SQL queries execute correctly against
the v4 schema.

v4 Schema Changes (Dec 2025):
- playbook_bullets renamed to akus
- 14 fields: situation, assertion, embeddings, counters, status, source, cluster_id
- Removed: modality, polarity, category, domain, content, updated_at, last_validated_at
- Edge target_type: 'aku' (was 'solution')

Run: pytest -v -m db_integration core/learning_loop/tests/integration/test_v3_services.py
"""


import pytest

# =============================================================================
# CURATOR Service Tests - Deduplication
# =============================================================================

class TestCuratorDedup:
    """Test CURATOR assertion_embedding deduplication."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_dedup_finds_similar_assertion(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Similar assertions should be detected as duplicates."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create first AKU
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
                RETURNING aku_id
                """,
                f"{prefix}_situation_1",
                f"{prefix}_assertion_1",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

            # Query for duplicate using same embedding (similarity = 1.0)
            dedup_result = await conn.fetchrow(
                """
                SELECT aku_id FROM akus
                WHERE 1 - (assertion_embedding <=> $1::vector) > $2
                  AND status IN ('candidate', 'active')
                ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
                LIMIT 1
                """,
                sample_embedding_str,
                0.70,  # DEDUP_THRESHOLD
            )

            assert dedup_result is not None
            assert dedup_result["aku_id"] == row["aku_id"]

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_evidence_increment_on_dedup(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Evidence count should increment when duplicate detected."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU with evidence_count=1
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
                RETURNING aku_id, evidence_count
                """,
                f"{prefix}_situation_2",
                f"{prefix}_assertion_2",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])
            aku_id = row["aku_id"]

            # Increment evidence (simulating CURATOR._increment_evidence)
            await conn.execute(
                """
                UPDATE akus
                SET evidence_count = evidence_count + 1
                WHERE aku_id = $1
                """,
                aku_id,
            )

            # Verify increment
            updated = await conn.fetchrow(
                "SELECT evidence_count FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["evidence_count"] == 2


# =============================================================================
# REFLECTOR Service Tests - Counter Updates and Edges
# =============================================================================

class TestReflectorAttribution:
    """Test REFLECTOR counter updates and caused_failure edges."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_helpful_counter_increment(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Helpful count should increment correctly."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU
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
                RETURNING aku_id
                """,
                f"{prefix}_situation_3",
                f"{prefix}_assertion_3",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])
            aku_id = row["aku_id"]

            # Increment helpful_count (simulating REFLECTOR._update_counter)
            await conn.execute(
                """
                UPDATE akus
                SET helpful_count = helpful_count + 1
                WHERE aku_id = $1
                """,
                aku_id,
            )

            # Verify increment
            updated = await conn.fetchrow(
                "SELECT helpful_count FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["helpful_count"] == 1

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_harmful_counter_increment(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """Harmful count should increment correctly."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU
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
                RETURNING aku_id
                """,
                f"{prefix}_situation_4",
                f"{prefix}_assertion_4",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])
            aku_id = row["aku_id"]

            # Increment harmful_count
            await conn.execute(
                """
                UPDATE akus
                SET harmful_count = harmful_count + 1
                WHERE aku_id = $1
                """,
                aku_id,
            )

            # Verify increment
            updated = await conn.fetchrow(
                "SELECT harmful_count FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["harmful_count"] == 1

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_caused_failure_edge_creation(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """caused_failure edge should be created correctly."""
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
                    0, 1, NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_1",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Create AKU
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
                    0, 1, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_5",
                f"{prefix}_assertion_5",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Create caused_failure edge (simulating REFLECTOR._upsert_edge)
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (source_id, source_type, target_id, target_type, edge_type, weight, evidence_count)
                VALUES ($1, 'cluster', $2, 'aku', 'caused_failure', 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1,
                    weight = 1.0 - (1.0 / (knowledge_edges.evidence_count + 2)),
                    updated_at = NOW()
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])

            # Verify edge
            edge = await conn.fetchrow(
                """
                SELECT source_id, source_type, target_id, target_type, edge_type, evidence_count
                FROM knowledge_edges WHERE edge_id = $1
                """,
                edge_row["edge_id"],
            )
            assert edge["source_id"] == cluster_id
            assert edge["target_id"] == aku_id
            assert edge["edge_type"] == "caused_failure"
            assert edge["evidence_count"] == 1


# =============================================================================
# CLUSTERER Service Tests - solved_by Edges
# =============================================================================

class TestClustererEdges:
    """Test CLUSTERER solved_by edge creation."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_solved_by_edge_creation(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """solved_by edge should be created for new AKUs."""
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
                f"{prefix}_cluster_2",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Create AKU
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
                    1, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_6",
                f"{prefix}_assertion_6",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Create solved_by edge (simulating CLUSTERER._upsert_edge)
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (source_id, source_type, target_id, target_type, edge_type, weight, evidence_count)
                VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1,
                    weight = 1.0 - (1.0 / (knowledge_edges.evidence_count + 2)),
                    updated_at = NOW()
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])

            # Verify edge
            edge = await conn.fetchrow(
                """
                SELECT source_id, target_id, edge_type
                FROM knowledge_edges WHERE edge_id = $1
                """,
                edge_row["edge_id"],
            )
            assert edge["edge_type"] == "solved_by"

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_aku_promotion_candidate_to_active(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """AKU should promote from candidate to active after 3 helpful counts."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU with helpful_count=3
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
                    3, 0, 0, 1, NOW()
                )
                RETURNING aku_id, status
                """,
                f"{prefix}_situation_7",
                f"{prefix}_assertion_7",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Try to promote (simulating CLUSTERER._maybe_promote_aku)
            await conn.execute(
                """
                UPDATE akus
                SET status = 'active'
                WHERE aku_id = $1
                  AND status = 'candidate'
                  AND helpful_count >= $2
                """,
                aku_id,
                3,  # PROMOTE_HELPFUL_COUNT
            )

            # Verify promotion
            updated = await conn.fetchrow(
                "SELECT status FROM akus WHERE aku_id = $1",
                aku_id,
            )
            assert updated["status"] == "active"


# =============================================================================
# ADVISOR Service Tests - Retrieval and Filtering
# =============================================================================

class TestAdvisorFiltering:
    """Test ADVISOR AKU retrieval and caused_failure exclusion."""

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_retrieval_by_situation_embedding(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """AKUs should be retrieved by situation_embedding similarity."""
        prefix = clean_test_data["prefix"]

        async with db_pool.acquire() as conn:
            # Create AKU
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
                    5, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_8",
                f"{prefix}_assertion_8",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])

            # Query with same embedding (simulating ADVISOR._vector_search)
            results = await conn.fetch(
                """
                SELECT
                    aku_id, situation, assertion,
                    helpful_count, harmful_count, neutral_count,
                    1 - (situation_embedding <=> $1::vector) as similarity
                FROM akus
                WHERE status IN ('candidate', 'active')
                  AND 1 - (situation_embedding <=> $1::vector) > $2
                ORDER BY similarity DESC
                LIMIT 50
                """,
                sample_embedding_str,
                0.50,  # VECTOR_THRESHOLD
            )

            assert len(results) >= 1
            # Find our test AKU
            test_aku = next(
                (r for r in results if r["aku_id"] == aku_row["aku_id"]),
                None
            )
            assert test_aku is not None
            assert test_aku["similarity"] > 0.99  # Same embedding = ~1.0 similarity

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_caused_failure_exclusion(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """AKUs with caused_failure edges should be excluded for that cluster."""
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
                    0, 5, NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_3",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Create harmful AKU
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
                    0, 5, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_9",
                f"{prefix}_assertion_9",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Create caused_failure edge
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (source_id, source_type, target_id, target_type, edge_type, weight, evidence_count)
                VALUES ($1, 'cluster', $2, 'aku', 'caused_failure', 1.0, 3)
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])

            # Query for harmful AKUs (simulating ADVISOR._get_harmful_for_cluster)
            harmful = await conn.fetch(
                """
                SELECT target_id FROM knowledge_edges
                WHERE source_id = $1 AND edge_type = 'caused_failure'
                """,
                cluster_id,
            )

            harmful_ids = {r["target_id"] for r in harmful}
            assert aku_id in harmful_ids

    @pytest.mark.db_integration
    @pytest.mark.asyncio
    async def test_cluster_solutions_via_solved_by(
        self, db_pool, clean_test_data, sample_embedding_str
    ):
        """AKUs linked via solved_by should be retrieved for cluster."""
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
                    5, 0, NOW(), NOW()
                )
                RETURNING cluster_id
                """,
                sample_embedding_str,
                f"{prefix}_cluster_4",
            )
            clean_test_data["ids"]["cluster_ids"].append(cluster_row["cluster_id"])
            cluster_id = cluster_row["cluster_id"]

            # Create AKU
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
                    5, 0, 0, 1, NOW()
                )
                RETURNING aku_id
                """,
                f"{prefix}_situation_10",
                f"{prefix}_assertion_10",
                sample_embedding_str,
            )
            clean_test_data["ids"]["aku_ids"].append(aku_row["aku_id"])
            aku_id = aku_row["aku_id"]

            # Create solved_by edge
            edge_row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edges (source_id, source_type, target_id, target_type, edge_type, weight, evidence_count)
                VALUES ($1, 'cluster', $2, 'aku', 'solved_by', 0.9, 5)
                RETURNING edge_id
                """,
                cluster_id,
                aku_id,
            )
            clean_test_data["ids"]["edge_ids"].append(edge_row["edge_id"])

            # Query for cluster solutions (simulating ADVISOR._get_cluster_solutions)
            solutions = await conn.fetch(
                """
                SELECT
                    a.aku_id, a.situation, a.assertion,
                    a.helpful_count, a.harmful_count,
                    ke.weight as edge_weight
                FROM akus a
                JOIN knowledge_edges ke ON ke.target_id = a.aku_id
                WHERE ke.source_id = $1
                  AND ke.edge_type = 'solved_by'
                  AND a.status = 'active'
                """,
                cluster_id,
            )

            assert len(solutions) == 1
            assert solutions[0]["aku_id"] == aku_id
            assert solutions[0]["edge_weight"] == 0.9
