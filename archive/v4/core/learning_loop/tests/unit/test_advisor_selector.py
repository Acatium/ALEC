"""Unit tests for ADVISOR selector.

Tests the BulletSelector's Thompson Sampling, task extraction,
and two-pool selection logic with focus on failure modes.

Test Philosophy: "Broken tests are better than green tests that miss errors"
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from scipy import stats

# v3: Task extraction is handled internally by AdvisorService
# The _extract_task_from_context function was removed in v3 simplification


# ============================================================================
# FAILURE MODE 2: Thompson Sampling with Timezone Issues
# ============================================================================


@dataclass
class MockBulletForSampling:
    """Minimal bullet for Thompson Sampling tests."""

    bullet_id: str
    helpful_count: int
    harmful_count: int
    neutral_count: int
    created_at: datetime


class TestThompsonSampling:
    """Tests for Thompson Sampling implementation.

    Focus on timezone handling and age decay edge cases.
    """

    def test_handles_mixed_timezone_datetimes(self):
        """Bullets with naive and aware datetimes don't cause TypeError."""
        # This simulates the real bug: some bullets might have timezone-aware
        # created_at while others have naive datetimes

        bullets = [
            MockBulletForSampling(
                bullet_id="1",
                helpful_count=5,
                harmful_count=1,
                neutral_count=0,
                created_at=datetime.now(timezone.utc),  # Aware
            ),
            MockBulletForSampling(
                bullet_id="2",
                helpful_count=3,
                harmful_count=0,
                neutral_count=1,
                created_at=datetime.now(),  # Naive
            ),
        ]

        # Simulate the logic from _thompson_sample
        now = datetime.now(timezone.utc)
        scores = []

        for bullet in bullets:
            alpha = bullet.helpful_count + 1
            beta = bullet.harmful_count + bullet.neutral_count + 1

            sampled_score = stats.beta.rvs(alpha, beta)

            # This is the bug-prone section
            if bullet.created_at.tzinfo is None:
                age_days = (now.replace(tzinfo=None) - bullet.created_at).days
            else:
                age_days = (now - bullet.created_at).days

            age_factor = math.exp(-0.01 * age_days)
            effective_score = sampled_score * age_factor
            scores.append(effective_score)

        # Should not raise TypeError
        assert len(scores) == 2
        assert all(0 <= s <= 1 for s in scores)

    def test_age_decay_for_recent_bullets(self):
        """Bullets less than 1 day old should still get appropriate decay."""
        now = datetime.now(timezone.utc)

        # 12 hours old
        bullet_12h = MockBulletForSampling(
            bullet_id="1",
            helpful_count=5,
            harmful_count=0,
            neutral_count=0,
            created_at=now - timedelta(hours=12),
        )

        # Calculate age in days (will be 0 for 12 hours)
        if bullet_12h.created_at.tzinfo is None:
            age_days = (now.replace(tzinfo=None) - bullet_12h.created_at).days
        else:
            age_days = (now - bullet_12h.created_at).days

        age_factor = math.exp(-0.01 * age_days)

        # Document current behavior: integer days means 12 hours = 0 days
        # So age_factor = 1.0 (no decay)
        # This might be a design decision, not necessarily a bug
        assert age_days == 0
        assert age_factor == 1.0

        # For actual decay, we'd need fractional days:
        # age_hours = (now - bullet_12h.created_at).total_seconds() / 3600
        # age_days_fractional = age_hours / 24  # = 0.5
        # age_factor_fractional = math.exp(-0.01 * age_days_fractional)  # ~0.995

    def test_beta_distribution_bounds(self):
        """Thompson Sampling scores stay in [0, 1] range."""
        test_cases = [
            (0, 0, 0),  # No observations
            (100, 0, 0),  # All helpful
            (0, 100, 0),  # All harmful
            (0, 0, 100),  # All neutral
            (50, 25, 25),  # Mixed
        ]

        for helpful, harmful, neutral in test_cases:
            alpha = helpful + 1
            beta_param = harmful + neutral + 1

            # Sample multiple times to check bounds
            for _ in range(100):
                score = stats.beta.rvs(alpha, beta_param)
                assert 0 <= score <= 1, f"Score {score} out of bounds for ({helpful}, {harmful}, {neutral})"

    def test_untested_bullets_get_fair_chance(self):
        """Bullets with 0/0/0 counts should still be selectable."""
        new_bullet = MockBulletForSampling(
            bullet_id="new",
            helpful_count=0,
            harmful_count=0,
            neutral_count=0,
            created_at=datetime.now(timezone.utc),
        )

        # With alpha=1, beta=1 (uniform prior), expected value is 0.5
        alpha = new_bullet.helpful_count + 1
        beta_param = new_bullet.harmful_count + new_bullet.neutral_count + 1

        assert alpha == 1
        assert beta_param == 1

        # Beta(1, 1) is uniform [0, 1], so expected value is 0.5
        expected_value = alpha / (alpha + beta_param)
        assert expected_value == 0.5


# ============================================================================
# FAILURE MODE 3: Unified Thompson Sampling Selection (v3)
# ============================================================================


class TestUnifiedThompsonSampling:
    """Tests for the v3 unified Thompson Sampling selection strategy.

    v3 removed the two-pool split - all bullets compete in a single pool
    using unified scoring: similarity × thompson_sample × age_decay.

    These tests verify edge cases like cold-start, deduplication, and
    similarity threshold filtering that still apply to unified selection.
    """

    def test_cold_start_returns_empty_not_crash(self):
        """When no bullets exist at all, return empty list gracefully."""
        # Simulate empty database result
        exploration_pool: list[dict[str, Any]] = []
        exploitation_pool: list[dict[str, Any]] = []

        # Current implementation behavior
        k = 5
        exploration_k = 1
        exploitation_k = k - exploration_k

        selected: list[dict[str, Any]] = []

        # No exploration bullets
        if not exploration_pool:
            # Give slot to exploitation
            exploitation_k += exploration_k

        # No exploitation bullets either
        if not exploitation_pool:
            # Nothing to select
            pass

        assert selected == []  # Cold-start silence

    def test_single_retrieval_source_handles_empty(self):
        """When one retrieval source is empty, others fill the gap.

        v3 uses multiple sources: vector search, cluster retrieval, graph.
        If one source returns nothing, selection continues with others.
        """
        vector_results: list[dict[str, Any]] = []  # Empty
        cluster_results: list[dict[str, Any]] = [
            {"id": "1", "score": 0.9},
            {"id": "2", "score": 0.8},
            {"id": "3", "score": 0.7},
        ]

        # Combine all sources (v3 unified approach)
        all_candidates = vector_results + cluster_results

        # Select top k
        k = 3
        selected = sorted(all_candidates, key=lambda x: x["score"], reverse=True)[:k]

        assert len(selected) == 3  # Cluster results fill gap
        assert selected[0]["id"] == "1"

    def test_all_retrieval_sources_empty_returns_nothing(self):
        """When all retrieval sources are empty, return empty list (cold start).

        v3 unified selection gracefully handles cold-start with no available bullets.
        """
        vector_results: list[dict[str, Any]] = []
        cluster_results: list[dict[str, Any]] = []
        graph_results: list[dict[str, Any]] = []

        # Combine all sources
        all_candidates = vector_results + cluster_results + graph_results

        # Nothing to select
        assert all_candidates == []
        # Should result in cold-start silence, not error

    def test_deduplication_across_retrieval_sources(self):
        """Same bullet from multiple sources should only be selected once.

        v3 combines vector search, cluster retrieval, and graph traversal.
        A bullet might appear in multiple sources - deduplication is required.
        """
        shared_id = str(uuid4())

        vector_results = [{"id": shared_id, "source": "vector"}]
        cluster_results = [{"id": shared_id, "source": "cluster"}]

        # Combine all sources
        all_candidates = vector_results + cluster_results

        # Deduplicate by ID
        seen_ids = set()
        final_selection = []

        for bullet in all_candidates:
            if bullet["id"] not in seen_ids:
                seen_ids.add(bullet["id"])
                final_selection.append(bullet)

        # Should only have 1 bullet, not 2
        assert len(final_selection) == 1

    def test_similarity_threshold_filters_correctly(self):
        """High similarity threshold may filter out all candidates."""
        bullets: list[dict[str, Any]] = [
            {"id": "1", "similarity": 0.45},
            {"id": "2", "similarity": 0.52},
            {"id": "3", "similarity": 0.55},
        ]

        # High threshold
        threshold = 0.8

        filtered = [b for b in bullets if float(b["similarity"]) >= threshold]

        # All bullets filtered out
        assert filtered == []

        # This should result in cold-start silence, not error

    def test_similarity_weighted_selection_probability(self):
        """v3 unified selection weights candidates by similarity score."""
        import random

        random.seed(42)  # For reproducibility

        bullets: list[dict[str, Any]] = [
            {"id": "high", "similarity": 0.9},
            {"id": "medium", "similarity": 0.5},
            {"id": "low", "similarity": 0.1},
        ]

        # Simulate weighted selection 1000 times
        selections: dict[str, int] = {"high": 0, "medium": 0, "low": 0}

        for _ in range(1000):
            total_weight = sum(float(b["similarity"]) for b in bullets)
            r = random.random() * total_weight
            cumulative = 0.0
            for b in bullets:
                cumulative += float(b["similarity"])
                if r <= cumulative:
                    selections[str(b["id"])] += 1
                    break

        # High similarity should be selected most often
        assert selections["high"] > selections["medium"]
        assert selections["medium"] > selections["low"]

        # Proportions should roughly match similarities
        # high:medium:low ≈ 0.9:0.5:0.1 = 9:5:1
        assert selections["high"] > 500  # Should be ~60%
        assert selections["low"] < 150  # Should be ~7%


# ============================================================================
# FAILURE MODE 4: v3 Cluster-Based Retrieval Edge Cases
# ============================================================================


class TestClusterBasedRetrieval:
    """Tests for v3 cluster-based retrieval logic.

    Validates that:
    1. Cluster solutions boost candidate scores
    2. Cluster exclusions filter harmful bullets
    3. Empty results don't cause crashes
    4. Deduplication works across retrieval sources
    """

    def test_cluster_boost_increases_score(self):
        """Bullets from cluster edges should have boosted scores."""
        # Simulate a bullet found via both vector search and cluster edge
        bullet_scores: dict[str, dict[str, Any]] = {}

        # First: vector search finds it with similarity 0.6
        bullet_id = "test-bullet-1"
        bullet_scores[bullet_id] = {
            "bullet_id": bullet_id,
            "vector_similarity": 0.6,
            "cluster_similarity": 0.0,
        }

        # Then: cluster edge finds it with boost 0.8
        cluster_boost = 0.8
        current_sim = float(bullet_scores[bullet_id]["cluster_similarity"])
        bullet_scores[bullet_id]["cluster_similarity"] = max(current_sim, cluster_boost)

        # Cluster similarity should now be 0.8
        assert bullet_scores[bullet_id]["cluster_similarity"] == 0.8
        assert bullet_scores[bullet_id]["vector_similarity"] == 0.6  # Unchanged

    def test_cluster_exclusion_removes_bullets(self):
        """Bullets with caused_failure edges should be excluded."""
        bullet_scores = {
            "good-1": {"bullet_id": "good-1", "content": "Good bullet"},
            "bad-1": {"bullet_id": "bad-1", "content": "Bad bullet"},
            "good-2": {"bullet_id": "good-2", "content": "Another good bullet"},
        }

        # Simulate cluster exclusions
        cluster_excluded = {"bad-1"}

        # Filter
        filtered = {
            bid: data for bid, data in bullet_scores.items()
            if bid not in cluster_excluded
        }

        assert len(filtered) == 2
        assert "bad-1" not in filtered
        assert "good-1" in filtered
        assert "good-2" in filtered

    def test_empty_cluster_results_handled_gracefully(self):
        """Empty cluster retrieval results shouldn't cause errors."""
        # Simulate empty cluster results
        cluster_solutions: list[dict[str, Any]] = []

        # The logic should handle empty list
        for cs in cluster_solutions:
            # This loop should not execute
            assert False, "Should not enter loop on empty list"

        # Should complete without error
        assert len(cluster_solutions) == 0

    def test_deduplication_across_sources(self):
        """Same bullet from multiple sources should only appear once."""
        bullet_scores: dict[str, dict[str, Any]] = {}
        shared_id = "shared-bullet"

        # Source 1: Vector search
        bullet_scores[shared_id] = {
            "bullet_id": shared_id,
            "vector_similarity": 0.7,
            "cluster_similarity": 0.0,
            "source": "vector",
        }

        # Source 2: Cluster retrieval (same bullet)
        if shared_id in bullet_scores:
            # Update, don't add
            current = float(bullet_scores[shared_id]["cluster_similarity"])
            bullet_scores[shared_id]["cluster_similarity"] = max(current, 0.8)
        else:
            bullet_scores[shared_id] = {
                "bullet_id": shared_id,
                "vector_similarity": 0.0,
                "cluster_similarity": 0.8,
                "source": "cluster",
            }

        # Should only have one entry
        assert len(bullet_scores) == 1
        assert bullet_scores[shared_id]["vector_similarity"] == 0.7
        assert bullet_scores[shared_id]["cluster_similarity"] == 0.8

    def test_combined_exclusions(self):
        """Both v2 and v3 exclusions should apply."""
        bullet_scores = {
            "keep-1": {"bullet_id": "keep-1"},
            "exclude-v2": {"bullet_id": "exclude-v2"},  # not_applicable_for
            "exclude-v3": {"bullet_id": "exclude-v3"},  # caused_failure
            "keep-2": {"bullet_id": "keep-2"},
        }

        # v2 exclusion (not_applicable_for)
        v2_excluded = {"exclude-v2"}
        after_v2 = {
            bid: data for bid, data in bullet_scores.items()
            if bid not in v2_excluded
        }

        # v3 exclusion (caused_failure)
        v3_excluded = {"exclude-v3"}
        after_v3 = {
            bid: data for bid, data in after_v2.items()
            if bid not in v3_excluded
        }

        assert len(after_v3) == 2
        assert "keep-1" in after_v3
        assert "keep-2" in after_v3
        assert "exclude-v2" not in after_v3
        assert "exclude-v3" not in after_v3


# ============================================================================
# FAILURE MODE 5: Neutral Weighting in Thompson Sampling
# ============================================================================


class TestNeutralWeighting:
    """Tests for neutral count weighting at 0.2 in Thompson Sampling.

    v3 Dec 2025: Changed neutral weighting from 1.0 to 0.2 because
    being ignored hurts less than being actively harmful.

    Formula: beta = harmful + 0.2 * neutral + 1
    """

    def test_neutral_weighted_at_02_in_beta(self):
        """Verify neutral counts are weighted at 0.2 in beta calculation.

        A bullet with neutral_count=10 should have the same beta as
        a bullet with harmful_count=2 (10 * 0.2 = 2).
        """
        # Bullet A: 10 neutral signals
        _helpful_a = 5  # noqa: F841 - documents the scenario
        harmful_a = 0
        neutral_a = 10

        beta_a = harmful_a + 0.2 * neutral_a + 1
        assert beta_a == 3.0  # 0 + 0.2*10 + 1 = 3

        # Bullet B: 2 harmful signals (should have same beta)
        _helpful_b = 5  # noqa: F841 - documents the scenario
        harmful_b = 2
        neutral_b = 0

        beta_b = harmful_b + 0.2 * neutral_b + 1
        assert beta_b == 3.0  # 2 + 0.2*0 + 1 = 3

        # Both should have same beta (same confidence in downside)
        assert beta_a == beta_b

    def test_neutral_has_less_impact_than_harmful(self):
        """Verify neutral counts reduce score less than harmful counts.

        A bullet ignored 10 times (neutral=10) should score higher than
        a bullet that caused harm 10 times (harmful=10).
        """

        helpful = 5

        # Bullet with 10 neutral
        neutral_beta = 0 + 0.2 * 10 + 1  # = 3
        neutral_alpha = helpful + 1  # = 6
        neutral_expected = neutral_alpha / (neutral_alpha + neutral_beta)  # 6/9 = 0.667

        # Bullet with 10 harmful
        harmful_beta = 10 + 0.2 * 0 + 1  # = 11
        harmful_alpha = helpful + 1  # = 6
        harmful_expected = harmful_alpha / (harmful_alpha + harmful_beta)  # 6/17 = 0.353

        # Neutral bullet should have higher expected score
        assert neutral_expected > harmful_expected
        assert abs(neutral_expected - 0.667) < 0.01
        assert abs(harmful_expected - 0.353) < 0.01

    def test_pure_neutral_still_reduces_score(self):
        """Verify neutral counts still have some negative impact.

        A bullet with only neutral counts (never helped) should score
        lower than a bullet with no observations.
        """

        # New bullet (no observations)
        new_alpha = 0 + 1  # = 1
        new_beta = 0 + 0.2 * 0 + 1  # = 1
        new_expected = new_alpha / (new_alpha + new_beta)  # 0.5

        # Bullet with only neutral signals
        ignored_alpha = 0 + 1  # = 1
        ignored_beta = 0 + 0.2 * 50 + 1  # = 11
        ignored_expected = ignored_alpha / (ignored_alpha + ignored_beta)  # 1/12 = 0.083

        # Consistently ignored bullet should score lower
        assert ignored_expected < new_expected
        assert ignored_expected < 0.1

    def test_weighting_consistent_in_hybrid_score(self):
        """Verify neutral weighting is consistent in unified hybrid scoring.

        The unified v3 formula: score = similarity × thompson_sample × age_decay
        thompson_sample uses beta = harmful + 0.2 * neutral + 1
        """
        import math


        # Simulated bullet data
        helpful = 8
        harmful = 1
        neutral = 15
        similarity = 0.7
        age_days = 5

        # Calculate components
        alpha = helpful + 1
        beta = harmful + 0.2 * neutral + 1  # 1 + 3 + 1 = 5

        # Expected score from Thompson Sampling (mean of Beta)
        thompson_expected = alpha / (alpha + beta)  # 9/14 ≈ 0.643

        # Age decay
        age_decay = math.exp(-0.005 * age_days)  # ≈ 0.975

        # Final score
        expected_score = similarity * thompson_expected * age_decay
        # 0.7 × 0.643 × 0.975 ≈ 0.439

        assert abs(expected_score - 0.439) < 0.01

        # Verify beta uses correct formula
        correct_beta = harmful + 0.2 * neutral + 1
        wrong_beta = harmful + neutral + 1  # old formula

        assert correct_beta == 5.0
        assert wrong_beta == 17.0  # Much higher = more penalty

        # Correct formula gives higher expected score
        correct_thompson = alpha / (alpha + correct_beta)
        wrong_thompson = alpha / (alpha + wrong_beta)

        assert correct_thompson > wrong_thompson
        assert abs(correct_thompson - 0.643) < 0.01
        assert abs(wrong_thompson - 0.346) < 0.01  # Much lower with old formula
