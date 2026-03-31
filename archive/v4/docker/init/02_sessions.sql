-- ============================================================================
-- ALEC Session Tables Initialization
-- ============================================================================
-- Creates sessions and session_outcomes tables for tracking chat sessions
-- and their effectiveness metrics
--
-- Run order: 02 (after 01_init_db.sql creates playbook_bullets)
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Sessions Table
-- ============================================================================
-- Tracks metadata for chat sessions (conversation history stored in LangGraph checkpoints)

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255),
    title VARCHAR,
    domain VARCHAR(100) NOT NULL DEFAULT 'chat',
    playbook_id UUID,  -- No FK constraint (playbooks table may not exist)
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    message_count INTEGER NOT NULL DEFAULT 0,
    -- Learning metrics for ALEC effectiveness tracking
    turns_to_success INTEGER,  -- Turn number when task was marked complete (null if ongoing/failed)
    problem_signature VARCHAR(255),  -- Hash of problem type for grouping similar problems
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sessions_domain ON sessions(domain);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_playbook_id ON sessions(playbook_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);
-- Learning effectiveness indexes
CREATE INDEX IF NOT EXISTS idx_sessions_problem_signature ON sessions(problem_signature);
CREATE INDEX IF NOT EXISTS idx_sessions_turns_to_success ON sessions(turns_to_success) WHERE turns_to_success IS NOT NULL;

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sessions_updated_at_trigger
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_sessions_updated_at();

-- ============================================================================
-- Session Outcomes Table
-- ============================================================================
-- Tracks effectiveness metrics and outcomes for completed sessions

CREATE TABLE IF NOT EXISTS session_outcomes (
    session_id UUID PRIMARY KEY,
    task_completed BOOLEAN NOT NULL,
    completion_confidence FLOAT NOT NULL,
    user_satisfaction INTEGER CHECK (user_satisfaction BETWEEN 1 AND 5),
    correction_count INTEGER NOT NULL DEFAULT 0,
    session_duration_seconds INTEGER,
    total_tokens INTEGER,
    total_cost_usd DECIMAL(10, 6),
    playbook_id UUID,  -- No FK constraint (playbooks table may not exist)
    outcome_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    outcome_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Foreign key to sessions table
    CONSTRAINT fk_session_outcomes_session
        FOREIGN KEY (session_id)
        REFERENCES sessions(session_id)
        ON DELETE CASCADE
);

-- Indexes for outcome queries
CREATE INDEX IF NOT EXISTS idx_session_outcomes_playbook_id ON session_outcomes(playbook_id);
CREATE INDEX IF NOT EXISTS idx_session_outcomes_timestamp ON session_outcomes(outcome_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_session_outcomes_task_completed ON session_outcomes(task_completed);

-- ============================================================================
-- Outcome Effectiveness Calculation Function
-- ============================================================================
-- Calculates overall effectiveness score from outcome metrics
-- Used by outcome_tracker.py and session_repository.py

CREATE OR REPLACE FUNCTION calculate_outcome_effectiveness(
    task_completed BOOLEAN,
    completion_confidence FLOAT,
    user_satisfaction INTEGER,
    correction_count INTEGER
) RETURNS FLOAT AS $$
DECLARE
    effectiveness_score FLOAT;
    completion_weight FLOAT := 0.4;
    confidence_weight FLOAT := 0.3;
    satisfaction_weight FLOAT := 0.2;
    correction_penalty_weight FLOAT := 0.1;

    completion_component FLOAT;
    confidence_component FLOAT;
    satisfaction_component FLOAT;
    correction_penalty FLOAT;
BEGIN
    -- Completion component (0.0 or 1.0)
    completion_component := CASE WHEN task_completed THEN 1.0 ELSE 0.0 END;

    -- Confidence component (already 0.0-1.0)
    confidence_component := COALESCE(completion_confidence, 0.5);

    -- Satisfaction component (1-5 scale normalized to 0.0-1.0)
    satisfaction_component := CASE
        WHEN user_satisfaction IS NULL THEN 0.5
        ELSE (user_satisfaction - 1.0) / 4.0
    END;

    -- Correction penalty (more corrections = lower score)
    -- Assume 5+ corrections = 0.0, linear decay
    correction_penalty := CASE
        WHEN correction_count >= 5 THEN 0.0
        ELSE 1.0 - (correction_count / 5.0)
    END;

    -- Weighted combination
    effectiveness_score := (
        completion_component * completion_weight +
        confidence_component * confidence_weight +
        satisfaction_component * satisfaction_weight +
        correction_penalty * correction_penalty_weight
    );

    -- Clamp to 0.0-1.0 range
    effectiveness_score := GREATEST(0.0, LEAST(1.0, effectiveness_score));

    RETURN effectiveness_score;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE sessions IS 'Chat session metadata. Conversation history stored in LangGraph checkpoints table.';
COMMENT ON COLUMN sessions.session_id IS 'Primary key, maps to LangGraph thread_id';
COMMENT ON COLUMN sessions.domain IS 'Domain classification (e.g., python-debugging, sql-optimization, chat)';
COMMENT ON COLUMN sessions.playbook_id IS 'Optional reference to playbook used (no FK constraint)';
COMMENT ON COLUMN sessions.status IS 'Session status: active, completed, failed';
COMMENT ON COLUMN sessions.message_count IS 'Total number of messages in conversation';

COMMENT ON TABLE session_outcomes IS 'Effectiveness metrics and outcomes for completed sessions';
COMMENT ON FUNCTION calculate_outcome_effectiveness IS 'Calculates weighted effectiveness score from multiple outcome metrics';
COMMENT ON COLUMN sessions.turns_to_success IS 'Turn number when task was completed (measures learning improvement)';
COMMENT ON COLUMN sessions.problem_signature IS 'Hash of problem type for grouping similar problems';

-- ============================================================================
-- Learning Effectiveness View
-- ============================================================================
-- Aggregates turns_to_success by problem_signature to measure learning improvement

CREATE OR REPLACE VIEW learning_effectiveness AS
SELECT
    problem_signature,
    domain,
    COUNT(*) as occurrences,
    AVG(turns_to_success) as avg_turns,
    MIN(turns_to_success) as best_turns,
    MAX(turns_to_success) as worst_turns,
    STDDEV(turns_to_success) as turns_stddev,
    -- Learning trend: compare first half vs second half of sessions
    CASE
        WHEN COUNT(*) >= 4 THEN
            'has_trend_data'
        ELSE
            'insufficient_data'
    END as trend_status,
    MIN(created_at) as first_occurrence,
    MAX(created_at) as last_occurrence
FROM sessions
WHERE turns_to_success IS NOT NULL
  AND problem_signature IS NOT NULL
GROUP BY problem_signature, domain
ORDER BY occurrences DESC;

COMMENT ON VIEW learning_effectiveness IS 'Aggregates session metrics by problem signature to measure learning improvement over time';

-- ============================================================================
-- End of Sessions Initialization
-- ============================================================================
