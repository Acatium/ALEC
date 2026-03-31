"""Integration tests for LLM Gateway API endpoints.

Tests endpoints with real database, mocks only external Anthropic API.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ============================================================================
# Test: Pydantic Models Validation
# ============================================================================


class TestRequestModels:
    """Test request/response model validation."""

    def test_chat_request_requires_agent_name(self):
        """ChatRequest should require agent_name field."""
        from core.llm_gateway.api.endpoints import ChatRequest

        with pytest.raises(Exception):  # Pydantic validation error
            ChatRequest(messages=[])  # type: ignore[call-arg]

    def test_chat_request_requires_messages(self):
        """ChatRequest should require messages field."""
        from core.llm_gateway.api.endpoints import ChatRequest

        with pytest.raises(Exception):
            ChatRequest(agent_name="test")  # type: ignore[call-arg]

    def test_chat_request_accepts_valid_input(self):
        """ChatRequest should accept valid input."""
        from core.llm_gateway.api.endpoints import ChatRequest, MessageInput

        request = ChatRequest(
            agent_name="session",
            messages=[MessageInput(role="user", content="Hello")],
        )

        assert request.agent_name == "session"
        assert len(request.messages) == 1

    def test_message_input_requires_role_and_content(self):
        """MessageInput should require role and content."""
        from core.llm_gateway.api.endpoints import MessageInput

        msg = MessageInput(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_chat_response_includes_usage_stats(self):
        """ChatResponse should include usage statistics."""
        from core.llm_gateway.api.endpoints import ChatResponse, UsageStats

        response = ChatResponse(
            content="Hello!",
            model="claude-haiku",
            usage=UsageStats(input_tokens=10, output_tokens=5),
        )

        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5
        assert response.usage.cache_creation_input_tokens == 0  # Default


# ============================================================================
# Test: Endpoint Logic (with mocked Anthropic only)
# ============================================================================


class TestChatEndpointLogic:
    """Test chat endpoint logic with real config, mocked Anthropic."""

    @pytest.mark.asyncio
    async def test_chat_returns_404_for_unknown_agent(self):
        """Should return 404 when agent not found."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        # Setup real config store with defaults
        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        # Inject into endpoints module
        endpoints.config_store = store
        endpoints.anthropic_client = MagicMock()

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/llm/chat",
                json={
                    "agent_name": "nonexistent_agent_xyz",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

        await store.close()

    @pytest.mark.asyncio
    async def test_chat_uses_config_from_store(self):
        """Should use model/temperature from ConfigStore."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.anthropic_client import LLMResponse
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        # Setup real config store
        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        # Mock only the Anthropic client (external API)
        mock_anthropic = AsyncMock()
        mock_anthropic.chat.return_value = LLMResponse(
            content="Test response",
            model="claude-haiku-4-5-20251001",
            usage={"input_tokens": 10, "output_tokens": 5,
                   "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        )

        endpoints.config_store = store
        endpoints.anthropic_client = mock_anthropic

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/llm/chat",
                json={
                    "agent_name": "session",  # Known default agent
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        assert response.status_code == 200

        # Verify Anthropic was called with config values
        call_kwargs = mock_anthropic.chat.call_args[1]
        session_config = store.get_config("session")
        assert session_config is not None
        assert call_kwargs["model"] == session_config.model
        assert call_kwargs["temperature"] == session_config.temperature

        await store.close()

    @pytest.mark.asyncio
    async def test_chat_extracts_system_messages(self):
        """Should extract system messages and pass as system_prompt."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.anthropic_client import LLMResponse
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        mock_anthropic = AsyncMock()
        mock_anthropic.chat.return_value = LLMResponse(
            content="Response",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 5,
                   "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        )

        endpoints.config_store = store
        endpoints.anthropic_client = mock_anthropic

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/llm/chat",
                json={
                    "agent_name": "session",
                    "messages": [
                        {"role": "system", "content": "You are helpful."},
                        {"role": "user", "content": "Hello"},
                    ],
                },
            )

        assert response.status_code == 200

        # System message should be extracted
        call_kwargs = mock_anthropic.chat.call_args[1]
        assert call_kwargs["system_prompt"] == "You are helpful."

        # Messages passed should not include system
        messages = call_kwargs["messages"]
        assert all(m["role"] != "system" for m in messages)

        await store.close()


# ============================================================================
# Test: Config Reload Endpoint
# ============================================================================


class TestReloadEndpoint:
    """Test config reload endpoint with real database."""

    @pytest.mark.asyncio
    async def test_reload_returns_agent_count(self):
        """reload-config should return count of loaded agents."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        endpoints.config_store = store
        endpoints.anthropic_client = MagicMock()

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/reload-config")

        assert response.status_code == 200
        data = response.json()
        assert "agents_loaded" in data
        assert data["agents_loaded"] >= 3  # At least default configs

        await store.close()


# ============================================================================
# Test: Get Agent Config Endpoint
# ============================================================================


class TestGetAgentConfigEndpoint:
    """Test get agent config endpoint."""

    @pytest.mark.asyncio
    async def test_get_config_returns_agent_details(self):
        """Should return agent configuration details."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        endpoints.config_store = store

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/agents/session/config")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "session"
        assert "model" in data
        assert "temperature" in data
        assert "max_tokens" in data

        await store.close()

    @pytest.mark.asyncio
    async def test_get_config_returns_404_for_unknown(self):
        """Should return 404 for unknown agent."""
        from core.llm_gateway.api import endpoints
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
        await store.initialize(db_url)

        endpoints.config_store = store

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(endpoints.router)

        async with AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/agents/unknown_agent_xyz/config")

        assert response.status_code == 404

        await store.close()
