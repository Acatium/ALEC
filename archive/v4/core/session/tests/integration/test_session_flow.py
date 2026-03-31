"""Integration tests for SESSION v3 flow.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.

These tests require a running PostgreSQL database.
Run with: pytest -v -m db_integration core/session/tests/integration/
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from core.session.infrastructure.session_store import SessionStore

pytestmark = pytest.mark.db_integration


@pytest_asyncio.fixture
async def session_store(db_pool):
    """Create a SessionStore with real database pool."""
    return SessionStore(db_pool)


class TestSessionStore:
    """Integration tests for SessionStore."""

    @pytest.mark.asyncio
    async def test_create_session(self, session_store, clean_test_data):
        """Should create a session in the database."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        session = await session_store.create(
            session_id=session_id,
            domain="test-domain",
            metadata={"test": True},
        )

        assert session["session_id"] == session_id
        assert session["domain"] == "test-domain"
        assert session["status"] == "active"
        assert session["message_count"] == 0

    @pytest.mark.asyncio
    async def test_get_session(self, session_store, clean_test_data):
        """Should retrieve session by ID."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        await session_store.create(session_id, "test")
        session = await session_store.get(session_id)

        assert session is not None
        assert session["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_none(self, session_store):
        """Should return None for nonexistent session."""
        session = await session_store.get(uuid4())
        assert session is None

    @pytest.mark.asyncio
    async def test_increment_message_count(self, session_store, clean_test_data):
        """Should increment message count."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        await session_store.create(session_id, "test")

        new_count = await session_store.increment_message_count(session_id)
        assert new_count == 1

        new_count = await session_store.increment_message_count(session_id)
        assert new_count == 2

    @pytest.mark.asyncio
    async def test_complete_session(self, session_store, clean_test_data):
        """Should mark session as completed."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        await session_store.create(session_id, "test")
        updated = await session_store.complete(session_id, "completed", "Task done")

        assert updated["status"] == "completed"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_save_and_get_history(self, session_store, db_pool, clean_test_data):
        """Should save turns and retrieve history."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        await session_store.create(session_id, "test")

        # Save turns
        await session_store.save_turn(
            session_id=session_id,
            turn_number=1,
            user_message="Hello",
            assistant_response="Hi there!",
            akus_shown=[],
        )

        await session_store.save_turn(
            session_id=session_id,
            turn_number=2,
            user_message="How are you?",
            assistant_response="I'm doing well!",
            akus_shown=[],
        )

        # Get history
        history = await session_store.get_history(session_id)

        assert len(history) == 2
        assert history[0]["turn_number"] == 1
        assert history[0]["user_message"] == "Hello"
        assert history[1]["turn_number"] == 2

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_store, clean_test_data):
        """Should list sessions with filters."""
        # Create multiple sessions
        for i in range(3):
            session_id = uuid4()
            clean_test_data["ids"]["session_ids"].append(session_id)
            await session_store.create(session_id, "test-list")

        sessions, total = await session_store.list_sessions(domain="test-list")

        assert total >= 3
        assert all(s["domain"] == "test-list" for s in sessions)


class TestSQLValidation:
    """SQL query validation tests.

    These tests verify SQL syntax against real schema.
    """

    @pytest.mark.asyncio
    async def test_session_store_queries_are_valid(self, db_pool):
        """All SessionStore SQL queries should be valid."""
        async with db_pool.acquire() as conn:
            # Test SELECT query
            await conn.fetch(
                """
                EXPLAIN SELECT session_id, domain, status, metadata,
                       message_count, created_at, updated_at, completed_at
                FROM sessions WHERE session_id = $1
                """,
                uuid4(),
            )

            # Test INSERT query
            await conn.fetch(
                """
                EXPLAIN INSERT INTO sessions (
                    session_id, domain, status, metadata,
                    message_count, created_at, updated_at
                ) VALUES ($1, $2, 'active', $3, 0, $4, $4)
                RETURNING session_id
                """,
                uuid4(), "test", {}, datetime.now(timezone.utc),
            )

            # Test UPDATE query
            await conn.fetch(
                """
                EXPLAIN UPDATE sessions
                SET status = $2, completed_at = $3, updated_at = $3
                WHERE session_id = $1
                """,
                uuid4(), "completed", datetime.now(timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_session_turns_queries_are_valid(self, db_pool):
        """Session turns SQL queries should be valid."""
        async with db_pool.acquire() as conn:
            # Test SELECT history
            await conn.fetch(
                """
                EXPLAIN SELECT turn_id, turn_number, user_message, assistant_response, created_at
                FROM session_turns
                WHERE session_id = $1
                ORDER BY turn_number ASC
                """,
                uuid4(),
            )

            # Test INSERT turn
            await conn.fetch(
                """
                EXPLAIN INSERT INTO session_turns (
                    session_id, turn_number, user_message, assistant_response,
                    akus_shown, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                uuid4(), 1, "test", "test", [], datetime.now(timezone.utc),
            )


class TestEvaluationAPICompatibility:
    """Tests verifying evaluation framework compatibility.

    These ensure alec_client.py contracts are preserved.
    """

    @pytest.mark.asyncio
    async def test_session_response_has_required_fields(self, session_store, clean_test_data):
        """Session response must have fields expected by alec_client.py."""
        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        session = await session_store.create(session_id, "test")

        # alec_client.py expects: session_id, status, message_count
        assert "session_id" in session
        assert "status" in session
        assert "message_count" in session
        assert "created_at" in session
        assert "updated_at" in session

    @pytest.mark.asyncio
    async def test_session_id_is_uuid_type(self, session_store, clean_test_data):
        """Session ID must be UUID type."""
        from uuid import UUID

        session_id = uuid4()
        clean_test_data["ids"]["session_ids"].append(session_id)

        session = await session_store.create(session_id, "test")

        assert isinstance(session["session_id"], UUID)
