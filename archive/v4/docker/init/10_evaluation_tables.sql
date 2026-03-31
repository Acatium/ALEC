-- Migration: 007_evaluation_tables
-- Description: Create tables for evaluation experiments, task results, and checkpoints
-- Created: 2025-11-21

-- Evaluation experiments
CREATE TABLE IF NOT EXISTS evaluation_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    experiment_type VARCHAR(50) NOT NULL,
    dataset_split VARCHAR(50) NOT NULL,
    learning_mode VARCHAR(20) NOT NULL DEFAULT 'disabled',  -- DEPRECATED: Learning now controlled via /agents service toggles
    config JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',
    success_rate FLOAT,
    tasks_completed INTEGER DEFAULT 0,
    tasks_total INTEGER DEFAULT 0,
    avg_iterations FLOAT,
    avg_tokens FLOAT,
    total_assertions INTEGER DEFAULT 0,
    passed_assertions INTEGER DEFAULT 0,
    comparison_group_id UUID,  -- Links experiments for A/B comparison
    -- Reproducibility columns
    llm_model VARCHAR(100),                 -- Model version (e.g., claude-haiku-4-5-20251001)
    llm_gateway_url VARCHAR(255),           -- LLM gateway endpoint
    evaluation_mode VARCHAR(20),            -- EVALUATION_MODE env var value
    codebase_commit VARCHAR(40),            -- Git commit hash at experiment start
    notes TEXT,                             -- Human-added context
    started_by VARCHAR(100),                -- User or service that initiated
    environment_snapshot JSONB,             -- Full environment capture
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for comparison groups
CREATE INDEX IF NOT EXISTS idx_eval_experiments_comparison_group ON evaluation_experiments(comparison_group_id);

-- Task results
CREATE TABLE IF NOT EXISTS evaluation_task_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID REFERENCES evaluation_experiments(id) ON DELETE CASCADE,
    task_id VARCHAR(50) NOT NULL,
    session_id UUID,
    success BOOLEAN NOT NULL,
    iterations INTEGER NOT NULL,
    tokens_used INTEGER,
    duration_ms INTEGER,
    bullets_used JSONB,
    error_message TEXT,
    test_results JSONB,  -- AppWorld ground truth evaluation (passes, failures, num_tests)
    task_description TEXT,  -- Human-readable task instruction
    created_at TIMESTAMP DEFAULT NOW()
);

-- Learning checkpoints
CREATE TABLE IF NOT EXISTS evaluation_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID REFERENCES evaluation_experiments(id) ON DELETE CASCADE,
    checkpoint_number INTEGER NOT NULL,
    tasks_completed INTEGER NOT NULL,
    success_rate FLOAT NOT NULL,
    avg_iterations FLOAT,
    avg_tokens FLOAT,
    bullet_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_eval_task_results_experiment ON evaluation_task_results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_eval_checkpoints_experiment ON evaluation_checkpoints(experiment_id);
CREATE INDEX IF NOT EXISTS idx_eval_experiments_status ON evaluation_experiments(status);
CREATE INDEX IF NOT EXISTS idx_eval_experiments_commit ON evaluation_experiments(codebase_commit);

-- Helper view: Experiment Configuration Summary for reproducibility analysis
CREATE OR REPLACE VIEW experiment_config_summary AS
SELECT
    id,
    name,
    experiment_type,
    dataset_split,
    learning_mode,
    llm_model,
    evaluation_mode,
    codebase_commit,
    status,
    success_rate,
    tasks_completed,
    tasks_total,
    config->>'task_limit' AS task_limit,
    config->>'turns_per_task' AS turns_per_task,
    config->>'checkpoint_interval' AS checkpoint_interval,
    config->>'grouping_strategy' AS grouping_strategy,
    started_at,
    completed_at,
    notes
FROM evaluation_experiments
ORDER BY started_at DESC;
