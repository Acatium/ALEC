# Test Framework Audit — Action Report

**Date:** 2026-02-22
**Branch:** v5
**Scope:** Full examination of `tests/` for best practice compliance and impact on project quality

---

## Current State

**253 passing, 6 failing, 1 skipped** across 36 test files (~6,000 lines of test code).

The 6 failures are all in `tests/integration/test_api.py` caused by schema drift — the `engagements.py` route now inserts a `summary` column that exists in `schema.sql` but the running test database hasn't been migrated. There is no migration tooling; schema changes require manual `ALTER TABLE` or full database recreation.

---

## Structure

Four-tier pyramid, correctly shaped:

| Tier | Files | Tests | DB | LLM | Speed |
|------|-------|-------|----|-----|-------|
| Unit | 23 | ~155 | No | No | <2s total |
| Integration | 9 | ~60 | Real PG | No | ~8s total |
| Component | 3 | ~8 | Real PG | MockLLM | ~2s total |
| Smoke | 1 | 1 | Real PG | Real API | Minutes, skipped by default |

Wide base of fast isolated tests, narrow top of slow realistic tests. This is correct.

---

## Strengths

### 1. Test isolation is excellent
Every test creates its own data via fixtures. The `clean_db` fixture deletes all rows in FK-safe order before *and* after each test. No shared state, no ordering dependencies, no flakiness from test pollution.

### 2. Mocking is appropriate per tier
Unit tests mock DB and network. Integration tests use real Postgres. Component tests use real Postgres + `MockLLMClient` with scripted FIFO responses. No over-mocking at any tier. The component tier (MockLLM + real DB) is particularly well-designed — it catches integration bugs without requiring an API key.

### 3. The convergence signal pipeline is thoroughly tested
This is the most critical business logic path, and it's well-defended:
- `test_graph_writer.py` — expansion vs. reinforcement observations created correctly
- `test_projections.py` — anti-gaming caps, per-source ratios, expected contradiction exclusion
- `test_convergence.py` — novelty decay formula mathematical properties
- `test_ranking.py` — annotation modifiers and trust tier multipliers stack correctly

### 4. Entity resolution has excellent coverage
Exact match → fuzzy match → create-new paths all tested, including the local cache layer that skips DB lookups on repeat encounters. Cache vs. DB rediscovery distinction is verified.

### 5. Test naming is descriptive and consistent
Names document expected behavior: `test_exact_name_match_returns_existing_entity`, `test_convergence_anti_gaming_cap`, `test_service_per_entity_error_isolation`. Tests serve as living documentation.

### 6. Consolidation versioning tested end-to-end
`test_consolidation.py` (component) verifies: first run creates v1 with status `current`, second run after more observations creates v2 and marks v1 `stale`. Cross-link detection (co-occurrence without explicit relationship) also covered.

---

## Problems

### P1. Schema drift breaks API tests (6 failures)

**Severity: High — tests are broken right now**

The `engagements.py` route inserts a `summary` column. `schema.sql` declares it. But the test database hasn't been migrated. Root cause: there is no migration tooling. Every schema change requires either manual `ALTER TABLE` against the running DB or full recreation.

**Fix:** Rebuild the test database from `schema.sql`, then implement a migration strategy (either numbered SQL files, Alembic, or a `schema_version` table with idempotent migrations).

### P2. Research workspace has zero API test coverage

**Severity: High — 18 endpoints completely untested**

`alec/api/routes/research.py` implements the core "living research workspace" feature: annotations CRUD, questions CRUD, entity corrections, entity merge (atomic transaction with relationship reassignment), manual directives, snapshots, source management, and report generation. None of these are tested at the API level.

The `test_api.py` fixture doesn't even mount the `research` router:
```python
app.include_router(engagements_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
# research_router: missing
```

Entity merge is the highest-risk untested operation — it reassigns relationships and observations, sums counts, merges aliases/properties, and deletes the source entity, all in a single transaction.

### P3. API tests are shallow even where they exist

**Severity: Medium**

The 8 existing API tests only verify: empty lists return `[]`, create returns `active`, get returns the created record, and 404 for nonexistent IDs. Missing:
- Mutation endpoints: PATCH, DELETE, restart, analyze
- Knowledge detail endpoints: entity detail, timeline, stats, consolidated
- Negative paths: invalid JSON → 422, malformed UUIDs, missing required fields
- Data persistence verification: create entity, then GET and verify it persists

### P4. No error/negative path testing at any API boundary

**Severity: Medium**

No tests verify that invalid inputs produce proper 422 responses instead of 500s. No tests for: type mismatches, empty required strings, out-of-range values, or duplicate creates. Users interact exclusively through the API — the HTTP boundary is the untested surface.

### P5. No concurrency tests

**Severity: Medium**

The architecture supports `max_workers=5` concurrent workers per cycle. There are no tests verifying that concurrent workers don't create duplicate entities via race conditions in entity resolution, corrupt shared state, or deadlock on database resources.

### P6. Smoke test provides minimal confidence

**Severity: Low**

The single smoke test runs 2 cycles and only asserts `entities > 0` and `observations > 0`. For a test that requires a real API key and takes significant time/cost to run, it should verify more: convergence detection, consolidation fires, report generates, correct event sequence.

---

## Missing Patterns

### No test coverage measurement
No `pytest-cov` in dependencies, no coverage configuration. Without coverage data, blind spots are invisible to developers. Add `pytest-cov` to dev dependencies and configure a minimum threshold.

### No parameterized tests
Functions with enumerable inputs (trust tiers: 3 values, annotation types: 5 values, source types: 2+) would benefit from `@pytest.mark.parametrize`. Example: `test_ranking.py` has 13 separate functions that could be 3 parameterized tests with less code and wider input coverage.

### No property-based testing
Entity resolution, convergence math, and ranking involve numeric algorithms where [Hypothesis](https://hypothesis.readthedocs.io/) could find edge cases (negative counts, empty strings, extreme floats) that hand-crafted tests miss.

### No markers beyond `smoke`
No way to selectively run DB-dependent tests vs. pure unit tests except by directory path. Markers like `@pytest.mark.db` would allow finer-grained CI selection (e.g., run unit-only on every push, DB tests on PR merge).

---

## Action Items

### Priority 1 — Fix what's broken

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1.1 | Rebuild test database from current `schema.sql` to fix the 6 API test failures | 5 min | Unblocks CI |
| 1.2 | Add migration strategy (numbered SQL files or `schema_version` table) to prevent recurrence | 2–4 hr | Prevents future schema drift |

### Priority 2 — Cover the highest-risk untested surface

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 2.1 | Add research router to `test_api.py` fixture, write tests for entity merge endpoint (atomic transaction correctness) | 2–3 hr | Highest-risk untested operation |
| 2.2 | Add tests for annotations CRUD, questions CRUD, directives POST | 2–3 hr | Core user-facing feature |
| 2.3 | Add tests for source management endpoints (add, update priority/trust_tier, delete) | 1–2 hr | Source trust tiers feed into coordinator |
| 2.4 | Add tests for snapshot and report generation endpoints | 1–2 hr | User-visible outputs |
| 2.5 | Add negative path tests: invalid payloads → 422, malformed UUIDs → 422, missing fields → 422 | 2 hr | Prevents silent 500s in production |

### Priority 3 — Strengthen confidence

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 3.1 | Add `pytest-cov` to dev dependencies, configure minimum threshold (start at 60%, raise over time) | 30 min | Visibility into blind spots |
| 3.2 | Add concurrency test: 3 workers writing to same engagement simultaneously, verify no duplicate entities | 2–3 hr | Race condition detection |
| 3.3 | Expand smoke test: verify convergence detection triggers, consolidation runs, report generates | 1–2 hr | End-to-end confidence |
| 3.4 | Add `@pytest.mark.db` marker to integration/component tests for selective CI execution | 30 min | CI flexibility |

### Priority 4 — Improve ergonomics

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 4.1 | Convert `test_ranking.py` to parameterized tests (reduce 13 tests → 3 parameterized) | 1 hr | Less code, wider input coverage |
| 4.2 | Change `db_pool` fixture scope to `session` for integration tests (reduces ~200ms overhead per test) | 30 min | Faster integration suite |
| 4.3 | Add Hypothesis property tests for convergence math and ranking score formulas | 2 hr | Edge case discovery |

---

## Per-File Quality Grades

### Unit Tests

| File | Grade | Notes |
|------|-------|-------|
| test_budget.py | A | Simple, correct, complete |
| test_community.py | A | Thorough cluster/hub/bridge coverage |
| test_config.py | B+ | Missing invalid-value edge cases |
| test_connector_registry.py | A- | Missing duplicate registration test |
| test_consolidation_domain.py | A- | Good dataclass verification |
| test_consolidation_service.py | A+ | Excellent mocking, error isolation tested |
| test_convergence.py | A | Mathematical invariants verified |
| test_domain.py | A- | Missing empty-list ranking edge case |
| test_dynamic_prompts.py | A | Mutation isolation, truncation tested |
| test_embeddings.py | A | Determinism, normalization, dimensionality |
| test_embeddings_st.py | B+ | Correct but mirrors mock tests closely |
| test_entity_resolution.py | A+ | Cache, fuzzy, exact paths all covered |
| test_event_bus.py | A | Error isolation, type isolation, immutability |
| test_html_report.py | A- | Good but helper could become fragile |
| test_local_files.py | A | Path traversal attack tested |
| test_mock_llm.py | A- | Tests the mock itself — good practice |
| test_ranking.py | A+ | 13 cases cover all modifier/multiplier combos |
| test_schema_proposer.py | A- | JSON extraction edge cases covered |
| test_setup_analyzer.py | A+ | HTTP mock, fallback, dedup all tested |
| test_source_config.py | A | URL inference, empty validation |
| test_templates.py | A- | SQL execution count verified |
| test_web_connector.py | A | Link extraction, caching, domain filtering |
| test_worker_drift.py | A+ | Boundary threshold, hash determinism, retry limits |

### Integration Tests

| File | Grade | Notes |
|------|-------|-------|
| test_pool.py | B | Infrastructure-only, doesn't verify constraints |
| test_entity_repo.py | A | Case-insensitive matching, alias resolution |
| test_relationship_repo.py | A | Evidence accumulation, GREATEST confidence |
| test_observation_repo.py | B+ | Missing ordering verification |
| test_graph_writer.py | A+ | Convergence signal pipeline fully verified |
| test_web_connector.py | A- | Good but uses local server, not real network |
| test_consolidation_repo.py | A+ | Cross-link detection, versioning, status transitions |
| test_projections.py | A+ | Anti-gaming, per-source ratios, contradiction exclusion |
| test_api.py | D | 6 failures, shallow, missing 30+ endpoints |

### Component Tests

| File | Grade | Notes |
|------|-------|-------|
| test_worker.py | A | Full tool-use loop verified with real DB |
| test_coordinator.py | A- | Empty-state optimization verified, but only 2 tests |
| test_consolidation.py | A+ | Version management, cross-links end-to-end |

### Smoke Tests

| File | Grade | Notes |
|------|-------|-------|
| test_full_loop.py | C+ | Runs but assertions are minimal |

---

## Bottom Line

The knowledge pipeline (entity resolution → graph writing → convergence → consolidation) is **well-defended by tests**. The ranking, drift detection, and community detection algorithms have thorough unit coverage with correct mathematical assertions.

The critical gap is the **API layer**: the HTTP boundary through which all user interaction flows. The research workspace — the project's core differentiating feature — has zero test coverage at the API tier. The 6 currently-broken tests demonstrate that schema changes can silently break the API test suite with no guardrails.

**Recommended sequence:** Fix the schema drift (P1), then write research workspace API tests (P2), then add coverage measurement (P3.1) to guide remaining work.
