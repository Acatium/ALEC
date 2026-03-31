"""Worker service — tool-use loop that explores sources and writes to graph."""

from __future__ import annotations

import json
from typing import Any

import structlog

from alec.agents.llm_client import LLMClient, LLMResponse
from alec.agents.prompts.worker import WORKER_BASE_PROMPT, build_worker_prompt
from alec.agents.tools.graph_tools import GRAPH_TOOLS, build_graph_tools
from alec.agents.tools.source_tools import SOURCE_TOOLS
from alec.connectors.protocol import SourceConnector
from alec.errors import BudgetExhaustedError, ToolError
from alec.events.bus import EventBus
from alec.events.types import WorkerCompleted, WorkerProgress
from alec.knowledge.domain import TaskRecord, WorkerResult
from alec.knowledge.graph_writer import GraphWriter
from alec.runtime.budget import BudgetTracker
from alec.runtime.drift import WorkerLoopState, check_drift, hash_tool_call

logger = structlog.get_logger()


class WorkerService:
    """Runs a single worker task through the tool-use loop."""

    def __init__(
        self,
        llm: LLMClient,
        connector: SourceConnector,
        graph: GraphWriter,
        budget: BudgetTracker,
        event_bus: EventBus,
        max_turns: int = 30,
        max_retries_per_tool: int = 3,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
        entity_vocabulary: list[str] | None = None,
    ) -> None:
        self._llm = llm
        self._connector = connector
        self._graph = graph
        self._budget = budget
        self._bus = event_bus
        self._max_turns = max_turns
        self._max_retries_per_tool = max_retries_per_tool

        # Dynamic schema
        self._entity_types = entity_types
        self._relationship_types = relationship_types
        self._entity_vocabulary = entity_vocabulary

        # Build tools dynamically
        if entity_types is not None or relationship_types is not None:
            self._tools = SOURCE_TOOLS + build_graph_tools(entity_types, relationship_types)
        else:
            self._tools = SOURCE_TOOLS + GRAPH_TOOLS
        self._graph_tool_names = {t["name"] for t in self._tools if t["name"] not in {
            "survey", "list_children", "read", "search"
        }}

    async def run(self, task: TaskRecord) -> WorkerResult:
        """Execute the worker task. Returns WorkerResult."""
        worker_id = f"worker-{task.task_id.hex[:8]}"

        # Build system prompt with task context
        system_prompt = self._build_system_prompt(task)
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"## Directive\n{task.directive}\n\n"
                    f"## Scope\n{task.max_scope}\n\n"
                    f"## Source\n{task.source_type}: {task.source_ref}\n\n"
                    + (f"## Context\n{task.relevant_context}\n" if task.relevant_context else "")
                ),
            }
        ]

        state = WorkerLoopState()
        scope_overflow = False
        turn_count = 0

        try:
            while turn_count < self._max_turns:
                turn_count += 1

                # Check budget before LLM call
                if not self._budget.check():
                    scope_overflow = True
                    logger.warning("worker.budget_exceeded", worker_id=worker_id)
                    break

                # LLM call
                response = await self._llm.call(
                    system=system_prompt,
                    messages=messages,
                    tools=self._tools,
                    max_tokens=4096,
                )

                # Track token usage
                await self._budget.record(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )

                # Worker decided it's done
                if response.stop_reason == "end_turn":
                    messages.append({"role": "assistant", "content": response.content})
                    break

                # Process tool calls
                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})

                    tool_results = []
                    for tc in response.tool_calls:
                        call_hash = hash_tool_call(tc.name, tc.input)

                        # Duplicate detection: return cached result
                        if call_hash in state.tool_call_cache:
                            tool_result = state.tool_call_cache[call_hash]
                            state.duplicate_calls_skipped += 1
                            logger.info(
                                "worker.duplicate_skipped",
                                worker_id=worker_id,
                                tool=tc.name,
                            )
                        elif (
                            state.tool_error_counts.get(call_hash, 0)
                            >= self._max_retries_per_tool
                        ):
                            tool_result = (
                                f"Error: retry limit ({self._max_retries_per_tool}) "
                                f"exceeded for {tc.name}"
                            )
                            state.retries_exhausted += 1
                            logger.warning(
                                "worker.retries_exhausted",
                                worker_id=worker_id,
                                tool=tc.name,
                            )
                        else:
                            tool_result = await self._execute_tool(tc.name, tc.input)
                            if tool_result.startswith("Error"):
                                state.tool_error_counts[call_hash] = (
                                    state.tool_error_counts.get(call_hash, 0) + 1
                                )
                            else:
                                state.tool_call_cache[call_hash] = tool_result

                        # Track entity types for drift detection
                        state.tool_call_count += 1
                        if tc.name == "add_entity" and not tool_result.startswith("Error"):
                            entity_type = tc.input.get("entity_type", "")
                            if entity_type:
                                state.entity_types_discovered[entity_type] = (
                                    state.entity_types_discovered.get(entity_type, 0) + 1
                                )

                        # Check drift every 5 tool calls
                        if (
                            state.tool_call_count % 5 == 0
                            and task.max_scope
                            and not state.drift_detected
                        ):
                            if check_drift(state, task.max_scope):
                                state.drift_detected = True
                                logger.warning(
                                    "worker.drift_detected",
                                    worker_id=worker_id,
                                    entity_types=state.entity_types_discovered,
                                    scope=task.max_scope,
                                )

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tc.id,
                                "content": tool_result,
                            }
                        )
                        logger.info(
                            "worker.tool_call",
                            worker_id=worker_id,
                            tool=tc.name,
                            turn=turn_count,
                        )

                    messages.append({"role": "user", "content": tool_results})

                    # Emit progress
                    await self._bus.emit(
                        WorkerProgress(
                            engagement_id=task.engagement_id,
                            task_id=task.task_id,
                            worker_id=worker_id,
                            current_action=self._summarize_tools(response),
                            entities_so_far=self._graph.entities_written,
                            observations_so_far=self._graph.observations_written,
                            tokens_used=self._budget.tokens_used,
                        )
                    )

        except BudgetExhaustedError:
            scope_overflow = True
            logger.warning("worker.budget_exhausted", worker_id=worker_id)
        except Exception as e:
            logger.error("worker.error", worker_id=worker_id, error=str(e))
            return WorkerResult(
                task_id=task.task_id,
                worker_id=worker_id,
                entities_written=self._graph.entities_written,
                relationships_written=self._graph.relationships_written,
                observations_written=self._graph.observations_written,
                followups_suggested=self._graph.followups_suggested,
                scope_overflow=scope_overflow,
                error=str(e),
                tokens_used=self._budget.tokens_used,
                drift_detected=state.drift_detected,
                duplicate_calls_skipped=state.duplicate_calls_skipped,
                retries_exhausted=state.retries_exhausted,
            )

        result = WorkerResult(
            task_id=task.task_id,
            worker_id=worker_id,
            entities_written=self._graph.entities_written,
            relationships_written=self._graph.relationships_written,
            observations_written=self._graph.observations_written,
            followups_suggested=self._graph.followups_suggested,
            scope_overflow=scope_overflow,
            tokens_used=self._budget.tokens_used,
            drift_detected=state.drift_detected,
            duplicate_calls_skipped=state.duplicate_calls_skipped,
            retries_exhausted=state.retries_exhausted,
        )

        await self._bus.emit(
            WorkerCompleted(
                engagement_id=task.engagement_id,
                task_id=task.task_id,
                worker_id=worker_id,
                entities_written=result.entities_written,
                relationships_written=result.relationships_written,
                observations_written=result.observations_written,
                scope_overflow=result.scope_overflow,
            )
        )

        return result

    async def _execute_tool(self, name: str, params: dict[str, Any]) -> str:
        """Route tool call to source connector or graph writer."""
        try:
            if name == "survey":
                entries = await self._connector.survey()
                return json.dumps(entries[:50])
            elif name == "list_children":
                children = await self._connector.list_children(params["ref"])
                return json.dumps(children[:100])
            elif name == "read":
                content = await self._connector.read(params["ref"])
                if len(content) > 50_000:
                    content = content[:50_000] + "\n\n[TRUNCATED — content exceeds 50k chars]"
                return content
            elif name == "search":
                results = await self._connector.search(params["query"])
                return json.dumps(results[:20])
            elif name in self._graph_tool_names:
                return await self._graph.execute(name, params)
            else:
                return f"Unknown tool: {name}"
        except ToolError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error("worker.tool_error", tool=name, error=str(e))
            return f"Error executing {name}: {e}"

    def _build_system_prompt(self, task: TaskRecord) -> str:
        if self._entity_types or self._relationship_types or self._entity_vocabulary:
            return build_worker_prompt(
                entity_types=self._entity_types,
                relationship_types=self._relationship_types,
                entity_vocabulary=self._entity_vocabulary,
            )
        return WORKER_BASE_PROMPT

    @staticmethod
    def _summarize_tools(response: LLMResponse) -> str:
        if not response.tool_calls:
            return "thinking"
        names = [tc.name for tc in response.tool_calls]
        return ", ".join(names)
