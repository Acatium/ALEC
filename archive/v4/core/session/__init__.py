"""SESSION service v3 - Pure orchestration for ALEC conversations.

This service handles:
1. Bullet retrieval coordination (Redis polling)
2. LLM calls via gateway
3. Kafka event emission for learning loop

No LangGraph - simple async orchestration.
"""

from core.session.service import SessionService

__all__ = ["SessionService"]
