"""LLM Gateway client (v3).

Async HTTP client for LLM calls via the gateway service.
"""

import os
import time
from typing import Any, AsyncIterator, Optional

import httpx

from core.common.observability import LLM_CALLS, LLM_DURATION, setup_logging

# Configuration
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8011")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))


class GatewayLLMClient:
    """Async LLM client via gateway."""

    def __init__(self, gateway_url: str = LLM_GATEWAY_URL):
        """Initialize client.

        Args:
            gateway_url: LLM gateway base URL.
        """
        self.gateway_url = gateway_url
        self._client: Optional[httpx.AsyncClient] = None
        self.logger = setup_logging("llm-client")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(LLM_TIMEOUT),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        agent_name: str = "session",
    ) -> tuple[str, dict[str, Any]]:
        """Non-streaming chat completion.

        Args:
            messages: List of message dicts with role and content.
            agent_name: Name for tracking/logging.

        Returns:
            Tuple of (response content, usage dict).
        """
        client = await self._get_client()

        start_time = time.time()

        try:
            response = await client.post(
                f"{self.gateway_url}/api/v1/llm/chat",
                json={
                    "agent_name": agent_name,
                    "messages": messages,
                },
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("content", "")
            usage = result.get("usage", {})

            duration = time.time() - start_time
            LLM_CALLS.labels(service="session", status="success").inc()
            LLM_DURATION.labels(service="session").observe(duration)

            self.logger.debug(
                "llm_call_completed",
                duration_ms=int(duration * 1000),
                tokens=usage.get("total_tokens", 0),
            )

            return content, usage

        except httpx.HTTPStatusError as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error(
                "llm_call_failed",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise

        except httpx.TimeoutException:
            LLM_CALLS.labels(service="session", status="timeout").inc()
            self.logger.error("llm_call_timeout")
            raise

        except Exception as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error("llm_call_error", error=str(e))
            raise

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]] = None,
        agent_name: str = "session",
    ) -> dict[str, Any]:
        """Chat completion with tool support.

        Args:
            messages: List of message dicts with role and content.
            tools: Optional list of tool definitions.
            agent_name: Name for tracking/logging.

        Returns:
            Dict with content, stop_reason, tool_calls, and usage.
        """
        client = await self._get_client()

        start_time = time.time()

        try:
            payload: dict[str, Any] = {
                "agent_name": agent_name,
                "messages": messages,
            }
            if tools:
                payload["tools"] = tools

            response = await client.post(
                f"{self.gateway_url}/api/v1/llm/chat",
                json=payload,
            )
            response.raise_for_status()

            result = response.json()

            duration = time.time() - start_time
            LLM_CALLS.labels(service="session", status="success").inc()
            LLM_DURATION.labels(service="session").observe(duration)

            self.logger.debug(
                "llm_call_with_tools_completed",
                duration_ms=int(duration * 1000),
                tokens=result.get("usage", {}).get("total_tokens", 0),
                stop_reason=result.get("stop_reason", "end_turn"),
                tool_calls_count=len(result.get("tool_calls", [])),
            )

            return {
                "content": result.get("content"),
                "stop_reason": result.get("stop_reason", "end_turn"),
                "tool_calls": result.get("tool_calls", []),
                "usage": result.get("usage", {}),
            }

        except httpx.HTTPStatusError as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error(
                "llm_call_with_tools_failed",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise

        except httpx.TimeoutException:
            LLM_CALLS.labels(service="session", status="timeout").inc()
            self.logger.error("llm_call_with_tools_timeout")
            raise

        except Exception as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error("llm_call_with_tools_error", error=str(e))
            raise

    async def stream(
        self,
        messages: list[dict[str, str]],
        agent_name: str = "session",
    ) -> AsyncIterator[str]:
        """Streaming chat completion.

        Args:
            messages: List of message dicts.
            agent_name: Name for tracking.

        Yields:
            Response content chunks.
        """
        client = await self._get_client()

        try:
            async with client.stream(
                "POST",
                f"{self.gateway_url}/api/v1/llm/stream",
                json={
                    "agent_name": agent_name,
                    "messages": messages,
                },
            ) as response:
                response.raise_for_status()

                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk

            LLM_CALLS.labels(service="session", status="success").inc()

        except httpx.HTTPStatusError as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error(
                "llm_stream_failed",
                status_code=e.response.status_code,
            )
            # Yield error message for SSE
            yield f"Error: {e.response.status_code}"

        except Exception as e:
            LLM_CALLS.labels(service="session", status="error").inc()
            self.logger.error("llm_stream_error", error=str(e))
            yield f"Error: {str(e)}"

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
