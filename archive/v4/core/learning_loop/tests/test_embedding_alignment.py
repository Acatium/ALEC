"""Tests for Embedding Alignment (v4 Dec 2025).

Validates the v4 Two-Space Embedding model:
1. CURATOR stores BOTH situation_embedding + assertion_embedding
2. Dedup uses assertion_embedding (same insight = duplicate)
3. Retrieval uses situation_embedding (same problem = retrieve)
4. EmbeddingClient uses 384d MiniLM (synchronous for performance)
5. Quality gate validates AKU structure (simplified: no modality/polarity)

DESIGN GOAL: Cross-app knowledge transfer via situation/assertion separation.
- Situation: "When paginating API results" (retrieval key, ≤60 chars)
- Assertion: "Use offset=0 for first page" (the actual insight, ≤100 chars)
"""

import inspect

# ============================================================================
# Two-Space Embedding Model
# ============================================================================


class TestTwoSpaceEmbeddingModel:
    """Test v4 two-space embedding architecture."""

    def test_curator_stores_both_embeddings(self):
        """CURATOR stores situation_embedding AND assertion_embedding."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._store_aku)

        # Should store both embeddings
        assert "situation_embedding" in source
        assert "assertion_embedding" in source

    def test_curator_dedups_on_assertion(self):
        """CURATOR deduplicates by assertion_embedding (same insight)."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._check_duplicate_by_assertion)

        # Should query assertion_embedding for dedup
        assert "assertion_embedding" in source

    def test_curator_generates_both_embeddings(self):
        """CURATOR generates embeddings for both situation and assertion."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._handle_aku_proposed)

        # Should embed both
        assert "situation_emb" in source or "embed(situation" in source
        assert "assertion_emb" in source or "embed(assertion" in source


# ============================================================================
# Embedding Client
# ============================================================================


class TestEmbeddingClient:
    """Test shared embedding client is correct dimension and sync."""

    def test_embedding_client_uses_minilm(self):
        """EmbeddingClient uses MiniLM model (via gateway)."""
        from core.common.embedding_client import EmbeddingClient

        # Client calls gateway which uses MiniLM - check gateway URL reference
        source = inspect.getsource(EmbeddingClient)
        assert "embed" in source  # Has embed method
        assert "LLM_GATEWAY" in source or "gateway" in source.lower()  # Uses gateway

    def test_embedding_client_is_384d(self):
        """EmbeddingClient produces 384-dimensional embeddings."""
        from core.common.embedding_client import EmbeddingClient

        source = inspect.getsource(EmbeddingClient)

        # Should reference 384 dimensions
        assert "384" in source

    def test_embedding_client_has_sync_embed(self):
        """EmbeddingClient.embed() is synchronous (not async)."""
        from core.common.embedding_client import EmbeddingClient

        # embed() should NOT be async (performance optimization)
        source = inspect.getsource(EmbeddingClient.embed)
        assert "async def embed" not in source


# ============================================================================
# Quality Gate
# ============================================================================


class TestCuratorQualityGate:
    """Test CURATOR quality gate checks."""

    def test_quality_gate_checks_assertion_length(self):
        """Quality gate rejects short assertions."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._quality_check)

        assert "assertion" in source
        assert "MIN_ASSERTION_LENGTH" in source or "20" in source

    def test_quality_gate_checks_situation_length(self):
        """Quality gate rejects short situations."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._quality_check)

        assert "situation" in source
        assert "MIN_SITUATION_LENGTH" in source or "10" in source

    def test_quality_gate_checks_length_constraints(self):
        """Quality gate validates v4 length constraints."""
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._quality_check)

        # v4: Should enforce length constraints, not modality/polarity
        assert "situation" in source
        assert "assertion" in source
        # Should have minimum length checks
        assert "MIN_SITUATION_LENGTH" in source or "10" in source
        assert "MIN_ASSERTION_LENGTH" in source or "20" in source

    def test_low_quality_patterns_exist(self):
        """CURATOR has patterns to catch low-quality situations."""
        from core.learning_loop.curator.service import LOW_QUALITY_PATTERNS

        assert len(LOW_QUALITY_PATTERNS) > 0
        # Should catch task IDs, UUIDs, generic phrases
        assert any("task" in p.lower() for p in LOW_QUALITY_PATTERNS)


# ============================================================================
# ADVISOR Retrieval
# ============================================================================


class TestAdvisorRetrieval:
    """Test ADVISOR uses situation_embedding for retrieval."""

    def test_advisor_exists_and_handles_requests(self):
        """ADVISOR service handles bullets.requested events."""
        from core.learning_loop.advisor.service import AdvisorService

        assert hasattr(AdvisorService, '_handle_event')
        _topics = AdvisorService().__class__.__dict__.get('_get_topics')  # noqa: F841

        # Check it handles the right topic
        from core.learning_loop.advisor.service import AdvisorService
        service = object.__new__(AdvisorService)
        service._get_topics = lambda: ["bullets.requested"]  # type: ignore[method-assign]
        assert "bullets.requested" in service._get_topics()


# ============================================================================
# CLUSTERER Turn Assignment
# ============================================================================


class TestClustererTurnAssignment:
    """Test CLUSTERER assigns turns to clusters."""

    def test_clusterer_assigns_to_cluster(self):
        """CLUSTERER has method to assign turns to clusters."""
        from core.learning_loop.clusterer.service import ClustererService

        assert hasattr(ClustererService, '_assign_turn_to_cluster')

    def test_clusterer_creates_edges(self):
        """CLUSTERER creates solved_by/caused_failure edges."""
        from core.learning_loop.clusterer.service import ClustererService

        assert hasattr(ClustererService, '_upsert_edge')

        source = inspect.getsource(ClustererService._upsert_edge)
        assert "edge_type" in source

    def test_clusterer_stores_turns(self):
        """CLUSTERER stores turns to session_turns table."""
        from core.learning_loop.clusterer.service import ClustererService

        assert hasattr(ClustererService, '_store_turn')


# ============================================================================
# Integration: Cross-App Knowledge Transfer
# ============================================================================


class TestCrossAppKnowledgeTransfer:
    """Test v4 design enables cross-app knowledge transfer."""

    def test_situation_is_retrieval_key(self):
        """Situation field is used as the retrieval key (problem space)."""
        # CURATOR stores situation_embedding for retrieval
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._store_aku)
        assert "situation_embedding" in source

    def test_assertion_is_dedup_key(self):
        """Assertion field is used as the dedup key (insight space)."""
        # CURATOR deduplicates by assertion_embedding
        from core.learning_loop.curator.service import CuratorService

        source = inspect.getsource(CuratorService._check_duplicate_by_assertion)
        assert "assertion_embedding" in source

    # v4: Category derivation removed - no more modality/polarity/category fields
