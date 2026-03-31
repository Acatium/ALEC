-- ============================================================================
-- ALEC Playbooks Table Initialization
-- ============================================================================
-- Creates playbooks table for organizing bullet collections
--
-- NOTE: Modern approach uses playbook_bullets table (created in 01_init_db.sql)
--       This table provides metadata and grouping for bullet collections
--
-- Run order: 03 (after sessions table)
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Playbooks Table
-- ============================================================================
-- Metadata for organizing and tracking playbook effectiveness

CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Basic Information
    name VARCHAR(200) NOT NULL,
    description TEXT,
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    domain VARCHAR(50) NOT NULL,

    -- DEPRECATED: Old embedded bullets approach
    -- Modern approach: query playbook_bullets table by domain
    bullets_deprecated JSONB DEFAULT '[]'::jsonb,

    -- DEPRECATED: Legacy decision tree and context fields
    -- Kept for backward compatibility during migration period
    decision_tree JSONB NOT NULL DEFAULT '{}'::jsonb,
    context_requirements JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Confidence Tracking
    current_confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (current_confidence BETWEEN 0.0 AND 1.0),
    evidence_count INTEGER NOT NULL DEFAULT 0,

    -- Status Management
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'draft', 'deprecated')),
    deprecated_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Most common query: active playbooks by domain
CREATE INDEX IF NOT EXISTS idx_playbooks_domain ON playbooks(domain);
CREATE INDEX IF NOT EXISTS idx_playbooks_status ON playbooks(status);

-- Combined index for active playbooks in specific domain
CREATE INDEX IF NOT EXISTS idx_playbooks_domain_status ON playbooks(domain, status)
    WHERE status = 'active';

-- Confidence-based queries
CREATE INDEX IF NOT EXISTS idx_playbooks_confidence ON playbooks(current_confidence DESC);

-- Domain + confidence for best playbook selection
CREATE INDEX IF NOT EXISTS idx_playbooks_domain_confidence ON playbooks(domain, current_confidence DESC)
    WHERE status = 'active';

-- Temporal queries
CREATE INDEX IF NOT EXISTS idx_playbooks_created_at ON playbooks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_playbooks_updated_at ON playbooks(updated_at DESC);

-- ============================================================================
-- Triggers for Auto-Update
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_playbooks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER playbooks_updated_at_trigger
    BEFORE UPDATE ON playbooks
    FOR EACH ROW
    EXECUTE FUNCTION update_playbooks_updated_at();

-- Auto-set deprecated_at when status changes to deprecated
CREATE OR REPLACE FUNCTION set_playbooks_deprecated_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'deprecated' AND OLD.status != 'deprecated' THEN
        NEW.deprecated_at = NOW();
    ELSIF NEW.status != 'deprecated' THEN
        NEW.deprecated_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER playbooks_deprecated_at_trigger
    BEFORE UPDATE ON playbooks
    FOR EACH ROW
    EXECUTE FUNCTION set_playbooks_deprecated_at();

-- ============================================================================
-- Seed Data: Default Universal Playbook
-- ============================================================================
-- Creates a default "universal" domain playbook that can be used as fallback

INSERT INTO playbooks (
    name,
    description,
    version,
    domain,
    status,
    current_confidence,
    evidence_count
) VALUES (
    'Universal Conversational AI',
    'Default playbook for general conversational AI interactions. Provides baseline strategies for all domains.',
    '1.0.0',
    'GENERAL',
    'active',
    0.5,
    0
) ON CONFLICT (playbook_id) DO NOTHING;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE playbooks IS 'Playbook metadata for organizing bullet collections. Modern approach queries playbook_bullets table by domain.';
COMMENT ON COLUMN playbooks.bullets_deprecated IS 'DEPRECATED: Old embedded bullets. Use playbook_bullets table instead.';
COMMENT ON COLUMN playbooks.decision_tree IS 'DEPRECATED: Legacy decision tree structure. Kept for backward compatibility.';
COMMENT ON COLUMN playbooks.context_requirements IS 'DEPRECATED: Legacy context requirements. Kept for backward compatibility.';
COMMENT ON COLUMN playbooks.current_confidence IS 'Effectiveness confidence score (0.0-1.0) based on usage outcomes';
COMMENT ON COLUMN playbooks.evidence_count IS 'Number of times this playbook has been used in sessions';

-- ============================================================================
-- Helper View: Playbook Effectiveness Summary
-- ============================================================================
-- Provides quick access to playbook effectiveness metrics

CREATE OR REPLACE VIEW playbook_effectiveness_summary AS
SELECT
    p.playbook_id,
    p.name,
    p.domain,
    p.status,
    p.current_confidence,
    p.evidence_count,
    COUNT(DISTINCT so.session_id) AS total_sessions,
    AVG(
        calculate_outcome_effectiveness(
            so.task_completed,
            so.completion_confidence,
            so.user_satisfaction,
            so.correction_count
        )
    ) AS avg_outcome_effectiveness,
    COUNT(DISTINCT CASE WHEN so.task_completed THEN so.session_id END) AS successful_sessions,
    CASE
        WHEN COUNT(DISTINCT so.session_id) > 0
        THEN COUNT(DISTINCT CASE WHEN so.task_completed THEN so.session_id END)::float / COUNT(DISTINCT so.session_id)
        ELSE 0.0
    END AS success_rate
FROM playbooks p
LEFT JOIN session_outcomes so ON p.playbook_id = so.playbook_id
GROUP BY p.playbook_id, p.name, p.domain, p.status, p.current_confidence, p.evidence_count;

COMMENT ON VIEW playbook_effectiveness_summary IS 'Aggregated effectiveness metrics for each playbook based on session outcomes';

-- ============================================================================
-- End of Playbooks Initialization
-- ============================================================================
