"""REFLECTOR prompts v2 - Causal attribution focus.

Key changes from v1:
1. Outcome-specific attribution guidance (conservative on ambiguous turns)
2. Explicit causation vs correlation distinction
3. Uncertainty handling (default to NEUTRAL)
4. Brief role context for stakes awareness

v4 Updates (gap-aku-001):
- Renamed bullets → AKUs (Atomic Knowledge Units)
- Removed modality/polarity from extraction
- Added length constraints (situation ≤60, assertion ≤100 chars)
"""

TURN_ANALYSIS_SYSTEM = """You analyze AI agent conversations to extract learning signals.
Your attributions directly affect which knowledge the system retains or discards.

TASK:
1. Identify the SITUATION - the general problem being solved (session-level)
2. Classify each turn's micro-outcome
3. Attribute which AKUs helped or harmed (with clear evidence only)

MICRO-OUTCOMES:
- solved: Agent achieved a concrete outcome or completed a sub-task
- progress: Agent made forward progress but hasn't completed
- stuck: Agent is uncertain, trying multiple approaches, or spinning
- error: Agent encountered an explicit error from the environment/API

SESSION SUCCESS CORRELATION:
- Session outcome (SUCCESS/FAILURE) indicates overall task completion
- If session SUCCESS, at least one turn should be "solved"
- Mark the turn with the decisive breakthrough as "solved"

ATTRIBUTION - CAUSATION REQUIRED:

For HELPED:
- Agent followed the AKU's specific advice
- That action contributed to the turn's positive outcome
- Appropriate on: solved, progress turns

For HARMED (use sparingly):
- Agent followed the AKU's specific advice
- That advice DIRECTLY CAUSED the negative outcome
- Must trace clear causal chain: advice → action → failure
- Most appropriate on: error turns (clear causal signal)
- Be VERY conservative on: stuck turns (ambiguous causation)

For NEUTRAL (default when uncertain):
- Agent didn't follow the AKU's advice
- Causation is unclear or speculative
- AKU was shown but unrelated to outcome

KEY DISTINCTION:
AKU shown + failure ≠ AKU caused failure
Many failures have causes unrelated to AKUs shown.
When uncertain between HARMED and NEUTRAL, choose NEUTRAL.

SITUATION FORMAT:
Keep abstract - no variable names, error messages, or debugging details.
Good: "When finding the least-played song in a music library"
Bad: "When fixing KeyError for 'id' field in the show_song response"

OUTPUT FORMAT:

SITUATION: [General problem being solved]

---TURN 1---
SUB_TASK: What agent was attempting
OUTCOME: [progress|solved|stuck|error]
HELPED: [aku_ids or "none"]
HARMED: [aku_ids or "none"]

---TURN 2---
...continue for all turns...

Only include AKU IDs with clear evidence. Default to "none" when uncertain.
"""

TURN_ANALYSIS_USER = """Analyze these conversation turns.

AKU reference (content for IDs shown in turns):
{akus_json}

Conversation turns:
{turns_json}

Session outcome: {session_success}

Provide analysis for each turn. Only attribute AKUs from that turn's "akus_shown" field.
For HARMED, require clear causal evidence - default to NEUTRAL when uncertain."""


# AKU extraction prompts - structured Q&A to force specificity
AKU_EXTRACTION_SYSTEM = """Analyze this stuck→recovery by answering each question.

QUESTION 1: What was the agent trying to ACCOMPLISH?
What user goal was the agent working toward when they got stuck?
Format: "[action verb] [specific object]" - e.g., "get play count for songs" or "find user's top tracks"
NOT acceptable: "complete the task" or "call the API" or "get data"

QUESTION 2: What SPECIFIC operation failed?
Identify the EXACT method call, field access, or operation that didn't work.
Format: "method_name()" or "object.field" or "response['key']"
NOT acceptable: "the API call" or "data access" or "the request"

QUESTION 3: What SPECIFIC operation succeeded?
Identify the EXACT method call, field access, or operation that worked instead.
Format: "method_name()" or "object.field" or "response['key']"
NOT acceptable: "alternative approach" or "different method" or "the fix"

QUESTION 4: What was UNEXPECTED?
What behavior surprised the agent that they couldn't have known beforehand?
Format: "[Q2 thing] does [unexpected], but [Q3 thing] does [expected]"
NOT acceptable: "API varies" or "response format differs" or "unexpected behavior"

SYNTHESIZE:
If ALL answers above are SPECIFIC, combine into:

---AKU---
SITUATION: When [Q1 - the user goal/intent, not the operation]
ASSERTION: [Q2] [unexpected behavior from Q4] - use [Q3] instead
---END---

LENGTH CONSTRAINTS (CRITICAL):
- SITUATION: Maximum 60 characters. Be concise.
- ASSERTION: Maximum 100 characters. Be specific but brief.

If your SITUATION exceeds 60 chars or ASSERTION exceeds 100 chars, shorten them.
Remove filler words. Use abbreviations if needed. Focus on the core insight.

OUTPUT NO_AKU IF:
- Any answer above is vague (doesn't name specific method/field/goal)
- The "fix" was adding print/logging/debugging
- You cannot identify concrete method/field names in the conversation
- You cannot fit the insight within the length constraints
"""

AKU_EXTRACTION_USER = """The agent was stuck/erroring, then recovered.

Stuck turn:
{stuck_turn}

Recovery turn:
{recovery_turn}

What insight enabled the recovery? Extract an AKU:"""
