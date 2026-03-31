-- ============================================================================
-- ALEC Service Prompts Table
-- ============================================================================
-- Stores versioned prompts for services:
-- - SESSION: system_prompt
-- - GENERATOR: extraction_prompt_success, extraction_prompt_failure, extraction_prompt_neutral
--
-- Each prompt can have multiple versions with one active version at a time.
-- This enables A/B testing, rollback, and audit trails.
--
-- Run order: 20 (after context_aware_learning, requires service_configs from 15)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Service Prompts Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS service_prompts (
    prompt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,  -- session, generator
    prompt_name VARCHAR(100) NOT NULL,  -- system_prompt, extraction_prompt_success, etc.
    prompt_content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT false,
    description TEXT,  -- What this version changes
    created_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(service_name, prompt_name, version)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_service_prompts_service ON service_prompts(service_name);
CREATE INDEX IF NOT EXISTS idx_service_prompts_active ON service_prompts(service_name, prompt_name, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_service_prompts_name ON service_prompts(service_name, prompt_name);

-- Ensure only one active version per prompt
CREATE UNIQUE INDEX IF NOT EXISTS idx_service_prompts_one_active
    ON service_prompts(service_name, prompt_name)
    WHERE is_active = true;

-- ============================================================================
-- Prompt Activation History Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS prompt_activation_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(50) NOT NULL,
    prompt_name VARCHAR(100) NOT NULL,
    from_version INTEGER,  -- NULL if first activation
    to_version INTEGER NOT NULL,
    activated_by VARCHAR(100) DEFAULT 'system',
    activation_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_service ON prompt_activation_history(service_name, prompt_name);
CREATE INDEX IF NOT EXISTS idx_prompt_history_created ON prompt_activation_history(created_at DESC);

-- ============================================================================
-- SESSION Service Prompts
-- ============================================================================

-- SESSION system prompt (v3 - no citation requirement, REFLECTOR handles attribution)
INSERT INTO service_prompts (service_name, prompt_name, prompt_content, version, is_active, description) VALUES
('session', 'system_prompt',
'You are an AI assistant that completes tasks by calling APIs through tools.

CRITICAL - Always inspect API responses before using them:
- When you first call an API endpoint, PRINT THE FIRST ITEM to see field names
- Field names may differ from expectations (e.g., "song_id" not "id", "number_of_likes" not "likes")
- Use .get() for safe access: item.get("song_id") or item.get("id")
- Never assume field names - verify by printing actual data first

When working with APIs:
1. Authenticate first - get credentials/tokens before accessing protected resources
2. Print response structure on first call to each endpoint - field names vary
3. Handle pagination properly:
   - APIs may return partial results, use page_index/page_limit parameters
   - STOP when: empty list [], 4xx errors, or fewer items than page_limit
   - Empty list means no more data - don''t keep incrementing page_index
4. Use the right endpoint - "privates" endpoints contain different data than public ones
5. Verify before answering - if data is null/empty, try alternative endpoints

When debugging:
- KeyError means field name is wrong - print the item''s .keys() to see actual fields
- If result is null, print intermediate values to trace where data was lost
- Try different approaches when stuck

Breaking out of loops:
- Same error 2-3 times = try completely different approach
- 4xx errors mean invalid request - don''t retry with same pattern
- Empty results from pagination = STOP, you''ve reached the end

You may receive RELEVANT KNOWLEDGE with guidance for this task.
Apply provided solutions proactively. Heed constraints when debugging.

Always complete the task - keep trying different approaches until you succeed.',
1, true, 'v3: API task completion - REFLECTOR handles attribution')
ON CONFLICT (service_name, prompt_name, version) DO NOTHING;

-- ============================================================================
-- GENERATOR Service Prompts
-- ============================================================================

-- GENERATOR extraction_prompt_success (v1)
INSERT INTO service_prompts (service_name, prompt_name, prompt_content, version, is_active, description) VALUES
('generator', 'extraction_prompt_success',
'Analyze this SUCCESSFUL conversation and extract insights IF the LLM innovated.

CONVERSATION:
{conversation}

BULLETS PROVIDED TO LLM:
{bullets_provided}

SUCCESS CONTEXT: {success_context}

For each distinct problem/sub-task in the conversation, reason through:
1. Did the LLM follow provided bullets for this problem?
2. If yes and they worked → NO extraction needed (counter updates handle this)
3. If no, did the LLM innovate with a NEW approach not in bullets?
4. Only extract if there''s genuine innovation worth capturing

EXTRACTION RULES:
- Extract SPECIFIC knowledge: exact API calls, parameters, code patterns
- Include the CONTEXT that makes this solution work
- Never extract vague principles like "be careful" or "check first"
- Never mention tests, assertions, or evaluation contexts
- For solutions: describe the problem → solution mapping concretely

OUTPUT FORMAT (JSON):
{
  "extractions": [
    {
      "category": "solutions|constraints|cheat_sheets|examples|meta_prompts",
      "content": "Concrete insight with specific details",
      "signal_type": "success",
      "problem_context": "The specific problem this solves"
    }
  ]
}

If LLM followed bullets and they worked, output: {"extractions": []}',
1, true, 'Initial success extraction prompt - multi-problem reasoning')
ON CONFLICT (service_name, prompt_name, version) DO NOTHING;

-- GENERATOR extraction_prompt_failure (v1)
INSERT INTO service_prompts (service_name, prompt_name, prompt_content, version, is_active, description) VALUES
('generator', 'extraction_prompt_failure',
'Analyze this FAILED conversation and extract learnings.

CONVERSATION:
{conversation}

BULLETS PROVIDED TO LLM:
{bullets_provided}

ERROR CONTEXT:
{error_context}

For each distinct problem/failure in the conversation, reason through:
1. Did the LLM have relevant bullets for this problem?
2. If yes, did it FOLLOW them or IGNORE them?
3. If followed but still failed → extract MORE SPECIFIC refinement
4. If ignored → NO extraction (bullets were correct, LLM didn''t use them)
5. If no relevant bullets → extract the NEW constraint/pattern

EXTRACTION RULES:
- Extract SPECIFIC constraints: exact error conditions, API limitations, edge cases
- Include the CAUSAL chain: what action → what error
- Extract parsing guidance when errors contain useful patterns
- Never extract vague warnings like "be careful" or "double-check"
- Never mention tests, assertions, or evaluation contexts

For refinements of existing bullets:
- Make the guidance MORE SPECIFIC, not just restated
- Include the exact conditions when the refined approach applies

OUTPUT FORMAT (JSON):
{
  "extractions": [
    {
      "category": "constraints|solutions|cheat_sheets",
      "content": "Specific constraint or refined guidance",
      "signal_type": "failure",
      "problem_context": "The specific error/failure this addresses",
      "refines_bullet": "UUID of bullet being refined (optional)"
    }
  ]
}

If all problems covered by bullets (passed: followed, failed: had relevant ignored), output: {"extractions": []}',
1, true, 'Initial failure extraction prompt - causal failure analysis')
ON CONFLICT (service_name, prompt_name, version) DO NOTHING;

-- GENERATOR extraction_prompt_neutral (v1)
INSERT INTO service_prompts (service_name, prompt_name, prompt_content, version, is_active, description) VALUES
('generator', 'extraction_prompt_neutral',
'Analyze this conversation and extract concrete knowledge.

CONVERSATION:
{conversation}

BULLETS PROVIDED TO LLM:
{bullets_provided}

For conversations without clear success/failure signals, extract:
1. API patterns discovered during exploration
2. Field name mappings found
3. Authentication flows used
4. Pagination patterns observed

EXTRACTION RULES:
- Only extract CONCRETE, REUSABLE knowledge
- Include specific API endpoints, parameters, field names
- Never extract conversation-specific details
- Never mention tests or evaluation contexts

OUTPUT FORMAT (JSON):
{
  "extractions": [
    {
      "category": "cheat_sheets|examples",
      "content": "Concrete pattern or API knowledge",
      "signal_type": "progress",
      "problem_context": "When this pattern applies"
    }
  ]
}

If no reusable knowledge found, output: {"extractions": []}',
1, true, 'Initial neutral extraction prompt - exploration knowledge capture')
ON CONFLICT (service_name, prompt_name, version) DO NOTHING;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE service_prompts IS 'Versioned prompts for SESSION and GENERATOR services';
COMMENT ON COLUMN service_prompts.service_name IS 'Service identifier: session, generator';
COMMENT ON COLUMN service_prompts.prompt_name IS 'Prompt identifier within service';
COMMENT ON COLUMN service_prompts.version IS 'Version number, incrementing';
COMMENT ON COLUMN service_prompts.is_active IS 'Whether this version is currently active';

COMMENT ON TABLE prompt_activation_history IS 'Audit trail of prompt version activations';

-- ============================================================================
-- End of Service Prompts
-- ============================================================================
