-- ============================================================================
-- Context-Aware Learning Migration
-- Phase 0.6: Similarity gating and contextual Thompson Sampling
-- ============================================================================

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. Add context_mismatch_count to playbook_bullets
-- ============================================================================
-- Tracks when bullets were used in wrong context (doesn't pollute effectiveness)

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'playbook_bullets' AND column_name = 'context_mismatch_count'
    ) THEN
        ALTER TABLE playbook_bullets
        ADD COLUMN context_mismatch_count INTEGER DEFAULT 0;
    END IF;
END $$;

COMMENT ON COLUMN playbook_bullets.context_mismatch_count IS
'Count of times bullet was used in wrong context (semantic similarity < threshold). Does not affect effectiveness_score.';

-- ============================================================================
-- 2. Create bullet_effectiveness_signals table
-- ============================================================================
-- Rich effectiveness signals for Librarian batch analysis
-- Captures multi-dimensional data: assessment + similarity + context relevance

CREATE TABLE IF NOT EXISTS bullet_effectiveness_signals (
    signal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bullet_id UUID REFERENCES playbook_bullets(bullet_id) ON DELETE CASCADE,
    session_id UUID,

    -- Effectiveness assessment
    assessment VARCHAR(20) NOT NULL CHECK (assessment IN ('helpful', 'neutral', 'harmful')),

    -- Context-awareness signals
    similarity_score FLOAT,  -- Cosine similarity between query and bullet embedding
    context_relevant BOOLEAN DEFAULT TRUE,  -- Was bullet semantically relevant?
    problem_signature VARCHAR(100),  -- Extracted from task_id (e.g., "024c982")

    -- Metadata
    source VARCHAR(50) DEFAULT 'effectiveness_reflector',  -- effectiveness_reflector, task_completed
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for Librarian batch queries
CREATE INDEX IF NOT EXISTS idx_bes_bullet ON bullet_effectiveness_signals(bullet_id);
CREATE INDEX IF NOT EXISTS idx_bes_created ON bullet_effectiveness_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bes_problem_sig ON bullet_effectiveness_signals(problem_signature);
CREATE INDEX IF NOT EXISTS idx_bes_context ON bullet_effectiveness_signals(context_relevant, created_at DESC);

COMMENT ON TABLE bullet_effectiveness_signals IS
'Rich effectiveness signals for Librarian batch analysis. Captures similarity_score and context_relevant flag.';

-- ============================================================================
-- 3. Create bullet_context_effectiveness table
-- ============================================================================
-- Per-(bullet, problem_signature) effectiveness counters for Contextual Thompson Sampling
-- Enables context-specific learning without polluting global scores

CREATE TABLE IF NOT EXISTS bullet_context_effectiveness (
    bullet_id UUID NOT NULL REFERENCES playbook_bullets(bullet_id) ON DELETE CASCADE,
    problem_signature VARCHAR(100) NOT NULL,

    -- Effectiveness counters (mirrors playbook_bullets)
    helpful_count INTEGER DEFAULT 0 CHECK (helpful_count >= 0),
    harmful_count INTEGER DEFAULT 0 CHECK (harmful_count >= 0),
    neutral_count INTEGER DEFAULT 0 CHECK (neutral_count >= 0),
    usage_count INTEGER DEFAULT 0 CHECK (usage_count >= 0),

    -- Metadata
    first_used_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (bullet_id, problem_signature)
);

-- Indexes for contextual Thompson Sampling queries
CREATE INDEX IF NOT EXISTS idx_bce_bullet ON bullet_context_effectiveness(bullet_id);
CREATE INDEX IF NOT EXISTS idx_bce_signature ON bullet_context_effectiveness(problem_signature);
CREATE INDEX IF NOT EXISTS idx_bce_last_used ON bullet_context_effectiveness(last_used_at DESC);

COMMENT ON TABLE bullet_context_effectiveness IS
'Per-context effectiveness counters for Contextual Thompson Sampling. Prevents cross-context pollution.';

-- ============================================================================
-- 4. Add configuration for context-aware learning
-- ============================================================================

INSERT INTO curation_config (key, value) VALUES
    ('context_aware_learning', '{
        "enabled": true,
        "similarity_threshold": 0.5,
        "min_context_observations": 3,
        "hierarchical_fallback": true
    }'::jsonb)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

COMMENT ON TABLE curation_config IS 'Global curation settings editable through the UI. Includes context_aware_learning config.';

-- ============================================================================
-- 5. Helper view: Context effectiveness summary
-- ============================================================================

CREATE OR REPLACE VIEW bullet_context_summary AS
SELECT
    bce.bullet_id,
    bce.problem_signature,
    bce.helpful_count,
    bce.harmful_count,
    bce.neutral_count,
    bce.usage_count,
    bce.last_used_at,
    pb.content,
    pb.domain,
    pb.category,
    pb.status,
    -- Calculated effectiveness for this context
    CASE
        WHEN (bce.helpful_count + bce.harmful_count + bce.neutral_count) = 0 THEN 0.5
        ELSE bce.helpful_count::float / (bce.helpful_count + bce.harmful_count + bce.neutral_count)
    END as context_effectiveness,
    -- Global effectiveness for comparison
    pb.effectiveness_score as global_effectiveness
FROM bullet_context_effectiveness bce
JOIN playbook_bullets pb ON bce.bullet_id = pb.bullet_id
ORDER BY bce.problem_signature, context_effectiveness DESC;

COMMENT ON VIEW bullet_context_summary IS
'Compares per-context effectiveness vs global effectiveness for each bullet.';

-- ============================================================================
-- 6. Helper view: Context mismatch analysis
-- ============================================================================

CREATE OR REPLACE VIEW context_mismatch_analysis AS
SELECT
    pb.bullet_id,
    pb.content,
    pb.domain,
    pb.category,
    pb.helpful_count,
    pb.harmful_count,
    pb.context_mismatch_count,
    pb.effectiveness_score,
    -- Mismatch ratio: high ratio suggests bullet is being used in wrong contexts
    CASE
        WHEN pb.usage_count = 0 THEN 0
        ELSE pb.context_mismatch_count::float / pb.usage_count
    END as mismatch_ratio
FROM playbook_bullets pb
WHERE pb.context_mismatch_count > 0
ORDER BY mismatch_ratio DESC;

COMMENT ON VIEW context_mismatch_analysis IS
'Identifies bullets frequently used in wrong contexts. High mismatch_ratio suggests retrieval issues.';

-- ============================================================================
-- End of Context-Aware Learning Migration
-- ============================================================================
