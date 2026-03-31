"""Unit tests for REFLECTOR service (v3).

Tests the REFLECTOR's turn analysis, outcome determination, and AKU extraction.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.learning_loop.reflector.service import ReflectorService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def reflector_service():
    """Create ReflectorService instance with mocked BaseService dependencies."""
    with patch.object(ReflectorService, "__init__", lambda self: None):
        service = ReflectorService()
        service.service_name = "reflector"
        service._buffers = {}
        service._buffer_timestamps = {}
        service.logger = MagicMock()
        yield service


# ============================================================================
# Test: Determine Outcome
# ============================================================================


class TestDetermineOutcome:
    """Tests for _determine_outcome method."""

    def test_helped_when_in_bullets_helped(self, reflector_service):
        """Bullet in bullets_helped list returns 'helped'."""
        turn = {
            "bullets_shown": ["bullet-1", "bullet-2"],
            "bullets_helped": ["bullet-1"],
            "bullets_harmed": [],
        }
        result = reflector_service._determine_outcome("bullet-1", turn)
        assert result == "helped"

    def test_harmed_when_in_bullets_harmed_on_error_turn(self, reflector_service):
        """Bullet in bullets_harmed list returns 'harmed' only on error turns.

        Policy: Harm attribution is only trusted on 'error' turns because they
        have clear causal signals. 'stuck' and 'progress' turns are too ambiguous.
        """
        turn = {
            "micro_outcome": "error",  # Required for harm attribution
            "bullets_shown": ["bullet-1", "bullet-2"],
            "bullets_helped": [],
            "bullets_harmed": ["bullet-2"],
        }
        result = reflector_service._determine_outcome("bullet-2", turn)
        assert result == "harmed"

    def test_harmed_neutral_on_progress_turn(self, reflector_service):
        """Bullet in bullets_harmed returns 'neutral' on progress turns (too ambiguous)."""
        turn = {
            "micro_outcome": "progress",  # Ambiguous, harm not trusted
            "bullets_shown": ["bullet-1", "bullet-2"],
            "bullets_helped": [],
            "bullets_harmed": ["bullet-2"],
        }
        result = reflector_service._determine_outcome("bullet-2", turn)
        assert result == "neutral"

    def test_harmed_neutral_on_stuck_turn(self, reflector_service):
        """Bullet in bullets_harmed returns 'neutral' on stuck turns (too ambiguous).

        Policy change: 'stuck' turns have 1.1:1 help:harm ratio (essentially noise).
        Only 'error' turns have clear causal signal for harm attribution.
        """
        turn = {
            "micro_outcome": "stuck",  # Ambiguous, harm not trusted
            "bullets_shown": ["bullet-1", "bullet-2"],
            "bullets_helped": [],
            "bullets_harmed": ["bullet-2"],
        }
        result = reflector_service._determine_outcome("bullet-2", turn)
        assert result == "neutral"

    def test_neutral_when_not_in_either_list(self, reflector_service):
        """Bullet not in helped or harmed returns 'neutral'."""
        turn = {
            "bullets_shown": ["bullet-1", "bullet-2", "bullet-3"],
            "bullets_helped": ["bullet-1"],
            "bullets_harmed": ["bullet-2"],
        }
        result = reflector_service._determine_outcome("bullet-3", turn)
        assert result == "neutral"

    def test_neutral_when_empty_lists(self, reflector_service):
        """Empty helped/harmed lists returns 'neutral'."""
        turn = {
            "bullets_shown": ["bullet-1"],
            "bullets_helped": [],
            "bullets_harmed": [],
        }
        result = reflector_service._determine_outcome("bullet-1", turn)
        assert result == "neutral"

    def test_neutral_when_lists_missing(self, reflector_service):
        """Missing helped/harmed keys returns 'neutral'."""
        turn = {"bullets_shown": ["bullet-1"]}
        result = reflector_service._determine_outcome("bullet-1", turn)
        assert result == "neutral"


# ============================================================================
# Test: Is Recovery Detection
# ============================================================================


class TestIsRecovery:
    """Tests for _is_recovery method - detects stuck/error → progress/solved."""

    def test_stuck_to_progress_is_recovery(self, reflector_service):
        """stuck → progress transition is detected as recovery."""
        turns = [
            {"micro_outcome": "stuck"},
            {"micro_outcome": "progress"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is True

    def test_stuck_to_solved_is_recovery(self, reflector_service):
        """stuck → solved transition is detected as recovery."""
        turns = [
            {"micro_outcome": "stuck"},
            {"micro_outcome": "solved"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is True

    def test_error_to_progress_is_recovery(self, reflector_service):
        """error → progress transition is detected as recovery."""
        turns = [
            {"micro_outcome": "error"},
            {"micro_outcome": "progress"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is True

    def test_error_to_solved_is_recovery(self, reflector_service):
        """error → solved transition is detected as recovery."""
        turns = [
            {"micro_outcome": "error"},
            {"micro_outcome": "solved"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is True

    def test_progress_to_solved_not_recovery(self, reflector_service):
        """progress → solved is NOT a recovery (no stuck/error)."""
        turns = [
            {"micro_outcome": "progress"},
            {"micro_outcome": "solved"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is False

    def test_stuck_to_stuck_not_recovery(self, reflector_service):
        """stuck → stuck is NOT a recovery."""
        turns = [
            {"micro_outcome": "stuck"},
            {"micro_outcome": "stuck"},
        ]
        result = reflector_service._is_recovery(turns[1], turns, 1)
        assert result is False

    def test_first_turn_never_recovery(self, reflector_service):
        """First turn (index 0) can never be a recovery."""
        turns = [{"micro_outcome": "solved"}]
        result = reflector_service._is_recovery(turns[0], turns, 0)
        assert result is False

    def test_recovery_in_longer_sequence(self, reflector_service):
        """Recovery detected correctly in longer turn sequence."""
        turns = [
            {"micro_outcome": "progress"},  # 0
            {"micro_outcome": "stuck"},     # 1
            {"micro_outcome": "error"},     # 2
            {"micro_outcome": "progress"},  # 3 - recovery from error
            {"micro_outcome": "solved"},    # 4
        ]
        # Only index 3 should be a recovery
        assert reflector_service._is_recovery(turns[0], turns, 0) is False
        assert reflector_service._is_recovery(turns[1], turns, 1) is False
        assert reflector_service._is_recovery(turns[2], turns, 2) is False  # stuck→error not recovery
        assert reflector_service._is_recovery(turns[3], turns, 3) is True   # error→progress IS recovery
        assert reflector_service._is_recovery(turns[4], turns, 4) is False  # progress→solved not recovery


# ============================================================================
# Test: Validate AKU
# ============================================================================


class TestValidateAKU:
    """Tests for _validate_aku method (v4: no modality/polarity)."""

    def test_valid_aku_passes(self, reflector_service):
        """Valid AKU with all required fields passes."""
        aku = {
            "situation": "When paginating through API results",
            "assertion": "Always check if the response has a next_page field before continuing",
        }
        result = reflector_service._validate_aku(aku)
        assert result is True

    def test_short_situation_fails(self, reflector_service):
        """Situation < 10 chars fails validation."""
        aku = {
            "situation": "Short",
            "assertion": "This is a valid assertion with enough content",
        }
        result = reflector_service._validate_aku(aku)
        assert result is False

    def test_short_assertion_fails(self, reflector_service):
        """Assertion < 20 chars fails validation."""
        aku = {
            "situation": "When using the API pagination",
            "assertion": "Check page",
        }
        result = reflector_service._validate_aku(aku)
        assert result is False

    def test_missing_fields_fail(self, reflector_service):
        """Missing required fields fail validation."""
        # Missing situation
        assert reflector_service._validate_aku({
            "assertion": "Valid assertion content here",
        }) is False

        # Missing assertion
        assert reflector_service._validate_aku({
            "situation": "Valid situation here",
        }) is False


# ============================================================================
# Test: Buffer Management
# ============================================================================


class TestBufferManagement:
    """Tests for turn buffer management."""

    def test_cleanup_removes_old_buffers(self, reflector_service):
        """Old buffers beyond TTL are cleaned up."""
        # Set up buffers with old timestamps
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        reflector_service._buffers = {
            "old-session": [{"turn": 1}],
            "recent-session": [{"turn": 1}],
        }
        reflector_service._buffer_timestamps = {
            "old-session": old_time,
            "recent-session": recent_time,
        }

        # Mock BUFFER_TTL_SECONDS to 1 hour
        with patch("core.learning_loop.reflector.service.BUFFER_TTL_SECONDS", 3600):
            reflector_service._cleanup_old_buffers()

        # Old session should be removed
        assert "old-session" not in reflector_service._buffers
        assert "old-session" not in reflector_service._buffer_timestamps

        # Recent session should remain
        assert "recent-session" in reflector_service._buffers
        assert "recent-session" in reflector_service._buffer_timestamps

    def test_empty_buffers_cleanup_is_safe(self, reflector_service):
        """Cleanup with no buffers doesn't crash."""
        reflector_service._buffers = {}
        reflector_service._buffer_timestamps = {}

        # Should not raise
        reflector_service._cleanup_old_buffers()

        assert reflector_service._buffers == {}


# ============================================================================
# Test: Outcome Reconciliation
# ============================================================================


class TestOutcomeReconciliation:
    """Tests for outcome reconciliation logic.

    When session succeeded but LLM marked no turns as 'solved',
    force the final turn to 'solved' to capture external success signal.
    """

    def test_reconciles_when_success_no_solved_turns(self, reflector_service):
        """Session success + no 'solved' turns → last turn forced to 'solved'."""
        resolved_turns = [
            {"micro_outcome": "progress", "bullets_shown": ["b1"]},
            {"micro_outcome": "progress", "bullets_shown": ["b2"]},
            {"micro_outcome": "progress", "bullets_shown": ["b3"]},
        ]
        session_success = True

        reflector_service._reconcile_outcomes(resolved_turns, session_success)

        # Last turn should be forced to 'solved'
        assert resolved_turns[-1]["micro_outcome"] == "solved"
        # Other turns unchanged
        assert resolved_turns[0]["micro_outcome"] == "progress"
        assert resolved_turns[1]["micro_outcome"] == "progress"

    def test_no_reconciliation_when_already_has_solved(self, reflector_service):
        """Session success + has 'solved' turn → no change."""
        resolved_turns = [
            {"micro_outcome": "progress", "bullets_shown": ["b1"]},
            {"micro_outcome": "solved", "bullets_shown": ["b2"]},
            {"micro_outcome": "progress", "bullets_shown": ["b3"]},
        ]
        session_success = True

        reflector_service._reconcile_outcomes(resolved_turns, session_success)

        # No changes - already has a solved turn
        assert resolved_turns[0]["micro_outcome"] == "progress"
        assert resolved_turns[1]["micro_outcome"] == "solved"
        assert resolved_turns[2]["micro_outcome"] == "progress"

    def test_no_reconciliation_on_failed_session(self, reflector_service):
        """Session failed → no reconciliation regardless of outcomes."""
        resolved_turns = [
            {"micro_outcome": "progress", "bullets_shown": ["b1"]},
            {"micro_outcome": "stuck", "bullets_shown": ["b2"]},
            {"micro_outcome": "error", "bullets_shown": ["b3"]},
        ]
        session_success = False

        reflector_service._reconcile_outcomes(resolved_turns, session_success)

        # No changes - session failed
        assert resolved_turns[0]["micro_outcome"] == "progress"
        assert resolved_turns[1]["micro_outcome"] == "stuck"
        assert resolved_turns[2]["micro_outcome"] == "error"

    def test_no_reconciliation_on_empty_turns(self, reflector_service):
        """Empty turns list → no crash, no reconciliation."""
        resolved_turns = []
        session_success = True

        # Should not raise
        reflector_service._reconcile_outcomes(resolved_turns, session_success)

        assert resolved_turns == []
