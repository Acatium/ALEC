# Roadmap: User Intent Understanding

## Problem

The current cross-session learning uses **exact task text matching** from AppWorld's `## Task\n` format. This won't work for real users who describe tasks in varied ways.

**Example:**
- "Find my least played song"
- "What song have I listened to the least?"
- "Which track in my library has the lowest play count?"

All mean the same thing but won't match exactly.

## Current State (Dec 2025)

Using exact task matching as scaffolding to:
1. Validate comparative analysis produces good AKUs
2. Dial in knowledge extraction and retrieval
3. Target: 100% AppWorld success rate

## Future Options

### Option A: Keyword-Enhanced Grouping (Hindsight-style)

**Approach:**
- Extract keywords from sessions: [spotify, song, library, play_count, least]
- Group sessions by keyword overlap (Jaccard similarity > 0.6)
- More robust than embedding similarity alone

**Pros:**
- Relatively simple to implement
- Keywords are stable across phrasing variations
- Can use existing NLP libraries (spaCy, etc.)

**Cons:**
- Still fuzzy - may group different tasks together
- Requires keyword extraction logic
- May miss semantic nuances

**Implementation sketch:**
```python
def extract_keywords(message: str) -> set[str]:
    # Extract entities: song, playlist, album, artist
    # Extract operations: get, find, list, filter, sort
    # Extract attributes: play_count, like_count, title
    return keywords

def group_by_keywords(sessions: list) -> list[list]:
    # Group by Jaccard similarity > 0.6
    pass
```

### Option B: Approach-Outcome Correlation

**Approach:**
- Don't try to match "same task"
- Instead: "when agents use approach X, what happens?"
- Correlate API calls with outcomes

**Example:**
```
show_song_privates + play_count context → 67% failure
show_song + play_count context → 80% success
```

**Pros:**
- Sidesteps task-matching problem entirely
- Statistical - works with noisy data
- Directly actionable

**Cons:**
- Requires API call extraction from responses
- Still needs some context grouping (what's "play_count context"?)
- May miss task-specific nuances

**Implementation sketch:**
```python
# Extract API calls from assistant responses
api_calls = extract_api_calls(assistant_response)
# Correlate with session outcome
correlations = correlate_api_with_outcome(api_calls, success)
```

### Option C: Entity-Operation Pairs

**Approach:**
- Structured extraction: (entity, operation, metric, source)
- Example: (song, find_minimum, play_count, library)
- Match on structured representation

**Pros:**
- More precise than keywords
- Captures semantic structure
- Amenable to LLM extraction

**Cons:**
- Requires LLM call for extraction (cost)
- Schema design is tricky
- May miss edge cases

### Option D: Periodic LLM Batch Analysis

**Approach:**
- Every N sessions, run LLM on batch
- "Here are 20 sessions involving Spotify play_count. What patterns distinguish success from failure?"

**Pros:**
- Most powerful - full reasoning capability
- Can discover unexpected patterns
- No schema design needed

**Cons:**
- Most expensive (LLM cost per batch)
- Latency - not real-time
- May need human review

## Recommended Path

### Phase 1: Validate with Exact Matching (Current)
- Target: 100% AppWorld success
- Prove that comparative analysis → good AKUs → improved retrieval

### Phase 2: Keyword Enhancement
- Add keyword extraction to LIBRARIAN
- Use keyword overlap for grouping
- Validate on AppWorld with artificial variation

### Phase 3: Approach Correlation
- Add API call extraction
- Build correlation engine
- Can run alongside keyword matching

### Phase 4: Hybrid System
- Keywords for initial grouping
- Approach correlation for refinement
- LLM batch analysis for discovery

## Key Insight

The fundamental question is: **How do you know two sessions are attempting the same task?**

Options range from:
- **Exact match** (current) - 100% precision, 0% recall for variations
- **Embedding similarity** (clustering) - fuzzy, groups different tasks
- **Keywords** - middle ground, explicit features
- **Structured extraction** - precise but expensive
- **LLM reasoning** - powerful but costly

The right answer is likely a **cascade**:
1. Try exact match first (cheap, precise)
2. Fall back to keyword overlap (cheap, fuzzy)
3. Use LLM for ambiguous cases (expensive, accurate)

## Success Metrics

- **Precision**: Of sessions grouped together, what % are truly same task?
- **Recall**: Of same-task sessions, what % are grouped together?
- **AKU Quality**: Do synthesized AKUs improve success rate?

Target: 80%+ precision, 60%+ recall, measurable success improvement.

## Timeline

- Phase 1: Current (Dec 2025)
- Phase 2: After 100% AppWorld success
- Phase 3-4: Based on real-world usage patterns

## References

- [Hindsight paper](https://arxiv.org/abs/2404.00498) - Memory-augmented LLM agents
- [Cross-Session Learning](./cross-session-learning.md) - Current implementation
