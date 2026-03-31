"""LLM prompts for REFLECTOR service."""

TURN_ANALYSIS_SYSTEM = """You are analyzing an AI agent's conversation turns to determine:
1. The general problem/situation the agent is trying to solve (session-level)
2. What sub-task the agent was attempting in each turn
3. The micro-outcome of each turn (progress, solved, stuck, or error)
4. Which bullets (contextual hints) helped or harmed the agent's performance

Micro-outcome definitions:
- solved: Agent achieved a concrete outcome, completed a sub-task, or made the key breakthrough
- progress: Agent made forward progress but hasn't completed the sub-task
- stuck: Agent is uncertain, trying multiple approaches, or explicitly stuck
- error: Agent encountered an error from the environment/API

IMPORTANT - Session Success Correlation:
- The session outcome (SUCCESS/FAILURE) tells you whether the overall task was completed
- If session outcome is SUCCESS, at least one turn MUST be marked "solved"
- Mark the turn that made the decisive breakthrough or final contribution as "solved"
- Don't be overly conservative - successful sessions have successful turns

IMPORTANT - Bullet Attribution:
Only attribute bullets that were shown in THAT SPECIFIC TURN (check the "bullets_shown" field).

A bullet HELPED if:
- Agent explicitly followed its advice and succeeded
- Agent's successful approach matches what the bullet recommended
- The bullet's information was directly relevant and contributed to success

A bullet HARMED if ANY of these are true:
- Agent followed the bullet's advice and it led to an error or failure
- The bullet suggested an approach that doesn't apply to THIS specific task
- The bullet's advice was misleading for this context (e.g., wrong API pattern)
- Agent got stuck trying to follow the bullet's recommendation
- The bullet distracted the agent from the correct approach
- On ERROR turns: if a bullet suggested the approach that caused the error, mark it HARMED
- On STUCK turns: if the agent is struggling with an approach a bullet recommended, mark it HARMED

CRITICAL: Don't be overly conservative on harm attribution!
- If the agent is stuck/erroring and a bullet was recommending the failing approach → HARMED
- If a bullet's advice doesn't match this specific situation → HARMED
- Implicit harm counts: even if agent didn't cite the bullet, if they followed its pattern and failed → HARMED
- Under-attributing harm prevents the system from learning what NOT to show

First, output the SITUATION - the general problem being solved across all turns.
Keep it abstract (no specific variable names, error messages, or debugging details).
Good: "When finding the least-played song in a music library"
Bad: "When fixing KeyError for 'id' field in the show_song response"

Then analyze each turn.

Output format:

SITUATION: [General problem - what is the agent trying to accomplish?]

---TURN 1---
SUB_TASK: Brief description of what agent was attempting
OUTCOME: progress
HELPED: none
HARMED: none

---TURN 2---
SUB_TASK: Brief description
OUTCOME: error
HELPED: none
HARMED: bullet_id_1

Continue for all turns. Use "none" if no bullets helped or harmed that turn.
"""

TURN_ANALYSIS_USER = """Analyze these conversation turns.

Bullet reference (content for IDs used in turns):
{bullets_json}

Conversation turns (each turn has "bullets_shown" - only attribute those bullets):
{turns_json}

Session outcome: {session_success}

Output the analysis for each turn. Only attribute bullets that appear in that turn's "bullets_shown" field:"""


AKU_EXTRACTION_SYSTEM = """You are extracting reusable knowledge from an AI agent's conversation.

When an agent recovers from being stuck or erroring, there's often a valuable insight to capture.

Extract an AKU (Atomic Knowledge Unit) with:
- SITUATION: WHEN does this apply? (retrieval key - should match similar future problems)
- ASSERTION: WHAT to do? (the actual advice, specific and actionable)
- MODALITY: How confident? (must/should/could)
- POLARITY: Action type? (do/dont/know)

Guidelines:
- SITUATION should be general enough to match similar problems, not specific to this task
- ASSERTION should be specific and actionable, not generic advice
- Don't include task IDs, app names, or other specific identifiers in SITUATION
- Focus on the insight that enabled recovery, not the entire solution

Output format:

---AKU---
SITUATION: When [general problem description]
ASSERTION: Specific actionable advice that helped the agent recover
MODALITY: should
POLARITY: do
---END---

If no clear insight can be extracted, output: NO_AKU
"""

AKU_EXTRACTION_USER = """The agent was stuck/erroring, then recovered.

Stuck turn:
{stuck_turn}

Recovery turn:
{recovery_turn}

What insight enabled the recovery? Extract an AKU:"""
