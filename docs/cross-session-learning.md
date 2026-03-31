# Cross-Session Learning: Task Comparative Analysis

## Overview

This document describes the task-based comparative analysis feature that enables LIBRARIAN and STRATEGIST to learn from cross-session patterns - comparing what works vs what fails for the same task.

## Problem Statement

The original architecture had a blind spot: no component could compare successful vs failed sessions for the same task to identify discriminating factors.

**Example failure mode:**
- Task: "Find the least-played song in my Spotify library"
- Some sessions succeed (use `show_song()` for GLOBAL play_count)
- Some sessions fail (use `show_song_privates()` for USER play_count)
- A bullet advising `show_song_privates()` was being retrieved and causing failures
- But no component could detect this pattern

## Solution: Task Comparative Analysis

### Architecture

```
LIBRARIAN (enhanced)
    │
    ├── Groups sessions by EXACT task description
    │   (extracts from "## Task\n" marker in first turn)
    │
    ├── For tasks with mixed success/failure:
    │   - Computes differential bullets (appear more in failures)
    │   - Extracts success breakthrough snippet
    │   - Extracts failure stuck snippet
    │
    └── Emits: library.task.comparative
                    │
                    ▼
STRATEGIST (new handler)
    │
    ├── Receives ~1.5k token comparative context
    │
    ├── Prompt asks:
    │   - What semantic distinction explains success vs failure?
    │   - Is any bullet misleading for this task context?
    │
    └── Emits: aku.proposed with clarifying AKU
```

### Data Flow

1. **LIBRARIAN** queries for tasks with mixed results:
   ```sql
   SELECT task_desc, successes, failures
   FROM task_sessions
   GROUP BY task_desc
   HAVING successes >= 2 AND failures >= 2
   ```

2. **LIBRARIAN** computes differential bullets:
   ```sql
   -- Bullets appearing more in failures than successes
   SELECT bullet_id, in_failures, in_successes
   WHERE in_failures > in_successes
   ```

3. **LIBRARIAN** extracts snippets:
   - Success: The `solved` turn from a successful session
   - Failure: A `stuck` turn from a failed session

4. **STRATEGIST** synthesizes clarifying AKU:
   - Input: ~1.5k tokens (task + snippets + differential bullets)
   - Output: AKU with semantic distinction (e.g., USER vs GLOBAL play_count)

### Token Efficiency

| Component | Tokens |
|-----------|--------|
| Task description | ~50 |
| Success snippet | ~200 |
| Failure snippet | ~200 |
| Differential bullets (3-5) | ~300 |
| Prompt template | ~500 |
| **Total per task** | **~1.3k** |

This is 100x more efficient than sending full session transcripts.

## Current Limitation: Exact Task Matching

**This implementation uses exact task text matching** from the `## Task\n` marker in AppWorld format. This is intentional scaffolding to:

1. Validate that comparative analysis produces good AKUs
2. Dial in the knowledge extraction and retrieval
3. Achieve 100% AppWorld success rate

**This will not generalize to real users** who describe tasks differently each time.

## Files Modified

- `core/agents/librarian/service.py` - Added `_detect_task_comparative()` and helper methods
- `core/agents/strategist/service.py` - Added `_handle_comparative()` handler
- `core/agents/strategist/prompts.py` - Added `SYNTHESIS_COMPARATIVE_SYSTEM/USER` prompts

## Configuration

```bash
# Minimum sessions needed for comparative analysis
LIBRARIAN_TASK_MIN_SESSIONS=4
LIBRARIAN_TASK_MIN_SUCCESSES=2
LIBRARIAN_TASK_MIN_FAILURES=2
```

## Testing

Run an evaluation, then trigger LIBRARIAN analysis:
```bash
curl -X POST http://localhost:8008/api/v1/system/intelligence/run
```

Check logs for comparative events:
```bash
docker-compose logs agents | grep "task_comparative\|comparative_aku"
```

## Related Documentation

- [User Intent Roadmap](./roadmap-user-intent.md) - Plan for generalizing beyond exact task matching
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
