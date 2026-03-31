"""Statistical scoring methods for bullet effectiveness.

Provides multiple approaches for ranking bullets based on their
observed effectiveness (helpful/neutral/harmful counts).
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np


class ScoringMethod(str, Enum):
    """Available scoring methods."""
    THOMPSON = "thompson"  # Thompson Sampling with Beta distribution
    WILSON = "wilson"  # Wilson Score lower bound
    UCB = "ucb"  # Upper Confidence Bound
    EWMA = "ewma"  # Exponential Weighted Moving Average
    ENSEMBLE = "ensemble"  # Combination of methods


@dataclass
class BulletStats:
    """Statistics for a single bullet."""
    bullet_id: str
    helpful_count: int
    neutral_count: int
    harmful_count: int
    observations: Optional[List[Tuple[str, float]]] = None  # (assessment, timestamp)

    @property
    def total_count(self) -> int:
        return self.helpful_count + self.neutral_count + self.harmful_count

    @property
    def positive_count(self) -> int:
        """Helpful + half of neutral (neutral is slightly positive)."""
        return self.helpful_count + self.neutral_count // 2

    @property
    def negative_count(self) -> int:
        """Harmful + half of neutral."""
        return self.harmful_count + (self.neutral_count - self.neutral_count // 2)


class BulletScorer:
    """Multi-method bullet scoring system."""

    def __init__(
        self,
        method: ScoringMethod = ScoringMethod.WILSON,
        ucb_c: float = 2.0,
        ewma_alpha: float = 0.3,
        decay_half_life_days: float = 7.0,
        wilson_z: float = 1.96,  # 95% confidence
    ):
        """Initialize scorer with configuration.

        Args:
            method: Primary scoring method to use
            ucb_c: Exploration constant for UCB (higher = more exploration)
            ewma_alpha: Weight for recent observations in EWMA (0-1)
            decay_half_life_days: Half-life for time decay in days
            wilson_z: Z-score for Wilson confidence interval
        """
        self.method = method
        self.ucb_c = ucb_c
        self.ewma_alpha = ewma_alpha
        self.decay_half_life_days = decay_half_life_days
        self.wilson_z = wilson_z
        self._global_observations = 0  # For UCB

    def score(self, stats: BulletStats) -> float:
        """Score a bullet using the configured method.

        Args:
            stats: Bullet statistics

        Returns:
            Score between 0 and 1 (higher is better)
        """
        if self.method == ScoringMethod.THOMPSON:
            return self.thompson_sample(stats)
        elif self.method == ScoringMethod.WILSON:
            return self.wilson_score(stats)
        elif self.method == ScoringMethod.UCB:
            return self.ucb_score(stats)
        elif self.method == ScoringMethod.EWMA:
            return self.ewma_score(stats)
        elif self.method == ScoringMethod.ENSEMBLE:
            return self.ensemble_score(stats)
        else:
            return self.wilson_score(stats)  # Default

    def thompson_sample(self, stats: BulletStats) -> float:
        """Thompson Sampling with Beta distribution.

        Classic multi-armed bandit approach. Samples from posterior
        distribution to balance exploration and exploitation.

        Args:
            stats: Bullet statistics

        Returns:
            Sampled score from Beta(helpful+1, harmful+1)
        """
        alpha = stats.helpful_count + 1
        beta = stats.harmful_count + 1
        return np.random.beta(alpha, beta)

    def wilson_score(self, stats: BulletStats) -> float:
        """Wilson Score lower bound of confidence interval.

        Better than raw proportion for ranking with few observations.
        Used by Reddit for comment ranking. Returns lower bound of
        confidence interval, which is conservative.

        Args:
            stats: Bullet statistics

        Returns:
            Lower bound of Wilson score interval
        """
        n = stats.total_count
        if n == 0:
            return 0.5  # Prior: assume neutral

        # Use positive_count which treats neutral as slightly positive
        p = stats.positive_count / n
        z = self.wilson_z

        denominator = 1 + z**2 / n
        center = p + z**2 / (2 * n)
        spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)

        lower_bound = (center - spread) / denominator
        return float(max(0, min(1, lower_bound)))

    def ucb_score(self, stats: BulletStats) -> float:
        """Upper Confidence Bound (UCB1) algorithm.

        More deterministic than Thompson Sampling. Adds exploration
        bonus that decreases as bullet is used more.

        Args:
            stats: Bullet statistics

        Returns:
            Mean + exploration bonus
        """
        n = stats.total_count
        if n == 0:
            return 1.0  # Always try untested bullets

        # Mean effectiveness
        mean = stats.positive_count / n

        # Exploration bonus (decreases with more observations)
        if self._global_observations > 0:
            exploration = self.ucb_c * np.sqrt(
                np.log(self._global_observations) / n
            )
        else:
            exploration = self.ucb_c * np.sqrt(1 / n)

        return float(min(1.0, mean + exploration))

    def ewma_score(self, stats: BulletStats) -> float:
        """Exponential Weighted Moving Average score.

        Weights recent observations more heavily. Good for detecting
        when a bullet's effectiveness changes over time.

        Args:
            stats: Bullet statistics (requires observations list)

        Returns:
            EWMA score between 0 and 1
        """
        if not stats.observations:
            # Fall back to simple average if no observation history
            n = stats.total_count
            if n == 0:
                return 0.5
            return stats.positive_count / n

        # Start with prior
        score = 0.5
        alpha = self.ewma_alpha

        # Process observations in chronological order
        sorted_obs = sorted(stats.observations, key=lambda x: x[1])
        for assessment, _ in sorted_obs:
            if assessment == "helpful":
                value = 1.0
            elif assessment == "harmful":
                value = 0.0
            else:  # neutral
                value = 0.5

            score = alpha * value + (1 - alpha) * score

        return score

    def time_decay_score(self, stats: BulletStats) -> float:
        """Time-decayed effectiveness score.

        Weights recent observations more heavily using exponential
        decay. Old observations become less relevant.

        Args:
            stats: Bullet statistics (requires observations list)

        Returns:
            Weighted average score
        """
        if not stats.observations:
            # Fall back to simple average
            n = stats.total_count
            if n == 0:
                return 0.5
            return stats.positive_count / n

        now = time.time()
        lambda_ = np.log(2) / (self.decay_half_life_days * 86400)

        weights = []
        values = []

        for assessment, timestamp in stats.observations:
            age = now - timestamp
            weight = np.exp(-lambda_ * age)

            if assessment == "helpful":
                value = 1.0
            elif assessment == "harmful":
                value = 0.0
            else:
                value = 0.5

            weights.append(weight)
            values.append(value)

        if sum(weights) == 0:
            return 0.5

        result: float = float(np.average(values, weights=weights))
        return result

    def ensemble_score(self, stats: BulletStats) -> float:
        """Ensemble of multiple scoring methods.

        Combines Wilson (conservative ranking) with Thompson
        (exploration) for balanced scoring.

        Args:
            stats: Bullet statistics

        Returns:
            Weighted average of methods
        """
        wilson = self.wilson_score(stats)
        thompson = self.thompson_sample(stats)

        # Weight Wilson more heavily for stability
        return 0.7 * wilson + 0.3 * thompson

    def set_global_observations(self, count: int) -> None:
        """Set total observation count for UCB calculation.

        Args:
            count: Total observations across all bullets
        """
        self._global_observations = count

    def rank_bullets(
        self,
        bullets: List[BulletStats],
        top_k: Optional[int] = None
    ) -> List[Tuple[str, float]]:
        """Rank bullets by score.

        Args:
            bullets: List of bullet statistics
            top_k: Optional limit on results

        Returns:
            List of (bullet_id, score) tuples, sorted descending
        """
        # Set global observations for UCB
        total_obs = sum(b.total_count for b in bullets)
        self.set_global_observations(total_obs)

        # Score all bullets
        scored = [(b.bullet_id, self.score(b)) for b in bullets]

        # Sort descending by score
        scored.sort(key=lambda x: x[1], reverse=True)

        if top_k:
            return scored[:top_k]
        return scored


# Utility functions for common operations

def wilson_confidence_interval(
    successes: int,
    total: int,
    z: float = 1.96
) -> Tuple[float, float]:
    """Calculate Wilson score confidence interval.

    Args:
        successes: Number of positive outcomes
        total: Total number of trials
        z: Z-score for confidence level (1.96 = 95%)

    Returns:
        (lower_bound, upper_bound) tuple
    """
    if total == 0:
        return (0.0, 1.0)

    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)

    lower = (center - spread) / denominator
    upper = (center + spread) / denominator

    return (max(0, lower), min(1, upper))


def dirichlet_sample(
    helpful: int,
    neutral: int,
    harmful: int
) -> np.ndarray:
    """Sample from Dirichlet distribution for 3-category feedback.

    Returns probability vector that sums to 1.

    Args:
        helpful: Helpful count
        neutral: Neutral count
        harmful: Harmful count

    Returns:
        Array of [p_helpful, p_neutral, p_harmful]
    """
    return np.random.dirichlet([helpful + 1, neutral + 1, harmful + 1])


def prob_a_better_than_b(
    a_helpful: int,
    a_total: int,
    b_helpful: int,
    b_total: int,
    samples: int = 10000
) -> float:
    """Probability that bullet A is better than bullet B.

    Uses Monte Carlo sampling from Beta distributions.

    Args:
        a_helpful: Helpful count for A
        a_total: Total count for A
        b_helpful: Helpful count for B
        b_total: Total count for B
        samples: Number of Monte Carlo samples

    Returns:
        Probability that A > B
    """
    a_samples = np.random.beta(
        a_helpful + 1,
        a_total - a_helpful + 1,
        samples
    )
    b_samples = np.random.beta(
        b_helpful + 1,
        b_total - b_helpful + 1,
        samples
    )
    return float(np.mean(a_samples > b_samples))


def bootstrap_confidence_interval(
    observations: List[str],
    n_bootstrap: int = 1000,
    ci: float = 0.95
) -> Tuple[float, float]:
    """Calculate bootstrap confidence interval for effectiveness.

    Non-parametric method that works with any distribution.

    Args:
        observations: List of "helpful", "neutral", "harmful"
        n_bootstrap: Number of bootstrap samples
        ci: Confidence interval (0.95 = 95%)

    Returns:
        (lower_bound, upper_bound) tuple
    """
    if not observations:
        return (0.0, 1.0)

    # Convert to numeric
    values = np.array([
        1.0 if o == "helpful" else (0.5 if o == "neutral" else 0.0)
        for o in observations
    ])

    # Bootstrap
    means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(values, size=len(values), replace=True)
        means.append(np.mean(sample))

    lower = np.percentile(means, (1 - ci) / 2 * 100)
    upper = np.percentile(means, (1 + ci) / 2 * 100)

    return (lower, upper)
