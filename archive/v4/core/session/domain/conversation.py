"""Conversation orchestration (v3).

Pure orchestration: bullets -> LLM -> events.
No LangGraph - simple async flow.

Supports two modes via USE_TOOL_SEARCH feature flag:
- False (default): Poll Redis for ADVISOR-selected bullets
- True: LLM uses search_knowledge tool to query DB directly
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from prometheus_client import Counter, Histogram

from core.common.observability import setup_logging
from core.session.domain.bullet_formatter import extract_bullet_ids, format_bullets_for_llm
from core.session.domain.llm_client import GatewayLLMClient
from core.session.infrastructure.bullet_cache import BulletCache
from core.session.infrastructure.kafka_producer import SessionKafkaProducer

# Feature flag - default OFF in Phase 1
USE_TOOL_SEARCH = os.getenv("USE_TOOL_SEARCH", "false").lower() == "true"

# Prometheus metrics
SESSION_TURNS = Counter(
    'session_turns_total',
    'Total conversation turns',
    ['status']
)

SESSION_TURN_DURATION = Histogram(
    'session_turn_duration_seconds',
    'Turn processing duration',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

BULLETS_USED = Counter(
    'session_bullets_used_total',
    'Bullets used in prompts',
    ['source']
)


# System prompt for ADVISOR path (bullets injected as text)
SYSTEM_PROMPT = """You are a helpful AI assistant. Use the provided context to give accurate, relevant responses.

When RELEVANT KNOWLEDGE is provided:
- Solutions (#S): Approaches that worked for similar problems - verify they match YOUR specific task
- Constraints (#C): Important rules and gotchas - CHECK THESE FIRST to avoid common mistakes
- Reference (#R): Quick facts and information

Cite knowledge by number [1], [2], etc. when you use it."""

# System prompt for tool search path (LLM searches knowledge base)
SYSTEM_PROMPT_WITH_TOOL = """You are a helpful AI assistant with access to a knowledge base.

You have a search_knowledge tool. Use it to:
- Check for API constraints BEFORE making calls
- Find solutions when encountering errors
- Verify your approach matches proven patterns

Search proactively, not just when stuck. Be specific in your queries.

When knowledge is returned:
- Solutions (#S): Verify they match YOUR specific task
- Constraints (#C): CHECK THESE FIRST to avoid common mistakes
- Reference (#R): Quick facts

Cite knowledge by number [1], [2], etc. when you use it."""


@dataclass
class TurnResult:
    """Result of processing a conversation turn."""
    response: str
    bullets_used: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    cluster_id: Optional[str] = None
    turn_number: int = 0
    duration_ms: int = 0


class ConversationOrchestrator:
    """Pure orchestration: bullets -> LLM -> events.

    Supports two modes:
    - ADVISOR path: bullets.requested -> poll Redis -> inject bullets
    - Tool path: LLM uses search_knowledge tool to query DB directly
    """

    def __init__(
        self,
        bullet_cache: BulletCache,
        kafka_producer: SessionKafkaProducer,
        llm_client: GatewayLLMClient,
        aku_search: Optional[Any] = None,
    ):
        """Initialize orchestrator.

        Args:
            bullet_cache: Redis bullet cache.
            kafka_producer: Kafka event producer.
            llm_client: LLM gateway client.
            aku_search: Optional AKUSearchTool for tool-based search.
        """
        self.bullet_cache = bullet_cache
        self.kafka = kafka_producer
        self.llm_client = llm_client
        self.aku_search = aku_search
        self.logger = setup_logging("conversation")

        # Log which mode we're in
        if USE_TOOL_SEARCH:
            self.logger.info("conversation_mode", mode="tool_search")
        else:
            self.logger.info("conversation_mode", mode="advisor")

        # Session state tracking
        self._session_bullets_shown: dict[str, set[str]] = {}
        self._session_cluster_ids: dict[str, str] = {}
        self._session_turn_counts: dict[str, int] = {}

    async def process_turn(
        self,
        session_id: str,
        turn_number: int,
        user_message: str,
        history: list[dict[str, str]],
        domain: str = "general",
    ) -> TurnResult:
        """Process a single conversation turn.

        Dispatches to tool-based or ADVISOR-based flow based on USE_TOOL_SEARCH flag.

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            user_message: User's input message.
            history: Conversation history (user/assistant messages).
            domain: Session domain.

        Returns:
            TurnResult with response, bullets used, and metadata.
        """
        if USE_TOOL_SEARCH and self.aku_search is not None:
            return await self._process_turn_with_tool(
                session_id, turn_number, user_message, history, domain
            )
        else:
            return await self._process_turn_with_advisor(
                session_id, turn_number, user_message, history, domain
            )

    async def _process_turn_with_advisor(
        self,
        session_id: str,
        turn_number: int,
        user_message: str,
        history: list[dict[str, str]],
        domain: str = "general",
    ) -> TurnResult:
        """Process turn using ADVISOR path (poll Redis for bullets).

        Flow:
        1. Emit bullets.requested
        2. Poll Redis for bullets (1.5s timeout)
        3. Build messages with windowing
        4. Call LLM
        5. Emit llm.response.received
        6. Return result

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            user_message: User's input message.
            history: Conversation history (user/assistant messages).
            domain: Session domain.

        Returns:
            TurnResult with response, bullets used, and metadata.
        """
        start_time = time.time()
        session_id_str = str(session_id)

        self.logger.info(
            "turn_started",
            session_id=session_id_str,
            turn_number=turn_number,
        )

        # Get previously shown bullets and cluster
        bullets_already_shown = list(self._session_bullets_shown.get(session_id_str, set()))
        prev_cluster_id = self._session_cluster_ids.get(session_id_str)

        # 1. Emit bullets.requested
        await self.kafka.emit_bullets_requested(
            session_id=session_id_str,
            turn_number=turn_number,
            problem_context=user_message,
            domain=domain,
            cluster_id=prev_cluster_id,
            bullets_already_shown=bullets_already_shown,
        )

        # 2. Wait for bullets (poll Redis)
        bullets, cluster_id = await self.bullet_cache.get_bullets(
            session_id=session_id_str,
            turn_number=turn_number,
            timeout_ms=3000,
        )

        # Track bullets shown and cluster
        if bullets:
            bullet_ids = extract_bullet_ids(bullets)
            if session_id_str not in self._session_bullets_shown:
                self._session_bullets_shown[session_id_str] = set()
            self._session_bullets_shown[session_id_str].update(bullet_ids)
            BULLETS_USED.labels(source="redis").inc(len(bullets))

        if cluster_id:
            self._session_cluster_ids[session_id_str] = cluster_id

        self.logger.info(
            "bullets_retrieved",
            session_id=session_id_str,
            count=len(bullets),
            source="redis" if bullets else "fallback",
        )

        # 3. Build messages with windowing
        messages = self._build_messages(history, user_message, bullets)

        # 4. Call LLM
        self.logger.info("llm_call_started", session_id=session_id_str)
        response, usage = await self.llm_client.chat(messages)

        duration_ms = int((time.time() - start_time) * 1000)

        self.logger.info(
            "llm_call_completed",
            session_id=session_id_str,
            duration_ms=duration_ms,
            tokens=usage.get("total_tokens", 0),
        )

        # 5. Emit llm.response.received
        await self.kafka.emit_llm_response(
            session_id=session_id_str,
            turn_number=turn_number,
            user_message=user_message,
            assistant_response=response,
            bullets_used=bullets,
        )

        # Metrics
        SESSION_TURNS.labels(status="success").inc()
        SESSION_TURN_DURATION.observe(duration_ms / 1000)

        self.logger.info(
            "turn_completed",
            session_id=session_id_str,
            turn_number=turn_number,
            duration_ms=duration_ms,
        )

        return TurnResult(
            response=response,
            bullets_used=bullets,
            usage=usage,
            cluster_id=cluster_id,
            turn_number=turn_number,
            duration_ms=duration_ms,
        )

    def _build_messages(
        self,
        history: list[dict[str, str]],
        user_message: str,
        bullets: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Build message list with windowing and bullet injection.

        Windowing strategy:
        - First turn (2 messages) always included
        - Last 4 turns (8 messages) always included
        - Middle turns trimmed if over limit

        Bullet injection:
        - Inject AFTER first user message for prompt caching efficiency

        Args:
            history: Previous conversation messages.
            user_message: Current user message.
            bullets: Bullets to inject.

        Returns:
            List of messages for LLM.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Window history
        if len(history) > 10:
            # First turn (2 messages)
            messages.extend(history[:2])
            # Last 4 turns (8 messages)
            messages.extend(history[-8:])
        else:
            messages.extend(history)

        # Inject bullets AFTER first user message for prompt caching
        if bullets:
            bullet_text = format_bullets_for_llm(bullets)
            if bullet_text:
                # Find first user message index (after system)
                insert_idx = 1
                for i, msg in enumerate(messages[1:], 1):
                    if msg.get("role") == "user":
                        insert_idx = i + 1
                        break

                messages.insert(insert_idx, {
                    "role": "user",
                    "content": bullet_text,
                })

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _process_turn_with_tool(
        self,
        session_id: str,
        turn_number: int,
        user_message: str,
        history: list[dict[str, str]],
        domain: str = "general",
    ) -> TurnResult:
        """Process turn using tool-based search (LLM searches KB directly).

        Flow:
        1. Cold-start fallback: proactive search on turn 1
        2. Build messages with tool-aware system prompt
        3. Tool execution loop:
           a. Call LLM with search_knowledge tool
           b. If tool_use, execute search and continue
           c. Repeat until end_turn
        4. Emit llm.response.received
        5. Return result

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            user_message: User's input message.
            history: Conversation history.
            domain: Session domain.

        Returns:
            TurnResult with response, bullets used, and metadata.
        """
        from core.session.domain.aku_search import SEARCH_KNOWLEDGE_TOOL

        start_time = time.time()
        session_id_str = str(session_id)

        self.logger.info(
            "turn_started_tool_mode",
            session_id=session_id_str,
            turn_number=turn_number,
        )

        # Track turn number
        self._session_turn_counts[session_id_str] = turn_number

        # Get previous cluster_id for continuity
        cluster_id: Optional[str] = self._session_cluster_ids.get(session_id_str)

        # Cold-start fallback: proactive search on turn 1
        proactive_bullets: list[dict[str, Any]] = []
        if turn_number == 1 and self.aku_search is not None:
            search_result = await self.aku_search.search(
                query=user_message[:500],
                cluster_id=cluster_id,
            )
            proactive_bullets = [
                {
                    "bullet_id": str(b.bullet_id),
                    "situation": b.situation,
                    "assertion": b.assertion,
                    "polarity": b.polarity,
                    "category": b.category,
                }
                for b in search_result.bullets
            ]
            if (cid := search_result.cluster_id) is not None:
                cluster_id = cid
                self._session_cluster_ids[session_id_str] = cid

            self.logger.info(
                "cold_start_search",
                session_id=session_id_str,
                bullets_found=len(proactive_bullets),
            )

        # Build messages with tool-aware system prompt
        messages = self._build_messages_for_tool(
            history, user_message, proactive_bullets
        )

        # Tool execution loop
        tools = [SEARCH_KNOWLEDGE_TOOL]
        all_bullets_used: list[dict[str, Any]] = list(proactive_bullets)
        total_usage: dict[str, Any] = {}
        max_tool_iterations = 5
        iteration = 0

        while iteration < max_tool_iterations:
            iteration += 1

            self.logger.info(
                "llm_call_with_tools",
                session_id=session_id_str,
                iteration=iteration,
            )

            result = await self.llm_client.chat_with_tools(
                messages=messages,
                tools=tools,
                agent_name="session",
            )

            # Accumulate usage
            for key, value in result.get("usage", {}).items():
                if isinstance(value, (int, float)):
                    total_usage[key] = total_usage.get(key, 0) + value

            # Check if we're done
            if result["stop_reason"] != "tool_use":
                response = result.get("content", "")
                break

            # Execute tool calls
            tool_results = []
            for tool_call in result["tool_calls"]:
                if tool_call["name"] == "search_knowledge" and self.aku_search is not None:
                    query = tool_call["input"].get("query", "")

                    self.logger.info(
                        "executing_search_tool",
                        session_id=session_id_str,
                        query=query[:100],
                    )

                    search_result = await self.aku_search.search(
                        query=query,
                        cluster_id=cluster_id,
                    )

                    # Track bullets used
                    for b in search_result.bullets:
                        bullet_dict = {
                            "bullet_id": str(b.bullet_id),
                            "situation": b.situation,
                            "assertion": b.assertion,
                            "polarity": b.polarity,
                            "category": b.category,
                        }
                        if bullet_dict not in all_bullets_used:
                            all_bullets_used.append(bullet_dict)

                    # Update cluster_id
                    if (cid := search_result.cluster_id) is not None:
                        cluster_id = cid
                        self._session_cluster_ids[session_id_str] = cid

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call["id"],
                        "content": search_result.formatted,
                    })

                    BULLETS_USED.labels(source="tool").inc(len(search_result.bullets))

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": result.get("content") or "",
            })

            # Append tool results as user message
            if tool_results:
                messages.append({
                    "role": "user",
                    "content": "\n".join(tr["content"] for tr in tool_results),
                })

        else:
            # Max iterations reached
            self.logger.warning(
                "tool_loop_max_iterations",
                session_id=session_id_str,
                iterations=max_tool_iterations,
            )
            response = result.get("content", "") if result else ""

        duration_ms = int((time.time() - start_time) * 1000)

        self.logger.info(
            "turn_completed_tool_mode",
            session_id=session_id_str,
            turn_number=turn_number,
            duration_ms=duration_ms,
            bullets_used=len(all_bullets_used),
            tool_iterations=iteration,
        )

        # Track bullets shown
        if all_bullets_used:
            if session_id_str not in self._session_bullets_shown:
                self._session_bullets_shown[session_id_str] = set()
            for b in all_bullets_used:
                self._session_bullets_shown[session_id_str].add(b["bullet_id"])

        # Emit llm.response.received
        await self.kafka.emit_llm_response(
            session_id=session_id_str,
            turn_number=turn_number,
            user_message=user_message,
            assistant_response=response,
            bullets_used=all_bullets_used,
        )

        # Metrics
        SESSION_TURNS.labels(status="success").inc()
        SESSION_TURN_DURATION.observe(duration_ms / 1000)

        return TurnResult(
            response=response,
            bullets_used=all_bullets_used,
            usage=total_usage,
            cluster_id=cluster_id,
            turn_number=turn_number,
            duration_ms=duration_ms,
        )

    def _build_messages_for_tool(
        self,
        history: list[dict[str, str]],
        user_message: str,
        proactive_bullets: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Build messages for tool-based search flow.

        Uses SYSTEM_PROMPT_WITH_TOOL and includes proactive bullets
        from cold-start search.

        Args:
            history: Previous conversation messages.
            user_message: Current user message.
            proactive_bullets: Bullets from cold-start search (turn 1).

        Returns:
            List of messages for LLM.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT_WITH_TOOL}]

        # Window history (same as ADVISOR path)
        if len(history) > 10:
            messages.extend(history[:2])
            messages.extend(history[-8:])
        else:
            messages.extend(history)

        # Include proactive bullets if present (turn 1 cold-start)
        if proactive_bullets:
            bullet_text = format_bullets_for_llm(proactive_bullets)
            if bullet_text:
                messages.append({
                    "role": "user",
                    "content": f"Initial knowledge (you can search for more):\n{bullet_text}",
                })

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    def clear_session(self, session_id: str) -> None:
        """Clear session state.

        Args:
            session_id: Session UUID string.
        """
        self._session_bullets_shown.pop(session_id, None)
        self._session_cluster_ids.pop(session_id, None)
        self._session_turn_counts.pop(session_id, None)
        self.bullet_cache.clear_session(session_id)
