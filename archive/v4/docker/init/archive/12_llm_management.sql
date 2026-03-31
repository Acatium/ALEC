-- ============================================================================
-- LLM Management Tables
-- ============================================================================
-- Tables for centralized prompt management and cost tracking
--
-- Run order: 12 (after 11_auto_apply_settings.sql)
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Prompt Templates Table
-- ============================================================================
-- Centralized storage for LLM prompts used across services
-- Enables tuning prompts without code changes

CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_type VARCHAR(100) NOT NULL UNIQUE,
    template_text TEXT NOT NULL,
    description TEXT,
    variables JSONB NOT NULL DEFAULT '[]'::jsonb,  -- List of variable names expected
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for prompt lookups
CREATE INDEX IF NOT EXISTS idx_prompt_templates_task_type ON prompt_templates(task_type);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_active ON prompt_templates(is_active) WHERE is_active = true;

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_prompt_templates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prompt_templates_updated_at_trigger
    BEFORE UPDATE ON prompt_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_prompt_templates_updated_at();

-- ============================================================================
-- LLM Usage Log Table
-- ============================================================================
-- Tracks token usage and costs per LLM call for cost analysis

CREATE TABLE IF NOT EXISTS llm_usage_log (
    usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name VARCHAR(255) NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10, 6) NOT NULL,
    session_id UUID,  -- Optional link to session
    duration_ms INTEGER,  -- Call duration
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for usage analysis
CREATE INDEX IF NOT EXISTS idx_llm_usage_agent ON llm_usage_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_llm_usage_task_type ON llm_usage_log(task_type);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_session ON llm_usage_log(session_id) WHERE session_id IS NOT NULL;

-- ============================================================================
-- Cost Summary View
-- ============================================================================
-- Aggregates costs by agent and task type for dashboard

CREATE OR REPLACE VIEW llm_cost_summary AS
SELECT
    agent_name,
    task_type,
    model,
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as call_count,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cache_read_tokens) as total_cache_read_tokens,
    SUM(cost_usd) as total_cost_usd,
    AVG(duration_ms) as avg_duration_ms
FROM llm_usage_log
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY agent_name, task_type, model, DATE_TRUNC('hour', created_at)
ORDER BY hour DESC, total_cost_usd DESC;

-- ============================================================================
-- Daily Cost Summary View
-- ============================================================================
-- Daily aggregates for cost trending

CREATE OR REPLACE VIEW llm_daily_cost_summary AS
SELECT
    agent_name,
    DATE(created_at) as day,
    COUNT(*) as call_count,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cache_read_tokens) as total_cache_read_tokens,
    SUM(cost_usd) as total_cost_usd,
    AVG(cost_usd) as avg_cost_per_call
FROM llm_usage_log
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY agent_name, DATE(created_at)
ORDER BY day DESC, total_cost_usd DESC;

-- ============================================================================
-- Seed Default Prompt Templates
-- ============================================================================

INSERT INTO prompt_templates (task_type, template_text, description, variables) VALUES
('domain_classification',
'Classify the domain of this conversation based on the user message.
Return a specific, descriptive domain name (e.g., "python-exceptions", "react-state-management").

User message: {user_message}

Respond with ONLY the domain name, lowercase with hyphens, nothing else.',
'Classifies the domain of a user message',
'["user_message"]'::jsonb),

('bullet_generation',
'Generate relevant contextual bullets for a conversation in the {domain} domain.
The user is asking about: {context}

Generate 3-5 concise, actionable bullet points that would help guide the response.
Format as a JSON array of objects with "category" (cheat_sheets|constraints|examples|meta_prompts|solutions) and "content" fields.',
'Generates bullets for a given domain and context',
'["domain", "context"]'::jsonb),

('solution_extraction',
'Analyze this successful task and extract 1-3 SPECIFIC techniques that made it work.

REQUIREMENTS:
- Each bullet must be ACTIONABLE (tells exactly what to do)
- Include SPECIFIC details (function names, parameters, data locations)
- Avoid generic advice ("be careful", "check errors", "handle properly")
- Focus on non-obvious discoveries (API quirks, data locations, hidden steps)

Task: {task_description}

Solution:
{final_response}

Output ONLY the bullet points, one per line, no numbering or markers. Be specific.',
'Extracts solution patterns from successful task completions',
'["task_description", "final_response"]'::jsonb),

('effectiveness_assessment',
'Evaluate each bullet used in a conversation and determine if it was helpful, neutral, or harmful.

Assessment Criteria:
- HELPFUL: The bullet directly improved response quality, accuracy, or relevance
- NEUTRAL: The bullet had no significant impact on the response
- HARMFUL: The bullet led to incorrect, irrelevant, or poor quality content

Conversation:
{conversation}

Bullets used:
{bullets}

Respond with a JSON array of assessments, each with "bullet_id", "rating" (helpful/neutral/harmful), "confidence" (0.0-1.0), and "reasoning".',
'Assesses effectiveness of bullets used in a conversation',
'["conversation", "bullets"]'::jsonb)

ON CONFLICT (task_type) DO NOTHING;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE prompt_templates IS 'Centralized LLM prompts for consistency and easy tuning';
COMMENT ON COLUMN prompt_templates.task_type IS 'Unique identifier for the prompt type (e.g., domain_classification)';
COMMENT ON COLUMN prompt_templates.variables IS 'JSON array of variable names expected in the template';
COMMENT ON COLUMN prompt_templates.version IS 'Auto-incremented version number for change tracking';

COMMENT ON TABLE llm_usage_log IS 'Token usage and cost tracking for all LLM calls';
COMMENT ON COLUMN llm_usage_log.cache_read_tokens IS 'Tokens served from Anthropic prompt cache (90% cost savings)';
COMMENT ON COLUMN llm_usage_log.cost_usd IS 'Calculated cost including cache savings';

COMMENT ON VIEW llm_cost_summary IS 'Hourly cost aggregates by agent and task type (last 7 days)';
COMMENT ON VIEW llm_daily_cost_summary IS 'Daily cost aggregates by agent (last 30 days)';

-- ============================================================================
-- End of LLM Management Tables
-- ============================================================================
