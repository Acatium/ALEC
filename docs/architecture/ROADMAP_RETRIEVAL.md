# Retrieval Enhancement Roadmap

This document captures learnings from analyzing [Hindsight](https://github.com/vectorize-io/hindsight), a competing agent memory system that achieves state-of-the-art results on long-horizon memory benchmarks.

**Reference:** [arXiv 2512.12818](https://arxiv.org/abs/2512.12818) - Hindsight achieves 83.6% on LongMemEval (vs 39% baseline) through structured memory + multi-strategy retrieval.

---

## Current ALEC Limitations

### 1. Single Retrieval Strategy
ALEC uses vector similarity (pgvector) + graph paths (solved_by edges). This misses:
- Exact keyword matches that embeddings don't capture
- Temporal relationships between memories
- Entity-based connections

### 2. No Evidence vs Inference Distinction
All ALEC bullets are "advice to follow" - no distinction between:
- Facts ("The API uses offset pagination")
- Experiences ("When I tried X, Y happened")
- Beliefs ("I think cursor pagination is better" with confidence)
- Observations ("Multiple APIs share this pattern")

### 3. No Reflection Mechanism
ALEC's STRATEGIST fills knowledge gaps but doesn't:
- Analyze existing bullets to form meta-patterns
- Create new memories from reflecting on old memories
- Build higher-order observations across similar bullets

---

## Recommended Enhancements (Priority Order)

### 1. BM25 Keyword Retrieval
**Effort:** Low (1-2 days) | **Impact:** High

PostgreSQL supports `tsvector` full-text search. Adding BM25 as a second retrieval path catches terms that embeddings miss.

**Implementation:**
```sql
-- Add tsvector column
ALTER TABLE playbook_bullets ADD COLUMN content_tsv tsvector;
CREATE INDEX idx_bullets_tsv ON playbook_bullets USING GIN(content_tsv);

-- Populate and maintain
UPDATE playbook_bullets SET content_tsv = to_tsvector('english', content);
CREATE TRIGGER bullets_tsv_update BEFORE INSERT OR UPDATE ON playbook_bullets
  FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(content_tsv, 'pg_catalog.english', content);
```

**Retrieval change:**
1. Run vector search (existing)
2. Run BM25 search: `WHERE content_tsv @@ plainto_tsquery('english', query)`
3. Merge via reciprocal rank fusion: `score = sum(1 / (k + rank))` for each result

### 2. Category-Aware Retrieval
**Effort:** Medium | **Impact:** Medium

ALEC already has categories (constraints, solutions, cheat_sheets, examples, meta_prompts). These could map to Hindsight's memory types:

| Hindsight | ALEC Category | Retrieval Priority |
|-----------|---------------|-------------------|
| World (facts) | cheat_sheets | Show first (grounding) |
| Experience | examples | Show for similar tasks |
| Opinion | constraints, solutions | Show with confidence |
| Observation | meta_prompts | Show for reasoning |

**Implementation:**
- Modify ADVISOR to group bullets by category
- Show cheat_sheets first (factual grounding)
- Then relevant solutions/constraints
- Add effectiveness score as "confidence" indicator

### 3. Reflection Service
**Effort:** Medium (1 week) | **Impact:** High

Extend STRATEGIST to analyze existing bullets (not just gaps):

**New capability:**
1. Find clusters of similar bullets (by assertion_embedding)
2. Identify patterns: "5 bullets mention _privates() methods"
3. Create meta-observation: "Spotify hides sensitive data behind _privates() variants"

**Implementation:**
```python
async def _reflect_on_bullets(self):
    """Analyze existing bullets to form meta-observations."""
    # Group similar bullets
    clusters = await self._cluster_bullets_by_assertion()

    for cluster in clusters:
        if len(cluster) >= 3:
            # LLM call to synthesize pattern
            observation = await self._synthesize_observation(cluster)
            if observation:
                # Store as meta_prompt category
                await self._store_observation(observation)
```

**Trigger:** Periodic (daily) or after N new bullets added.

### 4. Entity Extraction
**Effort:** High (2+ weeks) | **Impact:** Medium

Extract API/method names as entities and link related ones.

**Schema additions:**
```sql
CREATE TABLE entities (
    entity_id UUID PRIMARY KEY,
    name TEXT NOT NULL,  -- e.g., "show_song"
    entity_type TEXT,    -- "api_method", "field", "class"
    canonical_name TEXT, -- normalized form
    metadata JSONB
);

CREATE TABLE entity_mentions (
    mention_id UUID PRIMARY KEY,
    entity_id UUID REFERENCES entities,
    bullet_id UUID REFERENCES playbook_bullets,
    context TEXT  -- snippet around mention
);

CREATE TABLE entity_relations (
    relation_id UUID PRIMARY KEY,
    source_entity UUID REFERENCES entities,
    target_entity UUID REFERENCES entities,
    relation_type TEXT  -- "variant_of", "returns", "parameter_of"
);
```

**Extraction in REFLECTOR:**
- Use regex + LLM to identify API names, method calls, field accesses
- Create entities for new names
- Link variants: show_song ↔ show_song_privates

**Retrieval enhancement:**
- When query mentions "show_song", also retrieve bullets about related entities

---

## Benchmark Considerations

### LongMemEval vs AppWorld

Hindsight's benchmarks (LongMemEval, LoCoMo) test **long-horizon, cross-session memory** - recalling information from hours/days of conversation.

AppWorld tests **single-session, task-specific API navigation** - different requirements:
- LongMemEval needs sophisticated retrieval across large memory stores
- AppWorld needs specific API gotchas, not long-term recall

**Implication:** ALEC's simpler architecture may be sufficient for AppWorld. Retrieval enhancements matter more if we expand to general agent memory.

---

## Implementation Priority

| Phase | Enhancement | When to Implement |
|-------|-------------|-------------------|
| Current | Memory quality tightening | Now (completed) |
| Next | BM25 keyword retrieval | After validating quality improvements |
| Future | Reflection service | If cross-bullet patterns emerge |
| Future | Entity extraction | If cross-task transfer is needed |
| Future | Category-aware retrieval | If bullet count grows significantly |

---

## Metrics to Track

Before implementing enhancements, establish baselines:
- **Recall precision:** % of retrieved bullets that help
- **Coverage:** % of tasks where relevant bullets exist but weren't retrieved
- **Cross-task transfer:** Do bullets learned in task A help in task B?

These metrics will indicate which enhancements provide most value.

---

**Last Updated:** 2025-12-16
**Status:** Planning document - enhancements not yet implemented
