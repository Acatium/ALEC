# Design Documents — Archive Note

**Date:** 2026-02-22
**Context:** These documents were created during v5 planning (2026-02-07 through 2026-02-20) as architectural vision and buildable specifications. The implementation has since evolved beyond what was planned in several areas, and some planned features remain unbuilt.

This file maps each document's sections to their implementation status.

---

## ALEC_v5_design.md (~3800 lines)

The original architectural vision. Contains strategic thinking, design rationale, and feature specifications.

| Section | Topic | Status |
|---------|-------|--------|
| 1. Commercial Framing | Value proposition, competitive differentiation | **Current** — strategic framing unchanged |
| 2. Product Vision | "Discovery Intelligence" definition | **Current** — core vision unchanged |
| 3. Architecture | Blackboard pattern, coordination loop, convergence | **Implemented** — core loop works as designed. Manual directive dispatch added (not in original design). Coordinator now receives user annotations, questions, and source trust tiers |
| 4. Three-Tier Memory | Observations → entities → consolidated units | **Implemented** — schema matches. Note: vectors are 384-dim (all-MiniLM-L6-v2), not 1536-dim as originally designed |
| 5. Communication & Runtime | In-process + Postgres, supervisor, engagement model | **Implemented** — matches design closely |
| 6. Tool Registry & Source Access | SourceConnector protocol, source configuration | **Implemented** — local_files and web connectors built |
| 7. Developer Pipeline | Code generation, validation, sandbox execution | **Not implemented** — tables exist in schema but no runtime code. Future feature |
| 8. Agent Types & Prompt Governance | APR, Configure Agent, Query Agent, Ontology Agent | **Not implemented** — only Coordinator and Worker agents exist. APR/governance tables in schema but unused. Future feature |
| 9. Context Management | Context windows, handoff protocol, max_scope | **Partially implemented** — max_scope and worker budget exist. Advanced context pressure management not built |
| 10. Interface Design | UI mockups (Setup/Runtime/Inquiry modes) | **Superseded** — actual UI is significantly different. Living research workspace model with EngagementDashboard, SourceManager, QuestionsPanel, etc. Design mockups describe Chat/Query and Prompt Management panels that don't exist |
| 11. Application Layout | Directory structure, module map, DB schema, API inventory | **Significantly diverged** — planned 9 route files and ~70 endpoints; actual is 4 route files and ~38 endpoints. Frontend structure is flat (21 components + 3 pages) vs planned nested hierarchy. DB schema now has 22 tables (5 added: user_annotations, questions, snapshots, community_analysis, engagement_schema) |
| 12. Ontology Alignment | Cross-model alignment as core insight | **Schema exists, minimally used** — models and alignments tables present but the multi-model workflow isn't the primary usage pattern yet. The insight is architecturally sound |
| 13. Generalization Architecture | Platform vs domain separation, engagement templates | **Partially implemented** — engagement_schema table exists with per-engagement entity/relationship type definitions, templates (general_discovery, etc.), and LLM-based schema proposals. Platform vs domain separation not yet formalized |
| 14. Ontology Agent | Dynamic schema evolution agent | **Not implemented** — entirely aspirational. Future feature |
| 15. Open Questions | 16 questions (8 technical, 3 product, 3 strategic, 1 open) | **Mostly resolved** — MCP integration remains open |
| Appendix A | Competitive comparison | **Current** — updated 2026-02-20 |
| Appendix B | Design decisions log | **Historical reference** — captures "why" decisions were made |

**Unique value to preserve:** Sections 1, 2, 3, 12 (architectural rationale). Sections 7, 8, 13, 14 (specs for unbuilt features).

---

## runtime_component_specs.md (~2850 lines)

Buildable specifications for core runtime components. The closest document to implementation guidance.

| Section | Topic | Status |
|---------|-------|--------|
| 1. Coordinator Cycle | Projection building, convergence checking, directive generation | **Implemented** — actual `coordinator.py` and `projections.py` follow this pattern. Projection includes trust tiers, annotations, and questions sections. Enhanced convergence metric (novelty decay, per-source tracking, expansion deceleration) implemented via settings |
| 2. Worker Tool-Use Loop | Source/graph tools, worker prompt, GraphWriter, drift detection | **Implemented** — `worker.py` and `graph_writer.py` closely follow spec. Drift detection (dedup, retry limits, scope drift flags) implemented in `alec/runtime/drift.py` and integrated into worker loop |
| 3. Consolidation Process | Stale entity detection, synthesis, cross-link detection | **Partially implemented** — `consolidation.py` exists and runs post-cycle, but the full synthesis prompt and cross-link detection are simpler than specified |
| 4. Component Interaction | Supervisor class, data flow, LLM budget | **Implemented** — `supervisor.py` follows this pattern. Now includes manual directive dispatch at cycle start (not in spec) |
| 5. Community Detection | Louvain/Leiden for topic clusters | **Implemented** — community_analysis table in schema, Louvain algorithm in `alec/knowledge/community.py`, integrated into supervisor post-cycle flow, publishes CommunityDetected events |

**Unique value to preserve:** Section 3 (full consolidation spec — current implementation is simpler than specified). Sections 1.4, 2.7, and 5 have been implemented and can serve as reference for the original design intent.

---

## design_validation.md (~870 lines)

155 user stories across 6 personas with gap analysis.

| Section | Topic | Status |
|---------|-------|--------|
| 1. Methodology | 155 stories, 6 personas | **Reference** — still valid as a coverage test |
| 2. Summary | 102 fully covered, 20 partial, 33 gaps | **Partially stale** — some gaps have been addressed by implementation but the doc isn't updated |
| 3. Full Gaps (33 gaps) | Detailed gap analysis by category | **Partially addressed** — e.g., GAP-E2 (cascade delete) is now implemented; GAP-I6 (export) partially addressed by report generation; GAP-E8 (empty state UX) addressed by frontend components. Many gaps (GAP-G1-G6 governance, GAP-C1-C4 configuration) remain valid |
| 4-6. Partial Gaps, Strengths, Recommendations | Coverage analysis | **Still relevant** — recommendations remain a useful roadmap |
| 7. User Story Reference | 155 stories organized by persona | **High value** — use as a feature checklist for future development |
| 8. Design Decisions | Convergence, drift detection, community detection | **Still relevant** — these decisions are tracked in CLAUDE.md |

**Unique value to preserve:** The 155 user stories (Section 7) and the prioritized recommendations (Section 6) serve as a development roadmap.

---

## market_validation.md (~150 lines)

Market research and competitive positioning. Created 2026-02-20.

| Section | Topic | Status |
|---------|-------|--------|
| 1. Architecture Validation | arXiv + industry precedent | **Current** |
| 2. Competitive Landscape | Zep, Hebbia, Glean comparisons | **Current** (may need periodic refresh) |
| 3. Market Positioning | Compliance/provenance lead, beachhead verticals | **Current** |
| 4. Strategic Implications | Feature priorities, MCP consideration | **Partially stale** — states "UI/admin panel: Defer" but the UI is now fully implemented with 21 components, schema editor, community detection, etc. |

**Unique value:** This is the only document containing market research and competitive intelligence. Keep and periodically refresh.

---

## Summary

| Document | Keep? | Why |
|----------|-------|-----|
| `ALEC_v5_design.md` | Yes (archive) | Architectural rationale, unbuilt feature specs (developer pipeline, APR, ontology agent, generalization) |
| `runtime_component_specs.md` | Yes (archive) | Buildable specs for unbuilt features (enhanced convergence, drift detection, full consolidation, community detection) |
| `design_validation.md` | Yes (archive) | 155 user stories as feature checklist, gap analysis as roadmap |
| `market_validation.md` | Yes (keep current) | Only source of market research and competitive intelligence |

For current system documentation, see **`CLAUDE.md`** (development context) and **`README.md`** (project overview).
