"""Supervisor — main async loop that wires dependencies and runs cycles."""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from alec.agents.llm_client import AnthropicLLMClient, LLMClient
from alec.config.settings import Settings
from alec.connectors.protocol import SourceConnector
from alec.connectors.registry import ConnectorRegistry, default_registry
from alec.connectors.source_config import parse_source_spec
from alec.db.embeddings import EmbeddingService, MockEmbeddingService
from alec.db.pool import close_pool, create_pool
from alec.errors import BudgetExhaustedError
from alec.events.bus import EventBus
from alec.events.types import (
    CommunityDetected,
    ConvergenceReached,
    CycleCompleted,
    CycleStarted,
    EngagementStarted,
    WorkerDispatched,
)
from alec.knowledge.domain import ConsolidationConfig, ConvergenceConfig, TaskRecord, WorkerResult
from alec.knowledge.graph_writer import GraphWriter
from alec.knowledge.repositories.consolidation import ConsolidationRepository
from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.projections import ProjectionRepository
from alec.knowledge.repositories.relationships import RelationshipRepository
from alec.knowledge.repositories.schema import SchemaRepository
from alec.knowledge.repositories.tasks import TaskRepository
from alec.knowledge.templates import populate_schema
from alec.reports.html_report import generate_report
from alec.runtime.budget import BudgetTracker
from alec.runtime.consolidation import ConsolidationService
from alec.runtime.coordinator import CoordinatorService
from alec.runtime.worker import WorkerService

logger = structlog.get_logger()


class Supervisor:
    """Main loop: init engagement → coordinator cycles → dispatch workers → converge."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._shutdown = False

    async def run(
        self,
        sources: list[str],
        problem_statement: str = "",
        max_cycles: int = 3,
        report_path: str | None = None,
        pool: asyncpg.Pool | None = None,
        event_bus: EventBus | None = None,
        engagement_id: UUID | None = None,
    ) -> dict[str, object]:
        """Run the full supervisor loop. Returns summary dict.

        If pool is provided, it is used directly (caller manages lifecycle).
        If event_bus is provided, it is passed through to _run_loop.
        If engagement_id is provided, reuses an existing engagement (restart).
        """
        owns_pool = pool is None
        if owns_pool:
            pool = await create_pool(
                self._settings.database_url,
                min_size=self._settings.db_min_pool_size,
                max_size=self._settings.db_max_pool_size,
            )

        try:
            return await self._run_loop(
                pool,
                sources,
                problem_statement,
                max_cycles,
                report_path,
                event_bus,
                engagement_id,
            )
        finally:
            if owns_pool:
                await close_pool(pool)

    async def _run_loop(
        self,
        pool: asyncpg.Pool,
        sources: list[str],
        problem_statement: str,
        max_cycles: int,
        report_path: str | None = None,
        event_bus: EventBus | None = None,
        engagement_id: UUID | None = None,
    ) -> dict[str, object]:
        """Core loop with all dependencies wired."""
        # Wire repositories
        entity_repo = EntityRepository(pool)
        relationship_repo = RelationshipRepository(pool)
        observation_repo = ObservationRepository(pool)
        task_repo = TaskRepository(pool)
        projection_repo = ProjectionRepository(pool)

        # Wire services
        embedder: EmbeddingService
        if self._settings.use_real_embeddings:
            try:
                from alec.db.embeddings_st import SentenceTransformerEmbeddingService
            except ImportError:
                raise RuntimeError(
                    "Real embeddings enabled but sentence-transformers not installed. "
                    "Install with: pip install -e '.[embeddings]' "
                    "Or set ALEC_USE_REAL_EMBEDDINGS=false for testing only."
                )

            embedder = SentenceTransformerEmbeddingService(
                model_name=self._settings.embedding_model,
            )
            logger.info(
                "supervisor.embeddings",
                model=self._settings.embedding_model,
                dimensions=embedder.dimensions,
            )
        else:
            logger.warning(
                "supervisor.mock_embeddings",
                msg="Using mock embeddings — fuzzy entity resolution will NOT work",
            )
            embedder = MockEmbeddingService(
                dimensions=self._settings.embedding_dimensions,
            )

        if event_bus is None:
            event_bus = EventBus()

        llm: LLMClient
        if not self._settings.anthropic_api_key:
            raise RuntimeError(
                "No Anthropic API key configured. "
                "Set ALEC_ANTHROPIC_API_KEY environment variable."
            )
        llm = AnthropicLLMClient(
            api_key=self._settings.anthropic_api_key,
            model=self._settings.default_model,
        )

        consolidation_repo = ConsolidationRepository(pool)
        consolidation = ConsolidationService(
            repo=consolidation_repo,
            llm=llm,
            embedder=embedder,
            event_bus=event_bus,
        )
        consolidation_config = ConsolidationConfig()

        # Parse sources and create connectors
        registry = default_registry()
        connectors: dict[str, SourceConnector] = {}

        for source_str in sources:
            spec = parse_source_spec(source_str)
            connector = registry.create(spec.source_type, spec.config)
            key = self._connector_key(spec.source_type, spec.config)
            connectors[key] = connector

        try:
            sources_desc = ", ".join(sources)
            if not problem_statement:
                problem_statement = f"Discover and map knowledge from sources: {sources_desc}"

            if engagement_id is None:
                # Create new engagement
                async with pool.acquire() as conn:
                    engagement_id = await conn.fetchval(
                        """
                        INSERT INTO engagements
                            (name, problem_statement, summary, status, last_heartbeat)
                        VALUES ($1, $2, $3, 'active', NOW())
                        RETURNING engagement_id
                        """,
                        f"Discovery: {sources_desc[:200]}",
                        problem_statement,
                        problem_statement,
                    )
                    coordinator_id = await conn.fetchval(
                        """
                        INSERT INTO coordinator_instances (engagement_id, status)
                        VALUES ($1, 'active')
                        RETURNING instance_id
                        """,
                        engagement_id,
                    )
                    # Register all source configs
                    for source_str in sources:
                        spec = parse_source_spec(source_str)
                        await conn.execute(
                            """
                            INSERT INTO source_configs
                                (engagement_id, source_type, config, status)
                            VALUES ($1, $2, $3, 'verified')
                            """,
                            engagement_id,
                            spec.source_type,
                            json.dumps(spec.config),
                        )
            else:
                # Reuse existing engagement — create coordinator and register sources if needed
                async with pool.acquire() as conn:
                    coordinator_id = await conn.fetchval(
                        """
                        INSERT INTO coordinator_instances (engagement_id, status)
                        VALUES ($1, 'active')
                        RETURNING instance_id
                        """,
                        engagement_id,
                    )
                    await conn.execute(
                        "UPDATE engagements SET last_heartbeat = NOW() "
                        "WHERE engagement_id = $1",
                        engagement_id,
                    )
                    # Register source configs if not already present
                    existing = await conn.fetchval(
                        "SELECT COUNT(*) FROM source_configs "
                        "WHERE engagement_id = $1",
                        engagement_id,
                    )
                    if existing == 0:
                        for source_str in sources:
                            spec = parse_source_spec(source_str)
                            await conn.execute(
                                """
                                INSERT INTO source_configs
                                    (engagement_id, source_type, config, status)
                                VALUES ($1, $2, $3, 'verified')
                                """,
                                engagement_id,
                                spec.source_type,
                                json.dumps(spec.config),
                            )

            # Auto-populate schema with general_discovery template if empty
            schema_repo = SchemaRepository(pool)
            try:
                schema_count = await schema_repo.count(engagement_id)
                if schema_count == 0:
                    await populate_schema(pool, engagement_id, "general_discovery")
                    logger.info(
                        "supervisor.schema_populated",
                        engagement_id=str(engagement_id),
                        template="general_discovery",
                    )
            except Exception:
                logger.warning("supervisor.schema_populate_error", exc_info=True)

            await event_bus.emit(
                EngagementStarted(
                    engagement_id=engagement_id,
                    name=f"Discovery: {sources_desc[:200]}",
                )
            )

            logger.info(
                "supervisor.started",
                engagement_id=str(engagement_id),
                sources=sources,
                max_cycles=max_cycles,
            )

            convergence_config = ConvergenceConfig(
                convergence_threshold=self._settings.convergence_threshold,
                consecutive_cycles_required=self._settings.consecutive_cycles_required,
                novelty_decay=self._settings.convergence_novelty_decay,
                max_reinforcement_per_entity_per_cycle=(
                    self._settings.convergence_max_reinforcement_per_entity
                ),
                expansion_deceleration_cycles=(
                    self._settings.convergence_expansion_deceleration_cycles
                ),
            )

            # Handle signals
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_shutdown)

            # Periodic heartbeat so the API doesn't mark us as stalled
            # while workers are running (cycles can exceed 60s easily).
            heartbeat_stop = asyncio.Event()

            async def _heartbeat_loop() -> None:
                while not heartbeat_stop.is_set():
                    try:
                        async with pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE engagements SET last_heartbeat = NOW() "
                                "WHERE engagement_id = $1",
                                engagement_id,
                            )
                    except Exception:
                        logger.warning("supervisor.heartbeat_error", exc_info=True)
                    try:
                        await asyncio.wait_for(heartbeat_stop.wait(), timeout=30)
                        break  # event was set
                    except asyncio.TimeoutError:
                        pass  # loop again

            heartbeat_task = asyncio.create_task(_heartbeat_loop())

            # Main cycle loop — continue from last cycle number
            last_cycle_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            total_budget = BudgetTracker(
                max_tokens=self._settings.worker_max_tokens
                * max_cycles
                * self._settings.max_workers
            )

            async with pool.acquire() as conn:
                last_cycle = await conn.fetchval(
                    "SELECT COALESCE(MAX(cycle_number), 0) "
                    "FROM convergence_log WHERE engagement_id = $1",
                    engagement_id,
                )
            cycle_offset = last_cycle  # 0 for new engagements, N for restarts

            did_converge = False
            for cycle_num in range(cycle_offset + 1, cycle_offset + max_cycles + 1):
                if self._shutdown:
                    logger.info("supervisor.shutdown_requested")
                    break

                # Update heartbeat at start of each cycle
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE engagements SET last_heartbeat = NOW() "
                        "WHERE engagement_id = $1",
                        engagement_id,
                    )

                # Refresh connectors from source_configs (picks up newly added sources)
                await self._refresh_connectors(
                    pool, engagement_id, connectors, registry,
                )

                await event_bus.emit(
                    CycleStarted(
                        engagement_id=engagement_id,
                        cycle_number=cycle_num,
                    )
                )

                logger.info("supervisor.cycle_start", cycle=cycle_num)

                # Query schema types and entity vocabulary once per cycle
                entity_types: list[str] | None = None
                relationship_types: list[str] | None = None
                entity_vocabulary: list[str] | None = None
                try:
                    schema_entries = await schema_repo.get_all(engagement_id)
                    if schema_entries:
                        entity_types = [
                            e.name for e in schema_entries if e.kind == "entity_type"
                        ]
                        relationship_types = [
                            e.name for e in schema_entries if e.kind == "relationship_type"
                        ]
                    # Get top 50 entity names for vocabulary
                    top_entities = await entity_repo.list_by_engagement(engagement_id)
                    if top_entities:
                        entity_vocabulary = [e.name for e in top_entities[:50]]
                except Exception:
                    logger.warning("supervisor.schema_query_error", exc_info=True)

                # Update coordinator with current schema
                coordinator = CoordinatorService(
                    projections=projection_repo,
                    tasks=task_repo,
                    llm=llm,
                    entity_types=entity_types,
                    relationship_types=relationship_types,
                )

                # Dispatch manual directives (user-submitted via UI)
                async with pool.acquire() as conn:
                    manual_rows = await conn.fetch(
                        "SELECT task_id, directive, source_type, source_ref, max_scope "
                        "FROM tasks "
                        "WHERE engagement_id = $1 AND is_manual = TRUE AND status = 'queued' "
                        "ORDER BY created_at ASC",
                        engagement_id,
                    )
                if manual_rows:
                    manual_directives = [
                        TaskRecord(
                            task_id=r["task_id"],
                            engagement_id=engagement_id,
                            coordinator_id=None,
                            directive=r["directive"],
                            source_type=r["source_type"],
                            source_ref=r["source_ref"],
                            max_scope=r["max_scope"],
                        )
                        for r in manual_rows
                    ]
                    logger.info(
                        "supervisor.manual_directives",
                        count=len(manual_directives),
                    )
                    manual_results = await self._dispatch_workers(
                        directives=manual_directives,
                        engagement_id=engagement_id,
                        connectors=connectors,
                        entity_repo=entity_repo,
                        relationship_repo=relationship_repo,
                        observation_repo=observation_repo,
                        task_repo=task_repo,
                        embedder=embedder,
                        llm=llm,
                        event_bus=event_bus,
                        total_budget=total_budget,
                        entity_types=entity_types,
                        relationship_types=relationship_types,
                        entity_vocabulary=entity_vocabulary,
                    )
                    for wr in manual_results:
                        logger.info(
                            "supervisor.manual_worker_result",
                            worker_id=wr.worker_id,
                            entities=wr.entities_written,
                            error=wr.error,
                        )

                # Coordinator cycle
                cycle_result = await coordinator.run_cycle(
                    engagement_id=engagement_id,
                    coordinator_id=coordinator_id,
                    cycle_number=cycle_num,
                    last_cycle_at=last_cycle_at,
                    convergence_config=convergence_config,
                )

                if cycle_result.convergence_signal:
                    did_converge = True
                    await event_bus.emit(
                        ConvergenceReached(
                            engagement_id=engagement_id,
                            cycle_number=cycle_num,
                            final_ratio=cycle_result.cycle_stats.convergence_ratio,
                        )
                    )
                    logger.info("supervisor.converged", cycle=cycle_num)
                    break

                # Dispatch workers
                if cycle_result.directives:
                    worker_results = await self._dispatch_workers(
                        directives=cycle_result.directives,
                        engagement_id=engagement_id,
                        connectors=connectors,
                        entity_repo=entity_repo,
                        relationship_repo=relationship_repo,
                        observation_repo=observation_repo,
                        task_repo=task_repo,
                        embedder=embedder,
                        llm=llm,
                        event_bus=event_bus,
                        total_budget=total_budget,
                        entity_types=entity_types,
                        relationship_types=relationship_types,
                        entity_vocabulary=entity_vocabulary,
                    )

                    for wr in worker_results:
                        logger.info(
                            "supervisor.worker_result",
                            worker_id=wr.worker_id,
                            entities=wr.entities_written,
                            relationships=wr.relationships_written,
                            observations=wr.observations_written,
                            error=wr.error,
                        )

                await event_bus.emit(
                    CycleCompleted(
                        engagement_id=engagement_id,
                        cycle_number=cycle_num,
                        convergence_ratio=cycle_result.cycle_stats.convergence_ratio,
                        directives_generated=cycle_result.cycle_stats.directives_generated,
                    )
                )

                # Run consolidation if triggered (sequential — cross-links
                # must be visible to the next coordinator cycle)
                try:
                    cons_result = await consolidation.run(
                        engagement_id,
                        consolidation_config,
                    )
                    if cons_result is not None:
                        logger.info(
                            "supervisor.consolidation",
                            entities=cons_result.entities_consolidated,
                            cross_links=cons_result.cross_links_detected,
                            errors=len(cons_result.errors),
                        )
                except Exception:
                    logger.warning("supervisor.consolidation_error", exc_info=True)

                # Run post-cycle dedup sweep (after consolidation, before community)
                if self._settings.dedup_enabled:
                    try:
                        from alec.knowledge.dedup import run_dedup_sweep

                        dedup_result = await run_dedup_sweep(
                            engagement_id,
                            pool,
                            embedder,
                            auto_merge_threshold=self._settings.dedup_auto_merge_threshold,
                        )
                        if dedup_result.auto_merged > 0 or dedup_result.candidates_logged > 0:
                            logger.info(
                                "supervisor.dedup_sweep",
                                pairs_evaluated=dedup_result.pairs_evaluated,
                                auto_merged=dedup_result.auto_merged,
                                candidates_logged=dedup_result.candidates_logged,
                                errors=len(dedup_result.errors),
                            )
                    except Exception:
                        logger.warning("supervisor.dedup_error", exc_info=True)

                # Run community detection (post-consolidation)
                try:
                    from alec.knowledge.community import run_community_detection

                    comm_result = await run_community_detection(
                        engagement_id, cycle_num, pool
                    )
                    if comm_result:
                        logger.info(
                            "supervisor.community_detection",
                            communities=comm_result.community_count,
                            hubs=len(comm_result.hub_entities),
                            bridges=len(comm_result.bridge_entities),
                        )
                        await event_bus.emit(
                            CommunityDetected(
                                engagement_id=engagement_id,
                                cycle_number=cycle_num,
                                community_count=comm_result.community_count,
                                hub_count=len(comm_result.hub_entities),
                                bridge_count=len(comm_result.bridge_entities),
                            )
                        )
                except Exception:
                    logger.warning("supervisor.community_detection_error", exc_info=True)

                last_cycle_at = datetime.now(timezone.utc)

            # Stop the periodic heartbeat
            heartbeat_stop.set()
            await heartbeat_task

            # Mark engagement as completed/converged
            final_status = "converged" if did_converge else "completed"
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE engagements SET status = $1, updated_at = NOW(), "
                    "last_heartbeat = NOW() WHERE engagement_id = $2",
                    final_status,
                    engagement_id,
                )

            # Final summary
            async with pool.acquire() as conn:
                entity_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM entities WHERE engagement_id = $1",
                    engagement_id,
                )
                rel_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM relationships WHERE engagement_id = $1",
                    engagement_id,
                )
                obs_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM observations WHERE engagement_id = $1",
                    engagement_id,
                )

            # Generate HTML report
            try:
                actual_report_path = await generate_report(
                    pool,
                    engagement_id,
                    report_path,
                )
            except Exception:
                logger.warning("supervisor.report_error", exc_info=True)
                actual_report_path = None

            summary = {
                "engagement_id": str(engagement_id),
                "entities": entity_count,
                "relationships": rel_count,
                "observations": obs_count,
                "budget": total_budget.summary(),
                "report": actual_report_path,
            }
            logger.info("supervisor.complete", **summary)
            return summary

        finally:
            # Ensure heartbeat loop is stopped on any exit path
            heartbeat_stop.set()
            if not heartbeat_task.done():
                await heartbeat_task

            # Clean up connectors (e.g., close aiohttp sessions)
            for connector in connectors.values():
                close_fn = getattr(connector, "close", None)
                if close_fn is not None and callable(close_fn):
                    try:
                        await close_fn()
                    except Exception:
                        logger.warning("supervisor.connector_close_error", exc_info=True)

    @staticmethod
    def _connector_key(source_type: str, config: dict[str, Any]) -> str:
        """Derive the connector key from source_type and config.

        Matches the format used when building connectors: "type:ref".
        """
        if source_type == "local_files":
            return f"local_files:{config.get('base_path', '')}"
        elif source_type == "web":
            return f"web:{config.get('seed_url', '')}"
        else:
            return f"{source_type}:{config.get('ref', '')}"

    @staticmethod
    async def _refresh_connectors(
        pool: asyncpg.Pool,
        engagement_id: UUID,
        connectors: dict[str, SourceConnector],
        registry: ConnectorRegistry,
    ) -> None:
        """Sync connectors dict with source_configs table.

        Creates connectors for newly added sources and removes connectors
        for sources that have been deleted or disabled.
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source_type, config FROM source_configs "
                "WHERE engagement_id = $1 AND status = 'verified'",
                engagement_id,
            )

        # Build set of expected keys from DB
        db_keys: dict[str, tuple[str, dict[str, Any]]] = {}
        for row in rows:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            source_type = row["source_type"]
            key = Supervisor._connector_key(source_type, config)
            db_keys[key] = (source_type, config)

        # Add new sources
        for key, (source_type, config) in db_keys.items():
            if key not in connectors:
                try:
                    connectors[key] = registry.create(source_type, config)
                    logger.info("supervisor.connector_added", key=key)
                except Exception:
                    logger.warning(
                        "supervisor.connector_create_error",
                        key=key,
                        exc_info=True,
                    )

        # Remove connectors for sources no longer in DB
        removed_keys = [k for k in connectors if k not in db_keys]
        for key in removed_keys:
            connector = connectors.pop(key)
            close_fn = getattr(connector, "close", None)
            if close_fn is not None and callable(close_fn):
                try:
                    await close_fn()
                except Exception:
                    logger.warning("supervisor.connector_close_error", key=key, exc_info=True)
            logger.info("supervisor.connector_removed", key=key)

    def _match_connector(
        self,
        directive: TaskRecord,
        connectors: dict[str, SourceConnector],
    ) -> SourceConnector:
        """Match a directive to a connector.

        Priority: exact "type:ref" match → type match → first available.
        """
        exact_key = f"{directive.source_type}:{directive.source_ref}"
        if exact_key in connectors:
            return connectors[exact_key]

        # Type match
        for key, connector in connectors.items():
            if connector.source_type() == directive.source_type:
                return connector

        # Fallback to first available
        return next(iter(connectors.values()))

    async def _dispatch_workers(
        self,
        directives: list[TaskRecord],
        engagement_id: UUID,
        connectors: dict[str, SourceConnector],
        entity_repo: EntityRepository,
        relationship_repo: RelationshipRepository,
        observation_repo: ObservationRepository,
        task_repo: TaskRepository,
        embedder: EmbeddingService,
        llm: LLMClient,
        event_bus: EventBus,
        total_budget: BudgetTracker,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
        entity_vocabulary: list[str] | None = None,
    ) -> list[WorkerResult]:
        """Dispatch workers concurrently, capped at max_workers."""
        tasks = []
        for directive in directives[: self._settings.max_workers]:
            worker_id = f"worker-{directive.task_id.hex[:8]}"

            await task_repo.assign(directive.task_id, worker_id)

            await event_bus.emit(
                WorkerDispatched(
                    engagement_id=engagement_id,
                    task_id=directive.task_id,
                    worker_id=worker_id,
                    directive=directive.directive[:200],
                )
            )

            connector = self._match_connector(directive, connectors)

            graph = GraphWriter(
                engagement_id=engagement_id,
                model_id=None,
                worker_id=worker_id,
                source_ref=directive.source_ref,
                entities=entity_repo,
                relationships=relationship_repo,
                observations=observation_repo,
                embedder=embedder,
                similarity_threshold=self._settings.entity_similarity_threshold,
            )

            worker_budget = BudgetTracker(
                max_tokens=self._settings.worker_max_tokens,
            )

            worker = WorkerService(
                llm=llm,
                connector=connector,
                graph=graph,
                budget=worker_budget,
                event_bus=event_bus,
                max_turns=self._settings.worker_max_turns,
                entity_types=entity_types,
                relationship_types=relationship_types,
                entity_vocabulary=entity_vocabulary,
            )

            tasks.append(
                self._run_worker_task(
                    worker,
                    directive,
                    task_repo,
                    total_budget,
                    worker_budget,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        worker_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("supervisor.worker_exception", error=str(r))
            elif isinstance(r, WorkerResult):
                worker_results.append(r)

        return worker_results

    async def _run_worker_task(
        self,
        worker: WorkerService,
        directive: TaskRecord,
        task_repo: TaskRepository,
        total_budget: BudgetTracker,
        worker_budget: BudgetTracker,
    ) -> object:
        """Run a single worker and update task status."""

        try:
            result = await worker.run(directive)

            # Update task status
            if result.error:
                await task_repo.fail(directive.task_id, result.error)
            else:
                await task_repo.complete(
                    directive.task_id,
                    {
                        "entities_written": result.entities_written,
                        "relationships_written": result.relationships_written,
                        "observations_written": result.observations_written,
                        "scope_overflow": result.scope_overflow,
                        "tokens_used": result.tokens_used,
                    },
                )

            # Accumulate to total budget
            try:
                await total_budget.record(worker_budget.tokens_used, 0)
            except BudgetExhaustedError:
                pass  # Total budget warning, don't crash individual worker

            return result

        except Exception as e:
            await task_repo.fail(directive.task_id, str(e))
            raise

    def _handle_shutdown(self) -> None:
        logger.info("supervisor.shutdown_signal")
        self._shutdown = True
