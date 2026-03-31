"""LLM prompts for STRATEGIST service."""

SYNTHESIS_SYSTEM = """Analyze these failures by answering each question.

QUESTION 1: What USER GOAL do these failures share?
What were agents trying to accomplish when they failed?
Format: "[action verb] [specific object]" - e.g., "get play metrics" or "list user's playlists"
NOT acceptable: "complete the task" or "use the API" or "retrieve data"

QUESTION 2: What SPECIFIC operation keeps failing?
Look across failures - what exact method/field/operation fails repeatedly?
Format: "method_name()" or "object.field" or "response['key']"
NOT acceptable: "API calls" or "data retrieval" or "the operation"

QUESTION 3: What SPECIFIC alternative would work?
Based on error patterns, what exact method/field should agents use instead?
Format: "method_name()" or "object.field" or "response['key']"
NOT acceptable: "use different method" or "try alternative" or "handle error"

QUESTION 4: What's the GOTCHA?
What unexpected behavior causes Q2 to fail that agents wouldn't know?
Format: "[Q2] does [unexpected] - need [Q3] because [specific reason]"
NOT acceptable: "API behaves unexpectedly" or "format varies"

SYNTHESIZE:
If ALL answers above are SPECIFIC, combine into:

---AKU---
SITUATION: When [Q1 - the user goal/intent, not the operation]
ASSERTION: [Q2] [gotcha from Q4] - use [Q3] instead
MODALITY: should
POLARITY: do
---END---

OUTPUT NO_AKU IF:
- Any answer above is vague (doesn't name specific goal/method/field)
- You cannot identify a concrete pattern across the failures
- The insight would be "check/verify/inspect" (debugging, not knowledge)
"""

SYNTHESIS_GAP_USER = """This cluster has repeated failures but no documented solutions.

Cluster: {cluster_label}
Failure count: {failure_count}

Sample failed attempts:
{sample_turns}

Synthesize an AKU that would help future agents succeed:"""

SYNTHESIS_STRUGGLING_USER = """This cluster has solutions but they're not working well.

Cluster: {cluster_label}
Success rate: {success_rate:.1%}

Existing solutions (not working):
{existing_solutions}

Sample failures despite solutions:
{sample_failures}

Synthesize a NEW AKU with a different approach:"""


# Comparative analysis prompt - for cross-session learning
SYNTHESIS_COMPARATIVE_SYSTEM = """You analyze success vs failure patterns for the SAME task.

Some sessions succeed, some fail. Your job is to identify WHY.

ANALYSIS APPROACH:
1. Compare what successful sessions did vs what failed sessions did
2. Look for SEMANTIC DISTINCTIONS the existing bullets don't capture
3. Identify if any bullet is MISLEADING for this specific task context

COMMON PATTERNS TO LOOK FOR:
- API method confusion: show_song() vs show_song_privates() return different data
- Metric semantics: "play_count" might mean USER's count or GLOBAL count
- Field availability: some fields only in certain endpoints
- Context mismatch: bullet advice correct for one task type but wrong for this one

OUTPUT FORMAT:

If you identify a clear distinction:

---AKU---
SITUATION: When [the specific user goal from the task]
ASSERTION: [method_A] returns [X semantic], [method_B] returns [Y semantic] - for [this goal] use [correct method]
MODALITY: should
POLARITY: know
---END---

If a bullet is misleading:

---MISLEADING---
BULLET_ID: [id]
REASON: [why it's wrong for this task]
CORRECT_APPROACH: [what should be done instead]
---END---

OUTPUT NO_AKU IF:
- The difference is just debugging/printing approach
- You can't identify a semantic distinction
- Success vs failure seems random
"""

SYNTHESIS_COMPARATIVE_USER = """This exact task has mixed results - some sessions succeed, some fail.

Task: {task_description}
Success rate: {success_rate:.1f}% ({successes}/{total} sessions)

=== SUCCESSFUL APPROACH (breakthrough moment) ===
{success_snippet}

=== FAILED APPROACH (where agent got stuck) ===
{failure_snippet}

=== BULLETS APPEARING MORE IN FAILURES THAN SUCCESSES ===
{differential_bullets}

What semantic distinction explains why some sessions succeed and others fail?
If a bullet is misleading for this task, identify it."""
