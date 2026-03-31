"""Async HTTP client for ALEC session API."""

from typing import Any

import httpx


class ALECClientError(Exception):
    """Exception raised for ALEC API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ALECClient:
    """Async HTTP client for interacting with ALEC session service."""

    def __init__(
        self,
        base_url: str = "http://session:8008",
        timeout: float = 120.0,
    ):
        """Initialize ALEC client.

        Args:
            base_url: Base URL for the session service.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ALECClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not initialized."""
        if self._client is None:
            raise ALECClientError(
                "Client not initialized. Use 'async with ALECClient() as client:'"
            )
        return self._client

    async def create_session(
        self,
        first_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new chat session by sending the first message.

        This uses the /message endpoint with no session_id, which:
        1. Creates a new session
        2. Waits for bullet reflector (if enabled via service toggle)
        3. Injects bullets into prompt (if enabled via service toggle)
        4. Calls LLM and returns response

        Note: Learning is controlled via service toggles on /agents page,
        not per-request parameters.

        Args:
            first_message: Initial message to start the conversation.
            metadata: Optional metadata for the session.

        Returns:
            Session response containing session_id and initial response.

        Raises:
            ALECClientError: If the request fails.
        """
        client = self._get_client()

        # Use /message endpoint with no session_id to create session
        # This ensures proper session flow: create -> bullets -> LLM
        payload: dict[str, Any] = {
            "message": first_message,
            "metadata": metadata or {},
        }

        try:
            response = await client.post("/api/v1/chat/message", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise ALECClientError(
                f"Failed to create session: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ALECClientError(f"Request failed: {str(e)}") from e

    async def send_message(
        self,
        session_id: str,
        message: str,
    ) -> dict[str, Any]:
        """Send a message to an existing session.

        Args:
            session_id: The session ID to send the message to.
            message: The message content.

        Returns:
            Response containing the assistant's reply.

        Raises:
            ALECClientError: If the request fails.
        """
        client = self._get_client()

        payload = {
            "session_id": session_id,
            "message": message,
        }

        try:
            response = await client.post(
                "/api/v1/chat/message",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise ALECClientError(
                f"Failed to send message: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ALECClientError(f"Request failed: {str(e)}") from e

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session details.

        Args:
            session_id: The session ID to retrieve.

        Returns:
            Session details including messages and metadata.

        Raises:
            ALECClientError: If the request fails.
        """
        client = self._get_client()

        try:
            response = await client.get(f"/api/v1/chat/sessions/{session_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise ALECClientError(
                f"Failed to get session: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ALECClientError(f"Request failed: {str(e)}") from e

    async def complete_session(
        self,
        session_id: str,
        success: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Complete a session via SESSION API.

        This emits the session.ended event through SESSION, which is consumed
        by REFLECTOR for turn analysis and learning.

        Args:
            session_id: The session ID to complete.
            success: Whether the session completed successfully.
            reason: Optional reason for completion.

        Returns:
            Session response with updated status.

        Raises:
            ALECClientError: If the request fails.
        """
        client = self._get_client()

        payload = {
            "status": "completed" if success else "failed",
            "reason": reason,
        }

        try:
            response = await client.post(
                f"/api/v1/chat/sessions/{session_id}/complete",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise ALECClientError(
                f"Failed to complete session: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ALECClientError(f"Request failed: {str(e)}") from e

    async def health_check(self) -> bool:
        """Check if the ALEC session service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        client = self._get_client()

        try:
            response = await client.get("/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False
