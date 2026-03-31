-- Evaluation-Side Tracking Tables (Phase 0.4)
-- Description: Evaluation's own tracking infrastructure (separate from ALEC core)
-- Created: 2025-11-25

-- Task Outcome Tracking (evaluation harness's perspective)
-- This table tracks ground truth outcomes from the evaluation harness
-- Maintains architectural separation: ALEC core never reads this table
CREATE TABLE IF NOT EXISTS evaluation_task_outcomes (
    outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL,
    task_id VARCHAR(100) NOT NULL,
    session_id UUID NOT NULL,  -- Reference only, never insert into ALEC's sessions table
    success BOOLEAN NOT NULL,
    turns_to_success INTEGER,  -- NULL if failed
    total_turns INTEGER NOT NULL,
    problem_signature VARCHAR(100),  -- e.g., "024c982" from "024c982_2"
    execution_log JSONB,  -- Full execution history for debugging
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for outcome analysis
CREATE INDEX IF NOT EXISTS idx_eval_outcomes_experiment ON evaluation_task_outcomes(experiment_id);
CREATE INDEX IF NOT EXISTS idx_eval_outcomes_task ON evaluation_task_outcomes(task_id);
CREATE INDEX IF NOT EXISTS idx_eval_outcomes_problem ON evaluation_task_outcomes(problem_signature);
CREATE INDEX IF NOT EXISTS idx_eval_outcomes_session ON evaluation_task_outcomes(session_id);
CREATE INDEX IF NOT EXISTS idx_eval_outcomes_success ON evaluation_task_outcomes(success);

-- Helper View: Problem Signature Success Rates
-- Shows performance across task variants (e.g., 024c982_1, 024c982_2, 024c982_3)
CREATE OR REPLACE VIEW problem_signature_performance AS
SELECT
    problem_signature,
    experiment_id,
    COUNT(*) as total_variants,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_variants,
    AVG(CASE WHEN success THEN turns_to_success ELSE NULL END) as avg_turns_when_successful,
    AVG(total_turns) as avg_total_turns,
    ROUND(SUM(CASE WHEN success THEN 1 ELSE 0 END)::numeric / COUNT(*)::numeric * 100, 2) as success_rate_pct
FROM evaluation_task_outcomes
GROUP BY problem_signature, experiment_id
ORDER BY success_rate_pct DESC, total_variants DESC;

-- Helper View: Learning Curve Data
-- Shows success rate progression as the experiment progresses
CREATE OR REPLACE VIEW learning_curve_view AS
SELECT
    experiment_id,
    task_id,
    problem_signature,
    success,
    turns_to_success,
    total_turns,
    created_at,
    ROW_NUMBER() OVER (PARTITION BY experiment_id ORDER BY created_at) as task_sequence,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) OVER (
        PARTITION BY experiment_id
        ORDER BY created_at
        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
    ) as rolling_success_rate_10
FROM evaluation_task_outcomes
ORDER BY experiment_id, created_at;

-- Helper View: Cross-Session Learning Analysis
-- Tracks performance on task variants to measure cross-session learning
CREATE OR REPLACE VIEW cross_session_learning_analysis AS
WITH variant_order AS (
    SELECT
        experiment_id,
        problem_signature,
        task_id,
        success,
        turns_to_success,
        ROW_NUMBER() OVER (
            PARTITION BY experiment_id, problem_signature
            ORDER BY created_at
        ) as variant_number
    FROM evaluation_task_outcomes
)
SELECT
    experiment_id,
    problem_signature,
    MAX(variant_number) as total_variants,
    AVG(CASE WHEN variant_number = 1 THEN (CASE WHEN success THEN 1.0 ELSE 0.0 END) END) as first_variant_success_rate,
    AVG(CASE WHEN variant_number > 1 THEN (CASE WHEN success THEN 1.0 ELSE 0.0 END) END) as later_variant_success_rate,
    AVG(CASE WHEN variant_number = 1 THEN turns_to_success END) as first_variant_avg_turns,
    AVG(CASE WHEN variant_number > 1 THEN turns_to_success END) as later_variant_avg_turns
FROM variant_order
GROUP BY experiment_id, problem_signature
HAVING MAX(variant_number) > 1  -- Only show problems with multiple variants
ORDER BY experiment_id, problem_signature;
