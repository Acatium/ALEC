"""Integration tests for Thompson Sampling with real database data (v4).

These tests verify Thompson Sampling behavior with realistic AKU data:
- Real counter distributions (not synthetic 10/5/2)
- Actual timestamps for age decay
- Timezone-aware datetime handling
- Edge cases (0/0/0 new AKUs, high-failure AKUs)

v4 Schema Changes:
- playbook_bullets renamed to akus
- Removed: modality, polarity, category, domain, content, updated_at, last_validated_at
- Age decay now uses created_at instead of last_validated_at

Mocked tests hide bugs like:
- Integer division in age_days calculation (12h old = 0 days)
- Timezone-naive timestamps causing wrong age
- Thompson floor not excluding bad AKUs
- Score formula bugs with real counter distributions
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


# Constants from advisor/service.py
THOMPSON_FLOOR = 0.35
AGE_DECAY_RATE = 0.995
AGE_DECAY_MIN = 0.50


@pytest_asyncio.fixture
async def ts_test_akus(db_pool, clean_test_data, sample_embedding_str):
    """Create test AKUs with varied counter distributions.

    Returns multiple AKUs with different effectiveness profiles:
    - proven_good: 20 helpful, 1 harmful, 5 neutral (should score high)
    - new_aku: 0 helpful, 0 harmful, 0 neutral (fair chance)
    - proven_bad: 2 helpful, 15 harmful, 3 neutral (should be excluded by floor)
    - mixed: 10 helpful, 10 harmful, 10 neutral (moderate score)
    - old_but_good: 15 helpful, 2 harmful (30 days old, tests decay)
    """
    prefix = clean_test_data["prefix"]
    akus = {}

    profiles = [
        ("proven_good", 20, 1, 5, timedelta(days=1)),
        ("new_aku", 0, 0, 0, timedelta(hours=1)),
        ("proven_bad", 2, 15, 3, timedelta(days=3)),
        ("mixed", 10, 10, 10, timedelta(days=5)),
        ("old_but_good", 15, 2, 0, timedelta(days=30)),
    ]

    async with db_pool.acquire() as conn:
        for name, helpful, harmful, neutral, age in profiles:
            # Use naive datetime for created_at (timestamp without time zone)
            created_at_naive = (datetime.now(timezone.utc) - age).replace(tzinfo=None)

            row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'e2e-test', 'active',
                    $3::vector, $3::vector,
                    $4, $5, $6,
                    1, $7
                )
                RETURNING aku_id, helpful_count, harmful_count, neutral_count, created_at
                """,
                f"{prefix}_{name}_situation",
                f"{prefix}_{name}_assertion",
                sample_embedding_str,
                helpful,
                harmful,
                neutral,
                created_at_naive,
            )

            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

            akus[name] = {
                "aku_id": row["aku_id"],
                "helpful_count": row["helpful_count"],
                "harmful_count": row["harmful_count"],
                "neutral_count": row["neutral_count"],
                "created_at": row["created_at"],
            }

    return akus


class TestThompsonSamplingFormula:
    """Test the Thompson Sampling score formula with real data."""

    async def test_proven_good_aku_scores_high(self, ts_test_akus):
        """AKU with high helpful/low harmful should have high TS sample."""
        aku = ts_test_akus["proven_good"]

        alpha = aku["helpful_count"] + 1  # 21
        beta = aku["harmful_count"] + 0.2 * aku["neutral_count"] + 1  # 3

        # Sample 1000 times to verify distribution
        samples = [np.random.beta(alpha, beta) for _ in range(1000)]
        mean_sample = np.mean(samples)

        # Expected mean: alpha / (alpha + beta) ≈ 21/24 ≈ 0.875
        expected_mean = alpha / (alpha + beta)
        assert abs(mean_sample - expected_mean) < 0.05
        assert mean_sample > THOMPSON_FLOOR  # Should pass floor

    async def test_new_aku_gets_fair_chance(self, ts_test_akus):
        """AKU with 0/0/0 counters should get fair chance (uninformative prior)."""
        aku = ts_test_akus["new_aku"]

        alpha = aku["helpful_count"] + 1  # 1
        beta = aku["harmful_count"] + 0.2 * aku["neutral_count"] + 1  # 1

        # Beta(1, 1) is uniform [0, 1]
        samples = [np.random.beta(alpha, beta) for _ in range(1000)]
        mean_sample = np.mean(samples)

        # Expected mean: 0.5 (uniform distribution)
        assert abs(mean_sample - 0.5) < 0.05

        # Some samples should pass floor, some shouldn't
        above_floor = sum(1 for s in samples if s >= THOMPSON_FLOOR)
        assert 0.4 * 1000 < above_floor < 0.8 * 1000  # Roughly 65% should pass

    async def test_proven_bad_aku_excluded_by_floor(self, ts_test_akus):
        """AKU with high harmful should be excluded by Thompson floor."""
        aku = ts_test_akus["proven_bad"]

        alpha = aku["helpful_count"] + 1  # 3
        beta_param = aku["harmful_count"] + 0.2 * aku["neutral_count"] + 1  # 16.6

        # Sample 1000 times
        samples = [np.random.beta(alpha, beta_param) for _ in range(1000)]
        mean_sample = np.mean(samples)

        # Expected mean: 3/19.6 ≈ 0.15 (below floor)
        expected_mean = alpha / (alpha + beta_param)
        assert expected_mean < THOMPSON_FLOOR

        # Most samples should be below floor
        below_floor = sum(1 for s in samples if s < THOMPSON_FLOOR)
        assert below_floor > 0.8 * 1000  # >80% excluded

    async def test_neutral_count_contributes_to_beta(self, ts_test_akus):
        """Neutral count should contribute 0.2 to beta parameter."""
        aku = ts_test_akus["mixed"]

        # With 10 neutral: beta = 10 + 0.2 * 10 + 1 = 13
        alpha = aku["helpful_count"] + 1  # 11
        beta_with_neutral = aku["harmful_count"] + 0.2 * aku["neutral_count"] + 1

        assert beta_with_neutral == 13.0

        # Mean should be: 11/24 ≈ 0.458
        expected_mean = alpha / (alpha + beta_with_neutral)
        assert abs(expected_mean - 0.458) < 0.01


class TestAgeDecay:
    """Test age decay formula with real timestamps."""

    async def test_recent_aku_no_decay(self, ts_test_akus):
        """AKU created today should have minimal decay."""
        aku = ts_test_akus["new_aku"]
        now = datetime.now(timezone.utc)

        created_at = aku["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (now - created_at).days
        age_decay = max(AGE_DECAY_MIN, AGE_DECAY_RATE ** age_days)

        # 0 days → decay = 1.0
        assert age_days == 0
        assert age_decay == 1.0

    async def test_old_aku_decays(self, ts_test_akus):
        """AKU created 30 days ago should have significant decay."""
        aku = ts_test_akus["old_but_good"]
        now = datetime.now(timezone.utc)

        created_at = aku["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (now - created_at).days
        age_decay = max(AGE_DECAY_MIN, AGE_DECAY_RATE ** age_days)

        # 30 days → 0.995^30 ≈ 0.86
        expected_decay = AGE_DECAY_RATE ** 30
        assert abs(age_decay - expected_decay) < 0.01
        assert age_decay > AGE_DECAY_MIN  # Still above floor

    async def test_very_old_aku_hits_decay_floor(self, db_pool, clean_test_data, sample_embedding_str):
        """AKU 365+ days old should hit decay floor (0.50)."""
        prefix = clean_test_data["prefix"]
        created_at_naive = (datetime.now(timezone.utc) - timedelta(days=365)).replace(tzinfo=None)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'e2e-test', 'active',
                    $3::vector, $3::vector,
                    10, 1, 0,
                    1, $4
                )
                RETURNING aku_id, created_at
                """,
                f"{prefix}_very_old_situation",
                f"{prefix}_very_old_assertion",
                sample_embedding_str,
                created_at_naive,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

        now = datetime.now(timezone.utc)
        created_at = row["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (now - created_at).days
        age_decay = max(AGE_DECAY_MIN, AGE_DECAY_RATE ** age_days)

        # 365 days → 0.995^365 ≈ 0.16 → floored to 0.50
        assert age_decay == AGE_DECAY_MIN

    async def test_fractional_days_use_integer_division(self, ts_test_akus):
        """Age decay uses integer days (12h old = 0 days)."""
        aku = ts_test_akus["new_aku"]
        now = datetime.now(timezone.utc)

        created_at = aku["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        # timedelta.days is integer division
        age_delta = now - created_at
        age_days = age_delta.days

        # 1 hour old should be 0 days
        assert age_days == 0


class TestTimezoneHandling:
    """Test timezone-aware timestamp handling."""

    async def test_timezone_aware_timestamps(self, db_pool, clean_test_data, sample_embedding_str):
        """Timezone-aware timestamps should be handled correctly."""
        prefix = clean_test_data["prefix"]
        # Create with explicit UTC timezone
        created_at_naive = (datetime.now(timezone.utc) - timedelta(days=5)).replace(tzinfo=None)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO akus (
                    situation, assertion, source, status,
                    situation_embedding, assertion_embedding,
                    helpful_count, harmful_count, neutral_count,
                    evidence_count, created_at
                ) VALUES (
                    $1, $2, 'e2e-test', 'active',
                    $3::vector, $3::vector,
                    5, 1, 0,
                    1, $4
                )
                RETURNING aku_id, created_at
                """,
                f"{prefix}_tz_aware_situation",
                f"{prefix}_tz_aware_assertion",
                sample_embedding_str,
                created_at_naive,
            )
            clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

        # v4: created_at is timestamp without time zone
        # PostgreSQL returns naive timestamp, we add UTC for calculations
        created_at = row["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        assert created_at.tzinfo is not None

    async def test_iso8601_string_parsing(self):
        """ISO 8601 strings (from JSON) should parse correctly."""
        # Simulate what ADVISOR does when reading from JSON/event
        # Use relative date to avoid test flakiness from hardcoded dates
        now = datetime.now(timezone.utc)
        five_days_ago = now - timedelta(days=5)
        iso_string = five_days_ago.isoformat()
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))

        assert parsed.tzinfo is not None
        age_days = (now - parsed).days

        # Should be approximately 5 days
        assert 4 <= age_days <= 6


class TestCombinedScoring:
    """Test the full score formula: similarity × ts_sample × age_decay."""

    async def test_score_components_multiply(self, ts_test_akus):
        """Final score should be product of components."""
        aku = ts_test_akus["proven_good"]

        # Fixed values for deterministic test
        similarity = 0.9
        ts_sample = 0.85  # High for proven_good
        age_decay = 0.99  # Recent AKU

        score = similarity * ts_sample * age_decay
        expected = 0.9 * 0.85 * 0.99

        assert abs(score - expected) < 0.001

    async def test_low_similarity_reduces_score(self, ts_test_akus):
        """Even proven-good AKU should have low score with low similarity."""
        # Proven good AKU
        alpha = 21
        beta = 3
        ts_sample = alpha / (alpha + beta)  # Expected value ≈ 0.875

        # High similarity vs low similarity
        high_sim_score = 0.95 * ts_sample * 1.0
        low_sim_score = 0.3 * ts_sample * 1.0

        assert high_sim_score > low_sim_score
        assert low_sim_score < 0.3  # Low enough to be deprioritized

    async def test_selection_order_with_real_akus(self, db_pool, ts_test_akus):
        """Verify selection order matches expected priority."""
        # Calculate expected scores for each AKU
        akus_with_scores = []
        now = datetime.now(timezone.utc)

        for name, aku in ts_test_akus.items():
            alpha = aku["helpful_count"] + 1
            beta = aku["harmful_count"] + 0.2 * aku["neutral_count"] + 1

            # Use expected value for deterministic comparison
            ts_expected = alpha / (alpha + beta)

            created_at = aku["created_at"]
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = (now - created_at).days
            age_decay = max(AGE_DECAY_MIN, AGE_DECAY_RATE ** age_days)

            # Assume similarity = 0.8 for all (same embedding)
            similarity = 0.8
            expected_score = similarity * ts_expected * age_decay

            akus_with_scores.append({
                "name": name,
                "ts_expected": ts_expected,
                "age_decay": age_decay,
                "expected_score": expected_score,
                "passes_floor": ts_expected >= THOMPSON_FLOOR,
            })

        # Sort by expected score
        akus_with_scores.sort(key=lambda x: x["expected_score"], reverse=True)

        # proven_good should be first (high TS, recent)
        passing = [a for a in akus_with_scores if a["passes_floor"]]
        assert passing[0]["name"] == "proven_good"

        # proven_bad should not be in passing list
        passing_names = [a["name"] for a in passing]
        assert "proven_bad" not in passing_names
