# AKU System Simplification: Schema + Terminology + Presentation

## Problem Statement

AKUs (Atomic Knowledge Units) ARE retrieved correctly but not FOLLOWED.

**Revised diagnosis after deep analysis:**
1. AKUs are verbose (avg 426 chars each)
2. Schema has 30+ fields, only ~12 are needed
3. modality/polarity/category don't differentiate (83% in one bucket)
4. Terminology inconsistent ("bullet" vs "AKU")

---

## Design Principle: Radical Simplification

**An AKU is just:** `trigger` → `action`

| Purpose | Field | Example |
|---------|-------|---------|
| Retrieval | `situation` (short) | `play_music()` |
| Display | `assertion` (short) | `check duration manually (doesn't validate)` |
| Learning | `helpful_count`, `harmful_count` | Thompson Sampling |

**Everything else is noise.**

---

## Terminology Standardization

**Current:** Mixed "bullet" and "AKU" terminology (~2,800 references)

| Category | "bullet" refs |
|----------|---------------|
| Python (core/) | 1,859 |
| Frontend | 308 |
| SQL | 267 |
| Docs | 375 |

**Standardize to "AKU" everywhere:**

| Current | New |
|---------|-----|
| `playbook_bullets` table | `akus` |
| `bullet_id` | `aku_id` |
| `bullet.accepted` event | `aku.accepted` |
| `bullet.merged` event | `aku.merged` |
| `bullets.requested` event | `akus.requested` |
| `session:{id}:bullets` Redis | `session:{id}:akus` |
| `bullet_formatter.py` | `aku_formatter.py` |
| `bullet_cache.py` | `aku_cache.py` |
| `bullets_shown` column | `akus_shown` |
| `bullets_helped` column | `akus_helped` |
| `bullets_harmed` column | `akus_harmed` |

---

## Target Schema

```sql
CREATE TABLE akus (
    aku_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Core content (SHORT)
    situation TEXT NOT NULL,           -- Trigger: "play_music()" (max 60 chars)
    assertion TEXT NOT NULL,           -- Action: "check duration manually" (max 100 chars)

    -- Embeddings
    situation_embedding VECTOR(384),
    assertion_embedding VECTOR(384),

    -- Learning counters
    helpful_count INT DEFAULT 0,
    harmful_count INT DEFAULT 0,
    neutral_count INT DEFAULT 0,
    evidence_count INT DEFAULT 1,

    -- State
    status VARCHAR(20) DEFAULT 'candidate',
    cluster_id UUID REFERENCES problem_clusters(cluster_id),
    source VARCHAR(50) DEFAULT 'reflector',
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Index for vector search
CREATE INDEX idx_akus_situation_embedding ON akus
USING ivfflat (situation_embedding vector_cosine_ops);
```

**14 fields (was 30+).**

---

## Implementation Phases

### Phase 0: Clean Slate
Delete all AKUs via `/system/reset/bullets` (endpoint renamed in Phase 9).

### Phase 1: Schema Migration
**File:** `alembic/versions/xxx_simplify_to_akus.py`

```sql
-- Rename table
ALTER TABLE playbook_bullets RENAME TO akus;

-- Rename primary key
ALTER TABLE akus RENAME COLUMN bullet_id TO aku_id;

-- Drop unused columns
ALTER TABLE akus
DROP COLUMN IF EXISTS modality,
DROP COLUMN IF EXISTS polarity,
DROP COLUMN IF EXISTS category,
DROP COLUMN IF EXISTS domain,
DROP COLUMN IF EXISTS content,
DROP COLUMN IF EXISTS embedding,
DROP COLUMN IF EXISTS problem_description,
DROP COLUMN IF EXISTS solution_description,
DROP COLUMN IF EXISTS problem_embedding,
DROP COLUMN IF EXISTS signal_type,
DROP COLUMN IF EXISTS usage_count,
DROP COLUMN IF EXISTS effectiveness_score,
DROP COLUMN IF EXISTS tags,
DROP COLUMN IF EXISTS proven_at,
DROP COLUMN IF EXISTS total_causal_credit,
DROP COLUMN IF EXISTS last_validated_at,
DROP COLUMN IF EXISTS last_used_at,
DROP COLUMN IF EXISTS updated_at;

-- Update session_turns columns
ALTER TABLE session_turns RENAME COLUMN bullets_shown TO akus_shown;
ALTER TABLE session_turns RENAME COLUMN bullets_helped TO akus_helped;
ALTER TABLE session_turns RENAME COLUMN bullets_harmed TO akus_harmed;

-- Update knowledge_edges references (target_id now refers to aku_id)
-- No column rename needed, just update where target_type = 'bullet' → 'aku'
UPDATE knowledge_edges SET target_type = 'aku' WHERE target_type = 'bullet';
```

### Phase 2: Update CURATOR
**File:** `core/learning_loop/curator/service.py`

- Rename functions: `_handle_aku_proposed()` (already named correctly)
- Change table reference: `playbook_bullets` → `akus`
- Change column: `bullet_id` → `aku_id`
- Remove modality/polarity validation
- Remove `_derive_category()` function
- Add length validation (situation ≤60, assertion ≤100)

### Phase 3: Update ADVISOR
**File:** `core/learning_loop/advisor/service.py`

- Table: `playbook_bullets pb` → `akus a`
- Column: `pb.bullet_id` → `a.aku_id`
- Variables: `bullets` → `akus`, `bullet_ids` → `aku_ids`
- Remove modality, polarity, category from SELECTs

### Phase 4: Update REFLECTOR
**File:** `core/learning_loop/reflector/service.py`

- Variables: `bullets_helped` → `akus_helped`, `bullets_harmed` → `akus_harmed`
- Event payloads: use new column names

### Phase 5: Update Extraction Prompts
**File:** `core/learning_loop/reflector/prompts_v2.py`

```python
AKU_EXTRACTION_SYNTHESIS = """
SYNTHESIZE:
If ALL answers above are SPECIFIC, output:

---AKU---
SITUATION: [Q2 method/field] for [Q1 goal - max 5 words]
ASSERTION: Use [Q3]. ([Q4 - max 10 words])
---END---

CONSTRAINTS:
- SITUATION max 60 characters
- ASSERTION max 100 characters
"""
```

**Also update:** `core/agents/strategist/prompts.py`

### Phase 6: Rename Session Files
```
core/session/domain/bullet_formatter.py → aku_formatter.py
core/session/infrastructure/bullet_cache.py → aku_cache.py
```

Update all imports.

### Phase 7: Update Session Domain
**File:** `core/session/domain/aku_formatter.py` (renamed)

```python
def format_akus_for_llm(akus: list[dict[str, Any]]) -> str:
    if not akus:
        return ""

    lines = ["TIPS:"]
    for aku in akus:
        assertion = aku.get("assertion", "")
        if assertion:
            lines.append(f"• {assertion}")

    return "\n".join(lines) if len(lines) > 1 else ""
```

**File:** `core/session/domain/conversation.py`

- Update system prompt
- Rename variables: `bullets` → `akus`

### Phase 8: Update Session Infrastructure
**File:** `core/session/infrastructure/aku_cache.py` (renamed)

- Redis keys: `session:{id}:akus`, `session:{id}:turn:{n}:akus`
- Variables: `bullets` → `akus`

### Phase 9: Update Kafka Events
**Files:** All Kafka producers/consumers

| Old Event | New Event |
|-----------|-----------|
| `bullets.requested` | `akus.requested` |
| `bullet.accepted` | `aku.accepted` |
| `bullet.merged` | `aku.merged` |
| `bullet.synthesized` | `aku.synthesized` |

### Phase 10: Update AKU Search Tool
**File:** `core/session/domain/aku_search.py`

- Already named correctly
- Remove polarity formatting
- Update table reference

### Phase 11: Update API Routes
**File:** `core/session/api/library_routes.py`

- Internal references: `bullet` → `aku`
- Keep `/library` endpoint path (good abstraction)

### Phase 12: Update Frontend
**Files:** `frontend/src/**/*.ts`, `frontend/src/**/*.tsx`

- Types: `Bullet` → `AKU`
- Variables: `bullets` → `akus`
- API response handling

### Phase 13: Update Tests
- All test files referencing bullets
- Fixtures, mocks, assertions

### Phase 14: Update Documentation
- CLAUDE.md
- ARCHITECTURE.md
- README files
- Code comments

---

## Files Summary

| Category | Files | Changes |
|----------|-------|---------|
| **Migration** | 1 | New alembic migration |
| **Learning Loop** | 5 | curator, advisor, reflector, clusterer, text_parser |
| **Session** | 6 | conversation, aku_formatter, aku_cache, aku_search, routes |
| **Agents** | 2 | strategist prompts, librarian |
| **Frontend** | ~15 | Types, components, API calls |
| **Tests** | ~30 | Fixtures, assertions |
| **Docs** | 5 | CLAUDE.md, ARCHITECTURE.md, READMEs |

---

## Token Impact

| Metric | Before | After |
|--------|--------|-------|
| Avg AKU size | 426 chars | ~80 chars |
| 10 AKUs in prompt | ~1000 tokens | ~150 tokens |
| **Savings** | | **~850 tokens/turn** |

---

## Presentation Format

**Before:**
```
RELEVANT KNOWLEDGE:

Solutions (#S):
- [1] `play_music(playlist_id=X)` plays the playlist but does NOT
  validate playlist duration against workout requirements - check
  total duration manually before starting.

Cheat Sheets (#R):
- [2] `show_song_queue()` returns songs in queue order...
```

**After:**
```
TIPS:
• Use manual duration check. (play_music() doesn't validate length)
• Use show_song_privates() for play_count. (show_song() returns 0)
```

---

## Success Metrics

1. **Schema simplicity** - 14 fields (was 30+)
2. **Terminology consistency** - "AKU" everywhere
3. **Token efficiency** - <200 tokens for 10 AKUs
4. **AKU follow-through** - LLM acts on tips shown

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Large rename scope | Systematic find-replace, run tests after each phase |
| Schema migration | Clean slate = no data to migrate |
| Kafka event rename | Deploy consumers first, then producers |
| Frontend breaks | TypeScript will catch type mismatches |

---

## Key Insight

**The ontology was classification theater.**

modality × polarity × category = 18 theoretical combinations
Actual distribution: 83% in ONE bucket (do/should/solutions)

Removing them doesn't lose information - it removes noise.
Standardizing to "AKU" clarifies what these entities actually are: Atomic Knowledge Units.

---

## Phase 13: Test Coverage Changes (Detailed)

### Test Inventory

| Test Category | Files | "bullet" refs | Scope |
|---------------|-------|---------------|-------|
| Session Unit | 7 | 238 | Formatter, cache, conversation |
| Learning Loop Unit | 8 | 350 | Advisor, curator, reflector, clusterer |
| Learning Loop Integration | 7 | 379 | Thompson sampling, event flows, SQL |
| E2E | 7 | 144 | Full stack tests |
| **Total** | **29** | **1,111** | |

### 13.1 File Renames

| Current | New |
|---------|-----|
| `core/session/tests/unit/test_bullet_formatter.py` | `test_aku_formatter.py` |

### 13.2 Unit Test Updates by Service

#### CURATOR Tests (`core/learning_loop/tests/unit/test_curator_handler.py`)

**Tests to REMOVE:**
```python
class TestDeriveCategory:  # DELETE ENTIRE CLASS
    """Tests for _derive_category method."""
    def test_dont_polarity_is_constraints(...)   # polarity removed
    def test_know_polarity_is_cheat_sheets(...)  # polarity removed
    def test_do_polarity_is_solutions(...)       # polarity removed
    def test_missing_polarity_defaults_to_solutions(...)
```

**Tests to MODIFY:**
```python
class TestQualityCheck:
    def test_rejects_invalid_modality(...)  # DELETE - modality removed
    def test_rejects_invalid_polarity(...)  # DELETE - polarity removed
```

**Tests to ADD:**
```python
class TestLengthValidation:
    """New tests for situation/assertion length constraints."""

    def test_rejects_situation_over_60_chars(self, curator_service):
        """Situation > 60 chars should be rejected."""
        aku = {
            "situation": "A" * 61,  # 61 chars - too long
            "assertion": "Valid short assertion here",
        }
        result = curator_service._quality_check(aku)
        assert result is not None
        assert "situation_too_long" in result

    def test_rejects_assertion_over_100_chars(self, curator_service):
        """Assertion > 100 chars should be rejected."""
        aku = {
            "situation": "Valid situation",
            "assertion": "A" * 101,  # 101 chars - too long
        }
        result = curator_service._quality_check(aku)
        assert result is not None
        assert "assertion_too_long" in result

    def test_accepts_max_length_content(self, curator_service):
        """Exactly 60/100 chars should pass."""
        aku = {
            "situation": "A" * 60,   # Exactly 60
            "assertion": "B" * 100,  # Exactly 100
        }
        result = curator_service._quality_check(aku)
        assert result is None  # Passed

class TestSimplifiedSchema:
    """Tests verifying schema simplification."""

    def test_stores_without_modality_polarity(self, curator_service):
        """AKUs should store without modality/polarity fields."""
        # Verify INSERT doesn't include deprecated columns
        ...

    def test_accepts_aku_without_category(self, curator_service):
        """AKUs without category should be accepted (no longer required)."""
        ...
```

**Fixture updates:**
```python
@pytest.fixture
def valid_aku() -> dict[str, Any]:
    """Create a valid AKU payload - SIMPLIFIED."""
    return {
        "situation": "When iterating paginated APIs",  # ≤60 chars
        "assertion": "Use offset=0 for first page, increment by page_size",  # ≤100 chars
        # REMOVED: modality, polarity
    }
```

#### ADVISOR Tests (`core/learning_loop/tests/unit/test_advisor_selector.py`)

**Tests to MODIFY:**
```python
@dataclass
class MockBulletForSampling:  # RENAME to MockAkuForSampling
    """Minimal AKU for Thompson Sampling tests."""
    aku_id: str  # was bullet_id
    helpful_count: int
    harmful_count: int
    neutral_count: int
    created_at: datetime
```

**Variable renames throughout:**
- `bullet_id` → `aku_id`
- `bullets` → `akus`
- `bullet_scores` → `aku_scores`

#### REFLECTOR Tests (`core/learning_loop/tests/unit/test_reflector_service.py`)

**Variable renames:**
- `bullets_helped` → `akus_helped`
- `bullets_harmed` → `akus_harmed`
- `bullets_shown` → `akus_shown`

#### Formatter Tests (`core/session/tests/unit/test_bullet_formatter.py` → `test_aku_formatter.py`)

**Tests to REMOVE:**
```python
class TestFormatBulletsForLlm:  # RENAME to TestFormatAkusForLlm
    def test_formats_do_polarity_as_solutions(...)    # DELETE - no polarity
    def test_formats_dont_polarity_as_constraints(...) # DELETE
    def test_formats_know_polarity_as_reference(...)   # DELETE
    def test_all_categories_formatted(...)             # DELETE - no categories
    def test_default_polarity_is_do(...)               # DELETE
```

**Tests to ADD:**
```python
class TestFormatAkusForLlm:
    """Tests for simplified TIPS format."""

    def test_formats_as_tips_list(self, sample_akus):
        """AKUs should format as simple TIPS bullet list."""
        result = format_akus_for_llm(sample_akus)

        assert "TIPS:" in result
        assert "•" in result
        assert "Solutions (#S):" not in result  # No categories
        assert "Constraints (#C):" not in result

    def test_no_position_markers(self, sample_akus):
        """New format should NOT include [1], [2] markers."""
        result = format_akus_for_llm(sample_akus)

        assert "[1]" not in result
        assert "[2]" not in result

    def test_includes_proven_markers(self):
        """Proven AKUs should show [PROVEN] marker."""
        akus = [{
            "id": str(uuid4()),
            "assertion": "Test assertion",
            "effectiveness_tier": "proven",  # ≥80% effectiveness
        }]
        result = format_akus_for_llm(akus)
        assert "[PROVEN]" in result

    def test_sorts_by_score(self):
        """AKUs should be sorted by Thompson Sampling score."""
        akus = [
            {"id": "1", "assertion": "Low score", "score": 0.3},
            {"id": "2", "assertion": "High score", "score": 0.9},
        ]
        result = format_akus_for_llm(akus)
        # High score should appear first
        assert result.index("High score") < result.index("Low score")
```

**Function renames:**
- `format_bullets_for_llm` → `format_akus_for_llm`
- `format_bullets_compact` → `format_akus_compact`
- `extract_bullet_ids` → `extract_aku_ids`

### 13.3 Integration Test Updates

#### SQL Query Tests (`core/learning_loop/tests/integration/test_sql_queries.py`)

**All SQL queries updated:**
```python
# Before
"SELECT bullet_id FROM playbook_bullets WHERE ..."

# After
"SELECT aku_id FROM akus WHERE ..."
```

**Column references:**
- `bullets_shown` → `akus_shown`
- `bullets_helped` → `akus_helped`
- `bullets_harmed` → `akus_harmed`

#### Event Flow Tests (`core/learning_loop/tests/integration/test_event_flows.py`)

**Event type assertions:**
```python
# Before
assert event["event_type"] == "bullet.accepted"
assert event["event_type"] == "bullet.merged"

# After
assert event["event_type"] == "aku.accepted"
assert event["event_type"] == "aku.merged"
```

**Payload field names:**
```python
# Before
assert "bullet_id" in payload

# After
assert "aku_id" in payload
```

#### Thompson Sampling Tests (`core/learning_loop/tests/integration/test_thompson_sampling_real.py`)

**Table references in setup/teardown:**
```python
# Before
await conn.execute("INSERT INTO playbook_bullets ...")
await conn.execute("DELETE FROM playbook_bullets WHERE ...")

# After
await conn.execute("INSERT INTO akus ...")
await conn.execute("DELETE FROM akus WHERE ...")
```

### 13.4 Conftest Fixture Updates

#### `core/learning_loop/tests/conftest.py`

```python
@dataclass
class MockAku:  # was MockBullet
    """Mock AKU for testing."""
    aku_id: str  # was bullet_id
    situation: str  # was content
    assertion: str
    # REMOVED: category, domain, signal_type
    status: str = "candidate"
    helpful_count: int = 0
    harmful_count: int = 0
    neutral_count: int = 0
    created_at: Optional[datetime] = None
    situation_embedding: Optional[list[float]] = None  # was problem_embedding

@pytest.fixture
def sample_akus():  # was sample_bullets
    """Create sample AKUs for testing."""
    now = datetime.now(timezone.utc)
    return [
        MockAku(
            aku_id=str(uuid4()),
            situation="When paginating API responses",
            assertion="Use offset=0 for first page",
            # No category, domain, signal_type
            ...
        ),
        ...
    ]
```

#### `core/session/tests/conftest.py`

```python
@pytest.fixture
def sample_akus():  # was sample_bullets
    """Sample AKUs in simplified v4 format."""
    return [
        {
            "id": str(uuid4()),
            "situation": "When handling API pagination",
            "assertion": "Use offset=0 for the first page",
            # REMOVED: modality, polarity
            "score": 0.85,
        },
        ...
    ]
```

#### `e2e/conftest.py`

```python
@pytest_asyncio.fixture
async def clean_test_data(db_pool: asyncpg.Pool):
    """Cleanup fixture with renamed tables."""
    ...
    # Cleanup
    async with db_pool.acquire() as conn:
        # Before: DELETE FROM playbook_bullets
        await conn.execute(
            "DELETE FROM akus WHERE source LIKE $1",
            f"{prefix}%"
        )
```

### 13.5 E2E Test Updates

#### `e2e/tests/test_learning_loop.py`

**Kafka topic subscriptions:**
```python
# Before
consumer.subscribe(["bullet.accepted", "bullet.merged"])

# After
consumer.subscribe(["aku.accepted", "aku.merged"])
```

**API response assertions:**
```python
# Before
assert "bullet_id" in response.json()

# After
assert "aku_id" in response.json()
```

#### `e2e/tests/test_session_lifecycle.py`

**Redis key checks:**
```python
# Before
key = f"session:{session_id}:bullets"
key = f"session:{session_id}:turn:{turn}:bullets"

# After
key = f"session:{session_id}:akus"
key = f"session:{session_id}:turn:{turn}:akus"
```

### 13.6 New Test Files

#### `core/learning_loop/tests/unit/test_length_validation.py` (NEW)

```python
"""Unit tests for AKU length validation.

Tests the 60-char situation / 100-char assertion constraints.
"""

import pytest
from core.learning_loop.curator.service import CuratorService


class TestSituationLength:
    """Tests for situation field length constraints."""

    @pytest.mark.parametrize("length,should_pass", [
        (10, True),   # Minimum valid
        (30, True),   # Typical
        (60, True),   # Maximum valid
        (61, False),  # Over limit
        (100, False), # Way over
    ])
    def test_situation_length_boundary(self, curator_service, length, should_pass):
        """Validate situation length boundaries."""
        aku = {
            "situation": "A" * length,
            "assertion": "Valid assertion content here",
        }
        result = curator_service._quality_check(aku)
        if should_pass:
            assert result is None
        else:
            assert "situation_too_long" in result


class TestAssertionLength:
    """Tests for assertion field length constraints."""

    @pytest.mark.parametrize("length,should_pass", [
        (20, True),   # Minimum valid
        (50, True),   # Typical
        (100, True),  # Maximum valid
        (101, False), # Over limit
        (200, False), # Way over
    ])
    def test_assertion_length_boundary(self, curator_service, length, should_pass):
        """Validate assertion length boundaries."""
        aku = {
            "situation": "Valid situation",
            "assertion": "A" * length,
        }
        result = curator_service._quality_check(aku)
        if should_pass:
            assert result is None
        else:
            assert "assertion_too_long" in result
```

#### `core/session/tests/unit/test_tips_format.py` (NEW)

```python
"""Unit tests for TIPS presentation format.

Tests the simplified bullet-point presentation.
"""

from uuid import uuid4
from core.session.domain.aku_formatter import format_akus_for_llm


class TestTipsFormat:
    """Tests for TIPS presentation format."""

    def test_header_is_tips(self):
        """Format should start with 'TIPS:'."""
        akus = [{"id": str(uuid4()), "assertion": "Test"}]
        result = format_akus_for_llm(akus)
        assert result.startswith("TIPS:")

    def test_uses_bullet_points(self):
        """Each AKU should be a bullet point."""
        akus = [
            {"id": str(uuid4()), "assertion": "First tip"},
            {"id": str(uuid4()), "assertion": "Second tip"},
        ]
        result = format_akus_for_llm(akus)
        assert result.count("•") == 2

    def test_no_category_headers(self):
        """Should not include category headers."""
        akus = [{"id": str(uuid4()), "assertion": "Test"}]
        result = format_akus_for_llm(akus)

        assert "Solutions" not in result
        assert "Constraints" not in result
        assert "Reference" not in result
        assert "#S" not in result
        assert "#C" not in result
        assert "#R" not in result

    def test_effectiveness_tiers_shown(self):
        """High-effectiveness AKUs should show tier markers."""
        akus = [
            {"id": "1", "assertion": "Proven tip", "helpful_count": 10, "harmful_count": 1},
            {"id": "2", "assertion": "Tested tip", "helpful_count": 5, "harmful_count": 3},
        ]
        result = format_akus_for_llm(akus)

        # 10/11 = 90% → [PROVEN]
        # 5/8 = 62% → [TESTED]
        assert "[PROVEN]" in result or "[TESTED]" in result

    def test_max_token_efficiency(self):
        """10 AKUs should be under 200 tokens (~800 chars)."""
        akus = [
            {"id": str(uuid4()), "assertion": f"Tip number {i} with content"}
            for i in range(10)
        ]
        result = format_akus_for_llm(akus)

        # Rough estimate: 200 tokens ≈ 800 chars
        assert len(result) < 1000
```

---

## Phase 14: Documentation Updates (Detailed)

### 14.1 Documentation Inventory

| File | "bullet" refs | Priority |
|------|---------------|----------|
| `CLAUDE.md` | ~150 | HIGH |
| `ARCHITECTURE.md` | ~50 | HIGH |
| `core/learning_loop/README.md` | ~30 | HIGH |
| `core/session_v3/README.md` | ~20 | MEDIUM |
| `docs/cross-session-learning.md` | ~15 | MEDIUM |
| `docs/roadmap-user-intent.md` | ~10 | LOW |
| `docs/architecture/ROADMAP_RETRIEVAL.md` | ~10 | LOW |

### 14.2 CLAUDE.md Updates

#### Database Schema Section
```markdown
# Before
| `playbook_bullets` | Bullet storage with situation_embedding, assertion_embedding, counters |

# After
| `akus` | AKU storage with situation_embedding, assertion_embedding, counters |
```

#### SQL Queries Section
All debugging queries updated:
```sql
-- Before
SELECT bullet_id::text, helpful_count, harmful_count FROM playbook_bullets;

-- After
SELECT aku_id::text, helpful_count, harmful_count FROM akus;
```

#### Event Documentation
```markdown
# Before
| `bullet.accepted` | CURATOR | CLUSTERER | New bullet stored |
| `bullet.merged` | CURATOR | CLUSTERER | Evidence incremented |

# After
| `aku.accepted` | CURATOR | CLUSTERER | New AKU stored |
| `aku.merged` | CURATOR | CLUSTERER | Evidence incremented |
```

#### Key Code Locations Table
```markdown
# Before
| SESSION bullet formatting | `core/session_v3/domain/bullet_formatter.py` |

# After
| SESSION AKU formatting | `core/session_v3/domain/aku_formatter.py` |
```

#### Bullet Categories Section → AKU Format Section
```markdown
# REMOVE entire section:
## Bullet Categories
Five categories: `cheat_sheets`, `constraints`, `examples`, `meta_prompts`, `solutions`

# REPLACE with:
## AKU Format

**Simplified format (v4):**
- `situation` (≤60 chars): Retrieval trigger
- `assertion` (≤100 chars): Actionable advice

**Presentation:**
```
TIPS:
• [PROVEN] Use offset=0 for first page. (increment by page_size)
• Use show_song_privates() for play_count. (show_song() returns 0)
```

**Effectiveness tiers:**
- `[PROVEN]`: ≥80% help rate
- `[TESTED]`: ≥50% help rate
- No marker: <50% or untested
```

### 14.3 ARCHITECTURE.md Updates

#### Data Structures Section
```markdown
# Before
### Bullet Storage
| Field | Purpose |
|-------|---------|
| `bullet_id` | Primary key |
| `content` | Full bullet text |
| `modality` | must/should/could |
| `polarity` | do/dont/know |
| `category` | solutions/constraints/... |

# After
### AKU Storage
| Field | Purpose |
|-------|---------|
| `aku_id` | Primary key |
| `situation` | Retrieval trigger (≤60 chars) |
| `assertion` | Actionable advice (≤100 chars) |
| `situation_embedding` | For retrieval |
| `assertion_embedding` | For deduplication |
| `helpful_count` | Positive signals |
| `harmful_count` | Negative signals |
```

#### Events Table
```markdown
# Before
| `bullet.accepted` | CURATOR | CLUSTERER | New bullet stored |

# After
| `aku.accepted` | CURATOR | CLUSTERER | New AKU stored |
```

#### Mermaid Diagrams
Update all diagrams showing data flow to use "AKU" terminology.

### 14.4 core/learning_loop/README.md Updates

#### ASCII Diagrams
```
# Before
SESSION → bullets.requested → ADVISOR → Redis (bullets)

# After
SESSION → akus.requested → ADVISOR → Redis (akus)
```

#### Database Schema Table
```markdown
# Before
| `playbook_bullets` | Bullet storage with ... |

# After
| `akus` | AKU storage with ... |
```

#### Debugging SQL
```sql
-- Before
SELECT bullet_id::text, helpful_count FROM playbook_bullets;

-- After
SELECT aku_id::text, helpful_count FROM akus;
```

### 14.5 Terminology Replacement Rules

**Global find-replace patterns:**

| Pattern | Replacement | Context |
|---------|-------------|---------|
| `playbook_bullets` | `akus` | SQL, code |
| `bullet_id` | `aku_id` | SQL, code, JSON |
| `bullet.accepted` | `aku.accepted` | Kafka topics |
| `bullet.merged` | `aku.merged` | Kafka topics |
| `bullets.requested` | `akus.requested` | Kafka topics |
| `bullets_shown` | `akus_shown` | SQL columns |
| `bullets_helped` | `akus_helped` | SQL columns |
| `bullets_harmed` | `akus_harmed` | SQL columns |
| `bullet_formatter` | `aku_formatter` | Python modules |
| `bullet_cache` | `aku_cache` | Python modules |
| `Bullet` (type) | `AKU` | TypeScript |
| `bullets` (var) | `akus` | All languages |

**Exceptions (keep as-is):**
- Markdown bullet points (`•`, `-`, `*`)
- "bullet point" in prose descriptions

### 14.6 Code Comment Updates

Search and replace in all Python files:
```python
# Before
"""Select bullets for the current turn."""
# Returns list of bullets
def get_bullets(...):

# After
"""Select AKUs for the current turn."""
# Returns list of AKUs
def get_akus(...):
```

---

## Execution Order

**Recommended sequence to minimize breakage:**

1. **Phase 0**: Clean slate (delete existing data)
2. **Phase 1**: Schema migration (database first)
3. **Phases 2-5**: Learning Loop services (consumers ready for new events)
4. **Phase 13.4**: Update test conftest fixtures (tests can run)
5. **Phases 6-8**: Session service updates
6. **Phase 9**: Kafka event renames (producers last)
7. **Phases 10-11**: API routes
8. **Phase 12**: Frontend
9. **Phase 13.1-13.5**: Test updates (file renames, assertions)
10. **Phase 13.6**: New test files
11. **Phase 14**: Documentation

**Verification checkpoints:**
- After Phase 1: `pytest core/learning_loop/tests -v` passes
- After Phase 8: `pytest core/session/tests -v` passes
- After Phase 12: `npm run typecheck` passes
- After Phase 13: All tests green
- After Phase 14: `grep -r "bullet" docs/` returns only prose bullet points

---

## Test Execution Commands

```bash
# Run all affected tests
pytest core/learning_loop/tests core/session/tests e2e/tests -v

# Run specific test categories
pytest core/learning_loop/tests/unit -v              # Unit tests
pytest core/learning_loop/tests/integration -v       # Integration tests
pytest e2e/tests -v -m e2e                           # E2E tests

# Verify no "bullet" references remain in test assertions
grep -r "bullet_id" core/*/tests --include="*.py" | wc -l  # Should be 0
grep -r "playbook_bullets" core/*/tests --include="*.py" | wc -l  # Should be 0

# Type check frontend
cd frontend && npm run typecheck

# Verify documentation
grep -rn "bullet" CLAUDE.md ARCHITECTURE.md | grep -v "bullet point" | wc -l  # Should be 0
```
